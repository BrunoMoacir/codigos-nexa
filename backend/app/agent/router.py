import asyncio
import logging
from fastapi import APIRouter, HTTPException, Depends, Request, Query, status
from pydantic import BaseModel
from typing import List
from sqlalchemy.orm import Session

from app.agent.identity import usuario_da_requisicao
from app.agent.memoria import esquecer_conversas, thread_id_de
from app.agent.models import ChatMessage
from app.agent.singleton import get_agent as _get_agent
from langchain_core.messages import HumanMessage
from app.core.security import get_current_user, require_owner
from app.core.config import settings
from app.core.database import get_db
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["Agent Chat"])


def _chave_do_limite(request: Request) -> str:
    """
    Chave do rate limit: o usuário autenticado, com o IP como último recurso.

    O resto do projeto limita por IP de propósito (ver `app/main.py`), mas o
    chat é o endpoint caro — cada mensagem é uma conversa inteira de LLM com
    até 31 ferramentas — e o plano Free tem cota diária POR USUÁRIO. Limitar
    por IP faz um escritório ou uma operadora com CGNAT dividir 20 msg/min
    entre todo mundo, e deixa o mesmo usuário multiplicar o teto trocando de
    rede. A doc já descrevia "20/min por usuário"; era o código que divergia.
    """
    autorizacao = request.headers.get("authorization") or ""
    if autorizacao.lower().startswith("bearer "):
        try:
            from jose import jwt

            from app.core.security import ALGORITHM, SECRET_KEY

            payload = jwt.decode(
                autorizacao.split(" ", 1)[1], SECRET_KEY, algorithms=[ALGORITHM]
            )
            sub = payload.get("sub")
            if sub:
                return f"user:{sub}"
        except Exception:
            # Token inválido/expirado: quem decide o 401 é o get_current_user.
            # Aqui só não dá para identificar, então volta a valer o IP.
            pass
    return get_remote_address(request)


limiter = Limiter(key_func=_chave_do_limite)

# Singleton do agente LLM importado do módulo centralizado (app.agent.singleton)
# para evitar instâncias duplicadas entre os pontos de entrada.


class ChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    # A sessão da conversa (a mesma que o cliente mandou; nula = conversa
    # padrão). O app a reaproveita nas próximas mensagens e no histórico.
    session_id: str | None = None
    # Ferramentas que o agente chamou NESTE turno — o app mostra discretamente
    # sob a resposta, para o usuário saber de onde vieram os números.
    tools_used: list[str] = []
    created_at: str | None = None


class ChatClearResponse(BaseModel):
    deleted_count: int
    # Threads do checkpointer efetivamente esquecidos. Antes o endpoint
    # limpava só `chat_messages` e o agente continuava relendo a conversa.
    agent_threads_cleared: int = 0


class ChatHistoryItem(BaseModel):
    id: int
    role: str          # 'user' | 'assistant' (o banco guarda 'human' para o usuário)
    content: str
    session_id: str | None = None
    created_at: str    # ISO 8601


def _texto(conteudo) -> str:
    """
    O conteúdo final do LLM como texto. Com Anthropic ele pode vir como lista
    de blocos ({"type": "text", "text": ...}); gravar a lista crua numa
    coluna Text virava "[{'type': 'text'…}]" no histórico.
    """
    if isinstance(conteudo, str):
        return conteudo
    if isinstance(conteudo, list):
        return "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in conteudo
        )
    return str(conteudo or "")


def _ferramentas_do_turno(messages: list) -> list[str]:
    """
    Ferramentas chamadas desde a última mensagem humana.

    O estado devolvido traz o thread INTEIRO (o checkpointer relê a conversa),
    então olhar todas as mensagens listaria as ferramentas de turnos antigos.
    """
    inicio = 0
    for i, m in enumerate(messages):
        if isinstance(m, HumanMessage):
            inicio = i
    nomes: list[str] = []
    for m in messages[inicio:]:
        for chamada in (getattr(m, "tool_calls", None) or []):
            nome = chamada.get("name") if isinstance(chamada, dict) else getattr(chamada, "name", None)
            if nome and nome not in nomes:
                nomes.append(nome)
    return nomes


