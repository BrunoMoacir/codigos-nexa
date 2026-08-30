"""
demo/hive_app.py — A HIVE inteira, funcionando, numa tela.

Este é o app de teste ponta a ponta: as quatro superfícies do produto real
(Panorama, Oportunidades, Organizar e Chat) sobre os serviços de produção,
alimentadas por personas cujos dados passaram pelo ETL de verdade —
Pluggy-style → validação → ingestor → classificador → PF/PJ → Postgres.

Nada aqui é mock na camada de inteligência. O que a tela mostra é o que o
backend calcula:

  • as **31 ferramentas** do registro `AGENT_TOOLS`, executadas com a mesma
    vinculação de identidade do endpoint `/chat` (`usuario_da_requisicao` +
    `vincular_ao_usuario`) — a camada 4 da mitigação de prompt injection;
  • o **feed proativo** com o `ProactiveNotifier` e o
    `NotificationRelevanceFilter` reais, que são quem decide o que merece
    interromper o usuário;
  • o **agente LangGraph** de verdade no Chat, com o traço de quais ferramentas
    ele decidiu chamar;
  • o **gating de plano** real (`billing/plans.py`), inclusive o modo dark
    launch: o app mostra o que TERIA sido bloqueado em vez de esconder.

## O que este app testa, além de demonstrar

`demo/features.py` verifica na importação que o catálogo da interface e o
registro `AGENT_TOOLS` dizem a mesma coisa. Ferramenta nova sem lugar na tela,
ou entrada apontando para tool removida, e o app **não sobe** — com a lista do
que divergiu. É a mesma ideia do teste de inventário que substituiu o
`assert len(tools) == 14` escrito à mão: a interface não pode mentir sobre o
produto sem alguém perceber.

Cada card mostra a **linha de procedência** que a ferramenta emitiu
(`confianca`, `cobertura`, `fontes`, `degradado`). Em produção o agente nunca a
repete ao usuário — é informação de sistema. Aqui ela vira o selo visível, que
é a mesma decisão com a interface no lugar do modelo: dá para ver, de relance,
qual número é medição e qual saiu de um caminho de fallback.

## Rodar

    cd backend
    python3 -m demo.seed                  # popula as 3 personas (uma vez)
    streamlit run demo/hive_app.py        # → http://localhost:8501

O Chat precisa de `ANTHROPIC_API_KEY` (ou `OPENAI_API_KEY`); `demo/ambiente.py`
a procura em `backend/.env` e no `.env` da raiz. Sem chave, as outras três
superfícies funcionam inteiras e o Chat explica o que falta.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# `backend/` no path antes de tudo: o Streamlit executa este arquivo direto, e
# sem isto `import demo.*` e `import app.*` dependeriam do diretório de onde o
# comando foi disparado.
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# A resolução do ambiente precisa vir ANTES de qualquer import de `app.*`:
# `Settings` é instanciado na importação do módulo de config.
from demo.ambiente import carregar_env  # noqa: E402

_ORIGEM_ENV = carregar_env()

import streamlit as st  # noqa: E402

from demo import features as F  # noqa: E402
from demo import paineis as P  # noqa: E402
from demo.personas import PERSONAS  # noqa: E402

logging.getLogger("demo").setLevel(logging.WARNING)

st.set_page_config(page_title="HIVE", page_icon="🐝", layout="wide",
                   initial_sidebar_state="expanded")

# ══════════════════════════════════════════════════════════════════════
# Identidade visual — a mesma paleta de frontend-react/src/styles/globals.css
# ══════════════════════════════════════════════════════════════════════

OURO = "#D4A820"
CREME = "#F3EFEA"
FUNDO = "#1A1714"
SUPERFICIE = "#242018"
BORDA = "#34302A"
SECUNDARIO = "#949080"
VERDE = "#2EC8A4"
VERMELHO = "#F07A64"
AMBAR = "#ECB040"
AZUL = "#60B0F2"

CSS = f"""
<style>
  .stApp {{ background: {FUNDO}; }}
  section[data-testid="stSidebar"] {{ background: {SUPERFICIE}; border-right: 1px solid {BORDA}; }}
  h1, h2, h3, h4, p, span, div, label {{ color: {CREME}; }}
  .hv-marca {{ font-size: 2rem; font-weight: 800; letter-spacing: -0.05em; color: {OURO}; }}
  .hv-lema {{ color: {SECUNDARIO}; font-size: 0.82rem; margin-top: -0.4rem; }}
  .hv-card {{
    background: {SUPERFICIE}; border: 1px solid {BORDA}; border-radius: 14px;
    padding: 16px 18px; margin-bottom: 12px;
  }}
  .hv-card-titulo {{ font-size: 0.98rem; font-weight: 700; color: {CREME}; }}
  .hv-card-resumo {{ font-size: 0.78rem; color: {SECUNDARIO}; margin-top: 2px; }}
  .hv-kpi {{
    background: {SUPERFICIE}; border: 1px solid {BORDA}; border-radius: 14px; padding: 14px 16px;
  }}
  .hv-kpi-rot {{ font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.08em; color: {SECUNDARIO}; }}
  .hv-kpi-val {{ font-size: 1.5rem; font-weight: 800; letter-spacing: -0.04em; font-variant-numeric: tabular-nums; }}
  .hv-kpi-nota {{ font-size: 0.7rem; color: {SECUNDARIO}; }}
  .hv-selo {{
    display: inline-block; font-size: 0.64rem; font-weight: 700; padding: 2px 8px;
    border-radius: 999px; margin-right: 6px; letter-spacing: 0.03em;
  }}
  .hv-proc {{
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.66rem; color: {SECUNDARIO}; margin-top: 8px;
    border-top: 1px dashed {BORDA}; padding-top: 6px;
  }}
  .hv-barra-trilho {{ background: {BORDA}; border-radius: 999px; height: 7px; width: 100%; }}
  .hv-barra-fill {{ height: 7px; border-radius: 999px; }}
  .hv-cat {{ display: flex; align-items: center; gap: 10px; margin-bottom: 9px; }}
  .hv-cat-nome {{ font-size: 0.78rem; min-width: 120px; color: {CREME}; }}
  .hv-cat-val {{ font-size: 0.75rem; color: {SECUNDARIO}; min-width: 92px; text-align: right;
                 font-variant-numeric: tabular-nums; }}
  .hv-linha {{ border-top: 1px solid {BORDA}; margin: 18px 0 14px; }}
  div[data-testid="stMetricValue"] {{ font-size: 1.4rem; }}
  .stTabs [data-baseweb="tab-list"] {{ gap: 4px; }}
  .stTabs [data-baseweb="tab"] {{
    background: {SUPERFICIE}; border: 1px solid {BORDA}; border-radius: 10px 10px 0 0;
    padding: 8px 18px; font-weight: 600;
  }}
  .stTabs [aria-selected="true"] {{ background: {BORDA}; color: {OURO} !important; }}
