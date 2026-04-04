/**
 * transacoes.js — Lista de transações reais da API
 *
 * Campos exatos do backend (espelhando DashboardPage.tsx):
 *   txQuery.data?.transactions[]
 *     .amount          (negativo = débito, positivo = crédito)
 *     .date            (string ISO: "2026-03-15" ou "2026-03-15T14:30:00")
 *     .description     (nome do estabelecimento)
 *     .category        (string: "Alimentação", "Transporte"...)
 *     .account_name    (nome do cartão/conta)
 */

// ─── CATÉGORIA → ícone emoji ──────────────────────────────────────────────────
const TX_ICONS = {
  'alimentação':    { emoji: '🍔', bg: '#FFF3E0' },
  'transporte':     { emoji: '🚕', bg: '#E3F2FD' },
  'moradia':        { emoji: '🏠', bg: '#E8F5E9' },
  'lazer':          { emoji: '🎬', bg: '#F3E5F5' },
  'saúde':          { emoji: '💊', bg: '#FCE4EC' },
  'assinaturas':    { emoji: '📺', bg: '#EDE7F6' },
  'educação':       { emoji: '📚', bg: '#E8EAF6' },
  'compras':        { emoji: '🛍️', bg: '#FFF8E1' },
  'viagem':         { emoji: '✈️', bg: '#E0F7FA' },
  'restaurante':    { emoji: '🍽️', bg: '#FFF3E0' },
  'supermercado':   { emoji: '🛒', bg: '#E8F5E9' },
  'farmácia':       { emoji: '💊', bg: '#FCE4EC' },
  'combustível':    { emoji: '⛽', bg: '#E3F2FD' },
  'beleza':         { emoji: '💅', bg: '#FCE4EC' },
  'outros':         { emoji: '💳', bg: 'var(--blue-lighter)' },
};

function getTxIcon(category) {
  const key = (category || 'outros').toLowerCase();
  for (const [k, v] of Object.entries(TX_ICONS)) {
    if (key.includes(k)) return v;
  }
  return TX_ICONS['outros'];
}

// ─── ESTADO LOCAL ─────────────────────────────────────────────────────────────
let _filtroAtivo = 'todas';
let _cardsData   = {};   // { 'nome do cartão': [tx, tx, ...] }
let _faturasData = {};   // { 'YYYY-MM': total }

// ─── CARREGAR TRANSAÇÕES ──────────────────────────────────────────────────────
async function loadTransacoes() {
  const userId = auth.getUserId();
  if (!userId) return;

  try {
    // GET /transactions/{user_id}?limit=300&offset=0
    const data = await api.getTransactions(userId, 300, 0);

    // O backend retorna { transactions: [...] } ou array direto
    const txs = Array.isArray(data)
      ? data
      : (data.transactions || data.items || data.data || []);

    window._txData = txs;

    // Indexar por cartão para carrossel
    _buildCardsIndex(txs);

    // Renderizar lista principal
    renderTransacoes(txs);

    // Inicializar carrossel de cartões
    renderCartoes(_cardsData);

  } catch (err) {
    console.error('[Transações] Erro:', err);
  }
}

// ─── INDEXAR POR CARTÃO ───────────────────────────────────────────────────────
function _buildCardsIndex(txs) {
  _cardsData = {};
  txs.forEach(tx => {
    const account = tx.account_name || tx.account || tx.card || 'Conta principal';
    if (!_cardsData[account]) _cardsData[account] = [];
    _cardsData[account].push(tx);
  });
}

