import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { register, resendVerification } from '../api/auth';
import { describeError } from '../api/errors';

// ─── Utils ───────────────────────────────────────────────────────────────────
const pwStrength = (pw: string) => {
  if (!pw) return 0;
  let s = 0;
  if (pw.length >= 8) s++;
  if (pw.length >= 12) s++;
  if (/[A-Z]/.test(pw)) s++;
  if (/[0-9]/.test(pw)) s++;
  if (/[^A-Za-z0-9]/.test(pw)) s++;
  return s;
};
const PW_LABEL = ['', 'Muito fraca', 'Fraca', 'Média', 'Forte', 'Muito forte'];
const PW_COLOR = ['', '#F07A64', '#F5A94A', '#ECC94B', '#68D391', '#2EC8A4'];

/** Celular em dígitos com DDI, como o backend aceita (10–15 dígitos). */
const phoneE164 = (v: string) => {
  const d = v.replace(/\D/g, '');
  return d.length === 10 || d.length === 11 ? `55${d}` : d;
};

const fmtPhone = (v: string) => {
  const d = v.replace(/\D/g, '').slice(0, 11);
  if (d.length <= 2) return d.length ? `(${d}` : '';
  if (d.length <= 7) return `(${d.slice(0,2)}) ${d.slice(2)}`;
  if (d.length <= 10) return `(${d.slice(0,2)}) ${d.slice(2,6)}-${d.slice(6)}`;
  return `(${d.slice(0,2)}) ${d.slice(2,7)}-${d.slice(7)}`;
};

// ─── Honeycomb canvas ────────────────────────────────────────────────────────
const HoneycombCanvas: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mouse = useRef({ x: -9999, y: -9999 });
  const clicks = useRef<Array<{ x: number; y: number; t: number }>>([]);
  const rafRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;
    const DPR = Math.min(window.devicePixelRatio || 1, 2);
    const SIZE = 22, GAP = 5, SQRT3 = Math.sqrt(3);
    const GLOW_R = 160, WAVE_SPEED = 270, WAVE_WIDTH = 55;
    type Hex = { cx: number; cy: number; phase: number };
    let hexes: Hex[] = [];
    const resize = () => {
      canvas.width = window.innerWidth * DPR;
      canvas.height = window.innerHeight * DPR;
      ctx.scale(DPR, DPR); build();
    };
    const build = () => {
      hexes = [];
      const W = window.innerWidth, H = window.innerHeight;
      const cw = (SIZE + GAP) * 1.5, rh = SQRT3 * (SIZE + GAP * 0.5);
      for (let c = -1; c <= Math.ceil(W / cw) + 1; c++)
        for (let r = -1; r <= Math.ceil(H / rh) + 1; r++)
          hexes.push({ cx: c * cw + SIZE, cy: r * rh + (c % 2 !== 0 ? rh / 2 : 0) + SIZE, phase: Math.random() * Math.PI * 2 });
    };
    resize();
    window.addEventListener('resize', resize);
    const drawHex = (cx: number, cy: number, r: number) => {
      ctx.beginPath();
      for (let i = 0; i < 6; i++) {
        const a = (Math.PI / 3) * i;
        i === 0 ? ctx.moveTo(cx + r * Math.cos(a), cy + r * Math.sin(a)) : ctx.lineTo(cx + r * Math.cos(a), cy + r * Math.sin(a));
      }
      ctx.closePath();
    };
    const t0 = performance.now();
    const frame = (now: number) => {
      const t = (now - t0) / 1000;
      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
      const { x: mx, y: my } = mouse.current;
      clicks.current = clicks.current.filter(c => now - c.t < 1100);
      for (const h of hexes) {
        const dist = Math.hypot(h.cx - mx, h.cy - my);
        const hover = Math.max(0, 1 - dist / GLOW_R);
        let ripple = 0;
        for (const ck of clicks.current) {
          const age = (now - ck.t) / 1000, wave = age * WAVE_SPEED, d = Math.hypot(h.cx - ck.x, h.cy - ck.y);
          ripple = Math.max(ripple, Math.max(0, 1 - Math.abs(d - wave) / WAVE_WIDTH) * Math.max(0, 1 - age * 1.2));
        }
        const breathe = Math.sin(t * 0.65 + h.phase) * 0.5 + 0.5;
        const baseA = 0.012 + breathe * 0.022, total = Math.max(hover, ripple), s = SIZE - GAP * 0.5;
        drawHex(h.cx, h.cy, s);
        ctx.fillStyle = total > 0.02 ? `rgba(212,168,32,${total * 0.22})` : `rgba(243,239,234,${baseA * 0.38})`;
        ctx.fill();
        drawHex(h.cx, h.cy, s);
        ctx.strokeStyle = total > 0.02 ? `rgba(212,168,32,${0.07 + total * 0.75})` : `rgba(243,239,234,${baseA * 1.3})`;
        ctx.lineWidth = total > 0.15 ? 1.2 : 0.55;
        ctx.stroke();
      }
      rafRef.current = requestAnimationFrame(frame);
    };
    rafRef.current = requestAnimationFrame(frame);
    const onMove  = (e: MouseEvent) => { mouse.current = { x: e.clientX, y: e.clientY }; };
    const onClick = (e: MouseEvent) => { clicks.current.push({ x: e.clientX, y: e.clientY, t: performance.now() }); };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('click', onClick);
    return () => {
      window.removeEventListener('resize', resize);
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('click', onClick);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  return <canvas ref={canvasRef} style={{ position: 'fixed', inset: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 0 }} />;
};

