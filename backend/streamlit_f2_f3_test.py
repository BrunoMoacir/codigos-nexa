"""
streamlit_f2_f3_test.py — Chat Nexa com Tool Use (F2 Optimizer + F3 Architect)

Como usar:
    cd backend
    streamlit run streamlit_f2_f3_test.py

- Sem backend rodando (chamadas diretas ao Python)
- Dados de transações sintéticos configuráveis na sidebar
- Modelo: claude-haiku-4-5-20251001 com tool use
- A IA decide quando chamar cada funcionalidade e responde com análises reais
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

_BACKEND = Path(__file__).parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("REDIS_URL", "")

import anthropic
import polars as pl
import streamlit as st

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLIENTE ANTHROPIC
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except Exception:
    pass

@st.cache_resource
def get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY") or None
    return anthropic.Anthropic(api_key=api_key)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DADOS HISTÓRICOS — geradores por perfil comportamental
# Cada perfil ativa detectores específicos do pipeline de inteligência:
#   viajante  → TravelDetector, EXPLORADOR_GLOBAL cluster, lounge/milhas
#   foodie    → FoodieDetector, URBANO_FOODIE cluster, cashback alimentação
#   investidor→ InvestorDetector, INVESTIDOR_CAUTELOSO, cartões sem anuidade
#   familia   → FamilyDetector, FAMILIA_ESTRUTURADA, cashback farmácia/super
#   mei       → MEIDetector, MICROEMPREENDEDOR, renda PJ irregular
#   digital   → subscription_burn alto, DIGITAL_NATIVO, streaming/e-commerce (sem delivery)
#   imovel    → alta poupança, baixo committed_pct, melhor para F3 Architect
#   premium   → perfil misto equilibrado, bom para ambos F2 e F3
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _row(tx_id: int, desc: str, amount: float, dt: date, cat: str,
         recurring: bool = False, tx_type: str | None = None) -> dict:
    return {
        "transaction_id": f"TX{tx_id:04d}", "user_id": "user_teste",
        "account_id": "acc_001", "description": desc,
        "amount": amount, "date": dt,
        "transaction_type": tx_type or ("CREDIT" if amount > 0 else "DEBIT"),
        "category": cat, "is_recurring": recurring, "is_installment": False,
        "context_type": None, "context_confidence": 0.90,
        "context_override_by_user": False, "pj_subcategory": None,
    }


@st.cache_data
def build_transactions(monthly_income: float, monthly_spend: float,
                       perfil_tipo: str = "premium") -> pl.DataFrame:
    """
    Gera 12 meses de transações sintéticas realistas por perfil comportamental.
    Descrições calibradas para ativar os detectors do pipeline User Intelligence.
    """
    today = date.today()
    rows: list[dict] = []
    n = 1  # tx_id counter (closure via list to allow mutation in inner funcs)

    def add(*args, **kwargs) -> None:
        nonlocal n
        rows.append(_row(n, *args, **kwargs))
        n += 1

    # Variação mensal realista (sazonalidade de 12 meses)
    _VAR = [1.05, 0.95, 1.00, 0.92, 0.98, 1.12, 1.03, 0.96, 1.00, 0.94, 1.02, 1.10]

    for m in range(12):
        base = today - timedelta(days=30 * (m + 1))
        v = _VAR[m % 12]
        spend = monthly_spend * v

        # ── EXPLORADOR GLOBAL ────────────────────────────────────────────
        # Ativa: TravelDetector (travel_frequency_score 75-90),
        #        is_travel_related, is_foreign, merchant_category_l2 ∈ {VOO,HOTEL,AIRBNB,LOCADORA}
        #        lifestyle_cluster = EXPLORADOR_GLOBAL
        if perfil_tipo == "viajante":
            # CLT estável
            add("Salário Empresa Tech SA", monthly_income * (2.0 if m == 11 else 1.0),
                base + timedelta(days=5), "Renda", recurring=True)

            # Viagem doméstica: trimestral — voo + hospedagem
            if m % 3 == 0:
                add("LATAM VIAGENS PASSAGEM", -round(spend * 0.18, 2),
                    base + timedelta(days=8), "Viagem")
                add("BOOKING Hotel Fasano RJ", -round(spend * 0.10, 2),
                    base + timedelta(days=9), "Viagem")
                add("LOCALIZA RENT A CAR SP", -round(spend * 0.05, 2),
                    base + timedelta(days=10), "Viagem")

            # Airbnb alternado (todo mês par)
            if m % 2 == 0:
                add("AIRBNB * FLORIANOPOLIS SC", -round(spend * 0.09, 2),
                    base + timedelta(days=14), "Viagem")
            else:
                add("GOL LINHAS AEREAS PASSAGEM", -round(spend * 0.12, 2),
                    base + timedelta(days=6), "Viagem")
                add("DECOLAR HOTEL RESERVA", -round(spend * 0.07, 2),
                    base + timedelta(days=7), "Viagem")

            # Internacional: 8 dos 12 meses (moeda USD/EUR — ativa is_foreign)
            if m not in {2, 9, 11}:
                add("Amazon USD IOF INTERNACIONAL", -round(spend * 0.06, 2),
                    base + timedelta(days=15), "Internacional")
                if m % 3 == 0:
                    add("EXPEDIA EUR EXTERIOR IOF", -round(spend * 0.08, 2),
                        base + timedelta(days=16), "Internacional")

            # Alimentação leve (viajante come fora)
            for i, desc in enumerate(["IFOOD Restaurante Entrega", "Padaria Artesanal Central",
                                       "Supermercado Extra Compra"]):
                add(desc, -round(spend * 0.05, 2), base + timedelta(days=2 + i * 7), "Alimentação")

            # Streaming fidelidade
            add("NETFLIX BRASIL ASSINATURA", -55.90, base + timedelta(days=3), "Assinaturas", recurring=True)
            add("SPOTIFY PREMIUM MENSAL", -21.90, base + timedelta(days=3), "Assinaturas", recurring=True)

            # Moradia e transporte fixos
            add("Aluguel Imobiliária Santos", -round(spend * 0.18, 2),
                base + timedelta(days=1), "Moradia", recurring=True)
            add("Uber APP Corrida", -round(spend * 0.04, 2), base + timedelta(days=11), "Transporte")
            add("Combustível Shell Gasolina", -round(spend * 0.04, 2), base + timedelta(days=20), "Transporte")

        # ── URBANO FOODIE ────────────────────────────────────────────────
        # Ativa: FoodieDetector (foodie_score 72-88),
        #        merchant_category_l2 ∈ {DELIVERY, RESTAURANTE}
        #        lifestyle_cluster = URBANO_FOODIE
        elif perfil_tipo == "foodie":
            add("Salário Empresa Criativa", monthly_income * (2.0 if m == 11 else 1.0),
                base + timedelta(days=5), "Renda", recurring=True)

            # iFood frequente (2-3x por semana)
            for i in range(4):
                add("IFOOD PEDIDO RESTAURANTE", -round(spend * 0.06, 2),
                    base + timedelta(days=1 + i * 7), "Alimentação")
            add("RAPPI DELIVERY MERCADO", -round(spend * 0.04, 2),
                base + timedelta(days=4), "Alimentação")

            # Restaurantes presenciais — alta diversidade de merchants
            for i, rest in enumerate([
                "RESTAURANTE FASANO JANTAR", "SUSHI TEMAKERIA YASSU", "PIZZARIA BAGGIO",
                "HAMBURGER FIVE GUYS", "LANCHONETE SPOLETO ALMOÇO",
                "BAR EMPORIO BRASIL CERVEJA", "RESTAURANTE OUTBACK JANTAR",
            ]):
                add(rest, -round(spend * 0.03, 2),
                    base + timedelta(days=2 + i * 4), "Alimentação")

            # Fine dining mensal (ticket > R$150 — ativa fine_dining_flag)
            add("RESTAURANTE DOM ALEX ATALA", -round(max(spend * 0.05, 160.0), 2),
                base + timedelta(days=21), "Alimentação")

            # Supermercado (compra semanal)
            for i in range(3):
                add("Supermercado Pão de Acucar", -round(spend * 0.06, 2),
                    base + timedelta(days=6 + i * 9), "Alimentação")

            # Mercado gourmet/especialidade
            add("EMPORIO SANTA MARIA VINHO", -round(spend * 0.04, 2),
                base + timedelta(days=17), "Alimentação")
            add("WHOLE FOODS MARKET ORGANICOS", -round(spend * 0.03, 2),
                base + timedelta(days=25), "Alimentação")

            # Streaming + moradia + transporte básicos
            add("NETFLIX BRASIL ASSINATURA", -55.90, base + timedelta(days=3), "Assinaturas", recurring=True)
            add("SPOTIFY PREMIUM MENSAL", -21.90, base + timedelta(days=3), "Assinaturas", recurring=True)
            add("Aluguel Apartamento", -round(spend * 0.20, 2),
                base + timedelta(days=1), "Moradia", recurring=True)
            add("Uber APP Corrida", -round(spend * 0.06, 2), base + timedelta(days=12), "Transporte")
            add("Farmácia DROGASIL Mensal", -round(spend * 0.02, 2), base + timedelta(days=18), "Saúde")

        # ── INVESTIDOR CAUTELOSO ─────────────────────────────────────────
        # Ativa: InvestorDetector (investor_type ATIVO/DIVERSIFICADO),
        #        is_broker_txn, savings_rate 28-38%,
        #        lifestyle_cluster = INVESTIDOR_CAUTELOSO
        elif perfil_tipo == "investidor":
            add("Salário Empresa Contabilidade", monthly_income * (2.0 if m == 11 else 1.0),
                base + timedelta(days=5), "Renda", recurring=True)

            # Investimentos mensais diversificados (ativa _BROKER_KEYWORDS)
            add("TESOURODIRETO STN APLICACAO", -round(monthly_income * 0.15, 2),
                base + timedelta(days=7), "Investimentos")
            add("XP INVESTIMENTOS TED APORTE", -round(monthly_income * 0.10, 2),
                base + timedelta(days=8), "Investimentos")
            if m % 2 == 0:
                add("NUINVEST APORTE CDB", -round(monthly_income * 0.05, 2),
                    base + timedelta(days=9), "Investimentos")
            if m % 3 == 0:
                add("BTG APLICACAO FUNDO", -round(monthly_income * 0.05, 2),
                    base + timedelta(days=10), "Investimentos")

            # Gastos conservadores
            add("Supermercado Carrefour", -round(spend * 0.22, 2), base + timedelta(days=3), "Alimentação")
            add("IFOOD Pedido Semana", -round(spend * 0.05, 2), base + timedelta(days=12), "Alimentação")
            add("Aluguel Banco Inter Condominio", -round(spend * 0.22, 2),
                base + timedelta(days=1), "Moradia", recurring=True)
            add("Combustível Shell", -round(spend * 0.08, 2), base + timedelta(days=14), "Transporte")
            add("Farmácia Drogasil Vitaminas", -round(spend * 0.05, 2), base + timedelta(days=20), "Saúde")

            # Streaming básico (não exagera)
            add("NETFLIX BRASIL ASSINATURA", -45.90, base + timedelta(days=3), "Assinaturas", recurring=True)
            add("AMAZON PRIME VIDEO", -19.90, base + timedelta(days=3), "Assinaturas", recurring=True)

            # Educação financeira / cursos
            if m % 2 == 0:
                add("Coursera Assinatura Anual", -round(spend * 0.03, 2),
                    base + timedelta(days=15), "Educação")

        # ── FAMÍLIA ESTRUTURADA ──────────────────────────────────────────
        # Ativa: FamilyDetector (family_score 70-90), FamilyDetector baby signals
        #        merchant_category_l2 ∈ {ESCOLA, SAUDE, FARMACIA, SUPERMERCADO}
        #        lifestyle_cluster = FAMILIA_ESTRUTURADA
        elif perfil_tipo == "familia":
            # CLT estável — mesmo valor todo mês
            add("Salário CLT Empresa Sólida", monthly_income * (2.0 if m == 11 else 1.0),
                base + timedelta(days=5), "Renda", recurring=True)

            # Escola mensal (ativa ESCOLA L2 e FamilyDetector)
            add("COLEGIO SAO JOSE MENSALIDADE", -round(spend * 0.12, 2),
                base + timedelta(days=2), "Educação", recurring=True)
            if m % 3 == 0:
                add("ESCOLA IDIOMAS INGLES", -round(spend * 0.04, 2),
                    base + timedelta(days=3), "Educação")

            # Pediatria / saúde infantil (ativa SAUDE L2 e FamilyDetector)
            add("PLANO SAUDE UNIMED FAMILIA", -round(spend * 0.08, 2),
                base + timedelta(days=4), "Saúde", recurring=True)
            if m % 2 == 0:
                add("PEDIATR CLINICA INFANTIL DR JOAO", -round(spend * 0.04, 2),
                    base + timedelta(days=18), "Saúde")
            if m % 4 == 0:
                add("CLINICA INFANTIL ODONTO", -round(spend * 0.03, 2),
                    base + timedelta(days=22), "Saúde")

            # Farmácia recorrente (ativa FARMACIA L2)
            add("DROGASIL FARMACIA MENSAL", -round(spend * 0.05, 2),
                base + timedelta(days=10), "Saúde", recurring=True)
            add("FARMACIA PACHECO MEDICAMENTOS", -round(spend * 0.03, 2),
                base + timedelta(days=20), "Saúde")

            # Produtos de bebê (ativa _BABY_PRODUCT_KEYWORDS no FamilyDetector)
            add("PAMPERS FRALDA SUPER SECA", -round(spend * 0.04, 2),
                base + timedelta(days=6), "Bebê")
            add("HUGGIES NATURALS FRALDA", -round(spend * 0.03, 2),
                base + timedelta(days=16), "Bebê")

            # Supermercado pesado (SUPERMERCADO L2)
            for i in range(3):
                add("CARREFOUR SUPERMERCADO FAMILIA", -round(spend * 0.07, 2),
                    base + timedelta(days=5 + i * 9), "Alimentação")
            add("PAO DE ACUCAR HORTIFRUTI", -round(spend * 0.04, 2),
                base + timedelta(days=26), "Alimentação")

            # IFOOD ocasional
            add("IFOOD PEDIDO FAMILIA", -round(spend * 0.03, 2), base + timedelta(days=13), "Alimentação")

            # Moradia + transporte
            add("Aluguel Imobiliária Família", -round(spend * 0.20, 2),
                base + timedelta(days=1), "Moradia", recurring=True)
            add("Condomínio Banco Inter", -round(spend * 0.05, 2),
                base + timedelta(days=2), "Moradia", recurring=True)
            add("Combustível Shell Familia", -round(spend * 0.06, 2), base + timedelta(days=15), "Transporte")
            add("NETFLIX BRASIL ASSINATURA", -55.90, base + timedelta(days=3), "Assinaturas", recurring=True)

        # ── MICROEMPREENDEDOR ────────────────────────────────────────────
        # Ativa: MEIDetector (is_likely_mei=True), income_pattern=PJ (irregular)
        #        is_b2b, merchant_category_l2 = COWORKING
        #        lifestyle_cluster = MICROEMPREENDEDOR
        elif perfil_tipo == "mei":
            # PJ income — irregular: múltiplos recebimentos, valores variáveis
            base_income = monthly_income * v
            add("PIX RECEBIDO CLIENTE PREFEITURA", round(base_income * 0.45, 2),
                base + timedelta(days=3), "Renda")
            add("PIX RECEBIDO CLIENTE STARTUP", round(base_income * 0.35, 2),
                base + timedelta(days=10), "Renda")
            if m % 2 == 0:
                add("TED RECEBIDO EMPRESA XYZ", round(base_income * 0.25, 2),
                    base + timedelta(days=18), "Renda")

            # Ferramentas B2B (ativa _B2B_KEYWORDS → is_b2b=True)
            add("CONTA AZUL ASSINATURA MENSAL", -99.90, base + timedelta(days=5), "Serviços", recurring=True)
            add("OMIE SISTEMA GESTAO ERP", -149.00, base + timedelta(days=5), "Serviços", recurring=True)
            if m % 3 == 0:
                add("NOTA FISCAL NFSE PREFEITURA", -15.00, base + timedelta(days=8), "Serviços")
                add("BLING GESTAO COMERCIAL", -89.00, base + timedelta(days=9), "Serviços")

            # Coworking (ativa _COWORKING_KEYWORDS)
            add("WEWORK MENSAL ESCRITORIO", -round(spend * 0.12, 2),
                base + timedelta(days=1), "Serviços", recurring=True)
            if m % 4 == 0:
                add("COWORKING SP SALA REUNIAO", -round(spend * 0.03, 2),
                    base + timedelta(days=14), "Serviços")

            # Alimentação e transporte de trabalho
            add("IFOOD ALMOCO TRABALHO", -round(spend * 0.06, 2), base + timedelta(days=6), "Alimentação")
            add("Supermercado Extra Compras", -round(spend * 0.08, 2), base + timedelta(days=13), "Alimentação")
            add("RAPPI PEDIDO DELIVERY", -round(spend * 0.04, 2), base + timedelta(days=19), "Alimentação")
            add("Uber APP Corrida Trabalho", -round(spend * 0.06, 2), base + timedelta(days=11), "Transporte")
            add("Combustível Posto Shell", -round(spend * 0.05, 2), base + timedelta(days=22), "Transporte")

            # Moradia e streaming
            add("Aluguel Apartamento PJ", -round(spend * 0.18, 2),
                base + timedelta(days=1), "Moradia", recurring=True)
            add("SPOTIFY PREMIUM MENSAL", -21.90, base + timedelta(days=3), "Assinaturas", recurring=True)
            add("AMAZON PRIME VIDEO", -19.90, base + timedelta(days=3), "Assinaturas", recurring=True)

        # ── DIGITAL NATIVO ───────────────────────────────────────────────
        # Ativa: subscription_burn_monthly alto (STREAMING L2, sem DELIVERY)
        #        sem restaurante físico — compras 100% online/digital
        #        lifestyle_cluster = DIGITAL_NATIVO
        # Nota: todos os offsets ≤ day+6 para evitar sangramento de mês
        # (base=hoje-30 → day+6 ainda fica dentro do mesmo mês calendário)
        elif perfil_tipo == "digital":
            add("Salário Empresa Tech Remote", monthly_income * (2.0 if m == 11 else 1.0),
                base + timedelta(days=5), "Renda", recurring=True)

            # Streaming completo — ativa STREAMING L2 e subscription_burn_monthly > 200
            for desc, valor in [
                ("NETFLIX BRASIL ASSINATURA", 55.90),
                ("SPOTIFY PREMIUM MENSAL", 21.90),
                ("DISNEY PLUS ASSINATURA", 33.90),
                ("AMAZON PRIME VIDEO MENSAL", 19.90),
                ("HBO MAX ASSINATURA MAX", 34.90),
                ("GLOBOPLAY ASSINATURA MENSAL", 22.90),
                ("DEEZER PREMIUM MENSAL", 16.90),
            ]:
                add(desc, -valor, base + timedelta(days=3), "Assinaturas", recurring=True)

            # Ferramentas SaaS / cloud — não são STREAMING L2 mas contribuem para diversidade
            add("ADOBE CREATIVE CLOUD", -99.90, base + timedelta(days=3), "Assinaturas", recurring=True)
            add("GitHub Copilot Pro", -39.90, base + timedelta(days=3), "Assinaturas", recurring=True)

            # E-commerce digital — nunca delivery, nunca restaurante físico
            add("AMAZON.COM.BR MARKETPLACE COMPRA", -round(spend * 0.12, 2), base + timedelta(days=2), "Compras Online")
            add("SHOPEE.COM.BR PEDIDO ONLINE", -round(spend * 0.09, 2),       base + timedelta(days=4), "Compras Online")
            add("KABUM INFORMATICA COMPRA",     -round(spend * 0.08, 2),       base + timedelta(days=6), "Compras Online")
            add("AMERICANAS.COM PEDIDO",        -round(spend * 0.07, 2),       base + timedelta(days=5), "Compras Online")

            # Gaming digital
            add("STEAM GAMES COMPRA DIGITAL", -round(spend * 0.05, 2), base + timedelta(days=4), "Lazer")
            if m % 2 == 0:
                add("PlayStation Plus Extra", -44.90, base + timedelta(days=5), "Lazer")

            # PIX para serviços digitais (aumenta pix_proxy via credit_spend_ratio baixo)
            add("PIX NUBANK TRANSFERENCIA", -round(spend * 0.04, 2), base + timedelta(days=3), "Transferências")

            # Alimentação mínima — apenas supermercado online (sem IFOOD/RAPPI/UBER EATS)
            add("Supermercado Extra Online", -round(spend * 0.04, 2), base + timedelta(days=4), "Alimentação")

            # Moradia + transporte mínimos (offsets ≤ 6 dias)
            add("Aluguel Digital Nomad", -round(spend * 0.22, 2),
                base + timedelta(days=1), "Moradia", recurring=True)
            add("Uber APP Corrida",  -round(spend * 0.03, 2), base + timedelta(days=2), "Transporte")
            add("Farmácia Drogasil", -round(spend * 0.02, 2), base + timedelta(days=4), "Saúde")

        # ── COMPRADOR DE IMÓVEL ──────────────────────────────────────────
        # Alta poupança, baixo committed_pct, resilience_score alto
        # Melhor perfil para F3 Architect (confidence_score ~0.85, liquidity_impact baixo)
        elif perfil_tipo == "imovel":
            add("Salário CLT Empresa Sólida", monthly_income * (2.0 if m == 11 else 1.0),
                base + timedelta(days=5), "Renda", recurring=True)
            # Renda extra: bônus trimestral
            if m % 3 == 0:
                add("Bonificação Trimestral Empresa", round(monthly_income * 0.30, 2),
                    base + timedelta(days=20), "Renda")

            # Poupança disciplinada para entrada (ativa InvestorDetector)
            add("TESOURODIRETO STN APLICACAO", -round(monthly_income * 0.20, 2),
                base + timedelta(days=7), "Investimentos")
            add("XP INVESTIMENTOS CDB ENTRADA", -round(monthly_income * 0.10, 2),
                base + timedelta(days=8), "Investimentos")
            add("NUINVEST FUNDO IMOBILIARIO", -round(monthly_income * 0.05, 2),
                base + timedelta(days=9), "Investimentos")

            # Gastos controlados
            add("Supermercado Carrefour", -round(spend * 0.25, 2), base + timedelta(days=4), "Alimentação")
            add("IFOOD Pedido Ocasional", -round(spend * 0.04, 2), base + timedelta(days=14), "Alimentação")
            add("Aluguel Atual Imobiliária", -round(spend * 0.28, 2),
                base + timedelta(days=1), "Moradia", recurring=True)
            add("Condomínio Banco Inter", -round(spend * 0.06, 2),
                base + timedelta(days=2), "Moradia", recurring=True)
            add("Combustível Shell", -round(spend * 0.07, 2), base + timedelta(days=15), "Transporte")
            add("PLANO SAUDE UNIMED", -round(spend * 0.05, 2),
                base + timedelta(days=3), "Saúde", recurring=True)
            add("NETFLIX BRASIL ASSINATURA", -55.90, base + timedelta(days=3), "Assinaturas", recurring=True)
            add("SPOTIFY PREMIUM MENSAL", -21.90, base + timedelta(days=3), "Assinaturas", recurring=True)

        # ── PROFISSIONAL PREMIUM (padrão equilibrado) ────────────────────
        # Perfil misto: alguma viagem, algum investimento, consumo moderado
        # Bom para demonstrar F2 e F3 de forma balanceada
        else:
            add("Salário Empresa ABC Premium", monthly_income * (2.0 if m == 11 else 1.0),
                base + timedelta(days=5), "Renda", recurring=True, tx_type="CREDIT")

            # Alimentação (Nubank ativa eligibility_score bonus)
            add("IFOOD Pedido Nubank", -round(spend * 0.08, 2), base + timedelta(days=3), "Alimentação")
            add("Supermercado Extra Compra", -round(spend * 0.10, 2), base + timedelta(days=10), "Alimentação")
            add("RESTAURANTE OUTBACK JANTAR", -round(spend * 0.05, 2), base + timedelta(days=20), "Alimentação")
            add("PAO DE ACUCAR HORTIFRUTI", -round(spend * 0.04, 2), base + timedelta(days=25), "Alimentação")

            # Viagem moderada (2 trimestres) — ativa TravelDetector parcialmente
            if m % 6 in (0, 1):
                add("LATAM VIAGENS PASSAGEM", -round(spend * 0.12, 2), base + timedelta(days=8), "Viagem")
                add("BOOKING Hotel Reserva", -round(spend * 0.07, 2), base + timedelta(days=9), "Viagem")
            if m % 4 == 0:
                add("AIRBNB BRASIL HOSPEDAGEM", -round(spend * 0.06, 2), base + timedelta(days=15), "Viagem")

            # Internacional esporádico
            if m in {1, 4, 7, 10}:
                add("Amazon USD IOF INTERNACIONAL", -round(spend * 0.05, 2),
                    base + timedelta(days=16), "Internacional")

            # Investimentos moderados
            if m % 2 == 0:
                add("TESOURODIRETO STN APLICACAO", -round(monthly_income * 0.08, 2),
                    base + timedelta(days=7), "Investimentos")
            add("NUINVEST APORTE CDB", -round(monthly_income * 0.05, 2),
                base + timedelta(days=8), "Investimentos")

            # Streaming, saúde, moradia, transporte
            add("NETFLIX BRASIL ASSINATURA", -55.90, base + timedelta(days=3), "Assinaturas", recurring=True)
            add("SPOTIFY PREMIUM MENSAL", -21.90, base + timedelta(days=3), "Assinaturas", recurring=True)
            add("AMAZON PRIME VIDEO", -19.90, base + timedelta(days=3), "Assinaturas", recurring=True)
            add("Aluguel Imobiliária Santos", -round(spend * 0.20, 2),
                base + timedelta(days=1), "Moradia", recurring=True)
            add("Banco Inter Condomínio", -round(spend * 0.05, 2),
                base + timedelta(days=2), "Moradia", recurring=True)
            add("Uber APP Corrida", -round(spend * 0.05, 2), base + timedelta(days=12), "Transporte")
            add("Combustível Shell", -round(spend * 0.04, 2), base + timedelta(days=22), "Transporte")
            add("Farmácia DROGASIL Mensal", -round(spend * 0.04, 2), base + timedelta(days=18), "Saúde")
            add("ACADEMIA SMARTFIT MENSAL", -119.90, base + timedelta(days=5), "Saúde", recurring=True)
            add("Curso Coursera Educação", -round(spend * 0.03, 2), base + timedelta(days=14), "Educação")

    return pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Date))


@st.cache_resource
def get_optimizer():
    from app.optimizer.services.optimizer_service import OptimizerService
    return OptimizerService()


@st.cache_resource
def get_architect():
    from app.architect.services.architect_service import ArchitectService
    return ArchitectService()


@st.cache_resource
def get_card_kb():
    from app.optimizer.card_loader import CardKnowledgeBase
    kb = CardKnowledgeBase()
    kb.load()
    return kb


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TOOLS — implementação real das funcionalidades
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def tool_perfil_consumo(monthly_income: float, monthly_spend: float,
                        safe_to_spend: float, perfil_tipo: str = "premium") -> dict:
    from app.optimizer.profiler import ConsumptionProfiler
    df = build_transactions(monthly_income, monthly_spend, perfil_tipo)
    profiler = ConsumptionProfiler()
    p = profiler.build(df, safe_to_spend=safe_to_spend)
    return {
        # ── Financeiro básico ──
        "gasto_medio_mensal": round(p.monthly_avg_spend, 2),
        "renda_estimada_mensal": round(p.estimated_monthly_income, 2),
        "cobertura_meses": p.data_coverage_months,
        "estabilidade_gasto": round(p.spending_stability, 2),
        "gasto_internacional_mensal": round(p.international_spend_monthly, 2),
        "gasto_viagem_mensal": round(p.travel_spend_monthly, 2),
        "comprometido_pct": round(p.committed_percentage, 2),
        "savings_rate_pct": round(getattr(p, "savings_rate", 0.0), 1),
        "gasto_por_categoria": p.spend_by_category,
        # ── Income profile ──
        "income_profile": {
            "padrao": p.income_profile.income_pattern if p.income_profile else None,
            "renda_liquida": round(p.income_profile.monthly_net_income, 2) if p.income_profile else None,
            "confianca": round(p.income_profile.confidence, 2) if p.income_profile else None,
        },
        # ── User Intelligence (Fase 1 + 2) ──
        "lifestyle_cluster": getattr(p, "lifestyle_cluster", "NAO_CLASSIFICADO"),
        "cluster_scores": getattr(p, "cluster_scores", {}),
        "travel_frequency_score": round(getattr(p, "travel_frequency_score", 0.0), 1),
        "travel_profile": getattr(p, "travel_profile", "OCASIONAL"),
        "foodie_score": round(getattr(p, "foodie_score", 0.0), 1),
        "foodie_profile": getattr(p, "foodie_profile", "BASICO"),
        "investor_type": getattr(p, "investor_type", "NONE"),
        "is_likely_mei": getattr(p, "is_likely_mei", False),
        "family_score": round(getattr(p, "family_score", 0.0), 1),
        "merchant_diversity_score": round(getattr(p, "merchant_diversity_score", 0.0), 1),
        "subscription_burn_mensal": round(getattr(p, "subscription_burn_monthly", 0.0), 2),
        # ── Financial Stress Score ──
        "fss": round(getattr(p, "fss", 0.0), 1),
        "fss_nivel": getattr(p, "fss_level", "SAUDAVEL"),
        # ── Inteligência temporal ──
        "pico_gasto_dia_mes": getattr(p, "peak_spend_day_of_month", None),
        "padrao_gasto": getattr(p, "spending_pattern", "SEM_DADOS"),
        "melhor_dia_notificacao": getattr(p, "best_notification_day", None),
    }


def tool_prever_gastos(monthly_income: float, monthly_spend: float,
                       perfil_tipo: str = "premium") -> dict:
    """T3.2 — SpendPredictor: previsão de gastos dos próximos 30 dias por categoria."""
    from app.ml.spend_predictor import SpendPredictor
    df = build_transactions(monthly_income, monthly_spend, perfil_tipo)
    predictor = SpendPredictor()
    predictions = predictor.predict_by_category(df, min_monthly_spend=80.0)
    return {
        "previsao_30_dias": {
            cat: {
                "previsto_brl": pred.predicted_spend,
                "intervalo": [pred.lower_bound, pred.upper_bound],
                "metodo": pred.method,
                "meses_historico": pred.months_of_data,
            }
            for cat, pred in sorted(
                predictions.items(),
                key=lambda x: x[1].predicted_spend,
                reverse=True,
            )
        },
        "nota": (
            "Método 'moving_average' = média dos últimos 3 meses. "
            "Método 'prophet' = modelo de série temporal (requer ≥6 meses e pacote prophet instalado)."
        ),
    }


def tool_otimizar_cartao(
    monthly_income: float, monthly_spend: float, safe_to_spend: float,
    current_cards: list[str], perfil_tipo: str = "premium",
) -> dict:
    from app.optimizer.models import OptimizationRequest
    df = build_transactions(monthly_income, monthly_spend, perfil_tipo)
    svc = get_optimizer()
    req = OptimizationRequest(
        user_id="user_teste",
        current_cards=current_cards,
        safe_to_spend=safe_to_spend,
        monthly_income=monthly_income,
    )
    report = svc.analyze(req, df)
    result: dict = {
        "recomendacao": report.recommendation_type.value,
        "avisos": report.warnings,
        "cartoes_avaliados": len(report.all_cards),
    }
    if report.best_card:
        bc = report.best_card
        result["melhor_cartao"] = {
            "nome": bc.card_name,
            "emissor": bc.issuer,
            "bandeira": bc.flag.value,
            "anuidade_efetiva": bc.annuity_effective,
            "anuidade_isenta": bc.annuity_waived,
            "ganho_liquido_esperado_anual": round(bc.net_gain_expected, 2),
            "ganho_liquido_min": round(bc.net_gain_min, 2),
            "ganho_liquido_max": round(bc.net_gain_max, 2),
            "risco_liquidez": bc.liquidity_risk.value,
            "confianca": round(bc.confidence_score, 2),
            "elegibilidade": round(bc.eligibility_score, 2),
            "beneficios_destaque": bc.benefit_highlights,
            "passos_explicativos": bc.explanation_steps,
            "avisos_cartao": bc.warnings,
        }
    ranking = []
    for c in report.all_cards[:5]:
        ranking.append({
            "nome": c.card_name,
            "emissor": c.issuer,
            "ganho_liquido_esperado": round(c.net_gain_expected, 2),
            "anuidade": c.annuity_effective,
            "isenta": c.annuity_waived,
            "confianca": round(c.confidence_score, 2),
            "risco": c.liquidity_risk.value,
        })
    result["top5_ranking"] = ranking
    return result


def tool_roi_cartao_atual(
    card_id: str, monthly_income: float, monthly_spend: float,
    safe_to_spend: float, perfil_tipo: str = "premium",
) -> dict:
    from app.optimizer.profiler import ConsumptionProfiler
    from app.optimizer.simulator import CardSimulator
    df = build_transactions(monthly_income, monthly_spend, perfil_tipo)
    profiler = ConsumptionProfiler()
    profile = profiler.build(df, safe_to_spend=safe_to_spend)
    kb = get_card_kb()
    card = next((c for c in kb._cards if c.card_id == card_id), None)
    if card is None:
        return {"erro": f"Cartão '{card_id}' não encontrado. IDs disponíveis: " +
                ", ".join(c.card_id for c in kb._cards)}
    sim = CardSimulator()
    result = sim.simulate(card=card, profile=profile, safe_to_spend=safe_to_spend)
    net_roi = result.points_value_expected - card.base_annuity
    if net_roi > 0:
        verdict = "VALE_A_PENA"
        explicacao = f"A anuidade de R$ {card.base_annuity:,.2f} é compensada pelos R$ {result.points_value_expected:,.2f} em recompensas."
    elif net_roi > -200:
        verdict = "MARGINAL"
        explicacao = f"Prejuízo de R$ {abs(net_roi):,.2f}/ano. Avalie se os benefícios extras justificam."
    else:
        verdict = "NAO_VALE"
        explicacao = f"Prejuízo líquido de R$ {abs(net_roi):,.2f}/ano. Considere trocar de cartão."
    spend_for_waiver = None
    if card.waiver_rules.type == "spend_threshold" and card.waiver_rules.threshold:
        if profile.monthly_avg_spend < card.waiver_rules.threshold / 12:
            spend_for_waiver = round(card.waiver_rules.threshold / 12 - profile.monthly_avg_spend, 2)
    return {
        "cartao": card.name,
        "emissor": card.issuer,
        "anuidade_paga": card.base_annuity,
        "recompensas_geradas_anual": round(result.points_value_expected, 2),
        "roi_liquido_anual": round(net_roi, 2),
        "anuidade_isenta": result.annuity_waived,
        "gasto_adicional_para_isentar": spend_for_waiver,
        "veredicto": verdict,
        "explicacao": explicacao,
        "beneficios_tags": [t.value for t in card.benefit_tags],
    }


def tool_carteira_ideal(
    monthly_income: float, monthly_spend: float, safe_to_spend: float, max_cards: int,
    current_card_ids: list[str] | None = None, perfil_tipo: str = "premium",
) -> dict:
    from app.optimizer.multi_card_strategy import MultiCardStrategist
    from app.optimizer.profiler import ConsumptionProfiler
    df = build_transactions(monthly_income, monthly_spend, perfil_tipo)
    profiler = ConsumptionProfiler()
    profile = profiler.build(df, safe_to_spend=safe_to_spend)
    kb = get_card_kb()
    eligible = kb.filter_eligible(
        annual_income=monthly_income * 12,
        current_card_ids=current_card_ids,
        exclude_consigned=True,
    )
    strategy = MultiCardStrategist()
    result = strategy.optimize_portfolio(
        profile=profile,
        eligible_cards=eligible,
        max_cards=max_cards,
    )
    wallet = []
    for ca in result.cards:
        wallet.append({
            "cartao": ca.card.name,
            "categorias_direcionadas": ca.assigned_categories,
            "gasto_mensal_direcionado": round(ca.monthly_spend_directed, 2),
            "retorno_anual": round(ca.annual_return_from_this_card, 2),
            "anuidade_efetiva": round(ca.effective_annuity, 2),
            "motivo": ca.reason,
        })
    return {
        "retorno_anual_total": round(result.total_annual_return, 2),
        "ganho_liquido_total": round(result.net_annual_gain, 2),
        "ganho_vs_cartao_unico": round(result.vs_single_best, 2),
        "quantidade_cartoes": len(result.cards),
        "carteira": wallet,
        "explicacao": result.explanation,
    }


def tool_simular_aquisicao(
    valor: float, entrada: float, tipo: str, prazo_meses: int,
    perfil_risco: str, safe_to_spend: float, incluir_consorcio: bool,
    renda_aluguel: float | None, monthly_income: float,
) -> dict:
    from app.architect.models import SimulationRequest
    req_kwargs: dict = {
        "user_id": "user_teste",
        "target_amount": valor,
        "down_payment": entrada,
        "max_monthly_budget": safe_to_spend,
        "risk_profile": perfil_risco,
        "asset_type": tipo,
        "financing_months": prazo_meses,
        "amortization_method": "PRICE",
        "include_consortium": incluir_consorcio,
        "prefers_consortium": False,
        "monthly_income": monthly_income,
    }
    if tipo == "IMOVEL":
        req_kwargs["transaction_costs_pct"] = 0.04
    if renda_aluguel and renda_aluguel > 0:
        req_kwargs["expected_rental_income"] = renda_aluguel
    svc = get_architect()
    req = SimulationRequest(**req_kwargs)
    resp = svc.simulate(req, safe_to_spend=safe_to_spend)

    result: dict = {
        "estrategia_recomendada": resp.recommended_strategy.value,
        "custo_total_esperado": round(resp.costs.expected_cost, 0),
        "custo_total_minimo": round(resp.costs.min_cost, 0),
        "custo_total_maximo": round(resp.costs.max_cost, 0),
        "meses_para_aquisicao": resp.months_to_achieve,
        "impacto_liquidez_pct": round(resp.liquidity_impact * 100, 1),
        "confianca": round(resp.confidence_score, 2),
        "npv": {
            "financiamento": round(resp.npv.financing, 0),
            "consorcio": round(resp.npv.consortium, 0) if resp.npv.consortium else None,
            "poupar_investir": round(resp.npv.save_invest, 0),
            "break_even_cet": f"{resp.npv.break_even_cet:.1%}" if resp.npv.break_even_cet else None,
        },
        "avisos": resp.warnings,
        "plano_acao": [
            {"passo": s.step, "acao": s.action, "valor": s.amount, "critico": s.is_critical}
            for s in resp.action_plan
        ],
    }
    if resp.consortium_probability:
        prob = resp.consortium_probability
        result["consorcio_probabilidades"] = {
            "em_12_meses": f"{prob.win_12m:.0%}",
            "em_24_meses": f"{prob.win_24m:.0%}",
            "em_36_meses": f"{prob.win_36m:.0%}",
            "prazo_esperado_meses": prob.expected_months,
        }
    if resp.rental_leverage_plan:
        rlp = resp.rental_leverage_plan
        result["alavancagem_aluguel"] = {
            "cobertura_pct": round(rlp.rental_coverage_pct, 1),
            "desembolso_real_mensal": round(rlp.monthly_out_of_pocket, 0),
            "auto_sustentavel": rlp.is_self_sustaining,
            "custo_liquido_real": round(rlp.net_acquisition_cost, 0),
            "narrativa": rlp.narrative,
        }
    if resp.compound_strategies:
        result["estrategias_compostas"] = [
            {
                "tipo": cs.strategy_type.value,
                "parcela_bruta": round(cs.monthly_gross_payment, 0),
                "custo_liquido_mensal": round(cs.monthly_net_cost, 0),
                "auto_sustentavel": cs.is_self_sustaining,
                "npv": round(cs.npv, 0),
                "narrativa": cs.narrative,
            }
            for cs in resp.compound_strategies
        ]
    if resp.efficient_strategy:
        ef = resp.efficient_strategy
        result["estrategia_eficiente"] = {
            "tipo": ef.strategy_type.value,
            "score": round(ef.efficiency_score, 2),
            "perda_capital_pct": round(ef.capital_loss_pct, 1),
            "prontidao": ef.readiness_flag,
            "justificativa": ef.rationale,
        }
    if resp.card_optimization_bonus:
        b = resp.card_optimization_bonus
        result["bonus_cartao_parcelas"] = {
            "cartao": b.best_card_name,
            "retorno_mensal": round(b.monthly_bonus_brl, 2),
            "retorno_total": round(b.total_bonus_brl, 2),
            "reducao_custo_pct": round(b.effective_cost_reduction_pct, 1),
            "narrativa": b.narrative,
        }
    return result


def tool_timing_scenarios(
    valor: float, entrada_atual: float, poupanca_mensal: float,
    tipo: str, prazo_meses: int, safe_to_spend: float,
    cenarios_espera: list[int],
) -> dict:
    from app.architect.models import SimulationRequest
    from app.architect.simulators.strategy_engine import StrategyEngine
    svc = get_architect()
    req = SimulationRequest(
        user_id="user_teste",
        target_amount=valor,
        down_payment=entrada_atual,
        max_monthly_budget=safe_to_spend,
        asset_type=tipo,
        financing_months=prazo_meses,
        include_consortium=True,
    )
    try:
        market_rates = svc.fetch_market_rates(req)
    except Exception:
        market_rates = {
            "selic_annual": 0.1475, "cdi_annual": 0.1465,
            "best_cet_annual": 0.20, "ipca_annual": 0.045,
        }
    engine = StrategyEngine()
    scenarios = engine.simulate_timing_scenarios(
        request=req,
        market_rates=market_rates,
        monthly_savings=poupanca_mensal,
        scenarios=sorted(cenarios_espera),
    )
    return {
        "cenarios": [
            {
                "espera_meses": s.wait_months,
                "entrada_acumulada": round(s.accumulated_down_payment, 0),
                "principal": round(s.new_principal, 0),
                "parcela_mensal": round(s.monthly_payment, 0),
                "custo_total": round(s.total_cost_expected, 0),
                "economia_vs_agora": round(s.saving_vs_now, 0),
                "estrategia": s.recommended_strategy.value,
                "texto": s.comparison_text,
            }
            for s in scenarios
        ]
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TOOL SCHEMAS (definição para o claude-haiku)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TOOLS = [
    {
        "name": "perfil_consumo",
        "description": (
            "Analisa as transações e retorna perfil completo de consumo e inteligência comportamental: "
            "gasto médio, renda, estabilidade, categorias, cluster de estilo de vida (lifestyle_cluster), "
            "travel_frequency_score, foodie_score, investor_type, FSS (estresse financeiro), "
            "subscription_burn e padrão temporal. Use para qualquer pergunta sobre perfil financeiro."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "prever_gastos",
        "description": (
            "Previsão de gastos dos próximos 30 dias por categoria usando SpendPredictor (T3.2). "
            "Retorna valor previsto, intervalo de confiança (P10-P90) e método usado "
            "(prophet ou moving_average). Use quando o usuário perguntar quanto vai gastar "
            "no próximo mês ou querer planejar gastos futuros."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "otimizar_cartao",
        "description": (
            "Executa o Optimizer (F2) completo: analisa transações reais, "
            "filtra cartões elegíveis por renda, simula retorno de cada um "
            "(pontos/cashback vs anuidade) e retorna ranking com o melhor cartão recomendado. "
            "Use quando o usuário perguntar sobre cartões, milhas, cashback ou qual cartão pedir."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cartoes_atuais": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "IDs dos cartões que o usuário já possui. Ex: ['nubank-roxinho']",
                },
            },
            "required": [],
        },
    },
    {
        "name": "roi_cartao_atual",
        "description": (
            "Calcula o ROI do cartão atual do usuário: quanto ele gerou em recompensas "
            "vs quanto pagou de anuidade. Veredicto: VALE_A_PENA, MARGINAL ou NAO_VALE. "
            "Use quando o usuário perguntar se vale a pena manter um cartão específico."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "card_id": {
                    "type": "string",
                    "description": (
                        "ID do cartão na base de conhecimento. "
                        "Exemplos válidos: nubank-roxinho, nubank-ultravioleta, inter-standard, "
                        "inter-win, inter-black, itau-platinum, itau-personnalite, itau-personnalite-gold, "
                        "c6-standard, c6-carbon, xp-visa-infinite, picpay-card, meliuz-visa, "
                        "neon-visa, santander-free, santander-unique, bb-ourocard-gold, "
                        "bb-ourocard-infinite, bradesco-amex-gold, bradesco-amex-platinum, "
                        "smiles-gold-amex, latam-pass-black, amazon-prime-mastercard, "
                        "btgplus-mastercard, bradesco-diners-club"
                    ),
                },
            },
            "required": ["card_id"],
        },
    },
    {
        "name": "carteira_ideal",
        "description": (
            "Calcula a carteira ideal de múltiplos cartões (M2.2): distribui as categorias de gasto "
            "pelo cartão com maior retorno em cada uma. Retorna a combinação que maximiza recompensas. "
            "Use quando o usuário perguntar sobre usar mais de um cartão ou otimizar sua carteira."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "max_cartoes": {
                    "type": "integer",
                    "description": "Número máximo de cartões na carteira (1 a 4). Padrão: 2.",
                    "default": 2,
                },
            },
            "required": [],
        },
    },
    {
        "name": "simular_aquisicao",
        "description": (
            "Executa o Architect (F3): compara Financiamento, Consórcio e Poupar/Investir "
            "para aquisição de um bem. Retorna NPV de cada estratégia, impacto na liquidez, "
            "probabilidades do consórcio, plano de ação e alavancagem por aluguel (se informado). "
            "Use para perguntas sobre comprar imóvel, carro, reforma, financiamento, consórcio."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "valor": {
                    "type": "number",
                    "description": "Valor total do bem em R$.",
                },
                "entrada": {
                    "type": "number",
                    "description": "Valor de entrada disponível em R$. Padrão: 0.",
                    "default": 0,
                },
                "tipo": {
                    "type": "string",
                    "enum": ["IMOVEL", "VEICULO", "REFORMA", "VIAGEM", "OUTRO"],
                    "description": "Tipo do bem.",
                },
                "prazo_meses": {
                    "type": "integer",
                    "description": "Prazo do financiamento em meses. Padrão: 48 para veículo, 240 para imóvel.",
                    "default": 48,
                },
                "perfil_risco": {
                    "type": "string",
                    "enum": ["conservador", "moderado", "agressivo"],
                    "description": "Perfil de risco do usuário. Padrão: moderado.",
                    "default": "moderado",
                },
                "incluir_consorcio": {
                    "type": "boolean",
                    "description": "Incluir estratégia de consórcio na comparação. Padrão: true.",
                    "default": True,
                },
                "renda_aluguel": {
                    "type": "number",
                    "description": "Renda mensal de aluguel esperada em R$ (apenas para IMOVEL). Opcional.",
                },
            },
            "required": ["valor", "tipo"],
        },
    },
    {
        "name": "timing_scenarios",
        "description": (
            "Simula cenários de timing (M3.4): 'e se eu esperar N meses?'. "
            "Compara o custo de comprar agora vs esperar acumulando mais entrada. "
            "Use quando o usuário perguntar se vale esperar para comprar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "valor": {
                    "type": "number",
                    "description": "Valor total do bem em R$.",
                },
                "entrada_atual": {
                    "type": "number",
                    "description": "Entrada disponível hoje em R$.",
                    "default": 0,
                },
                "poupanca_mensal": {
                    "type": "number",
                    "description": "Quanto consegue poupar por mês em R$.",
                },
                "tipo": {
                    "type": "string",
                    "enum": ["IMOVEL", "VEICULO", "REFORMA", "VIAGEM", "OUTRO"],
                    "default": "OUTRO",
                },
                "prazo_meses": {
                    "type": "integer",
                    "description": "Prazo do financiamento em meses.",
                    "default": 48,
                },
                "cenarios_espera": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Lista de meses para simular. Ex: [0, 12, 24, 36].",
                    "default": [0, 6, 12, 24, 36],
                },
            },
            "required": ["valor", "poupanca_mensal"],
        },
    },
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXECUTOR DE TOOLS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def execute_tool(name: str, inputs: dict, monthly_income: float, monthly_spend: float,
                 safe_to_spend: float, current_card: str = "(nenhum)",
                 perfil_tipo: str = "premium") -> dict:
    active_cards = [current_card] if current_card != "(nenhum)" else []
    try:
        if name == "perfil_consumo":
            return tool_perfil_consumo(monthly_income, monthly_spend, safe_to_spend, perfil_tipo)
        if name == "prever_gastos":
            return tool_prever_gastos(monthly_income, monthly_spend, perfil_tipo)
        if name == "otimizar_cartao":
            return tool_otimizar_cartao(
                monthly_income, monthly_spend, safe_to_spend,
                current_cards=inputs.get("cartoes_atuais") or active_cards,
                perfil_tipo=perfil_tipo,
            )
        if name == "roi_cartao_atual":
            return tool_roi_cartao_atual(
                card_id=inputs.get("card_id") or (active_cards[0] if active_cards else ""),
                monthly_income=monthly_income, monthly_spend=monthly_spend,
                safe_to_spend=safe_to_spend, perfil_tipo=perfil_tipo,
            )
        if name == "carteira_ideal":
            return tool_carteira_ideal(
                monthly_income, monthly_spend, safe_to_spend,
                max_cards=inputs.get("max_cartoes", 2),
                current_card_ids=active_cards, perfil_tipo=perfil_tipo,
            )
        if name == "simular_aquisicao":
            return tool_simular_aquisicao(
                valor=inputs["valor"],
                entrada=inputs.get("entrada", 0),
                tipo=inputs["tipo"],
                prazo_meses=inputs.get("prazo_meses", 240 if inputs["tipo"] == "IMOVEL" else 48),
                perfil_risco=inputs.get("perfil_risco", "moderado"),
                safe_to_spend=safe_to_spend,
                incluir_consorcio=inputs.get("incluir_consorcio", True),
                renda_aluguel=inputs.get("renda_aluguel"),
                monthly_income=monthly_income,
            )
        if name == "timing_scenarios":
            return tool_timing_scenarios(
                valor=inputs["valor"],
                entrada_atual=inputs.get("entrada_atual", 0),
                poupanca_mensal=inputs["poupanca_mensal"],
                tipo=inputs.get("tipo", "OUTRO"),
                prazo_meses=inputs.get("prazo_meses", 48),
                safe_to_spend=safe_to_spend,
                cenarios_espera=inputs.get("cenarios_espera", [0, 6, 12, 24, 36]),
            )
        return {"erro": f"Tool '{name}' não reconhecida."}
    except Exception as e:
        import traceback
        return {"erro": str(e), "detalhe": traceback.format_exc()}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SYSTEM PROMPT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_system(monthly_income: float, monthly_spend: float, safe_to_spend: float, current_card: str) -> str:
    return f"""Você é Nexa, assistente financeiro pessoal brasileiro inteligente.

