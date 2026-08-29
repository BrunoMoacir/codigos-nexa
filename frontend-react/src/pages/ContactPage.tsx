import React, { useState } from 'react';
import { Link } from 'react-router-dom';

const css = `
  @import url('https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700,800,900&display=swap');
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  .cp-root {
    font-family: 'Satoshi', system-ui, sans-serif;
    min-height: 100vh;
    background: #0C0A08;
    color: #F3EFEA;
    display: grid;
    grid-template-columns: 480px 1fr;
  }

  @keyframes cp-up {
    from { opacity: 0; transform: translateY(14px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes pulse-dot {
    0%,100% { opacity: 1; }
    50% { opacity: 0.4; }
  }
  @keyframes shimmer-dash {
    0%   { background-position: 200% center; }
    100% { background-position: -200% center; }
  }
  @keyframes float {
    0%,100% { transform: translateY(0); }
    50%      { transform: translateY(-6px); }
  }

  /* ── ESQUERDO — formulário ── */
  .cp-left {
    padding: 52px 56px 48px;
    display: flex;
    flex-direction: column;
    border-right: 1px solid rgba(243,239,234,0.07);
    animation: cp-up 0.5s cubic-bezier(.16,1,.3,1) both;
  }

  .cp-logo {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 56px;
  }
  .cp-logo-name {
    font-size: 0.92rem;
    font-weight: 900;
    letter-spacing: 0.08em;
    color: #D4A820;
  }

  .cp-eyebrow {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: rgba(212,168,32,0.7);
    margin-bottom: 14px;
  }
  .cp-eyebrow-dot {
    width: 5px; height: 5px;
    border-radius: 50%;
    background: #D4A820;
    animation: pulse-dot 2.5s ease-in-out infinite;
  }

  .cp-title {
    font-size: clamp(2rem, 3.2vw, 2.6rem);
    font-weight: 900;
    letter-spacing: -0.05em;
    line-height: 1.08;
    color: #F3EFEA;
    margin-bottom: 14px;
  }
  /* Palavra em itálico dourado — igual à ref */
  .cp-title em {
    font-style: italic;
    color: #D4A820;
  }

  .cp-sub {
    font-size: 0.85rem;
    color: rgba(243,239,234,0.42);
    line-height: 1.7;
    margin-bottom: 36px;
    max-width: 340px;
  }

  /* Form fields */
  .cp-form { flex: 1; display: flex; flex-direction: column; }
  .cp-row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .cp-fields { display: flex; flex-direction: column; gap: 14px; margin-bottom: 28px; }

  .cp-label {
    display: block;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.45);
    margin-bottom: 7px;
  }
  .cp-input {
    width: 100%;
    padding: 11px 14px;
    background: rgba(243,239,234,0.04);
    color: #F3EFEA;
    border: 1px solid rgba(243,239,234,0.1);
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.88rem;
    outline: none;
    transition: border-color 0.15s, box-shadow 0.15s;
    resize: none;
  }
  .cp-input::placeholder { color: rgba(243,239,234,0.2); }
  .cp-input:focus {
    border-color: rgba(212,168,32,0.5);
    box-shadow: 0 0 0 3px rgba(212,168,32,0.07);
  }
  .cp-input.err { border-color: rgba(240,122,100,0.55); }
  .cp-field-err { font-size: 0.68rem; color: #F07A64; margin-top: 4px; font-weight: 500; }

  /* Botão de envio — largo, igual à ref */
  .cp-btn {
    width: 100%;
    padding: 14px;
    background: #F3EFEA;
    color: #0C0A08;
    border: none;
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.88rem;
    font-weight: 800;
    letter-spacing: 0.02em;
    cursor: pointer;
    transition: background 0.15s, transform 0.12s;
    margin-bottom: 16px;
  }
  .cp-btn:hover:not(:disabled) { background: #D4A820; transform: translateY(-1px); }
  .cp-btn:disabled { opacity: 0.35; cursor: not-allowed; }

  /* Email de contato no rodapé do form */
  .cp-contact-email {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-size: 0.78rem;
    color: rgba(243,239,234,0.38);
    text-decoration: none;
    transition: color 0.15s;
  }
  .cp-contact-email:hover { color: rgba(243,239,234,0.7); }

  .cp-back {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 0.75rem;
    font-weight: 500;
    color: rgba(243,239,234,0.3);
    text-decoration: none;
    margin-top: 12px;
    transition: color 0.15s;
  }
  .cp-back:hover { color: rgba(243,239,234,0.6); }

  /* ── DIREITO — dashboard preview ── */
  .cp-right {
    background: #0A0806;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 48px 40px;
    position: relative;
    overflow: hidden;
    animation: cp-up 0.5s cubic-bezier(.16,1,.3,1) 0.1s both;
  }

  /* Glow dourado de fundo */
  .cp-right::before {
    content: '';
    position: absolute;
    width: 500px; height: 500px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(212,168,32,0.06) 0%, transparent 65%);
    top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    pointer-events: none;
  }

  /* Frame do dashboard — igual ao card da referência */
  .cp-dash-frame {
    width: 100%;
    max-width: 580px;
    background: #17140F;
    border: 1px solid rgba(212,168,32,0.18);
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 32px 80px rgba(0,0,0,0.6), 0 0 0 1px rgba(212,168,32,0.06);
    animation: float 5s ease-in-out infinite;
    position: relative;
    z-index: 1;
  }

  /* Barra de título do "browser" */
  .cp-dash-titlebar {
    padding: 10px 14px;
    background: #0F0D0A;
    border-bottom: 1px solid rgba(243,239,234,0.06);
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .cp-dot-r { width: 8px; height: 8px; border-radius: 50%; background: rgba(240,122,100,0.5); }
  .cp-dot-y { width: 8px; height: 8px; border-radius: 50%; background: rgba(236,176,64,0.5); }
  .cp-dot-g { width: 8px; height: 8px; border-radius: 50%; background: rgba(46,200,164,0.5); }
  .cp-url-bar {
    flex: 1;
    margin: 0 12px;
    height: 20px;
    background: rgba(243,239,234,0.05);
    border-radius: 4px;
    display: flex;
    align-items: center;
    padding: 0 10px;
    font-size: 0.62rem;
    color: rgba(243,239,234,0.25);
  }

  /* Layout interno do mock dashboard */
  .cp-dash-inner {
    display: grid;
    grid-template-columns: 140px 1fr;
    height: 360px;
  }
  .cp-dash-sidebar {
    background: #0F0D0A;
    border-right: 1px solid rgba(243,239,234,0.05);
    padding: 16px 12px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .cp-dash-nav-logo {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 8px;
    margin-bottom: 10px;
  }
  .cp-dash-nav-logo span {
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0.06em;
    color: #D4A820;
  }
  .cp-dash-nav-item {
    height: 26px;
    border-radius: 6px;
    background: rgba(243,239,234,0.04);
    display: flex;
    align-items: center;
    padding: 0 8px;
    gap: 7px;
  }
  .cp-dash-nav-item.active {
    background: rgba(212,168,32,0.12);
    border: 1px solid rgba(212,168,32,0.15);
  }
  .cp-dash-nav-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: rgba(243,239,234,0.15);
    flex-shrink: 0;
  }
  .cp-dash-nav-item.active .cp-dash-nav-dot { background: #D4A820; }
  .cp-dash-nav-line {
    flex: 1;
    height: 5px;
    border-radius: 3px;
    background: rgba(243,239,234,0.07);
  }
  .cp-dash-nav-item.active .cp-dash-nav-line {
    background: rgba(212,168,32,0.35);
  }

  .cp-dash-content {
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  /* KPI cards */
  .cp-dash-kpis {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 8px;
  }
  .cp-dash-kpi {
    background: rgba(243,239,234,0.04);
    border: 1px solid rgba(243,239,234,0.07);
    border-radius: 8px;
    padding: 10px;
  }
  .cp-dash-kpi-label {
    font-size: 0.5rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.3);
    margin-bottom: 6px;
  }
  .cp-dash-kpi-val {
    font-size: 1rem;
    font-weight: 900;
    letter-spacing: -0.04em;
    color: #F3EFEA;
    margin-bottom: 3px;
  }
  .cp-dash-kpi-sub {
    font-size: 0.48rem;
    color: #2EC8A4;
    font-weight: 700;
  }

  /* Área do gráfico mock */
  .cp-dash-chart {
    background: rgba(243,239,234,0.03);
    border: 1px solid rgba(243,239,234,0.06);
    border-radius: 8px;
    padding: 12px;
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .cp-dash-chart-title {
    font-size: 0.6rem;
    font-weight: 700;
    color: rgba(243,239,234,0.45);
  }
  .cp-dash-chart-area {
    flex: 1;
    position: relative;
  }
  .cp-dash-chart-area svg { width: 100%; height: 100%; }

  /* Linha rows mock */
  .cp-dash-rows {
    display: flex;
    flex-direction: column;
    gap: 5px;
  }
  .cp-dash-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 8px;
    background: rgba(243,239,234,0.03);
    border-radius: 5px;
  }
  .cp-dash-row-av {
    width: 16px; height: 16px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .cp-dash-row-info { flex: 1; display: flex; flex-direction: column; gap: 2px; }
  .cp-dash-row-name { height: 5px; border-radius: 3px; background: rgba(243,239,234,0.12); width: 70%; }
  .cp-dash-row-sub  { height: 4px; border-radius: 3px; background: rgba(243,239,234,0.06); width: 45%; }
  .cp-dash-row-val  { font-size: 0.55rem; font-weight: 700; color: #D4A820; }

  /* Texto "em breve" sobre o preview */
  .cp-dash-overlay {
    position: absolute;
    bottom: 14px;
    right: 14px;
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: rgba(212,168,32,0.45);
    background: rgba(16,13,9,0.85);
    border: 1px solid rgba(212,168,32,0.15);
    border-radius: 6px;
    padding: 4px 9px;
  }

  /* Sucesso */
  .cp-sent {
    display: flex; flex-direction: column; align-items: flex-start;
    animation: cp-up 0.45s cubic-bezier(.16,1,.3,1) both;
  }
  .cp-sent-icon {
    width: 48px; height: 48px; border-radius: 50%;
    background: rgba(46,200,164,0.1); border: 1px solid rgba(46,200,164,0.28);
    display: flex; align-items: center; justify-content: center; margin-bottom: 18px;
  }
  .cp-sent-title { font-size: 1.6rem; font-weight: 900; color: #F3EFEA; letter-spacing: -0.04em; margin-bottom: 8px; }
  .cp-sent-sub { font-size: 0.82rem; color: rgba(243,239,234,0.42); line-height: 1.7; max-width: 320px; margin-bottom: 24px; }

  @media (max-width: 900px) {
    .cp-root { grid-template-columns: 1fr; }
    .cp-right { display: none; }
    .cp-left { padding: 36px 28px 48px; }
  }
`;