// ─── Dados dos bancos ─────────────────────────────────────────────────────────
const BANKS = [
  { name: 'Nubank',   abbr: 'Nu', bg: '#820AD1', fg: '#fff' },
  { name: 'Itaú',     abbr: 'IT', bg: '#EC7000', fg: '#fff' },
  { name: 'Bradesco', abbr: 'BD', bg: '#CC092F', fg: '#fff' },
  { name: 'C6 Bank',  abbr: 'C6', bg: '#2B2D33', fg: '#FFD700' },
  { name: 'Inter',    abbr: 'IN', bg: '#FF7A00', fg: '#fff' },
  { name: 'BTG',      abbr: 'BT', bg: '#1A1A2E', fg: '#D4A820' },
];

// Contexto para o painel esquerdo em cada step
const LEFT_CTX = [
  {
    step: '01',
    title: 'Conta protegida\ndesde o início.',
    bullets: [
      'Senha guardada só como hash bcrypt',
      'Telefone e e-mail usados só para a sua conta',
      'Nenhum dado bancário sem o seu consentimento',
      'Confirmação da conta por e-mail',
    ],
  },
  {
    step: '02',
    title: 'Transparência\nem tudo.',
    bullets: [
      'Tratamento de dados conforme a LGPD',
      'Dados usados somente para análise financeira',
      'Exporte ou apague seus dados quando quiser (Perfil)',
      'Sem anúncios, sem venda de dados',
    ],
  },
  {
    step: '03',
    title: 'Seu banco,\nsua decisão.',
    bullets: [
      'Conexão pelo Open Finance regulado (via Pluggy)',
      'Você escolhe quais contas compartilhar',
      'Revogue o acesso a qualquer momento',
      'Dados nunca repassados a terceiros',
    ],
  },
];

