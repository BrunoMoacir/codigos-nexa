# app/agent/tools/get_defense_analysis.py
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def get_defense_analysis(user_id: str, detectors: str = "d1,d2,d3,d4") -> str:
    """
    Análise completa de Defesa do Consumidor (D1–D4) — detecta irregularidades bancárias.

    Use esta ferramenta SEMPRE que o usuário perguntar sobre:
    - "Tenho cobranças irregulares / indevidas?"
    - "O banco está me cobrando algo que não deveria?"
    - "Existe venda casada na minha conta?" / "Me obrigaram a fazer um seguro"
    - "Meus juros estão abusivos / acima da média?"
    - "O banco aumentou minha tarifa sem avisar?"
    - "Quero ver tudo que pode estar errado na minha conta bancária"
    - "Defesa do consumidor" / "Meus direitos como cliente de banco"
    - "Tem alguma cobrança que posso contestar?"
    - "Me cobram tarifa de extrato / saque que deveria ser grátis"
    - Qualquer pergunta sobre irregularidades, abusos ou direitos bancários.

    Args:
        user_id:   ID do usuário (obrigatório).
        detectors: detectores a executar, separados por vírgula: d1,d2,d3,d4 (padrão: todos).
                   d1=venda casada, d2=cobranças indevidas, d3=juros abusivos, d4=aumento unilateral.
    """
    logger.info("[Tool] get_defense_analysis | user=%s detectors=%s", user_id, detectors)

    try:
        from app.defense.services.tied_sale_detector import TiedSaleDetector
        from app.defense.services.wrongful_charge_detector import WrongfulChargeDetector
        from app.defense.services.abusive_interest_detector import AbusiveInterestDetector
        from app.defense.services.unilateral_change_detector import UnilateralChangeDetector

        _detectors = {
            "d1": TiedSaleDetector(),
            "d2": WrongfulChargeDetector(),
            "d3": AbusiveInterestDetector(),
            "d4": UnilateralChangeDetector(),
        }

        selected = {d.strip().lower() for d in detectors.split(",")}
        valid = {"d1", "d2", "d3", "d4"}
        selected = selected & valid

        all_findings = []
        errors = []
        for key in ("d1", "d2", "d3", "d4"):
            if key not in selected:
                continue
            try:
                findings = _detectors[key].detect(user_id)
                all_findings.extend(findings)
            except Exception as exc:
                errors.append(f"{key}: {exc}")
                logger.error("[Tool] get_defense_analysis detector=%s: %s", key, exc)

    except Exception as exc:
        logger.error("[Tool] get_defense_analysis setup error: %s", exc)
        return (
            "Erro ao carregar detectores de defesa do consumidor. "
            "Verifique se o módulo defense está instalado corretamente."
        )

    lines = [
        "=== ANÁLISE DE DEFESA DO CONSUMIDOR (D1–D4) ===",
        "⚠️ Valores são ESTIMATIVAS educacionais — consulte advogado antes de acionar o JEC.",
        "",
    ]

    if not all_findings:
        lines += [
            "✅ Nenhuma irregularidade detectada nas análises realizadas.",
            "",
            "Continue monitorando mensalmente. Forneça mais histórico de transações",
            "para análise mais precisa.",
        ]
        if errors:
            lines += ["", f"(Alguns detectores retornaram erro: {'; '.join(errors)})"]
        return "\n".join(lines)

    total = sum(f.amount_disputed for f in all_findings)
    high   = [f for f in all_findings if f.severity == "high"]
    medium = [f for f in all_findings if f.severity == "medium"]
    low    = [f for f in all_findings if f.severity == "low"]

    lines += [
        f"🔍 {len(all_findings)} indício(s) detectado(s) | Estimativa total: R$ {total:.2f}",
        f"   Alta severidade: {len(high)} | Média: {len(medium)} | Baixa: {len(low)}",
        "",
    ]

    _LABELS = {
        "D1": "Venda Casada",
        "D2": "Cobrança Indevida",
        "D3": "Juros Abusivos",
        "D4": "Aumento Unilateral",
    }
    _SEVERITY_ICON = {"high": "🔴", "medium": "🟡", "low": "🟢", "info": "ℹ️"}

    for f in all_findings:
        icon = _SEVERITY_ICON.get(f.severity, "⚪")
        label = _LABELS.get(f.detector, f.detector)
        conf = f" | Confiança: {f.confidence:.0%}" if hasattr(f, "confidence") and f.confidence else ""
        lines += [
            f"{icon} [{label} — {f.bank_name}] {f.title}",
            f"   Estimativa contestável: R$ {f.amount_disputed:.2f}{conf}",
            f"   {f.description[:200]}{'...' if len(f.description) > 200 else ''}",
            f"   Base legal: {f.legal_basis[:120]}{'...' if len(f.legal_basis) > 120 else ''}",
            "",
        ]

    lines += [
        "── Próximos passos ──",
        "1. Use get_evidence_dossier para gerar carta ao banco, relato PROCON e modelo JEC.",
        "2. Use get_portability_analysis se suspeitar de juros altos em empréstimos (D6).",
        "3. Use get_negotiation_script para roteiro de negociação direta com o banco.",
        "",
        "⚠️ AVISO: Estes são INDÍCIOS — não garantia de direito. Consulte advogado.",
    ]

    if errors:
        lines += ["", f"(Detectores com erro: {'; '.join(errors)})"]

    return "\n".join(lines)
