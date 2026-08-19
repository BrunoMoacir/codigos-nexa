"""
app/jobs/cards_curation_audit.py — Job semanal (segunda, 03h30).

A base de 81 cartões é curada À MÃO e benefício de cartão muda o tempo todo:
anuidade sobe, cashback por categoria vira campanha temporária, programa de
pontos altera conversão. Não existe API pública de metadados de cartão no
Brasil, então não dá para atualizar automaticamente — mas dá para saber o
que está vencido e parar de confiar do mesmo jeito.

O job faz duas coisas:

  1. AVISA: lista o que passou do prazo de revisão (90 dias), ordenado por
     idade, para a curadoria saber por onde começar;
  2. MEDE: reporta a confiança efetiva já descontada do envelhecimento
     (`curation_freshness_factor`), que é o que o simulador aplica.

Não escreve na base. Curadoria de dado de produto é decisão humana — o job
existe para que ninguém precise lembrar de conferir, não para conferir
sozinho.
"""

import logging
from collections import Counter
from datetime import date

from app.jobs._base import job_guard

logger = logging.getLogger(__name__)

# Acima disso o registro entra no relatório como pendente de revisão.
_REVIEW_DAYS = 90
# Quantos itens listar nominalmente no log (o resto vira contagem).
_TOP_N = 15


def audit_card_curation(today: date | None = None) -> dict:
    """
    Estado da curadoria. Retorna dict serializável (usado pelo job e por
    quem quiser expor isso numa tela de operação).
    """
    from app.optimizer.card_loader import (
        CardKnowledgeBase,
        _CURATION_STALE_DAYS,
        curation_freshness_factor,
    )

    hoje = today or date.today()
    cards = CardKnowledgeBase().load()

    if not cards:
        logger.error("[CuracaoCartoes] Base vazia — nada auditado")
        return {"total": 0, "erro": "base vazia"}

    vencidos: list[dict] = []
    por_emissor: Counter[str] = Counter()
    fatores: list[float] = []

    for card in cards:
        last_updated = getattr(card, "last_updated", None)
        fator = curation_freshness_factor(last_updated, hoje)
        fatores.append(fator)

        try:
            idade = (hoje - date.fromisoformat(str(last_updated)[:10])).days
        except (TypeError, ValueError):
            idade = None  # sem data: tratado como obsoleto pelo fator

        if fator < 1.0:
            vencidos.append({
                "card_id": card.card_id,
                "issuer": card.issuer,
                "last_updated": last_updated,
                "idade_dias": idade,
                "fator_frescor": round(fator, 3),
                "confianca_efetiva": round(card.data_trust_score * fator, 3),
            })
            por_emissor[card.issuer] += 1

    vencidos.sort(key=lambda v: (v["idade_dias"] is not None, -(v["idade_dias"] or 10**6)))

    obsoletos = [v for v in vencidos if v["fator_frescor"] <= 0.6 + 1e-9]
    relatorio = {
        "total": len(cards),
        "vencidos": len(vencidos),
        "obsoletos": len(obsoletos),
        "prazo_revisao_dias": _REVIEW_DAYS,
        "obsoleto_a_partir_de_dias": _CURATION_STALE_DAYS,
        "fator_frescor_medio": round(sum(fatores) / len(fatores), 3),
        "por_emissor": dict(por_emissor.most_common()),
        "itens": vencidos[:_TOP_N],
    }

    if not vencidos:
        logger.info("[CuracaoCartoes] %s cartões, todos dentro do prazo", len(cards))
        return relatorio

    nivel = logging.WARNING if obsoletos else logging.INFO
    logger.log(
        nivel,
        "[CuracaoCartoes] %s de %s cartões vencidos (%s obsoletos há mais de %s dias) "
        "| frescor médio %.2f | emissores no topo: %s",
        len(vencidos), len(cards), len(obsoletos), _CURATION_STALE_DAYS,
        relatorio["fator_frescor_medio"],
        list(por_emissor.most_common(3)),
    )
    for item in relatorio["itens"]:
        logger.info(
            "[CuracaoCartoes]   %-28s %-14s %4s dias  confiança %.2f",
            item["card_id"], item["issuer"],
            item["idade_dias"] if item["idade_dias"] is not None else "s/d",
            item["confianca_efetiva"],
        )

    return relatorio


@job_guard("cards_curation_audit")
async def run_cards_curation_audit() -> None:
    audit_card_curation()
