"""
demo/features.py — O catálogo de funcionalidades da HIVE, ligado ao código real.

Este módulo é a ponte entre o app Streamlit e o produto. Ele não recalcula
nada: mapeia as **31 ferramentas do agente** (o registro canônico
`AGENT_TOOLS`) e os serviços de produção para as três superfícies do app —
Feed, Organizar e Chat — e executa cada uma com a mesma vinculação de
identidade que o endpoint `/chat` usa.

Por que as tools do agente e não os serviços direto: elas são a camada
auditada. `tests/agent/test_agente_producao.py` roda as 31 contra um usuário
com extrato real e reprova qualquer uma que levante ou registre erro. Chamar o
`BankFeeAnalyzer` na mão duplicaria a montagem de argumentos que já foi
corrigida lá dentro — e foi exatamente esse tipo de duplicata que deixou cinco
ferramentas caindo no próprio `except` até 2026-08-24.

O que o app acrescenta por cima é o que a prosa não dá: números estruturados
para os gráficos (`panorama`, `extrato`), o feed proativo real (`build_feed`) e
a leitura da linha `[NEXA]` de procedência, que em produção é informação de
sistema e aqui vira o selo de confiança visível na tela.

## A consistência é verificada na importação

`_verificar_catalogo()` roda no import e levanta se o catálogo divergir de
`AGENT_TOOLS` — ferramenta nova sem lugar na interface, ou entrada do catálogo
apontando para uma tool que não existe mais. O app não sobe com o catálogo
mentindo sobre o produto; é a mesma ideia do teste de inventário que substituiu
o `assert len(tools) == 14` escrito à mão.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("demo.features")

# ══════════════════════════════════════════════════════════════════════
# O vocabulário do catálogo
# ══════════════════════════════════════════════════════════════════════

FEED = "feed"
ORGANIZAR = "organizar"
CHAT = "chat"


@dataclass(frozen=True)
class Parametro:
    """Um argumento que a ferramenta aceita e o app pede ao usuário."""

    nome: str
    rotulo: str
    tipo: str  # "moeda" | "inteiro" | "texto" | "opcao"
    padrao: Any = None
    opcoes: tuple[str, ...] = ()
    ajuda: str = ""
    minimo: float = 0.0
    maximo: float = 1_000_000.0
    passo: float = 100.0


@dataclass(frozen=True)
class Ferramenta:
    """Uma funcionalidade do produto, do jeito que o app a apresenta."""

    tool: str
    titulo: str
    resumo: str
    doc: str              # número do doc em docs/funcionalidades/
    superficie: str       # FEED | ORGANIZAR | CHAT
    grupo: str            # a seção dentro da superfície
    plano: str = "free"   # gating real (billing/plans.py)
    icone: str = "•"
    lenta: bool = False   # chama rede externa (BACEN/SGS) — precisa de spinner
    parametros: tuple[Parametro, ...] = ()

    @property
    def caminho_do_doc(self) -> str:
        return f"docs/funcionalidades/{self.doc}"


# ══════════════════════════════════════════════════════════════════════
# O catálogo — 31 ferramentas, 18 docs, 3 superfícies
# ══════════════════════════════════════════════════════════════════════
#
# `superficie` segue a arquitetura de informação do app real
# (frontend-react/src/pages): o que CHEGA sozinho vai para o Feed, o que o
# usuário VAI OLHAR vai para Organizar, e o Chat tem todas porque o agente
# decide sozinho qual chamar.

CATALOGO: tuple[Ferramenta, ...] = (
    # ── Perfil e previsão (docs 02, 13) ──────────────────────────────
    Ferramenta(
        "get_user_profile_context", "Perfil comportamental",
        "Cluster de estilo de vida, FSS e eventos de vida detectados no extrato.",
        "13-inteligencia-comportamental.md", ORGANIZAR, "Você", icone="🧬",
    ),
    Ferramenta(
        "get_financial_forecast", "Projeção e margem segura",
        "Cashflow de 30 dias e quanto dá para gastar por dia sem ficar no vermelho.",
        "02-cashflow-e-safe-to-spend.md", ORGANIZAR, "Dinheiro", icone="📈",
    ),
    Ferramenta(
        "get_spending_alerts", "Alertas de gasto",
        "Anomalias estatísticas contra o seu próprio histórico.",
        "01-open-finance-e-etl.md", FEED, "Atenção", icone="🔔",
    ),
    Ferramenta(
        "get_goals_summary", "Metas",
        "Progresso e quanto falta guardar por mês.",
        "14-engajamento-e-retencao.md", ORGANIZAR, "Planejar", icone="🎯",
        parametros=(
            Parametro("monthly_savings", "Quanto pretende guardar/mês", "moeda",
                      padrao=500.0, maximo=50_000.0, passo=50.0),
        ),
    ),
    # ── Orçamento e pares (doc 14) ───────────────────────────────────
    Ferramenta(
        "get_budget_advice", "Orçamento 50/30/20",
        "Divide a renda em essenciais, estilo de vida e poupança sobre o gasto real.",
        "14-engajamento-e-retencao.md", ORGANIZAR, "Planejar", icone="📋",
        parametros=(
            Parametro("monthly_income", "Renda mensal (vazio = estimada pelo extrato)",
                      "moeda", padrao=0.0, maximo=200_000.0, passo=100.0,
                      ajuda="Deixe em 0 para a Nexa estimar pelo extrato — a regra 7b "
                            "do prompt proíbe o agente de inventar esse número."),
        ),
    ),
    Ferramenta(
        "get_peer_comparison", "Comparação com pares",
        "Como seu gasto se compara ao de quem tem renda parecida (anônimo).",
        "14-engajamento-e-retencao.md", ORGANIZAR, "Você", icone="👥",
        parametros=(
            Parametro("monthly_income", "Renda mensal", "moeda", padrao=6500.0,
                      maximo=200_000.0, passo=100.0),
        ),
    ),
    # ── Cartões (doc 03) ─────────────────────────────────────────────
    Ferramenta(
        "get_card_optimization", "Otimizador de cartões",
        "81 cartões de 37 emissores rodados sobre o seu padrão de gasto real.",
        "03-otimizador-de-cartoes.md", ORGANIZAR, "Cartões", icone="💳",
        parametros=(
            Parametro("monthly_spend", "Gasto mensal no cartão", "moeda",
                      padrao=0.0, maximo=100_000.0, passo=100.0,
                      ajuda="0 = deriva do extrato."),
        ),
    ),
    Ferramenta(
        "get_expert_card_analysis", "Especialista em cartões",
        "O aprofundamento com LLM para quando a confiança da simulação fica baixa.",
        "03-otimizador-de-cartoes.md", ORGANIZAR, "Cartões", icone="🧠",
        parametros=(
            Parametro("question", "Sua pergunta sobre cartões", "texto",
                      padrao="Qual cartão vale mais a pena para o meu perfil?"),
        ),
    ),
    # ── Compras (doc 07) ─────────────────────────────────────────────
    Ferramenta(
        "get_purchase_recommendation", "Compra inteligente",
        "Pix, débito, crédito à vista, parcelado ou CDC — pelo custo real, não pelo nominal.",
        "07-compra-inteligente.md", ORGANIZAR, "Decidir", icone="🛒", plano="free",
        parametros=(
            Parametro("amount", "Valor da compra", "moeda", padrao=3500.0,
                      maximo=500_000.0, passo=100.0),
            Parametro("category", "Categoria", "opcao", padrao="eletronicos",
                      opcoes=("eletronicos", "alimentacao", "supermercado", "viagem",
                              "saude", "educacao", "vestuario", "casa", "transporte")),
            Parametro("installments", "Parcelas", "inteiro", padrao=10,
                      minimo=1, maximo=48, passo=1),
        ),
    ),
    Ferramenta(
        "review_recent_purchases", "Revisão retroativa",
        "Compras grandes já feitas em que a forma de pagamento saiu mais cara.",
        "07-compra-inteligente.md", FEED, "Oportunidades", icone="🔁",
    ),
    # ── Simulações grandes (doc 04) ──────────────────────────────────
    Ferramenta(
        "get_financing_simulation", "Financiar × consórcio × investir",
        "VPL, Monte Carlo e dominância estocástica para a decisão grande.",
        "04-architect-simulacoes.md", ORGANIZAR, "Decidir", icone="🏗️", plano="pro",
        parametros=(
            Parametro("target_amount", "Valor do bem", "moeda", padrao=60_000.0,
                      maximo=5_000_000.0, passo=5_000.0),
            Parametro("down_payment", "Entrada", "moeda", padrao=15_000.0,
                      maximo=5_000_000.0, passo=1_000.0),
            Parametro("asset_type", "Tipo de bem", "opcao", padrao="vehicle",
                      opcoes=("vehicle", "property")),
            Parametro("financing_months", "Prazo (meses)", "inteiro", padrao=48,
                      minimo=6, maximo=420, passo=6),
        ),
    ),
    Ferramenta(
        "get_timing_scenarios", "Esperar ou comprar agora",
        "Compara comprar hoje contra poupar mais alguns meses.",
        "04-architect-simulacoes.md", ORGANIZAR, "Decidir", icone="⏳", plano="pro",
        parametros=(
            Parametro("target_amount", "Valor do bem", "moeda", padrao=60_000.0,
                      maximo=5_000_000.0, passo=5_000.0),
            Parametro("monthly_savings", "Quanto consegue poupar/mês", "moeda",
                      padrao=1_100.0, maximo=100_000.0, passo=100.0),
            Parametro("down_payment", "Entrada de hoje", "moeda", padrao=15_000.0,
                      maximo=5_000_000.0, passo=1_000.0),
        ),
    ),
    Ferramenta(
        "get_leverage_simulation", "Alavancagem imobiliária",
        "Comprar para alugar: aluguel, valorização e custo do capital.",
        "04-architect-simulacoes.md", ORGANIZAR, "Decidir", icone="🏢", plano="pro",
        parametros=(
            Parametro("city", "Cidade", "texto", padrao="BH"),
            Parametro("neighborhood", "Bairro", "texto", padrao="Buritis"),
            Parametro("sqm", "Metragem (m²)", "inteiro", padrao=70,
                      minimo=20, maximo=1000, passo=5),
        ),
    ),
    # ── Oportunidades (doc 09) ───────────────────────────────────────
    Ferramenta(
        "get_opportunities", "Radar de oportunidades",
        "Dinheiro parado, poupança rendendo abaixo do CDI, ranking líquido de IR.",
        "09-radar-de-oportunidades.md", FEED, "Oportunidades", icone="📡", plano="pro",
    ),
    Ferramenta(
        "get_best_bank", "Bank Match",
        "Qual banco encaixa no seu perfil, com peso por FSS e comportamento.",
        "09-radar-de-oportunidades.md", ORGANIZAR, "Bancos", icone="🏦", plano="pro",
    ),
    Ferramenta(
        "simulate_investment", "Simulador de investimento",
        "CDB, LCI, Tesouro e poupança com IR regressivo real.",
        "09-radar-de-oportunidades.md", ORGANIZAR, "Decidir", icone="💰",
        parametros=(
            Parametro("amount", "Quanto investir", "moeda", padrao=10_000.0,
                      maximo=5_000_000.0, passo=1_000.0),
            Parametro("holding_months", "Prazo (meses)", "inteiro", padrao=12,
                      minimo=1, maximo=120, passo=1),
        ),
    ),
    # ── Defesa do consumidor (doc 10) ────────────────────────────────
    Ferramenta(
        "detect_abusive_fees", "D1 — Tarifas abusivas",
        "Venda casada e cobrança sem contratação, com base legal citada.",
        "10-defesa-do-consumidor.md", FEED, "Defesa", icone="⚖️", plano="total",
    ),
    Ferramenta(
        "detect_wrongful_charges", "D2 — Cobranças indevidas",
        "Duplicidade no mesmo mês e tarifa nova sem precedente no histórico.",
        "10-defesa-do-consumidor.md", FEED, "Defesa", icone="🚩", plano="total",
    ),
    Ferramenta(
        "detect_abusive_interest", "D3 — Juros abusivos",
        "Sua taxa contra o CET médio publicado pelo BACEN (SGS).",
        "10-defesa-do-consumidor.md", FEED, "Defesa", icone="📛", plano="total",
        lenta=True,
    ),
    Ferramenta(
        "get_defense_analysis", "D1–D4 consolidado",
        "A análise de defesa inteira, com valor em discussão e ação em 3 níveis.",
        "10-defesa-do-consumidor.md", ORGANIZAR, "Defesa", icone="🛡️", plano="total",
        lenta=True,
    ),
    Ferramenta(
        "get_evidence_dossier", "D5 — Dossiê de evidências",
        "Carta ao banco, dossiê PROCON e minuta de petição JEC.",
        "10-defesa-do-consumidor.md", ORGANIZAR, "Defesa", icone="📄", plano="total",
        lenta=True,
    ),
    Ferramenta(
        "get_portability_analysis", "D6 — Portabilidade de crédito",
        "Res. CMN 5.057/2022: levar a dívida para outro banco, de graça.",
        "10-defesa-do-consumidor.md", ORGANIZAR, "Defesa", icone="🔀", plano="total",
    ),
    # ── Custos e negociação (docs 06, 08) ────────────────────────────
    Ferramenta(
        "get_bank_cost_analysis", "Raio-X de custos",
        "Cada tarifa itemizada, com o banco identificado e o benchmark de mercado.",
        "06-raio-x-de-custos.md", ORGANIZAR, "Bancos", icone="🔎", plano="pro",
    ),
    Ferramenta(
        "get_negotiation_script", "Negociador",
        "Roteiro de negociação com o Score Nexa como poder de barganha.",
        "08-negociador.md", ORGANIZAR, "Bancos", icone="🤝", plano="pro",
        parametros=(
            Parametro("bank_name", "Banco", "texto", padrao="",
                      ajuda="Vazio = o detector escolhe o de maior oportunidade."),
        ),
    ),
    # ── Fiscal e direitos (docs 11, 12) ──────────────────────────────
    Ferramenta(
        "get_fiscal_calendar", "Calendário fiscal",
        "Prazos que geram multa, personalizados pelo seu perfil.",
        "12-impostos-e-calendario-fiscal.md", FEED, "Atenção", icone="📅",
    ),
    Ferramenta(
        "get_fiscal_report", "Relatório fiscal MEI",
        "Faturamento PJ, teto do MEI e estimativa do DAS.",
        "12-impostos-e-calendario-fiscal.md", ORGANIZAR, "PF × PJ", icone="🧾",
        parametros=(
            Parametro("year", "Ano", "inteiro", padrao=0, minimo=0,
                      maximo=2100, passo=1, ajuda="0 = ano corrente."),
        ),
    ),
    Ferramenta(
        "get_forgotten_rights", "Direitos esquecidos",
        "SVR do BACEN, restituição de IRPF, FGTS e PIS/PASEP.",
        "11-direitos-esquecidos.md", FEED, "Oportunidades", icone="🔦",
    ),
    # ── Engajamento (doc 14) ─────────────────────────────────────────
    Ferramenta(
        "get_monthly_challenges", "Desafios do mês",
        "Metas curtas com selo, geradas a partir do seu próprio padrão.",
        "14-engajamento-e-retencao.md", ORGANIZAR, "Planejar", icone="🏅",
    ),
    Ferramenta(
        "get_annual_wrapped", "Wrapped financeiro",
        "O ano em retrospectiva: você contra os bancos.",
        "14-engajamento-e-retencao.md", ORGANIZAR, "Você", icone="🎁", plano="total",
        parametros=(
            Parametro("year", "Ano", "inteiro", padrao=0, minimo=0,
                      maximo=2100, passo=1, ajuda="0 = ano corrente."),
        ),
    ),
    # ── Promoções e plano (docs 03, 16) ──────────────────────────────
    Ferramenta(
        "get_transfer_promotions", "Promoções de transferência",
        "Bônus de pontos ativos, com guarda de curadoria vencida.",
        "03-otimizador-de-cartoes.md", FEED, "Oportunidades", icone="✨",
    ),
    Ferramenta(
        "get_plan_info", "Seu plano",
        "Free, Pro ou Total — o que libera e quanto do limite você já usou.",
        "16-billing-e-planos.md", ORGANIZAR, "Conta", icone="⭐",
    ),
)

POR_NOME: dict[str, Ferramenta] = {f.tool: f for f in CATALOGO}


def _verificar_catalogo() -> None:
    """
    O catálogo e o registro do agente têm de dizer a mesma coisa.

    Roda na importação e levanta com a lista exata do que divergiu. Uma
    ferramenta nova que ninguém colocou na interface é uma funcionalidade que o
    usuário não alcança; uma entrada apontando para tool removida é uma tela
    que quebra ao clicar. Falhar aqui é falhar barato.
    """
    from app.agent.graph import AGENT_TOOLS

    registradas = {t.name for t in AGENT_TOOLS}
    catalogadas = set(POR_NOME)

    sem_interface = sorted(registradas - catalogadas)
    sem_ferramenta = sorted(catalogadas - registradas)
    if sem_interface or sem_ferramenta:
        raise RuntimeError(
            "demo/features.py está fora de sincronia com AGENT_TOOLS.\n"
            f"  Tools sem lugar na interface: {sem_interface or 'nenhuma'}\n"
            f"  Catálogo apontando para tool inexistente: {sem_ferramenta or 'nenhuma'}\n"
            "Acrescente a entrada no CATALOGO (ou remova a obsoleta)."
        )


# ══════════════════════════════════════════════════════════════════════
# Execução — com a vinculação de identidade de produção
# ══════════════════════════════════════════════════════════════════════

@dataclass
class Resultado:
    ferramenta: Ferramenta
    texto: str = ""
    procedencia: dict = field(default_factory=dict)
    segundos: float = 0.0
    erro: str | None = None

    @property
    def degradado(self) -> str | None:
        return self.procedencia.get("degradado")

    @property
    def confianca(self) -> float | None:
        return self.procedencia.get("confianca")

    @property
    def cobertura(self) -> str | None:
        return self.procedencia.get("cobertura")

    @property
    def fontes(self) -> list[str]:
        return self.procedencia.get("fontes") or []

    @property
    def texto_limpo(self) -> str:
        """
        O texto sem a linha `[NEXA]`.

        Em produção o agente nunca a repete ao usuário — é informação de
        sistema. Aqui ela sai do corpo e vira o selo de procedência do card,
        que é a mesma decisão com a interface no lugar do modelo.
        """
        return "\n".join(
            linha for linha in self.texto.splitlines()
            if not linha.strip().startswith("[NEXA]")
        ).strip()


def executar(nome: str, user_id: str, **kwargs) -> Resultado:
    """
    Roda uma ferramenta do agente como o endpoint `/chat` roda.

    O `user_id` entra pelo contexto (`usuario_da_requisicao`), não só pelo
    argumento: é a camada 4 da mitigação de prompt injection, e exercitá-la
    aqui significa que o demo percorre o mesmo caminho de identidade que a
    produção — inclusive o `vincular_ao_usuario`, que sobrescreve o argumento
    pelo usuário autenticado.
    """
    from app.agent.graph import AGENT_TOOLS
    from app.agent.identity import usuario_da_requisicao, vincular_ao_usuario
    from app.agent.procedencia import ler_procedencia

    ferramenta = POR_NOME[nome]
    crua = next(t for t in AGENT_TOOLS if t.name == nome)
    ligada = vincular_ao_usuario(crua)

    argumentos: dict[str, Any] = {"user_id": user_id}
    for parametro in ferramenta.parametros:
        valor = kwargs.get(parametro.nome, parametro.padrao)
        if valor in (None, ""):
            continue
        argumentos[parametro.nome] = valor

    inicio = time.time()
    try:
        with usuario_da_requisicao(user_id):
            saida = ligada.invoke(argumentos)
        texto = saida if isinstance(saida, str) else str(saida)
        return Resultado(
            ferramenta=ferramenta, texto=texto,
            procedencia=ler_procedencia(texto) or {},
            segundos=round(time.time() - inicio, 2),
        )
    except Exception as exc:  # nenhuma tela cai por causa de uma ferramenta
        logger.warning("ferramenta %s falhou: %s", nome, exc)
        return Resultado(
            ferramenta=ferramenta, segundos=round(time.time() - inicio, 2),
            erro=f"{type(exc).__name__}: {exc}",
        )


def por_superficie(superficie: str) -> list[Ferramenta]:
    return [f for f in CATALOGO if f.superficie == superficie]


def grupos(superficie: str) -> list[str]:
    """Os grupos daquela superfície, na ordem em que aparecem no catálogo."""
    vistos: list[str] = []
    for f in CATALOGO:
        if f.superficie == superficie and f.grupo not in vistos:
            vistos.append(f.grupo)
    return vistos


_verificar_catalogo()