## Dados do usuário (sintéticos para teste)
- Renda mensal: R$ {monthly_income:,.0f}
- Gasto médio mensal: R$ {monthly_spend:,.0f}
- Safe-to-spend estimado: R$ {safe_to_spend:,.0f}
- Cartão atual: {current_card}

## Instruções gerais
- Responda SEMPRE em português brasileiro, de forma clara e direta.
- Use as ferramentas disponíveis para buscar dados reais antes de responder sobre finanças.
- Nunca invente números — execute a ferramenta e use os dados retornados.
- Seja objetivo: destaque o que é mais importante para o usuário tomar uma decisão.
- Use valores em R$ com formatação brasileira (ex: R$ 1.200,00).

## F2 — Optimizer de Cartões
IDs de cartão válidos na base de conhecimento (25 cartões):
Nubank: nubank-roxinho (1% cashback, grátis), nubank-ultravioleta (pontos premium, lounge)
Inter: inter-standard (0,5% cashback), inter-win, inter-black (1,5% cashback, lounge)
Itaú: itau-platinum, itau-personnalite, itau-personnalite-gold (pontos premium)
C6: c6-standard (grátis), c6-carbon (pontos + lounge)
Outros: xp-visa-infinite, picpay-card, meliuz-visa, neon-visa, santander-free,
santander-unique, bb-ourocard-gold, bb-ourocard-infinite, bradesco-amex-gold,
bradesco-amex-platinum, bradesco-diners-club, smiles-gold-amex, latam-pass-black,
amazon-prime-mastercard, btgplus-mastercard

