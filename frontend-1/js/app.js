/**
 * app.js — Inicialização, roteamento de telas e carregamento de dados
 *
 * Orquestra todos os módulos (home, transacoes, metas, notificacoes, graficos, agenda)
 */

// ─── ROTEAMENTO ───────────────────────────────────────────────────────────────

// Telas que têm o header global (com nome + toggle PJ/PF)
const screensWithGlobalHeader = ['home', 'graficos'];

// Mapeamento de nome de tela → id do nav button
const navIds = {
  home:       'nav-home',
  graficos:   'nav-graficos',
  chat:       'nav-chat',
  agenda:     'nav-agenda',
  perfil:     'nav-perfil',
  estrategias: 'nav-estrategias',
};

// Telas filhas → tela pai para highlight do nav
const navParent = {
  'transacoes': 'graficos',
  'detalhes':   'graficos',
  'metas':      'perfil',
  'notificacoes': 'home',
  'agenda':       'agenda',
  'historico-faturas': 'graficos',
  'busca': 'graficos',
};

let navHistory = ['home'];

function showScreen(name) {
  document.querySelectorAll('.screen').forEach(s => {
    s.style.display = 'none';
    s.classList.remove('screen-enter');
  });

  const target = document.getElementById(`screen-${name}`);
  if (target) {
    target.style.display = 'block';
    target.classList.add('screen-enter');
  }

  // Header global
  const globalHeader = document.querySelector('.header');
  const showHeader = screensWithGlobalHeader.includes(name);
  if (globalHeader) globalHeader.style.display = showHeader ? '' : 'none';

  // Nav ativo
  const navKey = navIds[name] ? name : (navParent[name] || null);
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  if (navKey && navIds[navKey]) {
    const navEl = document.getElementById(navIds[navKey]);
    if (navEl) navEl.classList.add('active');
  }

  // Ocultar bottom nav em telas de login/onboarding
  const bottomNav = document.querySelector('.bottom-nav');
  const hideNav = ['login', 'register', 'onboarding', 'loading'].includes(name);
  if (bottomNav) bottomNav.style.display = hideNav ? 'none' : '';
}

function goTo(name) {
  showScreen(name);
  if (navHistory[navHistory.length - 1] !== name) navHistory.push(name);

  // Carregar dados ao entrar em tela específica
  if (name === 'home')                { loadHome().catch(console.error); }
  if (name === 'graficos')            { initGraficos(); }
  if (name === 'chat')                { loadChat().catch(console.error); }
  if (name === 'assinatura' || name === 'ass-ver-todas') { loadSubscriptions().catch(console.error); }
  if (name === 'detalhes' || name === 'transacoes') { initDetalhes(); }
  if (name === 'transacoes')          { renderTransacoes(window._txData || []); }
  if (name === 'metas')               { loadMetas().catch(console.error); }
  if (name === 'notificacoes')        { loadNotificacoes().catch(console.error); }
  if (name === 'agenda')              { loadAgenda().catch(console.error); }
  if (name === 'comparativo')         { initComparativo(); }
  if (name === 'historico-faturas')   { renderFaturas('inter'); }
  if (name === 'busca') {
    setTimeout(() => {
      const inp = document.getElementById('busca-input');
      if (inp) { inp.value = ''; inp.focus(); }
      buscarTransacoes('');
    }, 100);
  }
  if (name === 'cx-selecionar-banco') {
    renderBancos(bancosOpenFinance);
    const s = document.getElementById('banco-search');
    if (s) s.value = '';
  }
}

function goBack() {
  navHistory.pop();
  goTo(navHistory[navHistory.length - 1] || 'home');
}

window.goTo   = goTo;
window.goBack = goBack;

// ─── INICIALIZAÇÃO ───────────────────────────────────────────────────────────

