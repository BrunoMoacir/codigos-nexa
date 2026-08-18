"""
app/forecast/cashflow/income_events.py — Renda como evento na linha do tempo.

╔══════════════════════════════════════════════════════════════════════╗
║ POR QUE ESTE MÓDULO EXISTE                                           ║
╚══════════════════════════════════════════════════════════════════════╝

A projeção de caixa nasceu sabendo só descer. Os dois detectores que a
alimentavam (SubscriptionDetector, InstallmentDetector) começam com
`filter(amount < 0)` — salário era matematicamente incapaz de virar
evento.

Resultado medido num CLT saudável (ganha 8.500, tem 3.000 na conta, quatro
meses sempre solvente): pior saldo projetado −R$ 421, safe-to-spend
R$ 0,00/dia, risco CRITICAL. O app dizia "você não pode gastar nada" para
quem tinha salário caindo em poucos dias.

╔══════════════════════════════════════════════════════════════════════╗
║ ASSIMETRIA DELIBERADA: RENDA É PROJETADA COM MAIS RIGOR              ║
╚══════════════════════════════════════════════════════════════════════╝

Errar para cima numa DESPESA é seguro (o usuário guarda demais). Errar
para cima numa RENDA é perigoso: o app libera gasto contra dinheiro que
pode não chegar. Por isso a régua aqui é mais dura que a das despesas:

  • série precisa de _MIN_OCORRENCIAS entradas, não uma;
  • cadência mensal comprovada (mediana entre 25 e 35 dias);
  • valor estável (coeficiente de variação < _CV_MAXIMO);
  • projeta o MENOR valor observado, não a média — se o salário variou
    entre 8.000 e 8.500, conta 8.000.

O que não passa nessas regras simplesmente não vira evento: nenhuma renda
projetada é melhor do que uma renda otimista.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

import polars as pl

logger = logging.getLogger(__name__)

# Uma entrada só não é padrão; duas já desenham cadência.
_MIN_OCORRENCIAS = 2
# Janela de tolerância da mediana dos intervalos (mensal com folga).
_GAP_MIN_DIAS = 25
_GAP_MAX_DIAS = 35
# Acima disso a renda é variável demais para virar promessa.
_CV_MAXIMO = 0.25


def detect_income_events(
    transactions_df: pl.DataFrame,
    horizon_days: int = 30,
    reference_date: Optional[date] = None,
) -> pl.DataFrame:
    """
    Créditos recorrentes projetados para a janela, no mesmo formato dos
    eventos de despesa (type/amount/next_due_date/merchant/origin).

    Devolve DataFrame vazio — nunca levanta — quando não há evidência
    suficiente: a projeção sem renda é conservadora, e conservador é o
    lado seguro de errar.
    """
    vazio = _vazio()

    if transactions_df is None or transactions_df.is_empty():
        return vazio
    if "amount" not in transactions_df.columns:
        return vazio

    df = _com_coluna_data(transactions_df)
    if df is None:
        return vazio

    creditos = df.filter(pl.col("amount") > 0)
    if creditos.height < _MIN_OCORRENCIAS:
        return vazio

    creditos = _somente_renda(creditos, df.filter(pl.col("amount") < 0))
    if creditos.height < _MIN_OCORRENCIAS:
        return vazio

    hoje = reference_date or date.today()
    limite = hoje + timedelta(days=horizon_days)

    eventos: list[dict] = []
    for chave, serie in _series_por_chave(creditos):
        evento_base = _avaliar_serie(chave, serie)
        if evento_base is None:
            continue
        eventos.extend(_projetar_ocorrencias(evento_base, hoje, limite))

    if not eventos:
        logger.info("[IncomeEvents] Nenhuma renda recorrente com evidência suficiente")
        return vazio

    total = sum(e["amount"] for e in eventos)
    logger.info(
        "[IncomeEvents] %s eventos de renda projetados (R$ %.2f na janela)",
        len(eventos), total,
    )
    return pl.DataFrame(eventos, schema=vazio.schema)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# INTERNO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _vazio() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "type": pl.Utf8,
            "amount": pl.Float64,
            "next_due_date": pl.Date,
            "merchant": pl.Utf8,
            "origin": pl.Utf8,
            "confidence": pl.Float64,
        }
    )


def _com_coluna_data(df: pl.DataFrame) -> Optional[pl.DataFrame]:
    """Normaliza a coluna de data para `_data` (pl.Date), venha ela como
    transaction_date (ETL) ou date (banco)."""
    for coluna in ("transaction_date", "date"):
        if coluna in df.columns:
            return df.with_columns(pl.col(coluna).cast(pl.Date).alias("_data"))
    return None


def _somente_renda(creditos: pl.DataFrame, debitos: pl.DataFrame) -> pl.DataFrame:
    """
    Reusa as exclusões do IncomeProfiler (estorno, transferência entre contas
    próprias, rendimento de investimento). Duplicar essa lista aqui seria
    garantir que as duas versões divergissem.
    """
    try:
        from app.forecast.etl.income_profiler import IncomeProfiler

        sinais: list[str] = []
        profiler = IncomeProfiler()
        # O IncomeProfiler trabalha com a coluna `date`.
        creditos_p = creditos.with_columns(pl.col("_data").alias("date"))
        debitos_p = debitos.with_columns(pl.col("_data").alias("date")) if not debitos.is_empty() else debitos

        filtrado = profiler._exclude_by_keywords(creditos_p, sinais)
        if not debitos_p.is_empty():
            filtrado = profiler._exclude_roundtrips(filtrado, debitos_p, sinais)
        if sinais:
            logger.debug("[IncomeEvents] %s", "; ".join(sinais))
        return filtrado
    except Exception as exc:
        logger.warning("[IncomeEvents] Exclusões do IncomeProfiler indisponíveis: %s", exc)
        return creditos


def _series_por_chave(creditos: pl.DataFrame):
    """Agrupa por origem do crédito — chave canônica quando o ETL a produziu."""
    coluna_chave = "merchant_key" if "merchant_key" in creditos.columns else "description"
    if coluna_chave not in creditos.columns:
        return []

    df = creditos.with_columns(
        pl.col(coluna_chave).cast(pl.String).fill_null("").str.to_lowercase().alias("_chave")
    ).filter(pl.col("_chave").str.len_chars() > 0)

    return [
        (chave, grupo.sort("_data"))
        for (chave,), grupo in df.group_by(["_chave"], maintain_order=True)
    ]


def _avaliar_serie(chave: str, serie: pl.DataFrame) -> Optional[dict]:
    """Uma série vira evento só se provar cadência mensal e valor estável."""
    if serie.height < _MIN_OCORRENCIAS:
        return None

    datas = serie["_data"].to_list()
    intervalos = [(datas[i] - datas[i - 1]).days for i in range(1, len(datas))]
    if not intervalos:
        return None

    intervalos_ordenados = sorted(intervalos)
    mediana = intervalos_ordenados[len(intervalos_ordenados) // 2]
    if not (_GAP_MIN_DIAS <= mediana <= _GAP_MAX_DIAS):
        return None

    valores = serie["amount"].to_list()
    media = sum(valores) / len(valores)
    if media <= 0:
        return None
    desvio = (sum((v - media) ** 2 for v in valores) / len(valores)) ** 0.5
    cv = desvio / media
    if cv > _CV_MAXIMO:
        return None

    # O MENOR valor da série, não a média: se variou, conta o pior caso.
    valor = min(valores)
    confianca = round(min(0.95, 0.6 + 0.1 * serie.height - cv), 2)

    return {
        "chave": chave,
        "ultima_data": datas[-1],
        "gap": mediana,
        "amount": float(valor),
        "confidence": confianca,
    }


def _projetar_ocorrencias(base: dict, hoje: date, limite: date) -> list[dict]:
    """Repete a cadência até o fim da janela, começando na próxima ocorrência."""
    eventos = []
    proxima = base["ultima_data"] + timedelta(days=base["gap"])

    # Cadência que já venceu sem aparecer no extrato (atraso, lag do banco):
    # avança para a próxima futura em vez de lançar no passado.
    while proxima <= hoje:
        proxima += timedelta(days=base["gap"])

    while proxima <= limite:
        eventos.append({
            "type": "INCOME",
            "amount": base["amount"],
            "next_due_date": proxima,
            "merchant": base["chave"][:80],
            "origin": "income_recurrence",
            "confidence": base["confidence"],
        })
        proxima += timedelta(days=base["gap"])

    return eventos
