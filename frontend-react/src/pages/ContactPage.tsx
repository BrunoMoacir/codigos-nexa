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
    display: flex;
    align-items: stretch;
    justify-content: center;
  }

  .cp-shell {
    width: 100%;
    max-width: 1100px;
    margin: 0 auto;
    display: grid;
    grid-template-columns: 300px 1fr;
    min-height: 100vh;
  }

  @keyframes cp-up {
    from { opacity: 0; transform: translateY(14px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes pulse-dot {
    0%,100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.6; transform: scale(0.85); }
  }

  /* ── PAINEL ESQUERDO ── */
  .cp-left {
    background: #100E0B;
    border-right: 1px solid rgba(243,239,234,0.1);
    padding: 40px 28px 32px;
    display: flex;
    flex-direction: column;
    animation: cp-up 0.5s cubic-bezier(.16,1,.3,1) both;
  }

  .cp-brand {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 44px;
  }
  .cp-brand-name {
    font-size: 0.95rem;
    font-weight: 900;
    letter-spacing: 0.06em;
    color: #D4A820;
  }

  /* Contact items com separadores pontilhados */
  .cp-items { flex: 1; }

  .cp-item {
    padding: 20px 0;
    border-bottom: 1px dashed rgba(243,239,234,0.12);
  }
  .cp-item:first-child {
    border-top: 1px dashed rgba(243,239,234,0.12);
  }

  .cp-item-title {
    font-size: 0.85rem;
    font-weight: 700;
    color: #F3EFEA;
    margin-bottom: 4px;
    letter-spacing: -0.01em;
  }
  .cp-item-desc {
    font-size: 0.75rem;
    color: rgba(243,239,234,0.42);
    line-height: 1.55;
    margin-bottom: 10px;
  }
  .cp-item-value {
    font-size: 0.78rem;
    font-weight: 600;
    color: #D4A820;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    text-decoration: none;
    cursor: pointer;
    background: none;
    border: none;
    font-family: inherit;
    padding: 0;
  }
  .cp-item-value:hover { opacity: 0.75; }

  .cp-online-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 0.72rem;
    font-weight: 700;
    color: #2EC8A4;
    background: rgba(46,200,164,0.1);
    border: 1px solid rgba(46,200,164,0.22);
    border-radius: 20px;
    padding: 3px 9px;
  }
  .cp-status-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: #2EC8A4;
    animation: pulse-dot 2s ease-in-out infinite;
  }

  .cp-copy-icon {
    color: rgba(243,239,234,0.3);
    cursor: pointer;
    transition: color 0.15s;
  }
  .cp-copy-icon:hover { color: #D4A820; }

  /* Social icons */
  .cp-socials {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-top: 32px;
    padding-top: 24px;
    border-top: 1px dashed rgba(243,239,234,0.08);
  }
  .cp-social-icon {
    color: rgba(243,239,234,0.3);
    transition: color 0.15s;
    text-decoration: none;
    display: flex;
  }
  .cp-social-icon:hover { color: rgba(243,239,234,0.7); }

  /* ── PAINEL DIREITO — FORM ── */
  .cp-right {
    padding: 40px 64px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    animation: cp-up 0.5s cubic-bezier(.16,1,.3,1) 0.08s both;
  }

  .cp-right-inner {
    max-width: 520px;
    width: 100%;
  }

  .cp-icon-wrap {
    width: 44px; height: 44px;
    border-radius: 10px;
    background: rgba(212,168,32,0.1);
    border: 1px solid rgba(212,168,32,0.2);
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 20px;
  }

  .cp-form-title {
    font-size: 1.7rem;
    font-weight: 900;
    letter-spacing: -0.04em;
    color: #F3EFEA;
    line-height: 1.2;
    margin-bottom: 8px;
  }
  .cp-form-sub {
    font-size: 0.82rem;
    color: rgba(243,239,234,0.42);
    line-height: 1.6;
    margin-bottom: 32px;
  }

  .cp-fields { display: flex; flex-direction: column; gap: 16px; margin-bottom: 28px; }
  .cp-row2   { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

  .cp-field-label {
    display: block;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.5);
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
    transition: border-color 0.15s, background 0.15s;
    resize: none;
  }
  .cp-input::placeholder { color: rgba(243,239,234,0.22); }
  .cp-input:focus { border-color: rgba(212,168,32,0.5); background: rgba(212,168,32,0.03); }
  .cp-input.err { border-color: rgba(240,122,100,0.55); }
  .cp-field-err { font-size: 0.7rem; color: #F07A64; margin-top: 4px; font-weight: 500; }

  /* Phone row with prefix */
  .cp-phone-wrap {
    display: flex;
    gap: 0;
    border: 1px solid rgba(243,239,234,0.1);
    border-radius: 10px;
    overflow: hidden;
    transition: border-color 0.15s;
  }
  .cp-phone-wrap:focus-within { border-color: rgba(212,168,32,0.5); }
  .cp-phone-prefix {
    padding: 11px 12px;
    background: rgba(243,239,234,0.06);
    border-right: 1px solid rgba(243,239,234,0.1);
    font-size: 0.82rem;
    color: rgba(243,239,234,0.55);
    white-space: nowrap;
    display: flex;
    align-items: center;
    gap: 4px;
    flex-shrink: 0;
  }
  .cp-phone-input {
    flex: 1;
    padding: 11px 14px;
    background: rgba(243,239,234,0.04);
    color: #F3EFEA;
    border: none;
    font-family: inherit;
    font-size: 0.88rem;
    outline: none;
  }
  .cp-phone-input::placeholder { color: rgba(243,239,234,0.22); }

  /* Botões de ação */
  .cp-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .cp-btn-back {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 11px 20px;
    background: transparent;
    color: rgba(243,239,234,0.6);
    border: 1px solid rgba(243,239,234,0.15);
    border-radius: 99px;
    font-family: inherit;
    font-size: 0.82rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
    text-decoration: none;
  }
  .cp-btn-back:hover { border-color: rgba(243,239,234,0.3); color: #F3EFEA; }

  .cp-btn-send {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 11px 28px;
    background: #D4A820;
    color: #0A0800;
    border: none;
    border-radius: 99px;
    font-family: inherit;
    font-size: 0.82rem;
    font-weight: 900;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    cursor: pointer;
    transition: background 0.15s, transform 0.12s, box-shadow 0.2s;
    box-shadow: 0 4px 18px rgba(212,168,32,0.25);
  }
  .cp-btn-send:hover:not(:disabled) {
    background: #C89010;
    transform: translateY(-1px);
    box-shadow: 0 6px 24px rgba(212,168,32,0.4);
  }
  .cp-btn-send:disabled { opacity: 0.35; cursor: not-allowed; }

  /* Sucesso */
  .cp-sent {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    padding: 8px 0;
    animation: cp-up 0.5s cubic-bezier(.16,1,.3,1) both;
  }
  .cp-sent-icon {
    width: 52px; height: 52px;
    border-radius: 50%;
    background: rgba(46,200,164,0.12);
    border: 1px solid rgba(46,200,164,0.3);
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 20px;
  }
  .cp-sent-title { font-size: 1.5rem; font-weight: 800; color: #F3EFEA; letter-spacing: -0.03em; margin-bottom: 8px; }
  .cp-sent-sub { font-size: 0.82rem; color: rgba(243,239,234,0.42); line-height: 1.65; max-width: 340px; margin-bottom: 28px; }

  @media (max-width: 860px) {
    .cp-shell { grid-template-columns: 1fr; }
    .cp-left { border-right: none; border-bottom: 1px dashed rgba(243,239,234,0.12); padding: 32px 24px; }
    .cp-right { padding: 32px 24px 48px; }
  }
`;

function CopyIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 13 13" fill="none" className="cp-copy-icon">
      <rect x="4" y="4" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.2"/>
      <path d="M2 9H1.5A1.5 1.5 0 0 1 0 7.5V1.5A1.5 1.5 0 0 1 1.5 0h6A1.5 1.5 0 0 1 9 1.5V2" stroke="currentColor" strokeWidth="1.2"/>
    </svg>
  );
}

export const ContactPage: React.FC = () => {
  const [fname, setFname] = useState('');
  const [lname, setLname] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [message, setMessage] = useState('');
  const [errs, setErrs] = useState({ fname: '', email: '', message: '' });
  const [sent, setSent] = useState(false);

  const fmtPhone = (v: string) => {
    const d = v.replace(/\D/g, '').slice(0, 11);
    if (d.length <= 2) return d;
    if (d.length <= 7) return `(${d.slice(0,2)}) ${d.slice(2)}`;
    return `(${d.slice(0,2)}) ${d.slice(2,7)}-${d.slice(7)}`;
  };

  const validate = () => {
    const e = { fname: '', email: '', message: '' };
    if (!fname.trim())  e.fname   = 'Preencha seu nome';
    if (!email.trim())  e.email   = 'Preencha o e-mail';
    else if (!/\S+@\S+\.\S+/.test(email)) e.email = 'E-mail inválido';
    if (!message.trim()) e.message = 'Escreva sua mensagem';
    setErrs(e);
    return !Object.values(e).some(Boolean);
  };

  const handleSubmit = (ev: React.FormEvent) => {
    ev.preventDefault();
    if (validate()) setSent(true);
  };

  const copy = (text: string) => navigator.clipboard?.writeText(text);

  return (
    <>
      <style>{css}</style>
      <div className="cp-root">
        <div className="cp-shell">
          {/* ── ESQUERDO ── */}
          <aside className="cp-left">
            <div className="cp-brand">
              <svg width="20" height="24" viewBox="0 0 180 200" fill="none">
                <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="#7A5002"/>
                <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="#D4A820"/>
                <polygon points="100,16 110,22 110,178 100,184" fill="#090500"/>
              </svg>
              <span className="cp-brand-name">HIVE</span>
            </div>

            <div className="cp-items">
              <div className="cp-item">
                <div className="cp-item-title">Chat de vendas</div>
                <div className="cp-item-desc">Interessado em conhecer mais? Fale com nossa equipe.</div>
                <button className="cp-item-value" onClick={() => copy('vendas@hive.com.br')}>
                  vendas@hive.com.br <CopyIcon />
                </button>
              </div>

              <div className="cp-item">
                <div className="cp-item-title">Suporte por e-mail</div>
                <div className="cp-item-desc">Retornamos em até 24 horas úteis.</div>
                <button className="cp-item-value" onClick={() => copy('suporte@hive.com.br')}>
                  suporte@hive.com.br <CopyIcon />
                </button>
              </div>

              <div className="cp-item">
                <div className="cp-item-title">Chat ao vivo</div>
                <div className="cp-item-desc">Atendimento imediato com nossa equipe, seg. a sex., 9h–18h.</div>
                <span className="cp-online-badge">
                  <span className="cp-status-dot" /> Online
                </span>
              </div>

              <div className="cp-item">
                <div className="cp-item-title">Telefone</div>
                <div className="cp-item-desc">Seg. a sex., 9h às 18h (horário de Brasília).</div>
                <button className="cp-item-value" style={{ marginBottom: 6 }} onClick={() => copy('08001234567')}>
                  0800 123 4567 <CopyIcon />
                </button>
                <button className="cp-item-value" onClick={() => copy('+5511999999999')}>
                  +55 (11) 9 9999-9999 <CopyIcon />
                </button>
              </div>
            </div>

            <div className="cp-socials">
              {/* X */}
              <a href="#" className="cp-social-icon" aria-label="X">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M9.28 7.1 14.7 1h-1.29L8.7 6.26 4.6 1H1l5.69 7.97L1 15h1.29l4.97-5.57L11.4 15H15L9.28 7.1zm-1.76 1.97-.58-.8L2.64 1.93h1.98l3.7 5.19.57.8 4.83 6.76h-1.98L7.52 9.07z" fill="currentColor"/>
                </svg>
              </a>
              {/* LinkedIn */}
              <a href="#" className="cp-social-icon" aria-label="LinkedIn">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M13.63 1H2.37A1.37 1.37 0 0 0 1 2.37v11.26A1.37 1.37 0 0 0 2.37 15h11.26A1.37 1.37 0 0 0 15 13.63V2.37A1.37 1.37 0 0 0 13.63 1zM5.5 12.5H3.5v-6h2v6zm-1-6.84a1.16 1.16 0 1 1 0-2.32 1.16 1.16 0 0 1 0 2.32zM12.5 12.5h-2V9.4c0-.74-.01-1.7-1.03-1.7-1.04 0-1.2.81-1.2 1.64v3.16h-2v-6h1.92v.82h.03A2.1 2.1 0 0 1 10.1 6.4c2.01 0 2.38 1.32 2.38 3.04v3.06z" fill="currentColor"/>
                </svg>
              </a>
              {/* GitHub */}
              <a href="#" className="cp-social-icon" aria-label="GitHub">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M8 1C4.13 1 1 4.13 1 8c0 3.1 2.01 5.73 4.79 6.65.35.06.48-.15.48-.34v-1.18C4.2 13.5 3.8 12.1 3.8 12.1c-.32-.81-.78-1.03-.78-1.03-.64-.43.05-.42.05-.42.7.05 1.07.72 1.07.72.63 1.07 1.64.76 2.04.58.06-.45.24-.76.44-.94-1.56-.18-3.2-.78-3.2-3.46 0-.77.27-1.39.72-1.88-.07-.18-.31-.89.07-1.85 0 0 .59-.19 1.92.72A6.6 6.6 0 0 1 8 4.5c.59 0 1.19.08 1.75.23 1.33-.9 1.92-.72 1.92-.72.38.96.14 1.67.07 1.85.45.49.72 1.11.72 1.88 0 2.69-1.64 3.28-3.2 3.46.25.22.47.64.47 1.29v1.92c0 .19.12.4.48.34A7.01 7.01 0 0 0 15 8C15 4.13 11.87 1 8 1z" fill="currentColor"/>
                </svg>
              </a>
              {/* YouTube */}
              <a href="#" className="cp-social-icon" aria-label="YouTube">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M14.56 4.34A1.79 1.79 0 0 0 13.3 3.07C12.26 2.8 8 2.8 8 2.8s-4.26 0-5.3.27A1.79 1.79 0 0 0 1.44 4.34C1.17 5.38 1.17 8 1.17 8s0 2.62.27 3.66a1.79 1.79 0 0 0 1.26 1.27C3.74 13.2 8 13.2 8 13.2s4.26 0 5.3-.27a1.79 1.79 0 0 0 1.26-1.27c.27-1.04.27-3.66.27-3.66s0-2.62-.27-3.66zM6.6 10.17V5.83L10.43 8 6.6 10.17z" fill="currentColor"/>
                </svg>
              </a>
            </div>
          </aside>

          {/* ── DIREITO — formulário ── */}
          <main className="cp-right">
            <div className="cp-right-inner">
              {sent ? (
                <div className="cp-sent">
                  <div className="cp-sent-icon">
                    <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
                      <path d="M4 11l5 5 9-9" stroke="#2EC8A4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </div>
                  <div className="cp-sent-title">Mensagem enviada!</div>
                  <p className="cp-sent-sub">
                    Recebemos seu contato e responderemos em até 24 horas úteis no e-mail <strong style={{ color: '#D4A820' }}>{email}</strong>.
                  </p>
                  <a href="/dashboard" className="cp-btn-send" style={{ textDecoration: 'none' }}>
                    VOLTAR AO PAINEL
                  </a>
                </div>
              ) : (
                <>
                  <div className="cp-icon-wrap">
                    <svg width="20" height="20" viewBox="0 0 180 200" fill="none">
                      <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="#7A5002"/>
                      <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="#D4A820"/>
                      <polygon points="100,16 110,22 110,178 100,184" fill="#090500"/>
                    </svg>
                  </div>

                  <div className="cp-form-title">Como entrar em contato?</div>
                  <p className="cp-form-sub">
                    Deixe seus dados e nossa equipe responderá em até 24 horas.
                  </p>

                  <form onSubmit={handleSubmit} noValidate>
                    <div className="cp-fields">
                      <div className="cp-row2">
                        <div>
                          <label className="cp-field-label">Nome</label>
                          <input className={`cp-input${errs.fname ? ' err' : ''}`} type="text" placeholder="Seu nome"
                            value={fname} onChange={e => { setFname(e.target.value); if (errs.fname) setErrs(p => ({...p, fname: ''})); }}
                            autoFocus />
                          {errs.fname && <div className="cp-field-err">{errs.fname}</div>}
                        </div>
                        <div>
                          <label className="cp-field-label">Sobrenome</label>
                          <input className="cp-input" type="text" placeholder="Sobrenome"
                            value={lname} onChange={e => setLname(e.target.value)} />
                        </div>
                      </div>

                      <div>
                        <label className="cp-field-label">E-mail</label>
                        <input className={`cp-input${errs.email ? ' err' : ''}`} type="email" placeholder="seu@email.com"
                          value={email} onChange={e => { setEmail(e.target.value); if (errs.email) setErrs(p => ({...p, email: ''})); }} />
                        {errs.email && <div className="cp-field-err">{errs.email}</div>}
                      </div>

                      <div>
                        <label className="cp-field-label">Telefone</label>
                        <div className="cp-phone-wrap">
                          <div className="cp-phone-prefix">
                            <svg width="14" height="10" viewBox="0 0 14 10" fill="none">
                              <rect width="14" height="10" rx="1" fill="#009B3A"/>
                              <circle cx="7" cy="5" r="3" fill="#FEDF00" stroke="#009B3A" strokeWidth="0.5"/>
                              <path d="M4.2 5h5.6" stroke="#009B3A" strokeWidth="0.5"/>
                            </svg>
                            +55
                          </div>
                          <input className="cp-phone-input" type="tel" placeholder="(11) 9 0000-0000"
                            value={phone} onChange={e => setPhone(fmtPhone(e.target.value))} />
                        </div>
                      </div>

                      <div>
                        <label className="cp-field-label">Mensagem</label>
                        <textarea className={`cp-input${errs.message ? ' err' : ''}`} rows={5}
                          placeholder="Descreva sua dúvida ou problema..."
                          value={message} onChange={e => { setMessage(e.target.value); if (errs.message) setErrs(p => ({...p, message: ''})); }} />
                        {errs.message && <div className="cp-field-err">{errs.message}</div>}
                      </div>
                    </div>

                    <div className="cp-actions">
                      <Link to="/login" className="cp-btn-back">
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                          <path d="M9 2L4 7l5 5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                        Voltar
                      </Link>
                      <button type="submit" className="cp-btn-send">Enviar</button>
                    </div>
                  </form>
                </>
              )}
            </div>
          </main>
        </div>
      </div>
    </>
  );
};
