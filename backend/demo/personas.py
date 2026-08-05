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
class BankAccount:
    """Uma conta dentro de um banco conectado."""
    type: str                       # CHECKING | SAVINGS | INVESTMENT | CREDIT
    balance: float


@dataclass
class ConnectedBank:
    """Um banco conectado via Open Finance, com suas contas."""
    institution: str                # nubank | itau | inter | bradesco | caixa | pagbank
    name: str                       # nome de exibição
    role: str                       # primary | spending | investment | savings | business
    accounts: list[BankAccount] = field(default_factory=list)


@dataclass
class Persona:
    user_id: str
    full_name: str
    email: str
    plan: str                       # free | pro | total
    monthly_income: float
    expected_cluster: str           # o que o profiler DEVE detectar
    banks: list[ConnectedBank] = field(default_factory=list)  # múltiplos bancos!
    goals: list[dict] = field(default_factory=list)
    _gen: object = None             # gerador do fluxo principal (banco primário)

    @property
    def institution(self) -> str:
        """Banco primário — retrocompat com serviços que usam persona.institution."""
        return self.banks[0].institution if self.banks else "nubank"

    def bank_by_role(self, role: str) -> ConnectedBank | None:
        return next((b for b in self.banks if b.role == role), None)


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


# ── fluxos SECUNDÁRIOS (outros bancos conectados) ────────────────────────
#
# Além do banco primário (fluxo principal do dia a dia), o brasileiro típico
# tem conta em banco digital para gastar, corretora/banco para investir e às
# vezes poupança em outro. Cada um vira uma conexão Open Finance com seu
# próprio extrato. Estes geradores criam o extrato realista de cada papel.

def _gen_investment_stream(acc: str, monthly_amount: float, seed: int) -> list[dict]:
    """Banco de investimentos: aporte mensal + rendimento creditado."""
    random.seed(seed)
    txns: list = []
    for start in _month_starts():
        _tx(txns, acc, _day(start, 6), "APLICACAO CDB LIQUIDEZ DIARIA", -monthly_amount, 9)
        _tx(txns, acc, _day(start, 28), "RENDIMENTO CDB CREDITO", monthly_amount * 0.011, 9)
    return txns


def _gen_savings_stream(acc: str, monthly_amount: float, seed: int) -> list[dict]:
    """Poupança: depósito mensal + rendimento da poupança."""
    random.seed(seed)
    txns: list = []
    for start in _month_starts():
        _tx(txns, acc, _day(start, 7), "DEPOSITO POUPANCA", -monthly_amount, 9)
        _tx(txns, acc, _day(start, 30), "RENDIMENTO POUPANCA", monthly_amount * 0.005, 9)
    return txns


def _gen_second_card_stream(acc: str, seed: int, merchants: list[str], lo: float, hi: float) -> list[dict]:
    """Cartão em outro banco: compras discricionárias."""
    random.seed(seed)
    txns: list = []
    for start in _month_starts():
        for j, dd in enumerate((4, 12, 19, 26)):
            _tx(txns, acc, _day(start, dd), merchants[j % len(merchants)],
                -random.uniform(lo, hi))
    return txns


# ── registro (agora com MÚLTIPLOS bancos conectados por pessoa) ───────────

def _acc(institution: str, acc_type: str) -> str:
    return f"acc-{institution}-{acc_type.lower()}"


