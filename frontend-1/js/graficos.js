/**
 * graficos.js — Gráficos com dados reais do forecast
 *
 * Consome: window._forecastData (já carregado por home.js)
 *          window._txData (já carregado por transacoes.js)
 */

let _graficosInited = false;
let _graficoRitmo   = null;
let _graficoDinheiro = null;
let _graficoDiarios  = null;
let _graficoDetalhes = null;
let _graficoComparativo = null;

function initGraficos() {
  if (_graficosInited) return;

  const forecast = window._forecastData;
  const txData   = window._txData || [];

  renderGraficoRitmo(forecast, txData);
  renderGraficoDinheiro(forecast);
  renderGraficoDiarios(txData);

  // Atualizar sumários derivados (orçamento, maior compra)
  try {
    updateBudgetSummary(forecast, txData);
  } catch (e) { /* non-fatal */ }

  _graficosInited = true;
}

// ─── 1. Ritmo de Gastos (barras por dia do mês) ───────────────────────────────
function renderGraficoRitmo(forecast, txData) {
  const canvas = document.getElementById('chart-ritmo');
  if (!canvas) return;

  // Calcular gasto por dia do mês a partir de txData
  const hoje  = new Date();
  const ano   = hoje.getFullYear();
  const mes   = hoje.getMonth();
  const daysInMonth = new Date(ano, mes + 1, 0).getDate();

  const gastoPorDia = Array(daysInMonth).fill(0);
  txData.forEach(tx => {
    const d = new Date(tx.date || tx.transaction_date);
    if (d.getFullYear() === ano && d.getMonth() === mes && (tx.amount || 0) < 0) {
      gastoPorDia[d.getDate() - 1] += Math.abs(tx.amount);
    }
  });

  const labels = gastoPorDia.map((_, i) => String(i + 1));
  const ideal  = forecast?.safe_to_spend?.safe_to_spend_daily || 0;
  const cores  = gastoPorDia.map(v => v > ideal && ideal > 0 ? '#0050B4' : '#0078F0');

  if (_graficoRitmo) _graficoRitmo.destroy();
  _graficoRitmo = new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Ideal',
          data: Array(daysInMonth).fill(ideal),
          backgroundColor: '#BDD9F7',
          borderRadius: { topLeft:6, topRight:6, bottomLeft:4, bottomRight:4 },
          borderSkipped: false,
          barPercentage: 0.55,
          categoryPercentage: 0.82,
          order: 2,
        },
        {
          label: 'Gasto',
          data: gastoPorDia,
          backgroundColor: cores,
          borderRadius: { topLeft:6, topRight:6, bottomLeft:4, bottomRight:4 },
          borderSkipped: false,
          barPercentage: 0.55,
          categoryPercentage: 0.82,
          order: 1,
        }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          mode: 'index', intersect: false,
          callbacks: {
            title: items => `Dia ${items[0].label}`,
            label: ctx => ctx.dataset.label === 'Ideal'
              ? ` Ideal: ${formatBRL(ctx.raw)}/dia`
              : ` Gasto: ${formatBRL(ctx.raw)}`,
          },
          backgroundColor: 'rgba(15,25,50,0.88)', padding: 10, cornerRadius: 10,
          titleFont: { family: 'Poppins', size: 11, weight: '700' },
          bodyFont:  { family: 'Poppins', size: 11 }, bodySpacing: 4,
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { display: false }, border: { display: false } },
        y: { display: false, min: 0 },
      },
      animation: { duration: 800, easing: 'easeOutQuart' },
      layout: { padding: { top: 6, bottom: 0, left: 2, right: 2 } },
    },
    plugins: [{
      id: 'refLine',
      afterDraw(chart) {
        if (ideal <= 0) return;
        const { ctx, scales: { y }, chartArea: { left, right } } = chart;
        const yPos = y.getPixelForValue(ideal);
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(left, yPos);
        ctx.lineTo(right, yPos);
        ctx.strokeStyle = 'rgba(100,140,180,0.5)';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 4]);
        ctx.stroke();
        ctx.restore();
      }
    }]
  });

  // Texto abaixo do gráfico
  const textEl = canvas.closest('.card')?.querySelector('p, .previsao-text');
  if (textEl && ideal > 0) {
    const gastoMedio = gastoPorDia.filter(v => v > 0).reduce((a, b) => a + b, 0) /
      Math.max(1, gastoPorDia.filter(v => v > 0).length);
    const diff = gastoMedio - ideal;
    if (diff > 0) {
      textEl.innerHTML = `Você está gastando, por dia, <strong>${formatBRL(diff)} acima do ideal</strong> para fechar o mês tranquilamente.`;
    } else {
      textEl.innerHTML = `Parabéns! Você está <strong>${formatBRL(Math.abs(diff))} abaixo do ideal</strong> por dia. Ótimo ritmo!`;
    }
  }
}

