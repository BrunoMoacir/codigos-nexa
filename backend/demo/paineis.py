"""
demo/paineis.py — Os números estruturados que a prosa das ferramentas não dá.

As 31 ferramentas do agente devolvem texto (é o que o LLM consome). Para
desenhar gráfico, barra de categoria e KPI o app precisa dos números, e é isso
que este módulo entrega — sempre chamando os MESMOS serviços de produção que a
ferramenta correspondente chama por dentro.

  panorama(uid)      → forecast, safe-to-spend, health score, cluster (doc 02/13)
  extrato(uid)       → KPIs, série mensal, categorias, PF/PJ, lançamentos (doc 01/05)
  compromissos(uid)  → shadow invoices: o que já está comprometido (doc 01)
  ritmo(uid)         → burn rate e categorias fora do ritmo (doc 02)
  pipeline(uid)      → os 8 estágios do ETL com os números reais desta conta (doc 01)
  conta(uid)         → plano, limites de uso e inventário LGPD (docs 16/17)
  plataforma()       → os 9 robôs agendados e o checkpointer em uso (docs 15/18)

Toda função devolve `{"ok": bool, ...}` e nunca levanta: uma tela do app pode
mostrar um painel vazio com o motivo, não pode cair.
"""

from __future__ import annotations

import logging
from datetime import date

import polars as pl

logger = logging.getLogger("demo.paineis")

_CORES = ("#D4A820", "#2EC8A4", "#60B0F2", "#F07A64", "#ECB040",
          "#B088E0", "#7FD1AE", "#E8846B")


