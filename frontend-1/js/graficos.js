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

  // Usar monthly_forecasts se disponível
  const forecasts = window._forecastData?.monthly_forecasts || [];
  const meses     = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];

  let labels = [];
  let data   = [];

  if (forecasts.length > 0) {
    labels = forecasts.map(f => `${meses[f.month - 1]}/${String(f.year).slice(2)}`);
    data   = forecasts.map(f => f.expected_expenses);
  } else {
    // Fallback: agrupar txData por mês
    const byMonth = {};
    (window._txData || []).forEach(tx => {
      const d = new Date(tx.date || tx.transaction_date);
      if (!isNaN(d) && (tx.amount || 0) < 0) {
        const key = `${meses[d.getMonth()]}/${String(d.getFullYear()).slice(2)}`;
        byMonth[key] = (byMonth[key] || 0) + Math.abs(tx.amount);
      }
    });
    const entries = Object.entries(byMonth).slice(-6);
    labels = entries.map(([k]) => k);
    data   = entries.map(([_, v]) => v);
  }

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
