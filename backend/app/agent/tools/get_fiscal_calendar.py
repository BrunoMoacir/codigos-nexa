# app/agent/tools/get_fiscal_calendar.py
import logging

from langchain_core.tools import tool
from app.core.formatacao import brl

logger = logging.getLogger(__name__)


@tool
def get_fiscal_calendar(user_id: str) -> str:
    """
    Retorna os eventos fiscais sazonais ativos para o usuário: prazo do IR,
    lotes de restituição, IPVA/IPTU, DAS e declaração anual do MEI,
    parcelas do 13º salário e distribuição do lucro do FGTS.

    Use esta ferramenta SEMPRE que o usuário perguntar sobre:
    - "Quando vence o IR / a declaração do imposto de renda?"
    - "Quando cai a restituição do IR?"
    - "Quando vence o DAS / a guia do MEI?"
    - "Quando recebo o 13º? O que fazer com o 13º?"
    - "Como me planejar para IPVA/IPTU?"
    - "Tem algum prazo fiscal chegando?"
    - Qualquer pergunta sobre calendário fiscal, prazos de impostos ou
      datas sazonais de dinheiro entrando/saindo.

    Args:
        user_id: ID do usuário (obrigatório).
    """
    logger.info("[Tool] get_fiscal_calendar | user=%s", user_id)

    try:
        from app.seasonality.service import get_seasonality_service

        response = get_seasonality_service().get_events(user_id)
    except Exception as exc:
        logger.error("[Tool] get_fiscal_calendar erro: %s", exc)
        return f"Erro ao consultar o calendário fiscal: {exc}"

    lines = [
        "=== CALENDÁRIO FISCAL SAZONAL (R2.c) ===",
        f"Data de referência: {response.reference_date.isoformat()}",
        f"Perfil detectado: "
        f"{'MEI/PJ' if response.profile_signals.get('is_mei') else 'sem sinal de MEI'}"
        f" · {'salário recorrente (CLT)' if response.profile_signals.get('has_salary') else 'sem salário recorrente detectado'}",
        "",
    ]

    if not response.events:
        lines += [
            "Nenhum evento fiscal com janela de alerta ativa no momento.",
            "As janelas cobertas são: declaração do IR (mar–mai), lotes de "
            "restituição (mai–set), IPVA/IPTU (jan–fev), DAS mensal do MEI "
            "(dia 13–20), DASN-SIMEI (jan–mai), 13º salário (nov–dez) e "
            "lucro do FGTS (jul–ago).",
        ]
        return "\n".join(lines)

    for i, evt in enumerate(response.events, 1):
        kind = "OBRIGAÇÃO (prazo legal)" if evt.is_obligation else "PLANEJAMENTO/DIREITO"
        lines += [
            f"── {i}. {evt.name} ──",
            f"Tipo: {kind}",
            f"Prazo: {evt.deadline.isoformat()} ({evt.days_until_deadline} dias)",
            evt.description,
        ]
        if evt.estimated_amount_brl is not None:
            origem = "dados reais das suas contas" if evt.is_personalized else "referência de mercado"
            lines.append(
                f"Valor estimado: {brl(evt.estimated_amount_brl)} (fonte: {origem})"
            )
        lines += [f"Ação sugerida: {evt.action_hint}", ""]

    lines.append(
        "Estimativas calculadas a partir das transações conectadas via Open "
        "Finance — sem viés de banco. Confirme valores oficiais nos canais "
        "do governo (e-CAC, PGMEI, app FGTS)."
    )
    return "\n".join(lines)