async function initApp() {
  showScreen('loading');

  try {
    // Carregar dados em paralelo
    const userId = auth.getUserId();
    if (!userId) {
      showScreen('login');
      return;
    }

    // Carregamento principal
    await Promise.allSettled([
      loadHome(),
      loadTransacoes(),
    ]);

    goTo('home');
  } catch (err) {
    console.error('[App] Erro ao inicializar:', err);
    showScreen('home'); // Mostrar home mesmo com erro parcial
  }
  
}

// ─── MODO PJ/PF ──────────────────────────────────────────────────────────────
let _modeAtual = 'PF';
function setMode(btn, mode) {
  _modeAtual = mode;
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const alertEl = document.getElementById('alert-text');
  if (alertEl) alertEl.innerHTML = `<strong>Atenção:</strong> você está no modo ${mode}.`;
}
window.setMode = setMode;

// ─── DETALHE DE TRANSAÇÃO ─────────────────────────────────────────────────────
function abrirTxDetalhe(nomeEnc, catEnc, valorEnc, cartaoEnc, dataEnc, parcelas, icon) {
  const dec = decodeURIComponent;
  document.getElementById('txd-nome').textContent     = dec(nomeEnc);
  document.getElementById('txd-cat').textContent      = dec(catEnc);
  document.getElementById('txd-valor').textContent    = dec(valorEnc);
  document.getElementById('txd-cartao').textContent   = dec(cartaoEnc) || '—';
  document.getElementById('txd-data').textContent     = dec(dataEnc);
  document.getElementById('txd-parcelas').textContent = parcelas || 'À vista';
  document.getElementById('txd-icon').textContent     = icon || 'Tx';
  goTo('tx-detalhe');
}
window.abrirTxDetalhe = abrirTxDetalhe;

// ─── MODO ESCURO ─────────────────────────────────────────────────────────────
let _darkMode = localStorage.getItem('dark_mode') === '1';
function applyDarkMode() {
  document.body.classList.toggle('dark', _darkMode);
}
function toggleDarkMode() {
  _darkMode = !_darkMode;
  localStorage.setItem('dark_mode', _darkMode ? '1' : '0');
  applyDarkMode();
  // Atualizar label no perfil
  document.querySelectorAll('.perfil-card-btn').forEach(b => {
    if (b.textContent.includes('Modo escuro') || b.textContent.includes('Modo claro')) {
      b.textContent = _darkMode ? 'Modo claro' : 'Modo escuro';
    }
  });
}
window.toggleDarkMode = toggleDarkMode;

// ─── LOGOUT ───────────────────────────────────────────────────────────────────
function logout() {
  if (confirm('Deseja sair da conta?')) auth.logout();
}
window.logout = logout;

// ─── PREMIUM / PLANO ─────────────────────────────────────────────────────────
let premiumSelecionado = 'anual';
let planoAtual = 'mensal';
let planoSelecionado = 'mensal';

function selecionarPremium(plano) {
  premiumSelecionado = plano;
  const svgCheck = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
  const cA = document.getElementById('premium-card-anual');
  const cM = document.getElementById('premium-card-mensal');
  const chA = document.getElementById('premium-check-anual');
  const chM = document.getElementById('premium-check-mensal');
  const btn = document.getElementById('premium-btn-confirmar');
  if (plano === 'anual') {
    if (cA) { cA.style.border = '4px solid #9DC9FB'; cA.style.background = 'linear-gradient(135deg, rgba(157,201,251,0.3), rgba(246,249,249,0.3))'; }
    if (cM) { cM.style.border = '1.5px solid #9DC9FB'; cM.style.background = 'var(--card-bg)'; }
    if (chA) { chA.style.background = '#9DC9FB'; chA.style.borderColor = '#9DC9FB'; chA.innerHTML = svgCheck; }
    if (chM) { chM.style.background = 'transparent'; chM.style.borderColor = '#9DC9FB'; chM.innerHTML = ''; }
    if (btn)  btn.textContent = 'Iniciar teste grátis — Anual';
  } else {
    if (cM) { cM.style.border = '4px solid #9DC9FB'; cM.style.background = 'linear-gradient(135deg, rgba(157,201,251,0.3), rgba(246,249,249,0.3))'; }
    if (cA) { cA.style.border = '1.5px solid #9DC9FB'; cA.style.background = 'var(--card-bg)'; }
    if (chM) { chM.style.background = '#9DC9FB'; chM.style.borderColor = '#9DC9FB'; chM.innerHTML = svgCheck; }
    if (chA) { chA.style.background = 'transparent'; chA.style.borderColor = '#9DC9FB'; chA.innerHTML = ''; }
    if (btn)  btn.textContent = 'Iniciar teste grátis — Mensal';
  }
}

