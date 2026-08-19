"""
app/core/scheduler.py — Scheduler de jobs periódicos (APScheduler)

Jobs registrados:
  02h00  fee_snapshot            D2/D4  — snapshot de tarifas bancárias por usuário
  02h30  product_catalog_refresh OPP V2 — catálogo vivo via Open Finance Dados Abertos
  03h00  opportunity_scan        OPP    — detecta dinheiro parado para todos os usuários
  04h00  health_score_snapshot MX.1  — persiste score diário para histórico
  */6h   notification_scheduler MX.3 — gera notificações proativas sem o usuário abrir o app
  07h00  daily_digest          R1.c  — compila eventos do dia e envia por email
  seg 03h30 cards_curation_audit F2 — avisa quais cartões passaram do prazo de revisão

Controle:
  SCHEDULER_ENABLED=true  em produção ativa os jobs.
  Em development (padrão false) o scheduler sobe mas não agenda nada,
  permitindo disparar jobs manualmente via endpoint de admin.
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")


def register_jobs() -> None:
    """
    Registra todos os jobs no scheduler.
    Só deve ser chamado quando SCHEDULER_ENABLED=true.
    """
    from app.jobs.fee_snapshot import run_fee_snapshot
    from app.jobs.market_fees_refresh import run_market_fees_refresh
    from app.jobs.opportunity_scan import run_opportunity_scan
    from app.jobs.product_catalog_refresh import run_product_catalog_refresh
    from app.jobs.health_score_snapshot import run_health_score_snapshot
    from app.jobs.notification_scheduler import run_notification_scheduler
    from app.jobs.daily_digest import run_daily_digest
    from app.jobs.intelligence_metrics import run_intelligence_metrics
    from app.jobs.cards_curation_audit import run_cards_curation_audit

    # Semanal: a base de cartões é curada à mão e envelhece. O job não
    # corrige nada (não há fonte automática de metadados de cartão no
    # Brasil) — ele avisa o que vencer, enquanto a confiança já decai
    # sozinha via curation_freshness_factor.
    scheduler.add_job(
        run_cards_curation_audit,
        CronTrigger(day_of_week="mon", hour=3, minute=30),
        id="cards_curation_audit",
        name="Auditoria da Curadoria de Cartões (F2)",
        replace_existing=True,
        misfire_grace_time=6 * 3600,
    )
    scheduler.add_job(
        run_fee_snapshot,
        CronTrigger(hour=2, minute=0),
        id="fee_snapshot",
        name="Fee Snapshot Diário (D2/D4)",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        run_market_fees_refresh,
        CronTrigger(hour=2, minute=15),
        id="market_fees_refresh",
        name="Baseline de Tarifas de Mercado (F5/D4 via Open Finance)",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        run_product_catalog_refresh,
        CronTrigger(hour=2, minute=30),
        id="product_catalog_refresh",
        name="Refresh do Catálogo Open Finance (OPP V2)",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        run_opportunity_scan,
        CronTrigger(hour=3, minute=0),
        id="opportunity_scan",
        name="Radar de Oportunidades (OPP)",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        run_health_score_snapshot,
        CronTrigger(hour=4, minute=0),
        id="health_score_snapshot",
        name="Health Score Snapshot (MX.1)",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        run_notification_scheduler,
        CronTrigger(hour="*/6"),
        id="notification_scheduler",
        name="Notificações Proativas (MX.3)",
        replace_existing=True,
        misfire_grace_time=1800,
    )
    scheduler.add_job(
        run_intelligence_metrics,
        CronTrigger(hour=5, minute=30),
        id="intelligence_metrics",
        name="Métricas de Inteligência + Calibração (loops de feedback)",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        run_daily_digest,
        CronTrigger(hour=7, minute=0),
        id="daily_digest",
        name="Daily Digest (R1.c)",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    logger.info(
        "[Scheduler] %d jobs registrados: %s",
        len(scheduler.get_jobs()),
        [j.id for j in scheduler.get_jobs()],
    )
