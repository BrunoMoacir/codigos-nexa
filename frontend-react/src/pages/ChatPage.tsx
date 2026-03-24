import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { AppShell } from '../components/layout/AppShell';
import { nexaApi } from '../api/nexa';

type Message = {
  role: 'user' | 'assistant';
  content: string;
  ts: string;
};

export const ChatPage: React.FC = () => {
  const userId = localStorage.getItem('user_id') || '';
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content:
        'Olá! Sou o assistente Nexa. Posso analisar seu orçamento, metas, cartões e simulações de compra.',
      ts: new Date().toISOString(),
    },
  ]);

  const chatMutation = useMutation({
    mutationFn: (message: string) => nexaApi.sendChatMessage(userId, message),
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

  const send = () => {
    const text = input.trim();
    if (!text || chatMutation.isPending) {
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
          background: '#fff',
          border: '1px solid #ebebeb',
          borderRadius: 12,
          padding: 14,
          display: 'grid',
          gridTemplateRows: '1fr auto',
          minHeight: 580,
        }}
      >
        <div style={{ overflowY: 'auto', padding: 6 }}>
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
                  background: m.role === 'user' ? '#111' : '#f5f5f5',
                  color: m.role === 'user' ? '#fff' : '#222',
                  fontSize: 14,
                  lineHeight: 1.5,
                  whiteSpace: 'pre-wrap',
                }}
              >
                {m.content}
              </div>
            </div>
          ))}
        </div>

        <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 10, display: 'flex', gap: 8 }}>
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
              border: '1px solid #ddd',
              borderRadius: 8,
              padding: '10px 12px',
              fontSize: 14,
            }}
          />
          <button
            onClick={send}
            disabled={chatMutation.isPending}
            style={{
              border: '1px solid #111',
              background: '#111',
              color: '#fff',
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