function confirmarPremium() {
  planoAtual = premiumSelecionado;
  planoSelecionado = premiumSelecionado;
  goTo('assinatura');
}

function confirmarTrocaPlano() {
  planoAtual = planoAtual === 'mensal' ? 'anual' : 'mensal';
  planoSelecionado = planoAtual;
  initAssinatura();
}

function initAssinatura() {
  const nomeEl     = document.getElementById('ass-plano-nome');
  const renovEl    = document.getElementById('ass-renovacao');
  const blocoAnual = document.getElementById('ass-trocar-anual');
  const blocoMens  = document.getElementById('ass-trocar-mensal');
  if (nomeEl)    nomeEl.textContent  = planoAtual === 'anual' ? 'Nexa Premium Anual' : 'Nexa Premium Mensal';
  if (renovEl)   renovEl.textContent = planoAtual === 'anual' ? '04/02/2027' : '04/03/2026';
  if (blocoAnual) blocoAnual.style.display = planoAtual === 'mensal' ? '' : 'none';
  if (blocoMens)  blocoMens.style.display  = planoAtual === 'anual'  ? '' : 'none';
}

window.selecionarPremium = selecionarPremium;
window.confirmarPremium  = confirmarPremium;
window.confirmarTrocaPlano = confirmarTrocaPlano;
window.initAssinatura    = initAssinatura;

// ─── CARROSSEL DE CARTÕES ─────────────────────────────────────────────────────
let _currentCard = 0;
function cartaoAtivo(index) {
  _currentCard = index;
  document.querySelectorAll('.cartao-dot').forEach((d, i) => {
    d.classList.toggle('active', i === index);
  });
}
window.cartaoAtivo = cartaoAtivo;

// Detecção de scroll no carrossel
window.addEventListener('load', () => {
  const carousel = document.getElementById('cartoes-carousel');
  if (!carousel) return;
  let scrollTimer;
  carousel.addEventListener('scroll', () => {
    clearTimeout(scrollTimer);
    scrollTimer = setTimeout(() => {
      const totalCards = document.querySelectorAll('.cartao-slide').length;
      if (!totalCards) return;
      const slideW = carousel.scrollWidth / totalCards;
      const idx    = Math.round(carousel.scrollLeft / slideW);
      _currentCard = Math.min(idx, totalCards - 1);
      cartaoAtivo(_currentCard);
    }, 60);
  }, { passive: true });
});

// ─── ONBOARDING ───────────────────────────────────────────────────────────────
let obSlide = 0;
function obNext() {
  const slides = document.querySelectorAll('[id^="ob-slide-"]');
  const dots   = document.querySelectorAll('[id^="ob-dot-"]');
  const btn    = document.getElementById('ob-btn-next');
  slides[obSlide].style.display = 'none';
  dots[obSlide].style.width = '6px';
  dots[obSlide].style.background = 'var(--blue-light)';
  obSlide++;
  if (obSlide >= slides.length) { goTo('home'); obSlide = 0; return; }
  slides[obSlide].style.display = '';
  dots[obSlide].style.width = '20px';
  dots[obSlide].style.background = 'var(--blue-primary)';
  if (btn) btn.textContent = obSlide === slides.length - 1 ? 'Começar' : 'Próximo';
}
window.obNext = obNext;

