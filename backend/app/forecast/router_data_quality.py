"""
app/forecast/router_data_quality.py — Transparência da ingestão.

Expõe o que o ETL descartou. Existe por dois motivos, um do usuário e um
nosso:

  • do usuário: "por que meu extrato tem menos lançamentos que o do app do
    banco?" tem que ter resposta, e a resposta é a DLQ;
  • nosso: taxa de rejeição concentrada num campo é a assinatura de
    conector quebrado — dá para saber antes do suporte encher.

Escopo por dono (require_owner), como todo endpoint que toca dado
financeiro: a DLQ guarda payload cru da Pluggy, que pode conter nome de
pagador e documento.
"""

import logging

from fastapi import APIRouter, Depends, Query, status

from app.core.db.rejections import rejection_stats
from app.core.security import require_owner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data-quality", tags=["Data Quality"])


@router.get(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Qualidade da ingestão — o que foi descartado e por quê",
    description=(
        "Transações que a Pluggy entregou e o firewall de validação recusou, "
        "agrupadas por tipo de erro e por campo, na janela pedida. "
        "Campo sempre igual no topo indica mudança de contrato do banco, "
        "não dado estranho de um usuário."
    ),
)
async def get_data_quality(
    user_id: str = Depends(require_owner),
    hours: int = Query(168, ge=1, le=720, description="Janela em horas (padrão: 7 dias)"),
    institution_id: str | None = Query(None, description="Filtra por banco"),
) -> dict:
    """
    **Exemplo de resposta:**
    ```json
    {
      "user_id": "user_123",
      "janela_horas": 168,
      "total_rejeitadas": 3,
      "por_erro": {"ValidationError": 3},
      "por_campo": {"transaction_date": 2, "amount": 1},
      "diagnostico": "ATENCAO: 2 rejeicoes concentradas em 'transaction_date'"
    }
    ```
    """
    logger.info("GET /data-quality/%s (janela=%sh)", user_id, hours)

    stats = rejection_stats(institution_id=institution_id, user_id=user_id, hours=hours)

    return {
        "user_id": user_id,
        "institution_id": institution_id,
        "janela_horas": stats.janela_horas,
        "total_rejeitadas": stats.total,
        "por_erro": stats.por_erro,
        "por_campo": stats.por_campo,
        "diagnostico": _diagnostico(stats),
    }


def _diagnostico(stats) -> str:
    """Traduz a estatística para a frase que o humano precisa ler."""
    if stats.total == 0:
        return "OK: nenhuma transação descartada na janela."

    if not stats.por_campo:
        return f"{stats.total} transações descartadas."

    campo, quantidade = next(iter(stats.por_campo.items()))
    if quantidade >= max(3, stats.total * 0.6):
        return (
            f"ATENCAO: {quantidade} de {stats.total} rejeições concentradas em "
            f"'{campo}' — cheiro de mudança de contrato do banco, não de dado "
            f"isolado."
        )

    return f"{stats.total} transações descartadas, sem campo dominante."
