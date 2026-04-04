/**
 * chat.js — UI mínima de chat que consome as rotas reais (/chat/ e /chat/history)
 */

async function loadChat() {
  const userId = auth.getUserId();
  if (!userId) return;

  const container = document.getElementById('chat-history');
  if (!container) return;
  container.innerHTML = '<div style="padding:12px;text-align:center;color:var(--text-muted);">Carregando conversa...</div>';

  try {
    const data = await api.getChatHistory(userId, 200);
    const msgs = Array.isArray(data) ? data : (data.messages || data.items || data.data || []);
    renderChatHistory(msgs);
  } catch (err) {
    console.error('[Chat] Erro ao carregar histórico:', err);
    container.innerHTML = '<div style="padding:12px;text-align:center;color:var(--red);">Erro ao carregar conversa.</div>';
  }
}

function renderChatHistory(msgs) {
  const container = document.getElementById('chat-history');
  if (!container) return;
  if (!msgs || msgs.length === 0) {
    container.innerHTML = '<div style="padding:12px;text-align:center;color:var(--text-muted);">Nenhuma mensagem ainda. Pergunte algo sobre suas finanças!</div>';
    return;
  }

  container.innerHTML = msgs.map(m => {
    // Suporta formatos: { role: 'user'|'assistant', text } ou { from: 'user'|'bot', message }
    const role = (m.role || m.from || '').toLowerCase();
    const text = m.text || m.message || m.content || m.body || '';
    const when = m.created_at ? new Date(m.created_at).toLocaleString() : '';
    const cls = role === 'user' || role === 'me' ? 'chat-msg-me' : 'chat-msg-bot';
    return `<div style="display:flex;flex-direction:column;gap:6px;margin-bottom:8px;align-items:${cls==='chat-msg-me'?'flex-end':'flex-start'};">
      <div style="max-width:82%;padding:10px 12px;border-radius:12px;background:${cls==='chat-msg-me'?'var(--blue-primary)':'var(--card-bg)'};color:${cls==='chat-msg-me'? '#fff':'var(--text-dark)'};">${escapeHtml(text)}</div>
      <div style="font-size:11px;color:var(--text-muted);">${when}</div>
    </div>`;
  }).join('');

  // Scroll to bottom
  container.scrollTop = container.scrollHeight;
}

function escapeHtml(s) {
  if (!s) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

async function sendChatUI() {
  const input = document.getElementById('chat-input');
  const btn   = document.getElementById('chat-send');
  const userId = auth.getUserId();
  if (!input || !userId) return;
  const text = input.value.trim();
  if (!text) return;

  btn.disabled = true;
  btn.textContent = 'Enviando...';

  try {
    // POST /chat/
    await api.sendChatMessage(userId, text);
    input.value = '';
    // Recarregar histórico (simple and reliable)
    await loadChat();
  } catch (err) {
    console.error('[Chat] Erro ao enviar:', err);
    alert('Erro ao enviar mensagem: ' + (err.message || '')); 
  } finally {
    btn.disabled = false;
    btn.textContent = 'Enviar';
  }
}

window.loadChat = loadChat;
window.sendChatUI = sendChatUI;
window.sendChatMessage = sendChatUI;
