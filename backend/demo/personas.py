"""
demo/personas.py — Personas realistas do mercado brasileiro.

Cada persona gera ~12 meses de transações no formato BRUTO da Pluggy
(mesmos campos que o webhook real entrega: id, accountId, description,
amount, transaction_date). Esses dicts entram no ETL REAL — nada é
pré-classificado. As personas são desenhadas para ACENDER a inteligência:
cada uma dispara um conjunto diferente de cards no feed e de respostas do
agente.

  ANA    — CLT confortável, digital e comedora fora: folha de R$ 8.500,
           delivery quase diário, seguro prestamista amarrado ao cartão (D1),
           R$ 52 mil parados na conta corrente (Radar), duas compras
           parceladas em curso e uma assinatura que subiu de preço.
  BRUNO  — MEI: fatura pela maquininha com meses cheios e fracos, mistura
           PF/PJ na mesma conta, paga DAS, tem tarifas de conta PJ (Raio-X,
           D2) e ferramentas B2B que acendem o detector de MEI.
  CARLA  — espiral: renda caindo 12 meses seguidos, rotativo e cheque
           especial CRESCENDO, título de capitalização debitado sem pedir
           (D1), gasto acima da renda. FSS CRÍTICO, margem zero.

Volume e calibração não são enfeite. A densidade (26–45 lançamentos/mês) é o
que tira o `DataQualityValidator` das lacunas e o que dá ao detector de
anomalias os "≥ 5 por categoria" que ele exige antes de comparar qualquer
coisa. E o comprometimento de cada uma (90%, 87%, 112% da renda) foi ajustado
medindo: com gasto empilhado sem renda correspondente, Bruno ficava com saldo
negativo e margem R$ 0, e Ana perdia a taxa de poupança — o que trocava o
cluster das duas.
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

_MONTHS_BACK = 12   # um ano: é o que acende tendência, Wrapped, sazonalidade e IR


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


# ══════════════════════════════════════════════════════════════════════
# Blocos de realismo — o que todo extrato brasileiro tem
# ══════════════════════════════════════════════════════════════════════
#
# Um extrato real não são 17 lançamentos por mês. São 60–120: café, transporte,
# padaria, farmácia, mercado no meio da semana. Essa densidade não é enfeite —
# ela é o que faz o `DataQualityValidator` sair de "cobertura temporal 0,55"
# (lacunas de 2+ dias em metade do mês) para uma base contínua, e o que dá ao
# `SpendingAnomalyDetector` os "≥ 5 lançamentos por categoria" que ele exige
# antes de comparar qualquer coisa com média e desvio.

_MIUDEZAS = (
    ("PADARIA {n}", 8, 32, 6),
    ("CAFETERIA {n}", 9, 28, 4),
    ("UBER *TRIP", 12, 48, 5),
    ("99POP *CORRIDA", 11, 42, 3),
    ("FARMACIA {n}", 18, 95, 2),
    ("MERCADO {n} COMPRA", 45, 190, 4),
    ("BANCA JORNAL", 6, 18, 2),
    ("ESTACIONAMENTO {n}", 10, 35, 3),
)
_SUFIXOS = ("CENTRO", "JARDINS", "VILA NOVA", "SANTANA", "IPIRANGA", "MOEMA")


def _cotidiano(txns: list, acc: str, start: date, intensidade: float = 1.0) -> None:
    """
    O ruído de fundo da vida: 30–70 lançamentos pequenos no mês.

    `intensidade` escala o volume por persona — quem está apertado gasta menos
    vezes, não só menos por vez.
    """
    for molde, lo, hi, vezes in _MIUDEZAS:
        for _ in range(max(1, int(vezes * intensidade))):
            dia = random.randint(1, 28)
            desc = molde.format(n=random.choice(_SUFIXOS))
            _tx(txns, acc, _day(start, dia), desc,
                -random.uniform(lo, hi), random.randint(7, 21))


def _assinaturas(txns: list, acc: str, start: date, planos: dict[str, float]) -> None:
    """
    Assinaturas com valor FIXO e dia fixo.

    O `SubscriptionDetector` v2 exige os cinco critérios ao mesmo tempo:
    keyword positiva, ≥ 3 ocorrências, ≥ 2,5 meses de intervalo, variação de
    valor < 10% e nenhuma marca de parcelamento. Valor variável derruba a
    detecção — por isso estes não passam por `random`.
    """
    for i, (nome, valor) in enumerate(planos.items()):
        _tx(txns, acc, _day(start, 5 + i * 3), nome, -valor, 3)


def _parcelamento(txns: list, acc: str, meses: list[date], desc: str,
                  total: float, n: int, inicio: int = 0, dia: int = 14) -> None:
    """
    Uma compra parcelada, com a marca `k/n` que o extrato brasileiro usa.

    É o que o `_extract_installment_info` procura (a regex de `k / n`), e o
    que vira compromisso futuro na projeção de caixa: o extrato só conta o
    passado, e a parcela 7/10 ainda tem três meses pela frente.
    """
    valor = round(total / n, 2)
    for k in range(n):
        indice = inicio + k
        if indice >= len(meses):
            break
        _tx(txns, acc, _day(meses[indice], dia), f"{desc} {k + 1}/{n}", -valor, 12)


def _tarifas(txns: list, acc: str, start: date, itens: dict[str, float]) -> None:
    """Cobranças do banco — o insumo do Raio-X (F5) e dos detectores D1/D2."""
    for i, (nome, valor) in enumerate(itens.items()):
        _tx(txns, acc, _day(start, 16 + i), nome, -valor, 4)


def _sujeira(txns: list, acc: str, meses: list[date]) -> None:
    """
    Dado sujo de propósito — o extrato real chega assim.

    Três defeitos que o pipeline tem de absorver sem contaminar análise:
    a duplicata exata (que o `dedup_hash` colapsa), a descrição ruidosa com
    asterisco e dígitos (que a normalização de merchant precisa reduzir ao
    mesmo comerciante) e o lançamento fora de ordem cronológica.
    """
    if not meses:
        return
    mes = meses[len(meses) // 2]
    # 1. duplicata exata: mesma conta, data, valor e descrição
    for _ in range(2):
        _tx(txns, acc, _day(mes, 9), "PAGAMENTO RECORRENTE SERVICO", -59.90, 11)
    # 2. o mesmo comerciante escrito de três jeitos
    for dia, texto in ((4, "PG *NETFLX 4471"), (11, "NETFLIX.COM 8891"),
                       (19, "NETFLIX COM BR *ASSIN")):
        _tx(txns, acc, _day(mes, dia), texto, -55.90, 13)
    # 3. lançamento antigo que só chegou agora (o agregador reprocessou)
    _tx(txns, acc, _day(meses[0], 22), "AJUSTE LANCAMENTO RETROATIVO", -18.40, 23)


# ── ANA — CLT foodie ─────────────────────────────────────────────────────

def _gen_ana(acc: str) -> list[dict]:
    """
    CLT com renda estável, delivery pesado e um banco que cobra caro.

    Acende: renda CLT por cadência + keyword, cluster URBANO_FOODIE, tarifa de
    pacote, **seguro prestamista (D1 — venda casada)**, rotativo esporádico
    (D3), parcelamento em curso (compromisso futuro + revisão retroativa),
    assinatura que sobe de preço, 13º e restituição de IR.
    """
    random.seed(101)
    txns: list = []
    meses = _month_starts()
    for i, start in enumerate(meses):
        _tx(txns, acc, _day(start, 5), "CREDITO SALARIO FOLHA MENSAL ACME LTDA", 8500.00, 8)
        _tx(txns, acc, _day(start, 10), "ALUGUEL APARTAMENTO IMOBILIARIA", -2100.00)
        _tx(txns, acc, _day(start, 12), "CONDOMINIO EDIFICIO", -680.00)
        _tx(txns, acc, _day(start, 8), "ENEL DISTRIBUICAO ENERGIA", -180.00)

        # Cobranças do banco. O seguro prestamista é o sinal de VENDA CASADA
        # (D1): produto de crédito amarrado a seguro que ninguém contratou.
        _tarifas(txns, acc, start, {
            "TARIFA PACOTE SERVICOS": 34.90,
            "SEGURO PRESTAMISTA CARTAO": 38.90,
        })

        # Assinaturas de valor fixo — os 5 critérios do detector v2.
        # A Netflix sobe no 8º mês: é o card de assinatura que aumentou.
        _assinaturas(txns, acc, start, {
            "NETFLIX.COM": 39.90 if i < 8 else 55.90,
            "SPOTIFY PREMIUM": 21.90,
            "AMAZON PRIME BR": 14.90,
            "GOOGLE ONE ARMAZENAMENTO": 9.90,
        })

        # Delivery e restaurante: alta frequência, muitos merchants distintos.
        _merchants = [
            "IFOOD *PEDIDO", "RAPPI *RESTAURANTE", "UBER EATS", "IFOOD *SUSHI",
            "AIQFOME *PEDIDO", "RESTAURANTE FASANO", "OUTBACK STEAKHOUSE",
            "IFOOD *HAMBURGUERIA", "STARBUCKS", "RAPPI *PADARIA",
        ]
        for j, dd in enumerate((2, 3, 5, 6, 8, 9, 11, 13, 15, 16, 18, 19,
                                21, 22, 24, 26, 27, 29)):
            _tx(txns, acc, _day(start, dd), _merchants[j % len(_merchants)],
                -random.uniform(48, 165))
        _tx(txns, acc, _day(start, 18), "SUPERMERCADO PAO DE ACUCAR",
            -random.uniform(220, 300))
        _tx(txns, acc, _day(start, 25), "DROGARIA SAO PAULO", -random.uniform(40, 120))
        _tx(txns, acc, _day(start, 6), "APLICACAO CDB LIQUIDEZ DIARIA ITAU", -1200.00, 9)
        # Intensidade calibrada, não escolhida: com 1.0 o comprometimento dela
        # ia a 92% da renda, a taxa de poupança zerava e o FSS subia para
        # ALERTA — o classificador então a tirava de URBANO_FOODIE. Densidade
        # que descaracteriza a persona não é realismo, é ruído.
        _cotidiano(txns, acc, start, intensidade=0.30)

        # Rotativo esporádico: três meses em que a fatura não foi paga inteira.
        if i in (4, 5, 9):
            _tx(txns, acc, _day(start, 14), "JUROS ROTATIVO CARTAO",
                -random.uniform(90, 210), 5)

        # 13º salário e restituição de IR — o ano tem eventos que o semestre não tem.
        if start.month == 12:
            _tx(txns, acc, _day(start, 18), "CREDITO 13 SALARIO FOLHA ACME LTDA", 8500.00, 8)
        if start.month == 5:
            _tx(txns, acc, _day(start, 28), "RESTITUICAO IRPF LOTE RECEITA FEDERAL",
                1840.00, 8)

    # Anuidade cobrada uma vez no ano.
    if len(meses) > 6:
        _tx(txns, acc, _day(meses[6], 20), "ANUIDADE CARTAO CREDITO PARC 1/1", -480.00, 4)

    # Compras parceladas em curso — viram compromisso futuro na projeção.
    _parcelamento(txns, acc, meses, "MAGAZINE LUIZA GELADEIRA", 4200.00, 10, inicio=5)
    _parcelamento(txns, acc, meses, "FAST SHOP NOTEBOOK", 5400.00, 12, inicio=2, dia=21)

    # Anomalia recente: compra muito acima do padrão dela.
    _tx(txns, acc, _day(meses[-1], 24), "MAGAZINE LUIZA ELETRO", -3890.00)
    _eventos_recentes(txns, acc, meses, "confortavel")
    _sujeira(txns, acc, meses)
    return txns


# ── BRUNO — MEI ──────────────────────────────────────────────────────────

def _gen_bruno(acc: str) -> list[dict]:
    """
    MEI que mistura tudo na mesma conta.

    Acende: classificador PF/PJ, detector de MEI, relatório fiscal/DAS,
    **tarifas de conta PJ (Raio-X + D2)**, renda instável com nota fiscal
    (keyword que dá confiança ao `IncomeProfiler`) e ferramentas B2B.
    """
    random.seed(202)
    txns: list = []
    meses = _month_starts()
    # Renda de MEI é instável: meses cheios e meses fracos.
    escalas = [1.4, 0.5, 1.2, 0.4, 1.5, 0.6, 1.3, 0.7, 1.1, 0.5, 1.4, 0.8]
    for i, (start, escala) in enumerate(zip(meses, escalas)):
        recebimentos = max(int(11 * escala), 4)
        for k in range(recebimentos):
            dd = 2 + (k * 26 // max(recebimentos, 1))
            _tx(txns, acc, _day(start, dd), random.choice([
                "PAGSEGURO *VENDAS", "STONE *RECEBIMENTO", "MERCADO PAGO VENDA",
                "PIX RECEBIDO CLIENTE PJ NOTA FISCAL", "GETNET *VENDA",
                "PIX RECEBIDO PRESTACAO SERVICO PJ",
            ]), random.uniform(260, 890) * escala)

        _tx(txns, acc, _day(start, 20), "DAS SIMEI PAGAMENTO GUIA", -76.90)

        # A conta PJ cobra — e no extrato do Bruno isso não existia, o que
        # deixava o Raio-X em R$ 0,00 e o D2 mudo para ele.
        _tarifas(txns, acc, start, {
            "TARIFA MANUTENCAO CONTA PJ": 42.00,
            "TARIFA TED ENVIO": 11.90,
            "TARIFA PACOTE SERVICOS EMPRESARIAL": 29.90,
        })

        # Ferramentas B2B — sinal `b2b_tools` do detector de MEI.
        _assinaturas(txns, acc, start, {
            "GOOGLE WORKSPACE": 34.90,
            "CANVA PRO ASSINATURA": 29.90,
            "MERCADO PAGO PONTO ALUGUEL": 49.00,
        })

        # Insumos PJ misturados na conta pessoal.
        _tx(txns, acc, _day(start, 6), "ATACADAO DISTRIBUICAO", -random.uniform(400, 900))
        _tx(txns, acc, _day(start, 7), "APLICACAO RESERVA CDB INTER", -900.00, 9)
        _tx(txns, acc, _day(start, 16), "FORNECEDOR EMBALAGENS LTDA",
            -random.uniform(150, 350))
        # Gastos PF.
        _tx(txns, acc, _day(start, 10), "ALUGUEL RESIDENCIAL", -1400.00)
        _tx(txns, acc, _day(start, 12), "SUPERMERCADO EXTRA", -random.uniform(300, 420))
        _tx(txns, acc, _day(start, 15), "POSTO IPIRANGA COMBUSTIVEL",
            -random.uniform(150, 260))
        # Nada de mensalidade escolar aqui: ela aciona o FamilyDetector, que
        # empatava em 0.8 com o score de MEI (travado nesse teto) e roubava o
        # cluster da persona. O gasto equivalente dele é o galpão.
        _tx(txns, acc, _day(start, 18), "ALUGUEL GALPAO COMERCIAL", -720.00)
        _cotidiano(txns, acc, start, intensidade=0.5)

    _parcelamento(txns, acc, meses, "DELL NOTEBOOK EQUIPAMENTO", 6000.00, 12, inicio=1)
    _eventos_recentes(txns, acc, meses, "mei")
    _sujeira(txns, acc, meses)
    return txns


# ── CARLA — estresse financeiro ──────────────────────────────────────────

def _gen_carla(acc: str) -> list[dict]:
    """
    Renda caindo e crédito caro segurando o mês.

    Acende: FSS alto → cluster ESTRESSE_FINANCEIRO, **juros abusivos (D3)**
    com rotativo e cheque especial crescentes, **título de capitalização
    (D1 — venda casada)**, tarifa recorrente, margem apertada e parcelamento
    que ela já não deveria ter assumido.
    """
    random.seed(303)
    txns: list = []
    meses = _month_starts()
    for i, start in enumerate(meses):
        # Renda em queda contínua ao longo do ano.
        renda = 4800.00 - i * 95.00
        _tx(txns, acc, _day(start, 5), "PIX RECEBIDO PAGAMENTO CLIENTE", renda, 8)
        _tx(txns, acc, _day(start, 10), "ALUGUEL KITNET", -1500.00)
        _tx(txns, acc, _day(start, 8), "CLARO MOVEL FATURA", -89.90)
        _tx(txns, acc, _day(start, 11), "ENERGIA ELETRICA", -210.00)
        inflacao = 1.0 + i * 0.035
        _tx(txns, acc, _day(start, 12), "SUPERMERCADO DIA",
            -random.uniform(400, 600) * inflacao)

        # Crédito caro, crescendo — o insumo do D3.
        _tx(txns, acc, _day(start, 14), "JUROS ROTATIVO CARTAO", -(110 + i * 38))
        _tx(txns, acc, _day(start, 14), "ENCARGOS CHEQUE ESPECIAL", -(70 + i * 26))
        _tx(txns, acc, _day(start, 15), "ADIANTAMENTO A DEPOSITANTE", -(50 + i * 17))

        # Venda casada: título de capitalização debitado junto do crédito.
        _tarifas(txns, acc, start, {
            "TARIFA MANUTENCAO CONTA": 29.90,
            "TITULO CAPITALIZACAO DEBITO AUTORIZADO": 59.90,
        })

        _tx(txns, acc, _day(start, 20), "FARMACIA POPULAR",
            -random.uniform(60, 140) * inflacao)
        _tx(txns, acc, _day(start, 25), "CARTAO CREDITO PAGAMENTO MINIMO",
            -random.uniform(300, 500) * inflacao)
        # 0.5 mantém o comprometimento em ~95% da renda, que é o alvo dela:
        # é esse número que sustenta o FSS em CRITICO e o cluster
        # ESTRESSE_FINANCEIRO.
        _cotidiano(txns, acc, start, intensidade=0.5)

    _parcelamento(txns, acc, meses, "CASAS BAHIA SOFA", 2400.00, 12, inicio=3)
    _eventos_recentes(txns, acc, meses, "apertado")
    _sujeira(txns, acc, meses)
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
        monthly_income=8500.0,
        # O classificador real a coloca em DIGITAL_NATIVO com URBANO_FOODIE
        # como secundário — ela é as duas coisas: come fora quase todo dia E
        # vive de banco digital, assinatura e PIX. As regras chegam a dar 0,70
        # para foodie contra 0,63 para digital, e o ML destilado decide pelo
        # segundo. Declarar aqui o que o produto conclui, em vez de ajustar o
        # extrato até o modelo concordar: o classificador é a lógica real, e
        # torcê-lo para bater com o rótulo seria calibrar a régua pela resposta.
        expected_cluster="DIGITAL_NATIVO",
        banks=[
            # Conta corrente alta de propósito: é o cenário de manchete do
            # produto. O detector protege 6 meses de despesa como reserva
            # (9 se o FSS estiver em ALERTA) e só o que sobra vira "dinheiro
            # parado" — com R$ 3.200 não sobrava nada e o Radar respondia
            # R$ 0,00 para todo mundo.
            ConnectedBank("nubank", "Nubank", "primary", [
                BankAccount("CHECKING", 52400.0), BankAccount("CREDIT", -2840.0)]),
            ConnectedBank("itau", "Itaú", "investment", [
                BankAccount("INVESTMENT", 18700.0)]),
            ConnectedBank("inter", "Banco Inter", "savings", [
                BankAccount("SAVINGS", 12500.0)]),
        ],
        goals=[
            {"name": "Reserva de emergência", "target": 30000, "current": 18400,
             "type": "emergencia", "target_date": "2027-06-30"},
            {"name": "Viagem Europa 2027", "target": 18000, "current": 3200,
             "type": "viagem", "target_date": "2027-07-01"},
            {"name": "Trocar de carro", "target": 45000, "current": 6100,
             "type": "carro", "target_date": "2028-03-01"},
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
            # Caixa da empresa parado na conta PJ — o dinheiro que o MEI deixa
            # ali entre um pagamento de fornecedor e outro.
            ConnectedBank("pagbank", "PagBank", "business", [
                BankAccount("CHECKING", 31500.0)]),
        ],
        goals=[
            {"name": "Capital de giro", "target": 15000, "current": 9200,
             "type": "outros", "target_date": "2027-01-31"},
            {"name": "Equipamento novo (marcenaria)", "target": 12000, "current": 1500,
             "type": "outros", "target_date": "2027-09-30"},
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
            {"name": "Sair do vermelho", "target": 5000, "current": 640,
             "type": "outros", "target_date": "2027-03-31"},
            {"name": "Reserva de 1 mês", "target": 3800, "current": 120,
             "type": "emergencia", "target_date": "2027-12-31"},
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


def _dias_atras(n: int) -> date:
    """Data a `n` dias de hoje — a janela dos detectores é relativa a agora."""
    return date.today() - timedelta(days=n)


def _eventos_recentes(txns: list, acc: str, meses: list[date], perfil: str) -> None:
    """
    O que aconteceu nas últimas semanas — e é o que o produto tem a dizer hoje.

    As datas aqui são contadas a partir de HOJE, não do dia do mês, porque é
    assim que os dois consumidores olham:

    - `review_recent_purchases` só considera os **últimos 14 dias** e só compra
      **à vista** acima de R$ 300 (é uma revisão do que ainda dá para agir:
      pedir estorno, trocar a forma de pagamento na próxima). Parcela antiga
      não entra.
    - `SpendingAnomalyDetector` compara com o baseline do próprio usuário na
      janela recente. Doze meses regulares não produzem anomalia nenhuma — e
      extrato real sempre tem.

    Colocar esses eventos em "dia 12 do mês corrente" os deixava a 19 dias de
    hoje, fora das duas janelas: o dado existia e nenhum detector o via.
    """
    if len(meses) < 2:
        return

    if perfil == "confortavel":
        # Compras grandes à vista, dentro da janela de 14 dias — é o que a
        # revisão retroativa procura.
        # "PIX" na descrição é o que o `_infer_paid_method` lê para saber COMO
        # foi pago. Sem marcador ele assume cartão à vista — que costuma ser a
        # opção ótima, e aí a revisão não tem o que dizer. Pagar no PIX uma
        # compra que renderia cashback é justamente o achado do F7 retroativo.
        _tx(txns, acc, _dias_atras(3), "PIX OTICA VISION OCULOS GRAU", -1280.00, 15)
        _tx(txns, acc, _dias_atras(8), "RESTAURANTE DOM PEDRO JANTAR", -640.00, 21)
        _tx(txns, acc, _dias_atras(11), "PIX SAMSUNG SMARTPHONE GALAXY", -4800.00, 14)
        # Duplicidade suspeita: mesmo comerciante, mesmo valor, dois dias.
        for atras in (5, 6):
            _tx(txns, acc, _dias_atras(atras), "IFOOD *PEDIDO", -98.70, 20)

    elif perfil == "mei":
        _tx(txns, acc, _dias_atras(2), "PIX GRAFICA EXPRESSA MATERIAL", -1950.00, 14)
        _tx(txns, acc, _dias_atras(6), "SERASA EXPERIAN CONSULTA", -389.00, 11)
        _tx(txns, acc, _dias_atras(10), "PIX IMPRESSORA EPSON PROFISSIONAL", -3600.00, 9)
        for atras in (4, 5):
            _tx(txns, acc, _dias_atras(atras), "ATACADAO DISTRIBUICAO", -712.40, 8)

    else:  # apertado — a anomalia dela é a emergência que estoura o mês
        _tx(txns, acc, _dias_atras(4), "PIX CLINICA ODONTOLOGICA URGENCIA", -890.00, 16)
        _tx(txns, acc, _dias_atras(9), "MECANICA AUTO SOCORRO", -720.00, 18)
        _tx(txns, acc, _dias_atras(12), "PIX MAGAZINE FOGAO 4 BOCAS", -1800.00, 13)


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
