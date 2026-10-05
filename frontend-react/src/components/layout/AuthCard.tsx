import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

/**
 * Cartão das telas públicas curtas (esqueci a senha, nova senha, confirmar
 * e-mail) — mesma identidade do login, sem o canvas animado.
 */
const css = `
  .ac-root {
    min-height: 100vh; display: flex; align-items: center; justify-content: center;
    background: radial-gradient(ellipse at top, #1A1410 0%, #0A0806 70%);
    font-family: 'Satoshi', system-ui, sans-serif; color: #F3EFEA; padding: 24px;
  }
  .ac-card {
    width: 100%; max-width: 420px; background: rgba(20,16,12,0.92);
    border: 1px solid rgba(212,168,32,0.22); border-radius: 18px; padding: 30px 28px;
  }
  .ac-logo { display: flex; align-items: center; gap: 10px; margin-bottom: 22px; text-decoration: none; }
  .ac-logo span { font-weight: 900; letter-spacing: 0.12em; color: #D4A820; }
  .ac-title { font-size: 1.25rem; font-weight: 800; letter-spacing: -0.02em; margin: 0 0 6px; }
  .ac-sub { font-size: 0.82rem; color: rgba(243,239,234,0.5); margin: 0 0 20px; line-height: 1.5; }
  .ac-label { display: block; font-size: 0.72rem; color: rgba(243,239,234,0.55); margin: 0 0 6px; }
  .ac-input {
    width: 100%; box-sizing: border-box; background: rgba(243,239,234,0.04);
    border: 1px solid rgba(243,239,234,0.12); border-radius: 10px; padding: 11px 12px;
    color: #F3EFEA; font-family: inherit; font-size: 0.9rem; margin-bottom: 14px;
  }
  .ac-input:focus { outline: none; border-color: rgba(212,168,32,0.55); }
  .ac-btn {
    width: 100%; background: #D4A820; color: #0A0800; border: none; border-radius: 10px;
    padding: 12px; font-weight: 800; font-family: inherit; font-size: 0.9rem; cursor: pointer;
  }
  .ac-btn:disabled { opacity: 0.55; cursor: default; }
  .ac-msg { font-size: 0.8rem; border-radius: 10px; padding: 10px 12px; margin: 0 0 14px; line-height: 1.45; }
  .ac-msg.erro { color: #F8AEA0; background: rgba(240,122,100,0.08); border: 1px solid rgba(240,122,100,0.25); }
  .ac-msg.ok { color: #7AE0C4; background: rgba(46,200,164,0.08); border: 1px solid rgba(46,200,164,0.25); }
  .ac-foot { margin-top: 18px; font-size: 0.78rem; color: rgba(243,239,234,0.45); text-align: center; }
  .ac-foot a { color: #D4A820; text-decoration: none; }
`;

export function AuthCard({ title, subtitle, children, footer }: {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <>
      <style>{css}</style>
      <div className="ac-root">
        <div className="ac-card">
          <Link to="/login" className="ac-logo">
            <svg width="22" height="24" viewBox="0 0 180 200" fill="none">
              <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="#7A5002"/>
              <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="#D4A820"/>
              <polygon points="100,16 110,22 110,178 100,184" fill="#090500"/>
            </svg>
            <span>HIVE</span>
          </Link>
          <h1 className="ac-title">{title}</h1>
          {subtitle && <p className="ac-sub">{subtitle}</p>}
          {children}
          <div className="ac-foot">{footer ?? <Link to="/login">Voltar ao login</Link>}</div>
        </div>
      </div>
    </>
  );
}
