# tests/opportunities/test_opp_notifications.py
"""
Ticket OPP4-D / Etapa 6 — cards de feed/notificações do OPP:
SAVINGS_BELOW_CDI (poupança abaixo do CDI, genérico) e
IDLE_MONEY_DETECTED (dinheiro parado confirmado).
"""
import pytest

from app.notifications.notifier import (
    IdleMoneyInput,
    NotificationContext,
    ProactiveNotifier,
    SavingsBelowCdiInput,
    generate_idle_money_notification,
    generate_savings_below_cdi_notification,
)
from app.notifications.state_store import _SEEN_TTL_DAYS, compute_fingerprint


def _savings_input(severity="HIGH"):
    return SavingsBelowCdiInput(
        savings_annual_pct=6.17,
        cdi_annual_pct=14.65,
        amount_reference_brl=10_000.0,
        estimated_loss_annual_brl=848.0,
        severity=severity,
        reason="Para cada R$ 10.000,00 na poupança, a diferença é de R$ 848,00/ano.",
    )


def _idle_input(gain=95.0):
    return IdleMoneyInput(
        idle_amount=12_000.0,
        monthly_loss=137.0,
        top_opportunity="Nubank CDB 100% CDI",
        top_gain_monthly_brl=gain,
    )


class TestSavingsBelowCdi:
    def test_gera_card_quando_severity_medium_ou_high(self):
        for severity in ("MEDIUM", "HIGH"):
            notes = generate_savings_below_cdi_notification(_savings_input(severity))
            assert len(notes) == 1
            assert notes[0].type == "SAVINGS_BELOW_CDI"
            assert notes[0].priority == "INFO"

    def test_nao_gera_card_com_severity_low(self):
        assert generate_savings_below_cdi_notification(_savings_input("LOW")) == []

    def test_nao_gera_card_sem_input(self):
        assert generate_savings_below_cdi_notification(None) == []

    def test_texto_usa_referencia_nao_saldo_presumido(self):
        """Regra do plano OPP.4: nunca afirmar saldo de poupança do usuário."""
        note = generate_savings_below_cdi_notification(_savings_input())[0]
        assert "você tem" not in note.message.lower().replace("se você tem", "")
        assert note.metadata["amount_reference_brl"] == 10_000.0


class TestIdleMoney:
    def test_gera_card_com_ganho_da_troca(self):
        notes = generate_idle_money_notification(_idle_input())
        assert len(notes) == 1
        assert notes[0].type == "IDLE_MONEY_DETECTED"
        assert "Nubank CDB 100% CDI" in notes[0].message

    def test_nao_gera_sem_input_ou_sem_ocioso(self):
        assert generate_idle_money_notification(None) == []
        zero = _idle_input()
        zero.idle_amount = 0.0
        assert generate_idle_money_notification(zero) == []


class TestIntegracaoComOrquestrador:
    def test_proactive_notifier_inclui_cards_opp(self):
        ctx = NotificationContext(
            savings_below_cdi=_savings_input(),
            idle_money=_idle_input(),
        )
        notes = ProactiveNotifier().generate(ctx)
        types = {n.type for n in notes}
        assert "SAVINGS_BELOW_CDI" in types
        assert "IDLE_MONEY_DETECTED" in types


class TestEstadoEDeduplicacao:
    def test_tipos_opp_tem_ttl_registrado(self):
        assert _SEEN_TTL_DAYS["SAVINGS_BELOW_CDI"] == 30
        assert _SEEN_TTL_DAYS["IDLE_MONEY_DETECTED"] == 14

    def test_fingerprint_estavel_dentro_do_mes(self):
        n1 = generate_savings_below_cdi_notification(_savings_input())[0]
        n2 = generate_savings_below_cdi_notification(_savings_input())[0]
        assert compute_fingerprint("u1", n1) == compute_fingerprint("u1", n2)

    def test_fingerprint_idle_agrupa_por_bucket_de_500(self):
        a, b = _idle_input(), _idle_input()
        na = generate_idle_money_notification(a)[0]
        b.idle_amount = 12_100.0  # mesmo bucket de R$500
        nb = generate_idle_money_notification(b)[0]
        assert compute_fingerprint("u1", na) == compute_fingerprint("u1", nb)


class TestRelevancia:
    def test_idle_money_filtrado_quando_ganho_irrisorio(self):
        from app.notifications.relevance_filter import NotificationRelevanceFilter

        big = generate_idle_money_notification(_idle_input(gain=95.0))
        small = generate_idle_money_notification(_idle_input(gain=1.0))
        f = NotificationRelevanceFilter()
        assert f.filter(big, monthly_income=5_000.0)
        assert not f.filter(small, monthly_income=5_000.0)
