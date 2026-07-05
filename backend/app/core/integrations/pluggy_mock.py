"""
app/integrations/open_finance/pluggy_mock.py - Mock CORRIGIDO da Pluggy

MUDANÇAS:
    ✅ "id" → "transaction_id"
    ✅ "date" → "transaction_date"
    ✅ Adicionado "account_id" (obrigatório)
    ✅ Formato de data corrigido (ISO 8601 com timezone)
    ✅ Netflix recorrente (3 meses) para teste de assinatura
"""

from datetime import datetime, timezone


class MockPluggyClient:
    """
    Cliente mock da Pluggy para testes.
    
    Simula respostas da API Pluggy com FORMATO CORRETO para TransactionWebhook.
    """
    
    def create_sandbox_item(self) -> dict:
        return {
            "id": "mock_item_id_123",
            "connector": {
                "id": "201",  # Nubank
                "name": "Nubank"
            },
            "status": "ACTIVE"
        }
    
    def get_accounts(self, item_id: str) -> dict:
        return {
            "results": [
                {
                    "id": "acc_001",
                    "name": "Conta Corrente Mock",
                    "type": "BANK",
                    "subtype": "CHECKING_ACCOUNT",
                    "balance": 5000.00,
                    "currencyCode": "BRL",
                    "connector": {"id": "201", "name": "Nubank"},
                },
                # Conta poupança — necessária para testar a personalização do
                # OPP.4 (poupança vs. CDI com saldo real); antes o mock só
                # cobria conta corrente (gap apontado no plano OPP.4, seção 2).
                {
                    "id": "acc_002",
                    "name": "Poupança Mock",
                    "type": "BANK",
                    "subtype": "SAVINGS_ACCOUNT",
                    "balance": 15000.00,
                    "currencyCode": "BRL",
                    "connector": {"id": "201", "name": "Nubank"},
                },
            ]
        }
    
    def get_transactions(self, account_id: str) -> dict:
        """
        Retorna transações mock realistas para teste do F4 (Divider PF/PJ).
        
        Inclui:
        - 25 transações totais
        - Mix balanceado PF vs PJ (60% PF, 40% PJ)
        - Horários variados (comerciais vs pessoais)
        - Valores realistas
        - Descrições discriminatórias
        """
        return {
            "results": [
                # =====================================================
                # TRANSAÇÕES PESSOAIS (PF) - 15 transações
                # =====================================================
                
                # PIX Recebido (PF)
                {
                    "transaction_id": "trx_pf_001",
                    "account_id": account_id,
                    "transaction_date": "2026-01-10T08:30:00Z",
                    "description": "PIX RECEBIDO - AMIGO",
                    "amount": 1500.00,
                    "balance": 6500.00,
                    "type": "CREDIT",
                    "category": "TRANSFER",
                    "status": "POSTED"
                },
                
                # Uber noturno (PF)
                {
                    "transaction_id": "trx_pf_002",
                    "account_id": account_id,
                    "transaction_date": "2026-01-15T18:45:00Z",
                    "description": "UBER *TRIP - SAO PAULO",
                    "amount": -45.50,
                    "balance": 6454.50,
                    "type": "DEBIT",
                    "category": "TRANSPORT",
                    "status": "POSTED",
                    "merchant": "Uber"
                },
                
                # Netflix (PF)
                {
                    "transaction_id": "trx_pf_003",
                    "account_id": account_id,
                    "transaction_date": "2026-01-20T10:00:00Z",
                    "description": "NETFLIX.COM",
                    "amount": -49.90,
                    "balance": 6404.60,
                    "type": "DEBIT",
                    "category": "ENTERTAINMENT",
                    "status": "POSTED",
                    "merchant": "Netflix"
                },
                
                # Supermercado (PF)
                {
                    "transaction_id": "trx_pf_004",
                    "account_id": account_id,
                    "transaction_date": "2026-01-22T14:30:00Z",
                    "description": "CARREFOUR SAO PAULO",
                    "amount": -285.40,
                    "balance": 6119.20,
                    "type": "DEBIT",
                    "category": "GROCERIES",
                    "status": "POSTED",
                    "merchant": "Carrefour"
                },
                
                # Academia (PF)
                {
                    "transaction_id": "trx_pf_005",
                    "account_id": account_id,
                    "transaction_date": "2026-01-23T19:00:00Z",
                    "description": "ACADEMIA FITNESS CLUB",
                    "amount": -89.90,
                    "balance": 6029.30,
                    "type": "DEBIT",
                    "category": "HEALTH",
                    "status": "POSTED",
                    "merchant": "Academia Fitness"
                },
                
                # Restaurante fim de semana (PF)
                {
                    "transaction_id": "trx_pf_006",
                    "account_id": account_id,
                    "transaction_date": "2026-01-24T12:30:00Z",
                    "description": "RESTAURANTE DO ZE",
                    "amount": -67.80,
                    "balance": 5961.50,
                    "type": "DEBIT",
                    "category": "FOOD",
                    "status": "POSTED",
                    "merchant": "Restaurante do Zé"
                },
                
                # Farmácia (PF)
                {
                    "transaction_id": "trx_pf_007",
                    "account_id": account_id,
                    "transaction_date": "2026-01-26T16:15:00Z",
                    "description": "DROGARIA SAO JOAO",
                    "amount": -123.45,
                    "balance": 5838.05,
                    "type": "DEBIT",
                    "category": "HEALTH",
                    "status": "POSTED",
                    "merchant": "Drogaria São João"
                },
                
                # Shopping pessoal (PF)
                {
                    "transaction_id": "trx_pf_008",
                    "account_id": account_id,
                    "transaction_date": "2026-01-27T15:20:00Z",
                    "description": "SHOPPING CENTER NORTE",
                    "amount": -234.67,
                    "balance": 5603.38,
                    "type": "DEBIT",
                    "category": "SHOPPING",
                    "status": "POSTED",
                    "merchant": "Shopping Center Norte"
                },
                
                # Cinema (PF)
                {
                    "transaction_id": "trx_pf_009",
                    "account_id": account_id,
                    "transaction_date": "2026-01-28T20:00:00Z",
                    "description": "CINEPOLIS SHOPPING",
                    "amount": -42.00,
                    "balance": 5561.38,
                    "type": "DEBIT",
                    "category": "ENTERTAINMENT",
                    "status": "POSTED",
                    "merchant": "Cinepolis"
                },
                
                # Padaria (PF)
                {
                    "transaction_id": "trx_pf_010",
                    "account_id": account_id,
                    "transaction_date": "2026-01-29T07:30:00Z",
                    "description": "PADARIA DO BAIRRO",
                    "amount": -15.80,
                    "balance": 5545.58,
                    "type": "DEBIT",
                    "category": "FOOD",
                    "status": "POSTED",
                    "merchant": "Padaria do Bairro"
                },
                
                # Spotify (PF)
                {
                    "transaction_id": "trx_pf_011",
                    "account_id": account_id,
                    "transaction_date": "2026-01-30T09:00:00Z",
                    "description": "SPOTIFY PREMIUM",
                    "amount": -19.90,
                    "balance": 5525.68,
                    "type": "DEBIT",
                    "category": "ENTERTAINMENT",
                    "status": "POSTED",
                    "merchant": "Spotify"
                },
                
                # Lavanderia (PF)
                {
                    "transaction_id": "trx_pf_012",
                    "account_id": account_id,
                    "transaction_date": "2026-01-31T17:45:00Z",
                    "description": "LAVANDERIA RAPIDA",
                    "amount": -35.00,
                    "balance": 5490.68,
                    "type": "DEBIT",
                    "category": "SERVICES",
                    "status": "POSTED",
                    "merchant": "Lavanderia Rápida"
                },
                
                # Cafeteria (PF)
                {
                    "transaction_id": "trx_pf_013",
                    "account_id": account_id,
                    "transaction_date": "2026-02-01T11:00:00Z",
                    "description": "STARBUCKS CAFE",
                    "amount": -28.50,
                    "balance": 5462.18,
                    "type": "DEBIT",
                    "category": "FOOD",
                    "status": "POSTED",
                    "merchant": "Starbucks"
                },
                
                # Pet shop (PF)
                {
                    "transaction_id": "trx_pf_014",
                    "account_id": account_id,
                    "transaction_date": "2026-02-02T16:30:00Z",
                    "description": "PET SHOP AMIGOS",
                    "amount": -156.78,
                    "balance": 5305.40,
                    "type": "DEBIT",
                    "category": "PETS",
                    "status": "POSTED",
                    "merchant": "Pet Shop Amigos"
                },
                
                # Livraria (PF)
                {
                    "transaction_id": "trx_pf_015",
                    "account_id": account_id,
                    "transaction_date": "2026-02-03T14:00:00Z",
                    "description": "LIVRARIA CULTURA",
                    "amount": -89.90,
                    "balance": 5215.50,
                    "type": "DEBIT",
                    "category": "EDUCATION",
                    "status": "POSTED",
                    "merchant": "Livraria Cultura"
                },
                
                # =====================================================
                # TRANSAÇÕES EMPRESARIAIS (PJ) - 10 transações
                # =====================================================
                
                # Salário empresa (PJ)
                {
                    "transaction_id": "trx_pj_001",
                    "account_id": account_id,
                    "transaction_date": "2026-01-25T06:00:00Z",
                    "description": "SALARIO - EMPRESA XYZ LTDA",
                    "amount": 8500.00,
                    "balance": 13715.50,
                    "type": "CREDIT",
                    "category": "SALARY",
                    "status": "POSTED"
                },
                
                # Material escritório (PJ)
                {
                    "transaction_id": "trx_pj_002",
                    "account_id": account_id,
                    "transaction_date": "2026-01-26T10:30:00Z",
                    "description": "PAPELARIA EMPRESARIAL LTDA",
                    "amount": -456.78,
                    "balance": 13258.72,
                    "type": "DEBIT",
                    "category": "OFFICE_SUPPLIES",
                    "status": "POSTED",
                    "merchant": "Papelaria Empresarial"
                },
                
                # Fornecedor (PJ)
                {
                    "transaction_id": "trx_pj_003",
                    "account_id": account_id,
                    "transaction_date": "2026-01-27T14:15:00Z",
                    "description": "FORNECEDOR ABC MATERIAL",
                    "amount": -1234.56,
                    "balance": 12024.16,
                    "type": "DEBIT",
                    "category": "SUPPLIES",
                    "status": "POSTED",
                    "merchant": "Fornecedor ABC"
                },
                
                # Aluguel comercial (PJ)
                {
                    "transaction_id": "trx_pj_004",
                    "account_id": account_id,
                    "transaction_date": "2026-01-28T08:00:00Z",
                    "description": "ALUGUEL ESCRITORIO - IMOBILIARIA XYZ",
                    "amount": -2500.00,
                    "balance": 9524.16,
                    "type": "DEBIT",
                    "category": "RENT",
                    "status": "POSTED",
                    "merchant": "Imobiliária XYZ"
                },
                
                # Viagem corporativa (PJ)
                {
                    "transaction_id": "trx_pj_005",
                    "account_id": account_id,
                    "transaction_date": "2026-01-29T11:45:00Z",
                    "description": "PASSAGEM AEREA - VIAGEM NEGOCIOS",
                    "amount": -890.30,
                    "balance": 8633.86,
                    "type": "DEBIT",
                    "category": "TRAVEL",
                    "status": "POSTED",
                    "merchant": "LATAM Airlines"
                },
                
                # Software empresarial (PJ)
                {
                    "transaction_id": "trx_pj_006",
                    "account_id": account_id,
                    "transaction_date": "2026-01-30T09:30:00Z",
                    "description": "LICENCA SOFTWARE EMPRESARIAL",
                    "amount": -567.89,
                    "balance": 8065.97,
                    "type": "DEBIT",
                    "category": "SOFTWARE",
                    "status": "POSTED",
                    "merchant": "Microsoft"
                },
                
                # Conta telefone corporativo (PJ)
                {
                    "transaction_id": "trx_pj_007",
                    "account_id": account_id,
                    "transaction_date": "2026-01-31T13:20:00Z",
                    "description": "TELEFONE CORPORATIVO - VIVO EMPRESAS",
                    "amount": -234.67,
                    "balance": 7831.30,
                    "type": "DEBIT",
                    "category": "TELEPHONE",
                    "status": "POSTED",
                    "merchant": "Vivo Empresas"
                },
                
                # Marketing (PJ)
                {
                    "transaction_id": "trx_pj_008",
                    "account_id": account_id,
                    "transaction_date": "2026-02-01T10:15:00Z",
                    "description": "AGENCIA MARKETING DIGITAL",
                    "amount": -1456.78,
                    "balance": 6374.52,
                    "type": "DEBIT",
                    "category": "MARKETING",
                    "status": "POSTED",
                    "merchant": "Agência Marketing Digital"
                },
                
                # Energia elétrica comercial (PJ)
                {
                    "transaction_id": "trx_pj_009",
                    "account_id": account_id,
                    "transaction_date": "2026-02-02T12:00:00Z",
                    "description": "ENERGIA ELETRICA - CEMIG EMPRESAS",
                    "amount": -678.90,
                    "balance": 5695.62,
                    "type": "DEBIT",
                    "category": "UTILITIES",
                    "status": "POSTED",
                    "merchant": "CEMIG Empresas"
                },
                
                # Consultoria (PJ)
                {
                    "transaction_id": "trx_pj_010",
                    "account_id": account_id,
                    "transaction_date": "2026-02-03T15:30:00Z",
                    "description": "CONSULTORIA CONTABIL - CONTADOR LTDA",
                    "amount": -890.12,
                    "balance": 4805.50,
                    "type": "DEBIT",
                    "category": "CONSULTING",
                    "status": "POSTED",
                    "merchant": "Contador Ltda"
                }
            ]
        }