// ─── RENDERIZAR LISTA ─────────────────────────────────────────────────────────
function renderTransacoes(txs) {
  const container = document.getElementById('lista-transacoes');
  if (!container) return;

  const filtradas = _filtroAtivo === 'todas'
    ? txs
    : txs.filter(tx => {
        const cat = (tx.category || '').toLowerCase();
        return cat.includes(_filtroAtivo.replace('ã', 'a').replace('ç', 'c'));
      });

  if (!filtradas.length) {
    container.innerHTML = '<div style="padding:24px;text-align:center;font-size:13px;color:var(--text-muted);">Nenhuma transação encontrada.</div>';
    _updateTotalLabel(0);
    return;
  }

  // Agrupar por dia
  const groups = {};
  filtradas.forEach(tx => {
    const d = new Date(tx.date || tx.transaction_date);
    const key = isNaN(d) ? 'Sem data' : d.toLocaleDateString('pt-BR', { weekday:'short', day:'numeric', month:'short' });
    if (!groups[key]) groups[key] = [];
    groups[key].push(tx);
  });

  const totalGastos = filtradas
    .filter(tx => Number(tx.amount) < 0)
    .reduce((s, tx) => s + Math.abs(Number(tx.amount)), 0);
  _updateTotalLabel(totalGastos);

  container.innerHTML = Object.entries(groups).map(([dia, itens]) => `
    <div style="padding:10px 16px 4px;font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.7px;">${dia}</div>
    ${itens.map(tx => {
      const {emoji, bg} = getTxIcon(tx.category);
      const valor  = Number(tx.amount || 0);
      const isDebit = valor < 0;
      const valFormatado = (isDebit ? '-' : '+') + formatBRL(Math.abs(valor));
      const valCor  = isDebit ? 'var(--text-dark)' : 'var(--green)';
      const cat     = tx.category || 'Outros';
      const nome    = tx.description || tx.name || 'Transação';
      const account = tx.account_name || tx.account || '';
      const nomeEnc    = encodeURIComponent(nome);
      const catEnc     = encodeURIComponent(cat);
      const valorEnc   = encodeURIComponent(valFormatado);
      const cartaoEnc  = encodeURIComponent(account);
      const dataEnc    = encodeURIComponent(new Date(tx.date).toLocaleDateString('pt-BR'));
      return `<div class="tx-item" onclick="abrirTxDetalhe('${nomeEnc}','${catEnc}','${valorEnc}','${cartaoEnc}','${dataEnc}','','')"
        style="display:flex;align-items:center;gap:12px;padding:12px 16px;border-bottom:1px solid rgba(200,224,248,0.4);cursor:pointer;transition:background 0.12s;">
        <div style="width:38px;height:38px;border-radius:11px;background:${bg};flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:18px;">${emoji}</div>
        <div style="flex:1;min-width:0;">
          <div style="font-size:13.5px;font-weight:600;color:var(--text-dark);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${nome}</div>
          <div style="font-size:11.5px;color:var(--text-muted);margin-top:1px;">${cat}${account ? ' • ' + account : ''}</div>
        </div>
        <div style="font-size:13.5px;font-weight:700;color:${valCor};white-space:nowrap;">${valFormatado}</div>
      </div>`;
    }).join('')}
  `).join('');
}

function _updateTotalLabel(total) {
  const el = document.getElementById('tx-total-label');
  if (el) el.textContent = formatBRL(total);
}

// ─── FILTROS TRANSAÇÕES ───────────────────────────────────────────────────────
function filtrarTx(btn, filtro) {
  _filtroAtivo = filtro;
  document.querySelectorAll('.filtro-chip').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderTransacoes(window._txData || []);
}

// ─── BUSCA ────────────────────────────────────────────────────────────────────
function buscarTransacoes(query) {
  const q = (query || '').toLowerCase();
  const txs = window._txData || [];
  const filtradas = q
    ? txs.filter(tx =>
        (tx.description || '').toLowerCase().includes(q) ||
        (tx.category    || '').toLowerCase().includes(q) ||
        (tx.account_name|| '').toLowerCase().includes(q)
      )
    : txs;

  const container = document.getElementById('busca-lista');
  if (!container) return;

  if (!filtradas.length) {
    container.innerHTML = `<div style="padding:24px;text-align:center;font-size:13px;color:var(--text-muted);">Nenhum resultado para "${query}".</div>`;
    return;
  }

  container.innerHTML = filtradas.slice(0, 50).map(tx => {
    const {emoji, bg} = getTxIcon(tx.category);
    const valor = Number(tx.amount || 0);
    const isDebit = valor < 0;
    const valFormatado = (isDebit ? '-' : '+') + formatBRL(Math.abs(valor));
    const valCor  = isDebit ? 'var(--text-dark)' : 'var(--green)';
    const nome    = tx.description || 'Transação';
    return `<div style="display:flex;align-items:center;gap:12px;padding:12px 16px;border-bottom:1px solid rgba(200,224,248,0.4);">
      <div style="width:36px;height:36px;border-radius:10px;background:${bg};flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:17px;">${emoji}</div>
      <div style="flex:1;min-width:0;">
        <div style="font-size:13px;font-weight:600;color:var(--text-dark);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${nome}</div>
        <div style="font-size:11px;color:var(--text-muted);">${tx.category || 'Outros'}</div>
      </div>
      <div style="font-size:13px;font-weight:700;color:${valCor};">${valFormatado}</div>
    </div>`;
  }).join('');
}

