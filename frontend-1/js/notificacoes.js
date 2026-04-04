/**
 * notificacoes.js — Notificações reais da API
 *
 * Consome: GET /notifications/{user_id}
 */

async function loadNotificacoes() {
  const userId = auth.getUserId();
  if (!userId) return;

  const forecast = window._forecastData;
  const health   = forecast?.financial_health || {};
  const income   = health.total_income ? health.total_income / Math.max(1, forecast?.period_analyzed_days / 30) : 0;

  try {
    const data = await api.getNotifications(userId, income);
    const notifs = Array.isArray(data) ? data : (data.notifications || data.alerts || data.items || []);
    renderNotificacoes(notifs);

    // Atualizar badge no header
    const badge = document.getElementById('notif-badge');
    if (badge) {
      const unread = notifs.filter(n => !n.read).length;
      badge.style.display = unread > 0 ? '' : 'none';
    }
  } catch (err) {
    console.error('[Notificacoes] Erro:', err);
  }
}

const NOTIF_ICONS = {
  ALERT:   { bg: '#FEE9E7', stroke: 'var(--red)',    svgPath: '<rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/>' },
  WARNING: { bg: '#FFF3E0', stroke: 'var(--orange)',  svgPath: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>' },
  SUCCESS: { bg: '#E8F5E9', stroke: 'var(--green)',   svgPath: '<polyline points="20 6 9 17 4 12"/>' },
  INFO:    { bg: 'var(--blue-lighter)', stroke: 'var(--blue-primary)', svgPath: '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>' },
};

function notifIcon(type) {
  return NOTIF_ICONS[type?.toUpperCase()] || NOTIF_ICONS.INFO;
}

function notifTimeAgo(dateStr) {
  if (!dateStr) return '';
  const d    = new Date(dateStr);
  const now  = new Date();
  const diff = (now - d) / 60000; // minutos
  if (diff < 1)   return 'Agora ';
  if (diff < 60)  return `Há ${Math.round(diff)} min`;
  if (diff < 1440) return `Há ${Math.round(diff / 60)} horas`;
  return `Há ${Math.round(diff / 1440)} dias`;
}

function renderNotificacoes(notifs) {
  const contentEl = document.querySelector('#screen-notificacoes .content');
  if (!contentEl) return;

  if (!notifs || notifs.length === 0) {
    contentEl.innerHTML = `<div style="padding:48px 20px;text-align:center;">
      <div style="font-size:40px;margin-bottom:12px;">🔔</div>
      <div style="font-size:15px;font-weight:600;color:var(--text-dark);">Sem notificações</div>
      <div style="font-size:13px;color:var(--text-muted);margin-top:6px;">Você está em dia com tudo!</div>
    </div>`;
    return;
  }

  // Separar hoje vs esta semana
  const hoje = new Date();
  hoje.setHours(0, 0, 0, 0);
  const hijosNotifs  = notifs.filter(n => n.created_at && new Date(n.created_at) >= hoje);
  const semanaNotifs = notifs.filter(n => !n.created_at || new Date(n.created_at) < hoje);

  function renderGrupo(lista, titulo) {
    if (!lista.length) return '';
    return `<div>
      <div style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.8px;margin-bottom:8px;">${titulo}</div>
      <div class="card" style="padding:0;overflow:hidden;">
        ${lista.map(n => {
          const ic   = notifIcon(n.type || n.level);
          const unread = !n.read;
          return `<div class="notif-item${unread ? ' notif-unread' : ''}" onclick="marcarLida(this)">
            <div class="notif-icon" style="background:${ic.bg};">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="${ic.stroke}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ic.svgPath}</svg>
            </div>
            <div class="notif-body">
              <div class="notif-title">${n.title || n.message?.substring(0, 40) || 'Notificação'}</div>
              <div class="notif-desc">${n.body || n.message || n.description || ''}</div>
              <div class="notif-time">${notifTimeAgo(n.created_at)}</div>
            </div>
            ${unread ? '<div class="notif-dot"></div>' : ''}
          </div>`;
        }).join('')}
      </div>
    </div>`;
  }

  contentEl.innerHTML =
    renderGrupo(hijosNotifs,  'Hoje') +
    renderGrupo(semanaNotifs, 'Anteriores');
}

function marcarLida(el) {
  el.classList.remove('notif-unread');
  const dot = el.querySelector('.notif-dot');
  if (dot) dot.remove();
  // Atualizar badge
  const totalUnread = document.querySelectorAll('.notif-unread').length;
  const badge = document.getElementById('notif-badge');
  if (badge) badge.style.display = totalUnread > 0 ? '' : 'none';
}

function marcarTodasLidas() {
  document.querySelectorAll('.notif-dot').forEach(d => d.style.display = 'none');
  document.querySelectorAll('.notif-unread').forEach(n => n.classList.remove('notif-unread'));
  const badge = document.getElementById('notif-badge');
  if (badge) badge.style.display = 'none';
}

window.loadNotificacoes  = loadNotificacoes;
window.marcarLida        = marcarLida;
window.marcarTodasLidas  = marcarTodasLidas;
