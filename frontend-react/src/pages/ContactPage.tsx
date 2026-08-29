import React, { useState } from 'react';
import { Link } from 'react-router-dom';

const css = `
  @import url('https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700,800,900&display=swap');
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  .cp-page {
    font-family: 'Satoshi', system-ui, sans-serif;
    min-height: 100vh;
    background: #F3F4F6;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 28px 20px;
  }

  /* Card externo — igual ao da referência */
  .cp-card {
    width: 100%;
    max-width: 1160px;
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 4px 32px rgba(0,0,0,0.07);
  }

  @keyframes cp-up {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes pulse-dot {
    0%,100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  /* ── NAV BAR — topo do card igual à ref ── */
  .cp-nav {
    display: flex;
    align-items: center;
    padding: 14px 24px;
    border-bottom: 1px solid #E5E7EB;
    gap: 28px;
  }
  .cp-nav-logo {
    display: flex;
    align-items: center;
    gap: 8px;
    text-decoration: none;
    flex-shrink: 0;
  }
  .cp-nav-logo-icon {
    width: 28px; height: 28px;
    background: #111827;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .cp-nav-logo-name {
    font-size: 0.9rem;
    font-weight: 800;
    color: #111827;
    letter-spacing: 0.04em;
  }

  .cp-nav-links {
    display: flex;
    align-items: center;
    gap: 20px;
    flex: 1;
  }
  .cp-nav-link {
    font-size: 0.82rem;
    font-weight: 500;
    color: #374151;
    text-decoration: none;
    display: flex;
    align-items: center;
    gap: 3px;
    white-space: nowrap;
  }
  .cp-nav-link.active {
    color: #111827;
    font-weight: 600;
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .cp-nav-chevron { opacity: 0.5; }

  .cp-nav-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }

  .cp-nav-login {
    padding: 7px 14px;
    background: white;
    color: #111827;
    border: 1px solid #D1D5DB;
    border-radius: 8px;
    font-family: inherit;
    font-size: 0.82rem;
    font-weight: 600;
    cursor: pointer;
    text-decoration: none;
    display: inline-block;
    transition: background 0.15s;
  }
  .cp-nav-login:hover { background: #F9FAFB; }

  .cp-nav-register {
    padding: 7px 14px;
    background: #111827;
    color: white;
    border: none;
    border-radius: 8px;
    font-family: inherit;
    font-size: 0.82rem;
    font-weight: 600;
    cursor: pointer;
    text-decoration: none;
    display: inline-block;
    transition: background 0.15s;
  }
  .cp-nav-register:hover { background: #1F2937; }

  /* ── CORPO — grid 2 colunas ── */
  .cp-body {
    display: grid;
    grid-template-columns: 1fr 1.08fr;
    min-height: 560px;
    position: relative;
    overflow: hidden;
  }

  /* Linhas tracejadas de grade — iguais à ref */
  .cp-grid-line {
    position: absolute;
    top: 0; bottom: 0;
    width: 1px;
    border-left: 1px dashed #E5E7EB;
    pointer-events: none;
    z-index: 0;
  }

  /* ── ESQUERDO — formulário ── */
  .cp-left {
    padding: 52px 48px 48px;
    position: relative;
    z-index: 1;
    animation: cp-up 0.45s cubic-bezier(.16,1,.3,1) both;
  }

  .cp-form-title {
    font-size: 1.75rem;
    font-weight: 800;
    letter-spacing: -0.04em;
    color: #111827;
    line-height: 1.15;
    margin-bottom: 8px;
  }
  .cp-form-title em {
    font-style: italic;
    font-weight: 800;
    color: #111827;
  }
  .cp-form-sub {
    font-size: 0.84rem;
    color: #6B7280;
    line-height: 1.65;
    margin-bottom: 28px;
  }

  .cp-label {
    display: block;
    font-size: 0.78rem;
    font-weight: 500;
    color: #374151;
    margin-bottom: 5px;
  }
  .cp-input {
    width: 100%;
    padding: 9px 12px;
    background: white;
    color: #111827;
    border: 1px solid #D1D5DB;
    border-radius: 8px;
    font-family: inherit;
    font-size: 0.85rem;
    outline: none;
    transition: border-color 0.15s, box-shadow 0.15s;
    resize: none;
  }
  .cp-input::placeholder { color: #9CA3AF; }
  .cp-input:focus { border-color: #111827; box-shadow: 0 0 0 3px rgba(17,24,39,0.07); }
  .cp-input.err { border-color: #EF4444; }
  .cp-field-err { font-size: 0.7rem; color: #EF4444; margin-top: 3px; }

  .cp-row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .cp-fields { display: flex; flex-direction: column; gap: 14px; margin-bottom: 20px; }

  /* Dropdown select estilizado */
  .cp-select-wrap { position: relative; }
  .cp-select {
    width: 100%;
    padding: 9px 32px 9px 12px;
    background: white;
    color: #111827;
    border: 1px solid #D1D5DB;
    border-radius: 8px;
    font-family: inherit;
    font-size: 0.85rem;
    outline: none;
    appearance: none;
    cursor: pointer;
    transition: border-color 0.15s;
  }
  .cp-select:focus { border-color: #111827; }
  .cp-select-arrow {
    position: absolute;
    right: 10px; top: 50%;
    transform: translateY(-50%);
    pointer-events: none;
    color: #6B7280;
  }

  /* Cards de seleção — iguais à ref */
  .cp-sel-cards { display: flex; flex-direction: column; gap: 10px; margin-bottom: 24px; }

  .cp-sel-card {
    border: 1.5px solid #E5E7EB;
    border-radius: 10px;
    padding: 14px 16px;
    cursor: pointer;
    transition: all 0.15s;
    display: flex;
    align-items: center;
    gap: 14px;
    background: white;
    user-select: none;
  }
  .cp-sel-card:hover { border-color: #9CA3AF; }
  .cp-sel-card.sel  { border-color: #111827; }

  .cp-sel-avatars {
    display: flex;
    align-items: center;
    flex-shrink: 0;
  }
  .cp-sel-av {
    width: 26px; height: 26px;
    border-radius: 50%;
    border: 2px solid white;
    margin-right: -7px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
  }
  .cp-sel-av:last-child { margin-right: 0; }

  .cp-sel-info { flex: 1; min-width: 0; }
  .cp-sel-title { font-size: 0.85rem; font-weight: 700; color: #111827; margin-bottom: 1px; }
  .cp-sel-desc  { font-size: 0.74rem; color: #6B7280; }

  .cp-sel-check {
    width: 20px; height: 20px;
    border-radius: 50%;
    border: 1.5px solid #D1D5DB;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: all 0.15s;
  }
  .cp-sel-card.sel .cp-sel-check {
    background: #111827;
    border-color: #111827;
  }

  .cp-btn-continue {
    width: 100%;
    padding: 12px;
    background: #111827;
    color: white;
    border: none;
    border-radius: 8px;
    font-family: inherit;
    font-size: 0.88rem;
    font-weight: 700;
    cursor: pointer;
    transition: background 0.15s;
    margin-bottom: 14px;
    letter-spacing: 0.01em;
  }
  .cp-btn-continue:hover { background: #1F2937; }

  .cp-email-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 0.78rem;
    color: #374151;
    text-decoration: underline;
    text-underline-offset: 3px;
    transition: color 0.15s;
  }
  .cp-email-link:hover { color: #111827; }

  /* ── DIREITO — frame do device (MacBook/tablet) ── */
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
    box-shadow: -8px 0 60px rgba(0,0,0,0.15), 0 20px 60px rgba(0,0,0,0.2);
    margin-right: -2px;
    min-height: 440px;
    display: flex;
    flex-direction: column;
    animation: cp-up 0.5s cubic-bezier(.16,1,.3,1) 0.1s both;
  }

  /* Barra superior do device */
  .cp-dev-topbar {
    padding: 10px 16px;
    background: #13110E;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }
  .cp-dev-logo { display: flex; align-items: center; gap: 6px; }
  .cp-dev-logo-name { font-size: 0.7rem; font-weight: 800; color: #D4A820; letter-spacing: 0.06em; }
  .cp-dev-version {
    font-size: 0.55rem;
    background: rgba(212,168,32,0.15);
    color: rgba(212,168,32,0.7);
    padding: 1px 5px;
    border-radius: 3px;
    font-weight: 700;
    letter-spacing: 0.04em;
  }
  .cp-dev-tabs {
    display: flex;
    gap: 0;
    margin-left: 16px;
    border-bottom: none;
  }
  .cp-dev-tab {
    font-size: 0.65rem;
    font-weight: 600;
    color: rgba(243,239,234,0.35);
    padding: 4px 10px;
    cursor: default;
    border-bottom: 2px solid transparent;
  }
  .cp-dev-tab.active {
    color: #F3EFEA;
    border-bottom-color: #D4A820;
  }
  .cp-dev-tab-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 14px; height: 14px;
    border-radius: 4px;
    background: #D4A820;
    color: #0A0800;
    font-size: 0.5rem;
    font-weight: 800;
    margin-left: 4px;
  }
  .cp-dev-url {
    flex: 1;
    text-align: right;
    font-size: 0.55rem;
    color: rgba(243,239,234,0.2);
    font-weight: 500;
  }

  /* Layout do dashboard dentro do device */
  .cp-dev-body {
    display: grid;
    grid-template-columns: 130px 1fr;
    flex: 1;
    overflow: hidden;
  }

  /* Sidebar do dashboard */
  .cp-dev-sidebar {
    background: #100D0A;
    border-right: 1px solid rgba(255,255,255,0.05);
    padding: 12px 8px;
    display: flex;
    flex-direction: column;
    gap: 2px;
    overflow: hidden;
  }
  .cp-dev-sb-section {
    font-size: 0.48rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.2);
    padding: 8px 8px 4px;
  }
  .cp-dev-sb-item {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 5px 8px;
    border-radius: 5px;
    font-size: 0.6rem;
    font-weight: 500;
    color: rgba(243,239,234,0.4);
    cursor: default;
  }
  .cp-dev-sb-item.active {
    background: rgba(212,168,32,0.1);
    color: #D4A820;
    font-weight: 700;
  }
  .cp-dev-sb-dot {
    width: 5px; height: 5px;
    border-radius: 50%;
    background: currentColor;
    opacity: 0.5;
    flex-shrink: 0;
  }
  .cp-dev-sb-item.active .cp-dev-sb-dot { opacity: 1; }
  .cp-dev-sb-divider {
    height: 1px;
    background: rgba(255,255,255,0.05);
    margin: 6px 0;
  }
  .cp-dev-sb-bottom {
    margin-top: auto;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  /* Main content do dashboard */
  .cp-dev-main {
    padding: 14px 16px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  /* Header do dashboard */
  .cp-dev-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
  }
  .cp-dev-page-title {
    font-size: 0.82rem;
    font-weight: 800;
    color: #F3EFEA;
    letter-spacing: -0.02em;
    margin-bottom: 1px;
  }
  .cp-dev-page-sub {
    font-size: 0.52rem;
    color: rgba(243,239,234,0.35);
  }
  .cp-dev-date-tabs {
    display: flex;
    gap: 2px;
    background: rgba(255,255,255,0.05);
    border-radius: 5px;
    padding: 2px;
  }
  .cp-dev-dt {
    font-size: 0.5rem;
    font-weight: 600;
    padding: 3px 7px;
    border-radius: 3px;
    color: rgba(243,239,234,0.4);
    cursor: default;
  }
  .cp-dev-dt.active {
    background: rgba(212,168,32,0.15);
    color: #D4A820;
  }

  /* KPIs */
  .cp-dev-kpis { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; }
  .cp-dev-kpi {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 7px;
    padding: 8px 10px;
  }
  .cp-dev-kpi-label {
    font-size: 0.5rem;
    color: rgba(243,239,234,0.35);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 4px;
  }
  .cp-dev-kpi-val {
    font-size: 0.82rem;
    font-weight: 900;
    color: #F3EFEA;
    letter-spacing: -0.03em;
    margin-bottom: 2px;
    font-variant-numeric: tabular-nums;
  }
  .cp-dev-kpi-delta {
    font-size: 0.5rem;
    font-weight: 700;
    color: #2EC8A4;
    display: flex;
    align-items: center;
    gap: 2px;
  }

  /* Gráfico */
  .cp-dev-chart {
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 7px;
    padding: 10px;
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-height: 100px;
  }
  .cp-dev-chart-hdr {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .cp-dev-chart-title {
    font-size: 0.58rem;
    font-weight: 700;
    color: rgba(243,239,234,0.5);
  }
  .cp-dev-chart-svg { flex: 1; }

  /* Lista de clientes/ativos */
  .cp-dev-list-hdr {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 2px;
  }
  .cp-dev-list-title {
    font-size: 0.6rem;
    font-weight: 700;
    color: #F3EFEA;
  }
  .cp-dev-list-count {
    font-size: 0.5rem;
    background: rgba(255,255,255,0.06);
    color: rgba(243,239,234,0.4);
    padding: 1px 5px;
    border-radius: 3px;
    font-weight: 600;
  }
  .cp-dev-rows { display: flex; flex-direction: column; gap: 3px; }
  .cp-dev-row {
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 5px 7px;
    border-radius: 5px;
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.04);
  }
  .cp-dev-row-av {
    width: 18px; height: 18px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.44rem;
    font-weight: 800;
    color: white;
    flex-shrink: 0;
  }
  .cp-dev-row-name {
    flex: 1;
    min-width: 0;
  }
  .cp-dev-row-nm { font-size: 0.55rem; font-weight: 600; color: #F3EFEA; }
  .cp-dev-row-em { font-size: 0.48rem; color: rgba(243,239,234,0.3); }
  .cp-dev-row-date { font-size: 0.48rem; color: rgba(243,239,234,0.3); flex-shrink: 0; }
  .cp-dev-row-val  { font-size: 0.55rem; font-weight: 700; color: #D4A820; flex-shrink: 0; font-variant-numeric: tabular-nums; }

  /* ── LOGOS BAR — iguais à ref ── */
  .cp-logos-bar {
    border-top: 1px solid #E5E7EB;
    padding: 18px 32px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .cp-logos-eyebrow {
    text-align: center;
    font-size: 0.72rem;
    color: #9CA3AF;
    font-weight: 500;
  }
  .cp-logos-row {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 28px;
    flex-wrap: wrap;
  }
  .cp-logo-item {
    font-size: 0.75rem;
    font-weight: 700;
    color: #9CA3AF;
    letter-spacing: 0.02em;
    opacity: 0.7;
    display: flex;
    align-items: center;
    gap: 5px;
  }

  /* Sucesso */
  .cp-sent {
    display: flex; flex-direction: column; align-items: flex-start;
    animation: cp-up 0.45s cubic-bezier(.16,1,.3,1) both;
  }
  .cp-sent-icon {
    width: 44px; height: 44px; border-radius: 50%;
    background: #ECFDF5; border: 1px solid #6EE7B7;
    display: flex; align-items: center; justify-content: center; margin-bottom: 18px;
  }
  .cp-sent-title { font-size: 1.5rem; font-weight: 800; color: #111827; letter-spacing: -0.03em; margin-bottom: 8px; }
  .cp-sent-sub { font-size: 0.82rem; color: #6B7280; line-height: 1.7; max-width: 320px; margin-bottom: 24px; }

  @media (max-width: 860px) {
    .cp-body { grid-template-columns: 1fr; }
    .cp-device-area { display: none; }
    .cp-left { padding: 36px 24px; }
    .cp-nav-links { display: none; }
  }
`;

