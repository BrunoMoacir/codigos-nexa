# backend/app/cashflow/projector.py

"""
Projetor de Fluxo de Caixa - MOTOR EVENT-DRIVEN DA NEXA

RESPONSABILIDADE:
    Simular o fluxo financeiro diário futuro do usuário a partir de eventos financeiros explícitos.

PRINCÍPIO:
    Nenhum saldo é projetado sem um evento financeiro que o justifique.

O projector não trabalha apenas com valores,
ele constrói uma LINHA DO TEMPO FINANCEIRA EXPLICÁVEL.

Cada dia futuro contém:
    - Saldo projetado
    - Lista de eventos financeiros causadores
    - Flag de risco

Isso permite:
    - Auditoria
    - Explicabilidade
    - Narrativa financeira
    - Agentes inteligentes
"""

import logging
import polars as pl
from datetime import date as _date, datetime as _datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Optional, Literal, List, Dict, Any

from app.forecast.cashflow.income_events import detect_income_events

logger = logging.getLogger(__name__)


RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def _to_date(valor: Any) -> Optional[_date]:
    """
    datetime/date/string → date.

    Existe porque o pipeline entrega `transaction_date` em Datetime (ETL,
    com timezone) e `date` (banco/DuckDB). Comparar os dois tipos como
    chave de dicionário falha em silêncio — a projeção saía plana.
    """
    if valor is None:
        return None
    if isinstance(valor, _datetime):
        return valor.date()
    if isinstance(valor, _date):
        return valor
    try:
        return _datetime.fromisoformat(str(valor)[:19]).date()
    except (TypeError, ValueError):
        return None


def _vazio_eventos() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "type": pl.Utf8,
            "amount": pl.Float64,
            "next_due_date": pl.Date,
            "merchant": pl.Utf8,
            "origin": pl.Utf8,
        }
    )


@dataclass
class ProjectionSummary:
    """
    Resumo agregado da projeção de cashflow.

    Esse resumo alimenta:
        - Safe-to-Spend
        - Alertas
        - Agente cognitivo
        - UI resumida

    Ele representa uma compressão informacional
    de toda a linha do tempo projetada.
    """
    
    horizon_days: int
    starting_balance: float
    ending_balance: float
    worst_balance: float
    negative_day: Optional[int]
    risk_level: RiskLevel
    total_shadow_impact: float
    total_income_impact: float = 0.0

    def to_dict(self) -> dict:
        """Serialização para a API (o engine e os schemas já esperavam isto)."""
        return asdict(self)


