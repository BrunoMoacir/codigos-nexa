import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';

// ─── Honeycomb canvas ────────────────────────────────────────────────────────
const HoneycombCanvas: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mouse = useRef({ x: -9999, y: -9999 });
  const clicks = useRef<Array<{ x: number; y: number; t: number }>>([]);
  const rafRef = useRef<number>();

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
      ctx.scale(DPR, DPR);
      build();
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
          const age = (now - ck.t) / 1000, wave = age * WAVE_SPEED;
          const d = Math.hypot(h.cx - ck.x, h.cy - ck.y);
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
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 40px 24px;
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

  /* Marca d'agua */
  .rp-wm {
    position: fixed;
    left: 50%; top: 50%;
    transform: translate(-50%, -50%);
    font-size: min(48vw, 480px);
    font-weight: 900;
    letter-spacing: -0.06em;
    color: transparent;
    -webkit-text-stroke: 1px rgba(212,168,32,0.03);
    pointer-events: none;
    z-index: 0;
    user-select: none;
    line-height: 1;
    white-space: nowrap;
  }

  @keyframes rp-up {
    from { opacity: 0; transform: translateY(18px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes rp-pop {
    0%   { opacity: 0; transform: scale(0.5); }
    65%  { transform: scale(1.12); }
    100% { opacity: 1; transform: scale(1); }
  }
  @keyframes shimmer {
    0%   { background-position: 200% center; }
    100% { background-position: -200% center; }
  }

  .rp-wrap {
    position: relative;
    z-index: 2;
    width: 100%;
    max-width: 460px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 22px;
  }

  /* ── Brand ── */
  .rp-brand {
    display: flex;
    align-items: center;
    gap: 12px;
    animation: rp-up 0.5s cubic-bezier(.16,1,.3,1) both;
  }
  .rp-brand-name {
    font-size: 1.5rem;
    font-weight: 900;
    letter-spacing: 0.03em;
    color: #D4A820;
  }

  /* ── Card ── */
  .rp-card {
    width: 100%;
    background: rgba(16, 13, 9, 0.95);
    border: 1px solid rgba(212,168,32,0.28);
    border-radius: 20px;
    padding: 28px 28px 26px;
    position: relative;
    overflow: hidden;
    box-shadow: 0 0 0 1px rgba(212,168,32,0.05), 0 8px 40px rgba(0,0,0,0.55), 0 0 60px rgba(212,168,32,0.04);
    animation: rp-up 0.6s cubic-bezier(.16,1,.3,1) 0.06s both;
  }
  .rp-card::before {
    content: '';
    position: absolute;
    top: 0; left: 8%; right: 8%;
    height: 2px;
    background: linear-gradient(90deg, transparent, rgba(212,168,32,0.82), transparent);
    border-radius: 0 0 2px 2px;
  }

  /* ── Steps indicator ── */
  .rp-steps {
    display: flex;
    align-items: center;
    margin-bottom: 26px;
  }
  .rp-step-item {
    display: flex;
    align-items: center;
    flex: 1;
  }
  .rp-step-item:last-child { flex: 0; }
  .rp-step-dot {
    width: 28px; height: 28px;
    border-radius: 50%;
    border: 1.5px solid rgba(243,239,234,0.14);
    background: transparent;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.68rem;
    font-weight: 800;
    color: rgba(243,239,234,0.22);
    transition: all 0.3s ease;
    flex-shrink: 0;
  }
  .rp-step-dot.active {
    border-color: #D4A820;
    background: rgba(212,168,32,0.1);
    color: #D4A820;
    box-shadow: 0 0 0 3px rgba(212,168,32,0.08);
  }
  .rp-step-dot.done {
    border-color: #D4A820;
    background: #D4A820;
    color: #0A0800;
  }
  .rp-step-line {
    flex: 1;
    height: 1px;
    background: rgba(243,239,234,0.08);
    margin: 0 6px;
    transition: background 0.4s ease;
  }
  .rp-step-line.done { background: rgba(212,168,32,0.42); }

  /* ── Step content ── */
  .rp-step-label {
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.28);
    margin-bottom: 5px;
  }
  .rp-step-title {
    font-size: 1.18rem;
    font-weight: 800;
    color: #F3EFEA;
    letter-spacing: -0.025em;
    margin-bottom: 20px;
  }

  /* ── Fields ── */
  .rp-fields { display: flex; flex-direction: column; gap: 12px; margin-bottom: 18px; }
  .rp-field-label {
    display: block;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.38);
    margin-bottom: 6px;
  }
  .rp-input {
    width: 100%;
    padding: 12px 14px;
    background: rgba(243,239,234,0.04);
    color: #F3EFEA;
    border: 1px solid rgba(243,239,234,0.1);
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.88rem;
    outline: none;
    transition: border-color 0.15s, background 0.15s;
  }
  .rp-input::placeholder { color: rgba(243,239,234,0.2); }
  .rp-input:focus { border-color: rgba(212,168,32,0.5); background: rgba(212,168,32,0.03); }
  .rp-input.err { border-color: rgba(240,122,100,0.55); background: rgba(240,122,100,0.04); }
  .rp-field-err {
    font-size: 0.7rem;
    color: #F07A64;
    margin-top: 5px;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 5px;
  }
  .rp-field-err::before { content: none; }

  /* ── Botões ── */
  .rp-btn {
    width: 100%;
    padding: 14px;
    background: linear-gradient(135deg, #C89010, #D4A820, #E8C030);
    background-size: 200% auto;
    color: #0A0800;
    border: none;
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.84rem;
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
    padding: 12px;
    background: transparent;
    color: rgba(243,239,234,0.38);
    border: 1px solid rgba(243,239,234,0.1);
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.8rem;
    font-weight: 500;
    cursor: pointer;
    transition: border-color 0.15s, color 0.15s;
    margin-top: 9px;
  }
  .rp-btn-ghost:hover { border-color: rgba(243,239,234,0.2); color: rgba(243,239,234,0.65); }

  /* ── Banks (step 2) ── */
  .rp-bank-info {
    font-size: 0.8rem;
    color: rgba(243,239,234,0.32);
    line-height: 1.65;
    margin-bottom: 18px;
  }
  .rp-banks {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-bottom: 18px;
  }
  .rp-bank-card {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 11px 13px;
    background: rgba(243,239,234,0.03);
    border: 1px solid rgba(243,239,234,0.07);
    border-radius: 10px;
    opacity: 0.6;
  }
  .rp-bank-icon {
    width: 28px; height: 28px;
    border-radius: 7px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.66rem;
    font-weight: 900;
    flex-shrink: 0;
  }
  .rp-bank-name {
    font-size: 0.74rem;
    font-weight: 600;
    color: rgba(243,239,234,0.55);
    line-height: 1.2;
  }
  .rp-bank-soon {
    font-size: 0.55rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: rgba(212,168,32,0.42);
  }

  /* ── Sucesso (step 3) ── */
  .rp-success {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: 6px 0 10px;
  }
  .rp-success-icon {
    width: 64px; height: 72px;
    margin-bottom: 22px;
    animation: rp-pop 0.55s cubic-bezier(.16,1,.3,1) both;
  }
  .rp-success-title {
    font-size: 1.45rem;
    font-weight: 900;
    color: #F3EFEA;
    letter-spacing: -0.03em;
    margin-bottom: 10px;
    line-height: 1.2;
  }
  .rp-success-sub {
    font-size: 0.82rem;
    color: rgba(243,239,234,0.38);
    line-height: 1.75;
    max-width: 290px;
    margin-bottom: 28px;
  }
  .rp-success-stat {
    display: flex;
    gap: 24px;
    margin-bottom: 28px;
  }
  .rp-stat {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
  }
  .rp-stat-value {
    font-size: 1.2rem;
    font-weight: 900;
    color: #D4A820;
    letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
  }
  .rp-stat-label {
    font-size: 0.62rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.28);
  }

  /* ── Login link ── */
  .rp-login-link {
    font-size: 0.72rem;
    color: rgba(243,239,234,0.22);
    text-align: center;
  }
  .rp-login-link a {
    color: #D4A820;
    text-decoration: none;
    font-weight: 600;
  }
  .rp-login-link a:hover { opacity: 0.8; }

  @media (max-width: 540px) {
    .rp-root { padding: 28px 16px; }
    .rp-card { padding: 24px 20px; border-radius: 16px; }
    .rp-banks { grid-template-columns: 1fr; }
  }
`;

// ─── Dados ───────────────────────────────────────────────────────────────────
const BANKS = [
  { name: 'Nubank',    abbr: 'Nu', bg: '#820AD1', fg: '#fff' },
  { name: 'Itaú',      abbr: 'IT', bg: '#EC7000', fg: '#fff' },
  { name: 'Bradesco',  abbr: 'BD', bg: '#CC092F', fg: '#fff' },
  { name: 'C6 Bank',   abbr: 'C6', bg: '#2B2D33', fg: '#FFD700' },
  { name: 'Inter',     abbr: 'IN', bg: '#FF7A00', fg: '#fff' },
  { name: 'BTG',       abbr: 'BT', bg: '#1A1A2E', fg: '#D4A820' },
];

// ─── Ícone de check SVG ──────────────────────────────────────────────────────
const CheckIcon = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
    <path d="M2 6l3 3 5-5" stroke="#0A0800" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

// ─── RegisterPage ─────────────────────────────────────────────────────────────
export const RegisterPage: React.FC = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errs, setErrs] = useState({ name: '', email: '', password: '', confirm: '' });

  useEffect(() => {
    const mm = (e: MouseEvent) => {
      document.documentElement.style.setProperty('--cx', `${e.clientX}px`);
      document.documentElement.style.setProperty('--cy', `${e.clientY}px`);
    };
    window.addEventListener('mousemove', mm);
    return () => window.removeEventListener('mousemove', mm);
  }, []);

  const validate1 = () => {
    const e = { name: '', email: '', password: '', confirm: '' };
    if (!name.trim())         e.name     = 'Preencha seu nome';
    if (!email.trim())        e.email    = 'Preencha o e-mail';
    else if (!/\S+@\S+\.\S+/.test(email)) e.email = 'E-mail inválido';
    if (!password)            e.password = 'Preencha a senha';
    else if (password.length < 6) e.password = 'Mínimo 6 caracteres';
    if (!confirm)             e.confirm  = 'Confirme a senha';
    else if (confirm !== password) e.confirm = 'Senhas não coincidem';
    setErrs(e);
    return !e.name && !e.email && !e.password && !e.confirm;
  };

  const handleStep1 = (ev: React.FormEvent) => {
    ev.preventDefault();
    if (validate1()) setStep(2);
  };

  const dot = (n: number) => (step > n ? 'done' : step === n ? 'active' : '');

  const firstName = name.trim().split(' ')[0] || '';

  return (
    <>
      <style>{css}</style>
      <div className="rp-root">
        <HoneycombCanvas />
        <div className="rp-wm" aria-hidden="true">HIVE</div>

        <div className="rp-wrap">
          {/* Logo */}
          <div className="rp-brand">
            <svg width="28" height="32" viewBox="0 0 180 200" fill="none">
              <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="#7A5002"/>
              <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="#D4A820"/>
              <polygon points="100,16 110,22 110,178 100,184" fill="#090500"/>
            </svg>
            <span className="rp-brand-name">HIVE</span>
          </div>

          {/* Card */}
          <div className="rp-card">
            {/* Indicador de passos */}
            <div className="rp-steps">
              <div className="rp-step-item">
                <div className={`rp-step-dot ${dot(1)}`}>{step > 1 ? <CheckIcon /> : '1'}</div>
                <div className={`rp-step-line ${step > 1 ? 'done' : ''}`} />
              </div>
              <div className="rp-step-item">
                <div className={`rp-step-dot ${dot(2)}`}>{step > 2 ? <CheckIcon /> : '2'}</div>
                <div className={`rp-step-line ${step > 2 ? 'done' : ''}`} />
              </div>
              <div className={`rp-step-dot ${dot(3)}`}>{step > 3 ? <CheckIcon /> : '3'}</div>
            </div>

            {/* ── Step 1: Dados ── */}
            {step === 1 && (
              <>
                <div className="rp-step-label">Passo 1 de 3</div>
                <div className="rp-step-title">Crie sua conta</div>
                <form onSubmit={handleStep1} noValidate>
                  <div className="rp-fields">
                    <div>
                      <label className="rp-field-label">Nome completo</label>
                      <input
                        className={`rp-input${errs.name ? ' err' : ''}`}
                        type="text" placeholder="Seu nome"
                        value={name} onChange={e => { setName(e.target.value); if (errs.name) setErrs(p => ({...p, name: ''})); }}
                        autoComplete="name" autoFocus
                      />
                      {errs.name && <div className="rp-field-err">{errs.name}</div>}
                    </div>
                    <div>
                      <label className="rp-field-label">E-mail</label>
                      <input
                        className={`rp-input${errs.email ? ' err' : ''}`}
                        type="email" placeholder="seu@email.com"
                        value={email} onChange={e => { setEmail(e.target.value); if (errs.email) setErrs(p => ({...p, email: ''})); }}
                        autoComplete="email"
                      />
                      {errs.email && <div className="rp-field-err">{errs.email}</div>}
                    </div>
                    <div>
                      <label className="rp-field-label">Senha</label>
                      <input
                        className={`rp-input${errs.password ? ' err' : ''}`}
                        type="password" placeholder="Mínimo 6 caracteres"
                        value={password} onChange={e => { setPassword(e.target.value); if (errs.password) setErrs(p => ({...p, password: ''})); }}
                        autoComplete="new-password"
                      />
                      {errs.password && <div className="rp-field-err">{errs.password}</div>}
                    </div>
                    <div>
                      <label className="rp-field-label">Confirmar senha</label>
                      <input
                        className={`rp-input${errs.confirm ? ' err' : ''}`}
                        type="password" placeholder="Repita a senha"
                        value={confirm} onChange={e => { setConfirm(e.target.value); if (errs.confirm) setErrs(p => ({...p, confirm: ''})); }}
                        autoComplete="new-password"
                      />
                      {errs.confirm && <div className="rp-field-err">{errs.confirm}</div>}
                    </div>
                  </div>
                  <button type="submit" className="rp-btn">Continuar</button>
                </form>
              </>
            )}

            {/* ── Step 2: Banco ── */}
            {step === 2 && (
              <>
                <div className="rp-step-label">Passo 2 de 3</div>
                <div className="rp-step-title">Conecte seu banco</div>
                <p className="rp-bank-info">
                  Conecte sua conta para que o HIVE analise seus dados e gere insights reais sobre seu dinheiro.
                </p>
                <div className="rp-banks">
                  {BANKS.map(b => (
                    <div key={b.name} className="rp-bank-card">
                      <div className="rp-bank-icon" style={{ background: b.bg, color: b.fg }}>{b.abbr}</div>
                      <div>
                        <div className="rp-bank-name">{b.name}</div>
                        <div className="rp-bank-soon">Em breve</div>
                      </div>
                    </div>
                  ))}
                </div>
                <button className="rp-btn" onClick={() => setStep(3)}>Conectar banco</button>
                <button className="rp-btn-ghost" onClick={() => setStep(3)}>Conectar mais tarde</button>
              </>
            )}

            {/* ── Step 3: Sucesso ── */}
            {step === 3 && (
              <div className="rp-success">
                <svg className="rp-success-icon" viewBox="0 0 180 200" fill="none">
                  <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="#7A5002"/>
                  <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="#D4A820"/>
                  <polygon points="100,16 110,22 110,178 100,184" fill="#090500"/>
                  <path d="M60 100 L78 118 L120 82" stroke="#0A0800" strokeWidth="10" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                <div className="rp-success-title">
                  {firstName ? `Bem-vindo, ${firstName}.` : 'Tudo certo.'}
                </div>
                <p className="rp-success-sub">
                  Sua conta está criada. Agora você tem acesso à inteligência financeira que os bancos não querem que você tenha.
                </p>
                <div className="rp-success-stat">
                  <div className="rp-stat">
                    <span className="rp-stat-value">+2.4k</span>
                    <span className="rp-stat-label">Usuários</span>
                  </div>
                  <div className="rp-stat">
                    <span className="rp-stat-value">R$12M</span>
                    <span className="rp-stat-label">Analisados</span>
                  </div>
                  <div className="rp-stat">
                    <span className="rp-stat-value">94%</span>
                    <span className="rp-stat-label">Aprovação</span>
                  </div>
                </div>
                <button className="rp-btn" onClick={() => navigate('/dashboard')}>
                  Entrar no HIVE
                </button>
              </div>
            )}
          </div>

          {step === 1 && (
            <div className="rp-login-link">
              Já tem uma conta? <Link to="/login">Entrar</Link>
            </div>
          )}
        </div>
      </div>
    </>
  );
};