Use `roi_cartao_atual` quando o usuário perguntar sobre um cartão específico (veredicto: VALE_A_PENA / MARGINAL / NAO_VALE).
Use `carteira_ideal` para montar combinação multi-cartão que maximize retorno por categoria.

## F3 — Architect de Aquisições
Tipos de bem suportados (campo `tipo` em `simular_aquisicao`):
- IMOVEL — apartamento/casa, mín R$50k, prazo 120–360 meses
- VEICULO — carro/moto, mín R$5k, prazo 36–84 meses
- REFORMA — obra/reforma, mín R$15k, prazo 24–120 meses
- VIAGEM — viagem nacional/internacional, mín R$10k, prazo 12–60 meses
- OUTRO — qualquer bem, mín R$1k, prazo 12–120 meses

Estratégias comparadas: FINANCING, CONSORTIUM, SAVE_INVEST.
Estratégias compostas (quando `renda_aluguel` for informado): FINANCING_RENTAL, CONSORTIUM_SELIC_RENTAL.
Quando mostrar comparações, use os NPVs retornados — financing NPV menor = mais barato.
Use `timing_scenarios` quando o usuário perguntar "vale esperar N meses?".
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AGENTIC LOOP — tool use com claude-haiku
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_agent(
    messages: list[dict],
    monthly_income: float, monthly_spend: float, safe_to_spend: float,
    current_card: str, perfil_tipo: str,
    tool_log_placeholder,
) -> tuple[str, list[dict]]:
    """
    Agentic loop: claude-haiku chama tools até retornar end_turn.
    Retorna (resposta_final, messages_atualizados).
    """
    client = get_client()
    system = build_system(monthly_income, monthly_spend, safe_to_spend, current_card)
    tool_calls_made: list[str] = []

    while True:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        # Adiciona resposta do assistente ao histórico
        assistant_content = resp.content
        messages = messages + [{"role": "assistant", "content": assistant_content}]

        if resp.stop_reason == "end_turn":
            text = next((b.text for b in resp.content if hasattr(b, "text")), "")
            return text, messages

        if resp.stop_reason == "tool_use":
            tool_results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input
                tool_calls_made.append(tool_name)

                # Atualiza o log de tools na interface
                tool_log_placeholder.info(
                    "🔧 **Chamando:** " + " → ".join(f"`{t}`" for t in tool_calls_made)
                )

                with st.spinner(f"⚙️ Executando `{tool_name}`..."):
                    result = execute_tool(
                        tool_name, tool_input,
                        monthly_income, monthly_spend, safe_to_spend,
                        current_card=current_card, perfil_tipo=perfil_tipo,
                    )

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })

            messages = messages + [{"role": "user", "content": tool_results}]
            continue

        # stop_reason inesperado
        break

    return "(sem resposta)", messages


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

