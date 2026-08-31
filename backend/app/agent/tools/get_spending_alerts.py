# app/agent/tools/get_spending_alerts.py
"""
Tool: get_spending_alerts
Retorna alertas financeiros ativos + notificações proativas do usuário.

Use SEMPRE que o usuário perguntar sobre:
- Alertas / avisos financeiros
- Se tem algo para se preocupar nas finanças
- Anomalias de gastos
- Assinaturas esquecidas
- Velocidade de gastos (burn rate)
"""
import logging

from langchain_core.tools import tool

from app.agent.procedencia import com_procedencia, degradada

logger = logging.getLogger(__name__)

# Janela do "recente". O detector compara esta fatia contra o histórico
# anterior a ela — os dois precisam existir, senão não há com o que comparar.
_JANELA_DIAS = 14


def _meses(df) -> int:
    """Meses distintos cobertos pelo extrato — a cobertura da procedência."""
    try:

        return int(df["transaction_date"].dt.strftime("%Y-%m").n_unique())
    except Exception:
        return 0


@tool
def get_spending_alerts(
    user_id: str,
    monthly_income: float | None = None,
) -> str:
    """
    Retorna os alertas financeiros ativos e notificações proativas do usuário.
    Inclui: anomalias de gasto, burn rate alto, assinaturas esquecidas,
    safe-to-spend baixo e oportunidades de cartão.

    Use esta ferramenta quando o usuário perguntar sobre:
    - Tem algum alerta / problema nas finanças?
    - Algum gasto anormal detectado?
    - Avisos importantes sobre as finanças
    - O que devo me preocupar este mês?

    Args:
        user_id: ID do usuário (obrigatório).
        monthly_income: Renda mensal (opcional — melhora detecção de anomalias).
    """
    logger.info("[Tool] get_spending_alerts para %s", user_id)
    try:
        from datetime import timedelta

        import polars as pl

        from app.core.db.queries import get_transactions_for_user
        from app.forecast.etl.spending_anomaly_detector import SpendingAnomalyDetector

        df = get_transactions_for_user(user_id)
        if df is None or df.is_empty():
            return degradada(
                "🔔 **Alertas e Notificações Financeiras**\n\n"
                "Não há transações para analisar. Conecte um banco para a Nexa "
                "comparar seus gastos com o seu próprio histórico.",
                motivo="sem_transacoes", fontes=["transactions_db"],
            )

        if "transaction_date" not in df.columns and "date" in df.columns:
            df = df.with_columns(pl.col("date").cast(pl.Datetime).alias("transaction_date"))

        # O detector compara a JANELA RECENTE contra o histórico do próprio
        # usuário — ele precisa dos dois DataFrames separados. A versão
        # anterior lia `result["alerts"]` do runner, chave que o pipeline não
        # produz, e depois chamava o ProactiveNotifier com um
        # `NotificationContext()` VAZIO. Nenhum dos dois caminhos tinha como
        # devolver alerta para usuário nenhum: a ferramenta respondia "suas
        # finanças parecem estáveis" para quem estivesse gastando 105% da
        # renda com cinco anomalias no mês.
        corte = df["transaction_date"].max() - timedelta(days=_JANELA_DIAS)
        recentes = df.filter(pl.col("transaction_date") >= corte)
        historico = df.filter(pl.col("transaction_date") < corte)
        if recentes.is_empty() or historico.is_empty():
            return com_procedencia(
                "🔔 **Alertas e Notificações Financeiras**\n\n"
                f"Base curta demais para comparar: são precisos ao menos "
                f"{_JANELA_DIAS} dias de histórico ANTES da janela recente "
                "para saber o que é incomum para você.",
                fontes=["transactions_db"], confianca=0.2,
                cobertura_meses=_meses(df),
            )

        perfil_renda = None
        try:
            from app.forecast.etl.income_profiler import IncomeProfiler

            perfil_renda = IncomeProfiler().build(df)
        except Exception as exc:  # renda é calibração, não requisito
            logger.debug("[Tool] alerts sem perfil de renda: %s", exc)

        anomalias = SpendingAnomalyDetector().detect(recentes, historico, perfil_renda)

        linhas = ["🔔 **Alertas e Notificações Financeiras**", ""]
        if not anomalias:
            linhas.append(
                f"✅ Nada fora do padrão nos últimos {_JANELA_DIAS} dias — "
                f"comparado com os seus próprios {_meses(df)} meses de histórico."
            )
            return com_procedencia(
                "\n".join(linhas), fontes=["transactions_db", "spending_anomaly_detector"],
                confianca=1.0, cobertura_meses=_meses(df),
            )

        por_severidade = {"ALERT": [], "WARNING": [], "INFO": []}
        for anomalia in anomalias:
            por_severidade.setdefault(
                str(getattr(anomalia, "severity", "INFO")), []
            ).append(anomalia)

        for severidade, titulo, emoji in (
            ("ALERT", "Exigem conferência agora", "🔴"),
            ("WARNING", "Fora do seu padrão", "🟡"),
            ("INFO", "Vale saber", "🔵"),
        ):
            grupo = por_severidade.get(severidade) or []
            if not grupo:
                continue
            linhas.append(f"{emoji} **{titulo}:**")
            for anomalia in grupo[:5]:
                linhas.append(f"   • {getattr(anomalia, 'description', str(anomalia))}")
            if len(grupo) > 5:
                linhas.append(f"   … e mais {len(grupo) - 5}.")
            linhas.append("")

        linhas.append(
            f"Total: {len(anomalias)} ponto(s) fora do padrão em "
            f"{len(recentes)} lançamentos dos últimos {_JANELA_DIAS} dias."
        )
        return com_procedencia(
            "\n".join(linhas),
            fontes=["transactions_db", "spending_anomaly_detector"]
                   + (["income_profiler"] if perfil_renda else []),
            confianca=1.0 if perfil_renda else 0.75,
            cobertura_meses=_meses(df),
        )

    except Exception as e:
        logger.error("[Tool] get_spending_alerts erro: %s", e, exc_info=True)
        return "Não foi possível verificar os alertas no momento. Tente novamente em instantes."
