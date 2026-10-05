# app/agent/tools/get_user_profile_context.py
"""
Tool: get_user_profile_context
Retorna o perfil comportamental completo do usuário via ConsumptionProfiler:
cluster de estilo de vida, FSS, eventos de vida e sinais detectados.

Resultado cacheado por 30 min por user_id para não rodar os 12 detectores
em cada mensagem do chat.
"""

import logging
from app.agent.procedencia import com_procedencia, degradada
from langchain_core.tools import tool
from app.core.formatacao import brl, numero

logger = logging.getLogger(__name__)

# Cache em memória simples: {user_id: (timestamp, resultado)}
# Complementado pelo Redis quando disponível (via get_redis).
_MEM_CACHE: dict[str, tuple[float, str]] = {}
_CACHE_TTL = 1800  # 30 min


def _get_cached(user_id: str) -> str | None:
    import time
    entry = _MEM_CACHE.get(user_id)
    if entry and (time.monotonic() - entry[0]) < _CACHE_TTL:
        return entry[1]
    return None


def _set_cached(user_id: str, value: str) -> None:
    import time
    _MEM_CACHE[user_id] = (time.monotonic(), value)


def _cluster_tone(cluster: str) -> str:
    tones = {
        "EXPLORADOR_GLOBAL":    "viajante frequente — priorize milhas, lounge e benefícios internacionais; aceita análise de ROI detalhada",
        "URBANO_FOODIE":        "apreciador gastronômico — destaque cashback em alimentação e restaurantes; linguagem descontraída",
        "INVESTIDOR_CAUTELOSO": "orientado a retorno — seja preciso em números, destaque custo de oportunidade e anuidade; evite termos vagos",
        "FAMILIA_ESTRUTURADA":  "perfil família — foque em segurança, educação e saúde financeira; linguagem acessível",
        "DIGITAL_NATIVO":       "usuário digital — linguagem direto ao ponto, destaque PIX, cashback e fintechs",
        "ESTRESSE_FINANCEIRO":  "em pressão financeira — seja empático, priorize cortes urgentes e evite sugestões de gasto",
        "MICROEMPREENDEDOR":    "MEI/autônomo — distinga fluxo PJ de PF, mencione DAS e separação de contas",
        "NAO_CLASSIFICADO":     "perfil neutro — use linguagem equilibrada e ofereça contexto antes de recomendar",
    }
    return tones.get(cluster, tones["NAO_CLASSIFICADO"])


def _pick_transactions_df(txns_raw: dict):
    """Seleciona o primeiro DataFrame Polars não vazio sem avaliar bool(df)."""
    import polars as pl

    for key in ("pf_pj_classified_df", "clean_df", "categorized_df"):
        value = txns_raw.get(key)
        if isinstance(value, pl.DataFrame) and not value.is_empty():
            return value
    return pl.DataFrame()


def _populate_fss(profile, transactions_df) -> None:
    """Popula FSS no mesmo formato usado pelo OptimizerService."""
    try:
        from app.optimizer.detectors.fss_calculator import FSSCalculator

        result = FSSCalculator().calc_fss(
            profile,
            transactions_df,
            resilience_score=int(getattr(profile, "resilience_score", 0) or 0),
        )
        profile.fss = result["fss"]
        profile.fss_level = result["fss_level"]
        profile.fss_signals = result.get("fss_signals", [])
        # `fss_confidence` era calculado pelo FSSCalculator e descartado aqui.
        # O FSS muda o tom de TODA resposta do agente e saía igual para 3 meses
        # de base e para 1 dia — o agente afirmava "você está em ALERTA" com a
        # mesma segurança nos dois casos.
        profile.fss_confidence = result.get("fss_confidence")
    except Exception as exc:
        logger.debug("[Tool] FSSCalculator indisponível para profile_context: %s", exc)


