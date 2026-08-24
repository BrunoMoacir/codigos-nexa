"""
app/negotiator/health_score.py — o Score Nexa do usuário, uma vez só.

O F13 usa o health score em cinco lugares: dois portões de detecção
(`_MIN_HEALTH_SCORE_FOR_BARGAIN` e o piso de 70 do `HEALTH_SCORE_ALTO`), o
prompt do gerador de roteiro, o texto do roteiro de emergência e o
`estimated_success_pct`. Ele vinha de duas cópias idênticas de um helper —
uma em `negotiator/router.py`, outra em `agent/tools/get_negotiation_script.py`
— e as duas faziam:

    from app.profile.user_profile_analyzer import UserProfileAnalyzer
    profile = UserProfileAnalyzer().analyze(transactions_df, user_id=user_id)
    return profile.health_score

`app.profile` NÃO EXISTE no projeto. Três erros na mesma linha e meia: o módulo
(o analisador vive em `app.forecast.etl.profiles`), o parâmetro (`analyze()`
recebe `df, income_profile, committed_pct` — nunca `user_id`) e o campo (o
atributo é `financial_health_score`). O `ModuleNotFoundError` caía no `except`
e o score voltava **50 para todo mundo, sempre**.

Consequências medidas:

  • `_detect_score_only` exige ≥ 70. Com 50 fixo, a oportunidade
    `HEALTH_SCORE_ALTO` NUNCA disparou — nem para quem tem 90.
  • `estimated_success_pct = max(40, min(80, score))` valia exatamente 50 em
    todo roteiro de fallback.
  • O prompt do Claude afirmava "Health Score Nexa: 50/100" e o roteiro de
    emergência mandava o usuário dizer ao gerente "meu score é 50/100 — perfil
    de baixo risco".
  • `_compute_confidence` somava um `score_factor` constante de 0,15.

Nada disso alterava o card viral: `HEALTH_SCORE_ALTO` nasce com
`potential_saving_monthly=0.0`, então a soma do consolidador é a mesma.

Este módulo é a fonte única. Devolve `None` — não 50 — quando o perfil não
pôde ser calculado: um número inventado que atravessa portão, prompt e roteiro
é pior que a ausência declarada.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def score_nexa(transactions_df) -> Optional[int]:
    """
    Health score 0–100 pela régua do `UserProfileAnalyzer`, ou `None`.

    A renda de referência passa pelo `IncomeProfiler` quando ele consegue
    rodar: sem isso, Pix recebido, estorno e transferência entre contas
    próprias inflam o denominador e o score sobe sozinho. O analisador aceita
    `transaction_date` ou `date`, então o DataFrame de
    `get_transactions_for_user` serve como vem.

    Args:
        transactions_df: polars.DataFrame de transações do usuário.

    Returns:
        Score inteiro em [0, 100], ou None se o perfil não pôde ser calculado.
    """
    try:
        if transactions_df is None or transactions_df.is_empty():
            logger.warning("[F13] Score Nexa indisponível: sem transações.")
            return None

        from app.forecast.etl.profiles import UserProfileAnalyzer

        profile = UserProfileAnalyzer().analyze(
            transactions_df, income_profile=_perfil_de_renda(transactions_df)
        )
        return int(profile.financial_health_score)
    except Exception as exc:
        logger.warning("[F13] Score Nexa indisponível: %s", exc)
        return None


def _perfil_de_renda(transactions_df):
    """`IncomeProfile` do `IncomeProfiler`, ou None — nunca propaga exceção."""
    try:
        from app.forecast.etl.income_profiler import IncomeProfiler

        return IncomeProfiler().build(transactions_df)
    except Exception as exc:
        logger.info(
            "[F13] IncomeProfiler indisponível — score vai pela renda bruta: %s", exc
        )
        return None


__all__ = ["score_nexa"]