PERSONAS: dict[str, Persona] = {
    "ana": Persona(
        user_id="demo-ana",
        full_name="Ana Souza",
        email="ana.demo@nexa.test",
        plan="total",
        monthly_income=6500.0,
        expected_cluster="URBANO_FOODIE",
        banks=[
            ConnectedBank("nubank", "Nubank", "primary", [
                BankAccount("CHECKING", 3200.0), BankAccount("CREDIT", -2840.0)]),
            ConnectedBank("itau", "Itaú", "investment", [
                BankAccount("INVESTMENT", 18700.0)]),
            ConnectedBank("inter", "Banco Inter", "savings", [
                BankAccount("SAVINGS", 12500.0)]),
        ],
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
        monthly_income=3800.0,
        expected_cluster="MICROEMPREENDEDOR",
        banks=[
            ConnectedBank("inter", "Banco Inter", "primary", [
                BankAccount("CHECKING", 1850.0), BankAccount("CREDIT", -1120.0)]),
            ConnectedBank("nubank", "Nubank", "spending", [
                BankAccount("CHECKING", 620.0)]),
            ConnectedBank("pagbank", "PagBank", "business", [
                BankAccount("CHECKING", 4200.0)]),
        ],
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
        monthly_income=3600.0,
        expected_cluster="ESTRESSE_FINANCEIRO",
        banks=[
            ConnectedBank("bradesco", "Bradesco", "primary", [
                BankAccount("CHECKING", 180.0), BankAccount("CREDIT", -3450.0)]),
            ConnectedBank("caixa", "Caixa Econômica", "savings", [
                BankAccount("SAVINGS", 640.0)]),
        ],
        goals=[
            {"name": "Sair do vermelho", "target": 5000, "current": 200, "type": "outros"},
        ],
        _gen=_gen_carla,
    ),
}


# Fluxos secundários por persona/role (extrato realista de cada banco extra)
def _secondary_streams(persona: Persona) -> dict[str, list[dict]]:
    """{institution: [raw_txns]} para os bancos NÃO-primários da persona.

    Contas de INVESTIMENTO e POUPANÇA são balance-only (aparecem com saldo,
    mas não geram extrato diário — como na vida real; o aporte foi uma
    transferência pontual). Só contas de GASTO e de NEGÓCIO geram extrato,
    para não distorcer o perfil comportamental com saídas que o profiler
    leria como gasto comprometido.
    """
    out: dict[str, list[dict]] = {}
    for bank in persona.banks[1:]:  # pula o primário
        acc = _acc(bank.institution, bank.accounts[0].type)
        seed = abs(hash(persona.user_id + bank.institution)) % 100000
        if bank.role == "spending":
            out[bank.institution] = _gen_second_card_stream(
                acc, seed, ["MERCADO LIVRE", "SHOPEE *COMPRA", "AMAZON BR", "POSTO SHELL"],
                40, 180)
        elif bank.role == "business":
            # PagBank do MEI: recebimentos da maquininha (PJ)
            random.seed(seed)
            txns: list = []
            for start in _month_starts():
                for dd in (5, 15, 25):
                    _tx(txns, acc, _day(start, dd), "PAGBANK *VENDA MAQUININHA",
                        random.uniform(200, 600))
            out[bank.institution] = txns
        # investment / savings → sem transações (só saldo via seed_full)
    return out


def generate_raw_transactions(persona: Persona) -> dict[str, list[dict]]:
    """
    Transações brutas estilo Pluggy AGRUPADAS POR BANCO conectado:
        {institution: [raw_txns]}
    O banco primário recebe o fluxo principal (comportamento da persona);
    os demais recebem seus extratos secundários. Cada grupo entra no ETL
    com o seu institution_id (BankStrategy por banco), como em produção.

    Datas futuras são removidas (mês corrente parcial, como no real).
    """
    today = date.today()
    primary = persona.banks[0]
    primary_acc = _acc(primary.institution, "checking")

    grouped: dict[str, list[dict]] = {primary.institution: persona._gen(primary_acc)}
    for inst, txns in _secondary_streams(persona).items():
        grouped.setdefault(inst, []).extend(txns)

    # filtra datas futuras em cada banco
    return {
        inst: [t for t in txns
               if datetime.fromisoformat(t["transaction_date"]).date() <= today]
        for inst, txns in grouped.items()
    }


__all__ = [
    "Persona", "ConnectedBank", "BankAccount", "PERSONAS",
    "generate_raw_transactions",
]