// ─── ADD CARTÃO ───────────────────────────────────────────────────────────────
// (Mantém lógica de detecção de BIN do original)
const BIN_MAP = {
  '5213':'nubank','5404':'nubank','4910':'nubank','5239':'nubank','5370':'nubank',
  '5166':'inter', '5187':'inter', '4514':'inter', '4556':'inter',
  '5277':'c6',    '4716':'c6',
  '5067':'bradesco','4389':'bradesco','5169':'bradesco','5276':'bradesco',
  '5178':'itau',  '4017':'itau',  '4024':'itau',  '5529':'itau',
  '5358':'santander','4532':'santander','5290':'santander',
  '5041':'bb',    '4984':'bb',    '5159':'bb',
  '5032':'caixa', '4502':'caixa',
  '5219':'btg',   '5231':'xp',
};
const BANCO_DESIGNS = {
  nubank:    { grad:'linear-gradient(145deg,#7A0AA8,#9B1ED6)', logo:'nu', logoSize:'18px', logoBg:'rgba(0,0,0,0.2)' },
  inter:     { grad:'linear-gradient(145deg,#F85C04,#FF7A1A)', logo:'inter', logoSize:'17px', logoBg:'rgba(255,255,255,0.18)' },
  c6:        { grad:'linear-gradient(145deg,#242424,#383838)', logo:'C6', logoSize:'20px', logoBg:'transparent', extra:'<span style="font-size:8px;color:rgba(255,255,255,0.5);margin-left:2px;"> BANK</span>' },
  bradesco:  { grad:'linear-gradient(145deg,#CC0000,#E8001C)', logo:'Bradesco', logoSize:'13px', logoBg:'rgba(255,255,255,0.15)' },
  itau:      { grad:'linear-gradient(145deg,#EC7000,#FF8C00)', logo:'itaú', logoSize:'15px', logoBg:'rgba(0,0,0,0.15)' },
  santander: { grad:'linear-gradient(145deg,#EC0000,#FF1A1A)', logo:'Santander', logoSize:'12px', logoBg:'rgba(255,255,255,0.15)' },
  bb:        { grad:'linear-gradient(145deg,#F8D000,#E6BC00)', logo:'BB', logoSize:'18px', logoBg:'rgba(0,0,0,0.15)', textColor:'#1A1A2E' },
  caixa:     { grad:'linear-gradient(145deg,#005CA9,#0074CC)', logo:'CAIXA', logoSize:'13px', logoBg:'rgba(255,255,255,0.15)' },
  btg:       { grad:'linear-gradient(145deg,#1A1A1A,#2D2D2D)', logo:'BTG', logoSize:'16px', logoBg:'rgba(255,255,255,0.1)' },
  xp:        { grad:'linear-gradient(145deg,#1A1A1A,#333)', logo:'XP', logoSize:'18px', logoBg:'rgba(255,255,255,0.1)' },
  outro:     { grad:'linear-gradient(145deg,#607D8B,#78909C)', logo:'Cartão', logoSize:'14px', logoBg:'rgba(255,255,255,0.2)' },
};
let bancoDetectado = null;
function detectarBIN(rawValue) {
  const digits = rawValue.replace(/\D/g,'');
  const bin4   = digits.substring(0,4);
  const banco  = BIN_MAP[bin4] || null;
  const masked = digits.padEnd(16,'•').replace(/(.{4})/g,'$1 ').trim();
  const numEl  = document.getElementById('add-cartao-num');
  if (numEl) numEl.textContent = digits.length > 0 ? masked : '•••• •••• •••• ••••';
  if (banco && banco !== bancoDetectado) {
    bancoDetectado = banco;
    aplicarDesignCartao(banco);
    const badge = document.getElementById('add-cartao-banco-detected');
    if (badge) { badge.style.display = 'flex'; document.getElementById('add-cartao-banco-nome').textContent = '✓ ' + banco.charAt(0).toUpperCase() + banco.slice(1) + ' detectado automaticamente'; }
    const wrap = document.getElementById('add-banco-manual-wrap');
    if (wrap) wrap.style.opacity = '0.4';
  } else if (!banco && bancoDetectado) {
    bancoDetectado = null;
    aplicarDesignCartao(null);
    const badge = document.getElementById('add-cartao-banco-detected');
    if (badge) badge.style.display = 'none';
    const wrap = document.getElementById('add-banco-manual-wrap');
    if (wrap) wrap.style.opacity = '1';
  }
}
function aplicarDesignCartao(banco) {
  const preview = document.getElementById('add-cartao-preview');
  const logoEl  = document.getElementById('add-cartao-logo');
  if (!preview || !logoEl) return;
  const design = BANCO_DESIGNS[banco] || BANCO_DESIGNS['outro'];
  if (!banco) { preview.style.background = 'linear-gradient(145deg,#B0BEC5,#90A4AE)'; logoEl.innerHTML = '<span style="font-size:15px;font-weight:800;color:#fff;letter-spacing:-0.3px;">Cartão</span>'; logoEl.style.background = 'rgba(255,255,255,0.2)'; return; }
  preview.style.background = design.grad;
  logoEl.style.background  = design.logoBg;
  logoEl.innerHTML = `<span style="font-size:${design.logoSize};font-weight:800;color:${design.textColor||'#fff'};letter-spacing:-0.3px;">${design.logo}</span>${design.extra||''}`;
}
function aplicarBancoManual(banco) { if (!banco || bancoDetectado) return; aplicarDesignCartao(banco); }
function formatarNumCartao(input) { let v = input.value.replace(/\D/g,'').substring(0,16); input.value = v.replace(/(.{4})/g,'$1 ').trim(); }
function formatarValidade(input) {
  let v = input.value.replace(/\D/g,'').substring(0,4);
  if (v.length > 2) v = v.substring(0,2) + '/' + v.substring(2);
  input.value = v;
  const el = document.getElementById('add-cartao-validade-preview');
  if (el) el.textContent = v || 'MM/AA';
}
function confirmarAddCartao() {
  const num = document.getElementById('add-num')?.value.replace(/\s/g,'');
  if (!num || num.length < 16) { alert('Número do cartão incompleto.'); return; }
  const banco  = bancoDetectado || document.getElementById('add-banco-select')?.value || 'outro';
  const design = BANCO_DESIGNS[banco] || BANCO_DESIGNS['outro'];
  const nomeBanco = banco === 'outro' ? 'seu banco' : banco.charAt(0).toUpperCase() + banco.slice(1);
  const el = document.getElementById('of-sugestao-banco');      if (el) el.textContent = nomeBanco;
  const elCard = document.getElementById('of-sugestao-banco-card'); if (elCard) elCard.textContent = nomeBanco;
  const card = document.getElementById('of-sugestao-card');     if (card) card.style.background = design.grad;
  const logoEl = document.getElementById('of-sugestao-logo');
  if (logoEl) logoEl.innerHTML = `<span style="font-size:${design.logoSize};font-weight:800;color:${design.textColor||'#fff'};">${design.logo}</span>${design.extra||''}`;
  goTo('add-cartao-of');
}
window.detectarBIN     = detectarBIN;
window.aplicarBancoManual = aplicarBancoManual;
window.formatarNumCartao  = formatarNumCartao;
window.formatarValidade   = formatarValidade;
window.confirmarAddCartao = confirmarAddCartao;

