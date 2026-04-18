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

@st.cache_resource
def get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        try:
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).parent.parent / ".env")
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        except Exception:
            pass
    return anthropic.Anthropic(api_key=api_key)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FAKE DATA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@st.cache_data
def build_transactions(monthly_income: float, monthly_spend: float) -> pl.DataFrame:
    today = date.today()
    rows = []
    tx_id = 1
    categories = {
        "Alimentacao": 0.25, "Transporte": 0.15, "Saude": 0.10,
        "Lazer": 0.12, "Moradia": 0.20, "Educacao": 0.08, "Outros": 0.10,
    }
    desc_map = {
        "Alimentacao": ["iFood Pedido", "Supermercado Extra", "Padaria Central"],
        "Transporte":  ["Uber Trip", "Combustível Shell", "99 Corrida"],
        "Saude":       ["Farmácia Drogasil", "Consulta Médica", "Academia Smart"],
        "Lazer":       ["Netflix", "Cinema Cinemark", "Bar e Restaurante"],
        "Moradia":     ["Aluguel Imobiliária", "Condomínio", "Luz Enel"],
        "Educacao":    ["Coursera", "Livros Amazon", "Escola de Idiomas"],
        "Outros":      ["Amazon Compras", "Magazine Luiza", "Loja X"],
    }
    for m in range(3):
        base = today - timedelta(days=30 * (m + 1))
        rows.append({
            "transaction_id": f"TX{tx_id:04d}", "user_id": "user_teste",
            "account_id": "acc_001", "description": "Salário Empresa ABC",
            "amount": monthly_income, "date": base + timedelta(days=5),
            "transaction_type": "CREDIT", "category": "Renda",
            "is_recurring": True, "is_installment": False,
            "context_type": None, "context_confidence": 0.9,
            "context_override_by_user": False, "pj_subcategory": None,
        })
        tx_id += 1
        for cat, pct in categories.items():
            cat_total = monthly_spend * pct
            n = max(1, int(cat_total / 150))
            per = cat_total / n
            for i in range(n):
                rows.append({
                    "transaction_id": f"TX{tx_id:04d}", "user_id": "user_teste",
                    "account_id": "acc_001",
                    "description": desc_map[cat][i % 3],
                    "amount": -round(per, 2),
                    "date": base + timedelta(days=2 + i * max(1, 28 // n)),
                    "transaction_type": "DEBIT" if cat in ("Moradia", "Educacao") else "CREDIT",
                    "category": cat, "is_recurring": cat == "Moradia",
                    "is_installment": False, "context_type": None,
                    "context_confidence": 0.85, "context_override_by_user": False,
                    "pj_subcategory": None,
                })
                tx_id += 1
        # gasto internacional mensal
        rows.append({
            "transaction_id": f"TX{tx_id:04d}", "user_id": "user_teste",
            "account_id": "acc_001", "description": "Amazon USD Internacional",
            "amount": -320.0, "date": base + timedelta(days=15),
            "transaction_type": "CREDIT", "category": "Outros",
            "is_recurring": False, "is_installment": False,
            "context_type": None, "context_confidence": 0.8,
            "context_override_by_user": False, "pj_subcategory": None,
        })
        tx_id += 1
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

def tool_perfil_consumo(monthly_income: float, monthly_spend: float, safe_to_spend: float) -> dict:
    from app.optimizer.profiler import ConsumptionProfiler
    df = build_transactions(monthly_income, monthly_spend)
    profiler = ConsumptionProfiler()
    p = profiler.build(df, safe_to_spend=safe_to_spend)
    return {
        "gasto_medio_mensal": p.monthly_avg_spend,
        "renda_estimada_mensal": p.estimated_monthly_income,
        "cobertura_meses": p.data_coverage_months,
        "estabilidade_gasto": round(p.spending_stability, 2),
        "gasto_internacional_mensal": p.international_spend_monthly,
        "gasto_viagem_mensal": p.travel_spend_monthly,
        "comprometido_pct": round(p.committed_percentage, 2),
        "gasto_por_categoria": p.spend_by_category,
        "income_profile": {
            "padrao": p.income_profile.income_pattern if p.income_profile else None,
            "renda_liquida": p.income_profile.monthly_net_income if p.income_profile else None,
            "confianca": round(p.income_profile.confidence, 2) if p.income_profile else None,
        },
    }


def tool_otimizar_cartao(
    monthly_income: float, monthly_spend: float, safe_to_spend: float,
    current_cards: list[str],
) -> dict:
    from app.optimizer.models import OptimizationRequest
    df = build_transactions(monthly_income, monthly_spend)
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
    card_id: str, monthly_income: float, monthly_spend: float, safe_to_spend: float,
) -> dict:
    from app.optimizer.profiler import ConsumptionProfiler
    from app.optimizer.simulator import CardSimulator
    df = build_transactions(monthly_income, monthly_spend)
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
) -> dict:
    from app.optimizer.multi_card_strategy import MultiCardStrategy
    from app.optimizer.profiler import ConsumptionProfiler
    df = build_transactions(monthly_income, monthly_spend)
    profiler = ConsumptionProfiler()
    profile = profiler.build(df, safe_to_spend=safe_to_spend)
    kb = get_card_kb()
    eligible = kb.filter_eligible(
        annual_income=monthly_income * 12,
        current_card_ids=[],
        exclude_consigned=True,
    )
    strategy = MultiCardStrategy(knowledge_base=kb)
    result = strategy.compute(
        profile=profile,
        eligible_cards=eligible,
        max_cards=max_cards,
        safe_to_spend=safe_to_spend,
    )
    wallet = []
    for ca in result.wallet:
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
        "ganho_vs_cartao_unico": round(result.gain_vs_single_card, 2),
        "quantidade_cartoes": len(result.wallet),
        "carteira": wallet,
    }


