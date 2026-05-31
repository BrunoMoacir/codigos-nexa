# app/agent/tools/get_expert_card_analysis.py
#
# Sub-agente especialista em cartões — Claude Opus 4.7
#
# Acionado quando o agente principal detecta:
#   - confidence_score do melhor cartão < 0.5
#   - data_coverage_months < 2 (histórico insuficiente)
#   - pergunta sobre cartão que não está na base de dados
#
# Capacidades extras:
#   - Web search (DuckDuckGo) para cartões desconhecidos ou novos no mercado
#   - Perfil completo do usuário como contexto (gastos, cluster, FSS, metas)
#   - Simulação detalhada de qualquer cartão pela base interna
#   - Raciocínio multi-etapa para estratégias complexas

from __future__ import annotations

import logging
from typing import Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ── Threshold de ativação ──────────────────────────────────────────────────────
_CONFIDENCE_THRESHOLD = 0.50   # abaixo disso → aciona especialista
_COVERAGE_THRESHOLD = 2        # meses mínimos de histórico


# ══════════════════════════════════════════════════════════════════════════════
# Ferramentas internas do sub-agente especialista
# ══════════════════════════════════════════════════════════════════════════════

def _make_expert_tools(user_id: str, monthly_income: Optional[float], monthly_spend: Optional[float]):
    """Cria as ferramentas específicas do sub-agente, com user_id fixo via closure."""

    from langchain_core.tools import tool as _tool

    @_tool
    def get_user_full_profile() -> str:
        """
        Retorna o perfil financeiro completo do usuário: cluster de estilo de vida,
        FSS, gastos por categoria, renda estimada, metas ativas, padrão de viagem,
        foodie score e cobertura de dados.
        Use esta ferramenta PRIMEIRO para entender quem é o usuário antes de recomendar.
        """
        try:
            import polars as pl
            from app.core.db.queries import get_transactions_for_user
            from app.optimizer.profiler import ConsumptionProfiler
            from app.goals.tracker import GoalTracker
            from app.core.db.session import get_db_session

            txns = get_transactions_for_user(user_id)
            profile = ConsumptionProfiler().build(txns) if not txns.is_empty() else None

            lines = [f"=== Perfil do usuário {user_id} ==="]

            if profile:
                lines += [
                    f"Cluster: {profile.lifestyle_cluster}",
                    f"Gasto mensal médio: R${profile.monthly_avg_spend:.0f}",
                    f"Renda estimada: R${profile.estimated_monthly_income:.0f}/mês",
                    f"Cobertura de dados: {profile.data_coverage_months} meses",
                    f"FSS: {profile.fss:.0f} ({profile.fss_level})",
                    f"Gasto de viagem: R${profile.travel_spend_monthly:.0f}/mês",
                    f"Gasto internacional: R${profile.international_spend_monthly:.0f}/mês",
                    f"Perfil viagem: {profile.travel_profile}",
                    f"Perfil foodie: {profile.foodie_profile}",
                    f"Taxa de poupança: {profile.savings_rate:.1f}%",
                    f"Tipo investidor: {profile.investor_type}",
                    f"É MEI: {profile.is_likely_mei}",
                    f"Família com filhos: {profile.is_family_with_kids}",
                    "Gastos por categoria (R$/mês):",
                ]
                for cat, val in sorted(profile.spend_by_category.items(), key=lambda x: -x[1])[:8]:
                    lines.append(f"  {cat}: R${val:.0f}")
            else:
                lines.append("Sem histórico de transações conectado.")
                if monthly_income:
                    lines.append(f"Renda declarada pelo usuário: R${monthly_income:.0f}/mês")
                if monthly_spend:
                    lines.append(f"Gasto declarado pelo usuário: R${monthly_spend:.0f}/mês")

            # Metas ativas
            try:
                with get_db_session() as db:
                    goals = GoalTracker(db).list_goals(user_id, status="ACTIVE")
                if goals:
                    lines.append(f"Metas ativas: {len(goals)}")
                    for g in goals[:3]:
                        pct = (g.current_amount / g.target_amount * 100) if g.target_amount > 0 else 0
                        lines.append(f"  - {g.name}: R${g.current_amount:.0f}/{g.target_amount:.0f} ({pct:.0f}%)")
            except Exception:
                pass

            return "\n".join(lines)

        except Exception as e:
            logger.warning("get_user_full_profile falhou: %s", e)
            return f"Não foi possível carregar o perfil completo: {e}"

    @_tool
    def list_cards_in_database(
        max_annuity: Optional[float] = None,
        min_annuity: Optional[float] = None,
        card_type: Optional[str] = None,
    ) -> str:
        """
        Lista os cartões disponíveis na base de conhecimento interna do Nexa.
        Use para verificar se um cartão específico está na base antes de pesquisar na internet.

        Args:
            max_annuity: filtro de anuidade máxima em R$ (ex: 500 para cartões até R$500/ano)
            min_annuity: filtro de anuidade mínima em R$ (ex: 400 para cartões premium)
            card_type: "CASHBACK", "POINTS" ou "INVESTBACK"
        """
        try:
            from app.optimizer.card_loader import CardKnowledgeBase
            cards = CardKnowledgeBase().load()

            filtered = cards
            if max_annuity is not None:
                filtered = [c for c in filtered if c.base_annuity <= max_annuity]
            if min_annuity is not None:
                filtered = [c for c in filtered if c.base_annuity >= min_annuity]
            if card_type:
                filtered = [c for c in filtered if c.card_type.value.upper() == card_type.upper()]

            lines = [f"Cartões na base ({len(filtered)} de {len(cards)}):"]
            for c in filtered:
                tags = ", ".join(t.value for t in c.benefit_tags[:3]) if c.benefit_tags else "-"
                lines.append(
                    f"  [{c.card_id}] {c.name} | {c.issuer} | "
                    f"anuidade=R${c.base_annuity:.0f} | tipo={c.card_type.value} | "
                    f"tags={tags}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Erro ao listar cartões: {e}"

    @_tool
    def simulate_card_for_user(
        card_id: str,
        monthly_spend_override: Optional[float] = None,
    ) -> str:
        """
        Simula o retorno financeiro de um cartão específico para este usuário.
        Retorna anuidade efetiva, ganho esperado, cenários pessimista/otimista e razões.

        Args:
            card_id: ID do cartão (use list_cards_in_database para encontrar o ID)
            monthly_spend_override: gasto mensal em R$ — usa perfil real se não informado
        """
        try:
            import polars as pl
            from app.core.db.queries import get_transactions_for_user
            from app.optimizer.profiler import ConsumptionProfiler
            from app.optimizer.card_loader import CardKnowledgeBase
            from app.optimizer.simulator import CardSimulator
            from dataclasses import replace as _replace

            kb = CardKnowledgeBase()
            kb.load()
            card = kb.get_by_id(card_id)
            if card is None:
                return f"Cartão '{card_id}' não encontrado na base. Use list_cards_in_database para ver os IDs disponíveis."

            txns = get_transactions_for_user(user_id)
            profile = ConsumptionProfiler().build(txns) if not txns.is_empty() else ConsumptionProfiler().build(pl.DataFrame())

            effective_spend = monthly_spend_override or monthly_spend or profile.monthly_avg_spend
            if effective_spend and effective_spend > profile.monthly_avg_spend:
                profile = _replace(profile, monthly_avg_spend=effective_spend)

            eff_income = monthly_income or (profile.income_profile.monthly_net_income if profile.income_profile else profile.estimated_monthly_income)
            safe = (eff_income * 0.30) if eff_income else None

            result = CardSimulator().simulate(card=card, profile=profile, safe_to_spend=safe)

            lines = [
                f"Simulação: {card.name} ({card.issuer})",
                f"  Anuidade efetiva: R${result.annuity_effective:.0f} (isenta: {result.annuity_waived})",
                f"  Benefícios esperados: R${result.points_value_expected:.0f}/ano",
                f"  Ganho líquido esperado: R${result.net_gain_expected:.0f}/ano",
                f"  Cenário pessimista: R${result.net_gain_min:.0f}/ano",
                f"  Cenário otimista: R${result.net_gain_max:.0f}/ano",
                f"  Risco de liquidez: {result.liquidity_risk.value}",
                f"  Confiança: {result.confidence_score:.0%}",
            ]
            if result.profile_match_reasons:
                lines.append("  Por que faz sentido:")
                for r in result.profile_match_reasons[:3]:
                    lines.append(f"    - {r}")
            return "\n".join(lines)

        except Exception as e:
            logger.warning("simulate_card_for_user falhou para %s: %s", card_id, e)
            return f"Erro ao simular {card_id}: {e}"

    @_tool
    def search_card_on_web(query: str) -> str:
        """
        Pesquisa informações sobre cartões de crédito na internet.
        Use quando o usuário perguntar sobre um cartão que não está na base interna,
        ou quando precisar de informações atualizadas sobre benefícios, promoções
        e comparativos de mercado.

        Args:
            query: consulta de busca (ex: "Nubank Ultravioleta beneficios 2025",
                   "melhor cartão de milhas para viagens internacionais Brasil 2025")
        """
        try:
            from duckduckgo_search import DDGS
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query + " cartão crédito Brasil", max_results=4, region="br-pt"):
                    results.append(f"**{r['title']}**\n{r['body']}\nFonte: {r['href']}")
            if not results:
                return "Nenhum resultado encontrado para essa busca."
            return "\n\n---\n".join(results)
        except Exception as e:
            logger.warning("search_card_on_web falhou: %s", e)
            return f"Web search indisponível: {e}. Responda com base no conhecimento interno."

    @_tool
    def get_opportunity_cost_for_user(current_card_id: str, months: int = 3) -> str:
        """
        Calcula quanto o usuário deixou de ganhar usando o cartão atual em vez
        dos melhores cartões disponíveis.

        Args:
            current_card_id: ID do cartão atual do usuário
            months: janela de análise em meses (padrão: 3)
        """
        try:
            import polars as pl
            from app.core.db.queries import get_transactions_for_user
            from app.optimizer.profiler import ConsumptionProfiler
            from app.optimizer.card_loader import CardKnowledgeBase
            from app.optimizer.opportunity_cost import OpportunityCostCalculator

            txns = get_transactions_for_user(user_id)
            if txns.is_empty():
                return "Sem histórico de transações para calcular custo de oportunidade."

            profile = ConsumptionProfiler().build(txns)
            kb = CardKnowledgeBase()
            all_cards = kb.load()
            current = next((c for c in all_cards if c.card_id == current_card_id), None)
            if current is None:
                return f"Cartão '{current_card_id}' não encontrado na base."

            candidates = [c for c in all_cards if c.card_id != current_card_id]
            report = OpportunityCostCalculator().calculate(
                profile=profile, current_card=current, candidate_cards=candidates, months=months
            )
            d = report.to_dict()
            best = d.get("best_opportunity", {})
            return (
                f"Cartão atual: {d.get('current_card_name')}\n"
                f"Total gasto no período: R${d.get('total_spent', 0):.0f}\n"
                f"Retorno gerado: R${d.get('current_card_reward_value', 0):.0f}\n"
                f"Melhor alternativa: {best.get('card_name', '-')}\n"
                f"Diferença: R${best.get('difference', 0):.0f} no período "
                f"(R${best.get('difference_annualized', 0):.0f}/ano)\n"
                f"Explicação: {best.get('explanation', '-')[:200]}"
            )
        except Exception as e:
            return f"Erro ao calcular custo de oportunidade: {e}"

    return [
        get_user_full_profile,
        list_cards_in_database,
        simulate_card_for_user,
        search_card_on_web,
        get_opportunity_cost_for_user,
    ]