// ─── LISTA DE BANCOS OPEN FINANCE ─────────────────────────────────────────────
const bancosOpenFinance = ['Banco do Brasil','Bradesco','Caixa Econômica Federal','Itaú','Santander','Nubank','Inter','C6 Bank','Next','Neon','Mercado Pago','PagSeguro','PicPay','BTG Pactual','XP','Sicoob','Sicredi','BRB','Banco Pan','Sofisa','Stone','Asaas'].sort((a,b) => a.localeCompare(b,'pt'));

function renderBancos(lista) {
  const container = document.getElementById('banco-lista');
  if (!container) return;
  if (!lista.length) { container.innerHTML = '<div style="padding:20px;text-align:center;font-size:13px;color:var(--text-muted);">Nenhuma instituição encontrada.</div>'; return; }
  container.innerHTML = lista.map(banco => `
    <button onclick="selecionarBanco('${banco.replace(/'/g,"\\'")}');goTo('cx-dados-banco')"
      style="display:flex;align-items:center;gap:12px;padding:12px 14px;background:var(--card-bg);border:none;border-radius:var(--radius-sm);cursor:pointer;font-family:'Poppins',sans-serif;width:100%;text-align:left;transition:background 0.15s;"
      onmouseover="this.style.background='var(--bg)'" onmouseout="this.style.background='var(--card-bg)'">
      <div style="width:36px;height:36px;border-radius:10px;background:var(--blue-lighter);flex-shrink:0;display:flex;align-items:center;justify-content:center;">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#2D7DD2" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="8" width="18" height="13" rx="2"/><path d="M3 8l9-5 9 5"/></svg>
      </div>
      <span style="font-size:13.5px;font-weight:500;color:var(--text-dark);">${banco}</span>
    </button>`).join('');
}
function filtrarBancos() {
  const q = document.getElementById('banco-search')?.value?.toLowerCase() || '';
  renderBancos(q ? bancosOpenFinance.filter(b => b.toLowerCase().includes(q)) : bancosOpenFinance);
}
let bancoSelecionado = '';
function selecionarBanco(nome) {
  bancoSelecionado = nome;
  const el = document.getElementById('banco-selecionado-nome');
  if (el) el.textContent = nome;
}
window.renderBancos   = renderBancos;
window.filtrarBancos  = filtrarBancos;
window.selecionarBanco = selecionarBanco;

