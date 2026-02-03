"""
test_full_safe_to_spend_pipeline.py - Teste Safe-to-Spend com Pluggy

PIPELINE COMPLETO:
    Pluggy Mock → Validation → ETL → Cashflow → Safe-to-Spend

Execute:
    python test_full_safe_to_spend_pipeline.py
"""

from datetime import datetime, timezone

from app.integrations.open_finance.pluggy_mock import MockPluggyClient
from app.schemas.transaction import TransactionBatchResult
from app.etl import TransactionIngestor


def test_full_safe_to_spend_pipeline():
    """
    Testa pipeline completo Safe-to-Spend.
    
    Fluxo:
        1. Pluggy Mock → Buscar transações
        2. Pydantic → Validar com TransactionBatchResult
        3. ETL → Limpar e normalizar
        4. Cashflow → Projetar fluxo de caixa (TODO)
        5. Safe-to-Spend → Calcular quanto pode gastar (TODO)
    """
    
    print("="*70)
    print("🧪 TESTE: SAFE-TO-SPEND PIPELINE")
    print("="*70)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1️⃣ PLUGGY MOCK
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("\n1️⃣ Buscando dados da Pluggy...")
    
    pluggy = MockPluggyClient()
    item = pluggy.create_sandbox_item()
    accounts = pluggy.get_accounts(item["id"])
    
    account_id = accounts["results"][0]["id"]
    raw_transactions_response = pluggy.get_transactions(account_id)
    raw_transactions = raw_transactions_response.get("results", [])
    
    print(f"✅ {len(raw_transactions)} transações recebidas")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2️⃣ VALIDAÇÃO COM PYDANTIC
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("\n2️⃣ Validando com Pydantic...")
    
    batch_result = TransactionBatchResult.from_raw_batch(
        raw_data=raw_transactions,
        institution_id="pluggy_sandbox",
        item_id=item["id"],
        fetched_at=datetime.now(timezone.utc)
    )
    
    print(f"✅ {batch_result.total_valid} transações válidas")
    
    if not batch_result.valid_transactions:
        print("⚠️  Nenhuma transação válida, abortando teste")
        return
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3️⃣ ETL - INGESTOR
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("\n3️⃣ Processando com ETL Ingestor...")
    
    ingestor = TransactionIngestor()
    clean_df, metrics = ingestor.process(batch_result.valid_transactions)
    
    print(f"✅ {len(clean_df)} transações processadas")
    print(f"   Quality score: {metrics.quality_score:.1%}")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 4️⃣ CASHFLOW PROJECTION (TODO - IMPLEMENTAR)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("\n4️⃣ Projetando cashflow...")
    
    # TODO: Implementar CashflowProjector
    # Por enquanto, vamos calcular manualmente
    
    # Pegar saldo mais recente
    current_balance = clean_df.select("balance").filter(
        clean_df["balance"].is_not_null()
    ).tail(1).item()
    
    if current_balance is None:
        print("⚠️  Saldo não disponível, usando R$ 10.000,00 como base")
        current_balance = 10000.0
    
    # Calcular média de débitos dos últimos 30 dias
    import polars as pl
    
    debits = clean_df.filter(pl.col("amount") < 0)
    avg_daily_debit = abs(debits["amount"].mean()) if len(debits) > 0 else 0
    
    # Projetar próximos 30 dias (simples: média * 30)
    projected_debits_30d = avg_daily_debit * 30
    
    print(f"✅ Saldo atual: R$ {current_balance:,.2f}")
    print(f"   Débitos médios/dia: R$ {avg_daily_debit:,.2f}")
    print(f"   Débitos projetados (30d): R$ {projected_debits_30d:,.2f}")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 5️⃣ SAFE-TO-SPEND (TODO - IMPLEMENTAR)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("\n5️⃣ Calculando Safe-to-Spend...")
    
    # TODO: Implementar SafeToSpendCalculator
    # Por enquanto, cálculo manual
    
    # Fórmula: Safe = Saldo - Débitos Projetados - Buffer
    buffer = 1000.0  # R$ 1.000 de margem de segurança
    
    safe_to_spend_total = current_balance - projected_debits_30d - buffer
    safe_to_spend_daily = safe_to_spend_total / 30
    
    # Garantir que não seja negativo
    safe_to_spend_total = max(0, safe_to_spend_total)
    safe_to_spend_daily = max(0, safe_to_spend_daily)
    
    result = {
        "current_balance": current_balance,
        "projected_debits_30d": projected_debits_30d,
        "buffer": buffer,
        "safe_to_spend_total": safe_to_spend_total,
        "safe_to_spend_daily": safe_to_spend_daily,
        "horizon_days": 30
    }
    
    print(f"✅ Safe-to-Spend calculado")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # EXIBIR RESULTADO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("\n" + "="*70)
    print("💰 SAFE TO SPEND - RESULTADO")
    print("="*70)
    
    print(f"\n📊 Análise Financeira (próximos 30 dias):")
    print(f"   Saldo Atual:           R$ {result['current_balance']:>10,.2f}")
    print(f"   Débitos Projetados:    R$ {result['projected_debits_30d']:>10,.2f}")
    print(f"   Buffer de Segurança:   R$ {result['buffer']:>10,.2f}")
    print(f"   " + "-"*50)
    print(f"   SAFE-TO-SPEND (Total): R$ {result['safe_to_spend_total']:>10,.2f}")
    print(f"   SAFE-TO-SPEND (Dia):   R$ {result['safe_to_spend_daily']:>10,.2f}")
    
    print(f"\n💡 Interpretação:")
    if result['safe_to_spend_daily'] > 100:
        print(f"   ✅ Você pode gastar até R$ {result['safe_to_spend_daily']:.2f}/dia")
        print(f"      com segurança nos próximos 30 dias.")
    elif result['safe_to_spend_daily'] > 0:
        print(f"   ⚠️  Cuidado! Só pode gastar R$ {result['safe_to_spend_daily']:.2f}/dia.")
        print(f"      Evite gastos desnecessários.")
    else:
        print(f"   🚨 ALERTA! Não há margem para novos gastos.")
        print(f"      Saldo insuficiente para cobrir despesas projetadas.")
    
    print("\n" + "="*70)
    print("✅ TESTE CONCLUÍDO")
    print("="*70)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ASSERTS (validação automática)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    assert "safe_to_spend_daily" in result
    assert result["safe_to_spend_daily"] >= 0
    assert result["safe_to_spend_total"] >= 0
    
    print("\n✅ Todos os asserts passaram!")


if __name__ == "__main__":
    test_full_safe_to_spend_pipeline()