# ══════════════════════════════════════════════════════════════════════════════
# Ferramenta principal — chamada pelo agente principal
# ══════════════════════════════════════════════════════════════════════════════

@tool
def get_expert_card_analysis(
    user_id: str,
    question: str,
    monthly_income: Optional[float] = None,
    monthly_spend: Optional[float] = None,
    original_confidence: Optional[float] = None,
    original_coverage_months: Optional[int] = None,
) -> str:
    """
    Sub-agente especialista em cartões de crédito, powered by Claude Opus 4.7.

    USE ESTA FERRAMENTA quando get_card_optimization retornar:
    - confidence_score do melhor cartão < 0.5 (dados insuficientes)
    - data_coverage_months < 2 (histórico muito curto)
    - Pergunta sobre cartão específico não encontrado na base interna
    - Perguntas estratégicas complexas: "devo trocar meu cartão?",
      "vale a pena ter dois cartões?", "qual estratégia de milhas?"

    O especialista pode pesquisar na internet cartões não cadastrados,
    simular cartões específicos e analisar o perfil completo do usuário.

    Args:
        user_id: ID do usuário autenticado.
        question: Pergunta original do usuário, com todo o contexto.
        monthly_income: Renda mensal declarada (R$), se informada.
        monthly_spend: Gasto mensal declarado (R$), se informado.
        original_confidence: confidence_score retornado por get_card_optimization (0-1).
        original_coverage_months: data_coverage_months do perfil.
    """
    logger.info(
        "[ExpertCard] Acionando para user=%s | conf=%.2f | coverage=%s meses",
        user_id,
        original_confidence or 0,
        original_coverage_months or "?",
    )

    try:
        from app.core.config import settings
        from langchain_anthropic import ChatAnthropic
        from langgraph.prebuilt import create_react_agent

        # Usa Opus 4.7 — mais capaz para raciocínio multi-etapa
        model_id = "claude-opus-4-7"
        if not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY == "mock":
            return (
                "Sub-agente especialista requer ANTHROPIC_API_KEY configurada. "
                "Configure no backend/.env e tente novamente."
            )

        llm = ChatAnthropic(
            model=model_id,
            temperature=0.0,
            api_key=settings.ANTHROPIC_API_KEY,
            max_tokens=4096,
        )

        expert_tools = _make_expert_tools(user_id, monthly_income, monthly_spend)

        context_note = []
        if original_confidence is not None:
            context_note.append(f"confiança da análise padrão: {original_confidence:.0%}")
        if original_coverage_months is not None:
            context_note.append(f"cobertura de dados: {original_coverage_months} meses")

        system_prompt = f"""Você é um especialista sênior em cartões de crédito brasileiro, \
chamado para aprofundar uma análise que teve {'baixa confiança ou dados insuficientes' if original_confidence and original_confidence < _CONFIDENCE_THRESHOLD else 'uma questão complexa'}.

{'Contexto: ' + ', '.join(context_note) + '.' if context_note else ''}

## FLUXO OBRIGATÓRIO:
1. Chame `get_user_full_profile` PRIMEIRO para entender o perfil completo.
2. Chame `list_cards_in_database` para ver o que está disponível internamente.
3. Se o usuário perguntou sobre um cartão específico que NÃO está na base,
   chame `search_card_on_web` para pesquisar informações atualizadas.
4. Simule os 2-3 cartões mais relevantes com `simulate_card_for_user`.
5. Se o usuário tem cartão atual, use `get_opportunity_cost_for_user`.

## REGRAS:
- Seja objetivo: apresente números reais (R$/ano de ganho líquido).
- Explique o raciocínio: "Para o seu perfil X com gastos Y, o cartão Z gera R$W/ano porque..."
- Se pesquisar na internet, cite a fonte e diferencie do que está confirmado na base interna.
- Responda SEMPRE em português brasileiro.
- Termine com uma recomendação clara e um próximo passo acionável.
"""

        agent = create_react_agent(llm, tools=expert_tools, prompt=system_prompt)

        inputs = {"messages": [{"role": "user", "content": f"[user_id={user_id}] {question}"}]}
        result = agent.invoke(inputs, config={"configurable": {"thread_id": f"expert_{user_id}"}})

        messages = result.get("messages", [])
        if not messages:
            return "Sub-agente especialista não retornou resposta."

        final = messages[-1].content
        logger.info("[ExpertCard] Análise concluída para user=%s (%d chars)", user_id, len(final))
        return final

    except Exception as e:
        logger.error("[ExpertCard] Erro: %s", e, exc_info=True)
        return (
            f"O sub-agente especialista encontrou um erro: {type(e).__name__}: {str(e)[:200]}. "
            "Use get_card_optimization como fallback."
        )
