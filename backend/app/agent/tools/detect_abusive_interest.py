# app/agent/tools/detect_abusive_interest.py
import logging

from langchain_core.tools import tool

from app.core.db.queries import get_transactions_for_user

logger = logging.getLogger(__name__)


@tool
def detect_abusive_interest(user_id: str) -> str:
    """
    Detecta juros acima da taxa média de mercado publicada pelo BACEN (D3).

    Use esta ferramenta SEMPRE que o usuário perguntar sobre:
    - "Estou pagando juros abusivos?"
    - "Meus juros estão acima da média do mercado?"
    - "O banco cobra mais de 10% ao mês no rotativo?"
    - "Cheque especial com juros absurdos — o que faço?"
    - "Como sei se estou pagando juros ilegais?"
    - "Meus juros de cartão estão abusivos?"
    - Qualquer dúvida sobre taxas de juros abusivas ou acima da taxa BACEN.

    Args:
        user_id: ID do usuário (obrigatório).
    """
    logger.info("[Tool] detect_abusive_interest | user=%s", user_id)

    # ── 1. Buscar taxas de mercado BACEN (SGS) ───────────────────────
    market_rates = _get_market_rates()

    # ── 2. Analisar oportunidades de negociação existentes ───────────
    high_interest_opps = _get_high_interest_opportunities(user_id)

    # ── 3. Buscar tarifas de juros nas transações ────────────────────
    transactions_df = get_transactions_for_user(user_id)
    detected_interest_fees = _extract_interest_fees(transactions_df)

    lines = [
        "=== DETECTOR DE JUROS ABUSIVOS (D3) ===",
        "",
        "── Taxas de Referência BACEN (SGS) ──",
        f"Crédito Rotativo PF (média mercado): {market_rates['rotativo_pct']:.2f}% a.m.",
        f"Crédito Rotativo PF (máximo mercado): {market_rates['rotativo_max_pct']:.2f}% a.m.",
        f"Cheque Especial (média mercado):       {market_rates['cheque_pct']:.2f}% a.m.",
        "",
    ]

    has_finding = False

    # Oportunidades detectadas pelo NegotiationOpportunityDetector
    rotativo_opps = [o for o in high_interest_opps if "ROTATIVO" in o.get("trigger", "")]
    cheque_opps   = [o for o in high_interest_opps if "CHEQUE"   in o.get("trigger", "")]

    if rotativo_opps:
        has_finding = True
        lines += [
            f"⚠️ Crédito Rotativo acima da média de mercado detectado:",
        ]
        for opp in rotativo_opps:
            lines.append(
                f"  • {opp['bank_name']}: "
                f"economia potencial R$ {opp['gain']:.2f}/mês "
                f"se migrar para o limite da série BACEN"
            )
        lines += [
            "  → Exija portabilidade de crédito (gratuita por lei) ou negocie redução via roteiro Nexa.",
            "",
        ]

    if cheque_opps:
        has_finding = True
        lines += [
            f"⚠️ Cheque Especial acima da média de mercado detectado:",
        ]
        for opp in cheque_opps:
            lines.append(
                f"  • {opp['bank_name']}: "
                f"economia potencial R$ {opp['gain']:.2f}/mês"
            )
        lines += [
            "  → O cheque especial é o crédito mais caro do mercado. "
            "Use o Negociador para reduzir a taxa ou migrar para crédito consignado/pessoal.",
            "",
        ]

    # Juros detectados nas transações (descrições com palavras-chave)
    if detected_interest_fees:
        has_finding = True
        lines += [
            f"💳 {len(detected_interest_fees)} cobrança(s) de juros identificada(s) nas transações:",
        ]
        for bank, desc, amount in detected_interest_fees:
            lines.append(f"  • {bank}: {desc} — R$ {amount:.2f}")
        lines.append("")

    if not has_finding:
        lines += [
            "✅ Nenhum indício de juros acima da média BACEN detectado nas suas transações recentes.",
            "",
            "Continue sem usar o crédito rotativo — é o caminho mais eficiente para manter "
            "o score alto e ter poder de barganha para negociar taxas futuras.",
        ]
    else:
        lines += [
            "── O que fazer ──",
            "1. Use a ferramenta get_negotiation_script para obter o roteiro completo de negociação.",
            "2. Solicite portabilidade de crédito — gratuita pela Resolução BACEN 3.401/2006.",
            "3. Se o banco negar redução, registre reclamação no Banco Central (bcb.gov.br/meubc).",
            "4. Para rotativo acumulado, avalie renegociação via SERASA Limpa Nome ou CPC do banco.",
        ]

    lines += [
        "",
        f"Fonte: BACEN SGS séries 20714 (rotativo PF) e 20706 (cheque especial). "
        f"Dados: {market_rates['date_ref']}.",
    ]

    return "\n".join(lines)


