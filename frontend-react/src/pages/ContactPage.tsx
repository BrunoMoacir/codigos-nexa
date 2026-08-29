import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

// ── Scramble text (efeito de filtro financeiro — substitui o slot-machine) ───
const GLYPHS = '₿€$¥£₹+%#@&×∑';
const ScrambleText: React.FC<{ text: string }> = ({ text }) => {
  const [chars, setChars] = useState<string[]>(() => text.split('').map(() => GLYPHS[0]));
  useEffect(() => {
    let frame = 0;
    const SETTLE = (i: number) => (i + 1) * 5;
    const MAX = SETTLE(text.length - 1) + 10;
    const tick = setInterval(() => {
      frame++;
      setChars(text.split('').map((ch, i) =>
        frame >= SETTLE(i) ? ch : GLYPHS[Math.floor(Math.random() * GLYPHS.length)]
      ));
      if (frame >= MAX) clearInterval(tick);
    }, 55);
    return () => clearInterval(tick);
  }, [text]);
  return <>{chars.join('')}</>;
};

// ── Padrão hexagonal (fundo do painel direito) ───────────────────────────────
const HEX_DATA = (() => {
  const SIZE = 20;
  const W = 1.732 * SIZE;
  const H = SIZE * 2;
  const result: Array<{ pts: string; op: number }> = [];
  for (let c = 0; c < 11; c++) {
    for (let r = 0; r < 10; r++) {
      const cx = c * W + (r % 2 !== 0 ? W / 2 : 0) + W / 2;
      const cy = r * (H * 0.75) + SIZE;
      const dist = Math.sqrt(Math.pow(cx - 240, 2) + Math.pow(cy - 240, 2));
      const op = Math.max(0.02, 0.09 - dist * 0.00018);
      const pts = Array.from({ length: 6 }, (_, k) => {
        const a = (Math.PI / 3) * k - Math.PI / 6;
        return `${(cx + (SIZE - 2) * Math.cos(a)).toFixed(1)},${(cy + (SIZE - 2) * Math.sin(a)).toFixed(1)}`;
      }).join(' ');
      result.push({ pts, op });
    }
  }
  return result;
})();

function HexBackground() {
  return (
    <svg
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 0 }}
      viewBox="0 0 480 520"
      preserveAspectRatio="xMidYMid slice"
    >
      <defs>
        <radialGradient id="cpHexGrad" cx="50%" cy="45%" r="60%">
          <stop offset="0%" stopColor="#D4A820" stopOpacity="0.14" />
          <stop offset="100%" stopColor="#D4A820" stopOpacity="0" />
        </radialGradient>
      </defs>
      {HEX_DATA.map((h, i) => (
        <polygon key={i} points={h.pts} fill="none"
          stroke={`rgba(212,168,32,${h.op.toFixed(3)})`} strokeWidth="0.8" />
      ))}
      <rect x="0" y="0" width="480" height="520" fill="url(#cpHexGrad)" />
    </svg>
  );
}