st.set_page_config(page_title="Nexa — Chat F2 + F3", page_icon="🏦", layout="wide")

st.title("🏦 Nexa — Chat Financeiro (F2 + F3)")
st.caption("IA: claude-haiku-4-5-20251001 · Tool use real · Dados sintéticos configuráveis")

# ── Sidebar ───────────────────────────────────────────────────────

_CLUSTER_HINT = {
    "viajante":   "EXPLORADOR_GLOBAL",
    "foodie":     "URBANO_FOODIE",
    "investidor": "INVESTIDOR_CAUTELOSO",
    "familia":    "FAMILIA_ESTRUTURADA",
    "mei":        "MICROEMPREENDEDOR",
    "digital":    "DIGITAL_NATIVO",
    "imovel":     "INVESTIDOR_CAUTELOSO",
    "premium":    "EXPLORADOR_GLOBAL / misto",
}

PERFIS = {
    # ── Perfis de User Intelligence (F2) ─────────────────────────────────────
    # Cluster: EXPLORADOR_GLOBAL | travel_frequency_score 78-88 | recomenda milhas/lounge
    "✈️  Explorador Global (R$ 12k)":     {"income": 12_000, "spend":  7_000, "safe":  5_000, "tipo": "viajante"},
    # Cluster: URBANO_FOODIE | foodie_score 72-85 | recomenda cashback alimentação
    "🍽️  Urbano Foodie (R$ 9k)":          {"income":  9_000, "spend":  6_500, "safe":  2_500, "tipo": "foodie"},
    # Cluster: INVESTIDOR_CAUTELOSO | investor_type ATIVO | savings_rate 28-38%
    "📈  Investidor Cauteloso (R$ 11k)":  {"income": 11_000, "spend":  5_500, "safe":  5_500, "tipo": "investidor"},
    # Cluster: FAMILIA_ESTRUTURADA | family_score 70-88 | recomenda cashback super/farmácia
    "👨‍👩‍👧  Família Estruturada (R$ 13k)":   {"income": 13_000, "spend":  8_500, "safe":  4_500, "tipo": "familia"},
    # Cluster: MICROEMPREENDEDOR | is_likely_mei=True | income_pattern=PJ
    "💼  Microempreendedor MEI (R$ 8k)":  {"income":  8_000, "spend":  5_000, "safe":  3_000, "tipo": "mei"},
    # Cluster: DIGITAL_NATIVO | subscription_burn ~R$206/mês | sem delivery, compras 100% digital
    "📱  Digital Nativo (R$ 7k)":         {"income":  7_000, "spend":  4_500, "safe":  2_500, "tipo": "digital"},
    # ── Perfis focados em F3 (Architect) ─────────────────────────────────────
    # Alta poupança, baixo committed_pct → confidence_score ~0.85 no Architect
    "🏗️  Comprador de Imóvel (R$ 20k)":   {"income": 20_000, "spend":  9_000, "safe": 11_000, "tipo": "imovel"},
    # Perfil equilibrado — bom para ambos F2 e F3
    "💼  Profissional Premium (R$ 15k)":  {"income": 15_000, "spend":  8_500, "safe":  6_500, "tipo": "premium"},
}

