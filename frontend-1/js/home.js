/**
 * home.js — Tela principal: Safe-to-Spend, Agenda, Categorias
 *
 * Campos exatos do backend (espelhando DashboardPage.tsx do frontend-react):
 *   forecast.safe_to_spend.safe_to_spend_total   → saldo disponível
 *   forecast.safe_to_spend.safe_to_spend_daily   → margem diária
 *   forecast.financial_health.total_expenses     → gastos totais do período
 *   forecast.financial_health.top_categories     → labels do donut
 *   forecast.shadow_invoices.invoices[]          → agenda / obrigações
 *     └ invoice.next_due_date | invoice.due_date
 *     └ invoice.description
 *     └ invoice.amount | invoice.estimated_amount
 *   budget.allocations[]                         → breakdown por categoria (budgetQuery)
 *     └ allocation.category, .current_amount, .suggested_amount
 *   transactions[].amount, .date, .description, .category, .account_name
 */

// Cache global (shared entre módulos)
window._forecastData  = null;
window._budgetData    = null;
window._txData        = [];
window._shadowData    = [];

let _safeToSpend   = 0;
let _totalExpenses = 0;
let _homeDonutChart = null;
let _saldoVis = true;

// ─── SVG OLHO ────────────────────────────────────────────────────────────────
const svgEyeOff = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#7A93B0" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`;
const svgEyeOn  = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#7A93B0" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`;

// ─── FORMATAÇÃO ───────────────────────────────────────────────────────────────
function formatBRL(value) {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(Math.abs(Number(value) || 0));
}

// ─── CARREGAR HOME ────────────────────────────────────────────────────────────
async function loadHome() {
  const userId = auth.getUserId();
  if (!userId) return;

  // Atualizar nome/avatar no header
  const firstName = auth.getUserName();
  const nameEl = document.getElementById('header-nome');
  if (nameEl) nameEl.textContent = firstName;
  const avatarEl = document.getElementById('header-avatar');
  if (avatarEl) avatarEl.textContent = firstName.charAt(0).toUpperCase();

  // Skeleton enquanto carrega
  _showSkeleton();

  try {
    // 1. Forecast principal
    const forecast = await api.getForecast(userId);
    window._forecastData = forecast;

    // Extrair campos exatos conforme DashboardPage.tsx
    const safeToSpend    = forecast.safe_to_spend    || {};
    const financialHealth = forecast.financial_health || {};
    const shadowInvoices  = forecast.shadow_invoices?.invoices || [];
    window._shadowData = shadowInvoices;

    _safeToSpend   = Number(safeToSpend.safe_to_spend_total   || safeToSpend.current_balance || 0);
    _totalExpenses = Number(financialHealth.total_expenses || 0);
    const dailySafe = Number(safeToSpend.safe_to_spend_daily || 0);

    // 2. Budget (para breakdown por categoria)
    const totalIncome = Number(financialHealth.total_income || 0);
      // Se não houver renda no forecast, estimar a partir das transações recentes
      let estimatedIncome = totalIncome;
      if (!estimatedIncome || estimatedIncome <= 0) {
        try {
          const txs = await api.getTransactions(userId, 300);
          window._txData = Array.isArray(txs) ? txs : (txs.transactions || txs.items || []);
          // Somar entradas (valores positivos) nos últimos 90 dias e converter para mensal
          const cutoff = Date.now() - 90 * 24 * 3600 * 1000;
          const positives = window._txData.filter(t => (t.amount || 0) > 0 && new Date(t.date || t.transaction_date).getTime() >= cutoff);
          const totalPos = positives.reduce((s, t) => s + Number(t.amount || 0), 0);
          estimatedIncome = Math.round((totalPos / 3) * 100) / 100; // aproximar para mensal
        } catch (_) {
          estimatedIncome = 0;
        }
      }

      if (estimatedIncome > 0) {
        try {
          const budget = await api.getBudget(userId, estimatedIncome);
          window._budgetData = budget;
        } catch (_) { /* budget opcional */ }
      }

    // Renderizar
    renderSaldo(_safeToSpend, _totalExpenses);
    renderPrevisao(forecast.cashflow, dailySafe);
    renderAgenda(shadowInvoices);
    renderGastosChart(financialHealth, window._budgetData);
    // Garantir que txData esteja disponível para sumários/gráficos
    if (!window._txData || !window._txData.length) {
      try {
        const txs2 = await api.getTransactions(userId, 300);
        window._txData = Array.isArray(txs2) ? txs2 : (txs2.transactions || txs2.items || []);
      } catch (_) { window._txData = window._txData || []; }
    }

    // Atualizar sumários derivados (orçamento, maior compra)
    try { window.updateBudgetSummary?.(window._forecastData, window._txData); } catch (e) { /* ignore */ }

  } catch (err) {
    console.error('[Home] Erro ao carregar forecast:', err);
    _showSaldoOffline();
  }
}

