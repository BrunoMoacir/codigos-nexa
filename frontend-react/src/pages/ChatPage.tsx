import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { Markdown } from '../components/Markdown';
import { chatApi, ROTULO_FERRAMENTA, TELA_DA_FERRAMENTA } from '../api/chat';
import type { ItemHistorico } from '../api/chat';
import { describeError } from '../api/errors';
import type { ApiErrorKind } from '../api/errors';
import { session } from '../api/session';

type Message = {
  role: 'user' | 'assistant';
  content: string;
  ts: string;
  tools?: string[];
  erro?: { kind: ApiErrorKind; reenviar?: string };
};

function mapHistoryItem(item: ItemHistorico): Message {
  return { role: item.role === 'assistant' ? 'assistant' : 'user', content: item.content, ts: item.created_at };
}

function newSessionId() {
  return globalThis.crypto?.randomUUID?.() || `chat-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/** A conversa atual de cada usuário (o prefixo hive_chat_ sai no logout). */
const chaveDaSessao = (userId: string) => `hive_chat_session:${userId}`;

function lerSessao(userId: string): string | null {
  try {
    return localStorage.getItem(chaveDaSessao(userId));
  } catch {
    return null; // storage bloqueado
  }
}

// Web Speech API type declarations
declare global {
  interface Window {
    SpeechRecognition: new () => SpeechRecognition;
    webkitSpeechRecognition: new () => SpeechRecognition;
  }
}

interface SpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  onend: (() => void) | null;
}

interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionResultList {
  readonly length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionResult {
  readonly isFinal: boolean;
  readonly length: number;
  item(index: number): SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
}

interface SpeechRecognitionAlternative {
  readonly transcript: string;
  readonly confidence: number;
}

const css = `
  .cp { display: flex; flex-direction: column; height: 100vh; background: #0E0C0A; position: relative; }

  /* Header */
  .cp-header { flex-shrink: 0; display: flex; align-items: center; justify-content: space-between; padding: 20px 32px 0; margin-bottom: 4px; }
  .cp-title { font-size: 1.05rem; font-weight: 700; color: #F3EFEA; letter-spacing: -0.01em; }
  .cp-subtitle { font-size: 0.72rem; color: rgba(243,239,234,0.3); margin-top: 2px; }
  .cp-clear { padding: 7px 14px; background: transparent; border: 1px solid rgba(243,239,234,0.1); border-radius: 8px; color: rgba(243,239,234,0.35); font-family: inherit; font-size: 0.74rem; font-weight: 500; cursor: pointer; transition: all 0.15s; }
  .cp-clear:hover { border-color: rgba(243,239,234,0.2); color: rgba(243,239,234,0.7); }

  /* Welcome screen */
  .cp-welcome { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 32px; gap: 28px; }
  .cp-welcome-title { font-size: 1.9rem; font-weight: 900; color: #F3EFEA; letter-spacing: -0.04em; text-align: center; }
  .cp-welcome-title span { color: #D4A820; }
  .cp-welcome-chips { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; max-width: 560px; }
  .cp-chip { padding: 9px 16px; background: rgba(243,239,234,0.04); border: 1px solid rgba(243,239,234,0.08); border-radius: 22px; color: rgba(243,239,234,0.45); font-family: inherit; font-size: 0.8rem; font-weight: 500; cursor: pointer; transition: all 0.15s; }
  .cp-chip:hover { background: rgba(212,168,32,0.08); border-color: rgba(212,168,32,0.2); color: rgba(243,239,234,0.85); }

  /* Messages */
  .cp-messages { flex: 1; min-height: 0; overflow-y: auto; padding: 16px 32px 8px; scrollbar-width: thin; scrollbar-color: rgba(243,239,234,0.08) transparent; display: flex; flex-direction: column; gap: 16px; }
  .cp-messages::-webkit-scrollbar { width: 4px; }
  .cp-messages::-webkit-scrollbar-thumb { background: rgba(243,239,234,0.08); border-radius: 4px; }

  .cp-msg { display: flex; align-items: flex-start; gap: 12px; max-width: 720px; }
  .cp-msg.user { align-self: flex-end; flex-direction: row-reverse; }
  .cp-msg.assistant { align-self: flex-start; }

  .cp-msg-avatar { width: 30px; height: 30px; border-radius: 50%; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 0.68rem; font-weight: 700; margin-top: 2px; }
  .cp-msg.assistant .cp-msg-avatar { background: rgba(212,168,32,0.15); border: 1px solid rgba(212,168,32,0.25); color: #D4A820; }
  .cp-msg.user .cp-msg-avatar { background: rgba(243,239,234,0.08); border: 1px solid rgba(243,239,234,0.12); color: rgba(243,239,234,0.5); }

  .cp-bubble { padding: 12px 16px; border-radius: 14px; font-size: 0.88rem; line-height: 1.6; white-space: pre-wrap; max-width: 560px; overflow-wrap: anywhere; }
  .cp-msg.assistant .cp-bubble { background: rgba(243,239,234,0.05); border: 1px solid rgba(243,239,234,0.08); color: rgba(243,239,234,0.85); border-radius: 4px 14px 14px 14px; }
  .cp-msg.user .cp-bubble { background: rgba(212,168,32,0.12); border: 1px solid rgba(212,168,32,0.2); color: #F3EFEA; border-radius: 14px 4px 14px 14px; }

  .cp-msg.assistant .cp-bubble { white-space: normal; }
  .md p { margin: 0 0 8px; } .md p:last-child { margin-bottom: 0; }
  .md ul, .md ol { margin: 0 0 8px; padding-left: 20px; } .md li { margin: 2px 0; }
  .md code { background: rgba(243,239,234,0.08); padding: 1px 5px; border-radius: 4px; font-size: 0.82em; }
  .md a { color: #D4A820; } .md hr { border: none; border-top: 1px solid rgba(243,239,234,0.1); margin: 10px 0; }
  .cp-msg.erro .cp-bubble { background: rgba(240,122,100,0.08); border-color: rgba(240,122,100,0.25); color: #F8AEA0; }
  .cp-meta { font-size: 0.68rem; color: rgba(243,239,234,0.3); margin-top: 6px; line-height: 1.5; }
  .cp-meta a, .cp-meta button { color: #D4A820; background: none; border: none; padding: 0; font: inherit; cursor: pointer; text-decoration: underline; }
  .cp-head-actions { display: flex; gap: 8px; }
  .cp-typing { display: flex; gap: 4px; align-items: center; padding: 14px 16px; }
  .cp-typing span { width: 6px; height: 6px; border-radius: 50%; background: rgba(212,168,32,0.5); animation: typing-dot 1.2s ease-in-out infinite; }
  .cp-typing span:nth-child(2) { animation-delay: 0.2s; }
  .cp-typing span:nth-child(3) { animation-delay: 0.4s; }
  @keyframes typing-dot { 0%,80%,100%{transform:scale(0.7);opacity:0.4} 40%{transform:scale(1);opacity:1} }

  /* Input area */
  .cp-footer { flex-shrink: 0; padding: 8px 32px 28px; }

  .cp-input-wrap { position: relative; }
  .cp-input-box { display: flex; align-items: flex-end; gap: 8px; background: rgba(243,239,234,0.05); border: 1px solid rgba(243,239,234,0.1); border-radius: 14px; padding: 10px 10px 10px 14px; transition: border-color 0.18s; }
  .cp-input-box:focus-within { border-color: rgba(212,168,32,0.3); }

  .cp-icon-btn { width: 34px; height: 34px; flex-shrink: 0; border-radius: 8px; border: none; background: rgba(243,239,234,0.06); color: rgba(243,239,234,0.4); cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.15s; }
  .cp-icon-btn:hover { background: rgba(243,239,234,0.1); color: rgba(243,239,234,0.8); }
  .cp-icon-btn.active { background: rgba(240,122,100,0.15); color: #F07A64; }
  .cp-icon-btn.recording { background: rgba(240,122,100,0.2); color: #F07A64; animation: rec-pulse 1s ease-in-out infinite; }
  @keyframes rec-pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }

  .cp-textarea { flex: 1; background: transparent; border: none; outline: none; color: #F3EFEA; font-family: inherit; font-size: 0.88rem; line-height: 1.5; resize: none; min-height: 22px; max-height: 140px; overflow-y: auto; }
  .cp-textarea::placeholder { color: rgba(243,239,234,0.2); }

  .cp-send { width: 36px; height: 36px; flex-shrink: 0; border-radius: 9px; border: none; background: #D4A820; color: #0C0A08; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: background 0.15s, opacity 0.15s; }
  .cp-send:hover:not(:disabled) { background: #E8C030; }
  .cp-send:disabled { opacity: 0.3; cursor: not-allowed; }

  .cp-hint { text-align: center; margin-top: 8px; font-size: 0.67rem; color: rgba(243,239,234,0.12); }

  .cp-mic-bar { display: flex; align-items: center; gap: 8px; padding: 6px 12px; background: rgba(240,122,100,0.08); border: 1px solid rgba(240,122,100,0.15); border-radius: 8px; margin-bottom: 8px; font-size: 0.75rem; color: rgba(240,122,100,0.7); font-weight: 500; }
  .cp-mic-dot { width: 6px; height: 6px; border-radius: 50%; background: #F07A64; animation: rec-pulse 0.8s ease-in-out infinite; }

  @media (max-width: 860px) {
    .cp { height: auto; min-height: calc(100vh - 70px); }
    .cp-messages, .cp-header, .cp-footer { padding-left: 16px; padding-right: 16px; }
    .cp-welcome { padding: 24px 16px; }
    .cp-welcome-title { font-size: 1.45rem; }
    .cp-bubble { max-width: 90vw; }
  }
`;

const SUGGESTIONS = [
  'Analise meus gastos do mês',
  'Quais tarifas estou pagando?',
  'Como aumentar meu score?',
  'Simule uma compra parcelada',
  'Quais investimentos me convêm?',
  'Me explique IOF e como evitar',
];

// O chat mandava a conversa inteira para o localStorage com chaves que o
// logout não limpava, puxava o histórico de TODAS as sessões misturado, tinha
// timeout de 15 s para um agente que pode levar 60, transformava qualquer erro
// (cota do plano, limite de requisições, LLM fora) em "verifique se o backend
// está ativo", oferecia anexar imagem que o backend nunca recebeu, e "Nova
// conversa" APAGAVA todo o histórico do usuário.
export const ChatPage: React.FC = () => {
  const userId = session.userId;
  const userName = session.userName || session.userEmail || 'U';
  const userInitials = userName.slice(0, 2).toUpperCase();
  const queryClient = useQueryClient();

  const endRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);

  const [input, setInput] = useState('');
  // as desta tela (perguntas, respostas, erros) — somadas ao histórico do servidor
  const [locais, setLocais] = useState<Message[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  // Sem sessão salva neste aparelho, retoma a da última conversa (outro
  // aparelho, ou depois do logout, que limpa o storage) em vez de abrir vazio.
  const [sessionId, setSessionId] = useState<string | null>(() => lerSessao(userId));
  useEffect(() => {
    if (sessionId || !userId) return;
    let vivo = true;
    chatApi.ultimaSessao(userId)
      .then(s => { if (vivo) setSessionId(s || newSessionId()); })
      .catch(() => { if (vivo) setSessionId(newSessionId()); });
    return () => { vivo = false; };
  }, [sessionId, userId]);

  const hasSpeech = typeof window !== 'undefined' && !!(window.SpeechRecognition || window.webkitSpeechRecognition);

  useEffect(() => {
    if (!sessionId) return;
    try { localStorage.setItem(chaveDaSessao(userId), sessionId); } catch { /* sem storage */ }
  }, [sessionId, userId]);

  // Só a conversa desta sessão — a mesma que a memória do agente enxerga.
  const historyQuery = useQuery({
    queryKey: ['chat', 'historico', userId, sessionId],
    queryFn: () => chatApi.historico(userId, sessionId!, 100),
    enabled: !!userId && !!sessionId,
    staleTime: Infinity,
  });

  const historico = useMemo(
    () => (historyQuery.data || []).map(mapHistoryItem).filter(m => m.content.trim()),
    [historyQuery.data],
  );
  const messages = useMemo(() => [...historico, ...locais], [historico, locais]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);

  const chatMutation = useMutation({
    mutationFn: (msg: string) => chatApi.enviar(userId, msg, sessionId!),
    onSuccess: (data) => {
      const content = data?.response?.trim() || 'Recebi sua mensagem, mas o agente não devolveu texto. Tente reformular.';
      setLocais(prev => [...prev, { role: 'assistant', content, tools: data?.tools_used || [], ts: data?.created_at || new Date().toISOString() }]);
    },
    onError: (err, msg) => {
      const e = describeError(err, 'Não consegui responder agora. Tente de novo em instantes.');
      const podeReenviar = e.kind !== 'upgrade_required' && e.kind !== 'validation';
      setLocais(prev => [...prev, {
        role: 'assistant',
        content: e.message,
        erro: { kind: e.kind, reenviar: podeReenviar ? msg : undefined },
        ts: new Date().toISOString(),
      }]);
    },
  });

  /** Começa outra conversa SEM apagar a anterior (ela continua no servidor). */
  const novaConversa = () => {
    const sid = newSessionId();
    setSessionId(sid);
    setLocais([]);
    queryClient.setQueryData(['chat', 'historico', userId, sid], []);
  };

  const apagarConversa = async () => {
    if (!confirm('Apagar esta conversa? As mensagens e o que o agente lembrou dela serão removidos.')) return;
    try {
      if (sessionId) await chatApi.apagar(userId, sessionId);
    } catch (err) {
      alert(describeError(err, 'Não foi possível apagar a conversa.').message);
      return;
    }
    novaConversa();
  };

  const send = useCallback((text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || chatMutation.isPending || !sessionId) return;
    setLocais(prev => [...prev, { role: 'user', content: msg, ts: new Date().toISOString() }]);
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    chatMutation.mutate(msg);
  }, [input, chatMutation, sessionId]);

  const reenviar = (msg: string) => {
    // tira a bolha de erro e a pergunta repetida antes de mandar de novo
    setLocais(prev => {
      const semErro = prev.slice(0, -1);
      return semErro.length && semErro[semErro.length - 1].content === msg ? semErro.slice(0, -1) : semErro;
    });
    send(msg);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 140)}px`;
  };

  const toggleRecording = useCallback(() => {
    if (!hasSpeech) return;
    if (isRecording) {
      recognitionRef.current?.stop();
      setIsRecording(false);
      return;
    }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const rec = new SR();
    rec.lang = 'pt-BR';
    rec.continuous = false;
    rec.interimResults = false;
    rec.onresult = (event: SpeechRecognitionEvent) => {
      const transcript = event.results[0]?.[0]?.transcript || '';
      if (transcript) setInput(prev => prev ? `${prev} ${transcript}` : transcript);
    };
    rec.onerror = () => setIsRecording(false);
    rec.onend = () => setIsRecording(false);
    recognitionRef.current = rec;
    rec.start();
    setIsRecording(true);
  }, [hasSpeech, isRecording]);

  const showWelcome = messages.length === 0 && !chatMutation.isPending && !historyQuery.isLoading && !!sessionId;

  const meta = (m: Message) => {
    if (m.erro) {
      return (
        <div className="cp-meta">
          {m.erro.kind === 'upgrade_required' && <Link to="/planos">Ver planos →</Link>}
          {m.erro.reenviar && <button onClick={() => reenviar(m.erro!.reenviar!)}>Tentar de novo</button>}
        </div>
      );
    }
    if (!m.tools?.length) return null;
    const telas = [...new Map(m.tools.filter(t => TELA_DA_FERRAMENTA[t]).map(t => [TELA_DA_FERRAMENTA[t].rota, TELA_DA_FERRAMENTA[t]])).values()];
    return (
      <div className="cp-meta">
        Consultou: {m.tools.map(t => ROTULO_FERRAMENTA[t] || t).join(', ')}
        {telas.map(t => <span key={t.rota}> · <Link to={t.rota}>{t.rotulo} →</Link></span>)}
      </div>
    );
  };

  return (
    <AppShell current="chat">
      <style>{css}</style>
      <div className="cp">

        {/* Header */}
        <div className="cp-header">
          <div>
            <div className="cp-title">Chat IA</div>
            <div className="cp-subtitle">Agente HIVE · usa os seus dados conectados</div>
          </div>
          <div className="cp-head-actions">
            {messages.length > 0 && (
              <button className="cp-clear" onClick={apagarConversa} disabled={chatMutation.isPending}>Apagar conversa</button>
            )}
            <button className="cp-clear" onClick={novaConversa} disabled={chatMutation.isPending}>Nova conversa</button>
          </div>
        </div>

        {historyQuery.isError && (
          <div className="cp-hint" style={{ color: '#F8AEA0' }}>
            {describeError(historyQuery.error, 'Não foi possível carregar a conversa anterior.').message}
          </div>
        )}

        {/* Welcome or Messages */}
        {showWelcome ? (
          <div className="cp-welcome">
            <div className="cp-welcome-title">
              Oi! Como posso<br />te ajudar hoje?
            </div>
            <div className="cp-welcome-chips">
              {SUGGESTIONS.map((s, i) => (
                <button key={i} className="cp-chip" onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </div>
        ) : (
          <div className="cp-messages" aria-live="polite">
            {messages.map((m, i) => (
              <div key={`${m.ts}-${i}`} className={`cp-msg ${m.role}${m.erro ? ' erro' : ''}`}>
                <div className="cp-msg-avatar">
                  {m.role === 'assistant' ? '◈' : userInitials}
                </div>
                <div>
                  <div className="cp-bubble">
                    {m.role === 'assistant' && !m.erro ? <Markdown texto={m.content} /> : m.content}
                  </div>
                  {meta(m)}
                </div>
              </div>
            ))}
            {chatMutation.isPending && (
              <div className="cp-msg assistant">
                <div className="cp-msg-avatar">◈</div>
                <div className="cp-bubble">
                  <div className="cp-typing" aria-label="O agente está respondendo">
                    <span/><span/><span/>
                  </div>
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>
        )}

        {/* Footer */}
        <div className="cp-footer">
          {isRecording && (
            <div className="cp-mic-bar">
              <div className="cp-mic-dot" />
              Ouvindo... fale agora
            </div>
          )}
          <div className="cp-input-wrap">
            <div className="cp-input-box">
              <textarea
                ref={textareaRef}
                className="cp-textarea"
                placeholder="Pergunte sobre seus gastos, tarifas, investimentos..."
                aria-label="Mensagem para o agente"
                value={input}
                onChange={handleInput}
                onKeyDown={handleKeyDown}
                rows={1}
              />

              {/* Microfone só onde o navegador transcreve (Web Speech) */}
              {hasSpeech && (
                <button
                  className={`cp-icon-btn${isRecording ? ' recording' : ''}`}
                  title={isRecording ? 'Parar gravação' : 'Falar'}
                  aria-label={isRecording ? 'Parar gravação' : 'Falar'}
                  onClick={toggleRecording}
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <rect x="4" y="1" width="6" height="8" rx="3" stroke="currentColor" strokeWidth="1.4"/>
                    <path d="M2 7c0 2.76 2.24 5 5 5s5-2.24 5-5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
                    <line x1="7" y1="12" x2="7" y2="13.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
                  </svg>
                </button>
              )}

              <button
                className="cp-send"
                aria-label="Enviar"
                disabled={!input.trim() || chatMutation.isPending}
                onClick={() => send()}
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M13 1L1 5.5l5 1.5L8.5 13 13 1z" fill="currentColor"/>
                </svg>
              </button>
            </div>
          </div>
          <div className="cp-hint">HIVE IA pode cometer erros — verifique informações importantes.</div>
        </div>
      </div>
    </AppShell>
  );
};