class CashflowProjector:
    """
    Motor de simulação financeira diária.

    Ele executa uma simulação determinística do futuro financeiro
    aplicando eventos financeiros previstos sobre o saldo atual.

    Esse motor é:

        - determinístico
        - explicável
        - auditável
        - resiliente

    Nenhum cálculo é estatístico aqui.
    Tudo é baseado em eventos financeiros reais detectados.
    """
    
    def __init__(self, horizon_days: int = 30):
        self.horizon_days = horizon_days
        self.logger = logging.getLogger(__name__)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CORE SIMULATION ENGINE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def project(
        self,
        transactions_df: pl.DataFrame,
        shadow_invoices_df: pl.DataFrame,
        current_balance: Optional[float] = None,
        reference_date: Optional[_date] = None,
        include_income: bool = True,
    ) -> pl.DataFrame:
        """
        Executa a simulação financeira diária.

        Estratégia:
            1. Determinar saldo inicial confiável
            2. Construir calendário futuro
            3. Indexar eventos financeiros por data
            4. Simular dia a dia:
                   saldo[t+1] = saldo[t] + soma(eventos_do_dia)
            5. Persistir rastreabilidade de eventos

        Resultado:
            Uma linha do tempo financeira completamente explicável.
        """

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 1: Validações e preparação dos dados
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        if transactions_df.is_empty():
            raise ValueError("DataFrame de transações está vazio")

        if "transaction_date" not in transactions_df.columns:
            raise ValueError("transactions_df precisa conter 'transaction_date'")

        # Ordenar cronologicamente
        df_sorted = transactions_df.sort("transaction_date")

        # Determinar saldo inicial confiável
        if current_balance is not None:
            starting_balance = float(current_balance)
        else:
            if "balance" not in df_sorted.columns:
                raise ValueError(
                    "transactions_df não possui coluna 'balance' e current_balance não foi informado"
                )
            # Procura para trás o último saldo conhecido: em conta de cartão
            # a Pluggy não manda balance, e falhar na última linha derrubava
            # a projeção inteira por causa de uma lacuna pontual.
            _last_balance = next(
                (b for b in reversed(df_sorted["balance"].to_list()) if b is not None),
                None,
            )
            if _last_balance is None:
                raise ValueError(
                    "Nenhuma transação com 'balance' conhecido — informe current_balance explicitamente"
                )
            starting_balance = float(_last_balance)

        # Data base da projeção.
        #
        # Ancorar na última transação parece natural, mas com o lag normal do
        # Open Finance (dias) a "projeção de 30 dias" gastava os primeiros
        # dias projetando datas JÁ VIVIDAS. A âncora é o mais recente entre a
        # última transação e hoje.
        #
        # Normalizar para `date` aqui não é detalhe: o calendário era montado
        # com o dtype da coluna e os eventos indexados por `.dt.date()`. Com
        # transaction_date em Datetime as chaves nunca casavam e a projeção
        # saía numa LINHA RETA — sem erro, sem aviso, com safe-to-spend
        # inflado. Só funcionava porque o NexaRunner castava para Date antes.
        last_date = _to_date(df_sorted["transaction_date"].max())
        today = reference_date or _date.today()
        start_date = max(last_date, today)

        if start_date != last_date:
            self.logger.info(
                "Projeção ancorada em hoje (%s); última transação em %s (defasagem de %s dias)",
                today, last_date, (today - last_date).days,
            )

        self.logger.info(
            f"Inicializando projeção: saldo R$ {starting_balance:,.2f} em {start_date}"
        )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 2: Construir linha do tempo futura
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        calendar = [
            start_date + timedelta(days=i + 1)
            for i in range(self.horizon_days)
        ]

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 3: Indexar eventos financeiros por data
        #
        # Aqui transformamos:
        #   shadow_invoices_df
        #
        # Em:
        #   { date -> [eventos] }
        #
        # Isso permite lookup O(1) por dia
        # durante a simulação.
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        events_by_day: Dict[Any, List[Dict[str, Any]]] = {}

        # Renda entra como evento de crédito. É o projector que detecta (e não
        # o chamador que injeta) de propósito: os detectores de despesa
        # filtram `amount < 0`, então quem esquecesse de somar a renda
        # receberia uma projeção que só sabe descer — foi exatamente o que
        # acontecia, e o sintoma era "safe-to-spend R$ 0,00" para assalariado.
        income_df = _vazio_eventos()
        if include_income:
            try:
                income_df = detect_income_events(
                    transactions_df=df_sorted,
                    horizon_days=self.horizon_days,
                    reference_date=start_date,
                )
            except Exception as exc:
                self.logger.warning("Detecção de renda falhou — projetando só despesas: %s", exc)

        fontes = [("shadow_invoice", shadow_invoices_df), ("income_recurrence", income_df)]
        eventos_fora_da_janela = 0
        janela = {d for d in (start_date + timedelta(days=i + 1) for i in range(self.horizon_days))}

        for origem_padrao, fonte in fontes:
            if fonte is None or fonte.is_empty():
                continue
            if "next_due_date" not in fonte.columns:
                self.logger.warning("Fonte %s sem 'next_due_date' — ignorada", origem_padrao)
                continue

            for row in fonte.iter_rows(named=True):
                day = _to_date(row.get("next_due_date"))
                if day is None:
                    continue

                event = {
                    "type": row.get("type", "shadow"),
                    "merchant": row.get("merchant", "UNKNOWN"),
                    "amount": float(row.get("amount") or 0.0),
                    "origin": row.get("origin") or origem_padrao,
                }

                if day not in janela:
                    eventos_fora_da_janela += 1
                    continue

                events_by_day.setdefault(day, []).append(event)

        if eventos_fora_da_janela:
            # Visível de propósito: foi um silêncio deste tipo que escondeu a
            # projeção em linha reta.
            self.logger.info(
                "%s eventos fora da janela de %s dias — ignorados",
                eventos_fora_da_janela, self.horizon_days,
            )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 4: Simulação financeira diária (núcleo matemático)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        current_balance = starting_balance
        projection_rows = []

        for idx, day in enumerate(calendar, start=1):

            daily_events = events_by_day.get(day, [])

            # Despesa e receita SEPARADAS. O saldo usa a soma; `expenses`
            # continua sendo só o que sai, porque é sobre as obrigações que o
            # buffer do safe-to-spend é dimensionado — somar a renda aqui
            # faria o colchão de segurança crescer junto com o salário, que é
            # o contrário do que ele significa.
            daily_expenses = sum(e["amount"] for e in daily_events if e["amount"] < 0)
            daily_income = sum(e["amount"] for e in daily_events if e["amount"] > 0)
            daily_delta = daily_expenses + daily_income

            # Atualizar saldo
            current_balance += daily_delta

            projection_rows.append({
                "date": day,
                "starting_balance": starting_balance,
                "projected_balance": round(current_balance, 2),
                "events": daily_events,
                "expenses": daily_expenses,
                "income": daily_income,
                "net_delta": daily_delta,
                "risk_flag": "NEGATIVE_BALANCE" if current_balance < 0 else None
            })

        projection_df = pl.DataFrame(projection_rows)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # LOG FINAL
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        worst_balance = projection_df['projected_balance'].min() or 0.0
        self.logger.info(
            f"Projeção finalizada: "
            f"Saldo final R$ {current_balance:,.2f} | "
            f"Menor saldo R$ {worst_balance:,.2f}"
        )

        return projection_df

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # RESUMO DA PROJEÇÃO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def get_summary(
        self,
        projection_df: pl.DataFrame,
        starting_balance: float,
    ) -> ProjectionSummary:
        """
        Comprime a linha do tempo no resumo que alimenta API, alertas e agente.

        Estava sendo chamado pelo CashflowEngine e NÃO EXISTIA: toda chamada
        de `CashflowEngine.analyze()` morria com AttributeError — o
        orquestrador documentado como porta de entrada da feature nunca
        rodou. O dataclass ProjectionSummary já existia, órfão.
        """
        if projection_df.is_empty():
            return ProjectionSummary(
                horizon_days=self.horizon_days,
                starting_balance=float(starting_balance),
                ending_balance=float(starting_balance),
                worst_balance=float(starting_balance),
                negative_day=None,
                risk_level="LOW",
                total_shadow_impact=0.0,
                total_income_impact=0.0,
            )

        saldos = projection_df["projected_balance"]
        ending_balance = float(saldos[-1])
        worst_balance = float(saldos.min())

        # Primeiro dia (1-indexado) em que o saldo fica negativo — é o que a
        # UI usa para dizer "seu aperto começa no dia 17".
        negative_day = None
        for indice, saldo in enumerate(saldos.to_list(), start=1):
            if saldo is not None and saldo < 0:
                negative_day = indice
                break

        despesas, receitas = 0.0, 0.0
        if "events" in projection_df.columns:
            for eventos_do_dia in projection_df["events"].to_list():
                for evento in eventos_do_dia or []:
                    valor = float(evento.get("amount") or 0.0)
                    if valor < 0:
                        despesas += valor
                    else:
                        receitas += valor

        return ProjectionSummary(
            horizon_days=self.horizon_days,
            starting_balance=float(starting_balance),
            ending_balance=round(ending_balance, 2),
            worst_balance=round(worst_balance, 2),
            negative_day=negative_day,
            risk_level=self._classify_risk(worst_balance, negative_day),
            total_shadow_impact=round(despesas, 2),
            total_income_impact=round(receitas, 2),
        )

    @staticmethod
    def _classify_risk(worst_balance: float, negative_day: Optional[int]) -> RiskLevel:
        """
        Risco da PROJEÇÃO (não do safe-to-spend): o que manda é o vale, e
        quão cedo ele chega — ficar negativo no dia 3 é pior que no dia 28.
        """
        if worst_balance < 0:
            return "CRITICAL" if (negative_day or 99) <= 7 else "HIGH"
        if worst_balance < 200:
            return "MEDIUM"
        return "LOW"