const css = `
  @import url('https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700,800,900&display=swap');
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  .cp-page {
    font-family: 'Satoshi', system-ui, sans-serif;
    min-height: 100vh;
    background: #0A0806;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 28px 20px;
  }

  .cp-card {
    width: 100%;
    max-width: 1160px;
    background: #13110E;
    border: 1px solid rgba(212,168,32,0.14);
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 8px 48px rgba(0,0,0,0.5), 0 0 0 1px rgba(212,168,32,0.04);
  }

  @keyframes cp-up {
    from { opacity:0; transform:translateY(10px); }
    to   { opacity:1; transform:translateY(0); }
  }

  @keyframes cp-logo-glow {
    0%,100% { filter: drop-shadow(0 0 3px rgba(212,168,32,0.35)) drop-shadow(0 0 1px rgba(212,168,32,0.5)); }
    50%     { filter: drop-shadow(0 0 10px rgba(212,168,32,0.7)) drop-shadow(0 0 4px rgba(255,200,60,0.4)); }
  }

  /* ── NAV ── */
  .cp-nav {
    display: flex;
    align-items: center;
    padding: 14px 24px;
    border-bottom: 1px solid rgba(243,239,234,0.07);
    gap: 28px;
    background: #0F0D0A;
  }
  .cp-nav-logo {
    display: flex;
    align-items: center;
    gap: 10px;
    text-decoration: none;
    flex-shrink: 0;
  }
  .cp-nav-logo-icon {
    width: 34px; height: 34px;
    background: #1E1A14;
    border: 1px solid rgba(212,168,32,0.3);
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    animation: cp-logo-glow 2.8s ease-in-out infinite;
  }
  .cp-nav-logo-name {
    font-size: 0.95rem;
    font-weight: 900;
    color: #D4A820;
    letter-spacing: 0.08em;
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }

  .cp-nav-links { display:flex; align-items:center; gap:20px; flex:1; }
  .cp-nav-actions { display:flex; align-items:center; gap:8px; flex-shrink:0; }
  .cp-nav-login {
    padding: 7px 14px;
    background: transparent;
    color: rgba(243,239,234,0.7);
    border: 1px solid rgba(243,239,234,0.15);
    border-radius: 8px;
    font-family: inherit;
    font-size: 0.82rem;
    font-weight: 600;
    cursor: pointer;
    text-decoration: none;
    display: inline-block;
    transition: all 0.15s;
  }
  .cp-nav-login:hover { border-color:rgba(243,239,234,0.3); color:#F3EFEA; }
  .cp-nav-register {
    padding: 7px 14px;
    background: #D4A820;
    color: #0A0800;
    border: none;
    border-radius: 8px;
    font-family: inherit;
    font-size: 0.82rem;
    font-weight: 800;
    cursor: pointer;
    text-decoration: none;
    display: inline-block;
    transition: background 0.15s, transform 0.12s;
  }
  .cp-nav-register:hover { background:#C89010; transform:translateY(-1px); }

  /* ── CORPO ── */
  .cp-body {
    display: grid;
    grid-template-columns: 1fr 1.08fr;
    min-height: 580px;
    position: relative;
    overflow: hidden;
  }
  .cp-grid-line {
    position: absolute;
    top:0; bottom:0; width:1px;
    border-left: 1px dashed rgba(243,239,234,0.05);
    pointer-events: none;
    z-index: 0;
  }

  /* ── ESQUERDO ── */
  .cp-left {
    padding: 44px 48px 44px;
    position: relative;
    z-index: 1;
    animation: cp-up 0.45s cubic-bezier(.16,1,.3,1) both;
  }

  .cp-form-title {
    font-size: clamp(1.6rem, 2.8vw, 2.1rem);
    font-weight: 900;
    letter-spacing: -0.04em;
    color: #F3EFEA;
    line-height: 1.12;
    margin-bottom: 10px;
  }
  .cp-form-title em {
    font-style: italic;
    color: #D4A820;
  }
  .cp-form-sub {
    font-size: 0.83rem;
    color: rgba(243,239,234,0.42);
    line-height: 1.65;
    margin-bottom: 28px;
    max-width: 360px;
  }

  /* Info items estilo Glimpse */
  .cp-info-items {
    display: flex;
    flex-direction: column;
    gap: 14px;
    margin-bottom: 32px;
  }
  .cp-info-item {
    display: flex;
    align-items: center;
    gap: 14px;
  }
  .cp-info-icon {
    width: 36px; height: 36px;
    border-radius: 9px;
    background: rgba(212,168,32,0.1);
    border: 1px solid rgba(212,168,32,0.18);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .cp-info-label {
    font-size: 0.65rem;
    font-weight: 600;
    color: rgba(243,239,234,0.35);
    text-transform: uppercase;
    letter-spacing: 0.07em;
    margin-bottom: 1px;
  }
  .cp-info-value {
    font-size: 0.85rem;
    font-weight: 700;
    color: #F3EFEA;
    text-decoration: none;
    transition: color 0.15s;
  }
  a.cp-info-value:hover { color: #D4A820; }

  /* Form fields */
  .cp-label {
    display: block;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.45);
    margin-bottom: 6px;
  }
  .cp-input {
    width: 100%;
    padding: 10px 13px;
    background: rgba(243,239,234,0.04);
    color: #F3EFEA;
    border: 1px solid rgba(243,239,234,0.1);
    border-radius: 8px;
    font-family: inherit;
    font-size: 0.86rem;
    outline: none;
    transition: border-color 0.15s, box-shadow 0.15s;
    resize: none;
  }
  .cp-input::placeholder { color: rgba(243,239,234,0.2); }
  .cp-input:focus { border-color:rgba(212,168,32,0.5); box-shadow:0 0 0 3px rgba(212,168,32,0.07); }
  .cp-input.err { border-color:rgba(240,122,100,0.55); }
  .cp-field-err { font-size:0.68rem; color:#F07A64; margin-top:4px; }

  .cp-row2 { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
  .cp-fields { display:flex; flex-direction:column; gap:14px; margin-bottom:22px; }

  /* Campo telefone com bandeira — SEM overflow:hidden (cortava o dropdown) */
  .cp-phone-wrap {
    display: flex;
    border: 1px solid rgba(243,239,234,0.1);
    border-radius: 8px;
    overflow: visible;
    transition: border-color 0.15s, box-shadow 0.15s;
    position: relative;
  }
  .cp-phone-wrap:focus-within { border-color:rgba(212,168,32,0.5); box-shadow:0 0 0 3px rgba(212,168,32,0.07); }
  .cp-phone-input {
    flex: 1;
    padding: 10px 13px;
    background: rgba(243,239,234,0.04);
    color: #F3EFEA;
    border: none;
    border-radius: 0 7px 7px 0;
    font-family: inherit;
    font-size: 0.86rem;
    outline: none;
  }
  .cp-phone-input::placeholder { color:rgba(243,239,234,0.2); }

  /* Botão continuar — dourado */
  .cp-btn-continue {
    width: 100%;
    padding: 12px;
    background: #D4A820;
    color: #0A0800;
    border: none;
    border-radius: 8px;
    font-family: inherit;
    font-size: 0.9rem;
    font-weight: 900;
    letter-spacing: 0.04em;
    cursor: pointer;
    transition: background 0.15s, transform 0.12s, box-shadow 0.2s;
    margin-bottom: 14px;
    box-shadow: 0 4px 18px rgba(212,168,32,0.2);
  }
  .cp-btn-continue:hover { background:#C89010; transform:translateY(-1px); box-shadow:0 6px 24px rgba(212,168,32,0.35); }

  .cp-email-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 0.77rem;
    color: rgba(243,239,234,0.35);
    text-decoration: underline;
    text-underline-offset: 3px;
    text-decoration-color: rgba(243,239,234,0.15);
    transition: color 0.15s;
  }
  .cp-email-link:hover { color:rgba(243,239,234,0.65); }

  /* ── DIREITO — device (sangra pela direita, igual referência) ── */
  .cp-device-area {
    position: relative;
    z-index: 1;
    overflow: hidden;
    background: #1C1814; /* fundo um pouco mais claro que o card para criar contraste */
    padding: 28px 0 28px 20px;
  }

  /* Bezel da tela — borda escura que simula moldura de monitor */
  .cp-device-bezel {
    width: 100%;
    height: 100%;
    min-height: 510px;
    background: #0A0806; /* bezel bem escuro, como a borda de um monitor */
    border-radius: 14px 0 0 14px;
    overflow: hidden;
    padding: 8px 0 8px 8px; /* espessura da moldura */
    box-shadow:
      -6px 0 32px rgba(0,0,0,0.5),
      0 0 0 1px rgba(255,255,255,0.06),
      inset 0 0 0 1px rgba(255,255,255,0.04);
    margin-right: -2px;
    display: flex;
    flex-direction: column;
    animation: cp-up 0.5s cubic-bezier(.16,1,.3,1) 0.1s both;
  }

  /* Área de tela dentro da moldura */
  .cp-device-screen {
    flex: 1;
    overflow: hidden;
    background: #0C0A08;
    border-radius: 8px 0 0 8px;
    position: relative;
    box-shadow: inset 0 0 40px rgba(0,0,0,0.4);
  }

  /* iframe escalado para parecer desktop real */
  .cp-dash-iframe {
    width: 1100px;
    height: 1050px;
    border: none;
    transform: scale(0.54);
    transform-origin: top left;
    pointer-events: none;
    display: block;
    background: #0C0A08;
  }

  /* ── TOPBAR do device ── */
  .cp-dev-topbar {
    padding: 10px 16px;
    background: #13110E;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }
  .cp-dev-logo { display:flex; align-items:center; gap:6px; }
  .cp-dev-logo-name { font-size:0.7rem; font-weight:800; color:#D4A820; letter-spacing:0.06em; }
  .cp-dev-version { font-size:0.52rem; background:rgba(212,168,32,0.15); color:rgba(212,168,32,0.7); padding:1px 5px; border-radius:3px; font-weight:700; }
  .cp-dev-tabs { display:flex; gap:0; margin-left:16px; }
  .cp-dev-tab { font-size:0.62rem; font-weight:600; color:rgba(243,239,234,0.3); padding:4px 10px; border-bottom:2px solid transparent; cursor:default; }
  .cp-dev-tab.active { color:#F3EFEA; border-bottom-color:#D4A820; }
  .cp-dev-tab-badge { display:inline-flex; align-items:center; justify-content:center; width:13px; height:13px; border-radius:3px; background:#D4A820; color:#0A0800; font-size:0.48rem; font-weight:800; margin-left:3px; }
  .cp-dev-url { flex:1; text-align:right; font-size:0.52rem; color:rgba(243,239,234,0.18); }

  /* ── LOGOS ── */
  .cp-logos-bar {
    border-top: 1px solid rgba(243,239,234,0.07);
    padding: 16px 32px;
    background: #0F0D0A;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .cp-logos-eyebrow { text-align:center; font-size:0.7rem; color:rgba(243,239,234,0.25); font-weight:500; }
  .cp-logos-row { display:flex; align-items:center; justify-content:center; gap:28px; flex-wrap:wrap; }
  .cp-logo-item { font-size:0.72rem; font-weight:700; color:rgba(243,239,234,0.2); letter-spacing:0.03em; }

  /* Sucesso */
  .cp-sent { display:flex; flex-direction:column; align-items:flex-start; animation:cp-up 0.45s cubic-bezier(.16,1,.3,1) both; }
  .cp-sent-icon { width:44px; height:44px; border-radius:50%; background:rgba(46,200,164,0.1); border:1px solid rgba(46,200,164,0.28); display:flex; align-items:center; justify-content:center; margin-bottom:18px; }
  .cp-sent-title { font-size:1.5rem; font-weight:900; color:#F3EFEA; letter-spacing:-0.04em; margin-bottom:8px; }
  .cp-sent-sub { font-size:0.82rem; color:rgba(243,239,234,0.42); line-height:1.7; max-width:320px; margin-bottom:24px; }

  @media (max-width:860px) {
    .cp-body { grid-template-columns:1fr; }
    .cp-device-area { display:none; }
    .cp-left { padding:36px 24px; }
  }
`;