// ─── SKELETON ────────────────────────────────────────────────────────────────
function _showSkeleton() {
  const saldoEl = document.getElementById('saldo-valor');
  if (saldoEl) saldoEl.innerHTML = '— <button class="eye-btn" onclick="toggleSaldo()">' + svgEyeOff + '</button>';
  const subEl = document.getElementById('saldo-sub');
  if (subEl) subEl.textContent = 'Carregando...';
}

function _showSaldoOffline() {
  const saldoEl = document.getElementById('saldo-valor');
  if (saldoEl) saldoEl.innerHTML = '— <button class="eye-btn" onclick="toggleSaldo()">' + svgEyeOff + '</button>';
  const subEl = document.getElementById('saldo-sub');
  if (subEl) subEl.textContent = 'Erro ao carregar dados da API';
}

// ─── SALDO ────────────────────────────────────────────────────────────────────
function renderSaldo(safeToSpend, totalExpenses) {
  const saldoEl = document.getElementById('saldo-valor');
  const subEl   = document.getElementById('saldo-sub');
  if (saldoEl) {
    saldoEl.innerHTML = formatBRL(safeToSpend) + ' <button class="eye-btn" onclick="toggleSaldo()">' + svgEyeOff + '</button>';
  }
  if (subEl) {
    subEl.textContent = 'Gastos do período: -' + formatBRL(totalExpenses);
  }
}

function toggleSaldo() {
  _saldoVis = !_saldoVis;
  const saldoEl = document.getElementById('saldo-valor');
  const subEl   = document.getElementById('saldo-sub');
  if (saldoEl) {
    saldoEl.innerHTML = (_saldoVis ? formatBRL(_safeToSpend) + ' ' : '••••••• ') +
      '<button class="eye-btn" onclick="toggleSaldo()">' + (_saldoVis ? svgEyeOff : svgEyeOn) + '</button>';
  }
  if (subEl) {
    subEl.textContent = _saldoVis
      ? 'Gastos do período: -' + formatBRL(_totalExpenses)
      : 'Gastos do período: •••••••';
  }
}

// ─── PREVISÃO ────────────────────────────────────────────────────────────────
function renderPrevisao(cashflow, dailySafe) {
  const el = document.querySelector('#screen-home .previsao-text');
  if (!el) return;
  const riskLevel = (cashflow || {}).risk_level || 'LOW';
  if (riskLevel === 'CRITICAL') {
    el.innerHTML = `⚠️ <strong>Atenção:</strong> previsão de saldo negativo nos próximos dias. Reduza gastos agora.`;
  } else if (riskLevel === 'HIGH') {
    el.innerHTML = `Seu ritmo está elevado. Margem segura: <strong>${formatBRL(dailySafe)}/dia</strong>.`;
  } else {
    el.innerHTML = `Tudo sob controle! Margem segura de <strong>${formatBRL(dailySafe)}/dia</strong> nos próximos 30 dias.`;
  }
}

// ─── AGENDA ──────────────────────────────────────────────────────────────────
// Espelha lógica de agendaItems em DashboardPage.tsx:
//   invoice.next_due_date | invoice.due_date
//   invoice.description
//   invoice.amount | invoice.estimated_amount
function renderAgenda(invoices) {
  if (!invoices || invoices.length === 0) return;

  const hoje = new Date();
  const agendaItems = invoices
    .map(inv => {
      const dueDate = String(inv.next_due_date || inv.due_date || '');
      if (!dueDate) return null;
      const due  = new Date(dueDate);
      const dueOnly = new Date(due.getFullYear(), due.getMonth(), due.getDate());
      const nowOnly = new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate());
      const daysUntil = Math.floor((dueOnly - nowOnly) / 86400000);
      return {
        description: inv.description || inv.service_name || 'Compromisso',
        amount: Math.abs(Number(inv.amount || inv.estimated_amount || 0)),
        daysUntil,
      };
    })
    .filter(Boolean)
    .sort((a, b) => a.daysUntil - b.daysUntil)
    .slice(0, 3);

  // Atualizar os 3 itens de agenda do HTML original
  const agendaEls = document.querySelectorAll('#screen-home .agenda-item span:last-child');
  agendaItems.forEach((item, i) => {
    const dias = item.daysUntil;
    const diasText = dias <= 0 ? 'hoje' : dias === 1 ? 'amanhã' : `em ${dias} dias`;
    const target = agendaEls[i];
    if (target) {
      target.textContent = `${item.description} — ${formatBRL(item.amount)} (${diasText}).`;
    }
  });

  // Se não há elementos individuais, tentar container genérico
  if (!agendaEls.length) {
    const container = document.querySelector('#screen-home .agenda-item')?.parentElement;
    if (!container) return;
    container.innerHTML = agendaItems.map(item => {
      const dias = item.daysUntil;
      const diasText = dias <= 0 ? 'hoje' : dias === 1 ? 'amanhã' : `em ${dias} dias`;
      return `<div class="agenda-item">
        <span class="dot dot-blue"></span>
        <span>${item.description} — ${formatBRL(item.amount)} (${diasText}).</span>
      </div>`;
    }).join('');
  }
}

