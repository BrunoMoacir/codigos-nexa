import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { API_BASE_URL } from '../api/client';

// ─── Slot-machine letter (ticker financeiro) ─────────────────────────────────
const SLOT_CHARS = ['$', '¥', '€', '%', '+', '#', '8', '4', '2', '1', '9', '6', '3', '7', '0', '5'];

const SlotLetter: React.FC<{ char: string; delay: number }> = ({ char, delay }) => {
  const outerRef = useRef<HTMLSpanElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const chars = [...SLOT_CHARS, char];

  useEffect(() => {
    const outer = outerRef.current;
    const track = trackRef.current;
    if (!outer || !track) return;
    // Começa invisible — nenhum char fica estático antes do spin
    outer.style.opacity = '0';
    const tid = setTimeout(() => {
      const h = outer.getBoundingClientRect().height;
      if (h > 0) {
        outer.style.transition = 'opacity 0.18s ease';
        outer.style.opacity = '1';
        track.style.transition = 'transform 1.1s cubic-bezier(0.16, 1, 0.3, 1)';
        track.style.transform = `translateY(-${(chars.length - 1) * h}px)`;
      }
    }, delay);
    return () => clearTimeout(tid);
  }, [chars.length, delay]);

  return (
    <span
      ref={outerRef}
      style={{ overflow: 'hidden', display: 'inline-block', height: '1em', verticalAlign: 'top', lineHeight: 1 }}
    >
      <div ref={trackRef} style={{ lineHeight: 1, willChange: 'transform' }}>
        {chars.map((c, i) => (
          <span key={i} style={{ display: 'block', height: '1em', lineHeight: 1, textAlign: 'center' }}>{c}</span>
        ))}
      </div>
    </span>
  );
};

