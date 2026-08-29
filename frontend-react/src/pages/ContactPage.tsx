import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';

// ── Slot-machine letter (mesmo efeito do login) ──────────────────────────────
const SLOT_CHARS = ['$','¥','€','%','+','#','8','4','2','1','9','6','3','7','0','5'];
const SlotLetter: React.FC<{ char: string; delay: number }> = ({ char, delay }) => {
  const outerRef = useRef<HTMLSpanElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const chars = [...SLOT_CHARS, char];
  useEffect(() => {
    const outer = outerRef.current;
    const track = trackRef.current;
    if (!outer || !track) return;
    outer.style.opacity = '0';
    const tid = setTimeout(() => {
      const h = outer.getBoundingClientRect().height;
      if (h > 0) {
        outer.style.transition = 'opacity 0.18s ease';
        outer.style.opacity = '1';
        track.style.transition = 'transform 1.1s cubic-bezier(0.16,1,0.3,1)';
        track.style.transform = `translateY(-${(chars.length - 1) * h}px)`;
      }
    }, delay);
    return () => clearTimeout(tid);
  }, [chars.length, delay]);
  return (
    <span ref={outerRef} style={{ overflow:'hidden', display:'inline-block', height:'1em', verticalAlign:'top', lineHeight:1 }}>
      <div ref={trackRef} style={{ lineHeight:1, willChange:'transform' }}>
        {chars.map((c,i) => <span key={i} style={{ display:'block', height:'1em', lineHeight:1, textAlign:'center' }}>{c}</span>)}
      </div>
    </span>
  );
};

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
    width: 28px; height: 28px;
    background: #1E1A14;
    border: 1px solid rgba(212,168,32,0.3);
    border-radius: 7px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .cp-nav-logo-name {
    font-size: 0.95rem;
    font-weight: 900;
    color: #D4A820;
    letter-spacing: 0.06em;
    line-height: 1;
    display: inline-flex;
    align-items: flex-start;
    gap: 0;
    font-variant-numeric: tabular-nums;
  }

  .cp-nav-links { display:flex; align-items:center; gap:20px; flex:1; }
  .cp-nav-link {
    font-size: 0.82rem;
    font-weight: 500;
    color: rgba(243,239,234,0.5);
    text-decoration: none;
    display: flex;
    align-items: center;
    gap: 3px;
    white-space: nowrap;
    transition: color 0.15s;
  }
  .cp-nav-link:hover { color: rgba(243,239,234,0.85); }
  .cp-nav-link.active {
    color: #F3EFEA;
    font-weight: 700;
    text-decoration: underline;
    text-underline-offset: 3px;
    text-decoration-color: rgba(212,168,32,0.5);
  }

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

  /* Badge "Contato" — estilo Glimpse */
  .cp-badge {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 5px 12px;
    border: 1px solid rgba(212,168,32,0.25);
    border-radius: 99px;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: rgba(212,168,32,0.8);
    margin-bottom: 18px;
  }
  .cp-badge svg { flex-shrink:0; }

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
  .cp-info-text {}
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

  /* Campo telefone com bandeira — estilo Glimpse */
  .cp-phone-wrap {
    display: flex;
    border: 1px solid rgba(243,239,234,0.1);
    border-radius: 8px;
    overflow: hidden;
    transition: border-color 0.15s, box-shadow 0.15s;
  }
  .cp-phone-wrap:focus-within { border-color:rgba(212,168,32,0.5); box-shadow:0 0 0 3px rgba(212,168,32,0.07); }
  .cp-phone-prefix {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 10px 12px;
    background: rgba(243,239,234,0.06);
    border-right: 1px solid rgba(243,239,234,0.1);
    font-family: inherit;
    font-size: 0.82rem;
    color: rgba(243,239,234,0.6);
    flex-shrink: 0;
    white-space: nowrap;
  }
  .cp-phone-input {
    flex: 1;
    padding: 10px 13px;
    background: rgba(243,239,234,0.04);
    color: #F3EFEA;
    border: none;
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

  /* ── DIREITO — device ── */
  .cp-device-area {
    display: flex;
    align-items: center;
    padding: 32px 0 32px 20px;
    position: relative;
    z-index: 1;
    overflow: hidden;
  }
  .cp-device-frame {
    width: 100%;
    background: #1A1714;
    border-radius: 14px 0 0 14px;
    overflow: hidden;
    box-shadow: -8px 0 60px rgba(0,0,0,0.3), 0 20px 60px rgba(0,0,0,0.3);
    margin-right: -2px;
    min-height: 460px;
    display: flex;
    flex-direction: column;
    animation: cp-up 0.5s cubic-bezier(.16,1,.3,1) 0.1s both;
  }
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

  .cp-dev-body { display:grid; grid-template-columns:130px 1fr; flex:1; overflow:hidden; }
  .cp-dev-sidebar { background:#100D0A; border-right:1px solid rgba(255,255,255,0.05); padding:12px 8px; display:flex; flex-direction:column; gap:2px; }
  .cp-dev-sb-section { font-size:0.46rem; font-weight:700; letter-spacing:0.1em; text-transform:uppercase; color:rgba(243,239,234,0.2); padding:8px 8px 4px; }
  .cp-dev-sb-item { display:flex; align-items:center; gap:6px; padding:5px 8px; border-radius:5px; font-size:0.58rem; font-weight:500; color:rgba(243,239,234,0.38); }
  .cp-dev-sb-item.active { background:rgba(212,168,32,0.1); color:#D4A820; font-weight:700; }
  .cp-dev-sb-dot { width:5px; height:5px; border-radius:50%; background:currentColor; opacity:0.5; flex-shrink:0; }
  .cp-dev-sb-item.active .cp-dev-sb-dot { opacity:1; }
  .cp-dev-sb-divider { height:1px; background:rgba(255,255,255,0.05); margin:6px 0; }

  .cp-dev-main { padding:14px 16px; overflow:hidden; display:flex; flex-direction:column; gap:10px; }
  .cp-dev-header { display:flex; align-items:flex-start; justify-content:space-between; }
  .cp-dev-page-title { font-size:0.82rem; font-weight:800; color:#F3EFEA; letter-spacing:-0.02em; margin-bottom:1px; }
  .cp-dev-page-sub { font-size:0.5rem; color:rgba(243,239,234,0.32); }
  .cp-dev-date-tabs { display:flex; gap:2px; background:rgba(255,255,255,0.05); border-radius:5px; padding:2px; }
  .cp-dev-dt { font-size:0.48rem; font-weight:600; padding:3px 7px; border-radius:3px; color:rgba(243,239,234,0.38); }
  .cp-dev-dt.active { background:rgba(212,168,32,0.15); color:#D4A820; }

  .cp-dev-kpis { display:grid; grid-template-columns:1fr 1fr 1fr; gap:6px; }
  .cp-dev-kpi { background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06); border-radius:7px; padding:8px 10px; }
  .cp-dev-kpi-label { font-size:0.48rem; color:rgba(243,239,234,0.32); font-weight:600; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:4px; }
  .cp-dev-kpi-val { font-size:0.82rem; font-weight:900; color:#F3EFEA; letter-spacing:-0.03em; margin-bottom:2px; font-variant-numeric:tabular-nums; }
  .cp-dev-kpi-delta { font-size:0.48rem; font-weight:700; color:#2EC8A4; }

  .cp-dev-chart { background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); border-radius:7px; padding:10px; flex:1; display:flex; flex-direction:column; gap:6px; min-height:90px; }
  .cp-dev-chart-hdr { display:flex; align-items:center; justify-content:space-between; }
  .cp-dev-chart-title { font-size:0.55rem; font-weight:700; color:rgba(243,239,234,0.45); }
  .cp-dev-chart-svg { flex:1; }

  .cp-dev-list-hdr { display:flex; align-items:center; justify-content:space-between; padding:0 2px; }
  .cp-dev-list-title { font-size:0.58rem; font-weight:700; color:#F3EFEA; }
  .cp-dev-list-count { font-size:0.48rem; background:rgba(255,255,255,0.06); color:rgba(243,239,234,0.38); padding:1px 5px; border-radius:3px; font-weight:600; }
  .cp-dev-rows { display:flex; flex-direction:column; gap:3px; }
  .cp-dev-row { display:flex; align-items:center; gap:7px; padding:5px 7px; border-radius:5px; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.04); }
  .cp-dev-row-av { width:18px; height:18px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:0.42rem; font-weight:800; color:white; flex-shrink:0; }
  .cp-dev-row-name { flex:1; min-width:0; }
  .cp-dev-row-nm { font-size:0.53rem; font-weight:600; color:#F3EFEA; }
  .cp-dev-row-em { font-size:0.46rem; color:rgba(243,239,234,0.28); }
  .cp-dev-row-date { font-size:0.46rem; color:rgba(243,239,234,0.28); flex-shrink:0; }
  .cp-dev-row-val  { font-size:0.53rem; font-weight:700; color:#D4A820; flex-shrink:0; font-variant-numeric:tabular-nums; }

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
    .cp-nav-links { display:none; }
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

function DashChart() {
  const pts:number[][] = [[0,72],[18,60],[28,68],[38,48],[58,55],[68,38],[78,50],[98,32],[108,42],[128,28],[138,35],[158,22],[168,30],[178,14],[188,8]];
  const line = pts.map(([x,y],i)=>`${i===0?'M':'L'}${x},${y}`).join(' ');
  const fill = line+` L${pts[pts.length-1][0]},72 L0,72 Z`;
  return (
    <svg viewBox="0 0 200 80" className="cp-dev-chart-svg" preserveAspectRatio="none">
      <defs>
        <linearGradient id="dag2" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#D4A820" stopOpacity="0.22"/>
          <stop offset="100%" stopColor="#D4A820" stopOpacity="0"/>
        </linearGradient>
      </defs>
      {[0,24,48,72].map(y=><line key={y} x1="0" y1={y} x2="200" y2={y} stroke="rgba(255,255,255,0.04)" strokeWidth="0.5"/>)}
      <path d={fill} fill="url(#dag2)"/>
      <path d={line} fill="none" stroke="#D4A820" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
      <circle cx={pts[pts.length-1][0]} cy={pts[pts.length-1][1]} r="2.5" fill="#D4A820"/>
      {['Jan','Mar','Mai','Jul','Set'].map((l,i)=>(
        <text key={l} x={(i/4)*196+2} y="79" fontSize="5.5" fill="rgba(243,239,234,0.22)" textAnchor="middle" fontFamily="Satoshi,system-ui">{l}</text>
      ))}
    </svg>
  );
}

const ROWS = [
  { name:'Nikolas G.',  email:'nikolas@hive.com.br', date:'Abr 3, 2025', val:'R$64,00', color:'#7C3AED' },
  { name:'Amélie L.',   email:'amelie@hive.com.br',  date:'Abr 3, 2025', val:'R$64,00', color:'#D4A820' },
  { name:'Ammar F.',    email:'ammar@hive.com.br',   date:'Abr 3, 2025', val:'R$18,00', color:'#2EC8A4' },
  { name:'Caitlyn K.',  email:'caitlyn@hive.com.br', date:'Abr 4, 2025', val:'R$64,00', color:'#F07A64' },
];

const LOGOS = ['Nubank','XP Inc.','BTG Pactual','Itaú','Bradesco','Clear','Rico','Avenue','Inter','C6 Bank'];

// ── Países com código DDI e emoji de bandeira ─────────────────────────────────
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
  .cp-country-wrap {
    position: relative;
  }
  .cp-country-btn {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 10px 12px;
    background: rgba(243,239,234,0.06);
    border-right: 1px solid rgba(243,239,234,0.1);
    font-family: inherit;
    font-size: 0.82rem;
    color: rgba(243,239,234,0.6);
    flex-shrink: 0;
    white-space: nowrap;
    cursor: pointer;
    border: none;
    outline: none;
    transition: background 0.15s;
    height: 100%;
    border-right: 1px solid rgba(243,239,234,0.1);
  }
  .cp-country-btn:hover { background: rgba(243,239,234,0.1); color: #F3EFEA; }

  .cp-country-dropdown {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    width: 240px;
    background: #1E1A14;
    border: 1px solid rgba(212,168,32,0.2);
    border-radius: 10px;
    box-shadow: 0 12px 40px rgba(0,0,0,0.5);
    z-index: 100;
    overflow: hidden;
    animation: cp-up 0.15s cubic-bezier(.16,1,.3,1) both;
  }
  .cp-country-search {
    width: 100%;
    padding: 10px 13px;
    background: rgba(243,239,234,0.04);
    color: #F3EFEA;
    border: none;
    border-bottom: 1px solid rgba(243,239,234,0.08);
    font-family: inherit;
    font-size: 0.82rem;
    outline: none;
  }
  .cp-country-search::placeholder { color: rgba(243,239,234,0.25); }
  .cp-country-list {
    max-height: 220px;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: rgba(212,168,32,0.2) transparent;
  }
  .cp-country-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 13px;
    cursor: pointer;
    font-size: 0.8rem;
    color: rgba(243,239,234,0.7);
    transition: background 0.1s;
  }
  .cp-country-item:hover { background: rgba(212,168,32,0.08); color: #F3EFEA; }
  .cp-country-item.sel  { background: rgba(212,168,32,0.12); color: #D4A820; }
  .cp-country-flag { font-size: 1rem; flex-shrink: 0; }
  .cp-country-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .cp-country-dial { color: rgba(243,239,234,0.4); font-size: 0.75rem; flex-shrink: 0; font-variant-numeric: tabular-nums; }
  .cp-country-item.sel .cp-country-dial { color: rgba(212,168,32,0.7); }
`;

const CountrySelector: React.FC<{
  selected: typeof COUNTRIES[0];
  onChange: (c: typeof COUNTRIES[0]) => void;
}> = ({ selected, onChange }) => {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const wrapRef = useRef<HTMLDivElement>(null);

  const filtered = COUNTRIES.filter(c =>
    c.name.toLowerCase().includes(search.toLowerCase()) ||
    c.dial.includes(search)
  );

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
        setSearch('');
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <div className="cp-country-wrap" ref={wrapRef}>
      <button type="button" className="cp-country-btn" onClick={() => setOpen(o => !o)}>
        <span style={{ fontSize: '1rem' }}>{selected.flag}</span>
        {selected.dial}
        <ChevronDown size={9} />
      </button>
      {open && (
        <div className="cp-country-dropdown">
          <input
            className="cp-country-search"
            placeholder="Buscar país ou código..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            autoFocus
          />
          <div className="cp-country-list">
            {filtered.map(c => (
              <div
                key={c.code}
                className={`cp-country-item${c.code === selected.code ? ' sel' : ''}`}
                onClick={() => { onChange(c); setOpen(false); setSearch(''); }}
              >
                <span className="cp-country-flag">{c.flag}</span>
                <span className="cp-country-name">{c.name}</span>
                <span className="cp-country-dial">{c.dial}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export const ContactPage: React.FC = () => {
  const [fname, setFname]   = useState('');
  const [lname, setLname]   = useState('');
  const [email, setEmail]   = useState('');
  const [phone, setPhone]   = useState('');
  const [message, setMessage] = useState('');
  const [errs, setErrs]     = useState({ fname:'', email:'', message:'' });
  const [sent, setSent]     = useState(false);
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
    if (validate()) setSent(true);
  };

  return (
    <>
      <style>{css + COUNTRY_DROPDOWN_CSS}</style>
      <div className="cp-page">
        <div className="cp-card">

          {/* NAV */}
          <nav className="cp-nav">
            <Link to="/login" className="cp-nav-logo">
              <div className="cp-nav-logo-icon"><HiveLogo size={16}/></div>
              <span className="cp-nav-logo-name">
                {'HIVE'.split('').map((ch,i) => <SlotLetter key={i} char={ch} delay={300+i*110}/>)}
              </span>
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
                    Nossa equipe responderá em até 24 horas úteis em{' '}
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

                  {/* Info items estilo Glimpse */}
                  <div className="cp-info-items">
                    <div className="cp-info-item">
                      <div className="cp-info-icon">
                        <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                          <rect x="1" y="2.5" width="13" height="10" rx="1.5" stroke="#D4A820" strokeWidth="1.2"/>
                          <path d="M1 5l6.5 4L14 5" stroke="#D4A820" strokeWidth="1.2" strokeLinecap="round"/>
                        </svg>
                      </div>
                      <div className="cp-info-text">
                        <div className="cp-info-label">E-mail:</div>
                        <a href="mailto:suporte@hive.com.br" className="cp-info-value">suporte@hive.com.br</a>
                      </div>
                    </div>
                    <div className="cp-info-item">
                      <div className="cp-info-icon">
                        <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                          <path d="M13 10.8c0 .28-.06.55-.2.82-.13.26-.31.5-.55.7-.4.36-.83.54-1.28.54-.32 0-.66-.08-1.03-.25A10 10 0 0 1 8.2 10.7a17.5 17.5 0 0 1-1.63-1.63 17 17 0 0 1-1.35-1.77c-.43-.63-.77-1.22-1.01-1.76C4.07 5.01 3.94 4.65 3.94 4.3c0-.34.07-.66.21-.95.14-.3.35-.56.63-.79.36-.27.74-.4 1.15-.4.16 0 .32.03.46.1.15.06.28.16.39.3l1.35 1.9c.11.15.2.28.25.41.06.12.09.24.09.35 0 .14-.04.27-.12.4-.08.12-.18.25-.31.37l-.42.44a.3.3 0 0 0-.09.22c0 .04.01.08.03.13.03.05.05.09.07.13.2.36.44.7.72 1.02.29.32.6.63.93.92.3.26.62.5.95.7.04.03.09.05.13.07.05.01.09.02.13.02a.31.31 0 0 0 .22-.1l.42-.41c.13-.12.25-.21.37-.26.12-.06.24-.09.37-.09.1 0 .21.02.32.07.12.05.25.13.38.24l1.94 1.38c.14.1.23.2.28.33.04.12.07.24.07.37z" stroke="#D4A820" strokeWidth="1.1"/>
                        </svg>
                      </div>
                      <div className="cp-info-text">
                        <div className="cp-info-label">Telefone:</div>
                        <a href="tel:+5511999999999" className="cp-info-value">+55 (11) 9 9999-9999</a>
                      </div>
                    </div>
                  </div>

                  {/* Form */}
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
                            value={phone} onChange={e=>setPhone(fmtPhone(e.target.value))}/>
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

            {/* DIREITO — device */}
            <div className="cp-device-area">
              <div className="cp-device-frame">
                <div className="cp-dev-topbar">
                  <div className="cp-dev-logo">
                    <HiveLogo size={12}/>
                    <span className="cp-dev-logo-name">HIVE</span>
                    <span className="cp-dev-version">v1.0</span>
                  </div>
                  <div className="cp-dev-tabs">
                    <div className="cp-dev-tab active">Painel</div>
                    <div className="cp-dev-tab">Carteira</div>
                    <div className="cp-dev-tab">Organizar <span className="cp-dev-tab-badge">4</span></div>
                    <div className="cp-dev-tab">Chat</div>
                  </div>
                  <div className="cp-dev-url">app.hive.com.br</div>
                </div>
                <div className="cp-dev-body">
                  <div className="cp-dev-sidebar">
                    <div className="cp-dev-sb-section">Principal</div>
                    {[{l:'Painel',a:true},{l:'Carteira',a:false},{l:'Objetivos',a:false},{l:'Estratégias',a:false}].map(item=>(
                      <div key={item.l} className={`cp-dev-sb-item${item.a?' active':''}`}>
                        <div className="cp-dev-sb-dot"/>{item.l}
                      </div>
                    ))}
                    <div className="cp-dev-sb-divider"/>
                    <div className="cp-dev-sb-section">Conta</div>
                    {['Configurações','Suporte','Documentação'].map(l=>(
                      <div key={l} className="cp-dev-sb-item"><div className="cp-dev-sb-dot"/>{l}</div>
                    ))}
                  </div>
                  <div className="cp-dev-main">
                    <div className="cp-dev-header">
                      <div>
                        <div className="cp-dev-page-title">Painel</div>
                        <div className="cp-dev-page-sub">Visão geral do seu patrimônio.</div>
                      </div>
                      <div className="cp-dev-date-tabs">
                        <div className="cp-dev-dt active">12 meses</div>
                        <div className="cp-dev-dt">30 dias</div>
                        <div className="cp-dev-dt">7 dias</div>
                        <div className="cp-dev-dt">24h</div>
                      </div>
                    </div>
                    <div className="cp-dev-kpis">
                      {[{label:'Patrimônio',val:'R$88.820',delta:'↑ +15%'},{label:'Rendimento',val:'R$3.604',delta:'↑ +8%'},{label:'Ativos',val:'12',delta:'↑ +2'}].map(k=>(
                        <div key={k.label} className="cp-dev-kpi">
                          <div className="cp-dev-kpi-label">{k.label}</div>
                          <div className="cp-dev-kpi-val">{k.val}</div>
                          <div className="cp-dev-kpi-delta">{k.delta}</div>
                        </div>
                      ))}
                    </div>
                    <div className="cp-dev-chart">
                      <div className="cp-dev-chart-hdr">
                        <div className="cp-dev-chart-title">Evolução patrimonial</div>
                      </div>
                      <DashChart/>
                    </div>
                    <div className="cp-dev-list-hdr">
                      <span className="cp-dev-list-title">Clientes</span>
                      <span className="cp-dev-list-count">1.656</span>
                    </div>
                    <div className="cp-dev-rows">
                      {ROWS.map(r=>(
                        <div key={r.name} className="cp-dev-row">
                          <div className="cp-dev-row-av" style={{background:r.color}}>{r.name[0]}</div>
                          <div className="cp-dev-row-name">
                            <div className="cp-dev-row-nm">{r.name}</div>
                            <div className="cp-dev-row-em">{r.email}</div>
                          </div>
                          <div className="cp-dev-row-date">{r.date}</div>
                          <div className="cp-dev-row-val">{r.val}</div>
                        </div>
                      ))}
                    </div>
                  </div>
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
