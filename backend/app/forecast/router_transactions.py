"""
app/api/v1/routes/transactions.py - Webhook para receber transações da Pluggy

╔══════════════════════════════════════════════════════════════════════╗
║ O QUE ESTE ARQUIVO FAZ                                               ║
╚══════════════════════════════════════════════════════════════════════╝

Recebe webhooks da Pluggy com transações e:
1. Valida com TransactionBatchResult (tolerante a erros)
2. Salva JSON cru no storage (auditoria)
3. Processa com ETL (ingestor + classifier)
4. Retorna status de processamento

╔══════════════════════════════════════════════════════════════════════╗
║ FLUXO COMPLETO                                                       ║
╚══════════════════════════════════════════════════════════════════════╝

Pluggy → POST /api/v1/transactions/webhook
          ↓
    Valida (Pydantic TransactionBatchResult)
          ↓
    Salva JSON cru (storage/raw_events.py)
          ↓
    ETL Pipeline:
      1. Ingestor (limpa + normaliza)
      2. Classifier (categoriza)
          ↓
    Retorna status (200 OK)
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.schemas.transaction import TransactionBatchResult
from app.core.webhook_security import resolve_user_from_item, verify_webhook_token
from app.forecast.etl import TransactionIngestor, TransactionClassifier
from app.core.database import get_db
from app.core.cache import cache_response, invalidate_user_cache

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURAÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

router = APIRouter(prefix="/transactions", tags=["Transactions"])
logger = logging.getLogger(__name__)

# Mapeamento Pluggy connector_id → institution_id
# Adicionar novos bancos aqui conforme integração for expandida
_CONNECTOR_MAP: dict[str, str] = {
    "201": "nubank",
    "202": "itau",
    "203": "bradesco",
    "204": "inter",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WEBHOOK: RECEBE TRANSAÇÕES DA PLUGGY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/webhook", status_code=status.HTTP_200_OK)
async def receive_transaction_webhook(
    payload: dict[str, Any],
    request: Request,
    user_id: str | None = Query(
        default=None,
        description=(
            "APENAS desenvolvimento (APP_MODE=dev): override manual do dono "
            "para testes locais. Em produção este parâmetro é IGNORADO — o "
            "dono vem do mapeamento server-side item_id → pluggy_items."
        ),
    ),
    db: Session = Depends(get_db)
):
    """
    Recebe webhook de transações da Pluggy.

    Segurança (auditoria 2026-07):
      1. Segredo compartilhado obrigatório (X-Webhook-Token ou ?token=),
         comparado em tempo constante; produção sem segredo → 503.
      2. Identidade NUNCA vem do chamador: item_id do payload é resolvido
         via pluggy_items. Item desconhecido → 404, nada é escrito.
    """
    # 0. AUTENTICAÇÃO DO WEBHOOK (fail-closed em produção)
    verify_webhook_token(request)

    # 1. EXTRAIR CONTEXTO DO WEBHOOK
    try:
        connector_id = str(payload.get("connector", {}).get("id", "unknown"))
        institution_id = _CONNECTOR_MAP.get(connector_id, "unknown")
        if institution_id == "unknown":
            logger.warning(
                "Webhook recebido com connector_id desconhecido: %s. "
                "Adicionar ao _CONNECTOR_MAP se for um banco válido.",
                connector_id,
            )
        
        item_id = payload.get("item", {}).get("id", "unknown")
        raw_transactions = payload.get("results", [])
        
        logger.info(
            "Webhook recebido",
            extra={
                "institution_id": institution_id,
                "item_id": item_id,
                "total_transactions": len(raw_transactions)
            }
        )
        
    except Exception as e:
        logger.error("Erro ao extrair contexto do webhook: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload inválido: faltam campos obrigatórios (connector, item, results)"
        )

    # 1.5. RESOLVER O DONO DOS DADOS — server-side, nunca do chamador
    resolved_user = resolve_user_from_item(item_id)
    if resolved_user is not None:
        user_id = resolved_user
    elif user_id and os.getenv("APP_MODE", "dev") != "prod":
        # Override manual só existe em desenvolvimento (mocks locais)
        logger.warning(
            "[Webhook] item_id=%s sem mapeamento — usando user_id=%s do "
            "query param (permitido APENAS em dev)", item_id, user_id,
        )
    else:
        logger.warning(
            "[Webhook] item_id=%s não mapeado em pluggy_items — descartando "
            "payload (nada foi escrito)", item_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item desconhecido: nenhum usuário conectou este item.",
        )

    # 2. VALIDAR BATCH (Pydantic - tolerante a erros)
    try:
        batch_result = TransactionBatchResult.from_raw_batch(
            raw_data=raw_transactions,
            institution_id=institution_id,
            item_id=item_id,
            fetched_at=datetime.now(timezone.utc)
        )
        
        logger.info(
            "Batch validado",
            extra={
                "total_valid": batch_result.total_valid,
                "total_rejected": batch_result.total_rejected,
                "rejection_rate": batch_result.rejection_rate
            }
        )
        
    except Exception as e:
        logger.error("Erro ao validar batch de transações: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao validar transações. Verifique o formato dos dados.",
        )
    
    # 3. PROCESSAR COM ETL (se houver transações válidas)
    if batch_result.valid_transactions:
        try:
            # PASSO 1: INGESTOR (Limpa + Normaliza)
            ingestor = TransactionIngestor()
            clean_df, metrics = ingestor.process(batch_result.valid_transactions)
            
            logger.info(
                "ETL Ingestor concluído",
                extra={
                    "records_processed": metrics.records_after_dedup,
                    "duplicates_removed": metrics.duplicates_removed,
                    "quality_score": metrics.quality_score
                }
            )
            
            # PASSO 2: CLASSIFIER (Categoriza)
            classifier = TransactionClassifier()
            categorized_df = classifier.predict(clean_df)
            
            logger.info("ETL Classifier concluído")
            
            # PASSO 3: SALVAR NO POSTGRES VIA SQLALCHEMY
            from app.core.db.queries import save_transactions_clean
            
            account_id = None
            if "account_id" in categorized_df.columns and not categorized_df.is_empty():
                account_id = categorized_df["account_id"][0]
                
            saved_rows = save_transactions_clean(
                db=db,
                df=categorized_df,
                user_id=user_id,
                account_id=account_id
            )
            
            logger.info(
                "ETL Pipeline completo",
                extra={
                    "final_records": len(categorized_df),
                    "saved_rows": saved_rows
                }
            )

            # Invalidar cache após salvar transações
            invalidate_user_cache(user_id)
            logger.debug(f"Cache invalidado para user_id={user_id} após novas transações")
            
        except Exception as e:
            logger.error("Erro no ETL Pipeline: %s", e, exc_info=True)
    
    if batch_result.should_alert:
        logger.log(
            getattr(logging, batch_result.alert_level),  # WARNING ou CRITICAL
            batch_result.alert_message,
            extra={
                "institution_id": institution_id,
                "rejection_rate": batch_result.rejection_rate
            }
        )
    
    return {
        "status": "processed",
        "batch_id": batch_result.batch_id,
        "institution_id": institution_id,
        "total_received": batch_result.total_received,
        "total_valid": batch_result.total_valid,
        "total_rejected": batch_result.total_rejected,
        "rejection_rate": batch_result.rejection_rate,
        "alert_level": batch_result.alert_level
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: Buscar transações processadas
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _extrato_normalizado(user_id: str):
    """
    O extrato do usuário com os nomes de coluna que a API expõe.

    `get_transactions_for_user` entrega `date` ou `transaction_date`,
    `category` ou `predicted_category` conforme a origem — a mesma deriva de
    nome que zerava a renda no ETL. Normaliza uma vez, para os dois endpoints.
    """
    import polars as pl
    from app.core.db.queries import get_transactions_for_user

    txns = get_transactions_for_user(user_id)
    if txns.is_empty():
        return txns
    rename = {
        "predicted_category": "category",
        "pf_pj_label": "context_type",
        "transaction_date": "date",
    }
    for old, new in rename.items():
        if old in txns.columns and new not in txns.columns:
            txns = txns.rename({old: new})
    if "date" in txns.columns:
        txns = txns.with_columns(pl.col("date").cast(pl.Date))
    return txns


@router.get("/{user_id}", status_code=status.HTTP_200_OK)
@cache_response(prefix="transactions", ttl=300)
async def get_user_transactions(
    user_id: str = Depends(__import__('app.core.security', fromlist=['require_owner']).require_owner),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    transaction_type: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db)
) -> dict:
    """
    Transações processadas do usuário, paginadas, mais recentes primeiro.

    `total` é a contagem REAL com os filtros aplicados — era o tamanho da
    página, e a tela não tinha como saber que o extrato fora truncado.
    `offset` era mandado pelo frontend e ignorado aqui, então a paginação era
    impossível. Lista vazia é 200 com `transactions: []`: "não há lançamentos"
    é resposta, não recurso inexistente.
    """
    import polars as pl

    try:
        txns = _extrato_normalizado(user_id)
        filtros = {
            "start_date": start_date,
            "end_date": end_date,
            "category": category,
            "transaction_type": transaction_type,
        }
        if txns.is_empty():
            return {
                "user_id": user_id, "total": 0, "limit": limit, "offset": offset,
                "has_more": False, "debit_count": 0, "credit_count": 0,
                "filters": filtros, "transactions": [],
            }

        if "date" in txns.columns:
            from datetime import date as dt_date
            if start_date:
                txns = txns.filter(pl.col("date") >= dt_date.fromisoformat(start_date))
            if end_date:
                txns = txns.filter(pl.col("date") <= dt_date.fromisoformat(end_date))

        if category and "category" in txns.columns:
            txns = txns.filter(pl.col("category").str.to_lowercase() == category.lower())

        if transaction_type and "amount" in txns.columns:
            tipo = transaction_type.lower()
            if tipo in ("debit", "expense"):
                txns = txns.filter(pl.col("amount") < 0)
            elif tipo in ("credit", "income"):
                txns = txns.filter(pl.col("amount") >= 0)

        # Ordem total e estável (data desc, id desc): sem desempate, páginas
        # consecutivas podiam repetir ou pular lançamentos do mesmo dia.
        ordem = [c for c in ("date", "transaction_id") if c in txns.columns]
        if ordem:
            txns = txns.sort(ordem, descending=True)

        total = txns.height
        debit_count = txns.filter(pl.col("amount") < 0).height if "amount" in txns.columns else 0
        credit_count = total - debit_count
        pagina = txns.slice(offset, limit)

        output_cols = [
            c
            for c in (
                "transaction_id", "account_id", "description", "amount", "date",
                "category", "transaction_type", "is_recurring", "is_installment",
                "context_type",
            )
            if c in pagina.columns
        ]
        serialized = pagina.select(output_cols).to_dicts()
        for row in serialized:
            if "date" in row and hasattr(row["date"], "isoformat"):
                row["date"] = row["date"].isoformat()
            row["id"] = row.get("transaction_id")
            row["type"] = "income" if (row.get("amount") or 0) >= 0 else "expense"

        logger.info(
            "GET /transactions/%s | total=%d | pagina=%d (offset=%d)",
            user_id, total, len(serialized), offset,
        )
        return {
            "user_id": user_id,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(serialized) < total,
            "debit_count": debit_count,
            "credit_count": credit_count,
            "filters": filtros,
            "transactions": serialized,
        }
    except HTTPException:
        raise
    except ValueError as exc:  # data inválida nos filtros
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Filtro inválido: {exc}",
        )
    except Exception:
        # O detail repetia a exceção crua (mensagem de driver, trecho de SQL).
        logger.exception("Erro ao consultar transações de %s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao buscar transações.",
        )


@router.get("/{user_id}/summary", status_code=status.HTTP_200_OK)
@cache_response(prefix="transactions_summary", ttl=300)
async def get_transactions_summary(
    user_id: str = Depends(__import__('app.core.security', fromlist=['require_owner']).require_owner),
    months: int = Query(default=12, ge=1, le=36),
) -> dict:
    """
    Resumo do extrato por mês e por categoria, calculado no servidor.

    O Organizar e o Dashboard montavam receita, gastos, saldo, taxa de
    poupança, o gráfico mensal e as categorias somando a primeira página de
    100 lançamentos no navegador — cerca de dois meses e meio de um extrato de
    um ano, com rótulos de mês fixos no código. Aqui o recorte é por mês real
    e cobre o período inteiro pedido.

    `income`/`expenses` são entradas e saídas brutas do extrato (positivos).
    Não é a renda líquida do `IncomeProfiler` — que exclui transferência entre
    contas próprias e estorno — e por isso a tela as rotula como entradas.
    """
    import polars as pl

    vazio = {
        "user_id": user_id, "period": {"start": None, "end": None},
        "n_transactions": 0, "months": [],
        "totals": {"income": 0.0, "expenses": 0.0, "net": 0.0, "savings_rate_pct": 0.0},
        "by_category": [], "data_as_of": None,
    }
    try:
        txns = _extrato_normalizado(user_id)
        if txns.is_empty() or "date" not in txns.columns or "amount" not in txns.columns:
            return vazio

        ultima = txns["date"].max()
        meses_com_dado = (
            txns.with_columns(pl.col("date").dt.strftime("%Y-%m").alias("_mes"))
            ["_mes"].unique().sort()
        )
        janela = meses_com_dado.tail(months).to_list()
        recorte = (
            txns.with_columns(pl.col("date").dt.strftime("%Y-%m").alias("_mes"))
            .filter(pl.col("_mes").is_in(janela))
        )

        por_mes = (
            recorte.group_by("_mes")
            .agg(
                pl.col("amount").filter(pl.col("amount") > 0).sum().alias("income"),
                (-pl.col("amount").filter(pl.col("amount") < 0)).sum().alias("expenses"),
            )
            .sort("_mes")
        )
        meses = [
            {
                "month": linha["_mes"],
                "income": round(float(linha["income"] or 0), 2),
                "expenses": round(float(linha["expenses"] or 0), 2),
                "net": round(float((linha["income"] or 0) - (linha["expenses"] or 0)), 2),
            }
            for linha in por_mes.iter_rows(named=True)
        ]
        entradas = sum(m["income"] for m in meses)
        saidas = sum(m["expenses"] for m in meses)

        categorias = []
        if "category" in recorte.columns:
            despesas = recorte.filter(pl.col("amount") < 0)
            if despesas.height:
                agrupado = (
                    despesas.with_columns(pl.col("category").fill_null("Outros"))
                    .group_by("category")
                    .agg((-pl.col("amount")).sum().alias("total"), pl.len().alias("count"))
                    .sort("total", descending=True)
                )
                for linha in agrupado.iter_rows(named=True):
                    total_cat = float(linha["total"] or 0)
                    categorias.append({
                        "category": linha["category"] or "Outros",
                        "total": round(total_cat, 2),
                        "count": int(linha["count"]),
                        "pct": round(total_cat / saidas * 100, 1) if saidas else 0.0,
                    })

        return {
            "user_id": user_id,
            "period": {
                "start": f"{janela[0]}-01" if janela else None,
                "end": ultima.isoformat() if ultima else None,
            },
            "n_transactions": recorte.height,
            "months": meses,
            "totals": {
                "income": round(entradas, 2),
                "expenses": round(saidas, 2),
                "net": round(entradas - saidas, 2),
                "savings_rate_pct": round((entradas - saidas) / entradas * 100, 1) if entradas else 0.0,
            },
            "by_category": categorias,
            "data_as_of": ultima.isoformat() if ultima else None,
        }
    except Exception:
        logger.exception("Erro ao resumir transações de %s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao resumir o extrato.",
        )