function HiveLogo({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={Math.round(size * 1.11)} viewBox="0 0 180 200" fill="none">
      <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="#7A5002"/>
      <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="#D4A820"/>
      <polygon points="100,16 110,22 110,178 100,184" fill="#090500"/>
    </svg>
  );
}

/* Mini gráfico de área decorativo */
function MiniChart() {
  const pts = [0,30,18,45,28,55,38,48,50,62,60,42,70,65,80,50,90,72,100,58];
  const d = pts.reduce((acc, v, i) => {
    if (i % 2 === 0) return acc + (i === 0 ? `M${v}` : ` L${v}`);
    return acc + `,${90 - v * 0.8}`;
  }, '');
  const fill = d + ` L100,90 L0,90 Z`;
  return (
    <svg viewBox="0 0 100 90" preserveAspectRatio="none">
      <defs>
        <linearGradient id="cg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#D4A820" stopOpacity="0.3"/>
          <stop offset="100%" stopColor="#D4A820" stopOpacity="0"/>
        </linearGradient>
      </defs>
      <path d={fill} fill="url(#cg)"/>
      <path d={d} fill="none" stroke="#D4A820" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

const AVATAR_COLORS = ['#D4A820','#2EC8A4','#F07A64','#60B0F2'];

export const ContactPage: React.FC = () => {
  const [fname, setFname]     = useState('');
  const [lname, setLname]     = useState('');
  const [email, setEmail]     = useState('');
  const [message, setMessage] = useState('');
  const [errs, setErrs]       = useState({ fname: '', email: '', message: '' });
  const [sent, setSent]       = useState(false);

  const validate = () => {
    const e = { fname: '', email: '', message: '' };
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
      <style>{css}</style>
      <div className="cp-root">

        {/* ── ESQUERDO ── */}
        <div className="cp-left">
          <div className="cp-logo">
            <HiveLogo size={24} />
            <span className="cp-logo-name">HIVE</span>
          </div>

          {sent ? (
            <div className="cp-sent">
              <div className="cp-sent-icon">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M4 10l4 4 8-8" stroke="#2EC8A4" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
              <div className="cp-sent-title">Mensagem enviada!</div>
              <p className="cp-sent-sub">
                Recebemos seu contato e nossa equipe responderá em até 24 horas úteis em{' '}
                <strong style={{ color: '#D4A820' }}>{email}</strong>.
              </p>
              <a href="/dashboard" className="cp-btn" style={{ textDecoration: 'none', textAlign: 'center', display: 'block' }}>
                Ir para o painel
              </a>
            </div>
          ) : (
            <>
              <div className="cp-eyebrow">
                <span className="cp-eyebrow-dot" /> Suporte
              </div>

              <h1 className="cp-title">
                Fale com nossa<br /><em>equipe amiga</em>
              </h1>
              <p className="cp-sub">
                Pronto para começar? Conta pra gente como podemos te ajudar.
              </p>

              <form className="cp-form" onSubmit={handleSubmit} noValidate>
                <div className="cp-fields">
                  <div className="cp-row2">
                    <div>
                      <label className="cp-label">Nome</label>
                      <input className={`cp-input${errs.fname ? ' err' : ''}`} type="text" placeholder="Seu nome"
                        value={fname} onChange={e => { setFname(e.target.value); if (errs.fname) setErrs(p => ({...p, fname: ''})); }}
                        autoFocus />
                      {errs.fname && <div className="cp-field-err">{errs.fname}</div>}
                    </div>
                    <div>
                      <label className="cp-label">Sobrenome</label>
                      <input className="cp-input" type="text" placeholder="Sobrenome"
                        value={lname} onChange={e => setLname(e.target.value)} />
                    </div>
                  </div>

                  <div>
                    <label className="cp-label">E-mail</label>
                    <input className={`cp-input${errs.email ? ' err' : ''}`} type="email" placeholder="voce@empresa.com"
                      value={email} onChange={e => { setEmail(e.target.value); if (errs.email) setErrs(p => ({...p, email: ''})); }} />
                    {errs.email && <div className="cp-field-err">{errs.email}</div>}
                  </div>

                  <div>
                    <label className="cp-label">Mensagem</label>
                    <textarea className={`cp-input${errs.message ? ' err' : ''}`} rows={5}
                      placeholder="Descreva sua dúvida ou problema..."
                      value={message} onChange={e => { setMessage(e.target.value); if (errs.message) setErrs(p => ({...p, message: ''})); }} />
                    {errs.message && <div className="cp-field-err">{errs.message}</div>}
                  </div>
                </div>

                <button type="submit" className="cp-btn">Continuar</button>

                <a href="mailto:suporte@hive.com.br" className="cp-contact-email">
                  <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
                    <rect x="1" y="2.5" width="11" height="8" rx="1.3" stroke="currentColor" strokeWidth="1.1"/>
                    <path d="M1 4l5.5 3.5L12 4" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/>
                  </svg>
                  suporte@hive.com.br
                </a>

                <Link to="/login" className="cp-back">
                  <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
                    <path d="M8.5 2L3.5 6.5l5 4.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  Voltar para o login
                </Link>
              </form>
            </>
          )}
        </div>

        {/* ── DIREITO — preview do dashboard ── */}
        <div className="cp-right">
          <div className="cp-dash-frame">
            {/* Barra estilo browser */}
            <div className="cp-dash-titlebar">
              <div className="cp-dot-r" />
              <div className="cp-dot-y" />
              <div className="cp-dot-g" />
              <div className="cp-url-bar">app.hive.com.br/dashboard</div>
            </div>

            {/* Mock layout do dashboard */}
            <div className="cp-dash-inner">
              {/* Sidebar */}
              <div className="cp-dash-sidebar">
                <div className="cp-dash-nav-logo">
                  <HiveLogo size={12} />
                  <span>HIVE</span>
                </div>
                {[true, false, false, false, false, false].map((active, i) => (
                  <div key={i} className={`cp-dash-nav-item${active ? ' active' : ''}`}>
                    <div className="cp-dash-nav-dot" />
                    <div className="cp-dash-nav-line" />
                  </div>
                ))}
              </div>

              {/* Conteúdo */}
              <div className="cp-dash-content">
                {/* KPIs */}
                <div className="cp-dash-kpis">
                  {[
                    { label: 'Patrimônio', val: 'R$ 84k', sub: '+12.4%' },
                    { label: 'Rendimento', val: 'R$ 3.2k', sub: '+8.1%' },
                    { label: 'Carteira',   val: '94.2%',  sub: '+2.3%' },
                  ].map(kpi => (
                    <div key={kpi.label} className="cp-dash-kpi">
                      <div className="cp-dash-kpi-label">{kpi.label}</div>
                      <div className="cp-dash-kpi-val">{kpi.val}</div>
                      <div className="cp-dash-kpi-sub">{kpi.sub}</div>
                    </div>
                  ))}
                </div>

                {/* Gráfico */}
                <div className="cp-dash-chart">
                  <div className="cp-dash-chart-title">Evolução patrimonial</div>
                  <div className="cp-dash-chart-area">
                    <MiniChart />
                  </div>
                </div>

                {/* Linhas de ativos */}
                <div className="cp-dash-rows">
                  {AVATAR_COLORS.map((color, i) => (
                    <div key={i} className="cp-dash-row">
                      <div className="cp-dash-row-av" style={{ background: color + '33', border: `1px solid ${color}44` }} />
                      <div className="cp-dash-row-info">
                        <div className="cp-dash-row-name" />
                        <div className="cp-dash-row-sub" />
                      </div>
                      <div className="cp-dash-row-val">+{(Math.random() * 15 + 2).toFixed(1)}%</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="cp-dash-overlay">Preview do painel</div>
          </div>
        </div>

      </div>
    </>
  );
};
