"""
app/rights/parametros_legais.py — parâmetros legais datados do T3

Todo número deste módulo muda por lei, quase sempre em janeiro. Espalhados
pelo código, eles apodrecem em silêncio e o produto passa a dar orientação
errada com a mesma confiança de antes. Foi o que aconteceu:

  • `_ABONO_SALARIAL_TETO = 5 * 1412.0` — errado em DOIS níveis. O critério
    do abono nunca foi 5 salários mínimos, e sim 2; e o salário mínimo de
    R$ 1.412 é de 2024. O teto usado (R$ 7.060) era 2,6× o real.
  • `28_559.70` — faixa anual de isenção do IRPF de 2024. Em 2026 a isenção
    passou a R$ 5.000/mês (Lei 15.270/2025), ou seja, mais que o dobro.
    Quem ganha R$ 3.000/mês era informado de que está "acima do limite de
    isenção".

Por isso os parâmetros ficam aqui, com fonte e vigência, e
`tests/rights/test_parametros_legais.py` **falha quando o ano vira**. Um
comentário dizendo "atualizar todo ano" não é uma guarda; um teste vermelho é.
"""

from __future__ import annotations

from datetime import date

# ── Vigência ──────────────────────────────────────────────────────────────

#: Ano-calendário a que os parâmetros abaixo se referem. O teste de vigência
#: quebra quando `date.today().year` passa disso — é o alarme de atualização.
ANO_VIGENCIA = 2026


# ── Salário mínimo ────────────────────────────────────────────────────────

SALARIO_MINIMO = 1621.00
SALARIO_MINIMO_FONTE = (
    "Salário mínimo nacional de 2026: R$ 1.621,00, vigente desde 01/01/2026."
)


# ── Abono salarial PIS/PASEP ──────────────────────────────────────────────

#: Teto de remuneração MÉDIA MENSAL no ano-base para ter direito ao abono.
#: Até o calendário 2025 era 2 salários mínimos. A partir de 2026 o limite foi
#: desvinculado do salário mínimo e passa a ser corrigido pelo INPC, até
#: convergir para 1,5 salário mínimo (pacote fiscal de 2024).
ABONO_TETO_REMUNERACAO_MENSAL = 2765.93
ABONO_ANO_BASE = 2024
ABONO_FONTE = (
    "Calendário 2026 do Abono Salarial (ano-base 2024): remuneração média "
    "mensal de até R$ 2.765,93. O critério deixou de ser 2 salários mínimos e "
    "passou a ser corrigido pelo INPC, convergindo para 1,5 salário mínimo."
)

#: Requisitos do abono que dependem de dados que a Nexa NÃO tem. Estão aqui
#: para serem MOSTRADOS ao usuário — é o que separa "você tem direito" (que
#: não podemos afirmar) de "confira estes três pontos" (que podemos).
ABONO_REQUISITOS_NAO_VERIFICAVEIS = [
    "Estar inscrito no PIS/PASEP há pelo menos 5 anos.",
    f"Ter exercido atividade remunerada por no mínimo 30 dias em {ABONO_ANO_BASE}.",
    "Ter os dados informados corretamente pelo empregador na RAIS/eSocial.",
]


def abono_proporcional(meses_trabalhados: int) -> float:
    """
    Valor do abono: 1/12 do salário mínimo vigente por mês trabalhado no
    ano-base, limitado a 12/12.

    A implementação anterior fixava `months_worked = 12` e devolvia o salário
    mínimo cheio para QUALQUER renda — os dois ramos da função davam o mesmo
    número, o que a tornava uma constante disfarçada de cálculo.
    """
    meses = max(0, min(int(meses_trabalhados), 12))
    return round(SALARIO_MINIMO * meses / 12, 2)


# ── FGTS ──────────────────────────────────────────────────────────────────

FGTS_ALIQUOTA_MENSAL = 0.08
FGTS_FONTE = (
    "Art. 15 da Lei 8.036/1990 — depósito mensal de 8% da remuneração do "
    "trabalhador com contrato de trabalho regido pela CLT."
)


# ── IRPF ──────────────────────────────────────────────────────────────────

#: Rendimento mensal até o qual não há imposto a pagar.
IRPF_ISENCAO_MENSAL = 5000.00
#: Acima disso e até este valor há redução gradual do imposto devido.
IRPF_REDUCAO_GRADUAL_ATE_MENSAL = 7350.00
IRPF_FONTE = (
    "Lei 15.270/2025, vigente desde 01/2026 — isenção até R$ 5.000,00/mês e "
    "redução gradual entre R$ 5.000,01 e R$ 7.350,00."
)


def irpf_isencao_anual() -> float:
    """Isenção mensal projetada no ano — para comparar com renda anual."""
    return round(IRPF_ISENCAO_MENSAL * 12, 2)


# ── Guarda de vigência ────────────────────────────────────────────────────

def parametros_vencidos(hoje: date | None = None) -> bool:
    """True quando o ano corrente já passou do ano de vigência dos parâmetros."""
    return (hoje or date.today()).year > ANO_VIGENCIA


AVISO_VENCIDO = (
    "Os parâmetros legais do módulo de Direitos Esquecidos são de "
    f"{ANO_VIGENCIA}. Atualize `app/rights/parametros_legais.py`: salário "
    "mínimo, teto do abono salarial (corrigido pelo INPC) e faixa de isenção "
    "do IRPF mudam em janeiro."
)


__all__ = [
    "ANO_VIGENCIA",
    "SALARIO_MINIMO",
    "SALARIO_MINIMO_FONTE",
    "ABONO_TETO_REMUNERACAO_MENSAL",
    "ABONO_ANO_BASE",
    "ABONO_FONTE",
    "ABONO_REQUISITOS_NAO_VERIFICAVEIS",
    "abono_proporcional",
    "FGTS_ALIQUOTA_MENSAL",
    "FGTS_FONTE",
    "IRPF_ISENCAO_MENSAL",
    "IRPF_REDUCAO_GRADUAL_ATE_MENSAL",
    "IRPF_FONTE",
    "irpf_isencao_anual",
    "parametros_vencidos",
    "AVISO_VENCIDO",
]