def tool_simular_aquisicao(
    valor: float, entrada: float, tipo: str, prazo_meses: int,
    perfil_risco: str, safe_to_spend: float, incluir_consorcio: bool,
    renda_aluguel: float | None,
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
    from app.architect.simulators.timing_simulator import TimingSimulator
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
    timing = TimingSimulator(architect_service=svc)
    scenarios = timing.compute(
        base_request=req,
        safe_to_spend=safe_to_spend,
        monthly_savings=poupanca_mensal,
        wait_months_list=sorted(cenarios_espera),
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
            "Analisa as transações do usuário e retorna seu perfil de consumo: "
            "gasto médio mensal, renda estimada, estabilidade, gastos por categoria, "
            "gastos internacionais e % comprometido com parcelas."
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
                        "Valores válidos: nubank-ultravioleta, nubank-roxinho, itau-personnalite, "
                        "c6-carbon, xp-visa-infinite, inter-black, picpay-card, next-visa"
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
                    "enum": ["IMOVEL", "VEICULO", "REFORMA", "OUTRO"],
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

def execute_tool(name: str, inputs: dict, monthly_income: float, monthly_spend: float, safe_to_spend: float) -> dict:
    try:
        if name == "perfil_consumo":
            return tool_perfil_consumo(monthly_income, monthly_spend, safe_to_spend)
        if name == "otimizar_cartao":
            return tool_otimizar_cartao(
                monthly_income, monthly_spend, safe_to_spend,
                current_cards=inputs.get("cartoes_atuais", []),
            )
        if name == "roi_cartao_atual":
            return tool_roi_cartao_atual(
                card_id=inputs["card_id"],
                monthly_income=monthly_income, monthly_spend=monthly_spend,
                safe_to_spend=safe_to_spend,
            )
        if name == "carteira_ideal":
            return tool_carteira_ideal(
                monthly_income, monthly_spend, safe_to_spend,
                max_cards=inputs.get("max_cartoes", 2),
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

## Instruções
- Responda SEMPRE em português brasileiro, de forma clara e direta.
- Use as ferramentas disponíveis para buscar dados reais antes de responder sobre finanças.
- Nunca invente números — execute a ferramenta e use os dados retornados.
- Seja objetivo: destaque o que é mais importante para o usuário tomar uma decisão.
- Use valores em R$ com formatação brasileira (ex: R$ 1.200,00).
- Quando mostrar comparações (ex: financiamento vs consórcio), use os NPVs retornados pela ferramenta.
- Cartões disponíveis na base: nubank-ultravioleta, nubank-roxinho, itau-personnalite, c6-carbon, xp-visa-infinite, inter-black, picpay-card, next-visa.
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AGENTIC LOOP — tool use com claude-haiku
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_agent(
    messages: list[dict],
    monthly_income: float, monthly_spend: float, safe_to_spend: float,
    current_card: str,
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

PERFIS = {
    "💼 Profissional Premium (R$ 15k)": {"income": 15_000, "spend": 8_500, "safe": 6_500},
    "🏠 Classe Média (R$ 8.5k)":        {"income":  8_500, "spend": 5_200, "safe": 3_300},
    "🎓 Jovem Profissional (R$ 5k)":    {"income":  5_000, "spend": 3_200, "safe": 1_800},
    "🚀 Executivo Alto (R$ 25k)":       {"income": 25_000, "spend": 14_000, "safe": 11_000},
}

with st.sidebar:
    st.header("⚙️ Perfil de Teste")
    perfil_nome = st.selectbox("Perfil base", list(PERFIS.keys()))
    p = PERFIS[perfil_nome]
    monthly_income = st.number_input("Renda mensal (R$)", value=p["income"], step=500)
    monthly_spend  = st.number_input("Gasto mensal (R$)", value=p["spend"],  step=200)
    safe_to_spend  = st.number_input("Safe-to-spend (R$)", value=p["safe"],  step=200)
    current_card   = st.selectbox(
        "Cartão atual",
        ["(nenhum)", "nubank-roxinho", "inter-black", "picpay-card", "next-visa", "nubank-ultravioleta"],
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

SUGESTOES = [
    "Qual cartão devo pedir com minha renda?",
    "Vale a pena manter o nubank-roxinho ou devo trocar?",
    "Me mostre a carteira ideal com 2 cartões.",
    "Quero comprar um apartamento de R$ 500 mil. Qual a melhor estratégia?",
    "Financiar um carro de R$ 80 mil: financiamento ou consórcio?",
    "Compro o imóvel agora ou espero mais 2 anos poupando?",
    "Como estão meus gastos por categoria?",
    "Se eu alugar o imóvel, compensa mais financiar ou entrar no consórcio?",
]

if not st.session_state["messages"]:
    st.write("**Perguntas para começar:**")
    cols = st.columns(2)
    for i, sug in enumerate(SUGESTOES):
        if cols[i % 2].button(sug, key=f"sug_{i}", use_container_width=True):
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
                monthly_income, monthly_spend, safe_to_spend, current_card,
                tool_log,
            )
        tool_log.empty()
        st.write(answer)

    # Salva resposta final no histórico (como string para renderização simples)
    st.session_state["messages"].append({"role": "assistant", "content": answer})
