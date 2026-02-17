"""
app/architect/utils/date_helpers.py - Helpers para datas

Feature: F3 - Nexa Architect
Version: 1.0.0

Funcoes:
- months_between: Diferenca em meses entre duas datas
- add_months: Adiciona meses a uma data
- business_days_between: Dias uteis entre datas (sem feriados)
- is_business_day: Verifica se data e dia util
- next_business_day: Proximo dia util
"""

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta


def months_between(start_date: date, end_date: date) -> int:
    """
    Calcula diferenca em meses entre duas datas.

    Args:
        start_date: Data inicial
        end_date: Data final

    Returns:
        Numero de meses (pode ser negativo se end < start)

    Example:
        >>> from datetime import date
        >>> months_between(date(2026, 1, 15), date(2028, 3, 15))
        26
        >>> months_between(date(2026, 6, 1), date(2026, 1, 1))
        -5
    """
    delta = relativedelta(end_date, start_date)
    return delta.years * 12 + delta.months


def add_months(base_date: date, months: int) -> date:
    """
    Adiciona meses a uma data.

    Lida corretamente com fim de mes (ex: 31/jan + 1 mes = 28/fev).

    Args:
        base_date: Data base
        months: Meses a adicionar (pode ser negativo)

    Returns:
        Nova data

    Example:
        >>> from datetime import date
        >>> add_months(date(2026, 1, 15), 13)
        datetime.date(2027, 2, 15)
        >>> add_months(date(2026, 1, 31), 1)
        datetime.date(2026, 2, 28)
    """
    return base_date + relativedelta(months=months)


def business_days_between(start_date: date, end_date: date) -> int:
    """
    Calcula dias uteis entre duas datas (aproximado).

    Considera: seg-sex como uteis, sab-dom como nao uteis.
    Nao considera feriados nacionais.

    Args:
        start_date: Data inicial (exclusiva)
        end_date: Data final (inclusiva)

    Returns:
        Numero de dias uteis

    Example:
        >>> from datetime import date
        >>> business_days_between(date(2026, 2, 16), date(2026, 2, 20))
        4
    """
    if end_date < start_date:
        return -business_days_between(end_date, start_date)

    total_days = (end_date - start_date).days
    weeks = total_days // 7
    business_days = weeks * 5

    # Dias restantes
    remaining = total_days % 7
    current = start_date + timedelta(weeks=weeks)

    for _ in range(remaining):
        if current.weekday() < 5:  # 0=Seg, 4=Sex
            business_days += 1
        current += timedelta(days=1)

    return business_days


def is_business_day(check_date: date) -> bool:
    """
    Verifica se data e dia util.

    Args:
        check_date: Data a verificar

    Returns:
        True se dia util (seg-sex)

    Example:
        >>> from datetime import date
        >>> is_business_day(date(2026, 2, 16))  # Segunda
        True
        >>> is_business_day(date(2026, 2, 15))  # Domingo
        False
    """
    return check_date.weekday() < 5


def next_business_day(base_date: date) -> date:
    """
    Retorna proximo dia util apos a data informada.

    Args:
        base_date: Data base

    Returns:
        Proxima data que e dia util (sempre > base_date)

    Example:
        >>> from datetime import date
        >>> next_business_day(date(2026, 2, 13))  # Sexta
        datetime.date(2026, 2, 16)
        >>> next_business_day(date(2026, 2, 14))  # Sabado
        datetime.date(2026, 2, 16)
    """
    current = base_date + timedelta(days=1)
    while not is_business_day(current):
        current += timedelta(days=1)
    return current


__all__ = [
    "months_between",
    "add_months",
    "business_days_between",
    "is_business_day",
    "next_business_day",
]