</style>
"""

_COR_PLANO = {"free": SECUNDARIO, "pro": AZUL, "total": OURO}
_COR_PRIORIDADE = {"CRITICAL": VERMELHO, "WARNING": AMBAR, "INFO": AZUL}
_ROTULO_CLUSTER = {
    "EXPLORADOR_GLOBAL": "✈️ Explorador Global",
    "URBANO_FOODIE": "🍽️ Urbano Foodie",
    "INVESTIDOR_CAUTELOSO": "📈 Investidor Cauteloso",
    "FAMILIA_ESTRUTURADA": "👨‍👩‍👧 Família Estruturada",
    "DIGITAL_NATIVO": "📱 Digital Nativo",
    "ESTRESSE_FINANCEIRO": "🆘 Estresse Financeiro",
    "MICROEMPREENDEDOR": "🧾 Microempreendedor",
    "NAO_CLASSIFICADO": "⚪ Não classificado",
}


# ══════════════════════════════════════════════════════════════════════
# Formatação
# ══════════════════════════════════════════════════════════════════════

def brl(valor) -> str:
    if valor is None:
        return "—"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def brl_curto(valor) -> str:
    if valor is None:
        return "—"
    if abs(valor) >= 1000:
        return f"R$ {valor/1000:,.1f}k".replace(",", "X").replace(".", ",").replace("X", ".")
    return brl(valor)


def selo(texto: str, cor: str) -> str:
    return (f'<span class="hv-selo" style="background:{cor}22;color:{cor};'
            f'border:1px solid {cor}55">{texto}</span>')


def barra(pct: float, cor: str) -> str:
    largura = max(0.0, min(100.0, pct))
    return (f'<div class="hv-barra-trilho"><div class="hv-barra-fill" '
            f'style="width:{largura:.1f}%;background:{cor}"></div></div>')


# ══════════════════════════════════════════════════════════════════════
# Cache — o pipeline real é caro; a tela não pode rodá-lo a cada clique
# ══════════════════════════════════════════════════════════════════════

@st.cache_data(show_spinner=False, ttl=600)
def _panorama(uid: str) -> dict:
    return P.panorama(uid)


@st.cache_data(show_spinner=False, ttl=600)
def _extrato(uid: str) -> dict:
    return P.extrato(uid)


@st.cache_data(show_spinner=False, ttl=600)
def _feed(uid: str, renda: float) -> dict:
    return P.feed_proativo(uid, renda)


@st.cache_data(show_spinner=False, ttl=600)
def _compromissos(uid: str) -> dict:
    return P.compromissos(uid)


@st.cache_data(show_spinner=False, ttl=600)
def _ritmo(uid: str) -> dict:
    return P.ritmo(uid)


@st.cache_data(show_spinner=False, ttl=600)
def _pipeline(uid: str) -> dict:
    return P.pipeline(uid)


@st.cache_data(show_spinner=False, ttl=600)
def _conta(uid: str) -> dict:
    return P.conta(uid)


@st.cache_data(show_spinner=False, ttl=600)
def _plataforma() -> dict:
    return P.plataforma()


@st.cache_data(show_spinner=False, ttl=900)
def _ferramenta(nome: str, uid: str, chave_args: str, args: dict) -> dict:
    """
    Executa uma ferramenta e guarda o resultado.

    `chave_args` entra na assinatura do cache de propósito: dois parâmetros
    diferentes na mesma ferramenta são duas execuções distintas, e sem ele o
    Streamlit devolveria o primeiro resultado para qualquer valor digitado.
    """
    resultado = F.executar(nome, uid, **args)
    return {
        "texto": resultado.texto_limpo,
        "erro": resultado.erro,
        "segundos": resultado.segundos,
        "confianca": resultado.confianca,
        "cobertura": resultado.cobertura,
        "fontes": resultado.fontes,
        "degradado": resultado.degradado,
    }


# ══════════════════════════════════════════════════════════════════════
# Gating de plano — o dark launch mostra o que TERIA bloqueado
# ══════════════════════════════════════════════════════════════════════

def libera(plano_do_usuario: str, plano_exigido: str) -> bool:
    from app.billing.plans import plan_satisfies

    return plan_satisfies(plano_do_usuario, plano_exigido)


def cartao_bloqueado(ferramenta: F.Ferramenta, plano: str) -> None:
    """
    O que o gating faria — sem esconder a funcionalidade.

    O produto nasce com o bloqueio DESLIGADO (dark launch, doc 16): o sistema
    registra o que teria bloqueado para medir o impacto antes de cobrar. A tela
    faz o mesmo: mostra o cadeado, o plano necessário, e deixa executar.
    """
    st.markdown(
        f'<div class="hv-card" style="border-color:{_COR_PLANO[ferramenta.plano]}55">'
        f'<div class="hv-card-titulo">{ferramenta.icone} {ferramenta.titulo} '
        f'{selo("🔒 " + ferramenta.plano.upper(), _COR_PLANO[ferramenta.plano])}</div>'
        f'<div class="hv-card-resumo">{ferramenta.resumo}</div>'
        f'<div class="hv-proc">Seu plano é <b>{plano}</b>. Em produção o gating está em '
        f'dark launch: registra o bloqueio e deixa passar, para medir o impacto '
        f'antes de cobrar de verdade.</div></div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════
# O cartão de uma ferramenta — coração da interface
# ══════════════════════════════════════════════════════════════════════

def _campos(ferramenta: F.Ferramenta, prefixo: str) -> dict:
    """Os parâmetros que a ferramenta aceita, como controles de formulário."""
    valores: dict = {}
    if not ferramenta.parametros:
        return valores
    colunas = st.columns(min(3, len(ferramenta.parametros)))
    for i, parametro in enumerate(ferramenta.parametros):
        with colunas[i % len(colunas)]:
            chave = f"{prefixo}_{ferramenta.tool}_{parametro.nome}"
            if parametro.tipo == "moeda":
                valores[parametro.nome] = st.number_input(
                    parametro.rotulo, min_value=float(parametro.minimo),
                    max_value=float(parametro.maximo), value=float(parametro.padrao),
                    step=float(parametro.passo), key=chave, help=parametro.ajuda or None,
                )
            elif parametro.tipo == "inteiro":
                valores[parametro.nome] = st.number_input(
                    parametro.rotulo, min_value=int(parametro.minimo),
                    max_value=int(parametro.maximo), value=int(parametro.padrao),
                    step=int(parametro.passo), key=chave, help=parametro.ajuda or None,
                )
            elif parametro.tipo == "opcao":
                valores[parametro.nome] = st.selectbox(
                    parametro.rotulo, options=list(parametro.opcoes),
                    index=list(parametro.opcoes).index(parametro.padrao)
                    if parametro.padrao in parametro.opcoes else 0,
                    key=chave, help=parametro.ajuda or None,
                )
            else:
                valores[parametro.nome] = st.text_input(
                    parametro.rotulo, value=str(parametro.padrao or ""),
                    key=chave, help=parametro.ajuda or None,
                )
    return valores


def _selo_de_procedencia(dados: dict) -> str:
    """
    A linha `[NEXA]` traduzida para a tela.

    É o que separa "R$ 0,00 medido" de "R$ 0,00 porque o detector não rodou" —
    a distinção que, sem marcador, vira "seu banco não cobra tarifas".
    """
    if dados.get("degradado"):
        return (f'{selo("⚠ DEGRADADO", VERMELHO)}<span style="color:{VERMELHO}">'
                f'caminho de fallback: <b>{dados["degradado"]}</b> — '
                f'nenhum número desta resposta é medição.</span>')

    partes = []
    confianca = dados.get("confianca")
    if confianca is not None:
        cor = VERDE if confianca >= 0.5 else AMBAR
        partes.append(selo(f"confiança {confianca:.0%}", cor))
    if dados.get("cobertura"):
        partes.append(selo(f"base {dados['cobertura']}", AZUL))
    if dados.get("fontes"):
        partes.append(f'fontes: {", ".join(dados["fontes"])}')
    if not partes:
        return "sem linha de procedência — resultado direto, sem qualificação"
    return " ".join(partes)


def cartao_de_ferramenta(ferramenta: F.Ferramenta, uid: str, plano: str,
                         prefixo: str, aberto: bool = False) -> None:
    """Um card executável: parâmetros, botão, resultado e procedência."""
    if not libera(plano, ferramenta.plano):
        cartao_bloqueado(ferramenta, plano)
        return

    selos = ""
    if ferramenta.plano != "free":
        selos += selo(ferramenta.plano.upper(), _COR_PLANO[ferramenta.plano])
    if ferramenta.lenta:
        selos += selo("rede externa", SECUNDARIO)

    with st.expander(f"{ferramenta.icone}  {ferramenta.titulo}", expanded=aberto):
        st.markdown(
            f'<div class="hv-card-resumo">{ferramenta.resumo} {selos}</div>'
            f'<div class="hv-proc">tool <code>{ferramenta.tool}</code> · '
            f'{ferramenta.caminho_do_doc}</div>',
            unsafe_allow_html=True,
        )
        argumentos = _campos(ferramenta, prefixo)
        chave_botao = f"{prefixo}_run_{ferramenta.tool}"
        rodar = st.button("Executar", key=chave_botao, type="secondary")
        chave_estado = f"exec::{prefixo}::{ferramenta.tool}"

        if rodar:
            aviso = ("Consultando BACEN/SGS — pode levar alguns segundos…"
                     if ferramenta.lenta else "Rodando o serviço real…")
            with st.spinner(aviso):
                st.session_state[chave_estado] = _ferramenta(
                    ferramenta.tool, uid,
                    "|".join(f"{k}={v}" for k, v in sorted(argumentos.items())),
                    argumentos,
                )

        dados = st.session_state.get(chave_estado)
        if not dados:
            return
        if dados.get("erro"):
            st.error(f"A ferramenta falhou: {dados['erro']}")
            return
        st.code(dados["texto"] or "(sem conteúdo)", language=None, wrap_lines=True)
        st.markdown(
            f'<div class="hv-proc">{_selo_de_procedencia(dados)} · '
            f'{dados["segundos"]}s</div>',
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════
# Superfície 1 — Panorama (o Dashboard do app real)
# ══════════════════════════════════════════════════════════════════════

def kpi(coluna, rotulo: str, valor: str, nota: str = "", cor: str = CREME) -> None:
    coluna.markdown(
        f'<div class="hv-kpi"><div class="hv-kpi-rot">{rotulo}</div>'
        f'<div class="hv-kpi-val" style="color:{cor}">{valor}</div>'
        f'<div class="hv-kpi-nota">{nota}</div></div>',
        unsafe_allow_html=True,
    )


def aba_panorama(uid: str, plano: str) -> None:
    dados = _panorama(uid)
    if not dados.get("ok"):
        st.error(dados.get("erro") or "Pipeline não retornou sucesso.")
        st.info("Rode `python3 -m demo.seed` no diretório `backend/`.")
        return

    perfil = dados.get("profile") or {}
    saude = dados.get("health_score") or {}
    margem_dia = dados.get("safe_to_spend_daily")

    st.markdown("#### Sua margem de hoje")
    colunas = st.columns(4)
    kpi(colunas[0], "Pode gastar hoje", brl(margem_dia),
        "sem ficar negativo em nenhum dia do mês", VERDE if (margem_dia or 0) > 0 else VERMELHO)
    kpi(colunas[1], "Margem do mês", brl(dados.get("safe_to_spend_total")),
        f"pior dia projetado: {brl(dados.get('min_projected_balance'))}", OURO)
    kpi(colunas[2], "Renda detectada", brl(dados.get("monthly_income")),
        f"padrão {dados.get('income_pattern') or '—'} · não é soma de créditos", CREME)
    kpi(colunas[3], "Health score", f"{saude.get('score') or '—'}/100",
        f"{saude.get('level') or '—'} · resiliência {saude.get('resilience') or '—'}",
        VERDE if (saude.get("score") or 0) >= 70 else AMBAR)

    st.markdown('<div class="hv-linha"></div>', unsafe_allow_html=True)

    esquerda, direita = st.columns([3, 2])
    with esquerda:
        st.markdown("**Projeção de caixa — 30 dias**")
        st.caption("Simulação event-driven: nenhum saldo é projetado sem um evento que o justifique.")
        forecast = dados.get("cashflow_forecast")
        if forecast is not None and not forecast.is_empty():
            serie = forecast.select(["date", "projected_balance"]).to_pandas()
            serie = serie.set_index("date")
            st.area_chart(serie, height=210, color=OURO)
            negativos = forecast.filter(forecast["projected_balance"] < 0)
            if len(negativos):
                st.warning(f"{len(negativos)} dia(s) com saldo projetado negativo — "
                           f"a margem é calculada sobre o vale, não sobre o saldo final.")
        else:
            st.info("Sem projeção disponível para esta conta.")

    with direita:
        st.markdown("**Quem o extrato diz que você é**")
        cluster = str(perfil.get("cluster") or "NAO_CLASSIFICADO")
        fss = perfil.get("fss")
        st.markdown(
            f'<div class="hv-card">'
            f'<div class="hv-card-titulo">{_ROTULO_CLUSTER.get(cluster, cluster)}</div>'
            f'<div class="hv-card-resumo">origem: {perfil.get("source") or "—"}'
            + (f' · confiança do ML {perfil["ml_confidence"]:.0%}'
               if perfil.get("ml_confidence") is not None else "")
            + "</div>"
            + (f'<div style="margin-top:10px" class="hv-kpi-rot">Estresse financeiro (FSS)</div>'
               f'<div class="hv-kpi-val" style="color:'
               f'{VERMELHO if fss and fss >= 60 else AMBAR if fss and fss >= 35 else VERDE}">'
               f'{fss:.0f}/100</div>'
               f'<div class="hv-kpi-nota">{perfil.get("fss_level") or "—"}</div>'
               if fss is not None else "")
            + (f'<div class="hv-proc">também detectado: '
               f'{", ".join(perfil.get("secondary") or [])}</div>'
               if perfil.get("secondary") else "")
            + "</div>",
            unsafe_allow_html=True,
        )
        if perfil.get("is_mei"):
            st.info("Sinais de MEI detectados — a separação PF/PJ e o relatório fiscal "
                    "ficam disponíveis em **Organizar**.")

    st.markdown('<div class="hv-linha"></div>', unsafe_allow_html=True)

    st.markdown("**Como estes números foram produzidos** — o ETL de 8 estágios nesta conta")
    etl = _pipeline(uid)
    if etl.get("ok"):
        qualidade = etl.get("qualidade") or {}
        colunas = st.columns([1, 1, 1, 1])
        kpi(colunas[0], "Qualidade da base", qualidade.get("nivel") or "—",
            f"confiança {qualidade['confianca']:.0%}" if qualidade.get("confianca") is not None else "",
            VERDE if (qualidade.get("confianca") or 0) >= 0.7 else AMBAR)
        kpi(colunas[1], "Lacunas no período", str(qualidade.get("lacunas", "—")),
            "intervalos de 2+ dias sem lançamento")
        kpi(colunas[2], "Anomalias", str(qualidade.get("anomalias", "—")),
            "contra o baseline do próprio usuário")
        kpi(colunas[3], "Transações", str(dados.get("n_transactions", "—")),
            "após dedup SHA-256")
        with st.expander("Os 8 estágios, um a um"):
            for estagio in etl["estagios"]:
                st.markdown(
                    f'**{estagio["nome"]}** — {estagio["o_que_faz"]}  \n'
                    f'<span class="hv-proc">nesta conta: {estagio["nesta_conta"]}</span>',
                    unsafe_allow_html=True,
                )
            for recomendacao in qualidade.get("recomendacoes", [])[:5]:
                st.caption(f"• {recomendacao}")


# ══════════════════════════════════════════════════════════════════════
# Superfície 2 — Oportunidades (o Feed)
# ══════════════════════════════════════════════════════════════════════

def aba_feed(uid: str, plano: str, renda: float) -> None:
    st.markdown("#### O que chegou até você")
    st.caption(
        "Cards do `ProactiveNotifier` passados pelo `NotificationRelevanceFilter` — "
        "o mesmo filtro que decide, em produção, o que merece interromper o usuário."
    )

    feed = _feed(uid, renda)
    cards = feed.get("cards") or []
    if not feed.get("ok"):
        st.error(feed.get("erro") or "Feed indisponível.")
    elif not cards:
        st.success("Nenhum card sobreviveu ao filtro de relevância. "
                   "Isso é o produto funcionando: silêncio quando não há o que dizer.")
    else:
        for card in cards:
            prioridade = card.get("priority", "INFO")
            cor = _COR_PRIORIDADE.get(prioridade, AZUL)
            meta = card.get("metadata") or {}
            impacto = meta.get("impact_brl") or meta.get("monthly_gain") or meta.get("amount")
            dica = card.get("action_hint")
            st.markdown(
                f'<div class="hv-card" style="border-left:3px solid {cor}">'
                f'<div class="hv-card-titulo">{card.get("title", "—")} '
                f'{selo(prioridade, cor)}'
                + (selo(brl(impacto), VERDE) if isinstance(impacto, int | float) else "")
                + f'</div><div class="hv-card-resumo">{card.get("message", "")}</div>'
                + (f'<div class="hv-card-resumo" style="color:{OURO};margin-top:6px">'
                   f'→ {dica}</div>' if dica else "")
                + f'<div class="hv-proc">detector: {card.get("type", "—")}</div>'
                + "</div>",
                unsafe_allow_html=True,
            )

    st.markdown('<div class="hv-linha"></div>', unsafe_allow_html=True)
    st.markdown("#### Os detectores por trás do feed")
    st.caption("Cada um roda o serviço de produção sobre o extrato desta conta.")

    for grupo in F.grupos(F.FEED):
        st.markdown(f"**{grupo}**")
        for ferramenta in F.por_superficie(F.FEED):
            if ferramenta.grupo == grupo:
                cartao_de_ferramenta(ferramenta, uid, plano, prefixo="feed")


# ══════════════════════════════════════════════════════════════════════
# Superfície 3 — Organizar
# ══════════════════════════════════════════════════════════════════════

def _bloco_categorias(categorias: list[dict]) -> None:
    for categoria in categorias:
        st.markdown(
            f'<div class="hv-cat">'
            f'<div class="hv-cat-nome">{categoria["categoria"]}</div>'
            f'<div style="flex:1">{barra(categoria["pct_do_maior"], categoria["cor"])}</div>'
            f'<div class="hv-cat-val">{brl_curto(categoria["total"])} '
            f'({categoria["pct_do_gasto"]:.0f}%)</div></div>',
            unsafe_allow_html=True,
        )


def aba_organizar(uid: str, plano: str) -> None:
    dados = _extrato(uid)
    if not dados.get("ok"):
        st.error(dados.get("erro") or "Sem extrato.")
        return

    colunas = st.columns(4)
    kpi(colunas[0], "Receita", brl_curto(dados["entradas"]), "no período carregado", VERDE)
    kpi(colunas[1], "Gastos", brl_curto(dados["saidas"]), "no período carregado", VERMELHO)
    kpi(colunas[2], "Saldo", brl_curto(dados["saldo"]), "receita − gastos",
        VERDE if dados["saldo"] >= 0 else VERMELHO)
    kpi(colunas[3], "Taxa de poupança", f"{dados['taxa_poupanca']:.0f}%",
        "quanto da receita sobrou", OURO)

    st.markdown('<div class="hv-linha"></div>', unsafe_allow_html=True)

    esquerda, direita = st.columns([3, 2])
    with esquerda:
        st.markdown("**Gasto por mês**")
        if dados["meses"]:
            import pandas as pd

            serie = pd.DataFrame({"gasto": dados["gasto_mensal"]}, index=dados["meses"])
            st.bar_chart(serie, height=200, color=OURO)
        else:
            st.info("Sem série mensal.")
    with direita:
        st.markdown("**Por categoria**")
        if dados["categorias"]:
            _bloco_categorias(dados["categorias"])
        else:
            st.info("Sem categorias.")

    pf_pj = dados.get("pf_pj") or {}
    ritmo = _ritmo(uid)
    compromissos = _compromissos(uid)

    esquerda, meio, direita = st.columns(3)
    with esquerda:
        st.markdown("**Pessoal × Empresa**")
        st.caption("Estágio 4 do ETL — regras determinísticas + suas correções.")
        total_pfpj = sum(pf_pj.values()) or 1
        for rotulo, cor in (("PF", VERDE), ("PJ", AZUL), ("UNCERTAIN", SECUNDARIO)):
            valor = pf_pj.get(rotulo, 0.0)
            st.markdown(
                f'<div class="hv-cat"><div class="hv-cat-nome">{rotulo}</div>'
                f'<div style="flex:1">{barra(valor / total_pfpj * 100, cor)}</div>'
                f'<div class="hv-cat-val">{brl_curto(valor)}</div></div>',
                unsafe_allow_html=True,
            )
        if pf_pj.get("UNCERTAIN"):
            st.caption("`UNCERTAIN` é o classificador recusando forçar um rótulo — "
                       "corrigir gera um `context_override`, que vence a regra daí em diante.")

    with meio:
        st.markdown("**Ritmo do mês (burn rate)**")
        if ritmo.get("ok"):
            nivel = ritmo.get("alert_level") or "—"
            cor = {"OK": VERDE, "ATTENTION": AMBAR,
                   "WARNING": AMBAR, "CRITICAL": VERMELHO}.get(nivel, SECUNDARIO)
            st.markdown(
                f'<div class="hv-kpi"><div class="hv-kpi-rot">Alerta</div>'
                f'<div class="hv-kpi-val" style="color:{cor}">{nivel}</div>'
                f'<div class="hv-kpi-nota">ritmo {ritmo.get("burn_rate_ratio", 0):.2f}× '
                f'do esperado · dia {ritmo.get("current_day", "—")}/'
                f'{ritmo.get("days_in_month", "—")}</div></div>',
                unsafe_allow_html=True,
            )
            fora = ritmo.get("categories_over_pace") or []
            for categoria in fora[:4]:
                nome = categoria.get("category") if isinstance(categoria, dict) else str(categoria)
                st.caption(f"• {nome} acima do ritmo")
        else:
            st.info(ritmo.get("erro") or "Sem burn rate.")

    with direita:
        st.markdown("**Já comprometido (shadow invoices)**")
        st.caption("O que o saldo da conta não mostra.")
        if compromissos.get("ok") and compromissos["eventos"]:
            st.markdown(
                f'<div class="hv-kpi"><div class="hv-kpi-rot">Total nos próximos 30 dias</div>'
                f'<div class="hv-kpi-val" style="color:{AMBAR}">'
                f'{brl_curto(compromissos["total_mensal"])}</div>'
                f'<div class="hv-kpi-nota">{len(compromissos["eventos"])} compromisso(s)</div>'
                f'</div>', unsafe_allow_html=True)
            for evento in compromissos["eventos"][:5]:
                st.caption(f"• {evento['descricao']} — {brl(evento['valor'])} "
                           f"({evento['tipo']}, venc. {evento['vencimento']})")
        else:
            st.info("Nenhum compromisso futuro detectado.")

    with st.expander(f"Lançamentos recentes ({dados['n_transacoes']} no total)"):
        import pandas as pd

        tabela = pd.DataFrame(dados["recentes"])
        if not tabela.empty:
            st.dataframe(tabela, use_container_width=True, hide_index=True)

    st.markdown('<div class="hv-linha"></div>', unsafe_allow_html=True)
    st.markdown("#### Suas ferramentas")
    st.caption("As 22 análises que você abre quando quer — cada uma é a mesma "
               "ferramenta que o agente chama no Chat.")

    abas = st.tabs(F.grupos(F.ORGANIZAR))
    for aba, grupo in zip(abas, F.grupos(F.ORGANIZAR)):
        with aba:
            for ferramenta in F.por_superficie(F.ORGANIZAR):
                if ferramenta.grupo == grupo:
                    cartao_de_ferramenta(ferramenta, uid, plano, prefixo="org")
            if grupo == "Conta":
                _bloco_conta(uid)


def _bloco_conta(uid: str) -> None:
    """Planos, limites e o inventário LGPD — docs 16 e 17."""
    info = _conta(uid)
    if not info.get("ok"):
        return
    st.markdown("**Planos**")
    colunas = st.columns(3)
    for coluna, plano in zip(colunas, info["planos"]):
        marca = "✓ seu plano" if plano["e_o_seu"] else (
            "incluído" if plano["ja_liberado"] else "não liberado")
        cor = _COR_PLANO.get(plano["id"], SECUNDARIO)
        coluna.markdown(
            f'<div class="hv-card" style="border-color:{cor}55">'
            f'<div class="hv-card-titulo">{plano["nome"]} '
            f'{selo(marca, cor if plano["ja_liberado"] else SECUNDARIO)}</div>'
            f'<div class="hv-kpi-val" style="color:{cor}">'
            f'{"grátis" if not plano["preco"] else brl(plano["preco"]) + "/mês"}</div>'
            f'<div class="hv-card-resumo">{plano["chamada"]}</div>'
            f'<div class="hv-proc">' + "<br>".join(f"• {f}" for f in plano["inclui"]) +
            "</div></div>",
            unsafe_allow_html=True,
        )

    st.markdown("**Limites de uso no seu plano**")
    for limite in info["limites"]:
        st.caption(f"• `{limite['contador']}` — **{limite['no_seu_plano']}** "
                   f"({limite['descricao']})")

    with st.expander(f"O que a HIVE guarda sobre você — {len(info['inventario_lgpd'])} tabelas (LGPD)"):
        st.caption(
            "`GET /privacy/export` percorre todas elas (art. 18, V) e "
            "`DELETE /privacy/erase` apaga (art. 18, VI) — incluindo os threads do "
            "checkpointer do agente, que guardam a cópia mais rica: suas perguntas "
            "e o retorno de cada ferramenta chamada."
        )
        for item in info["inventario_lgpd"]:
            st.caption(f"• `{item['tabela']}` — {item['o_que_guarda']}")


# ══════════════════════════════════════════════════════════════════════
# Superfície 4 — Chat (o agente LangGraph real, com as 31 ferramentas)
# ══════════════════════════════════════════════════════════════════════

_PERGUNTAS_SUGERIDAS = (
    "Como estão minhas finanças esse mês?",
    "Posso comprar um carro de R$ 60.000? Tenho R$ 15.000 de entrada.",
    "Meu banco está me cobrando alguma coisa indevida?",
    "Tenho 10 mil parados, onde rende mais?",
    "Qual cartão vale mais a pena para o meu perfil?",
    "Quanto eu paguei de tarifa nos últimos meses?",
)


@st.cache_resource(show_spinner="Construindo o agente (31 ferramentas)…")
def _agente():
    """
    O agente de produção, construído uma vez por processo.

    `cache_resource` e não `cache_data`: o grafo carrega as 31 definições de
    ferramenta e abre o checkpointer — reconstruir a cada rerun do Streamlit
    tornaria o chat inutilizável.
    """
    from app.agent.graph import build_financial_agent

    return build_financial_agent()


def _tem_llm() -> bool:
    from app.core.config import settings

    return bool(settings.ANTHROPIC_API_KEY or settings.OPENAI_API_KEY)


def _responder(uid: str, pergunta: str, sessao: str) -> dict:
    """
    Uma volta do agente, pelo mesmo caminho do endpoint `/chat`.

    As quatro camadas contra prompt injection estão todas aqui:
      1. o `user_id` vem da sessão autenticada, não do corpo da mensagem;
      2. qualquer `[user_id=...]` forjado no texto é neutralizado ANTES do LLM;
      3. o system prompt manda ignorar outro user_id (vem do `build`);
      4. `usuario_da_requisicao` + `vincular_ao_usuario` sobrescrevem o
         argumento que o modelo passa para a ferramenta — a única
         determinística das quatro.
    """
    import re

    from langchain_core.messages import HumanMessage

    from app.agent.identity import usuario_da_requisicao
    from app.agent.memoria import thread_id_de

    limpa = re.sub(r"\[\s*user_id\s*=[^\]]*\]", "[removido]", pergunta, flags=re.IGNORECASE)
    entrada = {"messages": [HumanMessage(content=f"[user_id={uid}] {limpa}")]}
    config = {"configurable": {"thread_id": thread_id_de(uid, sessao)}}

    with usuario_da_requisicao(uid):
        estado = _agente().invoke(entrada, config=config)

    mensagens = estado.get("messages", [])
    conteudo = mensagens[-1].content if mensagens else ""
    if isinstance(conteudo, list):
        conteudo = "".join(b.get("text", "") for b in conteudo if isinstance(b, dict))
    ferramentas = [
        chamada["name"]
        for m in mensagens
        for chamada in (getattr(m, "tool_calls", None) or [])
    ]
    return {"resposta": conteudo, "ferramentas": ferramentas,
            "sanitizada": limpa != pergunta}


def aba_chat(uid: str, plano: str) -> None:
    st.markdown("#### Consultor HIVE")
    st.caption(
        "O agente ReAct do produto: ele **pensa → escolhe a ferramenta → lê o "
        "resultado → responde**. As 31 do catálogo estão à disposição dele; o "
        "traço embaixo de cada resposta mostra quais ele decidiu usar."
    )

    if not _tem_llm():
        st.warning(
            "Sem `ANTHROPIC_API_KEY` (ou `OPENAI_API_KEY`) no ambiente, o chat não roda — "
            "e o produto responde **503 com mensagem clara**, nunca uma resposta "
            "fabricada. As outras três superfícies funcionam inteiras."
        )
        st.caption(f"Ambiente carregado de: {_ORIGEM_ENV}")
        st.markdown("**As perguntas que ele responderia:**")
        for pergunta in _PERGUNTAS_SUGERIDAS:
            st.caption(f"• {pergunta}")
        return

    historico = st.session_state.setdefault(f"chat::{uid}", [])
    usadas = len([m for m in historico if m["papel"] == "user"])
    limite = 5 if plano == "free" else None

    if limite is not None:
        restantes = max(0, limite - usadas)
        cor = VERDE if restantes > 2 else AMBAR if restantes else VERMELHO
        st.markdown(
            f'<div class="hv-proc">{selo(f"{restantes}/{limite} mensagens hoje", cor)} '
            f'o plano Free tem 5 mensagens de IA por dia (contador '
            f'<code>chat_messages</code>); no Pro é ilimitado.</div>',
            unsafe_allow_html=True,
        )

    if not historico:
        st.markdown("**Comece por aqui**")
        colunas = st.columns(3)
        for i, pergunta in enumerate(_PERGUNTAS_SUGERIDAS):
            if colunas[i % 3].button(pergunta, key=f"sug_{i}", use_container_width=True):
                st.session_state["pergunta_pendente"] = pergunta
                st.rerun()

    for mensagem in historico:
        with st.chat_message("user" if mensagem["papel"] == "user" else "assistant"):
            st.markdown(mensagem["texto"])
            if mensagem.get("ferramentas"):
                st.markdown(
                    '<div class="hv-proc">ferramentas chamadas: '
                    + " ".join(selo(f, OURO) for f in mensagem["ferramentas"])
                    + "</div>", unsafe_allow_html=True)

    pendente = st.session_state.pop("pergunta_pendente", None)
    digitada = st.chat_input("Pergunte sobre a sua vida financeira…")
    pergunta = pendente or digitada
    if not pergunta:
        return

    if limite is not None and usadas >= limite:
        st.error("Cota diária do plano Free esgotada (5 mensagens). "
                 "Em produção o usuário vê o upgrade para Pro — e a cota só é "
                 "consumida **depois** da checagem de LLM, para ninguém perder "
                 "mensagem por erro de configuração nosso.")
        return

    historico.append({"papel": "user", "texto": pergunta})
    with st.chat_message("user"):
        st.markdown(pergunta)

    with st.chat_message("assistant"):
        with st.spinner("O agente está consultando os seus dados…"):
            try:
                saida = _responder(uid, pergunta, st.session_state["sessao"])
            except Exception as exc:
                st.error(f"O agente falhou: {type(exc).__name__}: {exc}")
                historico.pop()
                return
        st.markdown(saida["resposta"])
        if saida["sanitizada"]:
            st.info("Sua mensagem continha um `[user_id=…]` — ele foi neutralizado "
                    "antes de chegar ao modelo (camada 2 da defesa contra prompt "
                    "injection). Tente: o agente só acessa a conta autenticada.")
        if saida["ferramentas"]:
            st.markdown(
                '<div class="hv-proc">ferramentas chamadas: '
                + " ".join(selo(f, OURO) for f in saida["ferramentas"])
                + "</div>", unsafe_allow_html=True)
    historico.append({"papel": "assistant", "texto": saida["resposta"],
                      "ferramentas": saida["ferramentas"]})

    if st.button("Apagar esta conversa"):
        from app.agent.memoria import esquecer_conversas

        st.session_state[f"chat::{uid}"] = []
        try:
            resultado = esquecer_conversas(uid)
            st.success(f"Histórico apagado — {resultado} "
                       "(as linhas do banco E os threads do checkpointer).")
        except Exception as exc:
            st.warning(f"Threads do checkpointer não apagados: {exc}")
        st.rerun()


# ══════════════════════════════════════════════════════════════════════
# Entrada — a tela de login do app real, com as contas conectadas
# ══════════════════════════════════════════════════════════════════════

_RETRATO = {
    "ana": ("CLT · delivery pesado", "Renda estável detectada, margem alta, "
            "assinatura que subiu de preço, poupança rendendo abaixo do CDI."),
    "bruno": ("MEI · maquininha", "Classificador PF/PJ, DAS e teto do MEI, "
              "gastos pessoais e do negócio na mesma conta."),
    "carla": ("Renda em queda", "FSS em alerta, juros de rotativo e cheque "
              "especial crescendo, margem apertada, tarifa recorrente."),
}


def tela_de_entrada() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    _, meio, _ = st.columns([1, 2, 1])
    with meio:
        st.markdown(
            '<div style="text-align:center;margin-top:8vh">'
            '<div class="hv-marca">🐝 HIVE</div>'
            '<div class="hv-lema">O advogado financeiro que os bancos '
            'não querem que você tenha.</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="hv-linha"></div>', unsafe_allow_html=True)
        st.markdown("**Entre com uma conta conectada**")
        st.caption(
            "Três personas cujos dados passaram pelo ETL de verdade — "
            "Pluggy-style → validação → ingestor → classificador → PF/PJ → Postgres. "
            "Cada uma acende inteligências diferentes do produto."
        )

        for chave, persona in PERSONAS.items():
            titulo, descricao = _RETRATO.get(chave, ("", ""))
            cor = _COR_PLANO.get(persona.plan, SECUNDARIO)
            bancos = ", ".join(b.name for b in persona.banks) or "—"
            st.markdown(
                f'<div class="hv-card">'
                f'<div class="hv-card-titulo">{persona.full_name} '
                f'{selo(persona.plan.upper(), cor)}</div>'
                f'<div class="hv-card-resumo">{titulo} — {descricao}</div>'
                f'<div class="hv-proc">{persona.email} · bancos: {bancos}</div></div>',
                unsafe_allow_html=True,
            )
            if st.button(f"Entrar como {persona.full_name}", key=f"login_{chave}",
                         use_container_width=True):
                st.session_state["persona"] = chave
                st.session_state["sessao"] = f"demo-{chave}"
                st.rerun()

        st.markdown('<div class="hv-linha"></div>', unsafe_allow_html=True)
        st.caption(
            "Sem personas no banco? Rode `python3 -m demo.seed` dentro de `backend/`. "
            f"Ambiente carregado de: **{_ORIGEM_ENV}**."
        )


# ══════════════════════════════════════════════════════════════════════
# Barra lateral — a conta, a plataforma e o que roda de madrugada
# ══════════════════════════════════════════════════════════════════════

def barra_lateral(chave_persona: str, uid: str, plano: str) -> None:
    persona = PERSONAS[chave_persona]
    st.sidebar.markdown(
        '<div class="hv-marca" style="font-size:1.4rem">🐝 HIVE</div>'
        '<div class="hv-lema">demo em produção</div>',
        unsafe_allow_html=True,
    )
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        f"**{persona.full_name}**  \n"
        f'<span class="hv-proc">{persona.email} · plano '
        f'{selo(plano.upper(), _COR_PLANO.get(plano, SECUNDARIO))}</span>',
        unsafe_allow_html=True,
    )

    st.sidebar.caption("**Bancos conectados**")
    for banco in persona.banks:
        saldo = sum(c.balance for c in banco.accounts)
        st.sidebar.caption(f"• {banco.name} ({banco.role}) — {brl_curto(saldo)}")

    st.sidebar.markdown("---")
    if st.sidebar.button("Trocar de conta", use_container_width=True):
        for chave in [k for k in st.session_state if k.startswith(("exec::", "chat::"))]:
            del st.session_state[chave]
        st.session_state.pop("persona", None)
        st.rerun()
    if st.sidebar.button("Recarregar dados (limpar cache)", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    plataforma = _plataforma()
    if plataforma.get("ok"):
        st.sidebar.markdown("---")
        st.sidebar.caption("**O que roda sem você abrir o app**")
        for robo in plataforma["robos"]:
            st.sidebar.caption(f"`{robo['quando']}` {robo['job']}")
        st.sidebar.markdown("---")
        st.sidebar.caption("**Plataforma**")
        checkpointer = plataforma["checkpointer"]
        st.sidebar.caption(
            f"memória do agente: `{checkpointer}`"
            + (f"  \nmotivo: {plataforma['checkpointer_motivo']}"
               if plataforma.get("checkpointer_motivo") else "")
        )
        st.sidebar.caption(
            f"LLM: `{plataforma['llm_provider']}` / `{plataforma['llm_model']}` — "
            + ("configurado ✓" if plataforma["llm_configurado"] else "**sem chave**")
        )
        st.sidebar.caption(f"ambiente: {_ORIGEM_ENV}")
    st.sidebar.markdown("---")
    st.sidebar.caption(
        f"{len(F.CATALOGO)} ferramentas do registro `AGENT_TOOLS`, "
        "verificadas contra a interface na importação."
    )


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def main() -> None:
    if "persona" not in st.session_state:
        tela_de_entrada()
        return

    st.markdown(CSS, unsafe_allow_html=True)
    chave = st.session_state["persona"]
    persona = PERSONAS[chave]
    uid, plano = persona.user_id, persona.plan

    barra_lateral(chave, uid, plano)

    st.markdown(
        f'<div class="hv-marca">🐝 HIVE</div>'
        f'<div class="hv-lema">Olá, {persona.full_name.split()[0]} — '
        f'aqui está o que os seus dados dizem hoje.</div>',
        unsafe_allow_html=True,
    )

    panorama, oportunidades, organizar, chat = st.tabs(
        ["Panorama", "Oportunidades", "Organizar", "Chat IA"]
    )
    with panorama:
        aba_panorama(uid, plano)
    with oportunidades:
        dados = _panorama(uid)
        aba_feed(uid, plano, float(dados.get("monthly_income") or 0.0))
    with organizar:
        aba_organizar(uid, plano)
    with chat:
        aba_chat(uid, plano)


main()
