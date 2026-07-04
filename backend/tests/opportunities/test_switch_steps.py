# tests/opportunities/test_switch_steps.py
"""OPP.5 — passos práticos de troca (build_switch_steps)."""

from app.opportunities.services.switch_steps import build_switch_steps


class TestCdbLciLca:
    def test_cdb_liquidez_diaria_menciona_resgate_livre(self):
        steps = build_switch_steps(
            bank_name="Nubank", product_type="CDB", liquidity_days=1,
            min_amount=1.0, is_exempt=False, fgc_covered=True,
        )
        assert any("Nubank" in s for s in steps)
        assert any("PIX" in s for s in steps)
        assert any("Liquidez diária" in s for s in steps)
        assert any("IR" in s for s in steps)
        assert any("FGC" in s for s in steps)

    def test_produto_com_prazo_alerta_sobre_vencimento(self):
        steps = build_switch_steps(
            bank_name="Banco Inter", product_type="LCI", liquidity_days=360,
            min_amount=5_000.0, is_exempt=True, fgc_covered=True,
        )
        assert any("prazo" in s.lower() for s in steps)
        assert any("isento" in s.lower() for s in steps)

    def test_minimo_aparece_quando_relevante(self):
        steps = build_switch_steps(
            bank_name="XP Investimentos", product_type="CDB", liquidity_days=1,
            min_amount=1_000.0, is_exempt=False, fgc_covered=True,
        )
        assert any("1,000.00" in s or "1.000,00" in s for s in steps)

    def test_valor_acima_do_teto_fgc_gera_alerta_de_divisao(self):
        steps = build_switch_steps(
            bank_name="Sofisa Direto", product_type="CDB", liquidity_days=1,
            min_amount=1.0, is_exempt=False, fgc_covered=True, amount=300_000.0,
        )
        assert any("excede" in s for s in steps)


class TestTesouro:
    def test_tesouro_tem_fluxo_proprio_sem_fgc(self):
        steps = build_switch_steps(
            bank_name="Tesouro Direto", product_type="TESOURO_SELIC",
            liquidity_days=1, min_amount=150.0, is_exempt=False, fgc_covered=False,
        )
        assert any("Tesouro Selic" in s for s in steps)
        assert any("custódia" in s for s in steps)
        assert not any("FGC" in s for s in steps)
