"""
Testes dos cards de retenção (R2.c / R2.b / R1.a) no pipeline MX.3:
geradores → relevance filter → fingerprints do state store.
"""

from datetime import date, datetime, timezone

from app.notifications.notifier import (
    ChallengeInput,
    FiscalSeasonInput,
    Notification,
    NotificationContext,
    ProactiveNotifier,
    PurchaseFollowupInput,
    generate_challenge_notifications,
    generate_fiscal_season_notifications,
    generate_purchase_followup_notifications,
)
from app.notifications.relevance_filter import NotificationRelevanceFilter
from app.notifications.state_store import compute_fingerprint


def _fiscal(code="IR_DECLARACAO", days=30, obligation=True, **kw) -> FiscalSeasonInput:
    return FiscalSeasonInput(
        event_code=code,
        name="Evento fiscal",
        description="Descrição do evento.",
        action_hint="Faça algo.",
        deadline="2026-05-31",
        days_until_deadline=days,
        is_obligation=obligation,
        **kw,
    )


def _challenge(status="COMPLETED", pct=100.0, ctype="SEM_TARIFAS") -> ChallengeInput:
    return ChallengeInput(
        challenge_id="ch1",
        challenge_type=ctype,
        title="Mês sem tarifas",
        month="2026-07",
        status=status,
        pct_progress=pct,
        target_label="0 tarifas",
        detail="detalhe",
    )


def _followup(savings=45.0, tx="tx1") -> PurchaseFollowupInput:
    return PurchaseFollowupInput(
        transaction_id=tx,
        merchant="magalu",
        amount=2500.0,
        category="Eletrônicos",
        purchase_date="2026-07-05",
        paid_method_label="PIX à vista",
        best_method_label="Cartão Nubank à vista",
        potential_savings_brl=savings,
    )


# ── FISCAL_SEASON ────────────────────────────────────────────────────

class TestFiscalSeasonGenerator:
    def test_obrigacao_urgente_vira_warning(self):
        notes = generate_fiscal_season_notifications([_fiscal(days=5)])
        assert notes[0].priority == "WARNING"

    def test_obrigacao_distante_e_info(self):
        notes = generate_fiscal_season_notifications([_fiscal(days=30)])
        assert notes[0].priority == "INFO"

    def test_planejamento_nunca_e_warning(self):
        notes = generate_fiscal_season_notifications(
            [_fiscal(code="FGTS_LUCRO", days=2, obligation=False)]
        )
        assert notes[0].priority == "INFO"

    def test_nunca_critical(self):
        notes = generate_fiscal_season_notifications([_fiscal(days=0)])
        assert all(n.priority != "CRITICAL" for n in notes)

    def test_maximo_3_eventos_mais_urgentes_primeiro(self):
        inputs = [_fiscal(code=f"E{i}", days=days)
                  for i, days in enumerate([40, 5, 20, 10, 1])]
        notes = generate_fiscal_season_notifications(inputs)
        assert len(notes) == 3
        assert [n.metadata["days_until_deadline"] for n in notes] == [1, 5, 10]

    def test_labels_de_prazo(self):
        hoje = generate_fiscal_season_notifications([_fiscal(days=0)])[0]
        amanha = generate_fiscal_season_notifications([_fiscal(days=1)])[0]
        depois = generate_fiscal_season_notifications([_fiscal(days=9)])[0]
        assert "vence hoje" in hoje.title
        assert "vence amanhã" in amanha.title
        assert "faltam 9 dias" in depois.title

    def test_metadata_carrega_valor_estimado(self):
        evt = _fiscal(estimated_amount_brl=3000.0, is_personalized=True)
        notes = generate_fiscal_season_notifications([evt])
        assert notes[0].metadata["estimated_amount_brl"] == 3000.0
        assert notes[0].metadata["is_personalized"] is True


# ── CHALLENGE_* ──────────────────────────────────────────────────────

class TestChallengeGenerator:
    def test_completed_gera_card(self):
        notes = generate_challenge_notifications([_challenge("COMPLETED")])
        assert len(notes) == 1
        assert notes[0].type == "CHALLENGE_COMPLETED"
        assert "Desafio concluído" in notes[0].title

    def test_active_acima_de_70_gera_progress(self):
        notes = generate_challenge_notifications([_challenge("ACTIVE", pct=80.0)])
        assert len(notes) == 1
        assert notes[0].type == "CHALLENGE_PROGRESS"

    def test_active_abaixo_de_70_silencioso(self):
        assert generate_challenge_notifications([_challenge("ACTIVE", pct=50.0)]) == []

    def test_failed_nao_gera_card(self):
        assert generate_challenge_notifications([_challenge("FAILED", pct=0.0)]) == []

    def test_metadata_permite_fingerprint(self):
        n = generate_challenge_notifications([_challenge("COMPLETED")])[0]
        assert n.metadata["challenge_type"] == "SEM_TARIFAS"
        assert n.metadata["month"] == "2026-07"