with st.sidebar:
    st.header("⚙️ Perfil de Teste")
    perfil_nome = st.selectbox("Perfil base", list(PERFIS.keys()))
    p = PERFIS[perfil_nome]
    perfil_tipo    = p["tipo"]
    monthly_income = st.number_input("Renda mensal (R$)", value=p["income"], step=500)
    monthly_spend  = st.number_input("Gasto mensal (R$)", value=p["spend"],  step=200)
    safe_to_spend  = st.number_input("Safe-to-spend (R$)", value=p["safe"],  step=200)
    st.caption(f"🧠 Cluster esperado: **{_CLUSTER_HINT.get(perfil_tipo, '—')}**")
    current_card   = st.selectbox(
        "Cartão atual",
        [
            "(nenhum)",
            # Nubank
            "nubank-roxinho", "nubank-ultravioleta",
            # Inter
            "inter-standard", "inter-win", "inter-black",
            # Itaú
            "itau-platinum", "itau-personnalite", "itau-personnalite-gold",
            # C6
            "c6-standard", "c6-carbon",
            # Outros
            "xp-visa-infinite", "picpay-card", "meliuz-visa",
            "neon-visa", "santander-free", "santander-unique",
            "bb-ourocard-gold", "bb-ourocard-infinite",
            "bradesco-amex-gold", "bradesco-amex-platinum",
            "smiles-gold-amex", "latam-pass-black",
            "amazon-prime-mastercard", "btgplus-mastercard",
            "bradesco-diners-club",
        ],
    )
    st.divider()
    st.caption("**Ferramentas disponíveis:**")
    for t in TOOLS:
        st.caption(f"• `{t['name']}`")
    st.divider()
    if st.button("🗑️ Limpar conversa"):
        st.session_state.pop("messages", None)
        st.rerun()