function HiveLogo({ size = 16, light = false }: { size?: number; light?: boolean }) {
  if (light) {
    return (
      <svg width={size} height={Math.round(size * 1.11)} viewBox="0 0 180 200" fill="none">
        <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="rgba(255,255,255,0.3)"/>
        <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="white"/>
        <polygon points="100,16 110,22 110,178 100,184" fill="rgba(0,0,0,0.2)"/>
      </svg>
    );
  }
  return (
    <svg width={size} height={Math.round(size * 1.11)} viewBox="0 0 180 200" fill="none">
      <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="#7A5002"/>
      <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="#D4A820"/>
      <polygon points="100,16 110,22 110,178 100,184" fill="#090500"/>
    </svg>
  );
}

function ChevronDown({ size = 10 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 10 10" fill="none">
      <path d="M2 3.5 5 6.5l3-3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
      <path d="M2 5l2.5 2.5 3.5-4" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

function DashChart() {
  // Pontos do gráfico mock — área sob a curva
  const pts = [[0,72],[8,60],[18,68],[28,48],[38,55],[48,38],[58,50],[68,32],[78,42],[88,28],[98,35],[108,22],[118,30],[128,18],[138,25],[148,14],[158,20],[168,10],[178,16],[188,8]];
  const W = 200; const H = 60;
  const line = pts.map(([x,y], i) => `${i===0?'M':'L'}${x},${y}`).join(' ');
  const fill = line + ` L${pts[pts.length-1][0]},${H} L0,${H} Z`;
  const xLabels = ['Jan','Mar','Mai','Jul','Set'];
  return (
    <svg viewBox={`0 0 ${W} ${H+16}`} className="cp-dev-chart-svg" preserveAspectRatio="none">
      <defs>
        <linearGradient id="dag" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#D4A820" stopOpacity="0.25"/>
          <stop offset="100%" stopColor="#D4A820" stopOpacity="0"/>
        </linearGradient>
      </defs>
      {/* Grid horizontais */}
      {[0,20,40,60].map(y => (
        <line key={y} x1="0" y1={y} x2={W} y2={y} stroke="rgba(255,255,255,0.04)" strokeWidth="0.5"/>
      ))}
      <path d={fill} fill="url(#dag)"/>
      <path d={line} fill="none" stroke="#D4A820" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
      {/* Ponto final destacado */}
      <circle cx={pts[pts.length-1][0]} cy={pts[pts.length-1][1]} r="2.5" fill="#D4A820"/>
      <circle cx={pts[pts.length-1][0]} cy={pts[pts.length-1][1]} r="4" fill="rgba(212,168,32,0.2)"/>
      {/* Labels X */}
      {xLabels.map((l, i) => (
        <text key={l} x={(i/(xLabels.length-1))*(W-4)+2} y={H+12} fontSize="6" fill="rgba(243,239,234,0.25)" textAnchor="middle" fontFamily="Satoshi, system-ui">{l}</text>
      ))}
    </svg>
  );
}

const ROWS = [
  { name: 'Nikolas G.',   email: 'nikolas@hive.com.br', date: 'Abr 3, 2025', val: 'R$64,00', color: '#7C3AED' },
  { name: 'Amélie L.',    email: 'amelie@hive.com.br',  date: 'Abr 3, 2025', val: 'R$64,00', color: '#D4A820' },
  { name: 'Ammar F.',     email: 'ammar@hive.com.br',   date: 'Abr 3, 2025', val: 'R$18,00', color: '#2EC8A4' },
  { name: 'Caitlyn K.',   email: 'caitlyn@hive.com.br', date: 'Abr 4, 2025', val: 'R$64,00', color: '#F07A64' },
];

const SEL_CARDS = [
  {
    avatars: ['#7C3AED','#D4A820','#2EC8A4','#F07A64','#60B0F2'],
    labels:  ['A','B','C','D','E'],
    title: 'Sou um investidor individual',
    desc:  'Quero gerir meu próprio patrimônio.',
  },
  {
    avatars: ['#F07A64','#ECB040','#2EC8A4'],
    labels:  ['X','Y','Z'],
    title: 'Faço parte de uma empresa',
    desc:  'Preciso de gestão multiusuário.',
  },
];

const LOGOS = [
  { name: 'Nubank' }, { name: 'XP Inc.' }, { name: 'BTG Pactual' },
  { name: 'Itaú' }, { name: 'Bradesco' }, { name: 'Clear' },
  { name: 'Rico' }, { name: 'Avenue' }, { name: 'Inter' }, { name: 'C6 Bank' },
];

export const ContactPage: React.FC = () => {
  const [fname, setFname]   = useState('');
  const [lname, setLname]   = useState('');
  const [email, setEmail]   = useState('');
  const [subject, setSubject] = useState('');
  const [selCard, setSelCard] = useState(0);
  const [errs, setErrs]     = useState({ fname: '', email: '' });
  const [sent, setSent]     = useState(false);

  const validate = () => {
    const e = { fname: '', email: '' };
    if (!fname.trim()) e.fname = 'Preencha seu nome';
    if (!email.trim()) e.email = 'Preencha o e-mail';
    else if (!/\S+@\S+\.\S+/.test(email)) e.email = 'E-mail inválido';
    setErrs(e);
    return !Object.values(e).some(Boolean);
  };

  const handleSubmit = (ev: React.FormEvent) => {
    ev.preventDefault();
    if (validate()) setSent(true);
  };

  return (
    <>
      <style>{css}</style>
      <div className="cp-page">
        <div className="cp-card">

          {/* ── NAV ── */}
          <nav className="cp-nav">
            <Link to="/login" className="cp-nav-logo">
              <div className="cp-nav-logo-icon">
                <HiveLogo size={16} light />
              </div>
              <span className="cp-nav-logo-name">HIVE</span>
            </Link>

            <div className="cp-nav-links">
              {['Produto','Preços','Recursos','Blog'].map(l => (
                <a key={l} href="#" className="cp-nav-link">
                  {l} <span className="cp-nav-chevron"><ChevronDown size={9}/></span>
                </a>
              ))}
              <a href="#" className="cp-nav-link active">Contato</a>
            </div>

            <div className="cp-nav-actions">
              <Link to="/login" className="cp-nav-login">Entrar</Link>
              <Link to="/register" className="cp-nav-register">Criar conta</Link>
            </div>
          </nav>

          {/* ── CORPO ── */}
          <div className="cp-body">
            {/* Linhas de grade tracejadas */}
            <div className="cp-grid-line" style={{ left: '33%' }} />
            <div className="cp-grid-line" style={{ left: '50%' }} />
            <div className="cp-grid-line" style={{ left: '67%' }} />

            {/* ESQUERDO */}
            <div className="cp-left">
              {sent ? (
                <div className="cp-sent">
                  <div className="cp-sent-icon">
                    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                      <path d="M3 9l4 4 8-8" stroke="#059669" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </div>
                  <div className="cp-sent-title">Mensagem enviada!</div>
                  <p className="cp-sent-sub">
                    Nossa equipe responderá em até 24 horas úteis em{' '}
                    <strong>{email}</strong>.
                  </p>
                  <Link to="/login" className="cp-btn-continue" style={{ textDecoration: 'none', textAlign: 'center', display: 'block' }}>
                    Voltar para o login
                  </Link>
                </div>
              ) : (
                <>
                  <h1 className="cp-form-title">
                    Entre em contato<br /><em>conosco</em>
                  </h1>
                  <p className="cp-form-sub">
                    Pronto para começar? Vamos conversar sobre como podemos te ajudar.
                  </p>

                  <form onSubmit={handleSubmit} noValidate>
                    <div className="cp-fields">
                      <div className="cp-row2">
                        <div>
                          <label className="cp-label">Nome</label>
                          <input className={`cp-input${errs.fname?' err':''}`} type="text" placeholder="Seu nome"
                            value={fname} onChange={e => { setFname(e.target.value); if(errs.fname) setErrs(p=>({...p,fname:''})); }} autoFocus/>
                          {errs.fname && <div className="cp-field-err">{errs.fname}</div>}
                        </div>
                        <div>
                          <label className="cp-label">Sobrenome</label>
                          <input className="cp-input" type="text" placeholder="Sobrenome"
                            value={lname} onChange={e => setLname(e.target.value)}/>
                        </div>
                      </div>

                      <div>
                        <label className="cp-label">E-mail</label>
                        <input className={`cp-input${errs.email?' err':''}`} type="email" placeholder="voce@empresa.com"
                          value={email} onChange={e => { setEmail(e.target.value); if(errs.email) setErrs(p=>({...p,email:''})); }}/>
                        {errs.email && <div className="cp-field-err">{errs.email}</div>}
                      </div>

                      <div>
                        <label className="cp-label">Assunto</label>
                        <div className="cp-select-wrap">
                          <select className="cp-select" value={subject} onChange={e => setSubject(e.target.value)}>
                            <option value="">Selecione um assunto...</option>
                            <option>Dúvida sobre a conta</option>
                            <option>Problema técnico</option>
                            <option>Parceria comercial</option>
                            <option>Imprensa</option>
                            <option>Outro</option>
                          </select>
                          <span className="cp-select-arrow"><ChevronDown size={12}/></span>
                        </div>
                      </div>
                    </div>

                    {/* Cards de seleção — iguais à ref */}
                    <div className="cp-sel-cards">
                      {SEL_CARDS.map((card, idx) => (
                        <div key={idx} className={`cp-sel-card${selCard===idx?' sel':''}`}
                          onClick={() => setSelCard(idx)}>
                          <div className="cp-sel-avatars">
                            {card.avatars.map((color, i) => (
                              <div key={i} className="cp-sel-av" style={{ background: color }}>
                                {card.labels[i]}
                              </div>
                            ))}
                          </div>
                          <div className="cp-sel-info">
                            <div className="cp-sel-title">{card.title}</div>
                            <div className="cp-sel-desc">{card.desc}</div>
                          </div>
                          <div className="cp-sel-check">
                            {selCard === idx && <CheckIcon />}
                          </div>
                        </div>
                      ))}
                    </div>

                    <button type="submit" className="cp-btn-continue">Continuar</button>

                    <a href="mailto:suporte@hive.com.br" className="cp-email-link">
                      <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
                        <rect x="1" y="2.5" width="11" height="8" rx="1.2" stroke="currentColor" strokeWidth="1.1"/>
                        <path d="M1 4l5.5 3.5L12 4" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/>
                      </svg>
                      suporte@hive.com.br
                    </a>
                  </form>
                </>
              )}
            </div>

            {/* DIREITO — device frame */}
            <div className="cp-device-area">
              <div className="cp-device-frame">
                {/* Topbar do app */}
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

                {/* Dashboard body */}
                <div className="cp-dev-body">
                  {/* Sidebar */}
                  <div className="cp-dev-sidebar">
                    <div className="cp-dev-sb-section">Principal</div>
                    {[
                      { label: 'Painel', active: true },
                      { label: 'Carteira', active: false },
                      { label: 'Objetivos', active: false },
                      { label: 'Estratégias', active: false },
                    ].map(item => (
                      <div key={item.label} className={`cp-dev-sb-item${item.active?' active':''}`}>
                        <div className="cp-dev-sb-dot"/>
                        {item.label}
                      </div>
                    ))}
                    <div className="cp-dev-sb-divider"/>
                    <div className="cp-dev-sb-section">Conta</div>
                    {['Configurações','Suporte','Documentação'].map(l => (
                      <div key={l} className="cp-dev-sb-item">
                        <div className="cp-dev-sb-dot"/>
                        {l}
                      </div>
                    ))}
                  </div>

                  {/* Main */}
                  <div className="cp-dev-main">
                    {/* Header */}
                    <div className="cp-dev-header">
                      <div>
                        <div className="cp-dev-page-title">Painel</div>
                        <div className="cp-dev-page-sub">Aqui está uma visão geral do seu patrimônio.</div>
                      </div>
                      <div className="cp-dev-date-tabs">
                        <div className="cp-dev-dt active">12 meses</div>
                        <div className="cp-dev-dt">30 dias</div>
                        <div className="cp-dev-dt">7 dias</div>
                        <div className="cp-dev-dt">24h</div>
                      </div>
                    </div>

                    {/* KPIs */}
                    <div className="cp-dev-kpis">
                      {[
                        { label: 'Patrimônio', val: 'R$88.820', delta: '+15%' },
                        { label: 'Rendimento', val: 'R$3.604',  delta: '+8%'  },
                        { label: 'Ativos',     val: '12',       delta: '+2'   },
                      ].map(k => (
                        <div key={k.label} className="cp-dev-kpi">
                          <div className="cp-dev-kpi-label">{k.label}</div>
                          <div className="cp-dev-kpi-val">{k.val}</div>
                          <div className="cp-dev-kpi-delta">↑ {k.delta}</div>
                        </div>
                      ))}
                    </div>

                    {/* Chart */}
                    <div className="cp-dev-chart">
                      <div className="cp-dev-chart-hdr">
                        <div className="cp-dev-chart-title">Evolução patrimonial</div>
                      </div>
                      <DashChart />
                    </div>

                    {/* Lista */}
                    <div className="cp-dev-list-hdr">
                      <span className="cp-dev-list-title">Clientes</span>
                      <span className="cp-dev-list-count">1.656</span>
                    </div>
                    <div className="cp-dev-rows">
                      {ROWS.map(r => (
                        <div key={r.name} className="cp-dev-row">
                          <div className="cp-dev-row-av" style={{ background: r.color }}>{r.name[0]}</div>
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

          {/* ── LOGOS — igual à ref ── */}
          <div className="cp-logos-bar">
            <div className="cp-logos-eyebrow">Confiado por investidores de todo o Brasil</div>
            <div className="cp-logos-row">
              {LOGOS.map(l => (
                <div key={l.name} className="cp-logo-item">{l.name}</div>
              ))}
            </div>
          </div>

        </div>
      </div>
    </>
  );
};
