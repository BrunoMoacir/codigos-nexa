"""
🧪 CASHFLOW E SAFE-TO-SPEND (F1) — COMPORTAMENTO DE PRODUÇÃO
═══════════════════════════════════════════════════════════════════════════════

Os dois testes que existiam para o motor asseriam `not is_empty()` e
`"projected_balance" in columns` — passavam com a projeção retornando uma
LINHA RETA. Este arquivo cobre o que o usuário sente na tela.

Cada teste aqui nasceu de um defeito medido:

  1. renda invisível  — os detectores de evento filtram `amount < 0`, então
     a projeção só sabia descer: CLT saudável recebia "R$ 0,00/dia,
     CRITICAL" com salário a três dias de cair;
  2. date × datetime  — calendário e eventos indexados por tipos diferentes:
     nenhum evento casava, saldo virava linha reta, safe-to-spend inflado;
  3. âncora no passado — projeção começava na última transação, gastando os
     primeiros dias da janela em datas já vividas;
  4. get_summary()    — chamado pelo CashflowEngine e inexistente: o
     orquestrador documentado como porta de entrada morria em AttributeError.

Como executar:
    cd backend && python -m pytest tests/test_cashflow_producao.py -v
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.forecast.cashflow.engine import CashflowEngine  # noqa: E402
from app.forecast.cashflow.income_events import detect_income_events  # noqa: E402
from app.forecast.cashflow.projector import CashflowProjector  # noqa: E402
from app.forecast.cashflow.safe_to_spend import SafeToSpendCalculator  # noqa: E402

HOJE = date.today()
SALDO_HOJE = 3000.0
SALARIO = 8500.0


def _extrato_clt(meses: int = 4, com_salario: bool = True) -> pl.DataFrame:
    """
    Assalariado comum: salário todo mês, aluguel, assinaturas e variáveis.
    Saldo reconstruído de trás para frente para terminar em SALDO_HOJE.
    """
    lancamentos = []
    for m in range(meses):
        base = HOJE - timedelta(days=30 * m)
        linhas = [
            (-25, "PIX RECEBIDO SALARIO EMPRESA TECH", SALARIO),
            (-20, "ALUGUEL APARTAMENTO", -2200.0),
            (-18, "NETFLIX.COM", -49.90),
            (-18, "SPOTIFY PREMIUM", -21.90),
            (-15, "SUPERMERCADO EXTRA", -850.0),
            (-10, "ENEL ENERGIA ELETRICA", -180.0),
            (-5, "IFOOD DELIVERY", -120.0),
        ]
        if not com_salario:
            linhas = [l for l in linhas if l[2] < 0]

        for delta, descricao, valor in linhas:
            dia = base + timedelta(days=delta)
            if dia <= HOJE:
                lancamentos.append({
                    "transaction_date": dia,
                    "amount": valor,
                    "description": descricao,
                    "balance": None,
                    "account_id": "acc_corrente",
                })

    lancamentos.sort(key=lambda t: t["transaction_date"])
    corrente = SALDO_HOJE - sum(t["amount"] for t in lancamentos)
    for t in lancamentos:
        corrente += t["amount"]
        t["balance"] = round(corrente, 2)

    return pl.DataFrame(lancamentos).with_columns(
        pl.col("transaction_date").cast(pl.Date)
    )


def _obrigacoes(dias: list[int], valor: float = -500.0) -> pl.DataFrame:
    return pl.DataFrame({
        "type": ["SUBSCRIPTION"] * len(dias),
        "amount": [valor] * len(dias),
        "next_due_date": [HOJE + timedelta(days=d) for d in dias],
        "merchant": ["obrigacao"] * len(dias),
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. RENDA NA LINHA DO TEMPO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestRendaNaProjecao:

    def test_assalariado_saudavel_nao_recebe_zero_por_dia(self):
        """
        O caso que expôs o defeito: ganha R$ 8.500, tem R$ 3.000 na conta,
        quatro meses sempre solvente. A resposta era R$ 0,00/dia e CRITICAL
        porque a projeção somava só obrigações.
        """
        df = _extrato_clt()
        obrigacoes = _obrigacoes([3, 8, 14], valor=-1100.0)  # R$ 3.300 no mês

        projecao = CashflowProjector().project(df, obrigacoes, current_balance=SALDO_HOJE)
        resultado = SafeToSpendCalculator().calculate(projecao, horizon_days=30)

        creditos = [
            evento
            for eventos in projecao["events"].to_list()
            for evento in eventos
            if evento["amount"] > 0
        ]
        assert creditos, "o salário mensal tem que virar evento de crédito"
        assert creditos[0]["type"] == "INCOME"

        assert resultado.safe_to_spend_total > 0, (
            "usuário solvente não pode receber margem zero"
        )
        assert resultado.risk_level != "CRITICAL"

    def test_sem_renda_recorrente_a_projecao_segue_conservadora(self):
        """
        Sem evidência de renda, nada é inventado: a projeção continua só
        com obrigações. Errar para cima na renda liberaria gasto contra
        dinheiro que pode não chegar.
        """
        df = _extrato_clt(com_salario=False)
        projecao = CashflowProjector().project(df, _obrigacoes([5]), current_balance=1000.0)

        creditos = [
            e for eventos in projecao["events"].to_list() for e in eventos if e["amount"] > 0
        ]
        assert not creditos
        assert projecao["projected_balance"][-1] == pytest.approx(500.0)

    def test_renda_projetada_usa_o_menor_valor_da_serie(self):
        """Salário que oscilou entre 8.000 e 8.500 conta como 8.000."""
        base = HOJE - timedelta(days=65)
        linhas = [
            {"transaction_date": base, "amount": 8500.0, "description": "SALARIO EMPRESA", "balance": 1.0, "account_id": "a"},
            {"transaction_date": base + timedelta(days=30), "amount": 8000.0, "description": "SALARIO EMPRESA", "balance": 1.0, "account_id": "a"},
            {"transaction_date": base + timedelta(days=60), "amount": 8400.0, "description": "SALARIO EMPRESA", "balance": 1.0, "account_id": "a"},
        ]
        df = pl.DataFrame(linhas).with_columns(pl.col("transaction_date").cast(pl.Date))

        eventos = detect_income_events(df, horizon_days=40, reference_date=HOJE)

        assert eventos.height >= 1
        assert eventos["amount"][0] == pytest.approx(8000.0), "conservador: o menor da série"

    def test_credito_avulso_nao_vira_renda(self):
        """Um PIX de amigo não é padrão — precisa de cadência mensal."""
        df = pl.DataFrame({
            "transaction_date": [HOJE - timedelta(days=10)],
            "amount": [1500.0],
            "description": ["PIX RECEBIDO AMIGO"],
            "balance": [1500.0],
            "account_id": ["a"],
        }).with_columns(pl.col("transaction_date").cast(pl.Date))

        assert detect_income_events(df, reference_date=HOJE).is_empty()

    def test_renda_semanal_ou_irregular_nao_entra(self):
        """Cadência fora da janela mensal (25–35 dias) não vira promessa."""
        linhas = [
            {"transaction_date": HOJE - timedelta(days=d), "amount": 500.0,
             "description": "FREELA CLIENTE", "balance": 1.0, "account_id": "a"}
            for d in (21, 14, 7)
        ]
        df = pl.DataFrame(linhas).with_columns(pl.col("transaction_date").cast(pl.Date))

        assert detect_income_events(df, reference_date=HOJE).is_empty()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. O BUG SILENCIOSO: TIPO DE DATA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestRobustezDeData:

    @pytest.mark.parametrize("dtype", ["date", "datetime"])
    def test_projecao_aplica_eventos_em_qualquer_dtype(self, dtype):
        """
        Com `transaction_date` em Datetime (o que o ETL produz), as chaves
        do calendário nunca casavam com as dos eventos: a projeção saía em
        linha reta, sem erro nenhum, e o safe-to-spend virava saldo − 200.
        Só não explodiu em produção porque o NexaRunner castava para Date.
        """
        df = _extrato_clt(meses=1)
        if dtype == "datetime":
            df = df.with_columns(pl.col("transaction_date").cast(pl.Datetime))

        projecao = CashflowProjector().project(
            df, _obrigacoes([5, 12], valor=-700.0), current_balance=5000.0, include_income=False
        )

        aplicados = sum(1 for eventos in projecao["events"].to_list() for _ in eventos)
        assert aplicados == 2, f"{dtype}: eventos não foram aplicados"
        assert projecao["projected_balance"][-1] == pytest.approx(3600.0)

    def test_evento_fora_da_janela_e_ignorado_sem_quebrar(self):
        df = _extrato_clt(meses=1)
        projecao = CashflowProjector().project(
            df, _obrigacoes([5, 90]), current_balance=5000.0, include_income=False
        )

        aplicados = sum(1 for eventos in projecao["events"].to_list() for _ in eventos)
        assert aplicados == 1, "o evento de 90 dias está fora do horizonte de 30"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. ÂNCORA TEMPORAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestAncoraTemporal:

    def test_extrato_defasado_nao_projeta_o_passado(self):
        """
        Lag do Open Finance é normal. Ancorando na última transação, os
        primeiros dias da "projeção de 30 dias" caíam em datas já vividas.
        """
        df = _extrato_clt(meses=1)
        df = df.filter(pl.col("transaction_date") <= HOJE - timedelta(days=6))

        projecao = CashflowProjector().project(df, _obrigacoes([]), current_balance=1000.0)

        primeiro_dia = projecao["date"][0]
        assert primeiro_dia > HOJE, "projeção não pode começar no passado"
        assert projecao.height == 30, "e continua entregando 30 dias úteis de futuro"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. ORQUESTRADOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestCashflowEngine:

    def test_engine_documentado_roda_ponta_a_ponta(self):
        """`get_summary()` era chamado e não existia: AttributeError sempre."""
        df = _extrato_clt()
        resultado = CashflowEngine().analyze(
            transactions_df=df,
            shadow_invoices_df=_obrigacoes([4, 11], valor=-900.0),
            monthly_income=SALARIO,
            include_daily_data=False,
        )

        resumo = resultado["projection"]["summary"]
        assert resumo["horizon_days"] == 30
        assert resumo["starting_balance"] == pytest.approx(SALDO_HOJE)
        assert resumo["total_shadow_impact"] < 0, "obrigações somam negativo"
        assert resumo["total_income_impact"] > 0, "salário entra no resumo"
        assert resultado["safe_to_spend"]["safe_to_spend_total"] >= 0
        assert resultado["risk_assessment"]["overall_risk"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

    def test_engine_aceita_ultima_transacao_sem_saldo(self):
        """Cartão de crédito não manda saldo — antes era TypeError."""
        df = _extrato_clt(meses=1)
        linhas = df.to_dicts()
        linhas[-1]["balance"] = None
        df_com_lacuna = pl.DataFrame(linhas).with_columns(
            pl.col("transaction_date").cast(pl.Date)
        )

        resultado = CashflowEngine().analyze(
            transactions_df=df_com_lacuna,
            shadow_invoices_df=_obrigacoes([5]),
            include_daily_data=False,
        )
        assert resultado["projection"]["summary"]["starting_balance"] > 0

    def test_negative_day_aponta_quando_o_aperto_comeca(self):
        """A UI promete explicar 'seu aperto começa no dia N'."""
        df = _extrato_clt(meses=1, com_salario=False)
        projector = CashflowProjector()
        projecao = projector.project(
            df, _obrigacoes([2], valor=-5000.0), current_balance=1000.0, include_income=False
        )
        resumo = projector.get_summary(projecao, starting_balance=1000.0)

        # O dia 1 da projeção é AMANHÃ (a janela começa em start_date + 1),
        # então um evento em D+2 cai no segundo dia projetado.
        assert resumo.negative_day == 2
        assert resumo.worst_balance == pytest.approx(-4000.0)
        assert resumo.risk_level == "CRITICAL", "negativo na primeira semana é crítico"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. SAFE-TO-SPEND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestSafeToSpend:

    def test_buffer_dimensionado_sobre_obrigacoes_e_nao_sobre_a_renda(self):
        """
        Com renda na projeção, somar tudo na coluna `expenses` fazia o
        colchão de segurança CRESCER junto com o salário — o contrário do
        que ele significa.
        """
        df = _extrato_clt()
        projecao = CashflowProjector().project(
            df, _obrigacoes([5, 10], valor=-1000.0), current_balance=SALDO_HOJE
        )

        despesas = float(projecao["expenses"].sum())
        receitas = float(projecao["income"].sum())

        assert despesas == pytest.approx(-2000.0), "só as obrigações"
        assert receitas > 0, "renda fica em coluna própria"

        resultado = SafeToSpendCalculator().calculate(projecao, horizon_days=30)
        # buffer = max(15% de 2000, 200) = 300
        assert resultado.safe_to_spend_total == pytest.approx(
            max(0.0, float(projecao["projected_balance"].min()) - 300.0)
        )

    def test_margem_usa_o_vale_e_nao_o_saldo_final(self):
        """
        Promessa do produto: "você não fica negativo em NENHUM dia" — não
        "você termina o mês positivo".
        """
        df = _extrato_clt(meses=1, com_salario=False)
        obrigacoes = pl.DataFrame({
            "type": ["SUBSCRIPTION", "INCOME_FAKE"],
            "amount": [-4000.0, 3500.0],
            "next_due_date": [HOJE + timedelta(days=5), HOJE + timedelta(days=20)],
            "merchant": ["aperto", "reembolso"],
        })

        projecao = CashflowProjector().project(
            df, obrigacoes, current_balance=5000.0, include_income=False
        )
        resultado = SafeToSpendCalculator().calculate(projecao, horizon_days=30)

        assert projecao["projected_balance"][-1] == pytest.approx(4500.0)
        assert resultado.min_projected_balance == pytest.approx(1000.0)
        assert resultado.safe_to_spend_total < 1000.0, "margem sai do vale, não do fim"