# ── Estado do chat ────────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state["messages"] = []

# ── Sugestões de perguntas ────────────────────────────────────────

# ── F2: uma pergunta por tool ─────────────────────────────────────
# perfil_consumo → gastos por categoria
# otimizar_cartao → ranking completo com best_card
# roi_cartao_atual → veredicto VALE/MARGINAL/NAO_VALE + gasto_adicional_para_isentar
# carteira_ideal → MultiCardStrategy, até 4 cartões
SUGESTOES_F2 = [
    # perfil_consumo — intelligence completa
    "Analise meu perfil completo: cluster de estilo de vida, score de viagem e estresse financeiro.",
    "Qual meu lifestyle cluster e o que ele diz sobre meus hábitos de consumo?",
    # otimizar_cartao — ranker hiperpersonalizado (T2.4)
    "Qual o melhor cartão para pedir com minha renda e padrão de gastos atual?",
    "Com meu perfil de viajante frequente, qual cartão gera mais milhas e acesso a lounge?",
    # roi_cartao_atual — veredicto VALE/MARGINAL/NAO_VALE
    "Vale a pena manter o nubank-roxinho ou devo trocar por outro cartão?",
    "Analise o ROI do latam-pass-black: a anuidade de R$ 1.090 está sendo compensada?",
    # carteira_ideal — MultiCard (T2.4 cluster-aware)
    "Monte a carteira ideal com até 3 cartões para maximizar cashback por categoria.",
    "Qual combinação de 2 cartões maximiza retorno para quem gasta muito em alimentação e viagem?",
    # prever_gastos — SpendPredictor (T3.2)
    "Quanto eu devo gastar no próximo mês por categoria? Quero planejar meu orçamento.",
    "Preveja meus gastos dos próximos 30 dias e diga em quais categorias devo me controlar.",
]

