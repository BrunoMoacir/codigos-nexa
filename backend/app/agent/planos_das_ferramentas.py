"""
app/agent/planos_das_ferramentas.py — o chat respeita os mesmos planos das rotas.

As rotas de Defesa, Radar e Raio-X exigem plano (`require_plan`), mas as
ferramentas do agente chamam os mesmos serviços por dentro: com o enforcement
ligado, um usuário Free pedia "tenho cobrança indevida?" no chat e recebia a
análise do plano Total. Aqui cada ferramenta paga aponta para a MESMA chave de
`FEATURE_MIN_PLAN` que a rota correspondente — mudou o plano de um recurso,
mudou nos dois lugares.

Limites de uso (Compra Inteligente, Negociador) também valem no chat: a cota é
verificada antes e debitada só depois de a ferramenta rodar.

Bloqueada, a ferramenta devolve um texto para o MODELO (não um erro): ele
explica ao usuário que o recurso é de outro plano, sem inventar o dado.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException

from app.billing.plans import FEATURE_MIN_PLAN, PLANS

logger = logging.getLogger(__name__)

# ferramenta → recurso de FEATURE_MIN_PLAN (o mesmo da rota equivalente)
FERRAMENTA_RECURSO: dict[str, str] = {
    # /defense/* — Total
    "get_defense_analysis": "defense",
    "detect_abusive_fees": "defense",
    "detect_wrongful_charges": "defense",
    "detect_abusive_interest": "defense",
    "get_evidence_dossier": "defense",
    "get_portability_analysis": "portability",
    # /opportunities/{user_id}, /bank-match, /banks — Pro
    "get_opportunities": "opportunities",
    "get_best_bank": "opportunities",
    # /costs/raio-x — Pro
    "get_bank_cost_analysis": "costs_xray",
    # /negotiator — Pro (e cota mensal abaixo)
    "get_negotiation_script": "negotiator",
}

# ferramenta → contador de uso (o mesmo que a rota equivalente debita)
FERRAMENTA_USO: dict[str, str] = {
    "get_purchase_recommendation": "purchase_checks",
    "get_negotiation_script": "negotiator_scripts",
}


def _mensagem(detalhe: dict | str) -> str:
    if isinstance(detalhe, dict):
        plano_id = str(detalhe.get("required_plan") or "pro")
        motivo = str(detalhe.get("reason") or "")
    else:
        plano_id, motivo = "pro", str(detalhe)
    plano = PLANS.get(plano_id)
    nome = plano.name if plano else plano_id.capitalize()
    preco = f" (R$ {plano.price_brl_monthly:.2f}/mês)".replace(".", ",") if plano and plano.price_brl_monthly else ""
    return (
        f"RECURSO DO PLANO {nome.upper()}: {motivo} "
        f"Diga ao usuário, com clareza, que isso faz parte do plano {nome}{preco} e que ele pode "
        "assinar em Perfil → Planos. NÃO tente obter o mesmo dado por outra ferramenta e NÃO "
        "estime o resultado."
    )


def bloqueio_da_ferramenta(nome: str, user_id: str) -> str | None:
    """None se a ferramenta pode rodar; senão, a mensagem para o modelo."""
    from app.billing.gating import bloqueio_de_plano, check_usage

    recurso = FERRAMENTA_RECURSO.get(nome)
    if recurso:
        detalhe = bloqueio_de_plano(user_id, FEATURE_MIN_PLAN[recurso])
        if detalhe:
            logger.info("[Agent] %s bloqueada pelo plano user=%s", nome, user_id)
            return _mensagem(detalhe)

    uso = FERRAMENTA_USO.get(nome)
    if uso:
        try:
            check_usage(user_id, uso)
        except HTTPException as exc:
            if exc.status_code == 402:
                logger.info("[Agent] %s bloqueada pela cota %s user=%s", nome, uso, user_id)
                return _mensagem(exc.detail)
            raise
    return None


def registrar_uso_da_ferramenta(nome: str, user_id: str) -> None:
    """Debita a cota da ferramenta depois de ela rodar. Nunca derruba a resposta."""
    from app.billing.gating import consume_usage

    uso = FERRAMENTA_USO.get(nome)
    if not uso:
        return
    try:
        consume_usage(user_id, uso)
    except HTTPException:
        pass  # a checagem anterior já decidiu; estourar aqui não apaga a resposta
    except Exception as exc:
        logger.warning("[Agent] cota %s não debitada user=%s: %s", uso, user_id, exc)


__all__ = ["FERRAMENTA_RECURSO", "FERRAMENTA_USO", "bloqueio_da_ferramenta", "registrar_uso_da_ferramenta"]