# ── Helpers ──────────────────────────────────────────────────────────

def _get_market_rates() -> dict:
    """Busca taxas BACEN via BacenCreditConnector; fallback para valores históricos."""
    try:
        from app.architect.connectors.bacen_credit import BacenCreditConnector
        rates = BacenCreditConnector().get_rates()
        return {
            "rotativo_pct":     rates["rotativo_monthly"] * 100,
            "rotativo_max_pct": rates["rotativo_max_monthly"] * 100,
            "cheque_pct":       rates["cheque_especial_monthly"] * 100,
            "date_ref":         "último dado BACEN disponível",
        }
    except Exception as exc:
        logger.debug("[detect_abusive_interest] BacenCreditConnector indisponível: %s", exc)
        return {
            "rotativo_pct":     15.67,
            "rotativo_max_pct": 17.70,
            "cheque_pct":       10.80,
            "date_ref":         "fallback histórico (BACEN indisponível)",
        }


def _get_high_interest_opportunities(user_id: str) -> list[dict]:
    """Recupera oportunidades de tipo JUROS_ROTATIVO_ALTO e CHEQUE_ESPECIAL_ALTO."""
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text
        from datetime import date, timedelta

        cutoff = date.today() - timedelta(days=90)
        with SessionLocal() as db:
            rows = db.execute(
                text(
                    "SELECT bank_name, trigger_type, potential_gain FROM negotiation_history"
                    " WHERE user_id = :uid"
                    "   AND trigger_type IN ('JUROS_ROTATIVO_ALTO', 'CHEQUE_ESPECIAL_ALTO')"
                    "   AND generated_at >= :cutoff"
                    " ORDER BY potential_gain DESC LIMIT 5"
                ),
                {"uid": user_id, "cutoff": cutoff},
            ).fetchall()
        return [
            {"bank_name": r[0], "trigger": r[1], "gain": float(r[2]) if r[2] else 0.0}
            for r in rows
        ]
    except Exception as exc:
        logger.debug("[detect_abusive_interest] _get_high_interest_opportunities: %s", exc)
        return []


def _extract_interest_fees(df) -> list[tuple[str, str, float]]:
    """Extrai linhas de transação com palavras-chave de juros do rotativo/cheque especial."""
    if df is None or df.is_empty():
        return []
    try:
        import polars as pl
        import unicodedata
        import re

        INTEREST_PATTERN = re.compile(
            r"\b(juro|encargo|rotativo|cheque especial|limite especial|financiamento)\b",
            re.IGNORECASE,
        )

        def _norm(s: str) -> str:
            return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()

        results = []
        desc_col = "description" if "description" in df.columns else None
        if desc_col is None:
            return []

        bank_col = "bank_name" if "bank_name" in df.columns else None
        amount_col = "amount" if "amount" in df.columns else None

        for row in df.filter(pl.col("amount") < 0).iter_rows(named=True):
            desc = row.get(desc_col, "") or ""
            if INTEREST_PATTERN.search(_norm(desc)):
                bank = row.get(bank_col, "Banco") if bank_col else "Banco"
                amount = abs(row.get(amount_col, 0.0)) if amount_col else 0.0
                results.append((bank, desc[:80], amount))

        return results[:10]
    except Exception as exc:
        logger.debug("[detect_abusive_interest] _extract_interest_fees: %s", exc)
        return []
