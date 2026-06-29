# app/agent/tools/detect_abusive_fees.py
import logging

from langchain_core.tools import tool

from app.costs.bank_fee_analyzer import BankFeeAnalyzer
from app.core.db.queries import get_transactions_for_user

logger = logging.getLogger(__name__)


@tool
def detect_abusive_fees(user_id: str) -> str:
    """
    Detecta tarifas abusivas e venda casada (D1) — seguros embutidos em crédito.

    Use esta ferramenta SEMPRE que o usuário perguntar sobre:
    - "Estou pagando alguma tarifa abusiva?"
    - "O banco me cobrou um seguro que eu não pedi?"
    - "Venda casada — o banco me obrigou a contratar algo?"
    - "Quais tarifas posso questionar ou contestar?"
    - "Me cobram seguro junto com meu crédito, isso é legal?"
    - Qualquer suspeita de cobrança abusiva ou seguro embutido em produto financeiro.

    Args:
        user_id: ID do usuário (obrigatório).
    """
    logger.info("[Tool] detect_abusive_fees | user=%s", user_id)

    transactions_df = get_transactions_for_user(user_id)

    if transactions_df.is_empty():
        return (
            "Não encontrei histórico de transações para detectar tarifas abusivas. "
            "Conecte sua conta bancária via Open Finance."
        )

    try:
        report = BankFeeAnalyzer().analyze(transactions_df, user_id=user_id)
    except Exception as exc:
        logger.error("[Tool] detect_abusive_fees | erro na análise: %s", exc)
        return "Erro ao analisar tarifas. Tente novamente em alguns instantes."

    # ── Filtrar tipos suspeitos ───────────────────────────────────────
    ABUSIVE_TYPES = {
        "SEGURO_EMBUTIDO",      # venda casada — ilegal pela Resolução BACEN 3.919/2010
        "SEGURO_PRESTAMISTA",   # seguro de vida em crédito — frequentemente embutido
        "TARIFA_CADASTRO",      # cobrança de cadastro sem contratação explícita
    }

    abusive_entries = [
        fee for fee in report.entries
        if fee.fee_type.value in ABUSIVE_TYPES
    ]

    # ── Tarifas novas (apareceram sem histórico) ─────────────────────
    new_fees = BankFeeAnalyzer.detect_new_fees(user_id, report.entries)
    new_fee_keys = {(f.bank_name, f.fee_type.value) for f in new_fees}

    lines = ["=== DETECTOR DE TARIFAS ABUSIVAS (D1) ===", ""]

    if not abusive_entries and not new_fees:
        lines += [
            "✅ Nenhuma tarifa classificada como abusiva ou venda casada foi detectada.",
            "",
            "Continue monitorando — novas cobranças aparecem na próxima análise mensal.",
        ]
        return "\n".join(lines)

    # Venda casada / seguros embutidos
    if abusive_entries:
        lines += [
            f"⚠️ {len(abusive_entries)} tarifa(s) suspeita(s) de VENDA CASADA detectada(s):",
            "",
        ]
        for fee in abusive_entries:
            is_new = (fee.bank_name, fee.fee_type.value) in new_fee_keys
            new_tag = " 🆕 NOVA" if is_new else ""
            lines.append(
                f"• {fee.bank_name} — {fee.fee_type.value}{new_tag}: R$ {fee.amount:.2f}"
            )
            if fee.description:
                lines.append(f"  Descrição: {fee.description}")
        lines += [
            "",
            "Base legal: Resolução BACEN 3.919/2010 proíbe a exigência de contratação de seguro "
            "como condição para obtenção de crédito (venda casada).",
            "Ação recomendada: solicite ao banco o cancelamento e reembolso retroativo. "
            "Se negado, registre reclamação no Banco Central (bcb.gov.br/meubc) ou PROCON.",
        ]

    # Tarifas novas sem histórico
    truly_new = [f for f in new_fees if f.fee_type.value not in ABUSIVE_TYPES]
    if truly_new:
        lines += ["", f"🆕 {len(truly_new)} tarifa(s) nova(s) detectada(s) este mês:"]
        for fee in truly_new:
            lines.append(f"• {fee.bank_name} — {fee.fee_type.value}: R$ {fee.amount:.2f}")
        lines += [
            "",
            "Tarifas novas sem aviso prévio (30 dias) violam a Resolução BACEN 3.919/2010. "
            "Questione o banco por escrito e exija comprovante da notificação prévia.",
        ]

    lines += ["", "Fonte: análise de transações Pluggy + catálogo FeeType Nexa."]
    return "\n".join(lines)
