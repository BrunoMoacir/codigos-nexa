"""
app/seasonality/fiscal_calendar.py — Calendário fiscal brasileiro (R2.c)

Funções puras (sem I/O) que, dada uma data de referência, retornam os
eventos fiscais cuja janela de alerta está ativa. A personalização
(valores estimados, aplicabilidade MEI/CLT) acontece no service — aqui
só existe o calendário em si, o que mantém as regras de datas 100%
testáveis sem banco.

Eventos cobertos:
  IR_DECLARACAO      01/03 – 31/05   entrega da declaração anual (DIRPF)
  IR_RESTITUICAO     5 lotes mai–set pagamento da restituição
  IPVA_IPTU          02/01 – 28/02   impostos de início de ano
  DAS_MEI            dia 13 – 20     guia mensal do MEI
  DASN_SIMEI         01/01 – 31/05   declaração anual do MEI
  DECIMO_PRIMEIRA    01/11 – 30/11   1ª parcela do 13º (depósito até 30/11)
  DECIMO_SEGUNDA     01/12 – 20/12   2ª parcela do 13º (depósito até 20/12)
  FGTS_LUCRO         15/07 – 31/08   distribuição do lucro do FGTS

As datas de deadline que caem em fim de semana não são ajustadas aqui —
a mensagem fala em "até DD/MM", que é como o usuário conhece a regra.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


# Aplicabilidade — decide qual sinal de perfil ativa o evento no service.
#   "all"  → todo usuário
#   "mei"  → apenas usuários com sinal de MEI/PJ
#   "clt"  → apenas usuários com salário recorrente detectado
Audience = str  # "all" | "mei" | "clt"


@dataclass
class CalendarEvent:
    """Um evento fiscal com janela de alerta ativa."""
    event_code: str
    name: str
    description: str
    action_hint: str
    window_start: date
    window_end: date
    deadline: date
    audience: Audience = "all"
    is_obligation: bool = False      # True = prazo legal (multa se perder)
    metadata: dict = field(default_factory=dict)

    def days_until_deadline(self, today: date) -> int:
        return (self.deadline - today).days


def _within(today: date, start: date, end: date) -> bool:
    return start <= today <= end


# ── Lotes de restituição do IR (calendário padrão da Receita) ────────
# Último dia útil de cada mês, maio a setembro. Aproximamos pelo último
# dia do mês — o alerta fala "no fim de <mês>", sem prometer dia exato.

_RESTITUICAO_MONTHS = (5, 6, 7, 8, 9)


def _last_day_of_month(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def active_events(today: date) -> list[CalendarEvent]:
    """
    Retorna os eventos fiscais cuja janela de alerta contém `today`.
    Ordenados por deadline crescente (mais urgente primeiro).
    """
    year = today.year
    events: list[CalendarEvent] = []

    # ── IR — declaração anual ─────────────────────────────────────────
    ir_start, ir_end = date(year, 3, 1), date(year, 5, 31)
    if _within(today, ir_start, ir_end):
        events.append(CalendarEvent(
            event_code="IR_DECLARACAO",
            name=f"Declaração do IR {year}",
            description=(
                f"O prazo de entrega da declaração do Imposto de Renda {year} "
                f"vai até 31/05. Quem entrega no início da janela recebe a "
                f"restituição nos primeiros lotes."
            ),
            action_hint=(
                "Separe os informes de rendimento dos seus bancos e corretoras. "
                "Entregar cedo = restituição mais cedo."
            ),
            window_start=ir_start,
            window_end=ir_end,
            deadline=ir_end,
            audience="all",
            is_obligation=True,
        ))

    # ── IR — lotes de restituição ─────────────────────────────────────
    for month in _RESTITUICAO_MONTHS:
        lot_day = _last_day_of_month(year, month)
        window_start = lot_day.replace(day=max(1, lot_day.day - 10))
        if _within(today, window_start, lot_day):
            lot_index = _RESTITUICAO_MONTHS.index(month) + 1
            events.append(CalendarEvent(
                event_code="IR_RESTITUICAO",
                name=f"{lot_index}º lote da restituição do IR",
                description=(
                    f"O {lot_index}º lote da restituição do IR cai no fim de "
                    f"{lot_day.strftime('%m/%Y')}. Restituição parada em conta "
                    f"corrente perde para a inflação todos os dias."
                ),
                action_hint=(
                    "Se receber, não deixe o dinheiro parado: o Radar de "
                    "Oportunidades compara CDB, LCI e Tesouro pelo retorno líquido."
                ),
                window_start=window_start,
                window_end=lot_day,
                deadline=lot_day,
                audience="all",
                is_obligation=False,
                metadata={"lot_index": lot_index},
            ))
            break   # no máximo um lote ativo por vez

    # ── IPVA / IPTU ───────────────────────────────────────────────────
    ipva_start, ipva_end = date(year, 1, 2), date(year, 2, 28)
    if _within(today, ipva_start, ipva_end):
        events.append(CalendarEvent(
            event_code="IPVA_IPTU",
            name="IPVA e IPTU do início do ano",
            description=(
                "Janeiro e fevereiro concentram IPVA, IPTU e matrícula escolar. "
                "Pagar o IPVA/IPTU à vista costuma dar 3–10% de desconto, "
                "dependendo do estado e do município."
            ),
            action_hint=(
                "Se tiver caixa, avalie o pagamento à vista com desconto — "
                "compare o desconto com o rendimento do CDI no mesmo período."
            ),
            window_start=ipva_start,
            window_end=ipva_end,
            deadline=ipva_end,
            audience="all",
            is_obligation=True,
        ))

    # ── DAS mensal (MEI) ──────────────────────────────────────────────
    das_deadline = date(year, today.month, 20)
    das_window_start = date(year, today.month, 13)
    if _within(today, das_window_start, das_deadline):
        events.append(CalendarEvent(
            event_code="DAS_MEI",
            name=f"DAS do MEI vence dia 20/{today.month:02d}",
            description=(
                f"A guia mensal do Simples Nacional (DAS) vence em "
                f"20/{today.month:02d}. Atraso gera multa de 0,33% ao dia "
                f"mais juros SELIC."
            ),
            action_hint="Emita a guia no app MEI ou no PGMEI e programe o pagamento.",
            window_start=das_window_start,
            window_end=das_deadline,
            deadline=das_deadline,
            audience="mei",
            is_obligation=True,
        ))

    # ── DASN-SIMEI (declaração anual do MEI) ──────────────────────────
    dasn_start, dasn_end = date(year, 1, 1), date(year, 5, 31)
    if _within(today, dasn_start, dasn_end):
        events.append(CalendarEvent(
            event_code="DASN_SIMEI",
            name=f"Declaração anual do MEI (DASN-SIMEI {year})",
            description=(
                f"A DASN-SIMEI de {year - 1} deve ser entregue até 31/05/{year}. "
                f"Sem ela o CNPJ fica inadimplente e pode ser cancelado."
            ),
            action_hint=(
                "Some o faturamento do ano anterior (o Relatório Fiscal PJ do "
                "Nexa já faz isso) e entregue no portal do Simples Nacional."
            ),
            window_start=dasn_start,
            window_end=dasn_end,
            deadline=dasn_end,
            audience="mei",
            is_obligation=True,
        ))

    # ── 13º salário ───────────────────────────────────────────────────
    dec1_start, dec1_end = date(year, 11, 1), date(year, 11, 30)
    if _within(today, dec1_start, dec1_end):
        events.append(CalendarEvent(
            event_code="DECIMO_PRIMEIRA",
            name="1ª parcela do 13º salário",
            description=(
                "A 1ª parcela do 13º deve ser depositada até 30/11. "
                "É a maior injeção de caixa do ano para quem é CLT — "
                "e o dinheiro que os bancos mais tentam capturar com ofertas ruins."
            ),
            action_hint=(
                "Defina o destino antes de o dinheiro cair: quitar dívida cara "
                "primeiro, depois reserva de emergência, depois investir."
            ),
            window_start=dec1_start,
            window_end=dec1_end,
            deadline=dec1_end,
            audience="clt",
            is_obligation=False,
            metadata={"parcela": 1},
        ))

    dec2_start, dec2_end = date(year, 12, 1), date(year, 12, 20)
    if _within(today, dec2_start, dec2_end):
        events.append(CalendarEvent(
            event_code="DECIMO_SEGUNDA",
            name="2ª parcela do 13º salário",
            description=(
                "A 2ª parcela do 13º deve ser depositada até 20/12 "
                "(com desconto de IR e INSS). Dezembro também concentra "
                "gastos de fim de ano — planeje antes de gastar."
            ),
            action_hint=(
                "Reserve agora o valor do IPVA/IPTU de janeiro: eles chegam "
                "em 30 dias e o 13º é a melhor fonte para pagá-los à vista."
            ),
            window_start=dec2_start,
            window_end=dec2_end,
            deadline=dec2_end,
            audience="clt",
            is_obligation=False,
            metadata={"parcela": 2},
        ))

    # ── Lucro do FGTS ─────────────────────────────────────────────────
    fgts_start, fgts_end = date(year, 7, 15), date(year, 8, 31)
    if _within(today, fgts_start, fgts_end):
        events.append(CalendarEvent(
            event_code="FGTS_LUCRO",
            name="Distribuição do lucro do FGTS",
            description=(
                "A Caixa distribui o lucro do FGTS até 31/08. O crédito é "
                "proporcional ao saldo em 31/12 do ano anterior e cai direto "
                "na conta do FGTS."
            ),
            action_hint=(
                "Confira o crédito no app FGTS. Aproveite para revisar se você "
                "tem contas inativas com saldo esquecido — o Monitor de Direitos "
                "do Nexa verifica isso."
            ),
            window_start=fgts_start,
            window_end=fgts_end,
            deadline=fgts_end,
            audience="all",
            is_obligation=False,
        ))

    events.sort(key=lambda e: e.deadline)
    return events


__all__ = ["CalendarEvent", "active_events"]