// ─── 2. Para onde seu dinheiro foi (donut por categoria) ──────────────────────
function renderGraficoDinheiro(forecast) {
  const canvas = document.getElementById('chart-dinheiro');
  if (!canvas) return;

  const health   = forecast?.financial_health || {};
  const cats     = health.top_categories || ['Outros'];
  const count    = cats.length;
  const data     = cats.map(() => Math.round(100 / count));
  if (data.length) data[data.length - 1] += 100 - data.reduce((a, b) => a + b, 0);

  const COLORS = ['#1252A3','#2D7DD2','#4A90D9','#6CB0F0','#A8D4F5','var(--blue-light)'];
  const bgColors = cats.map((_, i) => COLORS[i % COLORS.length]);

  if (_graficoDinheiro) _graficoDinheiro.destroy();
  _graficoDinheiro = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: cats,
      datasets: [{
        data,
        backgroundColor: bgColors,
        borderWidth: 0, hoverOffset: 3,
      }]
    },
    options: {
      cutout: '60%',
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => ` ${c.label}: ${c.raw}%` } }
      },
      animation: { duration: 500 }
    }
  });

  // Atualizar legenda de barras abaixo do donut
  const barsEl = canvas.closest('.card')?.querySelector('.graficos-bar-item');
  if (!barsEl) return;
  const parent = barsEl.parentElement;
  if (!parent) return;
  parent.innerHTML = cats.slice(0, 5).map((cat, i) => `
    <div class="graficos-bar-item">
      <div class="graficos-bar-top"><span>${cat}</span><span>${data[i]}%</span></div>
      <div class="bar-track"><div class="bar-fill" style="width:${data[i]}%;background:${bgColors[i]};"></div></div>
    </div>`).join('');
}

