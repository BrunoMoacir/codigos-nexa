"""
app/seasonality/profile_probe.py — Sinais de perfil para personalização (R2.c)

Consultas baratas em transactions_clean (sem rodar o pipeline completo do
NexaRunner) que respondem três perguntas:

  1. O usuário tem sinal de MEI/PJ?     → ativa DAS_MEI / DASN_SIMEI
  2. O usuário tem salário recorrente?  → ativa 13º e estima o valor
  3. Quanto pagou de IPVA/IPTU/DAS?     → personaliza valores nos cards

Todas as funções falham abertas (retornam o valor neutro) — a sazonalidade
genérica continua funcionando sem nenhum dado do usuário.

SQL portável Postgres/SQLite: usa LOWER(...) LIKE em vez de ILIKE. Para o
DAS, o SQL faz só a pré-seleção barata e o regex com fronteira de palavra
(MEI_REGEX) decide — LIKE '%das %' casava com "polegadas 2x", "lojas das
americanas" etc. (falso positivo medido em corpus real pelo
scripts/calibrate_retention_heuristics.py).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Nº mínimo de transações PJ nos últimos 90 dias para considerar perfil MEI/PJ
_MIN_PJ_TXNS = 5

# Pré-seleção SQL barata de candidatos a DAS (recall alto, precisão baixa)
_DAS_SQL_PREFILTER = ("%das%", "%simei%", "%simples%", "%pgmei%")

# Decisão final de DAS/MEI — fronteiras de palavra, calibrado contra os
# corpora reais (duckdb 12k + transactions_clean do PG dev)
MEI_REGEX = re.compile(
    r"\bdas\b.*(simples|mei|nacional)"       # "das simples nacional", "das mei"
    r"|(imposto|guia|pagamento|pgto)\s+das\b"  # "imposto das", "guia das"
    r"|\bdas\s+\d{2}/\d{4}\b"                # "das 06/2026"
    r"|\bpgmei\b|\bsimei\b|simples\s+nacional",
    re.IGNORECASE,
)

# Padrões de salário — LIKEs aplicados no SQL (ver _detect_salary); a
# calibração mostrou 317/323 créditos de salário capturados no corpus 12k
_SALARY_LIKE_PATTERNS = (
    "%salario%", "%salário%", "%folha%", "%provento%",
    "%remunera%", "%pro labore%", "%pro-labore%",
)

# Espelho regex dos LIKEs acima — usado pelo script de calibração para
# medir os mesmos padrões sobre qualquer corpus (manter em sincronia)
SALARY_REGEX = re.compile(
    r"salario|salário|folha|provento|remunera|pro.?labore",
    re.IGNORECASE,
)

# Padrões de IPVA/IPTU
_IPVA_IPTU_PATTERNS = ("%ipva%", "%iptu%", "%detran%")


@dataclass
class SeasonalProfile:
    """Sinais de perfil relevantes para o calendário fiscal."""
    is_mei: bool = False
    has_salary: bool = False
    monthly_salary_brl: float | None = None      # salário líquido recorrente
    last_das_amount_brl: float | None = None     # último DAS pago
    ipva_iptu_last_year_brl: float | None = None # IPVA+IPTU pagos no ano anterior
    annual_income_brl: float | None = None       # renda estimada 12m (p/ IR)


def build_profile(user_id: str, today: date | None = None) -> SeasonalProfile:
    """Monta o perfil sazonal do usuário com consultas diretas ao banco."""
    today = today or date.today()
    profile = SeasonalProfile()

    try:
        from app.core.database import SessionLocal

        with SessionLocal() as db:
            profile.is_mei = _detect_mei(db, user_id, today)
            if profile.is_mei:
                profile.last_das_amount_brl = _last_das_amount(db, user_id)

            salary = _detect_salary(db, user_id, today)
            if salary is not None:
                profile.has_salary = True
                profile.monthly_salary_brl = salary

            profile.ipva_iptu_last_year_brl = _ipva_iptu_paid(db, user_id, today.year - 1)
            profile.annual_income_brl = _annual_income(db, user_id, today)
    except Exception as exc:
        logger.warning("[SeasonalProfile] user=%s indisponível: %s", user_id, exc)

    return profile


# ── Detectores ───────────────────────────────────────────────────────

def _fetch_das_candidates(db, user_id: str) -> list[tuple]:
    """Pré-seleção SQL barata + decisão final via MEI_REGEX (fronteira de
    palavra). Retorna [(date, abs_amount, description)] ordenado desc."""
    from sqlalchemy import text

    rows = db.execute(
        text(
            "SELECT date, ABS(amount), description FROM transactions_clean"
            " WHERE user_id = :uid AND amount < 0"
            f" AND ({_like_clause('description', _DAS_SQL_PREFILTER)})"
            " ORDER BY date DESC LIMIT 200"
        ),
        {"uid": user_id},
    ).fetchall()
    return [r for r in rows if MEI_REGEX.search(r[2] or "")]


def _detect_mei(db, user_id: str, today: date) -> bool:
    """MEI/PJ = pagou DAS alguma vez OU tem volume PJ relevante em 90d."""
    from sqlalchemy import text

    if _fetch_das_candidates(db, user_id):
        return True

    cutoff = today - timedelta(days=90)
    row = db.execute(
        text(
            "SELECT COUNT(*) FROM transactions_clean"
            " WHERE user_id = :uid AND date >= :cutoff"
            " AND UPPER(COALESCE(context_type, '')) = 'PJ'"
        ),
        {"uid": user_id, "cutoff": cutoff},
    ).fetchone()
    return bool(row and int(row[0]) >= _MIN_PJ_TXNS)


def _last_das_amount(db, user_id: str) -> float | None:
    candidates = _fetch_das_candidates(db, user_id)
    if not candidates:
        return None
    return round(float(candidates[0][1]), 2)


def _detect_salary(db, user_id: str, today: date) -> float | None:
    """
    Salário recorrente = crédito marcado is_recurring OU descrição com
    salário/folha/pgto, presente em >= 2 dos últimos 3 meses.
    Retorna a mediana mensal (aproximada pela média das somas mensais).
    """
    from sqlalchemy import text

    cutoff = (today.replace(day=1) - timedelta(days=93)).replace(day=1)
    rows = db.execute(
        text(
            "SELECT date, amount FROM transactions_clean"
            " WHERE user_id = :uid AND amount > 0 AND date >= :cutoff"
            " AND (is_recurring = :yes"
            f"      OR {_like_clause('description', _SALARY_LIKE_PATTERNS)}"
            "      OR LOWER(COALESCE(category, '')) LIKE '%salario%'"
            "      OR LOWER(COALESCE(category, '')) LIKE '%salário%')"
        ),
        {"uid": user_id, "cutoff": cutoff, "yes": True},
    ).fetchall()

    monthly: dict[str, float] = {}
    for tx_date, amount in rows:
        key = str(tx_date)[:7]   # YYYY-MM
        monthly[key] = monthly.get(key, 0.0) + float(amount)

    # exclui o mês corrente (parcial) da contagem de recorrência
    current_key = today.strftime("%Y-%m")
    complete_months = {k: v for k, v in monthly.items() if k != current_key}
    if len(complete_months) < 2:
        return None

    values = sorted(complete_months.values())
    mid = len(values) // 2
    median = values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2
    return round(median, 2)


def _ipva_iptu_paid(db, user_id: str, year: int) -> float | None:
    from sqlalchemy import text

    start, end = date(year, 1, 1), date(year, 12, 31)
    row = db.execute(
        text(
            "SELECT SUM(ABS(amount)) FROM transactions_clean"
            " WHERE user_id = :uid AND amount < 0"
            " AND date >= :start AND date <= :end"
            f" AND ({_like_clause('description', _IPVA_IPTU_PATTERNS)})"
        ),
        {"uid": user_id, "start": start, "end": end},
    ).fetchone()
    total = float(row[0]) if row and row[0] is not None else 0.0
    return round(total, 2) if total > 0 else None


def _annual_income(db, user_id: str, today: date) -> float | None:
    from sqlalchemy import text

    cutoff = today - timedelta(days=365)
    row = db.execute(
        text(
            "SELECT SUM(amount) FROM transactions_clean"
            " WHERE user_id = :uid AND amount > 0 AND date >= :cutoff"
        ),
        {"uid": user_id, "cutoff": cutoff},
    ).fetchone()
    total = float(row[0]) if row and row[0] is not None else 0.0
    return round(total, 2) if total > 0 else None


def _like_clause(column: str, patterns: tuple[str, ...]) -> str:
    """Monta OR de LOWER(col) LIKE '<pattern>' — padrões são constantes internas."""
    return " OR ".join(
        f"LOWER(COALESCE({column}, '')) LIKE '{p}'" for p in patterns
    )


__all__ = ["MEI_REGEX", "SeasonalProfile", "build_profile"]
