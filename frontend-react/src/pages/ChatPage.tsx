import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { AppShell } from '../components/layout/AppShell';
import { nexaApi } from '../api/nexa';
import type { ChatHistoryItem } from '../api/types';

type Message = { role: 'user' | 'assistant'; content: string; ts: string; image?: string };

function mapHistoryItem(item: ChatHistoryItem): Message {
  return { role: item.role === 'assistant' ? 'assistant' : 'user', content: item.content, ts: item.created_at || new Date().toISOString() };
}

function newSessionId() {
  return globalThis.crypto?.randomUUID?.() || `chat-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
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

  .cp-bubble { padding: 12px 16px; border-radius: 14px; font-size: 0.88rem; line-height: 1.6; white-space: pre-wrap; max-width: 560px; }
  .cp-msg.assistant .cp-bubble { background: rgba(243,239,234,0.05); border: 1px solid rgba(243,239,234,0.08); color: rgba(243,239,234,0.85); border-radius: 4px 14px 14px 14px; }
  .cp-msg.user .cp-bubble { background: rgba(212,168,32,0.12); border: 1px solid rgba(212,168,32,0.2); color: #F3EFEA; border-radius: 14px 4px 14px 14px; }
  .cp-bubble img { max-width: 240px; border-radius: 8px; display: block; margin-top: 8px; }

  .cp-typing { display: flex; gap: 4px; align-items: center; padding: 14px 16px; }
  .cp-typing span { width: 6px; height: 6px; border-radius: 50%; background: rgba(212,168,32,0.5); animation: typing-dot 1.2s ease-in-out infinite; }
  .cp-typing span:nth-child(2) { animation-delay: 0.2s; }
  .cp-typing span:nth-child(3) { animation-delay: 0.4s; }
  @keyframes typing-dot { 0%,80%,100%{transform:scale(0.7);opacity:0.4} 40%{transform:scale(1);opacity:1} }

  /* Input area */
  .cp-footer { flex-shrink: 0; padding: 8px 32px 28px; }

  /* Attach menu */
  .cp-attach-menu {
    position: absolute; bottom: calc(100% + 8px); left: 0;
    background: #1A1714; border: 1px solid rgba(243,239,234,0.1); border-radius: 14px;
    overflow: hidden; min-width: 200px; box-shadow: 0 8px 32px rgba(0,0,0,0.5);
    animation: menu-in 0.12s ease;
  }
  @keyframes menu-in { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)} }
  .cp-attach-item { display: flex; align-items: center; gap: 12px; padding: 13px 16px; cursor: pointer; transition: background 0.12s; font-size: 0.83rem; color: rgba(243,239,234,0.7); font-weight: 500; }
  .cp-attach-item:hover { background: rgba(243,239,234,0.05); color: #F3EFEA; }
  .cp-attach-item-icon { font-size: 1rem; width: 20px; text-align: center; }
  .cp-attach-divider { height: 1px; background: rgba(243,239,234,0.06); margin: 0; }

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

  /* Image preview */
  .cp-img-preview { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; padding: 8px 10px; background: rgba(243,239,234,0.04); border: 1px solid rgba(243,239,234,0.08); border-radius: 10px; }
  .cp-img-thumb { width: 40px; height: 40px; border-radius: 6px; object-fit: cover; }
  .cp-img-name { font-size: 0.75rem; color: rgba(243,239,234,0.5); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .cp-img-remove { background: none; border: none; color: rgba(243,239,234,0.3); cursor: pointer; font-size: 1rem; padding: 0; transition: color 0.12s; }
  .cp-img-remove:hover { color: #F07A64; }

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

export const ChatPage: React.FC = () => {
  const userId = localStorage.getItem('user_id') || '';
  const userName = localStorage.getItem('user_name') || localStorage.getItem('user_email') || 'U';
  const userInitials = userName.slice(0, 2).toUpperCase();

  const storageKey = useMemo(() => `hive-chat:${userId || 'anon'}`, [userId]);
  const sessionKey = useMemo(() => `hive-session:${userId || 'anon'}`, [userId]);
  const endRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);

  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const [imagePreview, setImagePreview] = useState<{ dataUrl: string; name: string } | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [sessionId, setSessionId] = useState(() => {
    try { return localStorage.getItem(sessionKey) || newSessionId(); }
    catch { return newSessionId(); }
  });

  const hasSpeech = typeof window !== 'undefined' && !!(window.SpeechRecognition || window.webkitSpeechRecognition);

  const historyQuery = useQuery<ChatHistoryItem[]>({
    queryKey: ['chat-history', userId],
    queryFn: () => nexaApi.getChatHistory(userId, 100),
    enabled: !!userId,
  });

  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      const parsed = raw ? JSON.parse(raw) as Message[] : null;
      setMessages(Array.isArray(parsed) && parsed.length > 0 ? parsed : []);
    } catch { setMessages([]); }
  }, [storageKey]);

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
    setMessages([]);
    setImagePreview(null);
    try { localStorage.setItem(storageKey, '[]'); localStorage.setItem(sessionKey, sid); } catch {}
    try { await nexaApi.clearChatHistory(userId); await historyQuery.refetch(); } catch {}
  };

  const send = useCallback((text?: string, img?: string) => {
    const msg = (text || input).trim();
    if (!msg && !img) return;
    if (chatMutation.isPending) return;
    setMessages(prev => [...prev, { role: 'user', content: msg, image: img || imagePreview?.dataUrl, ts: new Date().toISOString() }]);
    setInput('');
    setImagePreview(null);
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    if (msg) chatMutation.mutate(msg);
  }, [input, imagePreview, chatMutation]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 140)}px`;
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      setImagePreview({ dataUrl: ev.target?.result as string, name: file.name });
    };
    reader.readAsDataURL(file);
    e.target.value = '';
    setShowAttachMenu(false);
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
      if (transcript) {
        setInput(prev => prev ? `${prev} ${transcript}` : transcript);
      }
    };
    rec.onerror = () => setIsRecording(false);
    rec.onend = () => setIsRecording(false);
    recognitionRef.current = rec;
    rec.start();
    setIsRecording(true);
  }, [hasSpeech, isRecording]);

  const showWelcome = messages.length === 0 && !chatMutation.isPending;

  return (
    <AppShell current="chat">
      <style>{css}</style>
      <div className="cp" onClick={() => setShowAttachMenu(false)}>

        {/* Header */}
        <div className="cp-header">
          <div>
            <div className="cp-title">Chat IA</div>
            <div className="cp-subtitle">Agente HIVE · Inteligência Financeira</div>
          </div>
          <button className="cp-clear" onClick={clearChat} disabled={historyQuery.isLoading}>
            Nova conversa
          </button>
        </div>

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
          <div className="cp-messages">
            {messages.map((m, i) => (
              <div key={`${m.ts}-${i}`} className={`cp-msg ${m.role}`}>
                <div className="cp-msg-avatar">
                  {m.role === 'assistant' ? '◈' : userInitials}
                </div>
                <div className="cp-bubble">
                  {m.content}
                  {m.image && <img src={m.image} alt="anexo" />}
                </div>
              </div>
            ))}
            {chatMutation.isPending && (
              <div className="cp-msg assistant">
                <div className="cp-msg-avatar">◈</div>
                <div className="cp-bubble">
                  <div className="cp-typing">
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
          {imagePreview && (
            <div className="cp-img-preview">
              <img src={imagePreview.dataUrl} alt="preview" className="cp-img-thumb" />
              <span className="cp-img-name">{imagePreview.name}</span>
              <button className="cp-img-remove" onClick={() => setImagePreview(null)}>✕</button>
            </div>
          )}
          <div className="cp-input-wrap">
            {showAttachMenu && (
              <div className="cp-attach-menu" onClick={e => e.stopPropagation()}>
                <div className="cp-attach-item" onClick={() => fileInputRef.current?.click()}>
                  <span className="cp-attach-item-icon">🖼</span>
                  Adicionar imagem
                </div>
                <div className="cp-attach-divider" />
                <div className="cp-attach-item" style={{ opacity: 0.4, cursor: 'not-allowed' }}>
                  <span className="cp-attach-item-icon">📎</span>
                  Adicionar arquivo <span style={{ fontSize: '0.65rem', marginLeft: 4 }}>(em breve)</span>
                </div>
              </div>
            )}
            <div className="cp-input-box">
              {/* Attach button */}
              <button
                className="cp-icon-btn"
                title="Anexar"
                onClick={e => { e.stopPropagation(); setShowAttachMenu(v => !v); }}
              >
                <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                  <path d="M7.5 1v13M1 7.5h13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
                </svg>
              </button>

              <textarea
                ref={textareaRef}
                className="cp-textarea"
                placeholder="Pergunte sobre seus gastos, tarifas, investimentos..."
                value={input}
                onChange={handleInput}
                onKeyDown={handleKeyDown}
                rows={1}
              />

              {/* Mic button */}
              {hasSpeech && (
                <button
                  className={`cp-icon-btn${isRecording ? ' recording' : ''}`}
                  title={isRecording ? 'Parar gravação' : 'Falar'}
                  onClick={toggleRecording}
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <rect x="4" y="1" width="6" height="8" rx="3" stroke="currentColor" strokeWidth="1.4"/>
                    <path d="M2 7c0 2.76 2.24 5 5 5s5-2.24 5-5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
                    <line x1="7" y1="12" x2="7" y2="13.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
                  </svg>
                </button>
              )}

              {/* Send button */}
              <button
                className="cp-send"
                disabled={(!input.trim() && !imagePreview) || chatMutation.isPending}
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

        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />
      </div>
    </AppShell>
  );
};
