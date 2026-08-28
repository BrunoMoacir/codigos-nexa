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
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800;900&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  .lp-root {
    font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
    min-height: 100vh;
    background: #0C0A08;
    color: #F3EFEA;
    position: relative;
    overflow: hidden;
  }

  /* Cursor glow suave — segue o mouse via CSS var */
  .lp-root::after {
    content: '';
    position: fixed;
    width: 480px;
    height: 480px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(212,168,32,0.045) 0%, transparent 65%);
    transform: translate(var(--cx,-9999px), var(--cy,-9999px)) translate(-50%,-50%);
    pointer-events: none;
    z-index: 1;
    transition: transform 0.06s linear;
  }

  /* Layout */
  .lp-layout {
    position: relative;
    z-index: 2;
    display: grid;
    grid-template-columns: 1fr 440px;
    min-height: 100vh;
    padding: 44px 96px 44px 52px;
    gap: 40px;
  }

  /* ── ESQUERDO ── */
  .lp-left {
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }

  /* Logo + HIVE grandão no topo */
  .lp-logo {
    display: flex;
    align-items: center;
    gap: 16px;
    animation: lp-fadeUp 0.6s cubic-bezier(.16,1,.3,1) both;
  }
  .lp-logo-word {
    font-size: 3.2rem;
    font-weight: 900;
    letter-spacing: 0.14em;
    color: #D4A820;
    line-height: 1;
  }

  .lp-hero {
    padding: 0 0 20px;
    animation: lp-fadeUp 0.75s cubic-bezier(.16,1,.3,1) 0.1s both;
  }

  .lp-headline {
    font-size: clamp(3.4rem, 5.8vw, 6rem);
    font-weight: 900;
    line-height: 0.93;
    letter-spacing: -0.04em;
    text-transform: uppercase;
    color: #F3EFEA;
    margin-bottom: 28px;
  }

  .lp-headline em {
    font-style: normal;
    color: #D4A820;
    display: block;
  }

  .lp-sub {
    font-size: 0.92rem;
    font-weight: 400;
    line-height: 1.8;
    color: rgba(243,239,234,0.62);
    max-width: 360px;
  }

  .lp-footer {
    font-size: 0.68rem;
    color: rgba(243,239,234,0.15);
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
    background: #100E0C;
    border: 1px solid rgba(243,239,234,0.09);
    border-radius: 20px;
    padding: 32px 30px 28px;
  }

  .lp-card-title {
    font-size: 1.15rem;
    font-weight: 800;
    color: #F3EFEA;
    letter-spacing: -0.02em;
    margin-bottom: 4px;
  }
  .lp-card-sub {
    font-size: 0.75rem;
    color: rgba(243,239,234,0.3);
    margin-bottom: 24px;
  }

  /* Fields */
  .lp-fields { display: flex; flex-direction: column; gap: 11px; margin-bottom: 18px; }
  .lp-field-label {
    display: block;
    font-size: 0.66rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.35);
    margin-bottom: 5px;
  }
  .lp-input {
    width: 100%;
    padding: 11px 14px;
    background: #1A1612;
    color: #F3EFEA;
    border: 1px solid rgba(243,239,234,0.1);
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.87rem;
    outline: none;
    transition: border-color 0.15s;
  }
  .lp-input::placeholder { color: rgba(243,239,234,0.22); }
  .lp-input:focus {
    border-color: rgba(212,168,32,0.5);
    background: #1E1A16;
  }

  /* Botão */
  .lp-btn {
    width: 100%;
    padding: 13px;
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
    margin-bottom: 14px;
  }
  .lp-btn:hover:not(:disabled) { background: #EAC02C; transform: translateY(-1px); }
  .lp-btn:active:not(:disabled) { transform: translateY(0); }
  .lp-btn:disabled { opacity: 0.3; cursor: not-allowed; }

  .lp-note {
    text-align: center;
    font-size: 0.65rem;
    color: rgba(243,239,234,0.15);
    line-height: 1.65;
    margin-bottom: 0;
  }

  .lp-separator {
    height: 1px;
    background: rgba(243,239,234,0.07);
    margin: 18px 0;
  }

  .lp-btn-register {
    display: block;
    width: 100%;
    padding: 13px;
    background: transparent;
    color: rgba(243,239,234,0.65);
    border: 1px solid rgba(243,239,234,0.14);
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.84rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-align: center;
    text-decoration: none;
    cursor: pointer;
    transition: border-color 0.15s, color 0.15s, background 0.15s;
  }
  .lp-btn-register:hover {
    border-color: rgba(212,168,32,0.35);
    color: #D4A820;
    background: rgba(212,168,32,0.05);
  }

  /* Decorativo — círculo canto superior direito (igual roon) */
  .lp-deco {
    position: fixed;
    top: -80px;
    right: -80px;
    width: 300px;
    height: 300px;
    border-radius: 50%;
    border: 1px solid rgba(212,168,32,0.06);
    pointer-events: none;
    z-index: 2;
  }
  .lp-deco::after {
    content: '';
    position: absolute;
    inset: 20px;
    border-radius: 50%;
    border: 1px solid rgba(212,168,32,0.04);
  }

  /* Animações */
  @keyframes lp-fadeUp {
    from { opacity: 0; transform: translateY(24px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  /* Mobile */
  @media (max-width: 860px) {
    .lp-layout {
      grid-template-columns: 1fr;
      padding: 36px 24px 48px;
      gap: 48px;
    }
    .lp-left { gap: 32px; }
    .lp-footer { order: 99; }
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

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!loginEmail || !loginPassword) { toast.error('Preencha e-mail e senha.'); return; }
    setLoading(true);
    const tid = toast.loading('Entrando…');
    try {
      const body = new URLSearchParams();
      body.append('username', loginEmail);
      body.append('password', loginPassword);
      const res = await fetch(`${API_BASE_URL}/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body,
      });
      if (res.ok) {
        const data = await res.json();
        localStorage.setItem('jwt_token', data.access_token);
        localStorage.setItem('user_id', data.user_id);
        localStorage.setItem('user_email', loginEmail);
        localStorage.setItem('nexa_data_origin', 'real');
        localStorage.setItem('nexa_data_origin_updated_at', new Date().toISOString());
        if (data.full_name) localStorage.setItem('user_name', data.full_name);
        toast.success('Bem-vindo ao HIVE', { id: tid });
        setTimeout(() => navigate('/chat'), 400);
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Credenciais inválidas', { id: tid });
      }
    } catch {
      toast.error('Erro de conexão', { id: tid });
    } finally { setLoading(false); }
  };

  return (
    <>
      <style>{css}</style>
      <div className="lp-root">
        <HoneycombCanvas />
        <div className="lp-deco" />

        <div className="lp-layout">
          {/* ── ESQUERDO ── */}
          <div className="lp-left">

            {/* Logo */}
            <div className="lp-logo">
              <svg width="44" height="50" viewBox="0 0 180 200" fill="none">
                {/* Hexágono pointy-top: igual aos da colmeia, com efeito 3D */}
                {/* Base âmbar escura (face direita) */}
                <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="#7A5002"/>
                {/* Face esquerda — ouro claro */}
                <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="#D4A820"/>
                {/* Faixa central escura */}
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
                Conecte suas contas e veja tudo que o banco<br />
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