# ── PURCHASE_FOLLOWUP ────────────────────────────────────────────────

class TestPurchaseFollowupGenerator:
    def test_gera_card_com_economia(self):
        notes = generate_purchase_followup_notifications([_followup(45.0)])
        assert len(notes) == 1
        assert notes[0].type == "PURCHASE_FOLLOWUP"
        assert notes[0].metadata["potential_savings_brl"] == 45.0

    def test_economia_minima_de_10_reais(self):
        assert generate_purchase_followup_notifications([_followup(5.0)]) == []

    def test_maximo_2_ordenados_por_economia(self):
        inputs = [_followup(20.0, "a"), _followup(90.0, "b"), _followup(50.0, "c")]
        notes = generate_purchase_followup_notifications(inputs)
        assert len(notes) == 2
        assert [n.metadata["transaction_id"] for n in notes] == ["b", "c"]

    def test_mensagem_tem_tom_de_aprendizado(self):
        n = generate_purchase_followup_notifications([_followup()])[0]
        assert "Modo Compra" in n.action_hint


# ── Orquestrador ─────────────────────────────────────────────────────

class TestOrquestrador:
    def test_contexto_completo_gera_os_tres_tipos(self):
        ctx = NotificationContext(
            fiscal_events=[_fiscal()],
            challenges=[_challenge("COMPLETED")],
            purchase_followups=[_followup()],
        )
        types = {n.type for n in ProactiveNotifier().generate(ctx)}
        assert {"FISCAL_SEASON", "CHALLENGE_COMPLETED", "PURCHASE_FOLLOWUP"} <= types

    def test_contexto_vazio_nao_gera_nada(self):
        assert ProactiveNotifier().generate(NotificationContext()) == []


# ── Relevance filter ─────────────────────────────────────────────────

def _note(type_: str, metadata: dict, priority: str = "INFO") -> Notification:
    return Notification(
        id="n1", type=type_, priority=priority, title="T", message="M",
        generated_at=datetime.now(timezone.utc), metadata=metadata,
    )


class TestRelevance:
    _rf = NotificationRelevanceFilter()

    def test_fiscal_dentro_da_janela_passa(self):
        n = _note("FISCAL_SEASON", {"days_until_deadline": 10})
        assert self._rf.filter([n], monthly_income=10_000.0) == [n]

    def test_challenge_completed_sempre_passa(self):
        n = _note("CHALLENGE_COMPLETED", {"pct_progress": 100.0})
        assert self._rf.filter([n], monthly_income=50_000.0) == [n]

    def test_followup_escala_com_renda(self):
        pequeno = _note("PURCHASE_FOLLOWUP", {"potential_savings_brl": 15.0})
        # renda alta → piso sobe (0.3% de 20k = R$60) → R$15 é ruído
        assert self._rf.filter([pequeno], monthly_income=20_000.0) == []
        # renda baixa → R$15 importa (piso mínimo R$10)
        assert self._rf.filter([pequeno], monthly_income=2_000.0) == [pequeno]


# ── Fingerprints ─────────────────────────────────────────────────────

class TestFingerprints:
    def test_fiscal_anual_estavel_no_ano(self):
        n = _note("FISCAL_SEASON", {"event_code": "IR_DECLARACAO"})
        assert compute_fingerprint("u1", n) == compute_fingerprint("u1", n)

    def test_das_distinto_de_evento_anual(self):
        das = _note("FISCAL_SEASON", {"event_code": "DAS_MEI"})
        ir = _note("FISCAL_SEASON", {"event_code": "IR_DECLARACAO"})
        assert compute_fingerprint("u1", das) != compute_fingerprint("u1", ir)

    def test_challenge_por_tipo_e_mes(self):
        a = _note("CHALLENGE_COMPLETED", {"challenge_type": "SEM_TARIFAS", "month": "2026-07"})
        b = _note("CHALLENGE_COMPLETED", {"challenge_type": "SEM_TARIFAS", "month": "2026-08"})
        c = _note("CHALLENGE_COMPLETED", {"challenge_type": "GUARDAR_VALOR", "month": "2026-07"})
        fps = {compute_fingerprint("u1", x) for x in (a, b, c)}
        assert len(fps) == 3

    def test_followup_por_transacao(self):
        a = _note("PURCHASE_FOLLOWUP", {"transaction_id": "tx1"})
        b = _note("PURCHASE_FOLLOWUP", {"transaction_id": "tx2"})
        assert compute_fingerprint("u1", a) != compute_fingerprint("u1", b)
        assert compute_fingerprint("u1", a) == compute_fingerprint("u1", a)