def _protegido(fn):
    """Painel que falha vira painel com motivo, nunca exceção na tela."""
    def _wrap(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            logger.warning("painel %s: %s", fn.__name__, exc)
            return {"ok": False, "erro": f"{type(exc).__name__}: {exc}"}
    _wrap.__name__ = fn.__name__
    _wrap.__doc__ = fn.__doc__
    return _wrap


# ══════════════════════════════════════════════════════════════════════
# Panorama e feed — reaproveitam os serviços já existentes do demo
# ══════════════════════════════════════════════════════════════════════

@_protegido
def panorama(user_id: str) -> dict:
    """Pipeline real + health score + cluster (o mesmo do Dashboard)."""
    from demo.services import dashboard_data

    return dashboard_data(user_id)


@_protegido
def feed_proativo(user_id: str, renda: float = 0.0) -> dict:
    """
    Cards do `ProactiveNotifier` + `NotificationRelevanceFilter` reais.

    O filtro de relevância é o que decide o que merece interromper o usuário —
    rodá-lo aqui é a diferença entre um feed e um despejo de detectores.
    """
    from demo.services import build_feed

    return {"ok": True, "cards": build_feed(user_id, renda)}


# ══════════════════════════════════════════════════════════════════════
# Extrato — o que a aba Organizar mostra
# ══════════════════════════════════════════════════════════════════════

def _normalizar(df: pl.DataFrame) -> pl.DataFrame:
    """
    Garante `transaction_date` a partir de `date`.

    A deriva entre os dois nomes é a mesma que zerava a renda no ETL e fixava
    `analysis_months = 1` no Raio-X. Normalizar uma vez, na entrada.
    """
    if "transaction_date" not in df.columns and "date" in df.columns:
        return df.with_columns(pl.col("date").cast(pl.Datetime).alias("transaction_date"))
    return df


@_protegido
def extrato(user_id: str, ultimos: int = 12) -> dict:
    """KPIs, série mensal, categorias, PF/PJ e lançamentos recentes."""
    from app.core.db.queries import get_transactions_for_user

    df = get_transactions_for_user(user_id)
    if df.is_empty():
        return {"ok": False, "erro": "Sem transações. Rode `python3 -m demo.seed`."}

    df = _normalizar(df)
    entradas = float(df.filter(pl.col("amount") > 0)["amount"].sum() or 0)
    saidas = float(abs(df.filter(pl.col("amount") < 0)["amount"].sum() or 0))
    saldo = entradas - saidas

    mensal = (
        df.filter(pl.col("amount") < 0)
        .with_columns(
            pl.col("transaction_date").dt.strftime("%Y-%m").alias("mes"),
            pl.col("amount").abs().alias("gasto"),
        )
        .group_by("mes").agg(pl.col("gasto").sum().alias("total"))
        .sort("mes").tail(ultimos)
    )

    categorias = []
    if "category" in df.columns:
        agrupado = (
            df.filter(pl.col("amount") < 0)
            .with_columns(pl.col("amount").abs().alias("gasto"))
            .group_by("category")
            .agg(pl.col("gasto").sum().alias("total"), pl.len().alias("n"))
            .sort("total", descending=True).head(8)
        )
        maior = float(agrupado["total"].max() or 1)
        for i, linha in enumerate(agrupado.iter_rows(named=True)):
            categorias.append({
                "categoria": linha["category"] or "Outros",
                "total": float(linha["total"]),
                "n": int(linha["n"]),
                "pct_do_maior": float(linha["total"]) / maior * 100,
                "pct_do_gasto": (float(linha["total"]) / saidas * 100) if saidas else 0.0,
                "cor": _CORES[i % len(_CORES)],
            })

    pf_pj = {}
    if "context_type" in df.columns:
        partes = (
            df.filter(pl.col("amount") < 0)
            .with_columns(pl.col("amount").abs().alias("gasto"))
            .group_by("context_type").agg(pl.col("gasto").sum().alias("total"))
        )
        pf_pj = {(linha["context_type"] or "UNCERTAIN"): float(linha["total"])
                 for linha in partes.iter_rows(named=True)}

    recentes = (
        df.sort("transaction_date", descending=True).head(20)
        .select([c for c in ("transaction_date", "description", "amount", "category",
                             "context_type", "is_recurring") if c in df.columns])
    )

    return {
        "ok": True,
        "n_transacoes": len(df),
        "entradas": entradas,
        "saidas": saidas,
        "saldo": saldo,
        "taxa_poupanca": (saldo / entradas * 100) if entradas else 0.0,
        "meses": mensal["mes"].to_list(),
        "gasto_mensal": [float(v) for v in mensal["total"].to_list()],
        "categorias": categorias,
        "pf_pj": pf_pj,
        "recentes": recentes.to_dicts(),
    }


@_protegido
def compromissos(user_id: str) -> dict:
    """
    Shadow invoices — o que o saldo da conta não mostra.

    É a peça que faz a projeção de caixa ser event-driven: o extrato só conta o
    passado, e parcela e assinatura comprometem o futuro.
    """
    from app.runner import get_runner

    resultado = get_runner("dev").run_from_db(user_id)
    eventos = (resultado or {}).get("projections", {}).get("shadow_events")
    if eventos is None or eventos.is_empty():
        return {"ok": True, "eventos": [], "total_mensal": 0.0}

    itens = []
    for linha in eventos.iter_rows(named=True):
        meta = linha.get("metadata") or {}
        if not isinstance(meta, dict):
            meta = {}
        itens.append({
            "tipo": linha.get("type"),
            "valor": abs(float(linha.get("amount") or 0)),
            "vencimento": linha.get("next_due_date"),
            "descricao": next((v for v in meta.values() if isinstance(v, str)), "—"),
            "confianca": float(linha.get("confidence") or 0),
        })
    itens.sort(key=lambda i: i["valor"], reverse=True)
    return {"ok": True, "eventos": itens,
            "total_mensal": sum(i["valor"] for i in itens)}


@_protegido
def ritmo(user_id: str) -> dict:
    """Burn rate: o ritmo de gasto do mês contra o ritmo esperado."""
    from app.runner import get_runner

    resultado = get_runner("dev").run_from_db(user_id)
    relatorio = (resultado or {}).get("analysis", {}).get("burn_rate")
    if relatorio is None:
        return {"ok": False, "erro": "Sem burn rate (precisa de ~3 meses de base)."}

    dados = relatorio.to_dict() if hasattr(relatorio, "to_dict") else dict(relatorio)
    return {"ok": True, **dados}


# ══════════════════════════════════════════════════════════════════════
# Pipeline ETL — os 8 estágios com os números desta conta
# ══════════════════════════════════════════════════════════════════════

_ESTAGIOS = (
    ("1 · Ingestor", "Normalização em Polars + estratégia por banco + dedup SHA-256"),
    ("2 · Classificador", "Categoria por regex; confiança derivada da cobertura do match"),
    ("3 · Recorrência", "Assinaturas (5 critérios obrigatórios) e parcelas"),
    ("4 · PF/PJ", "Regras determinísticas + overrides do usuário"),
    ("5 · Shadow invoices", "O compromisso futuro que o extrato não mostra"),
    ("6 · Qualidade", "Confiança 0–1 = 30% cobertura + 25% completude + 25% saldo + 20% anomalias"),
    ("7 · Perfil", "Renda real (não soma de créditos) e perfil comportamental"),
    ("8 · Persistência", "transactions_clean com ON CONFLICT(dedup_hash) DO NOTHING"),
)


@_protegido
def pipeline(user_id: str) -> dict:
    """O ETL de 8 estágios, com o que cada um produziu para esta conta."""
    from app.runner import get_runner

    resultado = get_runner("dev").run_from_db(user_id) or {}
    tx = resultado.get("transactions", {})
    projecoes = resultado.get("projections", {})
    analise = resultado.get("analysis", {})

    df = tx.get("pf_pj_classified_df")
    reparticao = {}
    recorrentes = parceladas = 0
    if df is not None and not df.is_empty():
        if "context_type" in df.columns:
            reparticao = dict(
                df.group_by("context_type").agg(pl.len().alias("n"))
                .iter_rows()
            )
        if "is_recurring" in df.columns:
            recorrentes = int(df.filter(pl.col("is_recurring")).height)
        if "is_installment" in df.columns:
            parceladas = int(df.filter(pl.col("is_installment")).height)

    categorias = 0
    if df is not None and not df.is_empty() and "category" in df.columns:
        categorias = int(df["category"].n_unique())

    qualidade = _qualidade(df)

    eventos = projecoes.get("shadow_events")
    renda = analise.get("income_profile")

    medidas = {
        "1 · Ingestor": f"{tx.get('raw_count', 0)} recebidas · "
                        f"{tx.get('valid_count', 0)} válidas · "
                        f"{tx.get('rejected_count', 0)} rejeitadas",
        "2 · Classificador": f"{categorias} categorias distintas",
        "3 · Recorrência": f"{recorrentes} recorrentes · {parceladas} parceladas",
        "4 · PF/PJ": " · ".join(f"{k}={v}" for k, v in sorted(reparticao.items())) or "—",
        "5 · Shadow invoices": f"{0 if eventos is None else len(eventos)} compromissos futuros",
        "6 · Qualidade": qualidade["resumo"],
        "7 · Perfil": (f"renda R$ {getattr(renda, 'monthly_net_income', 0):,.0f}/mês · "
                       f"confiança {getattr(renda, 'confidence', 0):.0%}"
                       if renda else "sem perfil de renda"),
        "8 · Persistência": f"{tx.get('valid_count', 0)} linhas em transactions_clean",
    }
    return {
        "ok": resultado.get("status") == "success",
        "qualidade": qualidade,
        "estagios": [{"nome": n, "o_que_faz": d, "nesta_conta": medidas.get(n, "—")}
                     for n, d in _ESTAGIOS],
    }


def _qualidade(df: pl.DataFrame | None) -> dict:
    """
    Estágio 6 rodado de verdade, não repetido de cor.

    `overall_confidence` é a média ponderada 30/25/25/20 descrita no doc 01. O
    painel mostra os quatro fatores separados porque é o que diz ONDE a base
    está fraca — um score agregado de 0,72 não distingue "faltam dias" de
    "faltam campos".
    """
    if df is None or df.is_empty():
        return {"resumo": "sem dados para validar", "fatores": []}
    from app.forecast.etl.data_quality import validate_data_quality

    laudo = validate_data_quality(_normalizar(df), period_days=180)
    confianca = getattr(laudo, "overall_confidence", None)
    return {
        "resumo": (f"{getattr(laudo, 'quality_level', '—')}"
                   + (f" · confiança {confianca:.0%}" if confianca is not None else "")),
        "nivel": getattr(laudo, "quality_level", None),
        "confianca": confianca,
        "fatores": [
            {"fator": "Cobertura temporal (30%)", "valor": getattr(laudo, "temporal_coverage", None)},
            {"fator": "Completude (25%)", "valor": getattr(laudo, "completeness_score", None)},
            {"fator": "Consistência de saldo (25%)", "valor": getattr(laudo, "balance_consistency", None)},
        ],
        "lacunas": getattr(laudo, "gap_count", 0),
        "anomalias": getattr(laudo, "anomaly_count", 0),
        "recomendacoes": list(getattr(laudo, "recommendations", []) or []),
    }


# ══════════════════════════════════════════════════════════════════════
# Conta — plano, limites e LGPD
# ══════════════════════════════════════════════════════════════════════

@_protegido
def conta(user_id: str) -> dict:
    """Plano efetivo, o que cada plano libera, limites de uso e inventário LGPD."""
    from app.billing.plans import FREE_LIMITS, PLANS, PRO_LIMITS, plan_satisfies
    from app.billing.service import BillingService

    try:
        plano = BillingService().get_effective_plan(user_id)
    except Exception:
        plano = "free"

    limites = []
    for chave, limite in {**FREE_LIMITS}.items():
        do_plano = PRO_LIMITS.get(chave) if plano != "free" else limite
        if plano == "total":
            texto = "ilimitado"
        elif do_plano is None:
            texto = "ilimitado"
        else:
            texto = f"{do_plano.limit}/{'dia' if do_plano.window == 'daily' else 'mês'}"
        limites.append({"contador": chave, "no_seu_plano": texto,
                        "descricao": limite.description})

    inventario = []
    try:
        from app.privacy.service import inventario_de_dados

        inventario = [{"tabela": t, "o_que_guarda": d} for t, d in inventario_de_dados()]
    except Exception as exc:
        logger.warning("inventário LGPD: %s", exc)

    return {
        "ok": True,
        "plano": plano,
        "planos": [{
            "id": p.plan_id, "nome": p.name, "preco": p.price_brl_monthly,
            "chamada": p.tagline, "inclui": list(p.features),
            "e_o_seu": p.plan_id == plano,
            "ja_liberado": plan_satisfies(plano, p.plan_id),
        } for p in PLANS.values()],
        "limites": limites,
        "inventario_lgpd": inventario,
    }


# ══════════════════════════════════════════════════════════════════════
# Plataforma — o que roda sem o usuário abrir o app
# ══════════════════════════════════════════════════════════════════════

_ROBOS = (
    ("02h00", "fee_snapshot", "Fotografa as tarifas pagas → histórico + baseline anônimo"),
    ("02h15", "market_fees_refresh", "Tarifas publicadas no Open Finance"),
    ("02h30", "product_catalog_refresh", "Catálogo vivo de renda fixa do mercado"),
    ("03h00", "opportunity_scan", "Dinheiro parado e poupança abaixo do CDI"),
    ("04h00", "health_score_snapshot", "Série temporal do score"),
    ("05h30", "intelligence_metrics", "Calibração do Negociador e acurácia"),
    ("*/6h", "notification_scheduler", "Gera e entrega as notificações do feed"),
    ("07h00", "daily_digest", "E-mail diário idempotente"),
    ("seg 03h30", "cards_curation_audit", "Lista os cartões com curadoria vencida"),
)


@_protegido
def plataforma() -> dict:
    """Os robôs agendados, a memória do agente e o provedor de LLM."""
    from app.agent.graph import checkpointer_em_uso
    from app.core.config import settings

    qual, motivo = checkpointer_em_uso()
    tem_chave = bool(settings.ANTHROPIC_API_KEY or settings.OPENAI_API_KEY)
    return {
        "ok": True,
        "robos": [{"quando": q, "job": j, "entrega": e} for q, j, e in _ROBOS],
        "checkpointer": qual,
        "checkpointer_motivo": motivo,
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
        "llm_configurado": tem_chave,
        "hoje": date.today().isoformat(),
    }