@tool
def get_user_profile_context(user_id: str) -> str:
    """
    Retorna o perfil comportamental completo do usuário: cluster de estilo de vida,
    nível de estresse financeiro (FSS), eventos de vida recentes e sinais detectados.

    CHAME ESTA FERRAMENTA na primeira mensagem de toda sessão e sempre que precisar
    personalizar uma recomendação. O resultado guia o tom e as prioridades de toda
    a conversa.

    Args:
        user_id: ID do usuário autenticado (obrigatório).
    """
    logger.info("[Tool] get_user_profile_context para %s", user_id)

    cached = _get_cached(user_id)
    if cached:
        logger.debug("[Tool] profile_context cache HIT para %s", user_id)
        return cached

    try:
        from app.runner import get_runner

        result = get_runner().run_from_db(user_id=user_id, horizon_days=30)
        if not result or result.get("status") != "success":
            return _no_data_response(user_id)

        txns_raw = result.get("transactions", {})
        transactions_df = _pick_transactions_df(txns_raw)

        if transactions_df.is_empty():
            return _no_data_response(user_id)

        from app.optimizer.profiler import ConsumptionProfiler
        profile = ConsumptionProfiler().build(transactions_df)
        _populate_fss(profile, transactions_df)

        text = com_procedencia(
            _format_profile(user_id, profile),
            fontes=["transactions_db", "consumption_profiler", "fss_calculator"],
            confianca=getattr(profile, "fss_confidence", None),
            cobertura_meses=_meses_de_extrato(transactions_df),
        )
        _set_cached(user_id, text)
        return text

    except Exception as exc:
        logger.error("[Tool] get_user_profile_context erro: %s", exc, exc_info=True)
        return degradada(
            "Não foi possível carregar o perfil comportamental agora. "
            "Prossiga com linguagem neutra e, se necessário, peça ao usuário "
            "que informe renda e principais categorias de gasto.",
            "perfil_indisponivel",
        )


def brief_do_perfil(user_id: str) -> str | None:
    """
    Versão compacta do perfil, para ir junto do system prompt.

    A "Regra Zero" (chamar `get_user_profile_context` antes de tudo) era uma
    instrução e nada mais: se o modelo pulasse a chamada — por economia, por
    uma pergunta que parecesse direta, ou porque o histórico foi aparado — a
    adaptação de tom por cluster simplesmente não acontecia. Para
    ESTRESSE_FINANCEIRO isso significa responder a quem está afundando com
    sugestão de produto novo, que é exatamente o que o prompt proíbe.

    O brief resolve o TOM de forma estrutural. A ferramenta continua existindo
    e valendo a pena: ela traz eventos de vida, comportamentos detectados,
    assinaturas e melhor dia de notificação, que não cabem aqui.

    Returns:
        Três a cinco linhas, ou None quando não há perfil (aí o agente segue
        com linguagem neutra, como já fazia).
    """
    try:
        texto = _get_cached(user_id) or get_user_profile_context.func(user_id)
    except Exception as exc:
        logger.warning("[Agent] brief do perfil indisponível para %s: %s", user_id, exc)
        return None

    if not texto or "Cluster:" not in texto:
        return None

    guardar = ("Cluster:", "Tom recomendado:", "Estresse Financeiro:",
               "Confiança do FSS:", "→ BASE CURTA:", "→ Priorize redução")
    linhas = [
        l.strip() for l in texto.splitlines()
        if any(l.strip().startswith(m) or m in l for m in guardar)
    ]
    return "\n".join(linhas) if linhas else None


def _meses_de_extrato(transactions_df) -> float:
    """Meses distintos presentes no extrato — a base do perfil."""
    import polars as pl

    coluna = next(
        (c for c in ("transaction_date", "date") if c in transactions_df.columns), None
    )
    if coluna is None:
        return 0.0
    try:
        return float(len(
            transactions_df.select(pl.col(coluna).cast(pl.Date).dt.strftime("%Y-%m"))
            .to_series().drop_nulls().unique()
        ))
    except Exception:
        return 0.0


def _no_data_response(user_id: str) -> str:
    return degradada(
        f"Perfil de {user_id}: sem transações conectadas ainda. "
        "Use linguagem neutra e instrua o usuário a conectar uma conta "
        "bancária via Open Finance para análise personalizada.",
        "sem_transacoes",
    )