// ─── CSS ─────────────────────────────────────────────────────────────────────
const css = `
  @import url('https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700,800,900&display=swap');
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  .rp-root {
    font-family: 'Satoshi', system-ui, sans-serif;
    min-height: 100vh;
    background: #0C0A08;
    color: #F3EFEA;
    position: relative;
    overflow: hidden;
  }

  .rp-root::after {
    content: '';
    position: fixed;
    width: 520px; height: 520px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(212,168,32,0.05) 0%, transparent 65%);
    transform: translate(var(--cx,-9999px), var(--cy,-9999px)) translate(-50%,-50%);
    pointer-events: none; z-index: 1;
    transition: transform 0.08s linear;
  }

  .rp-wm {
    position: fixed;
    left: 50%; top: 50%;
    transform: translate(-50%, -50%);
    font-size: min(48vw, 480px);
    font-weight: 900;
    letter-spacing: -0.06em;
    color: transparent;
    -webkit-text-stroke: 1px rgba(212,168,32,0.03);
    pointer-events: none; z-index: 0;
    user-select: none; line-height: 1; white-space: nowrap;
  }

  @keyframes rp-up {
    from { opacity: 0; transform: translateY(16px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes rp-pop {
    0%   { opacity: 0; transform: scale(0.5); }
    65%  { transform: scale(1.1); }
    100% { opacity: 1; transform: scale(1); }
  }
  @keyframes shimmer {
    0%   { background-position: 200% center; }
    100% { background-position: -200% center; }
  }

  /* ── Layout 2 colunas ── */
  .rp-layout {
    position: relative;
    z-index: 2;
    display: grid;
    grid-template-columns: 1fr 500px;
    min-height: 100vh;
    max-width: 1280px;
    margin: 0 auto;
    align-items: stretch;
  }

  /* ── ESQUERDO ── */
  .rp-left {
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 40px 32px 40px 56px;
    animation: rp-up 0.6s cubic-bezier(.16,1,.3,1) both;
  }

  .rp-logo {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .rp-logo-word {
    font-size: 1.1rem;
    font-weight: 900;
    letter-spacing: 0.03em;
    color: #D4A820;
  }

  /* Step progress — vertical */
  .rp-step-nav {
    display: flex;
    flex-direction: column;
    gap: 0;
    margin: 22px 0;
  }
  .rp-step-row {
    display: flex;
    align-items: flex-start;
    gap: 16px;
    position: relative;
  }
  .rp-step-col {
    display: flex;
    flex-direction: column;
    align-items: center;
    width: 28px;
    flex-shrink: 0;
  }
  .rp-step-ball {
    width: 28px; height: 28px;
    border-radius: 50%;
    border: 1.5px solid rgba(243,239,234,0.15);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.66rem;
    font-weight: 800;
    color: rgba(243,239,234,0.3);
    background: transparent;
    transition: all 0.35s ease;
    flex-shrink: 0;
  }
  .rp-step-ball.active {
    border-color: #D4A820;
    background: rgba(212,168,32,0.1);
    color: #D4A820;
    box-shadow: 0 0 0 4px rgba(212,168,32,0.08);
  }
  .rp-step-ball.done {
    border-color: #D4A820;
    background: #D4A820;
    color: #0A0800;
  }
  .rp-step-vline {
    width: 1px;
    height: 26px;
    background: rgba(243,239,234,0.08);
    transition: background 0.4s ease;
    margin: 4px 0;
  }
  .rp-step-vline.done { background: rgba(212,168,32,0.35); }
  .rp-step-info {
    padding-top: 3px;
    padding-bottom: 22px;
  }
  .rp-step-name {
    font-size: 0.8rem;
    font-weight: 700;
    color: rgba(243,239,234,0.42);
    letter-spacing: 0.01em;
    margin-bottom: 2px;
    transition: color 0.3s;
  }
  .rp-step-name.active { color: #F3EFEA; }
  .rp-step-name.done   { color: rgba(212,168,32,0.7); }
  .rp-step-desc {
    font-size: 0.72rem;
    color: rgba(243,239,234,0.28);
    line-height: 1.5;
  }
  .rp-step-row:last-child .rp-step-vline { display: none; }
  .rp-step-row:last-child .rp-step-info  { padding-bottom: 0; }

  /* Context area */
  .rp-ctx {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding-bottom: 12px;
  }
  .rp-ctx-num {
    font-size: 3rem;
    font-weight: 900;
    letter-spacing: -0.06em;
    color: transparent;
    -webkit-text-stroke: 1px rgba(212,168,32,0.18);
    line-height: 1;
    margin-bottom: 16px;
    user-select: none;
  }
  .rp-ctx-title {
    font-size: clamp(1.25rem, 2vw, 1.65rem);
    font-weight: 900;
    letter-spacing: -0.04em;
    line-height: 1.15;
    color: #F3EFEA;
    margin-bottom: 24px;
    white-space: pre-line;
  }
  .rp-ctx-bullets {
    display: flex;
    flex-direction: column;
    gap: 7px;
  }
  .rp-ctx-bullet {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    font-size: 0.78rem;
    color: rgba(243,239,234,0.62);
    line-height: 1.5;
  }
  .rp-ctx-bullet::before {
    content: '';
    width: 5px; height: 5px;
    border-radius: 50%;
    background: #D4A820;
    flex-shrink: 0;
    margin-top: 7px;
    opacity: 0.7;
  }

  .rp-left-footer {
    font-size: 0.68rem;
    color: rgba(243,239,234,0.25);
    letter-spacing: 0.03em;
  }

  /* ── DIREITO ── */
  .rp-right {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 36px 40px 36px 16px;
    animation: rp-up 0.6s cubic-bezier(.16,1,.3,1) 0.1s both;
  }

  .rp-card {
    width: 100%;
    background: rgba(16, 13, 9, 0.95);
    border: 1px solid rgba(212,168,32,0.28);
    border-radius: 20px;
    padding: 22px 22px 20px;
    position: relative;
    overflow: hidden;
    box-shadow: 0 0 0 1px rgba(212,168,32,0.05), 0 8px 40px rgba(0,0,0,0.55);
  }
  .rp-card::before {
    content: '';
    position: absolute;
    top: 0; left: 8%; right: 8%; height: 2px;
    background: linear-gradient(90deg, transparent, rgba(212,168,32,0.82), transparent);
    border-radius: 0 0 2px 2px;
  }

  .rp-card-label {
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: rgba(212,168,32,0.65);
    margin-bottom: 5px;
  }
  .rp-card-title {
    font-size: 1.15rem;
    font-weight: 800;
    color: #F3EFEA;
    letter-spacing: -0.025em;
    margin-bottom: 12px;
  }

  /* ── Google button ── */
  .rp-google {
    width: 100%;
    padding: 12px 16px;
    background: rgba(243,239,234,0.06);
    border: 1px solid rgba(243,239,234,0.13);
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    font-family: inherit;
    font-size: 0.83rem;
    font-weight: 600;
    color: rgba(243,239,234,0.82);
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s;
    margin-bottom: 10px;
  }
  .rp-google:hover { background: rgba(243,239,234,0.1); border-color: rgba(243,239,234,0.2); }

  .rp-or {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 10px;
    font-size: 0.65rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.28);
  }
  .rp-or::before, .rp-or::after {
    content: '';
    flex: 1; height: 1px;
    background: rgba(243,239,234,0.08);
  }

  /* ── Fields ── */
  .rp-fields { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; }
  .rp-row2   { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .rp-field-label {
    display: block;
    font-size: 0.63rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.55);
    margin-bottom: 5px;
  }
  .rp-input {
    width: 100%;
    padding: 11px 13px;
    background: rgba(243,239,234,0.04);
    color: #F3EFEA;
    border: 1px solid rgba(243,239,234,0.12);
    border-radius: 9px;
    font-family: inherit;
    font-size: 0.86rem;
    outline: none;
    transition: border-color 0.15s, background 0.15s;
  }
  .rp-input::placeholder { color: rgba(243,239,234,0.28); }
  .rp-input:focus { border-color: rgba(212,168,32,0.5); background: rgba(212,168,32,0.03); }
  .rp-input.err { border-color: rgba(240,122,100,0.55); background: rgba(240,122,100,0.04); }
  .rp-field-err {
    font-size: 0.7rem;
    color: #F07A64;
    margin-top: 4px;
    font-weight: 500;
  }

  /* ── Senha strength ── */
  .rp-pw-bars {
    display: flex;
    gap: 3px;
    margin-top: 7px;
  }
  .rp-pw-bar {
    flex: 1;
    height: 3px;
    border-radius: 2px;
    background: rgba(243,239,234,0.08);
    transition: background 0.3s;
  }
  .rp-pw-label {
    font-size: 0.65rem;
    font-weight: 600;
    margin-top: 4px;
    transition: color 0.3s;
    min-height: 1em;
  }

  /* ── Botão principal ── */
  .rp-btn {
    width: 100%;
    padding: 13px;
    background: linear-gradient(135deg, #C89010, #D4A820, #E8C030);
    background-size: 200% auto;
    color: #0A0800;
    border: none;
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.83rem;
    font-weight: 900;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    cursor: pointer;
    transition: background-position 0.3s, transform 0.12s, box-shadow 0.2s;
    box-shadow: 0 4px 18px rgba(212,168,32,0.2);
  }
  .rp-btn:hover:not(:disabled) {
    background-position: right center;
    transform: translateY(-1px);
    box-shadow: 0 6px 24px rgba(212,168,32,0.35);
  }
  .rp-btn:active:not(:disabled) { transform: translateY(0); }
  .rp-btn:disabled { opacity: 0.35; cursor: not-allowed; }

  .rp-btn-ghost {
    width: 100%;
    padding: 11px;
    background: transparent;
    color: rgba(243,239,234,0.5);
    border: 1px solid rgba(243,239,234,0.1);
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.78rem;
    font-weight: 500;
    cursor: pointer;
    margin-top: 8px;
    transition: border-color 0.15s, color 0.15s;
  }
  .rp-btn-ghost:hover { border-color: rgba(243,239,234,0.2); color: rgba(243,239,234,0.75); }

  /* ── Banks ── */
  .rp-bank-info {
    font-size: 0.79rem;
    color: rgba(243,239,234,0.52);
    line-height: 1.65;
    margin-bottom: 16px;
  }
  .rp-banks {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 7px;
    margin-bottom: 16px;
  }
  .rp-bank-card {
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 10px 12px;
    background: rgba(243,239,234,0.03);
    border: 1px solid rgba(243,239,234,0.07);
    border-radius: 9px;
    opacity: 0.62;
  }
  .rp-bank-icon {
    width: 26px; height: 26px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.62rem;
    font-weight: 900;
    flex-shrink: 0;
  }
  .rp-bank-name {
    font-size: 0.72rem;
    font-weight: 600;
    color: rgba(243,239,234,0.65);
    line-height: 1.2;
  }
  .rp-bank-soon {
    font-size: 0.53rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: rgba(212,168,32,0.48);
  }

  /* ── Termos ── */
  .rp-form-err {
    font-size: 0.78rem; color: #F8AEA0; background: rgba(240,122,100,0.08);
    border: 1px solid rgba(240,122,100,0.25); border-radius: 10px;
    padding: 10px 12px; margin: 4px 0 12px;
  }
  .rp-terms-summary {
    background: rgba(243,239,234,0.03);
    border: 1px solid rgba(243,239,234,0.08);
    border-radius: 10px;
    padding: 14px 16px;
    font-size: 0.76rem;
    color: rgba(243,239,234,0.52);
    line-height: 1.7;
    margin-bottom: 16px;
    max-height: 120px;
    overflow-y: auto;
  }
  .rp-terms-summary::-webkit-scrollbar { width: 4px; }
  .rp-terms-summary::-webkit-scrollbar-track { background: transparent; }
  .rp-terms-summary::-webkit-scrollbar-thumb { background: rgba(212,168,32,0.25); border-radius: 2px; }

  .rp-check-row {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    margin-bottom: 10px;
    cursor: pointer;
  }
  .rp-check-row input[type=checkbox] {
    appearance: none;
    -webkit-appearance: none;
    width: 16px; height: 16px;
    border: 1.5px solid rgba(243,239,234,0.22);
    border-radius: 4px;
    background: transparent;
    cursor: pointer;
    flex-shrink: 0;
    margin-top: 1px;
    transition: all 0.15s;
    position: relative;
  }
  .rp-check-row input[type=checkbox]:checked {
    background: #D4A820;
    border-color: #D4A820;
  }
  .rp-check-row input[type=checkbox]:checked::after {
    content: '';
    position: absolute;
    left: 3px; top: 1px;
    width: 8px; height: 5px;
    border-left: 2px solid #0A0800;
    border-bottom: 2px solid #0A0800;
    transform: rotate(-45deg);
  }
  .rp-check-label {
    font-size: 0.76rem;
    color: rgba(243,239,234,0.6);
    line-height: 1.5;
  }
  .rp-check-label a { color: #D4A820; text-decoration: none; }
  .rp-check-label a:hover { text-decoration: underline; }

  /* ── Sucesso ── */
  .rp-success {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: 8px 0 12px;
  }
  .rp-success-icon {
    width: 60px; height: 68px;
    margin-bottom: 20px;
    animation: rp-pop 0.55s cubic-bezier(.16,1,.3,1) both;
  }
  .rp-success-title {
    font-size: 1.35rem;
    font-weight: 900;
    color: #F3EFEA;
    letter-spacing: -0.03em;
    margin-bottom: 8px;
    line-height: 1.2;
  }
  .rp-success-sub {
    font-size: 0.8rem;
    color: rgba(243,239,234,0.48);
    line-height: 1.75;
    max-width: 280px;
    margin-bottom: 24px;
  }
  .rp-success-stats {
    display: flex;
    gap: 20px;
    margin-bottom: 24px;
  }
  .rp-stat { display: flex; flex-direction: column; align-items: center; gap: 2px; }
  .rp-stat-val {
    font-size: 1.15rem;
    font-weight: 900;
    color: #D4A820;
    letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
  }
  .rp-stat-lbl {
    font-size: 0.6rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.3);
  }

  /* ── Login link ── */
  .rp-login-link {
    font-size: 0.7rem;
    color: rgba(243,239,234,0.32);
    text-align: center;
    margin-top: 4px;
  }
  .rp-login-link a { color: #D4A820; text-decoration: none; font-weight: 600; }

  /* ── Mobile ── */
  @media (max-width: 900px) {
    .rp-layout { grid-template-columns: 1fr; min-height: auto; }
    .rp-left { display: none; }
    .rp-right { padding: 40px 24px 48px; align-items: flex-start; }
    .rp-root { display: flex; align-items: center; justify-content: center; }
  }
`;

