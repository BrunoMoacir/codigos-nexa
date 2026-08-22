"""
app/rights/services/contexto_transacional.py — leitura única do extrato do T3

Os quatro verificadores de direitos liam as transações cada um por conta
própria — cinco idas ao banco por chamada de `GET /rights/{user_id}`, e cada
uma com a sua versão da janela, da coluna de data e da regex. Daí saíram três
defeitos independentes que este módulo elimina de uma vez:

1. **Média por transação em vez de renda mensal.** `income["amount"].mean()`
   é a média de CADA CRÉDITO. Quem ganha R$ 12.000/mês e recebe 60 Pix
   pequenos aparecia com "renda média R$ 1.901,41/mês" e virava elegível ao
   abono salarial. Aqui a renda mensal é a soma dos créditos do mês, e a média
   é entre MESES.

2. **Contagem de linhas em vez de meses.** `months = salary_rows.height`
   contava lançamentos. Quem recebe adiantamento + salário tem 2 linhas por
   mês: a mesma renda de R$ 4.000/mês produzia estimativa 40% menor do que a
   de quem recebe de uma vez só.

3. **Janela sem limite superior.** O mês corrente, pela metade, entrava na
   média e a diluía — o mesmo defeito já corrigido no Radar de Oportunidades.
   Aqui a janela vai até o último dia do mês COMPLETO anterior.

As regexes também moram aqui. No FGTS e no IRPF havia uma constante compilada
(`_CLT_KEYWORDS`, `_IR_KEYWORDS`) que ninguém usava, e uma regex inline
diferente no meio do filtro. A inline do IRPF não casava
"IMPOSTO DE RENDA RETIDO NA FONTE" — a forma mais literal que um extrato
escreve — enquanto a constante morta casava.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Créditos com cara de salário CLT. `\b` em ambas as pontas para não casar
# "pagamento" dentro de outra palavra.
PADRAO_SALARIO = (
    r"(?i)\b(salario|salário|folha|holerite|vencimento|remuneracao|remuneração|clt|"
    r"pagamento\s+de\s+salario|adiantamento\s+salarial)\b"
)

# Débitos de imposto de renda retido na fonte. Inclui "imposto de renda
# retido", que a versão em produção não casava.
PADRAO_IRRF = (
    r"(?i)\b(irrf|ir\s+retido|ret\s+ir|ret\s+fonte|ir\s+fonte|"
    r"imposto\s+de\s+renda\s+retido|imposto\s+renda\s+retido|imposto\s+sobre\s+a\s+renda)\b"
)


def _primeiro_dia(meses_atras: int, hoje: date | None = None) -> date:
    d = (hoje or date.today()).replace(day=1)
    for _ in range(meses_atras):
        d = (d - timedelta(days=1)).replace(day=1)
    return d


@dataclass
class ContextoTransacional:
    """
    Agregados mensais do extrato, calculados uma vez e compartilhados pelos
    verificadores. `disponivel=False` significa "sem dado", nunca "zero".
    """

    disponivel: bool = False
    #: mês "YYYY-MM" → soma dos créditos do mês
    renda_por_mes: dict[str, float] = field(default_factory=dict)
    #: mês "YYYY-MM" → soma dos créditos com padrão salarial CLT
    salario_por_mes: dict[str, float] = field(default_factory=dict)
    #: total de IRRF retido (débitos) na janela, em valor absoluto positivo
    irrf_retido: float = 0.0
    #: quantos lançamentos de IRRF sustentam o total acima
    irrf_lancamentos: int = 0
    #: rótulo legível da janela, para aparecer na explicação ao usuário
    janela: str = ""

    # ── derivados ────────────────────────────────────────────────────────

    @property
    def meses_com_renda(self) -> int:
        return len(self.renda_por_mes)

    @property
    def meses_com_salario(self) -> int:
        return len(self.salario_por_mes)

    @property
    def renda_mensal_media(self) -> float | None:
        """Média ENTRE MESES da soma dos créditos de cada mês."""
        if not self.renda_por_mes:
            return None
        return round(sum(self.renda_por_mes.values()) / len(self.renda_por_mes), 2)

    @property
    def salario_mensal_medio(self) -> float | None:
        """Média entre meses do salário CLT — imune a adiantamento e 13º parcelado."""
        if not self.salario_por_mes:
            return None
        return round(sum(self.salario_por_mes.values()) / len(self.salario_por_mes), 2)

    @property
    def renda_anual(self) -> float | None:
        """Créditos somados na janela. Não é projeção: é o que caiu."""
        if not self.renda_por_mes:
            return None
        return round(sum(self.renda_por_mes.values()), 2)

    # ── carga ────────────────────────────────────────────────────────────

    @classmethod
    def carregar(
        cls,
        user_id: str,
        meses: int = 12,
        hoje: date | None = None,
    ) -> "ContextoTransacional":
        """
        Lê o extrato uma vez e devolve os agregados dos últimos `meses` meses
        COMPLETOS. Nunca levanta: sem dado, devolve `disponivel=False`.
        """
        try:
            import polars as pl

            from app.core.db.queries import get_transactions_for_user

            df = get_transactions_for_user(user_id)
            if df is None or df.is_empty():
                return cls()

            col_data = "transaction_date" if "transaction_date" in df.columns else "date"
            if col_data not in df.columns or "amount" not in df.columns:
                return cls()
            col_desc = next(
                (c for c in ("description", "memo", "name") if c in df.columns), None
            )

            inicio = _primeiro_dia(meses, hoje)
            fim = _primeiro_dia(0, hoje)  # 1º dia do mês corrente — exclusivo
            janela = df.filter(
                (pl.col(col_data) >= inicio) & (pl.col(col_data) < fim)
            )
            if janela.is_empty():
                return cls()

            janela = janela.with_columns(
                pl.col(col_data).dt.strftime("%Y-%m").alias("_mes")
            )

            creditos = janela.filter(pl.col("amount") > 0)
            renda_por_mes = {
                linha["_mes"]: round(float(linha["total"]), 2)
                for linha in creditos.group_by("_mes")
                .agg(pl.col("amount").sum().alias("total"))
                .iter_rows(named=True)
            }

            salario_por_mes: dict[str, float] = {}
            irrf_total, irrf_n = 0.0, 0
            if col_desc:
                salarios = creditos.filter(pl.col(col_desc).str.contains(PADRAO_SALARIO))
                salario_por_mes = {
                    linha["_mes"]: round(float(linha["total"]), 2)
                    for linha in salarios.group_by("_mes")
                    .agg(pl.col("amount").sum().alias("total"))
                    .iter_rows(named=True)
                }

                # Só DÉBITOS. Somar com sinal misturava a restituição já
                # recebida (crédito) com o imposto retido (débito): seis
                # retenções de R$ 500 mais uma restituição de R$ 4.000
                # viravam "R$ 1.000 de IRRF retido".
                irrf = janela.filter(
                    (pl.col("amount") < 0) & pl.col(col_desc).str.contains(PADRAO_IRRF)
                )
                irrf_total = round(abs(float(irrf["amount"].sum() or 0.0)), 2)
                irrf_n = irrf.height

            return cls(
                disponivel=True,
                renda_por_mes=renda_por_mes,
                salario_por_mes=salario_por_mes,
                irrf_retido=irrf_total,
                irrf_lancamentos=irrf_n,
                janela=f"{inicio.strftime('%m/%Y')} a "
                       f"{(fim - timedelta(days=1)).strftime('%m/%Y')}",
            )

        except Exception as exc:
            logger.warning("[ContextoTransacional] user=%s: %s", user_id, exc)
            return cls()


__all__ = ["ContextoTransacional", "PADRAO_SALARIO", "PADRAO_IRRF"]
