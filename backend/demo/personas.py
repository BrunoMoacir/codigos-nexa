"""
demo/personas.py — Personas realistas do mercado brasileiro.

Cada persona gera ~6 meses de transações no formato BRUTO da Pluggy
(mesmos campos que o webhook real entrega: id, accountId, description,
amount, transaction_date). Esses dicts entram no ETL REAL — nada é
pré-classificado. As personas são desenhadas para ACENDER a inteligência:
cada uma dispara um conjunto diferente de cards no feed e de respostas do
agente.

  ANA    — CLT foodie: renda estável, delivery pesado, tarifa bancária,
           poupança parada (idle money + sub-CDI), assinatura que subiu.
  BRUNO  — MEI: recebe via maquininha, mistura PF/PJ, paga DAS, tem
           dinheiro parado (dispara PF/PJ classifier + fiscal + OPP).
  CARLA  — estresse financeiro: renda caindo, rotativo com juros altos,
           gasto comprometido (dispara FSS crítico, juros abusivos D3).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone


@dataclass
class Persona:
    user_id: str
    full_name: str
    email: str
    plan: str                       # free | pro | total
    institution: str                # nubank | itau | inter | bradesco
    monthly_income: float
    expected_cluster: str           # o que o profiler DEVE detectar
    goals: list[dict] = field(default_factory=list)
    _gen: object = None             # função geradora de transações


# ── utilidades de geração ────────────────────────────────────────────────

_MONTHS_BACK = 6


def _iso(d: date, hour: int = 10) -> str:
    return datetime(d.year, d.month, d.day, hour, tzinfo=timezone.utc).isoformat()


def _month_starts(n: int = _MONTHS_BACK) -> list[date]:
    """Primeiros dias dos últimos n meses (mais antigo → mais recente)."""
    today = date.today()
    starts = []
    y, m = today.year, today.month
    for _ in range(n):
        starts.append(date(y, m, 1))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return list(reversed(starts))


def _tx(txns: list, acc: str, d: date, desc: str, amount: float, hour: int = 10):
    txns.append({
        "id": f"{acc}-{d.isoformat()}-{len(txns)}-{random.randint(1000, 9999)}",
        "accountId": acc,
        "transaction_date": _iso(d, hour),
        "description": desc,
        "amount": round(amount, 2),
    })


def _day(base: date, day: int) -> date:
    """Dia seguro dentro do mês de `base`."""
    import calendar

    last = calendar.monthrange(base.year, base.month)[1]
    return base.replace(day=min(day, last))


# ── ANA — CLT foodie ─────────────────────────────────────────────────────

def _gen_ana(acc: str) -> list[dict]:
    random.seed(101)
    txns: list = []
    for i, start in enumerate(_month_starts()):
        _tx(txns, acc, _day(start, 5), "PIX RECEBIDO SALARIO EMPRESA ACME LTDA", 6500.00, 8)
        _tx(txns, acc, _day(start, 10), "ALUGUEL APARTAMENTO IMOBILIARIA", -2100.00)
        _tx(txns, acc, _day(start, 10), "TARIFA PACOTE SERVICOS", -34.90)   # tarifa → D2/D4/raio-x
        _tx(txns, acc, _day(start, 12), "CONDOMINIO EDIFICIO", -680.00)
        _tx(txns, acc, _day(start, 8), "ENEL DISTRIBUICAO ENERGIA", -180.00)
        # streaming que SOBE de preço no 4º mês (subscription increase)
        netflix = 39.90 if i < 3 else 55.90
        _tx(txns, acc, _day(start, 15), "NETFLIX.COM", -netflix)
        _tx(txns, acc, _day(start, 15), "SPOTIFY", -21.90)
        # delivery/restaurante pesado (foodie): alta frequência + variedade de
        # merchants (diversidade) + tickets altos → dominante nos gastos livres
        _merchants = [
            "IFOOD *PEDIDO", "RAPPI *RESTAURANTE", "UBER EATS", "IFOOD *SUSHI",
            "AIQFOME *PEDIDO", "RESTAURANTE FASANO", "OUTBACK STEAKHOUSE",
            "IFOOD *HAMBURGUERIA", "STARBUCKS", "RAPPI *PADARIA",
        ]
        for j, dd in enumerate((3, 6, 8, 11, 13, 16, 19, 21, 24, 27)):
            _tx(txns, acc, _day(start, dd), _merchants[j % len(_merchants)],
                -random.uniform(55, 145))
        _tx(txns, acc, _day(start, 18), "SUPERMERCADO PAO DE ACUCAR", -random.uniform(220, 300))
        _tx(txns, acc, _day(start, 22), "UBER *TRIP", -random.uniform(18, 45))
        _tx(txns, acc, _day(start, 25), "DROGARIA SAO PAULO", -random.uniform(40, 120))
    # anomalia recente: uma compra muito acima do padrão no último mês
    last = _month_starts()[-1]
    _tx(txns, acc, _day(last, 24), "MAGAZINE LUIZA ELETRO", -3890.00)
    # deixa sobrar caixa acumulado parado (idle money): renda > gastos
    return txns


# ── BRUNO — MEI ──────────────────────────────────────────────────────────

def _gen_bruno(acc: str) -> list[dict]:
    random.seed(202)
    txns: list = []
    # renda de MEI é INSTÁVEL: meses cheios e meses fracos (sinal unstable_income)
    month_scales = [1.4, 0.5, 1.2, 0.4, 1.5, 0.6]
    for start, scale in zip(_month_starts(), month_scales):
        # recebimentos via maquininha (PJ) — volume varia muito mês a mês
        n_receipts = int(8 * scale)
        for k in range(max(n_receipts, 2)):
            dd = 2 + (k * 26 // max(n_receipts, 1))
            _tx(txns, acc, _day(start, dd), random.choice(
                ["PAGSEGURO *VENDAS", "STONE *RECEBIMENTO", "MERCADO PAGO VENDA",
                 "PIX RECEBIDO CLIENTE PJ", "GETNET *VENDA"]
            ), random.uniform(180, 700) * scale)
        _tx(txns, acc, _day(start, 20), "DAS SIMEI PAGAMENTO GUIA", -76.90)   # fiscal MEI
        # insumos PJ (misturados na mesma conta)
        _tx(txns, acc, _day(start, 6), "ATACADAO DISTRIBUICAO", -random.uniform(400, 900))
        _tx(txns, acc, _day(start, 16), "FORNECEDOR EMBALAGENS LTDA", -random.uniform(150, 350))
        # gastos PF (moderados — não devem dominar o perfil)
        _tx(txns, acc, _day(start, 10), "ALUGUEL RESIDENCIAL", -1400.00)
        _tx(txns, acc, _day(start, 12), "SUPERMERCADO EXTRA", -random.uniform(300, 420))
        _tx(txns, acc, _day(start, 15), "POSTO IPIRANGA COMBUSTIVEL", -random.uniform(150, 260))
        _tx(txns, acc, _day(start, 18), "ESCOLA INFANTIL MENSALIDADE", -720.00)
        _tx(txns, acc, _day(start, 22), "FARMACIA PACHECO", -random.uniform(50, 130))
    return txns


# ── CARLA — estresse financeiro ──────────────────────────────────────────

def _gen_carla(acc: str) -> list[dict]:
    random.seed(303)
    txns: list = []
    months = _month_starts()
    for i, start in enumerate(months):
        # renda caindo ao longo do tempo (income_drop)
        income = 4200.00 - i * 180.00
        _tx(txns, acc, _day(start, 5), "PIX RECEBIDO PAGAMENTO CLIENTE", income, 8)
        _tx(txns, acc, _day(start, 10), "ALUGUEL KITNET", -1500.00)
        _tx(txns, acc, _day(start, 8), "CLARO MOVEL FATURA", -89.90)
        _tx(txns, acc, _day(start, 11), "ENERGIA ELETRICA", -210.00)
        _tx(txns, acc, _day(start, 12), "SUPERMERCADO DIA", -random.uniform(400, 600))
        # juros de rotativo / cheque especial ABUSIVOS (D3) — crescendo
        _tx(txns, acc, _day(start, 14), "JUROS ROTATIVO CARTAO", -(120 + i * 40))
        _tx(txns, acc, _day(start, 14), "ENCARGOS CHEQUE ESPECIAL", -(80 + i * 25))
        _tx(txns, acc, _day(start, 16), "TARIFA MANUTENCAO CONTA", -29.90)
        _tx(txns, acc, _day(start, 20), "FARMACIA POPULAR", -random.uniform(60, 140))
        _tx(txns, acc, _day(start, 25), "CARTAO CREDITO PAGAMENTO MINIMO", -random.uniform(300, 500))
    return txns


# ── registro ─────────────────────────────────────────────────────────────

PERSONAS: dict[str, Persona] = {
    "ana": Persona(
        user_id="demo-ana",
        full_name="Ana Souza",
        email="ana.demo@nexa.test",
        plan="total",
        institution="nubank",
        monthly_income=6500.0,
        expected_cluster="URBANO_FOODIE",
        goals=[
            {"name": "Reserva de emergência", "target": 30000, "current": 8500, "type": "outros"},
            {"name": "Viagem Europa 2027", "target": 18000, "current": 3200, "type": "viagem"},
        ],
        _gen=_gen_ana,
    ),
    "bruno": Persona(
        user_id="demo-bruno",
        full_name="Bruno Lima (MEI)",
        email="bruno.demo@nexa.test",
        plan="pro",
        institution="inter",
        monthly_income=3800.0,
        expected_cluster="MICROEMPREENDEDOR",
        goals=[
            {"name": "Capital de giro", "target": 15000, "current": 4000, "type": "outros"},
        ],
        _gen=_gen_bruno,
    ),
    "carla": Persona(
        user_id="demo-carla",
        full_name="Carla Mendes",
        email="carla.demo@nexa.test",
        plan="free",
        institution="bradesco",
        monthly_income=3600.0,
        expected_cluster="ESTRESSE_FINANCEIRO",
        goals=[
            {"name": "Sair do vermelho", "target": 5000, "current": 200, "type": "outros"},
        ],
        _gen=_gen_carla,
    ),
}


def generate_raw_transactions(persona: Persona) -> list[dict]:
    """Transações brutas estilo Pluggy para a persona (entram no ETL real).

    Remove lançamentos com data futura: o mês corrente fica PARCIAL (só até
    hoje), como seria em produção — sem isso o burn rate trata o mês inteiro
    como consumido e inunda o feed com cards CRITICAL artificiais."""
    acc = f"acc-{persona.user_id}"
    today = date.today()
    raw = persona._gen(acc)
    return [
        t for t in raw
        if datetime.fromisoformat(t["transaction_date"]).date() <= today
    ]


__all__ = ["Persona", "PERSONAS", "generate_raw_transactions"]