// ─── BOOT ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  applyDarkMode();
  renderBancos(bancosOpenFinance);

  if (auth.isAuthenticated()) {
    initApp().catch(console.error);
  } else {
    showScreen('login');
  }
  
  // Carrega conexões bancárias do backend (Pluggy) e popula a tela
  async function loadConexoes() {
    const container = document.querySelector('#screen-conexoes-bancarias .content');
    const listEl = document.getElementById('banco-lista');
    try {
      const userId = auth.getUserId();
      const data = await api.getPluggyItems();
      const items = Array.isArray(data) ? data : (data.items || data.accounts || []);
      // Substituir a lista estática por conexões reais
      const conexHtml = items.length ? items.map(it => `
        <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 12px;background:var(--white);border-radius:var(--radius-sm);margin-bottom:8px;">
          <div style="display:flex;align-items:center;gap:10px;">
            <div style="width:34px;height:34px;border-radius:50%;background:var(--blue-lighter);flex-shrink:0;"></div>
            <div>
              <div style="font-size:13px;font-weight:600;color:var(--text-dark);">${(it.institution_name||it.name||it.bank_name||'Conta')}</div>
              <div style="font-size:11px;color:var(--text-muted);">Última atualização: ${it.last_synced || it.updated_at || '—'}</div>
            </div>
          </div>
          <div style="font-size:12px;color:var(--text-muted);">${it.status || ''}</div>
        </div>`).join('') : '<div style="padding:20px;text-align:center;color:var(--text-muted);">Nenhuma conexão encontrada.</div>';
      if (listEl) listEl.innerHTML = conexHtml;
    } catch (err) {
      // manter fallback estático
      console.warn('[Conexoes] não foi possível carregar Pluggy:', err);
    }
  }
  window.loadConexoes = loadConexoes;
});

window.initApp = initApp;