def _iso(valor) -> str | None:
    if valor is None:
        return None
    return valor.isoformat() if hasattr(valor, "isoformat") else str(valor)


@router.post("/", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat_with_agent(
    request: Request,
    chat_request: ChatRequest,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Endpoint principal para conversar com a Inteligência Nexa.
    O LLM vai interpretar a mensagem, decidir se precisa chamar alguma Ferramenta
    e retornar a resposta em linguagem natural.
    """
    if chat_request.user_id != current_user:
        raise HTTPException(status_code=403, detail="Não autorizado (token não pertence a este user_id)")

    # A disponibilidade do LLM é verificada ANTES de consumir a cota: o plano
    # Free tem 5 mensagens por dia, e cobrar uma delas para devolver 503 gasta
    # do usuário por um problema de configuração nosso.
    if settings.LLM_PROVIDER == "openai" and (not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "mock"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM (OpenAI) não configurado. Defina OPENAI_API_KEY no backend/.env para usar o chat.",
        )
    if settings.LLM_PROVIDER == "anthropic" and (not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY == "mock"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM (Anthropic) não configurado. Defina ANTHROPIC_API_KEY no backend/.env para usar o chat.",
        )

    # Gating: Free = 5 mensagens de IA/dia (402 quando enforcement ligado).
    # Verifica agora e DEBITA só depois da resposta gravada: debitar antes
    # cobrava a mensagem mesmo quando o agente estourava o tempo (504).
    from app.billing.gating import check_usage, consume_usage
    check_usage(current_user, "chat_messages")

    logger.info("Mensagem recebida de user_id=%s (len=%d)", chat_request.user_id, len(chat_request.message))

    try:
        # Injeta o user_id autenticado como contexto imutável do sistema.
        # IMPORTANTE: este valor vem do token JWT verificado, não do input do usuário.
        # O LLM deve usar EXCLUSIVAMENTE este user_id em todas as chamadas de ferramenta,
        # ignorando qualquer user_id que apareça na mensagem do usuário.
        # Sanitiza tentativas de spoofing do protocolo: qualquer "[user_id=...]"
        # dentro do corpo da mensagem é neutralizado antes de prefixar o real.
        import re
        sanitized_message = re.sub(
            r"\[\s*user_id\s*=[^\]]*\]", "[removido]", chat_request.message,
            flags=re.IGNORECASE,
        )
        inputs = {
            "messages": [
                HumanMessage(content=(
                    f"[user_id={chat_request.user_id}] "
                    f"{sanitized_message}"
                ))
            ]
        }

        # O thread_id agrupa o histórico na memória do agente. SEMPRE
        # prefixado pelo dono: `session_id` vem do corpo da requisição, e sem
        # o prefixo dois usuários que mandassem o mesmo valor compartilhariam
        # a conversa. Ver app/agent/memoria.py.
        thread_id = thread_id_de(current_user, chat_request.session_id)
        config = {"configurable": {"thread_id": thread_id}}

        # Executa o agente em thread pool com timeout de 60s para não bloquear workers
        loop = asyncio.get_event_loop()

        def _executar():
            # O contexto tem de ser fixado DENTRO da thread: run_in_executor
            # não copia contextvars. Daqui para baixo, toda ferramenta usa
            # `current_user` como user_id, ignorando o que o modelo pedir.
            with usuario_da_requisicao(current_user):
                return _get_agent().invoke(inputs, config=config)

        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, _executar),
                timeout=60.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Timeout no agente LLM para user_id=%s", chat_request.user_id)
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Tempo limite excedido. Tente novamente.",
            )

        # A resposta final do LLM estará na última mensagem do state
        messages = result.get("messages", [])
        if not messages:
            raise ValueError("Agente retornou lista de mensagens vazia")
        target_message = _texto(messages[-1].content)

        # Persistir a mensagem do usuário e a resposta do agente, na sessão.
        # As duas recebem o MESMO created_at (now() do Postgres é o início da
        # transação), e ordenar só por ele deixava a ordem indeterminada — a
        # resposta aparecia acima da pergunta. O flush entre elas garante que
        # a pergunta pegue o id menor; o histórico desempata por id.
        pergunta = ChatMessage(user_id=chat_request.user_id, role="human",
                               content=chat_request.message, session_id=chat_request.session_id)
        db.add(pergunta)
        db.flush()
        resposta = ChatMessage(user_id=chat_request.user_id, role="assistant",
                               content=target_message, session_id=chat_request.session_id)
        db.add(resposta)
        db.commit()
        db.refresh(resposta)

        try:
            consume_usage(current_user, "chat_messages")
        except HTTPException:
            # corrida entre duas abas no limite: a resposta já foi gerada e
            # gravada, então entrega; o contador já registrou o uso.
            pass

        return ChatResponse(
            response=target_message,
            session_id=chat_request.session_id,
            tools_used=_ferramentas_do_turno(messages),
            created_at=_iso(resposta.created_at),
        )

    except HTTPException:
        raise
    except Exception as e:
        # A mensagem da exceção ia inteira para o cliente (`{tipo}: {str(e)[:300]}`):
        # erro de driver de banco, URL com credencial, trecho de SQL. O detalhe
        # fica no log, com stack; o cliente recebe texto fixo.
        logger.error(
            "Erro no Agent Chat para user_id=%s: %s", chat_request.user_id, e, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível processar sua mensagem agora. Tente novamente em instantes.",
        )


@router.get("/history", response_model=List[ChatHistoryItem])
def get_chat_history(
    user_id: str = Depends(require_owner),
    limit: int = Query(50, ge=1, le=200, description="Número máximo de mensagens"),
    session_id: str | None = Query(None, description="Só a conversa desta sessão"),
    db: Session = Depends(get_db),
):
    """
    Histórico do usuário em ordem cronológica (mais antigo primeiro).

    Com `session_id`, só a conversa dessa sessão — a mesma que a memória do
    agente guarda. Sem filtro, a tela mostrava mensagens de todas as sessões
    enquanto o agente só lembrava da atual.
    """
    consulta = db.query(ChatMessage).filter(ChatMessage.user_id == user_id)
    if session_id:
        consulta = consulta.filter(ChatMessage.session_id == session_id)
    rows = (
        consulta
        # (created_at, id): pergunta e resposta podiam empatar no timestamp
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    rows = list(reversed(rows))

    return [
        ChatHistoryItem(
            id=row.id,
            role="user" if row.role in ("human", "user") else "assistant",
            content=row.content,
            session_id=getattr(row, "session_id", None),
            created_at=_iso(row.created_at),
        )
        for row in rows
    ]


@router.delete("/history", response_model=ChatClearResponse)
def clear_chat_history(
    user_id: str = Depends(require_owner),
    session_id: str | None = Query(None, description="Apaga só esta conversa"),
    db: Session = Depends(get_db),
) -> ChatClearResponse:
    """
    Remove o histórico do chat para o usuário autenticado.

    Duas coisas, não uma: as linhas de `chat_messages` (o que a UI mostra) e o
    estado do agente no checkpointer (o que o LLM relê a cada turno). Apagar só
    a primeira dava ao usuário a impressão de ter limpado a conversa enquanto o
    agente seguia com ela em contexto.
    """

    consulta = db.query(ChatMessage).filter(ChatMessage.user_id == user_id)
    if session_id:
        consulta = consulta.filter(ChatMessage.session_id == session_id)
    deleted_count = consulta.delete(synchronize_session=False)
    db.commit()

    memoria = esquecer_conversas(user_id, session_id=session_id)

    logger.info(
        "Historico de chat removido para user_id=%s | linhas=%d | threads=%d (%s)",
        user_id, deleted_count, memoria["apagados"], memoria["metodo"],
    )
    return ChatClearResponse(
        deleted_count=deleted_count,
        agent_threads_cleared=memoria["apagados"],
    )