// ─── 3. Gastos por hora do dia (barras horárias) ─────────────────────────────
function renderGraficoDiarios(txData) {
  const canvas = document.getElementById('chart-diarios');
  if (!canvas) return;

  const horasData = Array(24).fill(0);
  txData.forEach(tx => {
    const d = new Date(tx.date || tx.transaction_date);
    if (!isNaN(d) && (tx.amount || 0) < 0) {
      horasData[d.getHours()] += Math.abs(tx.amount);
    }
  });

  const labels = Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2,'0')}h`);
  const max    = Math.max(...horasData, 1);

  if (_graficoDiarios) _graficoDiarios.destroy();
  _graficoDiarios = new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: horasData,
        backgroundColor: horasData.map(v => {
          const pct = v / max;
          return pct > 0.7 ? '#1252A3' : pct > 0.3 ? '#4A90D9' : 'var(--blue-light)';
        }),
        borderRadius: 3, borderSkipped: false, barPercentage: 0.7,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { enabled: true } },
      scales: {
        x: {
          grid: { display: false },
          ticks: { font: { family: 'Poppins', size: 9 }, color: '#7A93B0', maxRotation: 90, minRotation: 90 },
          border: { color: '#D4E4F5' }
        },
        y: { display: false }
      }
    }
  });
}

// ─── 4. Comparativo mensal ────────────────────────────────────────────────────
let _comparativoInited = false;
function initComparativo() {
  if (_comparativoInited) return;
  _comparativoInited = true;

  const canvas = document.getElementById('chart-comparativo');
  if (!canvas) return;

  const meses = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];

  // Construir uma lista de months a partir de monthly_forecasts ou txData
  let monthSeries = [];
  const forecasts = window._forecastData?.monthly_forecasts;
  if (Array.isArray(forecasts) && forecasts.length) {
    monthSeries = forecasts.map(f => ({
      label: `${meses[f.month - 1]}/${String(f.year).slice(2)}`,
      value: Number(f.expected_expenses || 0),
      year: f.year, month: f.month,
    }));
  } else {
    // Agrupar txData por ano-mês (últimos 6 meses)
    const by = {};
    (window._txData || []).forEach(tx => {
      const d = new Date(tx.date || tx.transaction_date);
      if (isNaN(d)) return;
      const key = `${d.getFullYear()}-${d.getMonth()}`;
      by[key] = (by[key] || 0) + (tx.amount < 0 ? Math.abs(Number(tx.amount || 0)) : 0);
    });
    const entries = Object.entries(by).sort((a,b) => a[0].localeCompare(b[0]));
    const last = entries.slice(-6);
    monthSeries = last.map(([k,v]) => {
      const [y, m] = k.split('-').map(Number);
      return { label: `${meses[m]}/${String(y).slice(2)}`, value: v, year: y, month: m+1 };
    });
  }

  // Render selector de meses
  try {
    const selWrap = document.querySelector('#screen-comparativo .content > div');
    if (selWrap) {
      selWrap.innerHTML = monthSeries.map((m, i) => `<button class="filtro-chip${i===0? ' active':''}" data-idx="${i}">${m.label}</button>`).join('');
      selWrap.querySelectorAll('.filtro-chip').forEach(btn => btn.addEventListener('click', (ev) => {
        selWrap.querySelectorAll('.filtro-chip').forEach(b=>b.classList.remove('active'));
        btn.classList.add('active');
        const idx = Number(btn.getAttribute('data-idx'));
        selectComparativoMonth(idx);
      }));
    }
  } catch (e) { /* non-fatal */ }

  const labels = monthSeries.map(m => m.label);
  const data = monthSeries.map(m => m.value);

  const bgColors = data.map((_, i) => i === data.length - 1 ? '#2D7DD2' : '#BDD9F7');

  if (_graficoComparativo) _graficoComparativo.destroy();
  _graficoComparativo = new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: bgColors,
        borderRadius: { topLeft: 6, topRight: 6 },
        borderSkipped: false,
        barPercentage: 0.6,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => ` ${formatBRL(c.raw)}` }, backgroundColor: 'rgba(15,25,50,0.88)', padding: 8, cornerRadius: 8 }
      },
      scales: {
        x: { grid: { display: false }, ticks: { font: { family: 'Poppins', size: 10 }, color: '#7A93B0' }, border: { display: false } },
        y: { display: false }
      },
      animation: { duration: 600, easing: 'easeOutQuart' }
    }
  });
  // Inicializar seleção do mês (atualiza os cards resumo)
  function selectComparativoMonth(idx) {
    const cur = monthSeries[idx] || { label:'-', value:0 };
    const prev = monthSeries[idx+1] || { label:'-', value:0 };
    // Atualizar cards que existem no HTML
    const cards = document.querySelectorAll('#screen-comparativo .content > .card');
    if (cards && cards.length >= 2) {
      const curCard = cards[0];
      const prevCard = cards[1];
      const curLabelEl = curCard.querySelector('div');
      const curValEl = curCard.querySelector('div + div');
      const curDeltaEl = curCard.querySelector('div + div + div');
      if (curLabelEl) curLabelEl.textContent = cur.label;
      if (curValEl) curValEl.textContent = formatBRL(cur.value);
      const diff = cur.value - prev.value;
      const pct = prev.value ? Math.round((diff / prev.value) * 100) : 0;
      if (curDeltaEl) {
        curDeltaEl.textContent = `${diff >= 0 ? '▲' : '▼'} ${Math.abs(pct)}% vs anterior`;
        curDeltaEl.style.color = diff >= 0 ? 'var(--red)' : 'var(--green)';
      }
      if (prevCard) {
        const prevLabelEl = prevCard.querySelector('div');
        const prevValEl = prevCard.querySelector('div + div');
        if (prevLabelEl) prevLabelEl.textContent = prev.label;
        if (prevValEl) prevValEl.textContent = formatBRL(prev.value);
      }
    }
  }

  try { selectComparativoMonth(0); } catch (e) { /* ignore */ }
}

// ─── 5. Donut detalhes da categoria ──────────────────────────────────────────
let _detalhesInited = false;
function initDetalhes() {
  if (_detalhesInited) return;
  _detalhesInited = true;

  const ctx = document.getElementById('chart-detalhes-donut');
  if (!ctx) return;

  // Calcular por subcategoria das transações
  const byCat = {};
  (window._txData || []).forEach(tx => {
    if ((tx.amount || 0) < 0) {
      const cat = tx.category || 'Outros';
      byCat[cat] = (byCat[cat] || 0) + Math.abs(tx.amount);
    }
  });

  const sorted = Object.entries(byCat).sort((a, b) => b[1] - a[1]).slice(0, 6);
  const total  = sorted.reduce((s, [_, v]) => s + v, 0) || 1;
  const labels = sorted.map(([k]) => k);
  const data   = sorted.map(([_, v]) => Math.round((v / total) * 100));
  const colors = ['#1252A3','#2D7DD2','#4A90D9','#6CB0F0','#A8D4F5','var(--blue-light)'];

  if (_graficoDetalhes) _graficoDetalhes.destroy();
  _graficoDetalhes = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{ data, backgroundColor: colors, borderWidth: 0, hoverOffset: 4 }]
    },
    options: {
      cutout: '60%',
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ` ${c.label}: ${c.raw}%` } } },
      animation: { duration: 500 }
    }
  });
}

window.initGraficos   = initGraficos;
window.initComparativo = initComparativo;
window.initDetalhes   = initDetalhes;

// Atualiza sumários visuais: orçamento (total, gasto, diário) e maior compra
function updateBudgetSummary(forecast, txData) {
  const fmt = window.formatBRL || (v => String(v));
  const budgetElTotal = document.getElementById('budget-total');
  const budgetElSpent = document.getElementById('budget-spent');
  const budgetElDaily = document.getElementById('budget-daily');
  const maiorEl = document.getElementById('maior-compra');

  // Determinar total do orçamento: prefer allocations.suggested_amount, fallback para income
  let totalBudget = 0;
  const b = window._budgetData;
  if (b && Array.isArray(b.allocations) && b.allocations.length) {
    totalBudget = b.allocations.reduce((s, a) => s + Number(a.suggested_amount || a.current_amount || 0), 0);
  } else if (forecast?.financial_health?.total_income) {
    totalBudget = Number(forecast.financial_health.total_income || 0);
  }

  // Gasto atual: prefer financial_health.total_expenses, fallback sum of txData
  let spent = Number(forecast?.financial_health?.total_expenses || 0);
  if (!spent && Array.isArray(txData) && txData.length) {
    spent = txData.reduce((s, t) => s + (t.amount < 0 ? Math.abs(Number(t.amount || 0)) : 0), 0);
  }

  // Daily safe: de safe_to_spend.daily ou cálculo simples
  let daily = Number(forecast?.safe_to_spend?.safe_to_spend_daily || 0);
  if (!daily && totalBudget > 0) {
    const remaining = Math.max(0, totalBudget - spent);
    daily = Math.round((remaining / 30) * 100) / 100;
  }

  if (budgetElTotal) budgetElTotal.textContent = totalBudget > 0 ? fmt(totalBudget) : '—';
  if (budgetElSpent) budgetElSpent.textContent = spent > 0 ? fmt(spent) : '—';
  if (budgetElDaily) budgetElDaily.textContent = daily > 0 ? `Margem segura: ${fmt(daily)}/dia` : 'Sem dados suficientes para calcular margem diária.';

  // Maior compra: encontrar maior transação negativa
  try {
    const txs = Array.isArray(txData) ? txData : (window._txData || []);
    const negatives = txs.filter(t => Number(t.amount) < 0).map(t => ({ amt: Math.abs(Number(t.amount || 0)), d: t }));
    if (negatives.length) {
      negatives.sort((a, b) => b.amt - a.amt);
      const top = negatives[0];
      if (maiorEl) maiorEl.textContent = `${fmt(top.amt)} — ${top.d.description || top.d.merchant_name || top.d.category || ''}`;
    } else {
      if (maiorEl) maiorEl.textContent = '—';
    }
  } catch (e) {
    if (maiorEl) maiorEl.textContent = '—';
  }
}

window.updateBudgetSummary = updateBudgetSummary;