// ─── DONUT GASTOS ─────────────────────────────────────────────────────────────
// Usa budget.allocations[] (DashboardPage linha 176-191) ou financial_health.top_categories
const CAT_COLORS = {
  'Alimentação': '#0060C0', 'Transporte': '#0078F0', 'Moradia': '#64AAFA',
  'Lazer': '#85C0FF', 'Saúde': '#3CB37A', 'Assinaturas': '#9B5DE5',
  'Educação': '#F5A623', 'Outros': '#A0C4E8',
};
const FALLBACK_COLORS = ['#0060C0','#0078F0','#64AAFA','#85C0FF','#A0C4E8','#9B5DE5','#3CB37A','#F5A623'];

function renderGastosChart(financialHealth, budgetData) {
  let labels = [];
  let data   = [];

  // Prioridade 1: budget.allocations (mais preciso)
  if (budgetData?.allocations?.length) {
    const allocs = budgetData.allocations
      .map(a => ({
        category: a.category || 'Outros',
        spent: Number(a.current_amount || 0),
      }))
      .filter(a => a.spent > 0)
      .sort((a, b) => b.spent - a.spent)
      .slice(0, 6);

    const totalSpent = allocs.reduce((s, a) => s + a.spent, 0) || 1;
    labels = allocs.map(a => a.category);
    data   = allocs.map(a => Math.round((a.spent / totalSpent) * 100));
  }
  // Prioridade 2: top_categories do financial_health
  else if (financialHealth.top_categories?.length) {
    // top_categories pode ser ['Alimentação','Transporte'] ou [{category:'Alimentação',amount:123}]
    const raw = financialHealth.top_categories.slice(0, 6);
    if (raw.length && typeof raw[0] === 'object') {
      const items = raw.map(r => ({ category: r.category || r.name || 'Outros', amount: Number(r.amount || r.value || 0) }));
      const total = items.reduce((s, it) => s + (it.amount || 0), 0) || 1;
      labels = items.map(i => i.category);
      data = items.map(i => Math.round((i.amount / total) * 100));
      if (data.length) data[data.length - 1] += 100 - data.reduce((a, b) => a + b, 0);
    } else {
      const cats = raw;
      const n    = cats.length;
      labels = cats;
      data   = cats.map(() => Math.round(100 / n));
      if (data.length) data[data.length - 1] += 100 - data.reduce((a, b) => a + b, 0);
    }
  }
  // Fallback
  else {
    labels = ['Outros'];
    data   = [100];
  }

  const bgColors = labels.map((l, i) => CAT_COLORS[l] || FALLBACK_COLORS[i % FALLBACK_COLORS.length]);

  // Atualizar legenda HTML
  const legendItems = document.querySelectorAll('#screen-home .gastos-legend-item');
  labels.slice(0, legendItems.length).forEach((label, i) => {
    const dot = legendItems[i]?.querySelector('.gastos-legend-dot');
    const lbl = legendItems[i]?.querySelector('.gastos-legend-label');
    const pct = legendItems[i]?.querySelector('.gastos-legend-pct');
    if (dot) dot.style.background = bgColors[i];
    if (lbl) lbl.textContent = label;
    if (pct) pct.textContent = (data[i] || 0) + '%';
  });

  // Renderizar donut
  const canvas = document.getElementById('chart-home');
  if (!canvas) return;
  if (_homeDonutChart) _homeDonutChart.destroy();

  _homeDonutChart = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: bgColors,
        borderWidth: 3,
        borderColor: '#F0F8F8',
        hoverOffset: 4,
      }],
    },
    options: {
      cutout: '58%',
      rotation: -105,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: c => ` ${c.label}: ${c.raw}%` },
          backgroundColor: 'rgba(26,26,46,0.85)',
          padding: 8, cornerRadius: 8,
        },
      },
      animation: { animateRotate: true, duration: 800, easing: 'easeOutQuart' },
    },
  });
}

// ─── TOGGLE CARTÃO ────────────────────────────────────────────────────────────
// (mantido para compatibilidade com HTML original)
let _cartaoVis = true;
function toggleCartao() {
  _cartaoVis = !_cartaoVis;
  const el = document.getElementById('cartao-val-display');
  if (el) {
    const svg = _cartaoVis
      ? '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/>'
      : '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>';
    el.innerHTML = (_cartaoVis ? formatBRL(_safeToSpend) + ' ' : '••••••• ') +
      `<button class="eye-btn" onclick="toggleCartao()"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#1A1A2E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${svg}</svg></button>`;
  }
}

// ─── EXPORTS ──────────────────────────────────────────────────────────────────
window.loadHome    = loadHome;
window.toggleSaldo = toggleSaldo;
window.toggleCartao = toggleCartao;
window.formatBRL   = formatBRL;
window.svgEyeOff   = svgEyeOff;
window.svgEyeOn    = svgEyeOn;