// ─── RegisterPage ─────────────────────────────────────────────────────────────
export const RegisterPage: React.FC = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);

  // Step 1
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errs1, setErrs1] = useState({ name: '', email: '', phone: '', password: '', confirm: '' });

  // Step 2 — termos e criação da conta
  const [termAccepted, setTermAccepted] = useState(false);
  const [privAccepted, setPrivAccepted] = useState(false);
  const [termErr, setTermErr] = useState(false);
  const [criando, setCriando] = useState(false);
  const [erroCadastro, setErroCadastro] = useState('');
  const [reenviado, setReenviado] = useState(false);

  const strength = pwStrength(password);
  const firstName = name.trim().split(' ')[0] || '';

  useEffect(() => {
    const mm = (e: MouseEvent) => {
      document.documentElement.style.setProperty('--cx', `${e.clientX}px`);
      document.documentElement.style.setProperty('--cy', `${e.clientY}px`);
    };
    window.addEventListener('mousemove', mm);
    return () => window.removeEventListener('mousemove', mm);
  }, []);

  const validate1 = () => {
    const e = { name: '', email: '', phone: '', password: '', confirm: '' };
    if (!name.trim()) e.name = 'Preencha seu nome';
    if (!email.trim()) e.email = 'Preencha o e-mail';
    else if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) e.email = 'E-mail inválido';
    const digitos = phone.replace(/\D/g, '');
    if (digitos && digitos.length < 10) e.phone = 'Telefone incompleto';
    if (!password) e.password = 'Preencha a senha';
    else if (password.length < 8) e.password = 'Mínimo 8 caracteres';
    if (!confirm) e.confirm = 'Confirme a senha';
    else if (confirm !== password) e.confirm = 'Senhas não coincidem';
    setErrs1(e);
    return !Object.values(e).some(Boolean);
  };

  const handleStep1 = (ev: React.FormEvent) => { ev.preventDefault(); if (validate1()) setStep(2); };

  // A conta nasce AQUI, depois do aceite — o backend exige accepted_terms e
  // grava o instante do consentimento. Antes, nenhuma etapa chamava o
  // servidor e a tela final dizia "sua conta está criada".
  const criarConta = async () => {
    if (!termAccepted || !privAccepted) { setTermErr(true); return; }
    setCriando(true);
    setErroCadastro('');
    try {
      await register({
        email,
        password,
        full_name: name.trim(),
        phone: phone ? phoneE164(phone) : undefined,
        accepted_terms: true,
      });
      setStep(3);
    } catch (err) {
      const info = describeError(err);
      if (info.kind === 'validation' && /registrado/i.test(info.message)) {
        setErrs1(p => ({ ...p, email: 'Este e-mail já tem conta. Entre ou recupere a senha.' }));
        setStep(1);
      } else if (info.kind === 'validation') {
        setErroCadastro(info.message);
      } else {
        setErroCadastro(info.message || 'Não foi possível criar a conta agora.');
      }
    } finally {
      setCriando(false);
    }
  };

  const reenviarConfirmacao = async () => {
    try {
      await resendVerification(email);
      setReenviado(true);
    } catch {
      setReenviado(false);
    }
  };

  const dot = (n: number) => step > n ? 'done' : step === n ? 'active' : '';
  const ctx = LEFT_CTX[Math.min(step, 3) - 1];

  const STEPS = ['Criar conta', 'Termos de uso', 'Conectar banco'];
  const STEP_DESC = [
    'Dados e credenciais de acesso',
    'Leitura e aceite dos termos',
    'Vincule sua conta bancária',
  ];

  return (
    <>
      <style>{css}</style>
      <div className="rp-root">
        <HoneycombCanvas />
        <div className="rp-wm" aria-hidden="true">HIVE</div>

        <div className="rp-layout">
          {/* ── ESQUERDO ── */}
          <div className="rp-left">
            <div className="rp-logo">
              <svg width="24" height="28" viewBox="0 0 180 200" fill="none">
                <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="#7A5002"/>
                <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="#D4A820"/>
                <polygon points="100,16 110,22 110,178 100,184" fill="#090500"/>
              </svg>
              <span className="rp-logo-word">HIVE</span>
            </div>

            {/* Progress vertical */}
            <div className="rp-step-nav">
              {STEPS.map((s, i) => (
                <div key={i} className="rp-step-row">
                  <div className="rp-step-col">
                    <div className={`rp-step-ball ${dot(i + 1)}`}>
                      {step > i + 1
                        ? <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M1.5 5l2.5 2.5 4.5-4.5" stroke="#0A0800" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
                        : i + 1}
                    </div>
                    <div className={`rp-step-vline ${step > i + 1 ? 'done' : ''}`} />
                  </div>
                  <div className="rp-step-info">
                    <div className={`rp-step-name ${dot(i + 1)}`}>{s}</div>
                    <div className="rp-step-desc">{STEP_DESC[i]}</div>
                  </div>
                </div>
              ))}
            </div>

            {/* Contexto do step atual */}
            <div className="rp-ctx">
              <div className="rp-ctx-num">{ctx.step}</div>
              <div className="rp-ctx-title">{ctx.title}</div>
              <div className="rp-ctx-bullets">
                {ctx.bullets.map((b, i) => (
                  <div key={i} className="rp-ctx-bullet">{b}</div>
                ))}
              </div>
            </div>

            <div className="rp-left-footer">© 2025 HIVE · Todos os direitos reservados</div>
          </div>

          {/* ── DIREITO — card ── */}
          <div className="rp-right">
            <div style={{ width: '100%' }}>
              <div className="rp-card">
                {/* ── Step 1: Conta ── */}
                {step === 1 && (
                  <>
                    <div className="rp-card-label">Passo 1 de 3</div>
                    <div className="rp-card-title">Crie sua conta</div>

                    <form onSubmit={handleStep1} noValidate>
                      <div className="rp-fields">
                        <div>
                          <label className="rp-field-label">Nome completo</label>
                          <input className={`rp-input${errs1.name ? ' err' : ''}`} type="text" placeholder="Seu nome completo"
                            value={name} onChange={e => { setName(e.target.value); if (errs1.name) setErrs1(p => ({...p, name: ''})); }}
                            autoComplete="name" autoFocus />
                          {errs1.name && <div className="rp-field-err">{errs1.name}</div>}
                        </div>

                        <div>
                          <label className="rp-field-label">E-mail</label>
                          <input className={`rp-input${errs1.email ? ' err' : ''}`} type="email" placeholder="seu@email.com"
                            value={email} onChange={e => { setEmail(e.target.value); if (errs1.email) setErrs1(p => ({...p, email: ''})); }}
                            autoComplete="email" />
                          {errs1.email && <div className="rp-field-err">{errs1.email}</div>}
                        </div>

                        <div>
                          <label className="rp-field-label">Celular (opcional)</label>
                          <input className={`rp-input${errs1.phone ? ' err' : ''}`} type="tel" placeholder="(00) 00000-0000"
                            value={phone} onChange={e => { setPhone(fmtPhone(e.target.value)); if (errs1.phone) setErrs1(p => ({...p, phone: ''})); }}
                            inputMode="numeric" autoComplete="tel" />
                          {errs1.phone && <div className="rp-field-err">{errs1.phone}</div>}
                        </div>

                        <div>
                          <label className="rp-field-label">Senha</label>
                          <input className={`rp-input${errs1.password ? ' err' : ''}`} type="password" placeholder="Mínimo 8 caracteres"
                            value={password} onChange={e => { setPassword(e.target.value); if (errs1.password) setErrs1(p => ({...p, password: ''})); }}
                            autoComplete="new-password" />
                          {password && (
                            <>
                              <div className="rp-pw-bars">
                                {[1,2,3,4,5].map(i => (
                                  <div key={i} className="rp-pw-bar"
                                    style={{ background: i <= strength ? PW_COLOR[strength] : undefined }} />
                                ))}
                              </div>
                              <div className="rp-pw-label" style={{ color: PW_COLOR[strength] }}>
                                {PW_LABEL[strength]}
                              </div>
                            </>
                          )}
                          {errs1.password && <div className="rp-field-err">{errs1.password}</div>}
                        </div>

                        <div>
                          <label className="rp-field-label">Confirmar senha</label>
                          <input className={`rp-input${errs1.confirm ? ' err' : ''}`} type="password" placeholder="Repita a senha"
                            value={confirm} onChange={e => { setConfirm(e.target.value); if (errs1.confirm) setErrs1(p => ({...p, confirm: ''})); }}
                            autoComplete="new-password" />
                          {errs1.confirm && <div className="rp-field-err">{errs1.confirm}</div>}
                        </div>
                      </div>

                      <button type="submit" className="rp-btn">Continuar</button>
                    </form>
                  </>
                )}

                {/* ── Step 2: Termos (cria a conta) ── */}
                {step === 2 && (
                  <>
                    <div className="rp-card-label">Passo 2 de 3</div>
                    <div className="rp-card-title">Termos e privacidade</div>
                    <div className="rp-terms-summary">
                      <strong style={{ color: 'rgba(243,239,234,0.75)', display: 'block', marginBottom: 6 }}>Termos de Uso</strong>
                      O HIVE é uma plataforma de análise financeira pessoal. Ao utilizar nossos serviços, você concorda que seus dados financeiros serão usados exclusivamente para gerar insights personalizados dentro da plataforma. Não vendemos, alugamos ou compartilhamos seus dados com terceiros para fins comerciais. Você pode revogar o acesso e solicitar a exclusão da conta a qualquer momento.
                      <br /><br />
                      <strong style={{ color: 'rgba(243,239,234,0.75)', display: 'block', marginBottom: 6 }}>Política de Privacidade</strong>
                      Seus dados pessoais são tratados conforme a Lei Geral de Proteção de Dados (LGPD — Lei 13.709/2018). A senha é guardada apenas como hash (bcrypt) e as conexões trafegam por TLS. O HIVE não acessa sua conta bancária diretamente: só analisa os dados que você autoriza a compartilhar pelo Open Finance. Em Perfil você exporta ou apaga todos os seus dados.
                    </div>

                    <label className="rp-check-row">
                      <input type="checkbox" checked={termAccepted} onChange={e => { setTermAccepted(e.target.checked); setTermErr(false); }} />
                      <span className="rp-check-label">Li e aceito os Termos de Uso</span>
                    </label>
                    <label className="rp-check-row">
                      <input type="checkbox" checked={privAccepted} onChange={e => { setPrivAccepted(e.target.checked); setTermErr(false); }} />
                      <span className="rp-check-label">Li e aceito a Política de Privacidade</span>
                    </label>

                    {termErr && (
                      <div className="rp-field-err" style={{ marginBottom: 10 }}>
                        Aceite os termos para continuar
                      </div>
                    )}
                    {erroCadastro && <div className="rp-form-err" role="alert">{erroCadastro}</div>}

                    <button className="rp-btn" style={{ marginTop: 14 }} onClick={criarConta} disabled={criando}>
                      {criando ? 'Criando sua conta…' : 'Aceitar e criar conta'}
                    </button>
                    <button className="rp-btn-ghost" onClick={() => setStep(1)} disabled={criando}>Voltar</button>
                  </>
                )}

                {/* ── Step 3: Banco ── */}
                {step === 3 && (
                  <>
                    <div className="rp-card-label">Passo 3 de 3</div>
                    <div className="rp-card-title">Conecte seu banco</div>
                    <p className="rp-bank-info">
                      Sua conta foi criada. Agora conecte um banco pelo Open Finance para o HIVE analisar seus dados reais — você escolhe quais contas compartilhar e pode revogar quando quiser.
                    </p>
                    <div className="rp-banks">
                      {BANKS.map(b => (
                        <div key={b.name} className="rp-bank-card">
                          <div className="rp-bank-icon" style={{ background: b.bg, color: b.fg }}>{b.abbr}</div>
                          <div>
                            <div className="rp-bank-name">{b.name}</div>
                            <div className="rp-bank-soon">via Open Finance</div>
                          </div>
                        </div>
                      ))}
                    </div>
                    <button className="rp-btn" onClick={() => navigate('/connections')}>Conectar banco agora</button>
                    <button className="rp-btn-ghost" onClick={() => setStep(4)}>Conectar mais tarde</button>
                  </>
                )}

                {/* ── Step 4: Pronto ── */}
                {step === 4 && (
                  <div className="rp-success">
                    <svg className="rp-success-icon" viewBox="0 0 180 200" fill="none">
                      <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="#7A5002"/>
                      <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="#D4A820"/>
                      <polygon points="100,16 110,22 110,178 100,184" fill="#090500"/>
                      <path d="M58 100 L78 120 L122 78" stroke="#0A0800" strokeWidth="11" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                    <div className="rp-success-title">
                      {firstName ? `Bem-vindo, ${firstName}.` : 'Tudo certo.'}
                    </div>
                    <p className="rp-success-sub">
                      Enviamos um link de confirmação para <strong>{email.trim().toLowerCase()}</strong>.
                      Confirme quando puder — você já pode usar o HIVE.
                    </p>
                    <button className="rp-btn" onClick={() => navigate('/dashboard')}>Entrar no HIVE</button>
                    <button className="rp-btn-ghost" onClick={reenviarConfirmacao} disabled={reenviado}>
                      {reenviado ? 'Link reenviado' : 'Reenviar e-mail de confirmação'}
                    </button>
                  </div>
                )}
              </div>

              {step === 1 && (
                <div className="rp-login-link" style={{ marginTop: 14 }}>
                  Já tem uma conta? <Link to="/login">Entrar</Link>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
};
