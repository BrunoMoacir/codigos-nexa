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
    grid-template-columns: 360px 1fr;
  }

  @keyframes cp-up {
    from { opacity: 0; transform: translateY(14px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  /* ── PAINEL ESQUERDO ── */
  .cp-left {
    background: #0A0806;
    border-right: 1px solid rgba(243,239,234,0.06);
    padding: 48px 36px;
    display: flex;
    flex-direction: column;
    gap: 0;
    animation: cp-up 0.5s cubic-bezier(.16,1,.3,1) both;
  }

  .cp-brand {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 48px;
  }
  .cp-brand-name {
    font-size: 1rem;
    font-weight: 900;
    letter-spacing: 0.03em;
    color: #D4A820;
  }

  .cp-left-title {
    font-size: 1.4rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    color: #F3EFEA;
    line-height: 1.3;
    margin-bottom: 8px;
  }
  .cp-left-sub {
    font-size: 0.82rem;
    color: rgba(243,239,234,0.45);
    line-height: 1.65;
    margin-bottom: 40px;
  }

  .cp-contact-items {
    display: flex;
    flex-direction: column;
    gap: 0;
    flex: 1;
  }
  .cp-contact-item {
    padding: 18px 0;
    border-bottom: 1px solid rgba(243,239,234,0.06);
  }
  .cp-contact-item:first-child { border-top: 1px solid rgba(243,239,234,0.06); }

  .cp-contact-icon {
    width: 32px; height: 32px;
    border-radius: 8px;
    background: rgba(212,168,32,0.1);
    border: 1px solid rgba(212,168,32,0.18);
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 10px;
  }

  .cp-contact-label {
    font-size: 0.78rem;
    font-weight: 700;
    color: #F3EFEA;
    margin-bottom: 3px;
  }
  .cp-contact-desc {
    font-size: 0.72rem;
    color: rgba(243,239,234,0.42);
    line-height: 1.5;
    margin-bottom: 8px;
  }
  .cp-contact-value {
    font-size: 0.75rem;
    font-weight: 600;
    color: #D4A820;
    display: flex;
    align-items: center;
    gap: 6px;
    text-decoration: none;
  }
  .cp-contact-value:hover { opacity: 0.8; }

  .cp-status-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: #2EC8A4;
    display: inline-block;
    animation: pulse-dot 2s ease-in-out infinite;
  }
  @keyframes pulse-dot {
    0%,100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.6; transform: scale(0.85); }
  }

  .cp-left-footer {
    margin-top: 40px;
    font-size: 0.65rem;
    color: rgba(243,239,234,0.2);
  }

  /* ── PAINEL DIREITO — FORM ── */
  .cp-right {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 48px 80px;
    animation: cp-up 0.5s cubic-bezier(.16,1,.3,1) 0.08s both;
  }

  .cp-form-wrap {
    width: 100%;
    max-width: 520px;
  }

  .cp-form-label {
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: rgba(212,168,32,0.65);
    margin-bottom: 6px;
  }
  .cp-form-title {
    font-size: 1.6rem;
    font-weight: 900;
    letter-spacing: -0.04em;
    color: #F3EFEA;
    line-height: 1.2;
    margin-bottom: 6px;
  }
  .cp-form-sub {
    font-size: 0.82rem;
    color: rgba(243,239,234,0.42);
    line-height: 1.6;
    margin-bottom: 32px;
  }

  .cp-fields { display: flex; flex-direction: column; gap: 14px; margin-bottom: 20px; }
  .cp-row2   { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

  .cp-field-label {
    display: block;
    font-size: 0.63rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.55);
    margin-bottom: 6px;
  }
  .cp-input {
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
    resize: none;
  }
  .cp-input::placeholder { color: rgba(243,239,234,0.25); }
  .cp-input:focus { border-color: rgba(212,168,32,0.5); background: rgba(212,168,32,0.03); }
  .cp-input.err { border-color: rgba(240,122,100,0.55); }
  .cp-field-err { font-size: 0.7rem; color: #F07A64; margin-top: 4px; font-weight: 500; }

  /* Subject chips */
  .cp-subjects {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
    margin-bottom: 16px;
  }
  .cp-subject {
    padding: 6px 14px;
    border-radius: 20px;
    border: 1px solid rgba(243,239,234,0.1);
    background: transparent;
    color: rgba(243,239,234,0.45);
    font-family: inherit;
    font-size: 0.75rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }
  .cp-subject:hover { border-color: rgba(243,239,234,0.22); color: rgba(243,239,234,0.75); }
  .cp-subject.sel {
    border-color: rgba(212,168,32,0.5);
    background: rgba(212,168,32,0.08);
    color: #D4A820;
  }

  .cp-btn {
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
  .cp-btn:hover:not(:disabled) {
    background-position: right center;
    transform: translateY(-1px);
    box-shadow: 0 6px 24px rgba(212,168,32,0.35);
  }
  .cp-btn:disabled { opacity: 0.35; cursor: not-allowed; }

  .cp-back {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 0.75rem;
    font-weight: 500;
    color: rgba(243,239,234,0.35);
    text-decoration: none;
    margin-top: 16px;
    transition: color 0.15s;
  }
  .cp-back:hover { color: rgba(243,239,234,0.65); }

  /* Sucesso */
  .cp-sent {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: 24px 0;
    animation: cp-up 0.5s cubic-bezier(.16,1,.3,1) both;
  }
  .cp-sent-icon {
    width: 56px; height: 56px;
    border-radius: 50%;
    background: rgba(46,200,164,0.12);
    border: 1px solid rgba(46,200,164,0.3);
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 20px;
  }
  .cp-sent-title { font-size: 1.3rem; font-weight: 800; color: #F3EFEA; letter-spacing: -0.025em; margin-bottom: 8px; }
  .cp-sent-sub { font-size: 0.82rem; color: rgba(243,239,234,0.42); line-height: 1.65; max-width: 320px; margin-bottom: 28px; }

  @media (max-width: 900px) {
    .cp-root { grid-template-columns: 1fr; }
    .cp-left { border-right: none; border-bottom: 1px solid rgba(243,239,234,0.06); padding: 32px 24px; }
    .cp-right { padding: 32px 24px 48px; }
  }
`;

const SUBJECTS = ['Dúvida geral', 'Problema técnico', 'Sugestão', 'Parceria', 'Imprensa', 'Outro'];

export const ContactPage: React.FC = () => {
  const [fname, setFname] = useState('');
  const [lname, setLname] = useState('');
  const [email, setEmail] = useState('');
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [errs, setErrs] = useState({ fname: '', email: '', message: '' });
  const [sent, setSent] = useState(false);

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

  return (
    <>
      <style>{css}</style>
      <div className="cp-root">
        {/* ── ESQUERDO ── */}
        <aside className="cp-left">
          <div className="cp-brand">
            <svg width="22" height="26" viewBox="0 0 180 200" fill="none">
              <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="#7A5002"/>
              <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="#D4A820"/>
              <polygon points="100,16 110,22 110,178 100,184" fill="#090500"/>
            </svg>
            <span className="cp-brand-name">HIVE</span>
          </div>

          <div className="cp-left-title">Como podemos te ajudar?</div>
          <p className="cp-left-sub">
            Nossa equipe responde em até 24 horas úteis. Para urgências técnicas, use o chat ao vivo.
          </p>

          <div className="cp-contact-items">
            <div className="cp-contact-item">
              <div className="cp-contact-icon">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M2 3C2 2.45 2.45 2 3 2h8c.55 0 1 .45 1 1v6c0 .55-.45 1-1 1H4L1.5 12.5V3z" stroke="#D4A820" strokeWidth="1.3" strokeLinejoin="round"/>
                </svg>
              </div>
              <div className="cp-contact-label">Chat ao vivo</div>
              <div className="cp-contact-desc">Fale com a equipe em tempo real. Disponível de seg. a sex., 9h–18h.</div>
              <span className="cp-contact-value">
                <span className="cp-status-dot"/> Online agora
              </span>
            </div>

            <div className="cp-contact-item">
              <div className="cp-contact-icon">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <rect x="1" y="3" width="12" height="8" rx="1.5" stroke="#D4A820" strokeWidth="1.3"/>
                  <path d="M1 4l6 4 6-4" stroke="#D4A820" strokeWidth="1.3" strokeLinecap="round"/>
                </svg>
              </div>
              <div className="cp-contact-label">E-mail</div>
              <div className="cp-contact-desc">Resposta em até 24 horas úteis para dúvidas gerais.</div>
              <a href="mailto:suporte@hive.com.br" className="cp-contact-value">suporte@hive.com.br</a>
            </div>

            <div className="cp-contact-item">
              <div className="cp-contact-icon">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M12 9.8c0 .24-.05.47-.17.7-.11.22-.27.43-.48.6-.34.31-.71.46-1.1.46-.27 0-.57-.07-.88-.21A8.6 8.6 0 0 1 7.9 9.9a15 15 0 0 1-1.4-1.4 15.7 15.7 0 0 1-1.16-1.52c-.37-.54-.66-1.04-.87-1.51C4.16 5.01 4.05 4.7 4.05 4.4c0-.3.06-.57.18-.82.12-.25.3-.48.54-.67C5.03 2.63 5.32 2.5 5.62 2.5c.1 0 .2.02.3.06.1.04.2.1.27.2l.94 1.33c.08.1.14.2.18.3.04.09.07.18.07.26 0 .1-.03.2-.09.3a1.1 1.1 0 0 1-.24.29l-.33.34a.23.23 0 0 0-.07.17c0 .03.01.06.02.1.02.04.04.07.06.1.17.3.37.59.61.86.25.28.51.55.79.8.26.22.53.42.81.6.03.02.07.04.1.05.04.01.07.02.1.02a.23.23 0 0 0 .17-.08l.33-.32c.1-.1.2-.17.3-.22.1-.05.19-.08.3-.08.09 0 .17.02.26.06.1.05.2.11.3.2l1.34.96c.1.07.17.16.21.26.03.1.05.2.05.3z" stroke="#D4A820" strokeWidth="1.3" strokeMiterlimit="10"/>
                </svg>
              </div>
              <div className="cp-contact-label">Telefone</div>
              <div className="cp-contact-desc">Seg. a sex., 9h às 18h (horário de Brasília).</div>
              <a href="tel:+5511999999999" className="cp-contact-value">+55 (11) 9 9999-9999</a>
            </div>
          </div>

          <div className="cp-left-footer">© 2025 HIVE · Todos os direitos reservados</div>
        </aside>

        {/* ── DIREITO — formulário ── */}
        <main className="cp-right">
          <div className="cp-form-wrap">
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
                <a href="/dashboard" className="cp-btn" style={{ textAlign: 'center', textDecoration: 'none', display: 'block', padding: '14px' }}>
                  VOLTAR AO PAINEL
                </a>
              </div>
            ) : (
              <>
                <div className="cp-form-label">Suporte</div>
                <div className="cp-form-title">Fale com a gente</div>
                <p className="cp-form-sub">
                  Preencha o formulário abaixo e nossa equipe entrará em contato.
                </p>

                <div className="cp-subjects">
                  {SUBJECTS.map(s => (
                    <button key={s} type="button"
                      className={`cp-subject${subject === s ? ' sel' : ''}`}
                      onClick={() => setSubject(s === subject ? '' : s)}>
                      {s}
                    </button>
                  ))}
                </div>

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
                      <label className="cp-field-label">Mensagem</label>
                      <textarea className={`cp-input${errs.message ? ' err' : ''}`} rows={5}
                        placeholder="Descreva sua dúvida ou problema..."
                        value={message} onChange={e => { setMessage(e.target.value); if (errs.message) setErrs(p => ({...p, message: ''})); }} />
                      {errs.message && <div className="cp-field-err">{errs.message}</div>}
                    </div>
                  </div>

                  <button type="submit" className="cp-btn">Enviar mensagem</button>
                </form>

                <Link to="/login" className="cp-back">
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M9 2L4 7l5 5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  Voltar
                </Link>
              </>
            )}
          </div>
        </main>
      </div>
    </>
  );
};
