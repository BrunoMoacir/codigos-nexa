"""
app/architect/utils/formatters.py - Formatacao de valores

Feature: F3 - Nexa Architect
Version: 1.0.0

Funcoes:
- format_currency: R$ 1.234,56
- format_percentage: 12,50%
- format_months: 24 meses
- format_compact_number: R$ 1,5M
"""


def format_currency(
    amount: float,
    symbol: str = "R$",
    decimals: int = 2
) -> str:
    """
    Formata valor em moeda brasileira.

    Args:
        amount: Valor numerico
        symbol: Simbolo da moeda
        decimals: Casas decimais

    Returns:
        String formatada (ex: "R$ 1.234,56")

    Example:
        >>> format_currency(1234.56)
        'R$ 1.234,56'
        >>> format_currency(1000000)
        'R$ 1.000.000,00'
        >>> format_currency(-500.10)
        '-R$ 500,10'
    """
    sign = "-" if amount < 0 else ""
    abs_amount = abs(amount)

    # Formatar com f-string para evitar erros de ponto flutuante
    formatted = f"{abs_amount:,.{decimals}f}"  # "1,234.56"

    if decimals > 0:
        int_str, dec_str = formatted.split(".")
        int_str = int_str.replace(",", ".")
        return f"{sign}{symbol} {int_str},{dec_str}"
    else:
        int_str = formatted.replace(",", ".")
        return f"{sign}{symbol} {int_str}"


def format_percentage(
    value: float,
    decimals: int = 2,
    multiply_by_100: bool = True
) -> str:
    """
    Formata valor como percentual.

    Args:
        value: Valor decimal (ex: 0.125 ou 12.5)
        decimals: Casas decimais
        multiply_by_100: Se True, multiplica por 100

    Returns:
        String formatada (ex: "12,50%")

    Example:
        >>> format_percentage(0.125)
        '12,50%'
        >>> format_percentage(12.5, multiply_by_100=False)
        '12,50%'
    """
    if multiply_by_100:
        value = value * 100

    formatted = f"{value:.{decimals}f}".replace(".", ",")
    return f"{formatted}%"


def format_months(months: int) -> str:
    """
    Formata prazo em meses.

    Args:
        months: Numero de meses

    Returns:
        String formatada (ex: "24 meses", "1 ano", "2 anos e 3 meses")

    Raises:
        ValueError: Se months < 0

    Example:
        >>> format_months(24)
        '2 anos'
        >>> format_months(27)
        '2 anos e 3 meses'
        >>> format_months(1)
        '1 mes'
    """
    if months < 0:
        raise ValueError("Numero de meses nao pode ser negativo")

    if months == 0:
        return "0 meses"

    if months == 1:
        return "1 mes"

    if months < 12:
        return f"{months} meses"

    years = months // 12
    remaining_months = months % 12

    year_str = f"{years} ano" if years == 1 else f"{years} anos"

    if remaining_months == 0:
        return year_str

    month_str = f"{remaining_months} mes" if remaining_months == 1 else f"{remaining_months} meses"
    return f"{year_str} e {month_str}"


def format_compact_number(value: float) -> str:
    """
    Formata numero de forma compacta (1K, 1M, etc).

    Args:
        value: Valor numerico

    Returns:
        String compacta (ex: "R$ 1,2K", "R$ 1,5M")

    Example:
        >>> format_compact_number(1234)
        'R$ 1,2K'
        >>> format_compact_number(1500000)
        'R$ 1,5M'
    """
    abs_value = abs(value)
    sign = "-" if value < 0 else ""

    if abs_value >= 1_000_000:
        compact = abs_value / 1_000_000
        suffix = "M"
    elif abs_value >= 1_000:
        compact = abs_value / 1_000
        # Promover para M se arredondamento em :.1f >= 1000
        if round(compact, 1) >= 1000:
            compact = abs_value / 1_000_000
            suffix = "M"
        else:
            suffix = "K"
    else:
        return format_currency(value)

    formatted = f"{compact:.1f}".replace(".", ",")
    return f"{sign}R$ {formatted}{suffix}"


__all__ = [
    "format_currency",
    "format_percentage",
    "format_months",
    "format_compact_number",
]