SUGESTOES_F3 = [
    # IMOVEL — financing + consortium + NPV + rental leverage
    "Quero comprar um apartamento de R$ 500 mil com R$ 80 mil de entrada. Financiamento ou consórcio?",
    "Se eu alugar o imóvel de R$ 500 mil por R$ 2.800/mês, muda a conta do financiamento?",
    # VEICULO — consortium probability + 36-84 meses
    "Financiar um carro de R$ 80 mil em 60 meses: qual a melhor estratégia?",
    "Vale mais entrar no consórcio de R$ 80 mil ou financiar direto? Qual a chance de contemplação?",
    # REFORMA — PRICE curto prazo
    "Vou reformar minha casa por R$ 45 mil. Financiamento bancário ou poupar/investir 12 meses?",
    # timing_scenarios — esperar vs comprar agora
    "Compro o imóvel agora ou espero 12, 24 ou 36 meses juntando mais entrada? Simule os cenários.",
    "Vale esperar 18 meses para comprar o carro de R$ 80 mil com R$ 1.500 poupados por mês?",
    # compound strategies — consórcio + SELIC + aluguel
    "Analise estratégias compostas para comprar imóvel de R$ 600 mil com renda de aluguel de R$ 3 mil.",
]

if not st.session_state["messages"]:
    col_f2, col_f3 = st.columns(2)
    with col_f2:
        st.markdown("**🃏 F2 — Optimizer de Cartões**")
        for i, sug in enumerate(SUGESTOES_F2):
            if st.button(sug, key=f"f2_{i}", use_container_width=True):
                st.session_state["prefill"] = sug
    with col_f3:
        st.markdown("**🏗️ F3 — Architect de Aquisições**")
        for i, sug in enumerate(SUGESTOES_F3):
            if st.button(sug, key=f"f3_{i}", use_container_width=True):
                st.session_state["prefill"] = sug

