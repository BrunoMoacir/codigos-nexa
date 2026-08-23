import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { AppShell } from '../components/layout/AppShell';
import { nexaApi } from '../api/nexa';
import type { ChatHistoryItem } from '../api/types';

type Message = { role: 'user' | 'assistant'; content: string; ts: string };

function mapHistoryItem(item: ChatHistoryItem): Message {
  return { role: item.role === 'assistant' ? 'assistant' : 'user', content: item.content, ts: item.created_at || new Date().toISOString() };
}

function newSessionId() {
  return globalThis.crypto?.randomUUID?.() || `chat-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

const css = `
  .cp {
    display: flex;
    flex-direction: column;
    height: 100vh;
    background: #0E0C0A;
    position: relative;
  }

  .cp-header {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 20px 32px 0;
    margin-bottom: 20px;
  }
  .cp-header-left {}
  .cp-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: #F3EFEA;
    letter-spacing: -0.01em;
  }
  .cp-subtitle {
    font-size: 0.72rem;
    color: rgba(243,239,234,0.3);
    margin-top: 2px;
    letter-spacing: 0.01em;
  }
  .cp-clear {
    padding: 7px 14px;
    background: transparent;
    border: 1px solid rgba(243,239,234,0.1);
    border-radius: 8px;
    color: rgba(243,239,234,0.35);
    font-family: inherit;
    font-size: 0.74rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }
  .cp-clear:hover { border-color: rgba(243,239,234,0.2); color: rgba(243,239,234,0.7); }

  .cp-messages {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 0 32px 24px;
    scrollbar-width: thin;
    scrollbar-color: rgba(243,239,234,0.08) transparent;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  .cp-messages::-webkit-scrollbar { width: 4px; }
  .cp-messages::-webkit-scrollbar-thumb { background: rgba(243,239,234,0.08); border-radius: 4px; }

  .cp-msg {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    max-width: 720px;
  }
  .cp-msg.user { align-self: flex-end; flex-direction: row-reverse; }
  .cp-msg.assistant { align-self: flex-start; }

  .cp-msg-avatar {
    width: 30px;
    height: 30px;
    border-radius: 50%;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.68rem;
    font-weight: 700;
    margin-top: 2px;
  }
  .cp-msg.assistant .cp-msg-avatar {
    background: rgba(212,168,32,0.15);
    border: 1px solid rgba(212,168,32,0.25);
    color: #D4A820;
  }
  .cp-msg.user .cp-msg-avatar {
    background: rgba(243,239,234,0.08);
    border: 1px solid rgba(243,239,234,0.12);
    color: rgba(243,239,234,0.5);
  }

  .cp-bubble {
    padding: 12px 16px;
    border-radius: 14px;
    font-size: 0.88rem;
    line-height: 1.6;
    white-space: pre-wrap;
    max-width: 560px;
  }
  .cp-msg.assistant .cp-bubble {
    background: rgba(243,239,234,0.05);
    border: 1px solid rgba(243,239,234,0.08);
    color: rgba(243,239,234,0.85);
    border-radius: 4px 14px 14px 14px;
  }
  .cp-msg.user .cp-bubble {
    background: rgba(212,168,32,0.12);
    border: 1px solid rgba(212,168,32,0.2);
    color: #F3EFEA;
    border-radius: 14px 4px 14px 14px;
  }

  .cp-typing {
    display: flex;
    gap: 4px;
    align-items: center;
    padding: 14px 16px;
  }
  .cp-typing span {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: rgba(212,168,32,0.5);
    animation: typing-dot 1.2s ease-in-out infinite;
  }
  .cp-typing span:nth-child(2) { animation-delay: 0.2s; }
  .cp-typing span:nth-child(3) { animation-delay: 0.4s; }
  @keyframes typing-dot {
    0%, 80%, 100% { transform: scale(0.7); opacity: 0.4; }
    40% { transform: scale(1); opacity: 1; }
  }

  .cp-footer {
    flex-shrink: 0;
    padding: 0 32px 28px;
  }
  .cp-input-wrap {
    display: flex;
    align-items: flex-end;
    gap: 10px;
    background: rgba(243,239,234,0.05);
    border: 1px solid rgba(243,239,234,0.1);
    border-radius: 14px;
    padding: 12px 12px 12px 18px;
    transition: border-color 0.18s;
  }
  .cp-input-wrap:focus-within {
    border-color: rgba(212,168,32,0.3);
  }
  .cp-textarea {
    flex: 1;
    background: transparent;
    border: none;
    outline: none;
    color: #F3EFEA;
    font-family: inherit;
    font-size: 0.88rem;
    line-height: 1.5;
    resize: none;
    min-height: 22px;
    max-height: 140px;
    overflow-y: auto;
  }
  .cp-textarea::placeholder { color: rgba(243,239,234,0.2); }
  .cp-send {
    width: 36px;
    height: 36px;
    flex-shrink: 0;
    border-radius: 9px;
    border: none;
    background: #D4A820;
    color: #0C0A08;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.15s, opacity 0.15s;
  }
  .cp-send:hover:not(:disabled) { background: #E8C030; }
  .cp-send:disabled { opacity: 0.3; cursor: not-allowed; }
  .cp-hint {
    text-align: center;
    margin-top: 10px;
    font-size: 0.67rem;
    color: rgba(243,239,234,0.15);
  }

  /* Sugestões iniciais */
  .cp-suggestions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding: 0 32px 20px;
  }
  .cp-sug {
    padding: 8px 14px;
    background: rgba(243,239,234,0.04);
    border: 1px solid rgba(243,239,234,0.08);
    border-radius: 20px;
    color: rgba(243,239,234,0.45);
    font-family: inherit;
    font-size: 0.78rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }
  .cp-sug:hover {
    background: rgba(212,168,32,0.08);
    border-color: rgba(212,168,32,0.2);
    color: rgba(243,239,234,0.8);
  }

  @media (max-width: 860px) {
    .cp { height: auto; min-height: calc(100vh - 70px); }
    .cp-messages, .cp-header, .cp-footer { padding-left: 16px; padding-right: 16px; }
    .cp-suggestions { padding-left: 16px; padding-right: 16px; }
    .cp-bubble { max-width: 90vw; }
  }
`;

const SUGGESTIONS = [
  'Analise minhas despesas do mês',
  'Quais tarifas estou pagando?',
  'Como melhorar meu score?',
  'Simule uma compra parcelada',
];

export const ChatPage: React.FC = () => {
  const userId = localStorage.getItem('user_id') || '';
  const userName = localStorage.getItem('user_name') || localStorage.getItem('user_email') || 'U';
  const userInitials = userName.slice(0, 2).toUpperCase();

  const storageKey = useMemo(() => `hive-chat:${userId || 'anon'}`, [userId]);
  const sessionKey = useMemo(() => `hive-session:${userId || 'anon'}`, [userId]);
  const endRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const defaultMsg = useMemo<Message>(() => ({
    role: 'assistant',
    content: 'Olá! Sou o agente HIVE. Posso analisar seus gastos, identificar tarifas, simular compras e muito mais. Como posso ajudar?',
    ts: new Date().toISOString(),
  }), []);

  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([defaultMsg]);
  const [sessionId, setSessionId] = useState(() => {
    try { return localStorage.getItem(sessionKey) || newSessionId(); }
    catch { return newSessionId(); }
  });

  const historyQuery = useQuery<ChatHistoryItem[]>({
    queryKey: ['chat-history', userId],
    queryFn: () => nexaApi.getChatHistory(userId, 100),
    enabled: !!userId,
  });

  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      const parsed = raw ? JSON.parse(raw) as Message[] : null;
      setMessages(Array.isArray(parsed) && parsed.length > 0 ? parsed : [defaultMsg]);
    } catch { setMessages([defaultMsg]); }
  }, [defaultMsg, storageKey]);

  useEffect(() => {
    const history = (historyQuery.data || []).map(mapHistoryItem).filter(m => m.content.trim());
    if (history.length > 0) setMessages(history);
  }, [historyQuery.data]);

  useEffect(() => {
    try { localStorage.setItem(storageKey, JSON.stringify(messages)); } catch {}
  }, [messages, storageKey]);

  useEffect(() => {
    try { localStorage.setItem(sessionKey, sessionId); } catch {}
  }, [sessionId, sessionKey]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);

  const chatMutation = useMutation({
    mutationFn: (msg: string) => nexaApi.sendChatMessage(userId, msg, sessionId),
    onSuccess: (data) => {
      const content = data?.response || data?.answer || data?.message || 'Recebi, mas não obtive resposta do servidor.';
      setMessages(prev => [...prev, { role: 'assistant', content: String(content), ts: new Date().toISOString() }]);
      void historyQuery.refetch();
    },
    onError: () => {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Não consegui responder agora. Verifique se o backend está ativo.',
        ts: new Date().toISOString(),
      }]);
    },
  });

  const clearChat = async () => {
    const sid = newSessionId();
    setSessionId(sid);
    setMessages([defaultMsg]);
    try { localStorage.setItem(storageKey, JSON.stringify([defaultMsg])); localStorage.setItem(sessionKey, sid); } catch {}
    try { await nexaApi.clearChatHistory(userId); await historyQuery.refetch(); } catch {}
  };

  const send = (text?: string) => {
    const msg = (text || input).trim();
    if (!userId || !msg || chatMutation.isPending) return;
    setMessages(prev => [...prev, { role: 'user', content: msg, ts: new Date().toISOString() }]);
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    chatMutation.mutate(msg);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 140)}px`;
  };

  const showSuggestions = messages.length <= 1;

  return (
    <AppShell current="chat">
      <style>{css}</style>
      <div className="cp">
        <div className="cp-header">
          <div className="cp-header-left">
            <div className="cp-title">Chat IA</div>
            <div className="cp-subtitle">Agente HIVE · Inteligência Financeira</div>
          </div>
          <button className="cp-clear" onClick={clearChat} disabled={historyQuery.isLoading}>
            Nova conversa
          </button>
        </div>

        <div className="cp-messages">
          {messages.map((m, i) => (
            <div key={`${m.ts}-${i}`} className={`cp-msg ${m.role}`}>
              <div className="cp-msg-avatar">
                {m.role === 'assistant' ? 'H' : userInitials}
              </div>
              <div className="cp-bubble">{m.content}</div>
            </div>
          ))}
          {chatMutation.isPending && (
            <div className="cp-msg assistant">
              <div className="cp-msg-avatar">H</div>
              <div className="cp-bubble">
                <div className="cp-typing">
                  <span /><span /><span />
                </div>
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        {showSuggestions && (
          <div className="cp-suggestions">
            {SUGGESTIONS.map(s => (
              <button key={s} className="cp-sug" onClick={() => send(s)}>{s}</button>
            ))}
          </div>
        )}

        <div className="cp-footer">
          <div className="cp-input-wrap">
            <textarea
              ref={textareaRef}
              className="cp-textarea"
              placeholder="Pergunte sobre orçamento, tarifas, metas..."
              value={input}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              rows={1}
              disabled={chatMutation.isPending}
            />
            <button className="cp-send" onClick={() => send()} disabled={!input.trim() || chatMutation.isPending}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M2 7h10M8 3l4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>
          <div className="cp-hint">Enter para enviar · Shift+Enter para nova linha</div>
        </div>
      </div>
    </AppShell>
  );
};