function HiveLogo({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={Math.round(size*1.11)} viewBox="0 0 180 200" fill="none">
      <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="#7A5002"/>
      <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="#D4A820"/>
      <polygon points="100,16 110,22 110,178 100,184" fill="#090500"/>
    </svg>
  );
}

function ChevronDown({ size = 9 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 10 10" fill="none">
      <path d="M2 3.5 5 6.5l3-3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

const LOGOS = ['Nubank','XP Inc.','BTG Pactual','Itaú','Bradesco','Clear','Rico','Avenue','Inter','C6 Bank'];

// ── Países com código DDI ─────────────────────────────────────────────────────
const COUNTRIES = [
  { code: 'BR', flag: '🇧🇷', name: 'Brasil',              dial: '+55'  },
  { code: 'US', flag: '🇺🇸', name: 'Estados Unidos',      dial: '+1'   },
  { code: 'PT', flag: '🇵🇹', name: 'Portugal',            dial: '+351' },
  { code: 'AR', flag: '🇦🇷', name: 'Argentina',           dial: '+54'  },
  { code: 'CL', flag: '🇨🇱', name: 'Chile',               dial: '+56'  },
  { code: 'CO', flag: '🇨🇴', name: 'Colômbia',            dial: '+57'  },
  { code: 'MX', flag: '🇲🇽', name: 'México',              dial: '+52'  },
  { code: 'PE', flag: '🇵🇪', name: 'Peru',                dial: '+51'  },
  { code: 'UY', flag: '🇺🇾', name: 'Uruguai',             dial: '+598' },
  { code: 'PY', flag: '🇵🇾', name: 'Paraguai',            dial: '+595' },
  { code: 'BO', flag: '🇧🇴', name: 'Bolívia',             dial: '+591' },
  { code: 'VE', flag: '🇻🇪', name: 'Venezuela',           dial: '+58'  },
  { code: 'EC', flag: '🇪🇨', name: 'Equador',             dial: '+593' },
  { code: 'GB', flag: '🇬🇧', name: 'Reino Unido',         dial: '+44'  },
  { code: 'DE', flag: '🇩🇪', name: 'Alemanha',            dial: '+49'  },
  { code: 'FR', flag: '🇫🇷', name: 'França',              dial: '+33'  },
  { code: 'IT', flag: '🇮🇹', name: 'Itália',              dial: '+39'  },
  { code: 'ES', flag: '🇪🇸', name: 'Espanha',             dial: '+34'  },
  { code: 'NL', flag: '🇳🇱', name: 'Países Baixos',       dial: '+31'  },
  { code: 'CH', flag: '🇨🇭', name: 'Suíça',               dial: '+41'  },
  { code: 'JP', flag: '🇯🇵', name: 'Japão',               dial: '+81'  },
  { code: 'CN', flag: '🇨🇳', name: 'China',               dial: '+86'  },
  { code: 'IN', flag: '🇮🇳', name: 'Índia',               dial: '+91'  },
  { code: 'AU', flag: '🇦🇺', name: 'Austrália',           dial: '+61'  },
  { code: 'CA', flag: '🇨🇦', name: 'Canadá',              dial: '+1'   },
  { code: 'ZA', flag: '🇿🇦', name: 'África do Sul',       dial: '+27'  },
  { code: 'NG', flag: '🇳🇬', name: 'Nigéria',             dial: '+234' },
  { code: 'AE', flag: '🇦🇪', name: 'Emirados Árabes',     dial: '+971' },
  { code: 'IL', flag: '🇮🇱', name: 'Israel',              dial: '+972' },
  { code: 'KR', flag: '🇰🇷', name: 'Coreia do Sul',       dial: '+82'  },
];

const COUNTRY_DROPDOWN_CSS = `
  /* ── Botão trigger ── */
  .cp-country-btn {
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 0 12px;
    height: 100%;
    background: rgba(243,239,234,0.05);
    border: none;
    border-right: 1px solid rgba(243,239,234,0.1);
    border-radius: 7px 0 0 7px;
    font-family: inherit;
    font-size: 0.84rem;
    font-weight: 600;
    color: rgba(243,239,234,0.8);
    flex-shrink: 0;
    white-space: nowrap;
    cursor: pointer;
    outline: none;
    transition: background 0.15s;
    user-select: none;
  }
  .cp-country-btn:hover { background: rgba(243,239,234,0.09); }

  /* bandeira no botão — quadrado arredondado */
  .cp-flag-box {
    width: 28px; height: 28px;
    border-radius: 6px;
    background: rgba(255,255,255,0.07);
    display: flex; align-items: center; justify-content: center;
    font-size: 1.2rem;
    line-height: 1;
    flex-shrink: 0;
  }

  /* ── Dropdown ── */
  .cp-country-dropdown {
    position: absolute;
    top: calc(100% + 8px);
    left: 0;
    width: 300px;
    background: #1E1A14;
    border: 1px solid rgba(212,168,32,0.15);
    border-radius: 14px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.65), 0 0 0 1px rgba(212,168,32,0.05);
    z-index: 300;
    overflow: hidden;
    animation: cp-up 0.18s cubic-bezier(.16,1,.3,1) both;
  }

  /* barra de busca */
  .cp-country-search-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 13px 16px;
    border-bottom: 1px solid rgba(243,239,234,0.07);
    background: rgba(243,239,234,0.025);
  }
  .cp-country-search {
    flex: 1;
    background: transparent;
    color: #F3EFEA;
    border: none;
    font-family: inherit;
    font-size: 0.88rem;
    outline: none;
    caret-color: #D4A820;
  }
  .cp-country-search::placeholder { color: rgba(243,239,234,0.22); }

  /* lista */
  .cp-country-list {
    max-height: 260px;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: rgba(212,168,32,0.25) transparent;
  }

  /* item */
  .cp-country-item {
    display: flex;
    align-items: center;
    gap: 13px;
    padding: 11px 16px;
    cursor: pointer;
    transition: background 0.08s;
    user-select: none;
  }
  .cp-country-item:hover { background: rgba(212,168,32,0.07); }
  .cp-country-item.sel  { background: rgba(212,168,32,0.12); }

  /* bandeira — quadrado arredondado (igual WhatsApp) */
  .cp-flag-item-box {
    width: 36px; height: 36px;
    border-radius: 8px;
    background: rgba(255,255,255,0.06);
    display: flex; align-items: center; justify-content: center;
    font-size: 1.45rem;
    line-height: 1;
    flex-shrink: 0;
  }

  /* nome + código */
  .cp-country-text { flex: 1; min-width: 0; }
  .cp-country-name {
    font-size: 0.88rem;
    font-weight: 600;
    color: #F3EFEA;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.3;
  }
  .cp-country-code-tag {
    font-size: 0.78rem;
    color: rgba(243,239,234,0.38);
    font-variant-numeric: tabular-nums;
    font-weight: 400;
    line-height: 1.3;
  }
  .cp-country-item.sel .cp-country-name { color: #F8E97A; }
  .cp-country-item.sel .cp-country-code-tag { color: rgba(212,168,32,0.65); }

  /* checkmark */
  .cp-country-check { flex-shrink: 0; }
`;

const CountrySelector: React.FC<{
  selected: typeof COUNTRIES[0];
  onChange: (c: typeof COUNTRIES[0]) => void;
}> = ({ selected, onChange }) => {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);

  const filtered = COUNTRIES.filter(c =>
    c.name.toLowerCase().includes(search.toLowerCase()) || c.dial.includes(search)
  );

  // Abre/fecha: stopPropagation impede o listener do document de fechar imediatamente
  const toggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    setOpen(o => !o);
  };

  // Adiciona listener de click no document só enquanto aberto — fecha ao clicar fora
  useEffect(() => {
    if (!open) return;
    const close = () => { setOpen(false); setSearch(''); };
    document.addEventListener('click', close);
    const t = setTimeout(() => searchRef.current?.focus(), 60);
    return () => { document.removeEventListener('click', close); clearTimeout(t); };
  }, [open]);

  const pick = (e: React.MouseEvent, c: typeof COUNTRIES[0]) => {
    e.stopPropagation();
    onChange(c);
    setOpen(false);
    setSearch('');
  };

  return (
    <div style={{ position: 'relative' }}>
      {/* Trigger */}
      <button type="button" className="cp-country-btn" onClick={toggle}>
        <div className="cp-flag-box">
          <img
            src={`https://flagcdn.com/w40/${selected.code.toLowerCase()}.png`}
            alt={selected.name}
            style={{ width: 22, height: 16, objectFit: 'cover', borderRadius: 3, display: 'block' }}
          />
        </div>
        <span style={{ fontVariantNumeric: 'tabular-nums' }}>{selected.dial}</span>
        <ChevronDown size={9} />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="cp-country-dropdown" onClick={e => e.stopPropagation()}>

          {/* Busca */}
          <div className="cp-country-search-row">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ flexShrink: 0 }}>
              <circle cx="6" cy="6" r="4.5" stroke="rgba(243,239,234,0.3)" strokeWidth="1.4"/>
              <path d="M10 10l2.5 2.5" stroke="rgba(243,239,234,0.3)" strokeWidth="1.4" strokeLinecap="round"/>
            </svg>
            <input
              ref={searchRef}
              className="cp-country-search"
              placeholder="Buscar país ou código..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              autoComplete="off"
              data-form-type="other"
            />
          </div>

          {/* Lista */}
          <div className="cp-country-list">
            {filtered.length === 0 && (
              <div style={{ padding: '16px', fontSize: '0.82rem', color: 'rgba(243,239,234,0.28)', textAlign: 'center' }}>
                Nenhum país encontrado
              </div>
            )}
            {filtered.map(c => (
              <div
                key={c.code}
                className={`cp-country-item${c.code === selected.code ? ' sel' : ''}`}
                onClick={e => pick(e, c)}
              >
                {/* Bandeira real via flagcdn.com */}
                <div className="cp-flag-item-box">
                  <img
                    src={`https://flagcdn.com/w40/${c.code.toLowerCase()}.png`}
                    alt={c.name}
                    style={{ width: 28, height: 20, objectFit: 'cover', borderRadius: 4, display: 'block' }}
                  />
                </div>

                {/* Nome + código */}
                <div className="cp-country-text">
                  <div className="cp-country-name">{c.name}</div>
                  <div className="cp-country-code-tag">({c.dial})</div>
                </div>

                {/* Checkmark se selecionado */}
                {c.code === selected.code && (
                  <svg className="cp-country-check" width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M2.5 7l3.5 3.5 5.5-6" stroke="#D4A820" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export const ContactPage: React.FC = () => {
  const [fname, setFname]     = useState('');
  const [lname, setLname]     = useState('');
  const [email, setEmail]     = useState('');
  const [phone, setPhone]     = useState('');
  const [message, setMessage] = useState('');
  const [errs, setErrs]       = useState({ fname:'', email:'', message:'' });
  const [sent, setSent]       = useState(false);
  const [country, setCountry] = useState(COUNTRIES[0]);

  const fmtPhone = (v: string) => {
    const d = v.replace(/\D/g,'').slice(0,11);
    if (d.length<=2) return d;
    if (d.length<=7) return `(${d.slice(0,2)}) ${d.slice(2)}`;
    return `(${d.slice(0,2)}) ${d.slice(2,7)}-${d.slice(7)}`;
  };

  const validate = () => {
    const e = { fname:'', email:'', message:'' };
    if (!fname.trim()) e.fname = 'Preencha seu nome';
    if (!email.trim()) e.email = 'Preencha o e-mail';
    else if (!/\S+@\S+\.\S+/.test(email)) e.email = 'E-mail inválido';
    if (!message.trim()) e.message = 'Escreva sua mensagem';
    setErrs(e);
    return !Object.values(e).some(Boolean);
  };

  const handleSubmit = (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!validate()) return;
    const lines = [
      `*Nova mensagem via HIVE*`,
      ``,
      `*Nome:* ${fname}${lname ? ' ' + lname : ''}`,
      `*E-mail:* ${email}`,
      phone ? `*Telefone:* ${country.dial} ${phone}` : null,
      ``,
      `*Mensagem:*`,
      message,
    ].filter(Boolean).join('\n');
    window.open(`https://wa.me/5531995302006?text=${encodeURIComponent(lines)}`, '_blank');
    setSent(true);
  };

  return (
    <>
      <style>{css + COUNTRY_DROPDOWN_CSS}</style>
      <div className="cp-page">
        <div className="cp-card">

          {/* NAV */}
          <nav className="cp-nav">
            <Link to="/login" className="cp-nav-logo">
              <div className="cp-nav-logo-icon"><HiveLogo size={22}/></div>
              <span className="cp-nav-logo-name"><ScrambleText text="HIVE" /></span>
            </Link>
            <div className="cp-nav-links" />
            <div className="cp-nav-actions">
              <Link to="/login" className="cp-nav-login">Entrar</Link>
              <Link to="/register" className="cp-nav-register">Criar conta</Link>
            </div>
          </nav>

          {/* CORPO */}
          <div className="cp-body">
            <div className="cp-grid-line" style={{left:'33%'}}/>
            <div className="cp-grid-line" style={{left:'50%'}}/>
            <div className="cp-grid-line" style={{left:'67%'}}/>

            {/* ESQUERDO */}
            <div className="cp-left">
              {sent ? (
                <div className="cp-sent">
                  <div className="cp-sent-icon">
                    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                      <path d="M3 9l4 4 8-8" stroke="#2EC8A4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </div>
                  <div className="cp-sent-title">Mensagem enviada!</div>
                  <p className="cp-sent-sub">
                    Sua mensagem foi enviada para nosso WhatsApp. Retornamos em breve em{' '}
                    <strong style={{color:'#D4A820'}}>{email}</strong>.
                  </p>
                  <Link to="/login" className="cp-btn-continue" style={{textDecoration:'none',textAlign:'center',display:'block'}}>
                    Voltar para o login
                  </Link>
                </div>
              ) : (
                <>
                  <h1 className="cp-form-title">
                    Entre em contato<br /><em>conosco</em>
                  </h1>
                  <p className="cp-form-sub">
                    Nossa equipe de suporte está a uma mensagem de distância.
                  </p>

                  <div className="cp-info-items">
                    <div className="cp-info-item">
                      <div className="cp-info-icon">
                        <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                          <rect x="1" y="2.5" width="13" height="10" rx="1.5" stroke="#D4A820" strokeWidth="1.2"/>
                          <path d="M1 5l6.5 4L14 5" stroke="#D4A820" strokeWidth="1.2" strokeLinecap="round"/>
                        </svg>
                      </div>
                      <div>
                        <div className="cp-info-label">E-mail</div>
                        <a href="mailto:suporte@hive.com.br" className="cp-info-value">suporte@hive.com.br</a>
                      </div>
                    </div>
                    <div className="cp-info-item">
                      <div className="cp-info-icon">
                        <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                          <path d="M13 10.8c0 .28-.06.55-.2.82-.13.26-.31.5-.55.7-.4.36-.83.54-1.28.54-.32 0-.66-.08-1.03-.25A10 10 0 0 1 8.2 10.7a17.5 17.5 0 0 1-1.63-1.63 17 17 0 0 1-1.35-1.77c-.43-.63-.77-1.22-1.01-1.76C4.07 5.01 3.94 4.65 3.94 4.3c0-.34.07-.66.21-.95.14-.3.35-.56.63-.79.36-.27.74-.4 1.15-.4.16 0 .32.03.46.1.15.06.28.16.39.3l1.35 1.9c.11.15.2.28.25.41.06.12.09.24.09.35 0 .14-.04.27-.12.4-.08.12-.18.25-.31.37l-.42.44a.3.3 0 0 0-.09.22c0 .04.01.08.03.13.03.05.05.09.07.13.2.36.44.7.72 1.02.29.32.6.63.93.92.3.26.62.5.95.7.04.03.09.05.13.07.05.01.09.02.13.02a.31.31 0 0 0 .22-.1l.42-.41c.13-.12.25-.21.37-.26.12-.06.24-.09.37-.09.1 0 .21.02.32.07.12.05.25.13.38.24l1.94 1.38c.14.1.23.2.28.33.04.12.07.24.07.37z" stroke="#D4A820" strokeWidth="1.1"/>
                        </svg>
                      </div>
                      <div>
                        <div className="cp-info-label">WhatsApp</div>
                        <a href="https://wa.me/5531995302006" target="_blank" rel="noreferrer" className="cp-info-value">
                          +55 (31) 99530-2006
                        </a>
                      </div>
                    </div>
                  </div>

                  <form onSubmit={handleSubmit} noValidate>
                    <div className="cp-fields">
                      <div className="cp-row2">
                        <div>
                          <label className="cp-label">Nome</label>
                          <input className={`cp-input${errs.fname?' err':''}`} type="text" placeholder="Seu nome"
                            value={fname} onChange={e=>{setFname(e.target.value);if(errs.fname)setErrs(p=>({...p,fname:''}));}} autoFocus/>
                          {errs.fname && <div className="cp-field-err">{errs.fname}</div>}
                        </div>
                        <div>
                          <label className="cp-label">Sobrenome</label>
                          <input className="cp-input" type="text" placeholder="Sobrenome"
                            value={lname} onChange={e=>setLname(e.target.value)}/>
                        </div>
                      </div>

                      <div>
                        <label className="cp-label">E-mail</label>
                        <input className={`cp-input${errs.email?' err':''}`} type="email" placeholder="voce@empresa.com"
                          value={email} onChange={e=>{setEmail(e.target.value);if(errs.email)setErrs(p=>({...p,email:''}));}}/>
                        {errs.email && <div className="cp-field-err">{errs.email}</div>}
                      </div>

                      <div>
                        <label className="cp-label">Número de telefone</label>
                        <div className="cp-phone-wrap">
                          <CountrySelector selected={country} onChange={setCountry} />
                          <input className="cp-phone-input" type="tel" placeholder="(11) 9 0000-0000"
                            value={phone} onChange={e=>setPhone(fmtPhone(e.target.value))}
                            autoComplete="off" data-form-type="other"/>
                        </div>
                      </div>

                      <div>
                        <label className="cp-label">Mensagem</label>
                        <textarea className={`cp-input${errs.message?' err':''}`} rows={4}
                          placeholder="Escreva uma dúvida, feedback ou sugestão..."
                          value={message} onChange={e=>{setMessage(e.target.value);if(errs.message)setErrs(p=>({...p,message:''}));}}/>
                        {errs.message && <div className="cp-field-err">{errs.message}</div>}
                      </div>
                    </div>

                    <button type="submit" className="cp-btn-continue">Enviar mensagem</button>
                    <a href="mailto:suporte@hive.com.br" className="cp-email-link">
                      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                        <rect x="0.5" y="1.5" width="11" height="9" rx="1.2" stroke="currentColor" strokeWidth="1"/>
                        <path d="M0.5 3.5l5.5 3.5 5.5-3.5" stroke="currentColor" strokeWidth="1" strokeLinecap="round"/>
                      </svg>
                      suporte@hive.com.br
                    </a>
                  </form>
                </>
              )}
            </div>

            {/* DIREITO — device frame sangra pela direita (igual referência) */}
            <div className="cp-device-area">
              <HexBackground />
              <div className="cp-device-bezel">
                <div className="cp-device-screen">
                  <iframe
                    src="/dashboard"
                    className="cp-dash-iframe"
                    title="HIVE Dashboard"
                    scrolling="no"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* LOGOS */}
          <div className="cp-logos-bar">
            <div className="cp-logos-eyebrow">Confiado por investidores de todo o Brasil</div>
            <div className="cp-logos-row">
              {LOGOS.map(l=><div key={l} className="cp-logo-item">{l}</div>)}
            </div>
          </div>

        </div>
      </div>
    </>
  );
};