// ─── HISTÓRICO DE FATURAS ─────────────────────────────────────────────────────
function renderFaturas(cardName) {
  const container = document.getElementById('lista-faturas');
  if (!container) return;

  const txs = _cardsData[cardName] || window._txData || [];
  const meses = {};
  txs.forEach(tx => {
    if (Number(tx.amount) >= 0) return;
    const d = new Date(tx.date || tx.transaction_date);
    if (isNaN(d)) return;
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
    meses[key] = (meses[key] || 0) + Math.abs(Number(tx.amount));
  });

  const mesesNomes = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
  const entries = Object.entries(meses).sort((a, b) => b[0].localeCompare(a[0])).slice(0, 6);

  if (!entries.length) {
    container.innerHTML = '<div style="padding:16px;font-size:13px;color:var(--text-muted);">Sem histórico disponível.</div>';
    return;
  }

  container.innerHTML = entries.map(([key, total]) => {
    const [ano, mes] = key.split('-');
    const nomeMes = mesesNomes[+mes - 1];
    const isOpened = key === entries[0][0];
    return `<div style="display:flex;align-items:center;justify-content:space-between;padding:13px 16px;border-bottom:1px solid rgba(200,224,248,0.3);">
      <div>
        <div style="font-size:13.5px;font-weight:600;color:var(--text-dark);">${nomeMes}/${ano}</div>
        <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">${isOpened ? 'Fatura atual' : 'Pago'}</div>
      </div>
      <div style="font-size:15px;font-weight:700;color:var(--text-dark);">${formatBRL(total)}</div>
    </div>`;
  }).join('');
}

function selecionarCartaoFatura(btn, cardName) {
  document.querySelectorAll('#screen-historico-faturas .filtro-chip').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderFaturas(cardName);
}

// ─── CARROSSEL DE CARTÕES ─────────────────────────────────────────────────────
const CARD_DESIGNS = {
  'nubank':   { grad: 'linear-gradient(145deg,#7A0AA8,#9B1ED6)', logo: 'Nubank' },
  'inter':    { grad: 'linear-gradient(145deg,#F85C04,#FF7A1A)', logo: 'inter' },
  'c6':       { grad: 'linear-gradient(145deg,#242424,#383838)', logo: 'C6' },
  'bradesco': { grad: 'linear-gradient(145deg,#CC0000,#E8001C)', logo: 'Bradesco' },
  'itaú':     { grad: 'linear-gradient(145deg,#EC7000,#FF8C00)', logo: 'itaú' },
  'santander':{ grad: 'linear-gradient(145deg,#EC0000,#FF1A1A)', logo: 'Santander' },
  'bb':       { grad: 'linear-gradient(145deg,#F8D000,#E6BC00)', logo: 'BB', textColor: '#1A1A2E' },
  'caixa':    { grad: 'linear-gradient(145deg,#005CA9,#0074CC)', logo: 'CAIXA' },
  'default':  { grad: 'linear-gradient(145deg,#1252A3,#2D7DD2)', logo: '●' },
};

function getCardDesign(accountName) {
  const n = (accountName || '').toLowerCase();
  for (const [k, v] of Object.entries(CARD_DESIGNS)) {
    if (k !== 'default' && n.includes(k)) return v;
  }
  return CARD_DESIGNS['default'];
}

