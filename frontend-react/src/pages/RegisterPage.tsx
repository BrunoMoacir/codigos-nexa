import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { API_BASE_URL } from '../api/client';

// ─── Honeycomb canvas (igual ao login) ───────────────────────────────────────
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
    const GLOW_R = 150, WAVE_SPEED = 260, WAVE_WIDTH = 50;
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
        ctx.fillStyle = total > 0.02 ? `rgba(212,168,32,${total * 0.2})` : `rgba(243,239,234,${baseA * 0.35})`;
        ctx.fill();
        drawHex(h.cx, h.cy, s);
        ctx.strokeStyle = total > 0.02 ? `rgba(212,168,32,${0.05 + total * 0.7})` : `rgba(243,239,234,${baseA})`;
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
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800;900&display=swap');
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  .rp-root {
    font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
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
    width: 480px; height: 480px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(212,168,32,0.045) 0%, transparent 65%);
    transform: translate(var(--cx,-9999px), var(--cy,-9999px)) translate(-50%,-50%);
    pointer-events: none;
    z-index: 1;
    transition: transform 0.06s linear;
  }

  .rp-wrap {
    position: relative;
    z-index: 2;
    width: 100%;
    max-width: 480px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 28px;
  }

  /* Logo topo */
  .rp-brand {
    display: flex;
    align-items: center;
    gap: 12px;
    animation: rp-up 0.5s cubic-bezier(.16,1,.3,1) both;
  }
  .rp-brand-name {
    font-size: 1.6rem;
    font-weight: 900;
    letter-spacing: 0.14em;
    color: #D4A820;
  }

  /* Card */
  .rp-card {
    width: 100%;
    background: #100E0C;
    border: 1px solid rgba(243,239,234,0.09);
    border-radius: 24px;
    padding: 36px 32px 32px;
    animation: rp-up 0.6s cubic-bezier(.16,1,.3,1) 0.05s both;
  }

  /* Steps indicator */
  .rp-steps {
    display: flex;
    align-items: center;
    gap: 0;
    margin-bottom: 32px;
  }
  .rp-step-item {
    display: flex;
    align-items: center;
    gap: 0;
    flex: 1;
  }
  .rp-step-item:last-child { flex: 0; }
  .rp-step-dot {
    width: 28px; height: 28px;
    border-radius: 50%;
    border: 1.5px solid rgba(243,239,234,0.15);
    background: transparent;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.7rem;
    font-weight: 800;
    color: rgba(243,239,234,0.25);
    transition: all 0.3s ease;
    flex-shrink: 0;
    position: relative;
    z-index: 1;
  }
  .rp-step-dot.active {
    border-color: #D4A820;
    background: rgba(212,168,32,0.12);
    color: #D4A820;
  }
  .rp-step-dot.done {
    border-color: #D4A820;
    background: #D4A820;
    color: #0A0800;
  }
  .rp-step-line {
    flex: 1;
    height: 1px;
    background: rgba(243,239,234,0.1);
    margin: 0 4px;
    transition: background 0.4s ease;
  }
  .rp-step-line.done { background: rgba(212,168,32,0.4); }

  /* Step label */
  .rp-step-label {
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.28);
    margin-bottom: 6px;
  }
  .rp-step-title {
    font-size: 1.2rem;
    font-weight: 800;
    color: #F3EFEA;
    letter-spacing: -0.02em;
    margin-bottom: 24px;
  }

  /* Fields */
  .rp-fields { display: flex; flex-direction: column; gap: 12px; margin-bottom: 20px; }
  .rp-field-label {
    display: block;
    font-size: 0.66rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.35);
    margin-bottom: 5px;
  }
  .rp-input {
    width: 100%;
    padding: 12px 14px;
    background: #1A1612;
    color: #F3EFEA;
    border: 1px solid rgba(243,239,234,0.1);
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.87rem;
    outline: none;
    transition: border-color 0.15s;
  }
  .rp-input::placeholder { color: rgba(243,239,234,0.22); }
  .rp-input:focus { border-color: rgba(212,168,32,0.5); background: #1E1A16; }

  /* Botão primário */
  .rp-btn {
    width: 100%;
    padding: 14px;
    background: #D4A820;
    color: #0A0800;
    border: none;
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.84rem;
    font-weight: 900;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    cursor: pointer;
    transition: background 0.15s, transform 0.12s;
  }
  .rp-btn:hover:not(:disabled) { background: #EAC02C; transform: translateY(-1px); }
  .rp-btn:active:not(:disabled) { transform: translateY(0); }
  .rp-btn:disabled { opacity: 0.3; cursor: not-allowed; }

  /* Botão secundário (outline) */
  .rp-btn-outline {
    width: 100%;
    padding: 13px;
    background: transparent;
    color: rgba(243,239,234,0.55);
    border: 1px solid rgba(243,239,234,0.12);
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.82rem;
    font-weight: 600;
    cursor: pointer;
    transition: border-color 0.15s, color 0.15s;
    margin-top: 10px;
  }
  .rp-btn-outline:hover { border-color: rgba(243,239,234,0.25); color: rgba(243,239,234,0.8); }

  /* Divisor */
  .rp-divider {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 18px 0;
    color: rgba(243,239,234,0.15);
    font-size: 0.68rem;
    letter-spacing: 0.08em;
  }
  .rp-divider::before, .rp-divider::after {
    content: '';
    flex: 1;
    height: 1px;
    background: rgba(243,239,234,0.08);
  }

  /* Bancos grid (step 2) */
  .rp-banks {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-bottom: 20px;
  }
  .rp-bank-card {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 14px;
    background: #1A1612;
    border: 1px solid rgba(243,239,234,0.08);
    border-radius: 12px;
    cursor: default;
    transition: border-color 0.15s;
    opacity: 0.55;
  }
  .rp-bank-icon {
    width: 28px; height: 28px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.75rem;
    font-weight: 900;
    flex-shrink: 0;
  }
  .rp-bank-name {
    font-size: 0.75rem;
    font-weight: 600;
    color: rgba(243,239,234,0.6);
  }
  .rp-bank-soon {
    font-size: 0.58rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: rgba(212,168,32,0.5);
    margin-top: 2px;
  }
  .rp-bank-info {
    font-size: 0.72rem;
    color: rgba(243,239,234,0.28);
    text-align: center;
    line-height: 1.6;
    margin-bottom: 20px;
  }

  /* Sucesso (step 3) */
  .rp-success {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: 8px 0 12px;
  }
  .rp-success-hex {
    width: 72px; height: 80px;
    margin-bottom: 24px;
    animation: rp-pop 0.5s cubic-bezier(.16,1,.3,1) both;
  }
  .rp-success-title {
    font-size: 1.5rem;
    font-weight: 900;
    color: #F3EFEA;
    letter-spacing: -0.03em;
    margin-bottom: 10px;
  }
  .rp-success-sub {
    font-size: 0.85rem;
    color: rgba(243,239,234,0.45);
    line-height: 1.7;
    max-width: 300px;
    margin-bottom: 32px;
  }

  /* Login link */
  .rp-login-link {
    font-size: 0.72rem;
    color: rgba(243,239,234,0.28);
    text-align: center;
  }
  .rp-login-link a {
    color: #D4A820;
    text-decoration: none;
    font-weight: 600;
  }
  .rp-login-link a:hover { text-decoration: underline; }

  /* Animations */
  @keyframes rp-up {
    from { opacity: 0; transform: translateY(20px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes rp-pop {
    0%   { opacity: 0; transform: scale(0.6); }
    70%  { transform: scale(1.08); }
    100% { opacity: 1; transform: scale(1); }
  }

  @media (max-width: 540px) {
    .rp-card { padding: 28px 20px 24px; border-radius: 18px; }
    .rp-banks { grid-template-columns: 1fr; }
  }
`;

// ─── RegisterPage ─────────────────────────────────────────────────────────────
const BANKS = [
  { name: 'Nubank',   abbr: 'Nu',  bg: '#820AD1', fg: '#fff' },
  { name: 'Itaú',     abbr: 'IT',  bg: '#EC7000', fg: '#fff' },
  { name: 'Bradesco', abbr: 'BD',  bg: '#CC092F', fg: '#fff' },
  { name: 'C6 Bank',  abbr: 'C6',  bg: '#2B2D33', fg: '#FFD700' },
  { name: 'Inter',    abbr: 'IN',  bg: '#FF7A00', fg: '#fff' },
  { name: 'BTG',      abbr: 'BT',  bg: '#1A1A2E', fg: '#D4A820' },
];

export const RegisterPage: React.FC = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading] = useState(false);

  useEffect(() => {
    const mm = (e: MouseEvent) => {
      document.documentElement.style.setProperty('--cx', `${e.clientX}px`);
      document.documentElement.style.setProperty('--cy', `${e.clientY}px`);
    };
    window.addEventListener('mousemove', mm);
    return () => window.removeEventListener('mousemove', mm);
  }, []);

  const handleCreateAccount = (e: React.FormEvent) => {
    e.preventDefault();
    setStep(2);
  };

  const stepDot = (n: number) => {
    if (step > n) return 'done';
    if (step === n) return 'active';
    return '';
  };

  return (
    <>
      <style>{css}</style>
      <div className="rp-root">
        <HoneycombCanvas />

        <div className="rp-wrap">
          {/* Logo */}
          <div className="rp-brand">
            <svg width="32" height="36" viewBox="0 0 180 200" fill="none">
              <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="#7A5002"/>
              <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="#D4A820"/>
              <polygon points="100,16 110,22 110,178 100,184" fill="#090500"/>
            </svg>
            <span className="rp-brand-name">HIVE</span>
          </div>

          {/* Card */}
          <div className="rp-card">
            {/* Steps */}
            <div className="rp-steps">
              <div className="rp-step-item">
                <div className={`rp-step-dot ${stepDot(1)}`}>
                  {step > 1 ? '✓' : '1'}
                </div>
                <div className={`rp-step-line ${step > 1 ? 'done' : ''}`} />
              </div>
              <div className="rp-step-item">
                <div className={`rp-step-dot ${stepDot(2)}`}>
                  {step > 2 ? '✓' : '2'}
                </div>
                <div className={`rp-step-line ${step > 2 ? 'done' : ''}`} />
              </div>
              <div className="rp-step-dot" style={{ flex: 0 }}>
                <div className={`rp-step-dot ${stepDot(3)}`} style={{ position: 'static' }}>
                  {step > 3 ? '✓' : '3'}
                </div>
              </div>
            </div>

            {/* ── Step 1: Conta ── */}
            {step === 1 && (
              <>
                <div className="rp-step-label">Passo 1 de 3</div>
                <div className="rp-step-title">Crie sua conta</div>
                <form onSubmit={handleCreateAccount}>
                  <div className="rp-fields">
                    <div>
                      <label className="rp-field-label">Nome completo</label>
                      <input className="rp-input" type="text" placeholder="Seu nome"
                        value={name} onChange={e => setName(e.target.value)}
                        autoComplete="name" disabled={loading} autoFocus />
                    </div>
                    <div>
                      <label className="rp-field-label">E-mail</label>
                      <input className="rp-input" type="email" placeholder="seu@email.com"
                        value={email} onChange={e => setEmail(e.target.value)}
                        autoComplete="email" disabled={loading} />
                    </div>
                    <div>
                      <label className="rp-field-label">Senha</label>
                      <input className="rp-input" type="password" placeholder="Mínimo 6 caracteres"
                        value={password} onChange={e => setPassword(e.target.value)}
                        autoComplete="new-password" disabled={loading} />
                    </div>
                  </div>
                  <button type="submit" className="rp-btn">
                    Continuar
                  </button>
                </form>
              </>
            )}

            {/* ── Step 2: Banco ── */}
            {step === 2 && (
              <>
                <div className="rp-step-label">Passo 2 de 3</div>
                <div className="rp-step-title">Conecte seu banco</div>
                <p className="rp-bank-info">
                  Conecte sua conta bancária para que o HIVE possa analisar<br />
                  seus dados e te dar insights reais.
                </p>
                <div className="rp-banks">
                  {BANKS.map(b => (
                    <div key={b.name} className="rp-bank-card">
                      <div className="rp-bank-icon" style={{ background: b.bg, color: b.fg }}>
                        {b.abbr}
                      </div>
                      <div>
                        <div className="rp-bank-name">{b.name}</div>
                        <div className="rp-bank-soon">Em breve</div>
                      </div>
                    </div>
                  ))}
                </div>
                <button className="rp-btn" onClick={() => setStep(3)}>
                  Conectar banco
                </button>
                <button className="rp-btn-outline" onClick={() => setStep(3)}>
                  Conectar mais tarde
                </button>
              </>
            )}

            {/* ── Step 3: Sucesso ── */}
            {step === 3 && (
              <div className="rp-success">
                <svg className="rp-success-hex" viewBox="0 0 180 200" fill="none">
                  <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="#7A5002"/>
                  <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="#D4A820"/>
                  <polygon points="100,16 110,22 110,178 100,184" fill="#090500"/>
                </svg>
                <div className="rp-success-title">Bem-vindo ao HIVE{name ? `, ${name.split(' ')[0]}` : ''}.</div>
                <p className="rp-success-sub">
                  Sua conta está pronta. Agora você tem acesso à inteligência financeira que os bancos não querem que você tenha.
                </p>
                <button className="rp-btn" onClick={() => navigate('/dashboard')}>
                  Entrar no HIVE →
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