// ─── Canvas de Colmeia ───────────────────────────────────────────────────────
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
    const SIZE = 28;
    const GAP = 5;
    const SQRT3 = Math.sqrt(3);
    const GLOW_R = 200;
    const WAVE_SPEED = 300;
    const WAVE_WIDTH = 65;

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
      const W = window.innerWidth;
      const H = window.innerHeight;
      const cw = (SIZE + GAP) * 1.5;
      const rh = SQRT3 * (SIZE + GAP * 0.5);
      for (let c = -1; c <= Math.ceil(W / cw) + 1; c++) {
        for (let r = -1; r <= Math.ceil(H / rh) + 1; r++) {
          hexes.push({
            cx: c * cw + SIZE,
            cy: r * rh + (c % 2 !== 0 ? rh / 2 : 0) + SIZE,
            phase: Math.random() * Math.PI * 2,
          });
        }
      }
    };

    resize();
    window.addEventListener('resize', resize);

    const drawHex = (cx: number, cy: number, r: number) => {
      ctx.beginPath();
      for (let i = 0; i < 6; i++) {
        const a = (Math.PI / 3) * i;
        const x = cx + r * Math.cos(a);
        const y = cy + r * Math.sin(a);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.closePath();
    };

    const t0 = performance.now();

    const frame = (now: number) => {
      const t = (now - t0) / 1000;
      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
      const { x: mx, y: my } = mouse.current;

      // Limpar clicks antigos
      clicks.current = clicks.current.filter(c => now - c.t < 1100);

      for (const h of hexes) {
        const dist = Math.hypot(h.cx - mx, h.cy - my);
        const hover = Math.max(0, 1 - dist / GLOW_R);

        // Ripples de clicks
        let ripple = 0;
        for (const ck of clicks.current) {
          const age = (now - ck.t) / 1000;
          const wave = age * WAVE_SPEED;
          const d = Math.hypot(h.cx - ck.x, h.cy - ck.y);
          const fromWave = Math.abs(d - wave);
          const r = Math.max(0, 1 - fromWave / WAVE_WIDTH) * Math.max(0, 1 - age * 1.2);
          ripple = Math.max(ripple, r);
        }

        const breathe = Math.sin(t * 0.65 + h.phase) * 0.5 + 0.5;
        const baseA = 0.012 + breathe * 0.022;
        const total = Math.max(hover, ripple);
        const s = SIZE - GAP * 0.5;

        drawHex(h.cx, h.cy, s);
        ctx.fillStyle = total > 0.02
          ? `rgba(212,168,32,${total * 0.28})`
          : `rgba(243,239,234,${baseA * 0.4})`;
        ctx.fill();

        drawHex(h.cx, h.cy, s);
        ctx.strokeStyle = total > 0.02
          ? `rgba(212,168,32,${0.08 + total * 0.85})`
          : `rgba(243,239,234,${baseA * 1.4})`;
        ctx.lineWidth = total > 0.15 ? 1.4 : 0.65;
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

  return (
    <canvas
      ref={canvasRef}
      style={{ position: 'fixed', inset: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 0 }}
    />
  );
};

// ─── CSS ─────────────────────────────────────────────────────────────────────
const css = `
  @import url('https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700,800,900&display=swap');
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  .lp-root {
    font-family: 'Satoshi', system-ui, sans-serif;
    min-height: 100vh;
    background: #0C0A08;
    color: #F3EFEA;
    position: relative;
    overflow: hidden;
  }

  /* ── Shimmer animation ── */
  @keyframes shimmer {
    0%   { background-position: 200% center; }
    100% { background-position: -200% center; }
  }
  @keyframes scramble-cursor {
    0%,100% { opacity: 1; }
    50%      { opacity: 0; }
  }
  @keyframes lp-fadeUp {
    from { opacity: 0; transform: translateY(22px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes pulse-ring {
    0%,100% { opacity: 0.18; transform: translate(-50%,-50%) scale(1); }
    50%      { opacity: 0.07; transform: translate(-50%,-50%) scale(1.06); }
  }

  /* ── Cursor glow ── */
  .lp-root::after {
    content: '';
    position: fixed;
    width: 600px; height: 600px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(212,168,32,0.06) 0%, transparent 65%);
    transform: translate(var(--cx,-9999px), var(--cy,-9999px)) translate(-50%,-50%);
    pointer-events: none; z-index: 1;
    transition: transform 0.08s linear;
  }

  /* ── Marca d'água HIVE enorme — une as duas colunas ── */
  .lp-wm {
    position: fixed;
    left: 50%; top: 50%;
    transform: translate(-50%, -50%);
    font-size: min(52vw, 520px);
    font-weight: 900;
    letter-spacing: -0.06em;
    color: transparent;
    -webkit-text-stroke: 1px rgba(212,168,32,0.04);
    pointer-events: none;
    z-index: 0;
    user-select: none;
    line-height: 1;
    white-space: nowrap;
  }

  /* ── Anel pulsante atrás do form ── */
  .lp-ring {
    position: fixed;
    width: 520px; height: 520px;
    border-radius: 50%;
    border: 1px solid rgba(212,168,32,0.1);
    left: 72%; top: 50%;
    transform: translate(-50%,-50%);
    pointer-events: none;
    z-index: 0;
    animation: pulse-ring 4s ease-in-out infinite;
  }
  .lp-ring::before {
    content: '';
    position: absolute;
    inset: 40px;
    border-radius: 50%;
    border: 1px solid rgba(212,168,32,0.06);
  }

  /* ── Layout ── */
  .lp-layout {
    position: relative;
    z-index: 2;
    display: grid;
    grid-template-columns: 1fr 400px;
    min-height: 100vh;
    padding: 52px 80px;
    gap: 0;
    align-items: center;
    max-width: 1280px;
    margin: 0 auto;
  }

  /* Linha vertical de conexão entre os dois lados */
  .lp-divider {
    position: absolute;
    left: calc(50% + 20px);
    top: 12%;
    height: 76%;
    width: 1px;
    background: linear-gradient(to bottom,
      transparent 0%,
      rgba(212,168,32,0.2) 25%,
      rgba(212,168,32,0.2) 75%,
      transparent 100%
    );
    z-index: 2;
    pointer-events: none;
  }
  /* Nó dourado no meio da linha */
  .lp-divider::after {
    content: '';
    position: absolute;
    left: 50%; top: 50%;
    transform: translate(-50%,-50%);
    width: 5px; height: 5px;
    border-radius: 50%;
    background: #D4A820;
    box-shadow: 0 0 10px rgba(212,168,32,0.6);
  }

  /* ── ESQUERDO ── */
  .lp-left {
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    min-height: calc(100vh - 104px);
    padding-right: 32px;
    animation: lp-fadeUp 0.7s cubic-bezier(.16,1,.3,1) both;
  }

  /* Logo com shimmer */
  .lp-logo {
    display: flex;
    align-items: center;
    gap: 14px;
  }
  .lp-logo-word {
    font-size: 2.2rem;
    font-weight: 900;
    letter-spacing: 0.03em;
    color: #D4A820;
    font-variant-numeric: tabular-nums;
    line-height: 1;
    display: inline-flex;
    align-items: flex-start;
    gap: 0;
  }

  .lp-hero { flex: 1; display: flex; flex-direction: column; justify-content: center; }

  .lp-headline {
    font-size: clamp(3.8rem, 6vw, 6.5rem);
    font-weight: 900;
    line-height: 0.9;
    letter-spacing: -0.05em;
    text-transform: uppercase;
    color: #F3EFEA;
    margin-bottom: 32px;
  }

  /* "FILTRO." com shimmer de ouro */
  .lp-headline em {
    font-style: normal;
    display: block;
    background: linear-gradient(100deg, #C89010 0%, #F8E060 30%, #D4A820 55%, #F8E060 78%, #C89010 100%);
    background-size: 400% auto;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    animation: shimmer 3.5s linear infinite;
    position: relative;
    width: fit-content;
  }

  .lp-sub {
    font-size: 0.95rem;
    font-weight: 400;
    line-height: 1.8;
    color: rgba(243,239,234,0.68);
    max-width: 340px;
  }

  .lp-tags {
    display: flex;
    gap: 8px;
    margin-top: 28px;
  }
  .lp-tag {
    font-size: 0.63rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.3);
    border: 1px solid rgba(243,239,234,0.1);
    border-radius: 20px;
    padding: 4px 10px;
  }

  .lp-footer {
    font-size: 0.72rem;
    color: rgba(243,239,234,0.48);
    letter-spacing: 0.04em;
  }

  /* ── DIREITO ── */
  .lp-right {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    justify-content: center;
    animation: lp-fadeUp 0.7s cubic-bezier(.16,1,.3,1) 0.12s both;
  }
  .lp-right-inner {
    width: 100%;
    display: flex;
    flex-direction: column;
    align-items: stretch;
  }
  .lp-help-row {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 10px;
  }

  .lp-card {
    width: 100%;
    background: rgba(16, 13, 9, 0.94);
    border: 1px solid rgba(212,168,32,0.28);
    border-radius: 20px;
    padding: 28px 30px 26px;
    position: relative;
    overflow: hidden;
    box-shadow: 0 0 0 1px rgba(212,168,32,0.06), 0 8px 40px rgba(0,0,0,0.5), 0 0 60px rgba(212,168,32,0.04);
  }
  /* Linha dourada topo — mais visível */
  .lp-card::before {
    content: '';
    position: absolute;
    top: 0; left: 8%; right: 8%;
    height: 2px;
    background: linear-gradient(90deg, transparent, rgba(212,168,32,0.85), transparent);
    border-radius: 0 0 2px 2px;
  }

  .lp-card-title {
    font-size: 1.25rem;
    font-weight: 800;
    color: #F3EFEA;
    letter-spacing: -0.025em;
    margin-bottom: 4px;
  }
  .lp-card-sub {
    font-size: 0.78rem;
    color: rgba(243,239,234,0.45);
    margin-bottom: 18px;
    font-weight: 400;
  }

  .lp-fields { display: flex; flex-direction: column; gap: 14px; margin-bottom: 22px; }
  .lp-field-label {
    display: block;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.5);
    margin-bottom: 7px;
  }
  .lp-input {
    width: 100%;
    padding: 12px 16px;
    background: rgba(243,239,234,0.04);
    color: #F3EFEA;
    border: 1px solid rgba(243,239,234,0.1);
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.9rem;
    outline: none;
    transition: border-color 0.15s, background 0.15s;
  }
  .lp-input::placeholder { color: rgba(243,239,234,0.25); }
  .lp-input:focus { border-color: rgba(212,168,32,0.5); background: rgba(212,168,32,0.03); }
  .lp-input.err { border-color: rgba(240,122,100,0.55); background: rgba(240,122,100,0.04); }
  .lp-field-err {
    font-size: 0.7rem;
    color: #F07A64;
    margin-top: 5px;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 5px;
  }
  .lp-field-err::before { content: none; }

  .lp-btn {
    width: 100%;
    padding: 14px;
    background: linear-gradient(135deg, #C89010, #D4A820, #E8C030);
    background-size: 200% auto;
    color: #0A0800;
    border: none;
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.85rem;
    font-weight: 900;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    cursor: pointer;
    transition: background-position 0.3s, transform 0.12s, box-shadow 0.2s;
    margin-bottom: 14px;
    box-shadow: 0 4px 20px rgba(212,168,32,0.2);
  }
  .lp-btn:hover:not(:disabled) {
    background-position: right center;
    transform: translateY(-1px);
    box-shadow: 0 6px 28px rgba(212,168,32,0.35);
  }
  .lp-btn:active:not(:disabled) { transform: translateY(0); }
  .lp-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  .lp-note {
    text-align: center;
    font-size: 0.75rem;
    color: rgba(243,239,234,0.45);
    line-height: 1.65;
  }
  .lp-separator { height: 1px; background: rgba(243,239,234,0.07); margin: 18px 0; }

  .lp-help-link {
    font-size: 0.82rem;
    color: rgba(243,239,234,0.7);
    text-decoration: none;
    font-weight: 600;
    transition: color 0.15s;
    white-space: nowrap;
  }
  .lp-help-link:hover { color: #D4A820; }

  .lp-btn-register {
    display: block;
    width: 100%;
    padding: 13px;
    background: transparent;
    color: #D4A820;
    border: 1px solid rgba(212,168,32,0.22);
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.85rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    text-align: center;
    text-decoration: none;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
  }
  .lp-btn-register:hover {
    border-color: rgba(212,168,32,0.5);
    background: rgba(212,168,32,0.06);
  }

  @media (max-width: 860px) {
    .lp-layout { grid-template-columns: 1fr; padding: 36px 24px 48px; gap: 44px; max-width: none; }
    .lp-left { min-height: auto; padding-right: 0; gap: 28px; justify-content: flex-start; }
    .lp-divider, .lp-ring { display: none; }
    .lp-headline { font-size: clamp(3rem, 12vw, 4.2rem); }
    .lp-right { justify-content: stretch; }
  }
`;

// ─── LoginPage ────────────────────────────────────────────────────────────────
export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errs, setErrs] = useState({ email: false, password: false });

  // CSS var para cursor glow
  useEffect(() => {
    const mm = (e: MouseEvent) => {
      document.documentElement.style.setProperty('--cx', `${e.clientX}px`);
      document.documentElement.style.setProperty('--cy', `${e.clientY}px`);
    };
    window.addEventListener('mousemove', mm);
    return () => window.removeEventListener('mousemove', mm);
  }, []);

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    const newErrs = { email: !loginEmail.trim(), password: !loginPassword.trim() };
    setErrs(newErrs);
    if (newErrs.email || newErrs.password) return;
    navigate('/dashboard');
  };

  return (
    <>
      <style>{css}</style>
      <div className="lp-root">
        <HoneycombCanvas />

        {/* Marca d'água HIVE gigante — une as duas colunas */}
        <div className="lp-wm" aria-hidden="true">HIVE</div>

        {/* Anel pulsante no lado do form */}
        <div className="lp-ring" aria-hidden="true" />

        <div className="lp-layout">
          {/* ── ESQUERDO ── */}
          <div className="lp-left">
            <div className="lp-logo">
              <svg width="32" height="36" viewBox="0 0 180 200" fill="none">
                <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="#7A5002"/>
                <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="#D4A820"/>
                <polygon points="100,16 110,22 110,178 100,184" fill="#090500"/>
              </svg>
              <span className="lp-logo-word">
                {'HIVE'.split('').map((ch, i) => (
                  <SlotLetter key={i} char={ch} delay={400 + i * 130} />
                ))}
              </span>
            </div>

            <div className="lp-hero">
              <h1 className="lp-headline">
                Finanças<br />
                sem<br />
                <em>filtro.</em>
              </h1>
              <p className="lp-sub">
                Conecte suas contas e veja tudo que o banco não te conta sobre o seu próprio dinheiro.
              </p>
            </div>

            <div className="lp-footer">© 2025 HIVE · Todos os direitos reservados</div>
          </div>

          {/* ── DIREITO — form ── */}
          <div className="lp-right">
            <div className="lp-right-inner">
            <div className="lp-help-row">
              <a href="/contact" className="lp-help-link">Precisa de ajuda?</a>
            </div>
            <div className="lp-card">
              <div className="lp-card-title">Acesso ao painel</div>
              <div className="lp-card-sub">Entre com seus dados para continuar.</div>

              <form onSubmit={handleLogin}>
                <div className="lp-fields">
                  <div>
                    <label className="lp-field-label">E-mail</label>
                    <input
                      className={`lp-input${errs.email ? ' err' : ''}`}
                      type="email" placeholder="seu@email.com"
                      value={loginEmail}
                      onChange={e => { setLoginEmail(e.target.value); if (errs.email) setErrs(p => ({...p, email: false})); }}
                      autoComplete="email" disabled={loading}
                    />
                    {errs.email && <div className="lp-field-err">Preencha o e-mail</div>}
                  </div>
                  <div>
                    <label className="lp-field-label">Senha</label>
                    <input
                      className={`lp-input${errs.password ? ' err' : ''}`}
                      type="password" placeholder="••••••••"
                      value={loginPassword}
                      onChange={e => { setLoginPassword(e.target.value); if (errs.password) setErrs(p => ({...p, password: false})); }}
                      autoComplete="current-password" disabled={loading}
                    />
                    {errs.password && <div className="lp-field-err">Preencha a senha</div>}
                  </div>
                </div>
                <button type="submit" className="lp-btn" disabled={loading}>
                  {loading ? 'Entrando…' : 'Acessar painel'}
                </button>
              </form>

              <div className="lp-separator" />
              <Link to="/register" className="lp-btn-register">Criar uma conta</Link>
            </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};
