import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { AppShell } from '../components/layout/AppShell';
import { nexaApi } from '../api/nexa';
import type { ChatHistoryItem } from '../api/types';

type Message = {
  role: 'user' | 'assistant';
  content: string;
  ts: string;
};

function mapHistoryItem(item: ChatHistoryItem): Message {
  return {
    role: item.role === 'assistant' ? 'assistant' : 'user',
    content: item.content,
    ts: item.created_at || new Date().toISOString(),
  };
}

function generateChatSessionId() {
  return globalThis.crypto?.randomUUID?.() || `chat-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export const ChatPage: React.FC = () => {
  const userId = localStorage.getItem('user_id') || '';
  const storageKey = useMemo(() => `nexa-chat-history:${userId || 'anon'}`, [userId]);
  const sessionKey = useMemo(() => `nexa-chat-session:${userId || 'anon'}`, [userId]);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const defaultAssistantMessage = useMemo<Message>(
    () => ({
      role: 'assistant',
      content:
        'Olá! Sou o assistente Nexa. Posso analisar seu orçamento, metas, cartões e simulações de compra.',
      ts: new Date().toISOString(),
    }),
    []
  );

  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([defaultAssistantMessage]);
  const [sessionId, setSessionId] = useState(() => {
    try {
      return localStorage.getItem(sessionKey) || generateChatSessionId();
    } catch {
      return generateChatSessionId();
    }
  });

  const historyQuery = useQuery<ChatHistoryItem[]>({
    queryKey: ['chat-history', userId],
    queryFn: () => nexaApi.getChatHistory(userId, 100),
    enabled: !!userId,
  });

  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (!raw) {
        setMessages([defaultAssistantMessage]);
        return;
      }

      const parsed = JSON.parse(raw) as Message[];
      if (!Array.isArray(parsed) || parsed.length === 0) {
        setMessages([defaultAssistantMessage]);
        return;
      }

      setMessages(parsed);
    } catch {
      setMessages([defaultAssistantMessage]);
    }
  }, [defaultAssistantMessage, storageKey]);

  useEffect(() => {
    const history = (historyQuery.data || [])
      .map(mapHistoryItem)
      .filter((item) => item.content.trim().length > 0);

    if (history.length > 0) {
      setMessages(history);
    }
  }, [historyQuery.data]);

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(messages));
    } catch {
      // Ignora falha de persistência no navegador.
    }
  }, [messages, storageKey]);

  useEffect(() => {
    try {
      localStorage.setItem(sessionKey, sessionId);
    } catch {
      // Ignora falha de persistência no navegador.
    }
  }, [sessionId, sessionKey]);

  useEffect(() => {
    if (messagesEndRef.current && typeof messagesEndRef.current.scrollIntoView === 'function') {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [messages]);

  const chatMutation = useMutation({
    mutationFn: (message: string) => nexaApi.sendChatMessage(userId, message, sessionId),
    onSuccess: (data) => {
      const content =
        data?.response ||
        data?.answer ||
        data?.message ||
        'Recebi sua mensagem, mas a API não retornou texto de resposta.';

      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: String(content), ts: new Date().toISOString() },
      ]);
      void historyQuery.refetch();
    },
    onError: () => {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content:
            'Não consegui responder agora. Verifique se o backend está ativo e se a chave do provedor de IA está configurada.',
          ts: new Date().toISOString(),
        },
      ]);
    },
  });

  const clearChat = async () => {
    const nextSessionId = generateChatSessionId();
    const initial = [defaultAssistantMessage];

    setSessionId(nextSessionId);
    setMessages(initial);
    try {
      localStorage.setItem(storageKey, JSON.stringify(initial));
      localStorage.setItem(sessionKey, nextSessionId);
    } catch {
      // Ignora falha de persistência no navegador.
    }

    try {
      await nexaApi.clearChatHistory(userId);
      await historyQuery.refetch();
    } catch {
      // Mantém o estado local limpo mesmo se a exclusão remota falhar.
    }
  };

  const send = () => {
    const text = input.trim();
    if (!userId || !text || chatMutation.isPending) {
      return;
    }

    setMessages((prev) => [
      ...prev,
      { role: 'user', content: text, ts: new Date().toISOString() },
    ]);
    setInput('');
    chatMutation.mutate(text);
  };

  return (
    <AppShell
      current="chat"
      title="Chat Inteligente"
      subtitle="Converse com o agente Nexa para diagnósticos e recomendações financeiras."
    >
      <div
        style={{
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-color)',
          borderRadius: 12,
          padding: 14,
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
          height: 'calc(100vh - 220px)',
          maxHeight: 760,
          minHeight: 520,
          overflow: 'hidden',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>
            {historyQuery.isLoading
              ? 'Carregando memória do chat...'
              : historyQuery.isError
                ? 'Memória remota indisponível; usando histórico local do navegador.'
                : messages.length > 1
                  ? `${messages.length - 1} mensagens salvas`
                  : 'Nenhuma conversa salva ainda'}
          </div>

          <button
            onClick={clearChat}
            disabled={historyQuery.isLoading}
            style={{
              border: '1px solid var(--border-color)',
              background: 'var(--bg-surface)',
              color: 'var(--text-secondary)',
              borderRadius: 8,
              padding: '6px 10px',
              cursor: 'pointer',
              fontSize: 12,
              opacity: historyQuery.isLoading ? 0.7 : 1,
            }}
          >
            Limpar conversa
          </button>
        </div>

        <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: 6, scrollbarGutter: 'stable' }}>
          {messages.map((m, idx) => (
            <div
              key={`${m.ts}-${idx}`}
              style={{
                display: 'flex',
                justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start',
                marginBottom: 10,
              }}
            >
              <div
                style={{
                  maxWidth: '78%',
                  borderRadius: 10,
                  padding: '10px 12px',
                  background: m.role === 'user' ? 'var(--text-primary)' : 'var(--bg-hover)',
                  color: m.role === 'user' ? 'var(--bg-surface)' : 'var(--text-primary)',
                  fontSize: 14,
                  lineHeight: 1.5,
                  whiteSpace: 'pre-wrap',
                }}
              >
                {m.content}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: 10, display: 'flex', gap: 8, flexShrink: 0 }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder="Pergunte sobre orçamento, metas, cartões ou simulações..."
            style={{
              flex: 1,
              border: '1px solid var(--border-color)',
              borderRadius: 8,
              padding: '10px 12px',
              fontSize: 14,
              background: 'var(--bg-surface)',
              color: 'var(--text-primary)',
            }}
          />
          <button
            onClick={send}
            disabled={chatMutation.isPending}
            style={{
              border: '1px solid #111',
              background: 'var(--text-primary)',
              color: 'var(--bg-surface)',
              borderRadius: 8,
              padding: '10px 14px',
              cursor: 'pointer',
              fontSize: 13,
              opacity: chatMutation.isPending ? 0.6 : 1,
            }}
          >
            {chatMutation.isPending ? 'Enviando...' : 'Enviar'}
          </button>
        </div>
      </div>
    </AppShell>
  );
};
