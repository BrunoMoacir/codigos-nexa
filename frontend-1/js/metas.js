/**
 * metas.js — CRUD de Metas Financeiras via API real
 *
 * Consome:
 *   GET    /goals/{user_id}
 *   POST   /goals/{user_id}
 *   PATCH  /goals/{user_id}/{goal_id}/progress
 *   DELETE /goals/{user_id}/{goal_id}
 */

let _metas = [];

const META_ICONS = {
  viagem:    { icon: '✈️', color: 'var(--blue-lighter)', stroke: 'var(--blue-primary)' },
  imovel:    { icon: '🏠', color: '#E8F5E9', stroke: 'var(--green)' },
  carro:     { icon: '🚗', color: '#FFF3E0', stroke: 'var(--orange)' },
  educacao:  { icon: '📚', color: '#EDE7F6', stroke: '#7B1FA2' },
  outros:    { icon: '🎯', color: 'var(--blue-lighter)', stroke: 'var(--blue-primary)' },
};

function metaIcon(type) {
  return META_ICONS[(type || '').toLowerCase()] || META_ICONS.outros;
}

async function loadMetas() {
  const userId = auth.getUserId();
  if (!userId) return;

  const contentEl = document.querySelector('#screen-metas .content');
  if (contentEl) contentEl.style.opacity = '0.5';

  try {
    const data = await api.getGoals(userId, 'ACTIVE');
    _metas = Array.isArray(data) ? data : (data.goals || data.items || []);

    // Também buscar concluídas
    let completedMetas = [];
    try {
      const comp = await api.getGoals(userId, 'COMPLETED');
      completedMetas = Array.isArray(comp) ? comp : (comp.goals || comp.items || []);
    } catch (_) {}

    renderMetas(_metas, completedMetas);
  } catch (err) {
    console.error('[Metas] Erro:', err);
  } finally {
    if (contentEl) contentEl.style.opacity = '1';
  }
}

