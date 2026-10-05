# app/agent/tools/detect_wrongful_charges.py
import logging
from datetime import date, timedelta

from app.agent.procedencia import com_procedencia, degradada
from langchain_core.tools import tool

from app.costs.bank_fee_analyzer import BankFeeAnalyzer
from app.core.db.queries import get_transactions_for_user
from app.core.formatacao import brl

logger = logging.getLogger(__name__)


@tool
def detect_wrongful_charges(user_id: str) -> str:
    """
    Detecta cobranças indevidas: tarifas duplicadas, após cancelamento ou sem contrato (D2).

    Use esta ferramenta SEMPRE que o usuário perguntar sobre:
    - "Estou sendo cobrado indevidamente?"
    - "O banco me cobrou algo que eu não contratei."
    - "Tenho cobrança duplicada na fatura?"
    - "Ainda me cobram depois que cancela conta / cartão."
    - "Como identifico cobranças erradas?"
    - "Tenho suspeita de fraude nas minhas tarifas."
    - Qualquer suspeita de cobrança sem autorização, duplicada ou pós-cancelamento.

    Args:
        user_id: ID do usuário (obrigatório).
    """
    logger.info("[Tool] detect_wrongful_charges | user=%s", user_id)

    transactions_df = get_transactions_for_user(user_id)

    if transactions_df.is_empty():
        return (
            "Não encontrei histórico de transações para verificar cobranças indevidas. "
            "Conecte sua conta bancária via Open Finance."
        )

    try:
        report = BankFeeAnalyzer().analyze(transactions_df, user_id=user_id)
    except Exception as exc:
        logger.error("[Tool] detect_wrongful_charges | erro: %s", exc)
        return degradada(
            "Erro ao analisar cobranças. Tente novamente.",
            "analise_falhou",
        )

    # ── 1. Tarifas novas (sem histórico — apareceram pela primeira vez) ──
    # `BankCostReport` não tem `.entries` — a lista de tarifas individuais
    # chama-se `fees_detected` (ver app/costs/models.py). O AttributeError
    # subia da tool para o agente: D1 e D2 nunca produziram um achado.
    new_fees = BankFeeAnalyzer.detect_new_fees(user_id, report.fees_detected)

    # ── 2. Duplicatas no mesmo mês (mesmo banco + mesmo fee_type, mais de 1x) ──
    from collections import Counter
    fee_count: Counter = Counter()
    for entry in report.fees_detected:
        fee_count[(entry.bank_name, entry.fee_type.value)] += 1
    duplicates = [(bank, ftype, cnt) for (bank, ftype), cnt in fee_count.items() if cnt > 1]

    # ── 3. Tarifas no mês atual de bancos sem transação recente ─────────
    stale_banks = _detect_stale_bank_charges(user_id, transactions_df)

    lines = ["=== DETECTOR DE COBRANÇAS INDEVIDAS (D2) ===", ""]

    if not new_fees and not duplicates and not stale_banks:
        lines += [
            "✅ Nenhuma cobrança indevida óbvia detectada no período analisado.",
            "",
            "Dica: revise sua fatura mensalmente — cobranças indevidas tendem a "
            "aparecer após cancelamentos ou mudanças de plano.",
        ]
        return com_procedencia(
            "\n".join(lines),
            fontes=report.data_sources,
            confianca=report.confidence_score,
            cobertura_meses=report.analysis_months,
        )

    # Tarifas novas
    if new_fees:
        lines += [
            f"🆕 {len(new_fees)} tarifa(s) nova(s) sem histórico anterior:",
        ]
        for fee in new_fees:
            lines.append(f"  • {fee.bank_name} — {fee.fee_type.value}: {brl(fee.amount)}")
        lines += [
            "  → Tarifas sem histórico podem indicar cobrança não autorizada ou mudança de plano.",
            "  → Exija do banco comprovante do contrato que autoriza essa tarifa.",
            "",
        ]

    # Duplicatas
    if duplicates:
        lines += [
            f"🔁 {len(duplicates)} tarifa(s) cobrada(s) mais de uma vez no mesmo mês:",
        ]
        for bank, ftype, cnt in duplicates:
            lines.append(f"  • {bank} — {ftype}: {cnt}x no mesmo mês")
        lines += [
            "  → Solicite estorno da cobrança duplicada com a descrição exata e data de cada lançamento.",
            "",
        ]

    # Bancos inativos cobrando
    if stale_banks:
        lines += [
            f"👻 {len(stale_banks)} banco(s) cobrando sem transações recentes (possível conta não encerrada):",
        ]
        for bank in stale_banks:
            lines.append(f"  • {bank}")
        lines += [
            "  → Verifique se a conta foi de fato encerrada. Se sim, exija estorno e certidão de quitação.",
            "",
        ]

    lines += [
        "── Como contestar ──",
        "1. Registre a ocorrência no atendimento do banco (guarde o protocolo).",
        "2. Se não resolvido em 5 dias úteis, registre no Banco Central (bcb.gov.br/meubc).",
        "3. Para cobranças acima de R$ 20, vale acionar o PROCON ou Juizado Especial Cível.",
        "",
        "Fonte: análise de transações Pluggy + histórico bank_fee_history Nexa.",
    ]

    return com_procedencia(
        "\n".join(lines),
        fontes=report.data_sources,
        confianca=report.confidence_score,
        cobertura_meses=report.analysis_months,
    )


def _detect_stale_bank_charges(user_id: str, df) -> list[str]:
    """
    Detecta bancos que aparecem em bank_fee_history mas não têm transações
    nos últimos 60 dias — possível conta não encerrada sendo cobrada.
    """
    try:
        import polars as pl

        date_col = "transaction_date" if "transaction_date" in df.columns else "date"
        cutoff = date.today() - timedelta(days=60)

        active_banks = set(
            df.filter(pl.col(date_col) >= cutoff)
            .select("bank_name")
            .unique()["bank_name"]
            .to_list()
        ) if "bank_name" in df.columns else set()

        from app.core.database import SessionLocal
        from sqlalchemy import text

        current_month = date.today().strftime("%Y-%m")
        with SessionLocal() as db:
            rows = db.execute(
                text(
                    "SELECT DISTINCT bank_name FROM bank_fee_history"
                    " WHERE user_id = :uid AND month = :month"
                ),
                {"uid": user_id, "month": current_month},
            ).fetchall()

        fee_banks = {r[0] for r in rows}
        return list(fee_banks - active_banks) if active_banks else []
    except Exception as exc:
        logger.debug("[detect_wrongful_charges] _detect_stale_bank_charges: %s", exc)
        return []
