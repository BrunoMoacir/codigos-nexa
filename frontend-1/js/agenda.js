/**
 * agenda.js — Calendário financeiro com eventos das Shadow Invoices reais
 *
 * Consome: window._shadowData (carregado por home.js via loadHome)
 *          ou GET /shadow-invoices/{user_id} diretamente
 */

let selDay   = new Date().getDate();
let curMonth = new Date().getMonth();
let curYear  = new Date().getFullYear();

// { 'YYYY-M-D': ['desc1', 'desc2'] }
let _calEvents = {};

async function loadAgenda() {
  const userId = auth.getUserId();
  if (!userId) return;

  // Usar cache se já tiver
  let shadows = window._shadowData;
  if (!shadows || shadows.length === 0) {
    try {
      const data = await api.getShadowInvoices(userId);
      shadows = data?.invoices || data?.shadow_invoices || data || [];
      window._shadowData = shadows;
    } catch (err) {
      console.error('[Agenda] Erro ao buscar shadow invoices:', err);
      shadows = [];
    }
  }

  // Mapear shadow invoices → eventos do calendário
  _calEvents = {};
  shadows.forEach(s => {
    if (!s.next_due_date) return;
    const d   = new Date(s.next_due_date);
    const key = `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
    if (!_calEvents[key]) _calEvents[key] = [];
    const valor = s.estimated_amount ? ` — ${formatBRL(s.estimated_amount)}` : '';
    _calEvents[key].push(`${s.service_name || s.description}${valor}`);
  });

  // Inicializar calendário
  buildCalendar(curMonth, curYear);
  showEvents(selDay, curMonth, curYear);
}

function buildCalendar(month, year) {
  const grid = document.getElementById('cal-grid');
  if (!grid) return;

  // Atualizar selects
  const monthSel = document.getElementById('cal-month');
  const yearSel  = document.getElementById('cal-year');
  if (monthSel) monthSel.value = month;
  if (yearSel)  yearSel.value  = year;

  grid.innerHTML = '';
  ['Dom','Seg','Ter','Qua','Qui','Sex','Sáb'].forEach(h => {
    const el = document.createElement('div');
    el.className = 'cal-head';
    el.textContent = h;
    grid.appendChild(el);
  });

  const firstDay     = new Date(year, month, 1).getDay();
  const daysInMonth  = new Date(year, month + 1, 0).getDate();
  const prevDays     = new Date(year, month, 0).getDate();
  const today        = new Date();

  for (let i = firstDay - 1; i >= 0; i--) {
    const el = document.createElement('div');
    el.className   = 'cal-day other';
    el.textContent = prevDays - i;
    grid.appendChild(el);
  }

  for (let day = 1; day <= daysInMonth; day++) {
    const el   = document.createElement('div');
    el.className = 'cal-day';

    // Marcar se tem evento
    const key = `${year}-${month + 1}-${day}`;
    if (_calEvents[key]) el.classList.add('has-event');

    // Marcar hoje
    if (day === today.getDate() && month === today.getMonth() && year === today.getFullYear()) {
      el.classList.add('today');
    }

    // Marcar selecionado
    if (day === selDay && month === curMonth && year === curYear) {
      el.classList.add('selected');
    }

    el.textContent = day;
    el.onclick = () => {
      selDay = day;
      showEvents(day, month, year);
      buildCalendar(month, year);
    };
    grid.appendChild(el);
  }

  // Dias do próximo mês para preencher
  const rem = (7 - ((firstDay + daysInMonth) % 7)) % 7;
  for (let i = 1; i <= rem; i++) {
    const el = document.createElement('div');
    el.className   = 'cal-day other';
    el.textContent = i;
    grid.appendChild(el);
  }
}

function showEvents(day, month, year) {
  const months = ['janeiro','fevereiro','março','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro'];
  const dateEl  = document.getElementById('event-date');
  const listEl  = document.getElementById('event-list');
  if (dateEl) dateEl.textContent = `${day} de ${months[month]} de ${year}`;

  const key  = `${year}-${month + 1}-${day}`;
  const evts = _calEvents[key] || ['Nenhum evento para este dia.'];
  if (listEl) listEl.innerHTML = evts.map(e => `<li>${e}</li>`).join('');
}

function changeMonth(delta) {
  curMonth += delta;
  if (curMonth > 11) { curMonth = 0; curYear++; }
  if (curMonth < 0)  { curMonth = 11; curYear--; }
  buildCalendar(curMonth, curYear);
}

function updateCal() {
  curMonth = parseInt(document.getElementById('cal-month')?.value || '0');
  curYear  = parseInt(document.getElementById('cal-year')?.value  || String(new Date().getFullYear()));
  buildCalendar(curMonth, curYear);
}

window.loadAgenda    = loadAgenda;
window.buildCalendar = buildCalendar;
window.showEvents    = showEvents;
window.changeMonth   = changeMonth;
window.updateCal     = updateCal;
