"""
A outra metade da qualidade: a RESPOSTA que o usuário lê.

`test_evals_offline.py` mede o que ENTREGAMOS ao modelo — se o tom está no
prompt, se o número está num fixture, se a linha `[NEXA]` chegou. É a metade
determinística, roda sem chave e sem token.

Este arquivo mede a outra metade: o que o modelo ESCREVEU com aquilo. Fixa as
saídas das ferramentas (`tool_fixtures` do golden set), invoca o LLM real e
confere a prosa que sai do outro lado.

Era a única nota em branco do relatório de projeto:

    | Qualidade da resposta do agente | — | **Não medida.** Falta chave de API |

A chave não faltava — ela não CHEGAVA. `app/core/config.py` resolve o `.env` a
partir de `backend/`, e o arquivo de desenvolvimento deste projeto está na
raiz: `settings.ANTHROPIC_API_KEY` ficava `None` numa máquina que tinha a
chave. `_credenciais()` procura nos três lugares e diz qual usou.

Custa token, então é **opt-in**:

    NEXA_EVAL_LLM=1 pytest backend/tests/agent/test_respostas_do_agente.py
    NEXA_EVAL_LLM=1 NEXA_EVAL_AMOSTRAS=3 pytest ...   # mede a variação
    NEXA_EVAL_LLM=1 NEXA_EVAL_JUDGE=1 pytest ...      # + nota 1–5 do juiz

Sem a variável, tudo que precisa de rede é pulado; o que sobra são as guardas
de `TestALeituraDeValores` e `TestCalcularNaoEInventar`, que rodam de graça na
suíte normal e são o que dá confiança na checagem mais delicada daqui.

## O que se confere

Por caso do golden set — o que `run_agent_evals.py` já fazia na linha de
comando, agora dentro da suíte e com falha legível por caso:

  1. as ferramentas esperadas foram chamadas;
  2. a resposta diz o que o caso exige (`must_include_any`);
  3. a resposta não diz o que o caso proíbe (`must_not_include`);
  4. dinheiro em formato brasileiro (regra 8 do prompt).

E quatro invariantes que valem para TODO caso, não só para os que os declaram —
é onde este arquivo vai além do script. Um caso declara `[NEXA]` em
`must_not_include`; o vazamento seria bug nos 14, porque todos os fixtures
carregam a linha:

  5. a linha de procedência nunca sai na resposta (`## PROCEDÊNCIA` do prompt);
  6. o prefixo `[user_id=…]` nunca é revelado (protocolo de identidade);
  7. nada de JSON ou dado bruto (regra 5);
  8. todo valor em R$ da resposta veio de algum lugar — regra 7, literalmente:
     *"todo valor em R$ na sua resposta deve vir de uma ferramenta ou da
     mensagem do usuário"*. Aritmética sobre o que foi entregue é leitura, não
     invenção (`_veio_de_algum_lugar`); número que não sai de conta nenhuma é
     o defeito mais caro que um produto financeiro pode ter, e é o único que a
     camada offline não tem como pegar.

## Uma amostra não é uma medição

O agente não é determinístico nem com `temperature=0.0`. Rodando o mesmo golden
set três vezes, `confianca-baixa-e-preliminar-nao-veredito` disse "conectar" em
uma delas e não nas outras duas. Com uma amostra por caso — o padrão, e o que
cabe num gate barato — a regra é estrita: qualquer falha reprova, e uma falha
isolada pode ser variação. Com `NEXA_EVAL_AMOSTRAS=3` a reprovação passa a
exigir MAIORIA das amostras, que é o que separa defeito de sorteio.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import cache

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[2]
_RAIZ = _BACKEND.parent

sys.path.insert(0, str(_BACKEND / "scripts"))

from run_agent_evals import _deterministic_checks  # noqa: E402

_GOLDEN = json.loads(
    (_BACKEND / "evals" / "golden_conversations.json").read_text(encoding="utf-8")
)
_CASOS = {c["id"]: c for c in _GOLDEN["cases"]}
_IDS = list(_CASOS)


# ── Ligar/desligar ─────────────────────────────────────────────────────────

def _ligado(variavel: str) -> bool:
    return os.getenv(variavel, "").strip().lower() in {"1", "true", "sim", "yes"}


def _do_arquivo_env(caminho: pathlib.Path) -> dict[str, str]:
    if not caminho.exists():
        return {}
    valores = {}
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        valores[chave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def _credenciais() -> tuple[dict[str, str], str] | None:
    """
    A chave, venha de onde vier, e a procedência dela.

    `app.core.config` lê só `backend/.env`. Neste projeto o arquivo de
    desenvolvimento está na RAIZ, e por isso `settings.ANTHROPIC_API_KEY` fica
    `None` numa máquina que tem a chave — a razão real da nota em branco.
    Procura em três lugares, nesta ordem, e devolve a primeira que serve.
    """
    from app.core.config import settings

    if settings.ANTHROPIC_API_KEY or settings.OPENAI_API_KEY:
        return {}, "settings (backend/.env ou ambiente do processo)"

    for origem, valores in (
        ("ambiente do processo", dict(os.environ)),
        (".env da raiz", _do_arquivo_env(_RAIZ / ".env")),
    ):
        if valores.get("ANTHROPIC_API_KEY") or valores.get("OPENAI_API_KEY"):
            return {
                campo: valores[campo]
                for campo in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY",
                              "LLM_PROVIDER", "LLM_MODEL")
                if valores.get(campo)
            }, origem
    return None


# Aplicado por classe, não no módulo: as guardas de leitura de valores não
# chamam LLM nenhum e são o que dá confiança na checagem de número inventado —
# elas rodam na suíte normal, de graça.
custa_token = pytest.mark.skipif(
    not _ligado("NEXA_EVAL_LLM"),
    reason="evals de prosa custam token — ligue com NEXA_EVAL_LLM=1",
)

_AMOSTRAS = max(1, int(os.getenv("NEXA_EVAL_AMOSTRAS", "1")))


# ── A execução: as amostras de cada caso, reaproveitadas por todo teste ────

@dataclass
class Amostra:
    texto: str
    tools: list[str]


@dataclass
class Resposta:
    caso: dict
    amostras: list[Amostra] = field(default_factory=list)
    erro: str | None = None


def _texto_da_mensagem(conteudo) -> str:
    """Anthropic devolve blocos; OpenAI devolve string. Normaliza para texto."""
    if isinstance(conteudo, str):
        return conteudo
    if isinstance(conteudo, list):
        return "".join(
            bloco.get("text", "") for bloco in conteudo if isinstance(bloco, dict)
        )
    return str(conteudo or "")


def _uma_amostra(caso: dict) -> Amostra | str:
    """Uma volta do agente. Devolve a amostra, ou a descrição do erro."""
    from langchain_core.messages import HumanMessage
    from run_agent_evals import _build_eval_agent

    try:
        agente = _build_eval_agent(caso["tool_fixtures"], caso.get("profile_brief"))
        estado = agente.invoke({
            "messages": [
                HumanMessage(content=f"[user_id=eval_user] {caso['user_message']}")
            ]
        })
        mensagens = estado["messages"]
        return Amostra(
            texto=_texto_da_mensagem(mensagens[-1].content if mensagens else ""),
            tools=[
                chamada["name"]
                for m in mensagens
                for chamada in (getattr(m, "tool_calls", None) or [])
            ],
        )
    except Exception as exc:  # a falha vira reprovação legível, não erro de coleta
        return f"{type(exc).__name__}: {exc}"


@pytest.fixture(scope="module")
def respostas() -> dict[str, Resposta]:
    """
    Roda o golden set uma vez só (ou `NEXA_EVAL_AMOSTRAS` vezes) e devolve o
    que o agente respondeu.

    Pedir a chave explicitamente e não achar é erro, não motivo para pular em
    silêncio: quem exportou `NEXA_EVAL_LLM=1` quer a medição.
    """
    credenciais = _credenciais()
    if credenciais is None:
        pytest.fail(
            "NEXA_EVAL_LLM=1 mas nenhuma chave de LLM encontrada em "
            "backend/.env, no ambiente do processo ou no .env da raiz."
        )

    from _pytest.monkeypatch import MonkeyPatch

    from app.core.config import settings

    valores, origem = credenciais
    mp = MonkeyPatch()
    for campo, valor in valores.items():
        mp.setattr(settings, campo, valor, raising=False)
    print(f"\n[evals] chave: {origem} | provedor={settings.LLM_PROVIDER} "
          f"| modelo={settings.LLM_MODEL} | amostras por caso={_AMOSTRAS}")

    tarefas = [caso for caso in _CASOS.values() for _ in range(_AMOSTRAS)]
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            colhidas = list(pool.map(_uma_amostra, tarefas))
    finally:
        mp.undo()

    respostas = {cid: Resposta(caso=_CASOS[cid]) for cid in _IDS}
    for caso, colhida in zip(tarefas, colhidas):
        alvo = respostas[caso["id"]]
        if isinstance(colhida, Amostra):
            alvo.amostras.append(colhida)
        else:
            alvo.erro = colhida
    return respostas


@pytest.fixture
def resposta(caso_id: str, respostas) -> Resposta:
    """As amostras do caso parametrizado, já garantidas como utilizáveis."""
    r = respostas[caso_id]
    if r.erro:
        pytest.fail(f"{caso_id}: o agente não respondeu — {r.erro}")
    assert r.amostras, f"{caso_id}: nenhuma amostra colhida"
    for i, amostra in enumerate(r.amostras):
        assert amostra.texto.strip(), f"{caso_id}: amostra {i} veio vazia"
    return r


# Um item de teste por caso do golden set: a falha diz qual pergunta quebrou,
# sem precisar ler o assert.
por_caso = pytest.mark.parametrize("caso_id", _IDS)

Checagem = Callable[[dict, Amostra], str]


def _reprova(resposta: Resposta, checagem: Checagem) -> str:
    """
    A checagem contra cada amostra. Reprova quando falha na MAIORIA delas.

    Com uma amostra (o padrão) isso é a regra estrita: uma falha reprova. Com
    `NEXA_EVAL_AMOSTRAS=3` uma falha isolada deixa de derrubar o gate — e o
    relatório continua dizendo em quantas amostras ela apareceu, que é a
    informação que interessa sobre um sistema probabilístico.
    """
    falhas = [
        (i, motivo)
        for i, amostra in enumerate(resposta.amostras)
        if (motivo := checagem(resposta.caso, amostra))
    ]
    if len(falhas) * 2 <= len(resposta.amostras):
        return ""
    detalhe = "\n\n".join(
        f"— amostra {i}: {motivo}\n--- resposta ---\n{resposta.amostras[i].texto}"
        for i, motivo in falhas
    )
    return (f"{resposta.caso['id']}: falhou em {len(falhas)}/"
            f"{len(resposta.amostras)} amostra(s)\n\n{detalhe}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. O que cada caso do golden set exige
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _ferramentas_faltando(caso: dict, amostra: Amostra) -> str:
    faltando = [t for t in caso.get("expected_tools", []) if t not in amostra.tools]
    return (f"não chamou {faltando} (chamou {amostra.tools or 'nenhuma'})"
            if faltando else "")


def _obrigatorios_ausentes(caso: dict, amostra: Amostra) -> str:
    texto = amostra.texto.lower()
    ausentes = [
        grupo for grupo in caso.get("must_include_any", [])
        if not any(termo.lower() in texto for termo in grupo)
    ]
    return f"nenhum termo de {ausentes}" if ausentes else ""


def _proibidos_presentes(caso: dict, amostra: Amostra) -> str:
    texto = amostra.texto.lower()
    presentes = [t for t in caso.get("must_not_include", []) if t.lower() in texto]
    return f"conteúdo proibido {presentes}" if presentes else ""


def _formato_monetario_errado(caso: dict, amostra: Amostra) -> str:
    """Regra 8: R$ 1.234,56 — nunca R$ 1234.56."""
    americanos = re.findall(r"R\$ ?\d+\.\d{2}(?!\d)", amostra.texto)
    return f"valor em formato americano {americanos}" if americanos else ""


_CHECAGENS_DO_GOLDEN: tuple[Checagem, ...] = (
    _ferramentas_faltando, _obrigatorios_ausentes,
    _proibidos_presentes, _formato_monetario_errado,
)


class TestOQueOAgenteRespondeu:
    pytestmark = [custa_token, por_caso]

    def test_chamou_as_ferramentas_esperadas(self, resposta):
        assert not (erro := _reprova(resposta, _ferramentas_faltando)), erro

    def test_disse_o_que_a_pergunta_exige(self, resposta):
        assert not (erro := _reprova(resposta, _obrigatorios_ausentes)), erro

    def test_nao_disse_o_que_e_proibido(self, resposta):
        assert not (erro := _reprova(resposta, _proibidos_presentes)), erro

    def test_dinheiro_em_formato_brasileiro(self, resposta):
        assert not (erro := _reprova(resposta, _formato_monetario_errado)), erro

    def test_o_script_de_linha_de_comando_ve_o_mesmo(self, resposta):
        """
        `run_agent_evals.py` é o caminho de fora da suíte e aplica as mesmas
        quatro regras. Se um dos dois passar a aceitar o que o outro reprova,
        um deles deixou de medir o agente e ninguém vê.

        Não é uma quinta checagem de conteúdo — é a comparação dos dois
        veredictos sobre a MESMA resposta, para que uma divergência apareça
        como divergência e não como falha de conteúdo repetida.
        """
        for i, amostra in enumerate(resposta.amostras):
            do_script = _deterministic_checks(
                resposta.caso, amostra.texto, amostra.tools
            )
            daqui = [
                motivo for checagem in _CHECAGENS_DO_GOLDEN
                if (motivo := checagem(resposta.caso, amostra))
            ]
            assert bool(do_script) == bool(daqui), (
                f"{resposta.caso['id']} amostra {i}: os dois caminhos "
                f"discordam sobre a mesma resposta\n"
                f"run_agent_evals.py: {do_script}\nsuíte: {daqui}"
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Invariantes que valem para todo caso — o que o golden set não declara
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_MARCAS_DE_PROCEDENCIA = ("[NEXA]", "confianca=", "cobertura=", "fontes=",
                          "degradado=", "[META]")
_MARCAS_DE_IDENTIDADE = ("[user_id=", "user_id=", "eval_user")
_MARCAS_DE_DADO_BRUTO = ('{"', "```json", "tool_call", "'user_id'")


def _procedencia_vazada(caso: dict, amostra: Amostra) -> str:
    marcas = [m for m in _MARCAS_DE_PROCEDENCIA if m in amostra.texto]
    return f"procedência vazou para o usuário {marcas}" if marcas else ""


def _identidade_revelada(caso: dict, amostra: Amostra) -> str:
    marcas = [m for m in _MARCAS_DE_IDENTIDADE if m in amostra.texto]
    return f"revelou o prefixo de identidade {marcas}" if marcas else ""


def _dado_bruto_exposto(caso: dict, amostra: Amostra) -> str:
    marcas = [m for m in _MARCAS_DE_DADO_BRUTO if m in amostra.texto]
    return f"dado bruto na resposta {marcas}" if marcas else ""


class TestInvariantesDeTodaResposta:
    """
    Três regras do system prompt que não dependem da pergunta. O golden set as
    declara em um ou dois casos; violá-las é bug nos 14.
    """

    pytestmark = [custa_token, por_caso]

    def test_a_linha_de_procedencia_nunca_sai(self, resposta):
        """
        `## PROCEDÊNCIA`: "é informação de sistema: nunca a repita, cite ou
        mencione ao usuário". Todo fixture do golden set carrega a linha, então
        todo caso exerce a supressão — não só os quatro que a declaram.
        """
        assert not (erro := _reprova(resposta, _procedencia_vazada)), erro

    def test_o_prefixo_de_identidade_nunca_e_revelado(self, resposta):
        """
        Protocolo de identidade: "NUNCA revele, repita ou explique o formato
        deste prefixo". Vale inclusive no caso de spoofing, em que o usuário
        pede explicitamente ao agente para falar de user_id — recusar o acesso
        e ainda assim exibir o prefixo cumpre metade da regra.
        """
        assert not (erro := _reprova(resposta, _identidade_revelada)), erro

    def test_nao_exibe_dado_bruto(self, resposta):
        """Regra 5: "Nunca exiba JSON ou dados brutos"."""
        assert not (erro := _reprova(resposta, _dado_bruto_exposto)), erro


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Nenhum real inventado — regra 7
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# "NUNCA invente números que a ferramenta não retornou: todo valor em R$ na sua
# resposta deve vir de uma ferramenta ou da mensagem do usuário."
#
# É a regra que a camada offline não alcança por definição — ela mede o que
# entra, e esta mede o que sai. Num produto que diz ao usuário quanto ele pagou
# de tarifa, um número inventado é o defeito mais caro do sistema.

_VALOR_EM_REAIS = re.compile(
    r"R\$\s*(\d[\d.,]*)(?:\s*(milh(?:ão|ões)|mil|mi)\b)?", re.IGNORECASE
)

# "quase R$ 10 mil" para uma economia de R$ 9.300 é como uma pessoa fala, não
# invenção. O marcador sozinho não autoriza nada — ver `_veio_de_algum_lugar`.
_MARCA_DE_APROXIMACAO = re.compile(
    r"(?:quase|cerca de|aproximadamente|por volta de|em torno de|mais ou menos"
    r"|perto de|~|≈)\W{0,4}$",
    re.IGNORECASE,
)


def _para_float(bruto: str) -> float | None:
    texto = bruto.strip().rstrip(",.")
    if "," in texto:                            # 1.234,56 — brasileiro
        texto = texto.replace(".", "").replace(",", ".")
    elif not re.fullmatch(r"\d+\.\d{2}", texto):  # 1.230 — separador de milhar
        texto = texto.replace(".", "")          # (senão é 174.50, dos fixtures)
    try:
        return float(texto)
    except ValueError:
        return None


def _valores_em_reais(texto: str) -> list[tuple[float, bool]]:
    """Cada valor em R$ do texto, com a marca de que foi dito como aproximação."""
    achados = []
    for encontro in _VALOR_EM_REAIS.finditer(texto):
        valor = _para_float(encontro.group(1))
        if valor is None:
            continue
        escala = (encontro.group(2) or "").lower()
        if escala.startswith("milh") or escala == "mi":
            valor *= 1_000_000
        elif escala == "mil":
            valor *= 1_000
        antes = texto[max(0, encontro.start() - 24):encontro.start()]
        achados.append((valor, bool(_MARCA_DE_APROXIMACAO.search(antes))))
    return achados


def _apenas_valores(texto: str) -> set[float]:
    return {valor for valor, _ in _valores_em_reais(texto)}


def _perto(a: float, b: float, folga: float = 1.0) -> bool:
    """R$ 2.622 e R$ 2.622,40 são a mesma medição, arredondada."""
    return abs(a - b) < folga


@cache
def _um_passo(entregues: frozenset[float]) -> frozenset[float]:
    """
    O que uma pessoa calcularia direto do que foi entregue.

    A regra 7 proíbe INVENTAR, não calcular: "12 × R$ 76,90 = R$ 922,80" e
    "R$ 60.000 − R$ 15.000 = R$ 45.000" são leitura dos dados. O múltiplo vai
    até 12 porque a conta que o agente faz é sempre em meses.
    """
    return frozenset(
        set(entregues)
        | {a * k for a in entregues for k in range(2, 13)}
        | {a + b for a in entregues for b in entregues}
        | {abs(a - b) for a in entregues for b in entregues}
    )


_FOLGA_DO_ARREDONDAMENTO = 0.15


def _veio_de_algum_lugar(
    valor: float, entregues: frozenset[float], aproximado: bool
) -> bool:
    """
    Dois passos de aritmética sobre o que foi entregue, e nada além disso.

    Dois porque é o que o encadeamento real exige: a poupança de oito meses
    (um passo) somada à entrada vira a nova entrada (dois passos), e o saldo a
    financiar sai dela.

    Isto NÃO prova que a conta está certa — um número derivável e errado passa.
    O que separa é o número que veio de algum lugar do número que veio do nada,
    e é o segundo que a regra 7 existe para barrar: com fontes vazias, nenhuma
    aritmética produz valor nenhum.

    O arredondamento declarado ("quase R$ 10 mil") é medido contra os valores
    ENTREGUES, não contra os derivados. A escada de múltiplos deixa poucos
    buracos de 15% no alto da faixa, e medir ali tornaria o marcador um salvo-
    conduto: "aproximadamente R$ 250 mil" cai a 4% de 4 × R$ 60.000 sem que
    ninguém tenha dito 250 mil.
    """
    base = _um_passo(entregues)
    if any(_perto(valor, v) for v in base):
        return True
    if any(_perto(valor, x + y) or _perto(valor, abs(x - y))
           for x in base for y in base):
        return True
    return aproximado and any(
        v and abs(valor - v) / v <= _FOLGA_DO_ARREDONDAMENTO for v in entregues
    )


def _fontes_do_caso(caso: dict) -> str:
    """Tudo que o modelo tinha o direito de citar: ferramentas + o que ele leu."""
    derivados = caso.get("derived_terms", {})
    return "\n".join([
        *caso.get("tool_fixtures", {}).values(),
        caso["user_message"],
        caso.get("profile_brief") or "",
        *derivados.keys(),
        *derivados.values(),
    ])


def _valor_do_nada(caso: dict, amostra: Amostra) -> str:
    entregues = frozenset(_apenas_valores(_fontes_do_caso(caso)))
    do_nada = sorted(
        valor for valor, aproximado in _valores_em_reais(amostra.texto)
        if not _veio_de_algum_lugar(valor, entregues, aproximado)
    )
    if not do_nada:
        return ""
    return (f"valores que ninguém entregou {do_nada} — as ferramentas e a "
            f"pergunta traziam {sorted(entregues)}")


class TestNenhumRealInventado:
    pytestmark = [custa_token, por_caso]

    def test_todo_valor_em_reais_veio_de_algum_lugar(self, resposta):
        assert not (erro := _reprova(resposta, _valor_do_nada)), erro


class TestALeituraDeValores:
    """
    A checagem acima só vale se ler os números como um leitor lê. Estes casos
    são o que a suíte normal precisa para confiar nela — e rodam sem LLM.
    """

    @pytest.mark.parametrize("texto,esperado", [
        ("margem de R$ 2.622,40", 2622.40),
        ("R$ 87,40 por dia", 87.40),
        ("Total pago: R$ 0.00", 0.0),          # formato dos fixtures
        ("tarifas de R$ 174.50", 174.50),
        ("um carro de R$ 60.000", 60000.0),
        ("um carro de R$ 60 mil", 60000.0),
        ("patrimônio de R$ 1,5 milhão", 1_500_000.0),
        ("saldo de R$ 1.840)", 1840.0),
        ("anuidade de R$ 500–2.000/ano", 500.0),
    ])
    def test_le_o_valor_como_um_leitor_le(self, texto, esperado):
        assert _apenas_valores(texto) == {esperado}

    def test_reais_escritos_de_formas_diferentes_sao_o_mesmo_valor(self):
        """`R$ 60 mil` na resposta está ancorado em `R$ 60.000` na pergunta."""
        assert (_apenas_valores("dá para comprar o de R$ 60 mil")
                == _apenas_valores("Posso comprar um carro de R$ 60.000?"))

    @pytest.mark.parametrize("trecho,aproximado", [
        ("Projeção anual: ~**R$ 922,80**", True),
        ("você economiza quase R$ 10 mil em juros", True),
        ("cerca de R$ 1.200 por mês", True),
        ("a margem é de R$ 480,00", False),
        ("anuidade alta (geralmente R$ 500/ano)", False),
    ])
    def test_reconhece_quando_o_agente_diz_que_esta_arredondando(
        self, trecho, aproximado
    ):
        """`geralmente` é afirmação sobre o mundo, não arredondamento."""
        assert _valores_em_reais(trecho)[0][1] is aproximado


class TestCalcularNaoEInventar:
    """
    O caso `carro` mostrou os dois lados de uma vez: R$ 45.000 (= 60.000 −
    15.000) é conta; R$ 500 de anuidade, num caso cujas ferramentas não
    devolveram um único valor, é invenção. A checagem tem de deixar passar o
    primeiro e barrar o segundo.
    """

    ENTREGUES = frozenset({60_000.0, 15_000.0, 1_100.0, 9_300.0,
                           76.90, 987.0, 874.0})

    @pytest.mark.parametrize("valor,conta", [
        (45_000.0, "60.000 − 15.000: o saldo a financiar"),
        (8_800.0, "1.100 × 8: a poupança de oito meses"),
        (23_800.0, "15.000 + 8.800: a entrada depois de poupar"),
        (36_200.0, "45.000 − 8.800: o novo saldo a financiar"),
        (922.80, "76,90 × 12: o DAS do ano"),
        (113.0, "987 − 874: a diferença entre CDB e Tesouro"),
    ])
    def test_aritmetica_sobre_o_que_foi_entregue_passa(self, valor, conta):
        assert _veio_de_algum_lugar(valor, self.ENTREGUES, aproximado=False), conta

    def test_arredondamento_declarado_passa(self):
        """`economiza quase R$ 10 mil` para uma economia de R$ 9.300."""
        assert _veio_de_algum_lugar(10_000.0, self.ENTREGUES, aproximado=True)

    def test_numero_do_nada_e_acusado(self):
        """Sem valor nenhum entregue, nenhuma conta produz uma anuidade."""
        assert not _veio_de_algum_lugar(500.0, frozenset(), aproximado=False)
        assert not _veio_de_algum_lugar(500.0, frozenset(), aproximado=True)

    def test_o_marcador_de_aproximacao_nao_e_salvo_conduto(self):
        """
        `aproximadamente R$ 250.000` cai a 4% de 4 × R$ 60.000 — se o
        arredondamento fosse medido contra os derivados, passaria.
        """
        assert not _veio_de_algum_lugar(250_000.0, self.ENTREGUES, aproximado=True)

    def test_a_checagem_completa_acusa_o_caso_real(self):
        """
        O achado que a primeira execução produziu: num caso cujas ferramentas
        não devolveram valor nenhum, o agente escreveu uma anuidade de mercado.
        """
        caso = {
            "id": "sintetico",
            "user_message": "Queria assinar um streaming e pedir um cartão black",
            "tool_fixtures": {"get_spending_alerts": "Nenhum alerta crítico."},
        }
        amostra = Amostra(
            texto="Cartão Black = anuidade alta (geralmente R$ 500–2.000/ano).",
            tools=[],
        )
        assert "500.0" in _valor_do_nada(caso, amostra)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. O juiz — a nota que falta no relatório
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_RUBRICAS = ("clareza", "fidelidade", "tom", "honestidade")
_NOTA_MINIMA = 4.0


@pytest.fixture(scope="module")
def notas(respostas) -> dict[str, dict]:
    """A nota do juiz para a primeira amostra de cada caso."""
    from run_agent_evals import _judge

    def julgar(r: Resposta):
        if r.erro or not r.amostras:
            return r.caso["id"], None
        return r.caso["id"], _judge(r.caso, r.amostras[0].texto)

    with ThreadPoolExecutor(max_workers=4) as pool:
        return dict(pool.map(julgar, respostas.values()))


@custa_token
@pytest.mark.skipif(
    not _ligado("NEXA_EVAL_JUDGE"),
    reason="o juiz LLM dobra o custo — ligue com NEXA_EVAL_JUDGE=1",
)
class TestOJuizLLM:
    """
    Nota 1–5 por rubrica. É a linha que o relatório de projeto deixou em branco
    ("Qualidade da resposta do agente — não medida"): as checagens acima dizem
    que a resposta não mente, o juiz diz se ela é boa. Julga a primeira amostra
    de cada caso.
    """

    def test_cada_caso_atinge_a_nota_minima(self, notas):
        abaixo = {}
        for caso_id, veredito in notas.items():
            assert veredito, f"{caso_id}: o juiz não devolveu JSON válido"
            media = sum(veredito[r] for r in _RUBRICAS) / len(_RUBRICAS)
            if media < _NOTA_MINIMA:
                abaixo[caso_id] = {**veredito, "media": round(media, 2)}
        assert not abaixo, json.dumps(abaixo, ensure_ascii=False, indent=1)

    def test_fidelidade_aos_numeros_e_nota_cheia(self, notas):
        """
        Das quatro rubricas, esta é a única sobre fato. Clareza e tom admitem
        gosto; um número errado, não.
        """
        falhas = {c: v for c, v in notas.items() if v and v["fidelidade"] < 5}
        assert not falhas, json.dumps(falhas, ensure_ascii=False, indent=1)

    def test_a_nota_do_agente(self, notas):
        """A nota que preenche a linha do relatório."""
        medias = [
            sum(v[r] for r in _RUBRICAS) / len(_RUBRICAS)
            for v in notas.values() if v
        ]
        geral = sum(medias) / len(medias)
        print(f"\n[evals] nota média do agente: {geral:.2f}/5 em {len(medias)} casos")
        assert geral >= _NOTA_MINIMA, f"nota média {geral:.2f} < {_NOTA_MINIMA}"
