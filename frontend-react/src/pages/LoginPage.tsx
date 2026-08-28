import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { API_BASE_URL } from '../api/client';

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
    const SIZE = 22;
    const GAP = 5;
    const SQRT3 = Math.sqrt(3);
    const GLOW_R = 150;
    const WAVE_SPEED = 260;
    const WAVE_WIDTH = 50;

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
          ? `rgba(212,168,32,${total * 0.2})`
          : `rgba(243,239,234,${baseA * 0.35})`;
        ctx.fill();

        drawHex(h.cx, h.cy, s);
        ctx.strokeStyle = total > 0.02
          ? `rgba(212,168,32,${0.05 + total * 0.7})`
          : `rgba(243,239,234,${baseA})`;
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
    display: flex;
    align-items: center;
    justify-content: center;
  }

  /* Cursor glow suave */
  .lp-root::after {
    content: '';
    position: fixed;
    width: 520px;
    height: 520px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(212,168,32,0.055) 0%, transparent 65%);
    transform: translate(var(--cx,-9999px), var(--cy,-9999px)) translate(-50%,-50%);
    pointer-events: none;
    z-index: 1;
    transition: transform 0.06s linear;
  }

  /* Layout centralizado */
  .lp-layout {
    position: relative;
    z-index: 2;
    display: grid;
    grid-template-columns: 1fr 400px;
    width: 100%;
    max-width: 1020px;
    min-height: 100vh;
    padding: 56px 52px;
    gap: 56px;
    align-items: center;
  }

  /* ── ESQUERDO ── */
  .lp-left {
    display: flex;
    flex-direction: column;
    gap: 40px;
  }

  .lp-logo {
    display: flex;
    align-items: center;
    gap: 14px;
    animation: lp-fadeUp 0.6s cubic-bezier(.16,1,.3,1) both;
  }
  .lp-logo-word {
    font-size: 1.6rem;
    font-weight: 900;
    letter-spacing: 0.18em;
    color: #D4A820;
    line-height: 1;
  }

  .lp-hero {
    animation: lp-fadeUp 0.75s cubic-bezier(.16,1,.3,1) 0.1s both;
  }

  .lp-headline {
    font-size: clamp(3.2rem, 5.2vw, 5.4rem);
    font-weight: 900;
    line-height: 0.93;
    letter-spacing: -0.04em;
    text-transform: uppercase;
    color: #F3EFEA;
    margin-bottom: 24px;
  }
  .lp-headline em {
    font-style: normal;
    color: #D4A820;
    display: block;
    position: relative;
    width: fit-content;
  }
  .lp-headline em::after {
    content: '';
    position: absolute;
    left: 0;
    bottom: -6px;
    width: 100%;
    height: 3px;
    background: rgba(212,168,32,0.35);
    border-radius: 2px;
  }

  .lp-sub {
    font-size: 0.93rem;
    font-weight: 400;
    line-height: 1.75;
    color: rgba(243,239,234,0.55);
    max-width: 380px;
  }

  .lp-footer {
    font-size: 0.7rem;
    color: rgba(243,239,234,0.38);
    letter-spacing: 0.04em;
    animation: lp-fadeUp 0.75s cubic-bezier(.16,1,.3,1) 0.3s both;
  }

  /* ── DIREITO — form ── */
  .lp-right {
    display: flex;
    align-items: center;
    animation: lp-fadeUp 0.75s cubic-bezier(.16,1,.3,1) 0.15s both;
  }

  .lp-card {
    width: 100%;
    background: #131008;
    border: 1px solid rgba(243,239,234,0.11);
    border-radius: 20px;
    padding: 32px 28px;
  }

  .lp-card-title {
    font-size: 1.2rem;
    font-weight: 800;
    color: #F3EFEA;
    letter-spacing: -0.02em;
    margin-bottom: 5px;
  }
  .lp-card-sub {
    font-size: 0.78rem;
    color: rgba(243,239,234,0.5);
    margin-bottom: 24px;
    font-weight: 400;
  }

  /* Fields */
  .lp-fields { display: flex; flex-direction: column; gap: 12px; margin-bottom: 20px; }
  .lp-field-label {
    display: block;
    font-size: 0.67rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.55);
    margin-bottom: 6px;
  }
  .lp-input {
    width: 100%;
    padding: 12px 14px;
    background: rgba(243,239,234,0.05);
    color: #F3EFEA;
    border: 1px solid rgba(243,239,234,0.12);
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.9rem;
    outline: none;
    transition: border-color 0.15s, background 0.15s;
  }
  .lp-input::placeholder { color: rgba(243,239,234,0.28); }
  .lp-input:focus {
    border-color: rgba(212,168,32,0.55);
    background: rgba(212,168,32,0.04);
  }

  /* Botão principal */
  .lp-btn {
    width: 100%;
    padding: 14px;
    background: #D4A820;
    color: #0A0800;
    border: none;
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.85rem;
    font-weight: 900;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    cursor: pointer;
    transition: background 0.15s, transform 0.12s;
    margin-bottom: 12px;
  }
  .lp-btn:hover:not(:disabled) { background: #EAC02C; transform: translateY(-1px); }
  .lp-btn:active:not(:disabled) { transform: translateY(0); }
  .lp-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  .lp-note {
    text-align: center;
    font-size: 0.67rem;
    color: rgba(243,239,234,0.35);
    line-height: 1.65;
  }

  .lp-separator {
    height: 1px;
    background: rgba(243,239,234,0.08);
    margin: 18px 0;
  }

  /* Botão criar conta */
  .lp-btn-register {
    display: block;
    width: 100%;
    padding: 13px;
    background: transparent;
    color: rgba(243,239,234,0.85);
    border: 1px solid rgba(243,239,234,0.18);
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.85rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    text-align: center;
    text-decoration: none;
    cursor: pointer;
    transition: border-color 0.15s, color 0.15s, background 0.15s;
  }
  .lp-btn-register:hover {
    border-color: rgba(212,168,32,0.4);
    color: #D4A820;
    background: rgba(212,168,32,0.05);
  }

  /* Animações */
  @keyframes lp-fadeUp {
    from { opacity: 0; transform: translateY(20px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  /* Mobile */
  @media (max-width: 860px) {
    .lp-root { align-items: flex-start; }
    .lp-layout {
      grid-template-columns: 1fr;
      padding: 36px 24px 48px;
      gap: 44px;
      min-height: 100vh;
    }
    .lp-left { gap: 28px; }
    .lp-headline { font-size: clamp(2.8rem, 11vw, 4rem); }
  }
`;

// ─── LoginPage ────────────────────────────────────────────────────────────────
export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [loading, setLoading] = useState(false);

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
    navigate('/dashboard');
  };

  return (
    <>
      <style>{css}</style>
      <div className="lp-root">
        <HoneycombCanvas />

        <div className="lp-layout">
          {/* ── ESQUERDO ── */}
          <div className="lp-left">

            {/* Logo */}
            <div className="lp-logo">
              <svg width="28" height="32" viewBox="0 0 180 200" fill="none">
                <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="#7A5002"/>
                <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="#D4A820"/>
                <polygon points="100,16 110,22 110,178 100,184" fill="#090500"/>
              </svg>
              <span className="lp-logo-word">HIVE</span>
            </div>

            <div className="lp-hero">
              <h1 className="lp-headline">
                Finanças<br />
                sem<br />
                <em>filtro.</em>
              </h1>
              <p className="lp-sub">
                Conecte suas contas e veja tudo que o banco
                não te conta sobre o seu próprio dinheiro.
              </p>
            </div>

            <div className="lp-footer">© 2025 HIVE · Todos os direitos reservados</div>
          </div>

          {/* ── DIREITO — form ── */}
          <div className="lp-right">
            <div className="lp-card">
              <div className="lp-card-title">Acesso ao painel</div>
              <div className="lp-card-sub">Entre com seus dados para continuar.</div>

              <form onSubmit={handleLogin}>
                <div className="lp-fields">
                  <div>
                    <label className="lp-field-label">E-mail</label>
                    <input className="lp-input" type="email" placeholder="seu@email.com"
                      value={loginEmail} onChange={e => setLoginEmail(e.target.value)}
                      autoComplete="email" disabled={loading} />
                  </div>
                  <div>
                    <label className="lp-field-label">Senha</label>
                    <input className="lp-input" type="password" placeholder="••••••••"
                      value={loginPassword} onChange={e => setLoginPassword(e.target.value)}
                      autoComplete="current-password" disabled={loading} />
                  </div>
                </div>
                <button type="submit" className="lp-btn" disabled={loading}>
                  {loading ? 'Entrando…' : 'Acessar painel'}
                </button>
              </form>

              <div className="lp-note">Ao entrar você aceita os Termos de Uso.</div>

              <div className="lp-separator" />

              <Link to="/register" className="lp-btn-register">
                Criar uma conta
              </Link>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};
