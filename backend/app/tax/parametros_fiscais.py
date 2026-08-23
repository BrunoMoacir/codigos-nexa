"""
app/tax/parametros_fiscais.py — regras tributárias de investimento, num lugar só

Havia DUAS tabelas de bracket de IR no projeto, com semânticas diferentes:
`_IR_BANDS` em `fiscal/ir_pf_calculator.py`, em DIAS e correta, e `_BRACKETS`
em `tax/services/tax_loss_harvesting.py`, em MESES e com o significado
invertido — a lista `(6, 0.225)` era lida como "o próximo degrau é aos 6
meses", quando 6 meses é o fim da faixa em que a posição já está. O resultado
foi um detector que disparava em 1 de 29 prazos possíveis.

Este módulo é a fonte única. Trabalha em DIAS, que é a unidade da lei.

Fontes:
  Lei 11.033/2004, art. 1º — tabela regressiva de IR em renda fixa e fundos.
    (a citação anterior, "Lei 8.981/1995, art. 65", é de outro regime)
  Lei 11.033/2004, art. 3º, I — isenção de ganhos em ações até R$ 20.000 de
    ALIENAÇÕES no mês; não se aplica a FII nem a day trade.
  Lei 8.668/1993 e IN RFB 1.585/2015 — FII: 20% sobre o ganho, sem isenção.
  IN RFB 1.585/2015, art. 64 — come-cotas em maio e novembro.
  IN RFB 1.585/2015 — compensação de perdas por categoria.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal, Optional

# ── Tabela regressiva (Lei 11.033/2004, art. 1º) ──────────────────────
# (último dia da faixa, alíquota). "Até 180 dias" → 180 é inclusivo.
TABELA_REGRESSIVA: list[tuple[int, float]] = [
    (180, 0.225),
    (360, 0.200),
    (720, 0.175),
]
ALIQUOTA_ACIMA_DE_720 = 0.150

BASE_LEGAL_REGRESSIVA = "Lei 11.033/2004, art. 1º — tabela regressiva de IR."


def aliquota_regressiva(dias: int) -> float:
    """Alíquota da tabela regressiva para um prazo em dias."""
    for limite, aliquota in TABELA_REGRESSIVA:
        if dias <= limite:
            return aliquota
    return ALIQUOTA_ACIMA_DE_720


def proximo_degrau(dias: int) -> Optional[tuple[int, float]]:
    """
    `(dias_que_faltam, nova_aliquota)` até a alíquota cair — ou None se já
    está na menor faixa.

    O degrau começa no dia SEGUINTE ao fim da faixa: "até 180 dias" é 22,5%,
    então a queda para 20% acontece no dia 181. Era exatamente isso que a
    versão em meses errava: aos 180 dias ela mandava esperar mais 6 MESES
    quando falta 1 dia, e para qualquer prazo dentro de uma faixa ela
    devolvia a alíquota da própria faixa, o que fazia o detector se calar.
    """
    for limite, _aliquota in TABELA_REGRESSIVA:
        if dias <= limite:
            faltam = limite + 1 - dias
            return faltam, aliquota_regressiva(limite + 1)
    return None


# ── Classes de compensação de prejuízo ────────────────────────────────
#
# Compensar prejuízo NÃO é possível em renda fixa. O IR do CDB, do Tesouro e
# das debêntures é retido na fonte sobre o rendimento de CADA operação; não
# existe apuração que permita abater a perda de um papel do ganho de outro.
# A compensação existe em renda variável e, com restrições, entre fundos.
#
# `None` = a perda não abate nada. Classes iguais compensam entre si.
ClasseCompensacao = Literal["bolsa", "fii", "fundo", "fundo_acoes"]

CLASSE_POR_PRODUTO: dict[str, Optional[str]] = {
    # Renda variável em bolsa — compensa dentro da própria categoria,
    # com saldo carregado indefinidamente.
    "ACAO": "bolsa",
    "ETF": "bolsa",
    "BDR": "bolsa",
    # FII é categoria SEPARADA: perda de FII só abate ganho de FII.
    "FII": "fii",
    # Fundos: perda abate ganho de fundo da MESMA administradora e mesma
    # classificação tributária (IN RFB 1.585/2015).
    "FUNDO_RF": "fundo",
    "FUNDO_MM": "fundo",
    "FUNDO_ACOES": "fundo_acoes",
    # Renda fixa — sem compensação.
    "CDB": None,
    "LC": None,
    "LF": None,
    "TESOURO": None,
    "DEBENTURE": None,
    "DEBENTURE_INCENTIVADA": None,
    "LCI": None,
    "LCA": None,
    "CRI": None,
    "CRA": None,
    "POUPANCA": None,
}

BASE_LEGAL_COMPENSACAO = (
    "IN RFB 1.585/2015 — a compensação de perdas ocorre dentro da mesma "
    "categoria: ações/ETF entre si, FII apenas com FII, e fundos apenas com "
    "fundos da mesma administradora e mesma classificação tributária. "
    "Renda fixa não tem compensação: o IR é retido na fonte por operação."
)


def classe_de_compensacao(product_type: str) -> Optional[str]:
    """Classe de compensação do produto, ou None se a perda não abate nada."""
    return CLASSE_POR_PRODUTO.get((product_type or "").upper())


# ── Alíquota de ganho por classe ──────────────────────────────────────

#: Swing trade em bolsa: 15% sobre o ganho líquido do mês.
ALIQUOTA_BOLSA = 0.15
#: FII: 20% sobre o ganho, sem isenção por valor.
ALIQUOTA_FII = 0.20


def aliquota_de_ganho(product_type: str, dias: int) -> float:
    """
    Alíquota aplicável ao GANHO da posição.

    A tabela regressiva vale para renda fixa e fundos. Ação e ETF são 15%
    lineares e FII é 20% linear — aplicar a regressiva neles (como o
    `InvestmentProfiler` fazia, via `calc_ir_on_cdb`) dá 22,5% numa posição
    de 3 meses, meio ponto e meio acima do devido.
    """
    classe = classe_de_compensacao(product_type)
    if classe == "bolsa":
        return ALIQUOTA_BOLSA
    if classe == "fii":
        return ALIQUOTA_FII
    return aliquota_regressiva(dias)


# ── Isenção de R$ 20.000 em alienações de ações ───────────────────────

ISENCAO_BOLSA_ALIENACOES_MES = 20_000.00
BASE_LEGAL_ISENCAO_BOLSA = (
    "Lei 11.033/2004, art. 3º, I — ganhos em alienações de ações são isentos "
    "quando o total vendido no mês fica em até R$ 20.000,00. Não se aplica a "
    "FII nem a day trade."
)


def ganho_de_bolsa_e_isento(valor_total_alienado_mes: float) -> bool:
    """True quando o total de alienações do mês cabe na isenção."""
    return valor_total_alienado_mes <= ISENCAO_BOLSA_ALIENACOES_MES


# ── Come-cotas ────────────────────────────────────────────────────────

COME_COTAS_MESES = (5, 11)
#: 15% para fundo de LONGO prazo; fundo de curto prazo (carteira média até
#: 365 dias) sofre 20%. A Pluggy não informa a duração da carteira, então o
#: número é apresentado como o piso, com o rótulo dizendo qual é.
COME_COTAS_ALIQUOTA_LONGO_PRAZO = 0.15
COME_COTAS_ALIQUOTA_CURTO_PRAZO = 0.20
BASE_LEGAL_COME_COTAS = (
    "IN RFB 1.585/2015, art. 64 — antecipação semestral de IR no último dia "
    "útil de maio e de novembro: 15% em fundos de longo prazo e 20% em fundos "
    "de curto prazo."
)


def proximo_come_cotas(hoje: date) -> tuple[date, str]:
    """
    Data e nome do mês da próxima incidência de come-cotas.

    A versão anterior decidia o rótulo por `meses_restantes <= 5`, o que
    marcava "maio" em SETE dos doze meses do ano — de junho a outubro a
    distância até novembro é ≤ 5. E o mês de incidência devolvia 6 meses,
    ignorando que a cobrança é naquele mesmo mês. A data impressa para maio
    era a string `"31/{ano}"`, sem mês.
    """
    for mes in COME_COTAS_MESES:
        if hoje.month <= mes:
            return _ultimo_dia(hoje.year, mes), _NOME_MES[mes]
    return _ultimo_dia(hoje.year + 1, COME_COTAS_MESES[0]), _NOME_MES[COME_COTAS_MESES[0]]


_NOME_MES = {5: "maio", 11: "novembro"}


def _ultimo_dia(ano: int, mes: int) -> date:
    if mes == 12:
        return date(ano, 12, 31)
    return date(ano, mes + 1, 1) - timedelta(days=1)


# ── Fator R — Anexo III vs Anexo V ────────────────────────────────────

FATOR_R_LIMITE = 0.28
BASE_LEGAL_FATOR_R = (
    "LC 123/2006, art. 18, §§ 5º-J e 5º-M — atividades de serviço são "
    "tributadas pelo Anexo III quando a folha de salários dos 12 meses "
    "anteriores representa 28% ou mais da receita bruta do mesmo período; "
    "abaixo disso, pelo Anexo V."
)


def anexo_por_fator_r(folha_12m: float, receita_12m: float) -> tuple[str, Optional[float]]:
    """
    `("III"|"V", fator_r)` — ou `("V", None)` quando não há receita para o
    denominador (sem receita, não há Fator R e o Anexo V é o conservador).
    """
    if receita_12m <= 0:
        return "V", None
    fator = folha_12m / receita_12m
    return ("III" if fator >= FATOR_R_LIMITE else "V"), round(fator, 4)


__all__ = [
    "TABELA_REGRESSIVA",
    "ALIQUOTA_ACIMA_DE_720",
    "BASE_LEGAL_REGRESSIVA",
    "aliquota_regressiva",
    "proximo_degrau",
    "CLASSE_POR_PRODUTO",
    "BASE_LEGAL_COMPENSACAO",
    "classe_de_compensacao",
    "ALIQUOTA_BOLSA",
    "ALIQUOTA_FII",
    "aliquota_de_ganho",
    "ISENCAO_BOLSA_ALIENACOES_MES",
    "BASE_LEGAL_ISENCAO_BOLSA",
    "ganho_de_bolsa_e_isento",
    "COME_COTAS_MESES",
    "COME_COTAS_ALIQUOTA_LONGO_PRAZO",
    "COME_COTAS_ALIQUOTA_CURTO_PRAZO",
    "BASE_LEGAL_COME_COTAS",
    "proximo_come_cotas",
    "FATOR_R_LIMITE",
    "BASE_LEGAL_FATOR_R",
    "anexo_por_fator_r",
]
