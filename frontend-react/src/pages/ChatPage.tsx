import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { AppShell } from '../components/layout/AppShell';
import { nexaApi } from '../api/nexa';
import type { ChatHistoryItem, ChatSessionItem } from '../api/types';

type Message = { role: 'user' | 'assistant'; content: string; ts: string; image?: string; id?: number };

function mapHistoryItem(item: ChatHistoryItem): Message {
  return { role: item.role === 'assistant' ? 'assistant' : 'user', content: item.content, ts: item.created_at || new Date().toISOString(), id: item.id };
}

const HiveGlyph = ({ size = 14 }: { size?: number }) => (
  <svg width={size} height={size * 1.11} viewBox="0 0 180 200" fill="none">
    <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="#7A5002"/>
    <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="#D4A820"/>
    <polygon points="100,16 110,22 110,178 100,184" fill="#0A0800"/>
  </svg>
);

function newSessionId() {
  return globalThis.crypto?.randomUUID?.() || `chat-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function relativeTime(iso: string): string {
  const then = new Date(iso.includes('Z') || iso.includes('+') ? iso : `${iso}Z`).getTime();
  if (Number.isNaN(then)) return '';
  const diffMin = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (diffMin < 1) return 'Agora';
  if (diffMin < 60) return `Há ${diffMin} min`;
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `Há ${diffH}h`;
  const diffD = Math.round(diffH / 24);
  if (diffD === 1) return 'Ontem';
  if (diffD < 7) return `Há ${diffD} dias`;
  return new Date(then).toLocaleDateString('pt-BR');
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
  .cp-header { flex-shrink: 0; display: flex; align-items: flex-start; justify-content: space-between; padding: 20px 32px 0; margin-bottom: 4px; }
  .cp-header-left { position: relative; }
  .cp-title-row { display: flex; align-items: center; gap: 6px; position: relative; }
  .cp-title { font-size: 1.05rem; font-weight: 700; color: #F3EFEA; letter-spacing: -0.01em; }
  .cp-subtitle { font-size: 0.72rem; color: rgba(243,239,234,0.3); margin-top: 2px; }
  .cp-clear { display: flex; align-items: center; gap: 6px; padding: 8px 16px 8px 12px; background: rgba(243,239,234,0.04); border: 1px solid rgba(243,239,234,0.1); border-radius: 999px; color: rgba(243,239,234,0.55); font-family: inherit; font-size: 0.78rem; font-weight: 600; cursor: pointer; transition: all 0.15s; }

  /* Dropdown de conversas */
  .cp-sessions-trigger {
    width: 20px; height: 20px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    background: transparent; border: none; border-radius: 6px;
    color: rgba(243,239,234,0.35); cursor: pointer;
    transition: all 0.15s;
  }
  .cp-sessions-trigger:hover, .cp-sessions-trigger.open { background: rgba(243,239,234,0.08); color: #D4A820; }
  .cp-sessions-trigger.open svg { transform: rotate(180deg); }
  .cp-sessions-trigger svg { transition: transform 0.15s; }

  .cp-sessions-panel {
    position: absolute; top: calc(100% + 10px); left: 0;
    width: 320px; max-height: 380px; overflow-y: auto;
    background: #171310; border: 1px solid rgba(243,239,234,0.1); border-radius: 14px;
    box-shadow: 0 12px 40px rgba(0,0,0,0.55);
    padding: 8px; z-index: 20;
    animation: menu-in 0.12s ease;
  }
  .cp-sessions-heading { font-size: 0.62rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: rgba(243,239,234,0.3); padding: 6px 10px 8px; }
  .cp-sessions-empty { padding: 14px 10px; font-size: 0.78rem; color: rgba(243,239,234,0.3); text-align: center; }
  .cp-session-item {
    display: flex; align-items: center; justify-content: space-between; gap: 10px;
    width: 100%; padding: 10px; border-radius: 9px; border: none;
    background: transparent; cursor: pointer; text-align: left; font-family: inherit;
    transition: background 0.12s;
  }
  .cp-session-item:hover { background: rgba(243,239,234,0.05); }
  .cp-session-item.active { background: rgba(212,168,32,0.1); }
  .cp-session-title { font-size: 0.82rem; font-weight: 600; color: rgba(243,239,234,0.8); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
  .cp-session-item.active .cp-session-title { color: #F3EFEA; }
  .cp-session-time { font-size: 0.66rem; color: rgba(243,239,234,0.28); flex-shrink: 0; }
  .cp-clear:hover { border-color: rgba(212,168,32,0.3); background: rgba(212,168,32,0.06); color: #F3EFEA; }
  .cp-clear:disabled { opacity: 0.4; cursor: not-allowed; }

  /* Welcome screen */
  .cp-welcome { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 32px; gap: 22px; }
  .cp-welcome-icon {
    width: 52px; height: 52px;
    border-radius: 16px;
    background: rgba(212,168,32,0.1);
    border: 1px solid rgba(212,168,32,0.25);
    display: flex; align-items: center; justify-content: center;
    color: #D4A820;
    animation: cp-icon-pulse 2.4s ease-in-out infinite;
  }
  @keyframes cp-icon-pulse {
    0%, 100% { filter: drop-shadow(0 0 4px rgba(212,168,32,0.25)); }
    50%      { filter: drop-shadow(0 0 14px rgba(212,168,32,0.5)); }
  }
  .cp-welcome-title { font-size: 2rem; font-weight: 900; color: #F3EFEA; letter-spacing: -0.03em; text-align: center; }
  .cp-welcome-title span { color: #D4A820; }
  .cp-welcome-sub { font-size: 0.86rem; color: rgba(243,239,234,0.4); text-align: center; margin-top: -12px; }
  .cp-cards { display: flex; flex-wrap: wrap; gap: 14px; justify-content: center; max-width: 800px; margin-top: 8px; }
  .cp-card {
    width: 234px;
    display: flex; flex-direction: column; gap: 10px;
    text-align: left;
    background: rgba(243,239,234,0.035);
    border: 1px solid rgba(243,239,234,0.08);
    border-radius: 16px;
    padding: 18px;
    cursor: pointer;
    font-family: inherit;
    transition: border-color 0.15s, background 0.15s, transform 0.15s;
  }
  .cp-card:hover { border-color: rgba(212,168,32,0.35); background: rgba(212,168,32,0.05); transform: translateY(-2px); }
  .cp-card-icon {
    width: 34px; height: 34px;
    border-radius: 9px;
    background: rgba(212,168,32,0.1);
    display: flex; align-items: center; justify-content: center;
    color: #D4A820;
  }
  .cp-card-title { font-size: 0.9rem; font-weight: 700; color: #F3EFEA; line-height: 1.3; }
  .cp-card-desc { font-size: 0.76rem; color: rgba(243,239,234,0.4); line-height: 1.55; flex: 1; }
  .cp-card-btn {
    margin-top: 2px;
    padding: 8px 0;
    text-align: center;
    background: rgba(243,239,234,0.05);
    border: 1px solid rgba(243,239,234,0.1);
    border-radius: 9px;
    font-size: 0.73rem; font-weight: 700; color: rgba(243,239,234,0.65);
    transition: all 0.15s;
  }
  .cp-card:hover .cp-card-btn { background: #D4A820; border-color: #D4A820; color: #0A0800; }

  /* Messages */
  .cp-messages { flex: 1; min-height: 0; overflow-y: auto; padding: 16px 32px 8px; scrollbar-width: thin; scrollbar-color: rgba(243,239,234,0.08) transparent; display: flex; flex-direction: column; gap: 16px; }
  .cp-messages::-webkit-scrollbar { width: 4px; }
  .cp-messages::-webkit-scrollbar-thumb { background: rgba(243,239,234,0.08); border-radius: 4px; }

  .cp-msg { display: flex; flex-direction: column; gap: 8px; max-width: 720px; }
  .cp-msg.user { align-self: flex-end; }
  .cp-msg.assistant { align-self: flex-start; max-width: 680px; }

  .cp-msg-mark { opacity: 0.9; }

  .cp-bubble { padding: 12px 16px; border-radius: 14px; font-size: 0.88rem; line-height: 1.6; white-space: pre-wrap; max-width: 560px; }
  .cp-msg.assistant .cp-bubble { background: transparent; border: none; padding: 0; color: rgba(243,239,234,0.88); max-width: none; }
  .cp-msg.user .cp-bubble { background: rgba(212,168,32,0.12); border: 1px solid rgba(212,168,32,0.2); color: #F3EFEA; border-radius: 14px 4px 14px 14px; }
  .cp-bubble img { max-width: 240px; border-radius: 8px; display: block; margin-top: 8px; }

  .cp-typing { display: flex; gap: 4px; align-items: center; padding: 4px 0; }
  .cp-typing span { width: 5px; height: 5px; border-radius: 2px; background: rgba(212,168,32,0.5); animation: typing-dot 1.2s ease-in-out infinite; }
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

  .cp-input-wrap { position: relative; max-width: 760px; margin: 0 auto; width: 100%; }
  .cp-input-box { display: flex; align-items: flex-end; gap: 8px; background: rgba(243,239,234,0.05); border: 1px solid rgba(243,239,234,0.1); border-radius: 16px; padding: 8px 8px 8px 16px; transition: border-color 0.18s, box-shadow 0.18s; }
  .cp-input-box:focus-within { border-color: rgba(212,168,32,0.35); box-shadow: 0 0 0 3px rgba(212,168,32,0.08); }

  .cp-icon-btn { width: 36px; height: 36px; flex-shrink: 0; border-radius: 10px; border: none; background: rgba(243,239,234,0.06); color: rgba(243,239,234,0.4); cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.15s; }
  .cp-icon-btn:hover { background: rgba(243,239,234,0.1); color: rgba(243,239,234,0.8); }
  .cp-icon-btn.active { background: rgba(240,122,100,0.15); color: #F07A64; }
  .cp-icon-btn.recording { background: rgba(212,168,32,0.18); color: #D4A820; }
  @keyframes rec-pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }

  .cp-textarea { flex: 1; background: transparent; border: none; outline: none; color: #F3EFEA; font-family: inherit; font-size: 0.88rem; line-height: 1.5; resize: none; min-height: 22px; max-height: 140px; overflow-y: auto; padding: 7px 0; }
  .cp-textarea::placeholder { color: rgba(243,239,234,0.22); }

  .cp-send { width: 38px; height: 38px; flex-shrink: 0; border-radius: 10px; border: none; background: #D4A820; color: #0C0A08; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: background 0.15s, opacity 0.15s, transform 0.15s; }
  .cp-send:hover:not(:disabled) { background: #E8C030; transform: translateY(-1px); }
  .cp-send:disabled { opacity: 0.3; cursor: not-allowed; }

  /* Image preview */
  .cp-img-preview { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; padding: 8px 10px; background: rgba(243,239,234,0.04); border: 1px solid rgba(243,239,234,0.08); border-radius: 10px; }
  .cp-img-thumb { width: 40px; height: 40px; border-radius: 6px; object-fit: cover; }
  .cp-img-name { font-size: 0.75rem; color: rgba(243,239,234,0.5); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .cp-img-remove { background: none; border: none; color: rgba(243,239,234,0.3); cursor: pointer; font-size: 1rem; padding: 0; transition: color 0.12s; }
  .cp-img-remove:hover { color: #F07A64; }

  .cp-hint { text-align: center; margin-bottom: 10px; font-size: 0.76rem; font-weight: 500; color: rgba(243,239,234,0.38); }

  .cp-mic-bar { display: flex; align-items: center; gap: 14px; padding: 14px 18px; background: rgba(212,168,32,0.09); border: 1px solid rgba(212,168,32,0.4); border-radius: 14px; margin-bottom: 10px; box-shadow: 0 0 28px rgba(212,168,32,0.14); }
  .cp-mic-label { font-size: 0.95rem; font-weight: 800; color: #D4A820; flex-shrink: 0; white-space: nowrap; letter-spacing: -0.01em; }
  .cp-wave { display: flex; align-items: center; gap: 3px; height: 30px; flex: 1; }
  .cp-wave-bar { width: 3px; border-radius: 2px; background: linear-gradient(180deg, #F8E060, #D4A820); min-height: 3px; transition: height 0.08s ease-out; }

  @media (max-width: 860px) {
    .cp { height: auto; min-height: calc(100vh - 70px); }
    .cp-messages, .cp-header, .cp-footer { padding-left: 16px; padding-right: 16px; }
    .cp-welcome { padding: 24px 16px; }
    .cp-welcome-title { font-size: 1.45rem; }
    .cp-bubble { max-width: 90vw; }
  }
`;

const SUGGESTION_CARDS = [
  {
    icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M2 14V8M7 14V2M12 14v-5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>,
    title: 'Como estão meus gastos?',
    desc: 'Um raio-x rápido de pra onde seu dinheiro foi esse mês.',
    prompt: 'Analise meus gastos do mês e me diga onde posso economizar.',
    action: 'Ver resumo',
  },
  {
    icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.6"/><path d="M11 11l3.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>,
    title: 'Tem tarifa escondida?',
    desc: 'Encontre cobranças que você nem sabia que estava pagando.',
    prompt: 'Quais tarifas estou pagando e quais dá pra cortar?',
    action: 'Analisar tarifas',
  },
  {
    icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.6"/><circle cx="8" cy="8" r="2" fill="currentColor"/></svg>,
    title: 'Financiar ou investir?',
    desc: 'Simule financiamento, consórcio ou investir o dinheiro.',
    prompt: 'Vale mais a pena financiar, fazer consórcio ou investir o dinheiro?',
    action: 'Simular',
  },
];

function greetingNow() {
  const h = new Date().getHours();
  if (h < 12) return 'Bom dia';
  if (h < 18) return 'Boa tarde';
  return 'Boa noite';
}

export const ChatPage: React.FC = () => {
  const userId = localStorage.getItem('user_id') || '';
  const userName = localStorage.getItem('user_name') || localStorage.getItem('user_email') || 'U';
  const firstName = userName.includes('@') ? userName.split('@')[0] : userName.split(' ')[0];

  const sessionKey = useMemo(() => `hive-session:${userId || 'anon'}`, [userId]);
  const endRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const waveRafRef = useRef<number | undefined>(undefined);

  const WAVE_BARS = 26;

  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const [imagePreview, setImagePreview] = useState<{ dataUrl: string; name: string } | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [waveLevels, setWaveLevels] = useState<number[]>(() => Array(WAVE_BARS).fill(0.08));
  const [showSessions, setShowSessions] = useState(false);
  const [sessionId, setSessionId] = useState(() => {
    try { return localStorage.getItem(sessionKey) || newSessionId(); }
    catch { return newSessionId(); }
  });

  const storageKey = useMemo(() => `hive-chat:${userId || 'anon'}:${sessionId}`, [userId, sessionId]);

  const hasSpeech = typeof window !== 'undefined' && !!(window.SpeechRecognition || window.webkitSpeechRecognition);

  const historyQuery = useQuery<ChatHistoryItem[]>({
    queryKey: ['chat-history', userId, sessionId],
    queryFn: () => nexaApi.getChatHistory(userId, 100, sessionId),
    enabled: !!userId,
  });

  const sessionsQuery = useQuery<ChatSessionItem[]>({
    queryKey: ['chat-sessions', userId],
    queryFn: () => nexaApi.getChatSessions(userId),
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
    if (historyQuery.data === undefined) return; // esta sessão ainda não resolveu
    const history = historyQuery.data
      .map(mapHistoryItem)
      .filter(m => m.content.trim())
      .sort((a, b) => (a.id ?? 0) - (b.id ?? 0));
    setMessages(history);
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
      void sessionsQuery.refetch();
    },
    onError: () => {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Não consegui responder agora. Verifique se o backend está ativo.',
        ts: new Date().toISOString(),
      }]);
    },
  });

  // "Nova conversa": só abre uma sessão nova e vazia — as conversas
  // anteriores continuam existindo e acessíveis pela lista de sessões.
  const clearChat = () => {
    const sid = newSessionId();
    setSessionId(sid);
    setMessages([]);
    setImagePreview(null);
    setShowSessions(false);
    try { localStorage.setItem(sessionKey, sid); } catch {}
  };

  const switchSession = (sid: string) => {
    setShowSessions(false);
    if (sid === sessionId) return;
    setSessionId(sid);
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

  const stopWave = useCallback(() => {
    if (waveRafRef.current) cancelAnimationFrame(waveRafRef.current);
    waveRafRef.current = undefined;
    micStreamRef.current?.getTracks().forEach(t => t.stop());
    micStreamRef.current = null;
    if (audioCtxRef.current) { audioCtxRef.current.close().catch(() => {}); audioCtxRef.current = null; }
    analyserRef.current = null;
    setWaveLevels(Array(WAVE_BARS).fill(0.08));
  }, []);

  const startWave = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micStreamRef.current = stream;
      const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new AudioCtx();
      audioCtxRef.current = ctx;
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 128;
      analyser.smoothingTimeConstant = 0.75;
      source.connect(analyser);
      analyserRef.current = analyser;

      const freqData = new Uint8Array(analyser.frequencyBinCount);
      const bucketSize = Math.max(1, Math.floor(freqData.length / WAVE_BARS));

      const tick = () => {
        analyser.getByteFrequencyData(freqData);
        const bars: number[] = [];
        for (let i = 0; i < WAVE_BARS; i++) {
          let sum = 0;
          const start = i * bucketSize;
          for (let j = 0; j < bucketSize; j++) sum += freqData[start + j] || 0;
          const avg = sum / bucketSize / 255; // 0..1
          bars.push(Math.max(0.08, Math.min(1, avg * 1.6)));
        }
        setWaveLevels(bars);
        waveRafRef.current = requestAnimationFrame(tick);
      };
      tick();
    } catch {
      // Sem permissão de mic para o visualizador — a transcrição por voz ainda funciona.
    }
  }, []);

  useEffect(() => () => stopWave(), [stopWave]);

  const toggleRecording = useCallback(() => {
    if (!hasSpeech) return;
    if (isRecording) {
      recognitionRef.current?.stop();
      setIsRecording(false);
      stopWave();
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
    rec.onerror = () => { setIsRecording(false); stopWave(); };
    rec.onend = () => { setIsRecording(false); stopWave(); };
    recognitionRef.current = rec;
    rec.start();
    setIsRecording(true);
    void startWave();
  }, [hasSpeech, isRecording, startWave, stopWave]);

  const showWelcome = messages.length === 0 && !chatMutation.isPending;

  return (
    <AppShell current="chat">
      <style>{css}</style>
      <div className="cp" onClick={() => { setShowAttachMenu(false); setShowSessions(false); }}>

        {/* Header */}
        <div className="cp-header">
          <div className="cp-header-left">
            <div className="cp-title-row">
              <div className="cp-title">Chat IA</div>
              <button
                className={`cp-sessions-trigger${showSessions ? ' open' : ''}`}
                onClick={e => { e.stopPropagation(); setShowSessions(v => !v); }}
                title="Conversas"
              >
                <svg width="10" height="6" viewBox="0 0 10 6" fill="none"><path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
              </button>

              {showSessions && (
                <div className="cp-sessions-panel" onClick={e => e.stopPropagation()}>
                  <div className="cp-sessions-heading">Conversas</div>
                  {sessionsQuery.isLoading && <div className="cp-sessions-empty">Carregando…</div>}
                  {!sessionsQuery.isLoading && (sessionsQuery.data || []).length === 0 && (
                    <div className="cp-sessions-empty">Suas conversas vão aparecer aqui</div>
                  )}
                  {(sessionsQuery.data || []).map(s => (
                    <button
                      key={s.session_id}
                      className={`cp-session-item${s.session_id === sessionId ? ' active' : ''}`}
                      onClick={() => switchSession(s.session_id)}
                    >
                      <span className="cp-session-title">{s.title}</span>
                      <span className="cp-session-time">{relativeTime(s.last_message_at)}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="cp-subtitle">Agente HIVE — Inteligência Financeira</div>
          </div>
          <button className="cp-clear" onClick={clearChat} disabled={historyQuery.isLoading}>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M6 1v10M1 6h10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>
            Nova conversa
          </button>
        </div>

        {/* Welcome or Messages */}
        {showWelcome ? (
          <div className="cp-welcome">
            <div className="cp-welcome-icon">
              <svg width="24" height="27" viewBox="0 0 180 200" fill="none">
                <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="#7A5002"/>
                <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="#D4A820"/>
                <polygon points="100,16 110,22 110,178 100,184" fill="#0A0800"/>
              </svg>
            </div>
            <div className="cp-welcome-title">
              {greetingNow()}, <span>{firstName || 'você'}</span>
            </div>
            <div className="cp-welcome-sub">O que você quer entender sobre o seu dinheiro hoje?</div>
            <div className="cp-cards">
              {SUGGESTION_CARDS.map((c, i) => (
                <button key={i} className="cp-card" onClick={() => send(c.prompt)}>
                  <div className="cp-card-icon">{c.icon}</div>
                  <div className="cp-card-title">{c.title}</div>
                  <div className="cp-card-desc">{c.desc}</div>
                  <div className="cp-card-btn">{c.action}</div>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="cp-messages">
            {messages.map((m, i) => (
              <div key={`${m.ts}-${i}`} className={`cp-msg ${m.role}`}>
                {m.role === 'assistant' && <div className="cp-msg-mark"><HiveGlyph size={18} /></div>}
                <div className="cp-bubble">
                  {m.content}
                  {m.image && <img src={m.image} alt="anexo" />}
                </div>
              </div>
            ))}
            {chatMutation.isPending && (
              <div className="cp-msg assistant">
                <div className="cp-msg-mark"><HiveGlyph size={18} /></div>
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
              <span className="cp-mic-label">Ouvindo...</span>
              <div className="cp-wave">
                {waveLevels.map((lvl, i) => (
                  <div key={i} className="cp-wave-bar" style={{ height: `${Math.max(3, Math.round(lvl * 30))}px` }} />
                ))}
              </div>
            </div>
          )}
          {imagePreview && (
            <div className="cp-img-preview">
              <img src={imagePreview.dataUrl} alt="preview" className="cp-img-thumb" />
              <span className="cp-img-name">{imagePreview.name}</span>
              <button className="cp-img-remove" onClick={() => setImagePreview(null)}>✕</button>
            </div>
          )}
          <div className="cp-hint">HIVE IA pode cometer erros — verifique informações importantes.</div>
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
