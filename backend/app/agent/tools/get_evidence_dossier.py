# app/agent/tools/get_evidence_dossier.py
import logging
from datetime import date

from langchain_core.tools import tool
from app.core.formatacao import brl

logger = logging.getLogger(__name__)


@tool
def get_evidence_dossier(
    user_id: str,
    charge_date: str = "",
    correction_index: str = "IPCA",
) -> str:
    """
    Gera o Dossiê de Evidências (D5) — carta ao banco, relato PROCON e modelo JEC.

    Use esta ferramenta SEMPRE que o usuário perguntar sobre:
    - "Gera uma carta para enviar ao meu banco"
    - "Quero contestar formalmente as cobranças" / "como faço uma reclamação formal?"
    - "Cria um dossiê / documento das irregularidades"
    - "Quero protocolar no PROCON / Consumidor.gov.br"
    - "Gera modelo de petição para JEC / Juizado Especial"
    - "Quero os documentos para contestar o banco"
    - "Como faço para reclamar por escrito?"
    - Qualquer pedido de documento formal para contestar banco ou acionar órgão de defesa.

    Args:
        user_id:          ID do usuário (obrigatório).
        charge_date:      Data da cobrança mais antiga no formato YYYY-MM-DD (opcional).
                          Se fornecida, calcula correção monetária acumulada desde essa data.
        correction_index: Índice de correção: IPCA (padrão), SELIC ou INPC.
    """
    logger.info(
        "[Tool] get_evidence_dossier | user=%s charge_date=%s index=%s",
        user_id, charge_date, correction_index,
    )

    try:
        from app.defense.services.tied_sale_detector import TiedSaleDetector
        from app.defense.services.wrongful_charge_detector import WrongfulChargeDetector
        from app.defense.services.abusive_interest_detector import AbusiveInterestDetector
        from app.defense.services.unilateral_change_detector import UnilateralChangeDetector
        from app.defense.services.evidence_builder import EvidenceBuilder

        _detectors = [
            TiedSaleDetector(),
            WrongfulChargeDetector(),
            AbusiveInterestDetector(),
            UnilateralChangeDetector(),
        ]

        all_findings = []
        for detector in _detectors:
            try:
                all_findings.extend(detector.detect(user_id))
            except Exception as exc:
                logger.debug("[Tool] get_evidence_dossier detector error: %s", exc)

        parsed_date = None
        if charge_date:
            try:
                parsed_date = date.fromisoformat(charge_date)
            except ValueError:
                logger.debug("[Tool] get_evidence_dossier: data inválida %s", charge_date)

        valid_indexes = {"IPCA", "SELIC", "INPC"}
        index = correction_index.upper() if correction_index.upper() in valid_indexes else "IPCA"

        dossier = EvidenceBuilder().build_dossier(
            user_id=user_id,
            findings=all_findings,
            charge_date=parsed_date,
            correction_index=index,
        )

    except Exception as exc:
        logger.error("[Tool] get_evidence_dossier error: %s", exc)
        return (
            "Erro ao gerar o dossiê de evidências. "
            "Verifique se o módulo defense está disponível e tente novamente."
        )

    total = dossier.total_disputed_amount
    n = dossier.total_findings

    lines = [
        "=== DOSSIÊ DE EVIDÊNCIAS (D5) ===",
        "⚠️ AVISO LEGAL: Documentos gerados como modelo educacional.",
        "Revise e preencha seus dados pessoais antes de protocolar.",
        "",
        f"📋 {n} achado(s) | Estimativa total contestável: {brl(total)}",
    ]

    if dossier.monetary_correction:
        c = dossier.monetary_correction
        lines.append(
            f"📈 Correção monetária ({c.index}): "
            f"{brl(c.original_value)} → {brl(c.corrected_value)} "
            f"(+{brl(c.correction_brl)} em {c.monthly_rates_used or 0} meses)"
        )

    lines += [
        "",
        "── Documentos gerados ──",
        "✅ Carta de Contestação ao Banco",
        "✅ Relato para PROCON / Consumidor.gov.br",
        "✅ Modelo de Petição para Juizado Especial Cível (JEC)",
        "",
        "── Carta ao Banco (resumo) ──",
    ]

    carta_preview = dossier.contestation_letter
    lines.append(carta_preview[:800] + "\n[...documento completo disponível no endpoint /dossier...]")

    lines += [
        "",
        "── Trilha de Canais (siga nesta ordem) ──",
        "1. SAC do banco (prazo: 5 dias úteis) — registre o protocolo",
        "2. Ouvidoria do banco (prazo: 10 dias úteis) — exija resposta formal",
        "3. Consumidor.gov.br — plataforma do Ministério da Justiça",
        "4. BACEN (bcb.gov.br/meubc) — tarifas e juros",
        "5. PROCON — gratuito, 30–60 dias",
        "6. JEC — até R$ 28.200 sem advogado",
        "",
        "Para acesso completo a todos os documentos, use o endpoint:",
        f"GET /api/v1/defense/{user_id}/dossier",
        f"(adicione ?charge_date={charge_date or 'YYYY-MM-DD'}&correction_index={index})",
    ]

    return "\n".join(lines)