function renderCartoes(cardsData) {
  const carousel = document.getElementById('cartoes-carousel');
  const dotsEl   = document.querySelector('.cartoes-dots');
  if (!carousel) return;

  const contas = Object.entries(cardsData);
  if (!contas.length) return;

  const slides = contas.map(([account, txs]) => {
    const design = getCardDesign(account);
    const faturaAbertura = txs
      .filter(tx => Number(tx.amount) < 0)
      .reduce((s, tx) => s + Math.abs(Number(tx.amount)), 0);

    // Últimas 2 transações para exibir no rodapé do cartão
    const lastTx = txs.sort((a, b) => new Date(b.date) - new Date(a.date))[0];
    const lastDate = lastTx ? new Date(lastTx.date).toLocaleDateString('pt-BR', {day:'2-digit',month:'2-digit'}) : '';
    const last = lastTx ? lastTx.description?.slice(0, 18) || 'Última transação' : '';

    // Últimas 4 dígitos do account name se tiver número
    const digits = (account.match(/\d+/) || [''])[0].slice(-4);
    const displayName = account.length > 18 ? account.slice(0, 15) + '...' : account;

    return `<div class="cartao-slide">
      <div class="cartao-card" style="background:${design.grad};">
        <div class="cartao-card-top">
          <span class="cartao-card-bank" style="color:${design.textColor || '#fff'};">${design.logo}</span>
          <svg class="cartao-card-chip" width="28" height="22" viewBox="0 0 42 34" fill="none">
            <rect x="1" y="1" width="40" height="32" rx="5" stroke="rgba(255,255,255,0.5)" stroke-width="1.5" fill="rgba(255,255,255,0.12)"/>
            <line x1="14" y1="1" x2="14" y2="33" stroke="rgba(255,255,255,0.3)" stroke-width="1"/>
            <line x1="28" y1="1" x2="28" y2="33" stroke="rgba(255,255,255,0.3)" stroke-width="1"/>
            <line x1="1" y1="12" x2="41" y2="12" stroke="rgba(255,255,255,0.3)" stroke-width="1"/>
            <line x1="1" y1="22" x2="41" y2="22" stroke="rgba(255,255,255,0.3)" stroke-width="1"/>
          </svg>
        </div>
        <div class="cartao-card-num">•••• •••• •••• ${digits || '••••'}</div>
        <div class="cartao-card-footer">
          <div>
            <div class="cartao-card-label">Fatura aberta</div>
            <div class="cartao-card-val">${formatBRL(faturaAbertura)}</div>
          </div>
          <div style="text-align:right;">
            <div class="cartao-card-label">Última: ${lastDate}</div>
            <div class="cartao-card-val" style="font-size:10px;opacity:0.8;">${last}</div>
          </div>
        </div>
      </div>
    </div>`;
  });

  // Adicionar botão "+" de adicionar cartão
  slides.push(`<div class="cartao-slide">
    <div class="cartao-card cartao-add" onclick="goTo('add-cartao')">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
      <span style="font-size:14px;font-weight:700;margin-top:8px;">Adicionar conta</span>
    </div>
  </div>`);

  carousel.innerHTML = slides.join('');

  // Dots
  if (dotsEl) {
    dotsEl.innerHTML = slides.map((_, i) =>
      `<span class="cartao-dot${i === 0 ? ' active' : ''}" onclick="cartaoAtivo(${i})"></span>`
    ).join('');
  }

  // Também atualizar despesas do cartão ativo na tela home
  _updateCartaoDesp(0, contas);
}

function _updateCartaoDesp(index, contas) {
  if (!contas || !contas[index]) return;
  const [, txs] = contas[index];
  const total = txs
    .filter(tx => Number(tx.amount) < 0)
    .reduce((s, tx) => s + Math.abs(Number(tx.amount)), 0);
  const despEl = document.getElementById('cartao-desp-valor');
  if (despEl) despEl.textContent = formatBRL(total);
}

// ─── EXPORTS ──────────────────────────────────────────────────────────────────
window.loadTransacoes       = loadTransacoes;
window.renderTransacoes     = renderTransacoes;
window.filtrarTx            = filtrarTx;
window.buscarTransacoes     = buscarTransacoes;
window.renderFaturas        = renderFaturas;
window.selecionarCartaoFatura = selecionarCartaoFatura;
window.renderCartoes        = renderCartoes;