function renderMetas(ativas, concluidas) {
  const contentEl = document.querySelector('#screen-metas .content');
  if (!contentEl) return;

  // Cards de resumo
  const resumoHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
      <div class="card" style="text-align:center;padding:14px 12px;">
        <div style="font-size:22px;font-weight:800;color:var(--green);">${ativas.length}</div>
        <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">Metas ativas</div>
      </div>
      <div class="card" style="text-align:center;padding:14px 12px;">
        <div style="font-size:22px;font-weight:800;color:var(--blue-primary);">${concluidas.length}</div>
        <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">Concluídas</div>
      </div>
    </div>`;

  // Metas ativas
  const ativasHTML = ativas.map(meta => {
    const prog    = Math.min(100, Math.round((meta.current_amount / meta.target_amount) * 100));
    const faltam  = Math.max(0, meta.target_amount - meta.current_amount);
    const icon    = metaIcon(meta.goal_type);
    const prazo   = meta.target_date
      ? `Vence em ${new Date(meta.target_date).toLocaleDateString('pt-BR', { month: 'short', year: 'numeric' })}`
      : 'Sem prazo definido';
    const corBar  = prog >= 75 ? 'var(--green)' : 'var(--blue-primary)';
    const mensal  = meta.monthly_contribution_needed
      ? `Economia sugerida: <strong style="color:var(--text-dark);">${formatBRL(meta.monthly_contribution_needed)}/mês</strong>`
      : 'Sem cálculo de contribuição';

    return `<div class="card" style="padding:0;overflow:hidden;">
      <div style="padding:14px 16px;border-bottom:1px solid rgba(200,224,248,0.4);">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;">
          <div style="display:flex;align-items:center;gap:10px;">
            <div style="width:36px;height:36px;border-radius:10px;background:${icon.color};display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:18px;">${icon.icon}</div>
            <div>
              <div style="font-size:14px;font-weight:700;color:var(--text-dark);">${meta.name}</div>
              <div style="font-size:12px;color:var(--text-muted);">${prazo}</div>
            </div>
          </div>
          <div style="text-align:right;">
            <div style="font-size:16px;font-weight:800;color:var(--text-dark);">${formatBRL(meta.current_amount)}</div>
            <div style="font-size:11px;color:var(--text-muted);">de ${formatBRL(meta.target_amount)}</div>
          </div>
        </div>
        <div style="background:var(--bg);border-radius:6px;height:8px;overflow:hidden;margin-bottom:6px;">
          <div style="width:${prog}%;height:100%;background:linear-gradient(90deg,${corBar},${corBar}99);border-radius:6px;transition:width 0.6s ease;"></div>
        </div>
        <div style="display:flex;justify-content:space-between;">
          <span style="font-size:12px;color:${corBar};font-weight:600;">${prog}% concluído</span>
          <span style="font-size:12px;color:var(--text-muted);">Faltam ${formatBRL(faltam)}</span>
        </div>
      </div>
      <div style="padding:10px 16px;display:flex;justify-content:space-between;align-items:center;">
        <span style="font-size:12px;color:var(--text-muted);">${mensal}</span>
        <button class="btn-pill" style="font-size:12px;padding:4px 12px;"
          onclick="abrirModalProgressoMeta('${meta.goal_id}','${encodeURIComponent(meta.name)}',${meta.target_amount - meta.current_amount})">
          +Valor
        </button>
      </div>
    </div>`;
  }).join('');

  // Metas concluídas
  const concluidasHTML = concluidas.slice(0, 3).map(meta => {
    const icon = metaIcon(meta.goal_type);
    const dt   = meta.updated_at
      ? new Date(meta.updated_at).toLocaleDateString('pt-BR', { month: 'short', year: 'numeric' })
      : '';
    return `<div class="card" style="opacity:0.75;padding:14px 16px;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div style="display:flex;align-items:center;gap:10px;">
          <div style="width:36px;height:36px;border-radius:10px;background:${icon.color};display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:18px;">${icon.icon}</div>
          <div>
            <div style="font-size:14px;font-weight:700;color:var(--text-dark);">${meta.name}</div>
            <div style="font-size:12px;color:var(--green);font-weight:600;">✓ Concluída${dt ? ' em ' + dt : ''}</div>
          </div>
        </div>
        <div style="font-size:16px;font-weight:800;color:var(--green);">${formatBRL(meta.target_amount)}</div>
      </div>
    </div>`;
  }).join('');

  // Botão nova meta
  const novaBtnHTML = `<button onclick="abrirModalNovaMeta()"
    style="width:100%;background:none;border:2px dashed var(--border);border-radius:var(--radius-md);padding:16px;font-size:14px;font-weight:600;font-family:'Poppins',sans-serif;color:var(--blue-primary);cursor:pointer;display:flex;align-items:center;justify-content:center;gap:8px;">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--blue-primary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
    Nova meta
  </button>`;

  contentEl.innerHTML = resumoHTML + ativasHTML + concluidasHTML + novaBtnHTML;
}

// ─── MODAL NOVA META ─────────────────────────────────────────────────────────
function abrirModalNovaMeta() {
  const existing = document.getElementById('modal-nova-meta');
  if (existing) existing.remove();

  const modal = document.createElement('div');
  modal.id = 'modal-nova-meta';
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:200;display:flex;align-items:flex-end;';
  modal.innerHTML = `
    <div style="background:var(--card-bg);width:100%;max-width:430px;margin:0 auto;border-radius:20px 20px 0 0;padding:24px 20px;max-height:80vh;overflow-y:auto;">
      <div style="font-size:16px;font-weight:700;color:var(--text-dark);margin-bottom:16px;">Nova meta financeira</div>
      <div class="perfil-campo" style="margin-bottom:12px;">
        <div class="perfil-campo-label">Nome da meta</div>
        <div style="padding:12px 16px;"><input id="nm-nome" type="text" placeholder="Ex: Viagem para Europa" style="width:100%;border:none;background:transparent;font-size:14px;font-family:'Poppins',sans-serif;color:var(--text-dark);outline:none;"/></div>
      </div>
      <div class="perfil-campo" style="margin-bottom:12px;">
        <div class="perfil-campo-label">Tipo</div>
        <div style="padding:8px 16px;">
          <select id="nm-tipo" style="width:100%;border:none;background:transparent;font-size:14px;font-family:'Poppins',sans-serif;color:var(--text-dark);outline:none;">
            <option value="outros">Outros</option>
            <option value="viagem">Viagem</option>
            <option value="imovel">Imóvel</option>
            <option value="carro">Carro</option>
            <option value="educacao">Educação</option>
          </select>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px;">
        <div class="perfil-campo">
          <div class="perfil-campo-label">Valor alvo (R$)</div>
          <div style="padding:12px 16px;"><input id="nm-alvo" type="number" placeholder="0,00" style="width:100%;border:none;background:transparent;font-size:14px;font-family:'Poppins',sans-serif;color:var(--text-dark);outline:none;"/></div>
        </div>
        <div class="perfil-campo">
          <div class="perfil-campo-label">Já guardei (R$)</div>
          <div style="padding:12px 16px;"><input id="nm-atual" type="number" placeholder="0,00" style="width:100%;border:none;background:transparent;font-size:14px;font-family:'Poppins',sans-serif;color:var(--text-dark);outline:none;"/></div>
        </div>
      </div>
      <div class="perfil-campo" style="margin-bottom:20px;">
        <div class="perfil-campo-label">Data alvo (opcional)</div>
        <div style="padding:12px 16px;"><input id="nm-data" type="date" style="width:100%;border:none;background:transparent;font-size:14px;font-family:'Poppins',sans-serif;color:var(--text-dark);outline:none;"/></div>
      </div>
      <div id="nm-error" style="color:var(--red);font-size:12px;margin-bottom:8px;"></div>
      <button id="nm-btn" onclick="confirmarNovaMeta()" class="confirmar-btn" style="background:var(--blue-primary);color:#fff;">Criar meta</button>
      <button onclick="document.getElementById('modal-nova-meta').remove()" style="width:100%;background:none;border:none;margin-top:10px;font-size:13px;color:var(--text-muted);font-family:'Poppins',sans-serif;cursor:pointer;">Cancelar</button>
    </div>`;
  document.body.appendChild(modal);
}

async function confirmarNovaMeta() {
  const nome    = document.getElementById('nm-nome')?.value.trim();
  const tipo    = document.getElementById('nm-tipo')?.value;
  const alvo    = parseFloat(document.getElementById('nm-alvo')?.value || '0');
  const atual   = parseFloat(document.getElementById('nm-atual')?.value || '0');
  const data    = document.getElementById('nm-data')?.value;
  const errEl   = document.getElementById('nm-error');
  const btn     = document.getElementById('nm-btn');

  if (!nome || alvo <= 0) {
    if (errEl) errEl.textContent = 'Preencha o nome e o valor alvo.';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Criando...';
  if (errEl) errEl.textContent = '';

  try {
    await api.createGoal(auth.getUserId(), {
      name: nome,
      goal_type: tipo,
      target_amount: alvo,
      current_amount: atual,
      target_date: data || undefined,
    });
    document.getElementById('modal-nova-meta')?.remove();
    await loadMetas();
  } catch (err) {
    if (errEl) errEl.textContent = err.message || 'Erro ao criar meta.';
    btn.disabled = false;
    btn.textContent = 'Criar meta';
  }
}

// ─── MODAL PROGRESSO ─────────────────────────────────────────────────────────
function abrirModalProgressoMeta(goalId, nomeEnc, restante) {
  const nome = decodeURIComponent(nomeEnc);
  const existing = document.getElementById('modal-progresso-meta');
  if (existing) existing.remove();

  const modal = document.createElement('div');
  modal.id = 'modal-progresso-meta';
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:200;display:flex;align-items:flex-end;';
  modal.innerHTML = `
    <div style="background:var(--card-bg);width:100%;max-width:430px;margin:0 auto;border-radius:20px 20px 0 0;padding:24px 20px;">
      <div style="font-size:16px;font-weight:700;color:var(--text-dark);margin-bottom:4px;">Adicionar valor</div>
      <div style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">${nome} — faltam ${formatBRL(restante)}</div>
      <div class="perfil-campo" style="margin-bottom:16px;">
        <div class="perfil-campo-label">Valor a adicionar (R$)</div>
        <div style="padding:12px 16px;"><input id="mp-valor" type="number" placeholder="0,00" style="width:100%;border:none;background:transparent;font-size:16px;font-family:'Poppins',sans-serif;color:var(--text-dark);outline:none;"/></div>
      </div>
      <div id="mp-error" style="color:var(--red);font-size:12px;margin-bottom:8px;"></div>
      <button id="mp-btn" onclick="confirmarProgressoMeta('${goalId}')" class="confirmar-btn" style="background:var(--blue-primary);color:#fff;">Confirmar</button>
      <button onclick="document.getElementById('modal-progresso-meta').remove()" style="width:100%;background:none;border:none;margin-top:10px;font-size:13px;color:var(--text-muted);font-family:'Poppins',sans-serif;cursor:pointer;">Cancelar</button>
    </div>`;
  document.body.appendChild(modal);
}

async function confirmarProgressoMeta(goalId) {
  const valor = parseFloat(document.getElementById('mp-valor')?.value || '0');
  const errEl = document.getElementById('mp-error');
  const btn   = document.getElementById('mp-btn');

  if (valor <= 0) {
    if (errEl) errEl.textContent = 'Informe um valor maior que zero.';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Salvando...';

  try {
    await api.updateGoalProgress(auth.getUserId(), goalId, { amount_to_add: valor });
    document.getElementById('modal-progresso-meta')?.remove();
    await loadMetas();
  } catch (err) {
    if (errEl) errEl.textContent = err.message || 'Erro ao atualizar.';
    btn.disabled = false;
    btn.textContent = 'Confirmar';
  }
}

window.loadMetas               = loadMetas;
window.abrirModalNovaMeta      = abrirModalNovaMeta;
window.confirmarNovaMeta       = confirmarNovaMeta;
window.abrirModalProgressoMeta = abrirModalProgressoMeta;
window.confirmarProgressoMeta  = confirmarProgressoMeta;
