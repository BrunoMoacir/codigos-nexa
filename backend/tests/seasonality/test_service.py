"""
Testes do SeasonalityService (R2.c) — personalização por perfil.

O perfil é injetado direto (sem banco): o service só decide filtragem por
audiência e enriquecimento de valores.
"""

from datetime import date

from app.seasonality.profile_probe import SeasonalProfile
from app.seasonality.service import SeasonalityService

_service = SeasonalityService()
_USER = "user_test"


def _events(today: date, profile: SeasonalProfile) -> dict:
    resp = _service.get_events(_USER, today=today, profile=profile)
    return {e.event_code: e for e in resp.events}


# ── Filtragem por audiência ──────────────────────────────────────────

class TestAudiencia:
    def test_sem_sinal_mei_nao_ve_das(self):
        events = _events(date(2026, 1, 15), SeasonalProfile())
        assert "DAS_MEI" not in events
        assert "DASN_SIMEI" not in events
        assert "IPVA_IPTU" in events          # audiência "all" permanece

    def test_mei_ve_das_e_dasn(self):
        events = _events(date(2026, 1, 15), SeasonalProfile(is_mei=True))
        assert "DAS_MEI" in events
        assert "DASN_SIMEI" in events

    def test_sem_salario_nao_ve_13o(self):
        events = _events(date(2026, 11, 15), SeasonalProfile())
        assert "DECIMO_PRIMEIRA" not in events

    def test_clt_ve_13o(self):
        profile = SeasonalProfile(has_salary=True, monthly_salary_brl=6000.0)
        events = _events(date(2026, 11, 15), profile)
        assert "DECIMO_PRIMEIRA" in events


# ── Personalização de valores ────────────────────────────────────────

class TestPersonalizacao:
    def test_13o_estimado_como_metade_do_salario(self):
        profile = SeasonalProfile(has_salary=True, monthly_salary_brl=6000.0)
        evt = _events(date(2026, 11, 15), profile)["DECIMO_PRIMEIRA"]
        assert evt.estimated_amount_brl == 3000.0
        assert evt.is_personalized is True

    def test_13o_sem_valor_quando_salario_desconhecido(self):
        profile = SeasonalProfile(has_salary=True, monthly_salary_brl=None)
        evt = _events(date(2026, 11, 15), profile)["DECIMO_PRIMEIRA"]
        assert evt.estimated_amount_brl is None
        assert evt.is_personalized is False

    def test_das_usa_ultimo_valor_pago(self):
        profile = SeasonalProfile(is_mei=True, last_das_amount_brl=76.9)
        evt = _events(date(2026, 1, 15), profile)["DAS_MEI"]
        assert evt.estimated_amount_brl == 76.9
        assert "76" in evt.description

    def test_ipva_usa_pago_ano_anterior(self):
        profile = SeasonalProfile(ipva_iptu_last_year_brl=2400.0)
        evt = _events(date(2026, 1, 15), profile)["IPVA_IPTU"]
        assert evt.estimated_amount_brl == 2400.0
        assert evt.is_personalized is True

    def test_ir_abaixo_do_teto_menciona_isencao(self):
        profile = SeasonalProfile(annual_income_brl=20_000.0)
        evt = _events(date(2026, 4, 10), profile)["IR_DECLARACAO"]
        assert "abaixo do teto" in evt.description

    def test_ir_acima_do_teto_e_obrigatorio(self):
        profile = SeasonalProfile(annual_income_brl=120_000.0)
        evt = _events(date(2026, 4, 10), profile)["IR_DECLARACAO"]
        assert "obrigatória" in evt.description

    def test_evento_generico_nao_afirma_valores(self):
        evt = _events(date(2026, 1, 15), SeasonalProfile())["IPVA_IPTU"]
        assert evt.estimated_amount_brl is None
        assert evt.is_personalized is False


# ── Resposta completa ────────────────────────────────────────────────

class TestResposta:
    def test_response_carrega_sinais_de_perfil(self):
        profile = SeasonalProfile(is_mei=True, has_salary=True)
        resp = _service.get_events(_USER, today=date(2026, 1, 15), profile=profile)
        assert resp.profile_signals == {"is_mei": True, "has_salary": True}
        assert resp.total == len(resp.events)
        assert resp.user_id == _USER

    def test_days_until_deadline_consistente(self):
        resp = _service.get_events(
            _USER, today=date(2026, 5, 20), profile=SeasonalProfile()
        )
        ir = next(e for e in resp.events if e.event_code == "IR_DECLARACAO")
        assert ir.days_until_deadline == 11   # 20/05 → 31/05
