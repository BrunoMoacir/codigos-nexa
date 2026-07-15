# tests/opportunities/test_bank_comparator.py
"""
Regra de liquidez para perfis frágeis (docs/OPP1_DINHEIRO_PARADO_PLANO.md,
seção 5.4 / checklist item "Produtos de baixa liquidez não são priorizados
para reserva protegida"):

  Para fss_level in {"ALERTA", "CRITICO"}, produtos sem liquidez diária
  (liquidity_days > 1) devem ficar abaixo de produtos com liquidez diária no
  ranking, mesmo que rendam mais líquido. Sem fss_level (ou SAUDAVEL/ATENCAO),
  o ranking continua puramente por annual_rate_net_pct, como antes.
"""
import pytest

from app.opportunities.services.bank_comparator import BankComparator

_CDI_ANNUAL = 0.1465  # ~14.65% a.a., mesmo valor usado como fallback no engine


@pytest.fixture(scope="module")
def comparator() -> BankComparator:
    return BankComparator()


def _top_eligible(ranked):
    return next(p for p in ranked if p.eligible)


class TestRankingPadraoSemFssLevel:
    def test_sem_fss_level_ordena_so_por_taxa_liquida(self, comparator):
        ranked = comparator.rank(amount=10_000, holding_months=12, cdi_annual=_CDI_ANNUAL)
        eligible = [p for p in ranked if p.eligible]
        rates = [p.annual_rate_net_pct for p in eligible]
        assert rates == sorted(rates, reverse=True)

    def test_fss_saudavel_nao_prioriza_liquidez(self, comparator):
        """SAUDAVEL/ATENCAO não são frágeis — comportamento idêntico ao padrão."""
        sem_fss = comparator.rank(amount=10_000, holding_months=12, cdi_annual=_CDI_ANNUAL)
        com_saudavel = comparator.rank(
            amount=10_000, holding_months=12, cdi_annual=_CDI_ANNUAL, fss_level="SAUDAVEL"
        )
        assert [p.bank_name for p in sem_fss] == [p.bank_name for p in com_saudavel]


class TestPrioridadeDeLiquidezParaPerfilFragil:
    @pytest.mark.parametrize("fss_level", ["ALERTA", "CRITICO"])
    def test_top_pick_tem_liquidez_diaria_mesmo_com_taxa_menor(self, comparator, fss_level):
        # amount baixo o bastante para não restringir elegibilidade
        ranked = comparator.rank(
            amount=100, holding_months=12, cdi_annual=_CDI_ANNUAL, fss_level=fss_level
        )
        top = _top_eligible(ranked)
        assert top.liquidity_days <= 1

    def test_produto_de_baixa_liquidez_com_taxa_maior_existe_no_catalogo(self, comparator):
        """Confirma a premissa do teste acima: sem proteção de liquidez, o
        melhor produto do catálogo para este valor NÃO tem liquidez diária —
        senão o teste anterior não provaria nada."""
        ranked = comparator.rank(amount=100, holding_months=12, cdi_annual=_CDI_ANNUAL)
        top_sem_protecao = _top_eligible(ranked)
        assert top_sem_protecao.liquidity_days > 1

    def test_liquidez_diaria_ainda_ordenada_por_taxa_entre_si(self, comparator):
        """Dentro do grupo 'liquidez diária', a ordem continua por taxa líquida."""
        ranked = comparator.rank(
            amount=100, holding_months=12, cdi_annual=_CDI_ANNUAL, fss_level="CRITICO"
        )
        daily = [p for p in ranked if p.eligible and p.liquidity_days <= 1]
        rates = [p.annual_rate_net_pct for p in daily]
        assert rates == sorted(rates, reverse=True)

    def test_elegibilidade_continua_acima_de_liquidez(self, comparator):
        """min_amount alto o bastante para tornar produtos de liquidez diária
        inelegíveis — eles devem ir para o fim mesmo assim, não furar a fila
        por causa da liquidez."""
        ranked = comparator.rank(
            amount=1.0, holding_months=12, cdi_annual=_CDI_ANNUAL, fss_level="CRITICO"
        )
        eligible_flags = [p.eligible for p in ranked]
        # todos os elegíveis vêm antes de todos os inelegíveis
        assert eligible_flags == sorted(eligible_flags, reverse=True)