def _format_profile(user_id: str, profile) -> str:
    lines = [f"=== PERFIL NEXA — {user_id} ==="]

    # Cluster e tom
    cluster = profile.lifestyle_cluster
    lines.append(f"Cluster: {cluster}")
    lines.append(f"Tom recomendado: {_cluster_tone(cluster)}")
    lines.append("")

    # FSS
    fss_emoji = {"SAUDAVEL": "✅", "ATENCAO": "⚠️", "ALERTA": "🔴", "CRITICO": "🆘"}.get(
        profile.fss_level, "⚠️"
    )
    lines.append(
        f"Estresse Financeiro: {fss_emoji} {profile.fss_level} "
        f"(FSS {profile.fss:.0f}/100)"
    )
    # O FSS muda o TOM de toda resposta. Com base curta ele continua sendo o
    # melhor palpite que temos, mas o agente não pode afirmá-lo como fato — e
    # até aqui saía igual para 3 meses de extrato e para 1 dia.
    fss_conf = getattr(profile, "fss_confidence", None)
    if fss_conf is not None:
        lines.append(f"  Confiança do FSS: {fss_conf:.0%}")
        if fss_conf < 0.5:
            lines.append(
                "  → BASE CURTA: trate o nível de estresse como indício, não como "
                "diagnóstico. Não abra a resposta por ele; se precisar mencionar, "
                "diga que há poucos meses de histórico."
            )
    if profile.fss_level in ("ALERTA", "CRITICO"):
        lines.append("  → Priorize redução de gastos e estabilidade antes de recomendar novos produtos.")
    elif profile.fss_level == "ATENCAO":
        lines.append("  → Mencione pontos de atenção com delicadeza; não alarme desnecessariamente.")
    fss_signals = getattr(profile, "fss_signals", [])
    if fss_signals:
        lines.append("  Sinais FSS: " + "; ".join(str(s) for s in fss_signals[:3]))
    lines.append("")

    # Sinais comportamentais
    signals = []
    if profile.travel_frequency_score > 0:
        travel_label = profile.travel_profile if hasattr(profile, "travel_profile") else "—"
        signals.append(
            f"Viajante {travel_label} "
            f"(score {profile.travel_frequency_score:.0f}/100, "
            f"{brl(profile.travel_spend_monthly, 0)}/mês em viagens)"
        )
    if profile.foodie_score > 0:
        foodie_label = profile.foodie_profile if hasattr(profile, "foodie_profile") else "—"
        signals.append(f"Foodie {foodie_label} (score {profile.foodie_score:.0f}/100)")
    if profile.investor_type != "NONE":
        signals.append(f"Investidor {profile.investor_type}")
    if profile.is_likely_mei:
        signals.append("MEI / Autônomo detectado")
    if profile.is_family_with_kids:
        signals.append("Família com filhos")
    if profile.is_digital_nomad:
        signals.append("Nômade digital")
    elif profile.is_airbnb_user:
        signals.append("Usa Airbnb com frequência")

    if signals:
        lines.append("Comportamentos detectados:")
        for s in signals:
            lines.append(f"  • {s}")
    else:
        lines.append("Comportamentos: perfil ainda sem sinais fortes.")
    lines.append("")

    # Finanças resumidas
    savings_pct = getattr(profile, "savings_rate", 0.0)
    committed_pct = getattr(profile, "committed_percentage", 0.0)
    lines.append(
        f"Finanças: gasto médio {brl(profile.monthly_avg_spend, 0)}/mês | "
        f"poupança {numero(savings_pct, 1)}% | "
        f"comprometimento {committed_pct * 100:.0f}%"
    )

    # Subscrições
    sub_burn = getattr(profile, "subscription_burn_monthly", 0.0)
    if sub_burn > 0:
        lines.append(f"Assinaturas: {brl(sub_burn, 0)}/mês em streaming/serviços")
    lines.append("")

    # Timing
    best_day = getattr(profile, "best_notification_day", None)
    if best_day:
        lines.append(f"Melhor dia para notificações: dia {best_day} do mês")
        lines.append("")

    return "\n".join(lines)
