# app/agent/tools/get_portability_analysis.py
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def get_portability_analysis(user_id: str) -> str:
    """
    Análise de Portabilidade de Crédito (D6) — detecta contratos com taxa acima do mercado.

    Use esta ferramenta SEMPRE que o usuário perguntar sobre:
    - "Vale a pena portar meu crédito / empréstimo?"
    - "Minha taxa de empréstimo está cara?" / "Pago juros altos no meu financiamento"
    - "Posso portar para outro banco e pagar menos?"
    - "Como faço portabilidade de crédito?"
    - "Quanto economizaria em outro banco?"
    - "Meu empréstimo consignado / pessoal / veículo está abusivo"
    - "Quero simular portabilidade"
    - "É grátis pedir portabilidade?"
    - Qualquer dúvida sobre mudar o crédito de banco para pagar menos juros.

    Args:
        user_id: ID do usuário (obrigatório).
    """
    logger.info("[Tool] get_portability_analysis | user=%s", user_id)

    try:
        from app.defense.services.portability_detector import PortabilityDetector
        findings = PortabilityDetector().detect(user_id)
    except Exception as exc:
        logger.error("[Tool] get_portability_analysis error: %s", exc)
        findings = []

    lines = [
        "=== ANÁLISE DE PORTABILIDADE DE CRÉDITO (D6) ===",
        "Base legal: Res. CMN 5.057/2022 — portabilidade GRATUITA para o consumidor.",
        "Banco cedente tem 5 dias úteis para contraproposta.",
        "",
    ]

    if not findings:
        lines += [
            "✅ Nenhum contrato com taxa significativamente acima do benchmark detectado.",
            "",
            "Possíveis motivos:",
            "• Suas taxas já estão próximas à média de mercado — ótimo!",
            "• Não há dados de empréstimos conectados via Open Finance.",
            "  → Conecte sua conta ou informe a taxa contratada para análise precisa.",
            "",
            "💡 Mesmo sem dados conectados, você pode solicitar portabilidade diretamente",
            "no banco destino — é gratuita e o banco de origem tem 5 dias úteis para responder.",
        ]
        return "\n".join(lines)

    total_economy = sum(f.amount_disputed for f in findings)
    lines += [
        f"💰 {len(findings)} oportunidade(s) de portabilidade detectada(s)",
        f"   Economia estimada total: R$ {total_economy:.2f}",
        "",
    ]

    for f in findings:
        conf_pct = f"{f.confidence:.0%}" if hasattr(f, "confidence") and f.confidence else "—"
        lines += [
            f"🔵 {f.bank_name} — {f.title}",
            f"   {f.description[:250]}{'...' if len(f.description) > 250 else ''}",
            f"   Economia estimada: R$ {f.amount_disputed:.2f} | Confiança: {conf_pct}",
            "",
        ]
        if hasattr(f, "evidence_points") and f.evidence_points:
            for ev in f.evidence_points[:5]:
                lines.append(f"   • {ev}")
            lines.append("")

    lines += [
        "── Roteiro de Portabilidade (Res. CMN 5.057/2022) ──",
        "1. Entre em contato com o banco DESTINO informando:",
        "   modalidade, saldo devedor e prazo remanescente.",
        "2. O banco destino enviará proposta ao banco de origem.",
        "3. O banco de origem tem 5 dias úteis para contraproposta.",
        "4. Se a contraproposta for melhor, avalie aceitar.",
        "5. A transferência é GRATUITA por lei — nunca pague taxas.",
        "6. Se o banco cobrar qualquer taxa, registre no BACEN (bcb.gov.br/meubc).",
        "",
        "Para análise completa via API: GET /api/v1/defense/{user_id}/portability",
        "",
        "⚠️ Valores são estimativas. A aprovação depende da análise de crédito do banco destino.",
    ]

    return "\n".join(lines)
