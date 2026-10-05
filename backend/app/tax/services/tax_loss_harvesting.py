"""
app/tax/services/tax_loss_harvesting.py — T1: Tax-Loss Harvesting

Duas oportunidades:

1. **Harvest loss** — realizar perda para abater ganho tributável, SOMENTE nas
   classes em que a lei permite compensar.
2. **Hold longer** — segurar a posição até o próximo degrau da tabela
   regressiva, quando o degrau está perto.

O que estava errado, e é a razão de este arquivo ter sido reescrito:

**`hold_longer` disparava em 1 de 29 prazos.** `_next_bracket` devolvia a faixa
em que a posição JÁ estava, não a seguinte, e a comparação
`next_rate >= current_rate` matava todos os casos internos à faixa. Varredura
de 1 a 29 meses: só `holding_months == 6` passava — e nesse dizia "em 6
mês(es) a alíquota cai", quando aos 180 dias falta UM dia para os 181 que
mudam a faixa. Todo caso útil (faltando 1 ou 2 meses para o degrau) era
descartado em silêncio. A tabela agora vem de `parametros_fiscais`, em DIAS.

**`harvest_loss` estava invertido em relação à lei.** Não filtrava por classe
de ativo, então:

  • Ficava MUDO em ação/FII/ETF — o `estimated_ir` só era calculado quando
    havia taxa anual contratada, que a Pluggy não informa para renda variável;
    com `gains_ir == 0` o detector saía pela porta dos fundos. É justamente a
    classe em que a compensação existe.
  • DISPARAVA em renda fixa, onde compensação de prejuízo NÃO existe: o IR do
    CDB e do Tesouro é retido na fonte sobre o rendimento de cada operação, e
    a perda de um papel não abate o ganho de outro. A recomendação mandava
    resgatar realizando prejuízo por um benefício fiscal inexistente naquela
    classe — dano real, e irreversível.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from app.tax.models import InvestmentPosition, TaxOpportunity
from app.tax.parametros_fiscais import (
    BASE_LEGAL_COMPENSACAO,
    BASE_LEGAL_REGRESSIVA,
    ISENCAO_BOLSA_ALIENACOES_MES,
    aliquota_regressiva,
    classe_de_compensacao,
    ganho_de_bolsa_e_isento,
    proximo_degrau,
)
from app.core.formatacao import brl, numero

logger = logging.getLogger(__name__)

#: Acima disso, "segure mais um pouco" deixa de ser conselho acionável.
_JANELA_MAXIMA_DIAS = 180
#: Abaixo disso não vale interromper o usuário.
_ECONOMIA_MINIMA_BRL = 50.0

#: Classes cujo IR segue a tabela regressiva — as únicas em que esperar o
#: próximo degrau faz sentido. Ação e ETF são 15% lineares e FII é 20%
#: linear: não há degrau para esperar.
_CLASSES_COM_DEGRAU = {None, "fundo", "fundo_acoes"}

_ROTULO_CLASSE = {
    "bolsa": "ações e ETFs",
    "fii": "fundos imobiliários",
    "fundo": "fundos de investimento",
    "fundo_acoes": "fundos de ações",
}


class TaxLossHarvester:
    """Oportunidades de colheita de prejuízo e de espera por bracket."""

    def find_opportunities(
        self, positions: list[InvestmentPosition]
    ) -> list[TaxOpportunity]:
        opportunities: list[TaxOpportunity] = []
        opportunities.extend(self._find_harvest_loss(positions))
        opportunities.extend(self._find_hold_longer(positions))
        return opportunities

    # ── Harvest loss ─────────────────────────────────────────────────

    def _find_harvest_loss(
        self, positions: list[InvestmentPosition]
    ) -> list[TaxOpportunity]:
        results: list[TaxOpportunity] = []

        for chave, grupo in self._agrupar_por_classe(positions).items():
            classe, administradora = chave
            results.extend(self._harvest_de_um_grupo(classe, administradora, grupo))

        return results

    @staticmethod
    def _agrupar_por_classe(
        positions: list[InvestmentPosition],
    ) -> dict[tuple[str, str | None], list[InvestmentPosition]]:
        """
        Agrupa pelas fronteiras em que a compensação de fato acontece.

        Fundos só compensam entre fundos da MESMA administradora e mesma
        classificação tributária, então entram no grupo com o nome da
        instituição junto. Ações/ETF e FII compensam dentro da própria
        categoria, no mercado inteiro.
        """
        grupos: dict[tuple[str, str | None], list[InvestmentPosition]] = defaultdict(list)
        for pos in positions:
            if pos.is_exempt:
                continue
            classe = classe_de_compensacao(pos.product_type)
            if classe is None:
                continue  # renda fixa: perda não abate nada
            administradora = pos.bank_name if classe.startswith("fundo") else None
            grupos[(classe, administradora)].append(pos)
        return grupos

    def _harvest_de_um_grupo(
        self,
        classe: str,
        administradora: str | None,
        grupo: list[InvestmentPosition],
    ) -> list[TaxOpportunity]:
        perdas = [p for p in grupo if p.unrealized_gain < 0]
        ganhos = [p for p in grupo if p.unrealized_gain > 0]
        if not perdas or not ganhos:
            return []

        ir_dos_ganhos = round(sum(p.estimated_ir for p in ganhos), 2)
        if ir_dos_ganhos <= 0:
            return []

        # Ações e ETFs: se a venda inteira das posições com ganho couber na
        # isenção mensal, não há IR a abater — e realizar prejuízo para
        # compensar um ganho ISENTO é perda pura.
        if classe == "bolsa":
            total_alienado = sum(p.current_balance for p in ganhos)
            if ganho_de_bolsa_e_isento(total_alienado):
                logger.info(
                    "[harvest] grupo bolsa ignorado: R$ %.2f de alienação cabe na "
                    "isenção mensal de R$ %.2f",
                    total_alienado, ISENCAO_BOLSA_ALIENACOES_MES,
                )
                return []

        perda_total = round(abs(sum(p.unrealized_gain for p in perdas)), 2)
        ganho_total = round(sum(p.unrealized_gain for p in ganhos), 2)
        abatimento = min(perda_total, ganho_total)
        if abatimento <= 0:
            return []

        # Fração do ganho que a perda cobre × IR desse ganho. Substitui a
        # "alíquota do prazo MÉDIO das posições com ganho", que errava quando
        # a carteira tinha prazos dispersos: aqui cada posição já contribuiu
        # com o IR da sua própria alíquota.
        economia_total = round(ir_dos_ganhos * (abatimento / ganho_total), 2)
        if economia_total < _ECONOMIA_MINIMA_BRL:
            return []

        escopo = _ROTULO_CLASSE.get(classe, classe)
        if administradora:
            escopo = f"{escopo} da {administradora}"

        results: list[TaxOpportunity] = []
        for pos in perdas:
            perda = round(abs(pos.unrealized_gain), 2)
            parcela = round(economia_total * (perda / perda_total), 2)
            results.append(
                TaxOpportunity(
                    opportunity_type="harvest_loss",
                    title=f"Colheita de perda — {pos.product_type} {pos.bank_name}",
                    description=(
                        f"Posição com perda não realizada de {brl(perda)}. "
                        f"Nesta carteira há {brl(ganho_total)} de ganho tributável em "
                        f"{escopo}, com {brl(ir_dos_ganhos)} de IR. Realizar a perda "
                        f"abate parte desse ganho e economiza cerca de "
                        f"{brl(parcela)} de IR."
                    ),
                    position_ref=f"{pos.bank_name} — {pos.product_name}",
                    recommended_action=(
                        f"Resgatar a posição (perda de {brl(perda)}) e reinvestir em "
                        f"ativo equivalente. A perda abate ganhos de {escopo} apurados no "
                        f"mesmo mês, e o saldo não usado fica acumulado para os meses "
                        f"seguintes. {BASE_LEGAL_COMPENSACAO}"
                    ),
                    estimated_tax_saving_brl=parcela,
                    confidence="medium",
                )
            )
        return results

    # ── Hold longer ──────────────────────────────────────────────────

    def _find_hold_longer(
        self, positions: list[InvestmentPosition]
    ) -> list[TaxOpportunity]:
        results: list[TaxOpportunity] = []

        for pos in positions:
            if pos.is_exempt or pos.unrealized_gain <= 0:
                continue
            if classe_de_compensacao(pos.product_type) not in _CLASSES_COM_DEGRAU:
                continue  # ação/ETF (15%) e FII (20%) não têm degrau de prazo

            dias, exato = pos.dias_aplicados()
            degrau = proximo_degrau(dias)
            if degrau is None:
                continue
            faltam_dias, nova_aliquota = degrau
            aliquota_atual = aliquota_regressiva(dias)
            if faltam_dias > _JANELA_MAXIMA_DIAS:
                continue

            economia = round(pos.unrealized_gain * (aliquota_atual - nova_aliquota), 2)
            if economia < _ECONOMIA_MINIMA_BRL:
                continue

            results.append(
                TaxOpportunity(
                    opportunity_type="hold_longer",
                    title=f"Aguardar bracket de IR — {pos.product_type} {pos.bank_name}",
                    description=(
                        f"Resgate hoje: {numero(aliquota_atual*100, 1)}% de IR sobre o ganho de "
                        f"{brl(pos.unrealized_gain)}. "
                        f"{self._frase_prazo(faltam_dias, exato)} a alíquota cai para "
                        f"{numero(nova_aliquota*100, 1)}%. Economia estimada: {brl(economia)}."
                    ),
                    position_ref=f"{pos.bank_name} — {pos.product_name}",
                    recommended_action=(
                        f"Não resgatar {self._frase_prazo(faltam_dias, exato).lower()} "
                        f"para cair da faixa {numero(aliquota_atual*100, 1)}% → "
                        f"{numero(nova_aliquota*100, 1)}% de IR. {BASE_LEGAL_REGRESSIVA}"
                    ),
                    estimated_tax_saving_brl=economia,
                    confidence="high" if exato else "medium",
                    action_deadline=self._deadline(faltam_dias, exato),
                )
            )

        return results

    @staticmethod
    def _frase_prazo(dias: int, exato: bool) -> str:
        if not exato:
            # Sem data de aplicação, o prazo vem de meses-calendário × 30 e
            # erra até ~15 dias. Prometer "faltam 3 dias" em cima disso seria
            # precisão inventada.
            meses = max(1, round(dias / 30))
            return f"Em cerca de {meses} mês(es)"
        if dias <= 1:
            return "Amanhã"
        if dias <= 45:
            return f"Em {dias} dias"
        return f"Em {dias} dias (~{dias // 30} meses)"

    @staticmethod
    def _deadline(dias: int, exato: bool) -> str:
        if not exato:
            return f"Não resgatar por aproximadamente {max(1, round(dias / 30))} mês(es)"
        return f"Não resgatar pelos próximos {dias} dia(s)"


__all__ = ["TaxLossHarvester"]
