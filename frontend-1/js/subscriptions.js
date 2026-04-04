/**
 * subscriptions.js — Renderiza assinaturas consumindo /subscriptions/{user_id}
 */

async function loadSubscriptions() {
  const userId = auth.getUserId();
  if (!userId) return;

  const container = document.getElementById('ass-list');
  const loading = document.getElementById('ass-list-loading');
  if (loading) loading.textContent = 'Carregando assinaturas...';

  try {
    const data = await api.getSubscriptions(userId);
    const subs = Array.isArray(data) ? data : (data.subscriptions || data.items || []);

    if (!subs || subs.length === 0) {
      container.innerHTML = '<div style="padding:14px;color:var(--text-muted);">Nenhuma assinatura encontrada.</div>';
      return;
    }

    // Agrupar por categoria se disponível
    const groups = {};
    subs.forEach(s => {
      const cat = s.category || s.service_type || 'Outros';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(s);
    });

    // Render
    const html = Object.entries(groups).map(([cat, items]) => {
      const itemsHtml = items.map(it => {
        const name = it.service_name || it.description || it.name || 'Assinatura';
        const amt  = it.amount || it.estimated_amount || it.monthly_amount || 0;
        return `<div class="ass-item" style="border-bottom:1px solid var(--bg);display:flex;align-items:center;justify-content:space-between;padding:12px 16px;">
          <div style="display:flex;align-items:center;gap:10px;"><div class="ass-icon"></div><span class="ass-name">${escapeHtml(name)}</span></div>
          <span class="ass-val">${formatBRL(amt)}</span>
        </div>`;
      }).join('');
      return `<div>
        <div style="font-size:11px;font-weight:600;color:var(--text-muted);padding:12px 16px 6px;text-transform:uppercase;letter-spacing:0.5px;">${escapeHtml(cat)}</div>
        ${itemsHtml}
      </div>`;
    }).join('');

    container.innerHTML = html;

    // Atualizar resumo (count + total mensal)
    try {
      const count = subs.length;
      const total = subs.reduce((s, it) => {
        const amt = Number(it.monthly_amount || it.amount || it.estimated_amount || 0) || 0;
        return s + amt;
      }, 0);
      const cntEl = document.getElementById('ass-count');
      const totEl = document.getElementById('ass-total');
      const topEl = document.getElementById('ass-top-list');
      const headerEl = document.getElementById('ass-ver-todas-header');
      if (cntEl) cntEl.textContent = String(count);
      if (totEl) totEl.textContent = formatBRL(total);
      if (headerEl) headerEl.textContent = `${count} assinaturas ativas — ${formatBRL(total)}/mês`;

      // Top 4 assinaturas (por valor) para o card compacto
      if (topEl) {
        const top = subs.slice().sort((a,b) => (Number(b.monthly_amount||b.amount||b.estimated_amount||0) - Number(a.monthly_amount||a.amount||a.estimated_amount||0))).slice(0,4);
        topEl.innerHTML = top.map(it => {
          const name = it.service_name || it.description || it.name || 'Assinatura';
          return `<div style="display:flex;align-items:center;gap:5px;font-size:11px;color:var(--text-mid);">
            <span style="width:10px;height:10px;background:var(--blue-primary);border-radius:3px;flex-shrink:0;"></span>${escapeHtml(name)}
          </div>`;
        }).join('');
      }
    } catch (e) { /* não fatal */ }
  } catch (err) {
    console.error('[Subscriptions] Erro:', err);
    container.innerHTML = '<div style="padding:12px;color:var(--red);">Erro ao carregar assinaturas.</div>';
  }
}

function escapeHtml(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

window.loadSubscriptions = loadSubscriptions;
