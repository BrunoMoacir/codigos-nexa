"""
Testes do calendário fiscal puro (R2.c) — app/seasonality/fiscal_calendar.py

Funções sem I/O: cada teste fixa uma data de referência e verifica quais
janelas estão ativas, os deadlines e a ordenação.
"""

from datetime import date

from app.seasonality.fiscal_calendar import active_events


def _codes(today: date) -> list[str]:
    return [e.event_code for e in active_events(today)]


# ── Janelas por época do ano ─────────────────────────────────────────

class TestJanelasAtivas:
    def test_abril_tem_ir_e_dasn(self):
        codes = _codes(date(2026, 4, 10))
        assert "IR_DECLARACAO" in codes
        assert "DASN_SIMEI" in codes
        assert "IPVA_IPTU" not in codes       # janela acabou em 28/02
        assert "DECIMO_PRIMEIRA" not in codes

    def test_janeiro_meio_do_mes_tem_ipva_dasn_e_das(self):
        codes = _codes(date(2026, 1, 15))     # dia 15 ∈ [13, 20] → DAS ativo
        assert "IPVA_IPTU" in codes
        assert "DASN_SIMEI" in codes
        assert "DAS_MEI" in codes
        assert "IR_DECLARACAO" not in codes   # só a partir de 01/03

    def test_janeiro_inicio_do_mes_nao_tem_das(self):
        codes = _codes(date(2026, 1, 5))      # antes do dia 13
        assert "DAS_MEI" not in codes

    def test_novembro_tem_primeira_parcela_13o(self):
        codes = _codes(date(2026, 11, 15))
        assert "DECIMO_PRIMEIRA" in codes
        assert "DECIMO_SEGUNDA" not in codes

    def test_dezembro_ate_dia_20_tem_segunda_parcela_13o(self):
        codes = _codes(date(2026, 12, 10))
        assert "DECIMO_SEGUNDA" in codes
        assert "DECIMO_PRIMEIRA" not in codes

    def test_dezembro_depois_do_dia_20_sem_13o(self):
        codes = _codes(date(2026, 12, 28))
        assert "DECIMO_SEGUNDA" not in codes

    def test_julho_tem_fgts_lucro_e_das(self):
        codes = _codes(date(2026, 7, 20))
        assert "FGTS_LUCRO" in codes
        assert "DAS_MEI" in codes

    def test_maio_final_tem_ir_e_primeiro_lote_restituicao(self):
        codes = _codes(date(2026, 5, 25))
        assert "IR_DECLARACAO" in codes
        assert "IR_RESTITUICAO" in codes

    def test_no_maximo_um_lote_de_restituicao_por_vez(self):
        for d in (date(2026, 5, 25), date(2026, 6, 25), date(2026, 9, 25)):
            codes = _codes(d)
            assert codes.count("IR_RESTITUICAO") <= 1

    def test_inicio_de_junho_sem_eventos(self):
        # IR acabou (31/05), lote de junho só a partir de ~20/06, FGTS só 15/07
        assert _codes(date(2026, 6, 5)) == []


# ── Propriedades estruturais ─────────────────────────────────────────

class TestEstrutura:
    def test_eventos_ordenados_por_deadline(self):
        events = active_events(date(2026, 1, 15))
        deadlines = [e.deadline for e in events]
        assert deadlines == sorted(deadlines)

    def test_days_until_deadline(self):
        events = active_events(date(2026, 3, 1))
        ir = next(e for e in events if e.event_code == "IR_DECLARACAO")
        assert ir.days_until_deadline(date(2026, 3, 1)) == 91   # 01/03 → 31/05
        assert ir.days_until_deadline(date(2026, 5, 31)) == 0

    def test_obrigacoes_marcadas_corretamente(self):
        jan = {e.event_code: e for e in active_events(date(2026, 1, 15))}
        assert jan["DAS_MEI"].is_obligation is True
        assert jan["DASN_SIMEI"].is_obligation is True

        jul = {e.event_code: e for e in active_events(date(2026, 7, 25))}
        assert jul["FGTS_LUCRO"].is_obligation is False

    def test_audiencia_por_evento(self):
        jan = {e.event_code: e for e in active_events(date(2026, 1, 15))}
        assert jan["DAS_MEI"].audience == "mei"
        assert jan["IPVA_IPTU"].audience == "all"

        nov = {e.event_code: e for e in active_events(date(2026, 11, 10))}
        assert nov["DECIMO_PRIMEIRA"].audience == "clt"

    def test_restituicao_carrega_lote_no_metadata(self):
        events = active_events(date(2026, 7, 28))
        lote = next(e for e in events if e.event_code == "IR_RESTITUICAO")
        assert lote.metadata["lot_index"] == 3   # julho = 3º lote

    def test_funciona_em_ano_diferente(self):
        codes = _codes(date(2027, 4, 10))
        assert "IR_DECLARACAO" in codes
        ir = next(e for e in active_events(date(2027, 4, 10))
                  if e.event_code == "IR_DECLARACAO")
        assert ir.deadline == date(2027, 5, 31)