# ── Histórico de mensagens ─────────────────────────────────────────

for msg in st.session_state["messages"]:
    if msg["role"] == "user" and isinstance(msg["content"], str):
        with st.chat_message("user"):
            st.write(msg["content"])
    elif msg["role"] == "assistant":
        content = msg["content"]
        if isinstance(content, list):
            text = next((b.text for b in content if hasattr(b, "text")), None)
            if text:
                with st.chat_message("assistant"):
                    st.write(text)
        elif isinstance(content, str):
            with st.chat_message("assistant"):
                st.write(content)

# ── Input ─────────────────────────────────────────────────────────

prefill = st.session_state.pop("prefill", "")
user_input = st.chat_input("Pergunte sobre seus cartões, financiamento, consórcio, gastos...")
text = user_input or prefill

if text:
    # Mostra mensagem do usuário
    with st.chat_message("user"):
        st.write(text)

    # Adiciona ao histórico como string simples
    st.session_state["messages"].append({"role": "user", "content": text})

    # Converte histórico para formato anthropic (apenas user/assistant alternados)
    api_messages = []
    for m in st.session_state["messages"]:
        role = m["role"]
        content = m["content"]
        if isinstance(content, str):
            api_messages.append({"role": role, "content": content})
        elif role == "assistant" and isinstance(content, list):
            # Blocos do assistente (podem ter tool_use)
            api_messages.append({"role": role, "content": content})

    # Executa o agentic loop
    with st.chat_message("assistant"):
        tool_log = st.empty()
        with st.spinner("Nexa pensando..."):
            answer, updated_messages = run_agent(
                api_messages,
                monthly_income, monthly_spend, safe_to_spend,
                current_card, perfil_tipo,
                tool_log,
            )
        tool_log.empty()
        st.write(answer)

    # Salva resposta final no histórico (como string para renderização simples)
    st.session_state["messages"].append({"role": "assistant", "content": answer})
