import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { nexaApi } from '../api/nexa';

const BRANDS = ['Visa', 'Mastercard', 'Elo', 'American Express', 'Hipercard'];
const LEVELS = ['Standard', 'Gold', 'Platinum', 'Black', 'Infinite'];

const css = `
  @import url('https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700,800,900&display=swap');
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  .ac-root {
    font-family: 'Satoshi', system-ui, sans-serif;
    min-height: 100vh;
    background: #0C0A08;
    color: #F3EFEA;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 32px 20px;
    position: relative;
    overflow: hidden;
  }
  .ac-glow {
    position: fixed;
    left: 50%; top: 50%;
    transform: translate(-50%, -50%);
    width: 900px; height: 900px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(212,168,32,0.2) 0%, rgba(212,168,32,0.07) 42%, transparent 72%);
    pointer-events: none; z-index: 0;
  }

  .ac-card {
    width: 100%;
    max-width: 460px;
    background: rgba(16, 13, 9, 0.95);
    border: 1px solid rgba(212,168,32,0.28);
    border-radius: 20px;
    padding: 28px 28px 26px;
    position: relative;
    overflow: hidden;
    z-index: 1;
    box-shadow: 0 0 0 1px rgba(212,168,32,0.05), 0 8px 40px rgba(0,0,0,0.55);
  }
  .ac-card::before {
    content: '';
    position: absolute;
    top: 0; left: 8%; right: 8%; height: 2px;
    background: linear-gradient(90deg, transparent, rgba(212,168,32,0.82), transparent);
  }

  .ac-label { font-size: 0.6rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: rgba(212,168,32,0.65); margin-bottom: 6px; }
  .ac-title { font-size: 1.3rem; font-weight: 800; color: #F3EFEA; letter-spacing: -0.025em; margin-bottom: 6px; }
  .ac-sub   { font-size: 0.82rem; color: rgba(243,239,234,0.4); line-height: 1.5; margin-bottom: 22px; }

  .ac-preview {
    aspect-ratio: 1.586 / 1;
    max-width: 220px;
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 22px;
    background: linear-gradient(135deg, #45484D 0%, #2A2C30 45%, #17181B 100%);
    display: flex; flex-direction: column; justify-content: space-between;
    box-shadow: 0 10px 24px rgba(0,0,0,0.4);
  }
  .ac-preview-bank { font-size: 0.72rem; font-weight: 800; color: #F3EFEA; }
  .ac-preview-num  { font-size: 0.78rem; font-weight: 500; letter-spacing: 0.08em; color: rgba(243,239,234,0.85); font-variant-numeric: tabular-nums; }
  .ac-preview-brand{ font-size: 0.68rem; font-weight: 800; font-style: italic; color: rgba(243,239,234,0.7); align-self: flex-end; }

  .ac-fields { display: flex; flex-direction: column; gap: 14px; margin-bottom: 22px; }
  .ac-row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .ac-field-label { display: block; font-size: 0.63rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: rgba(243,239,234,0.5); margin-bottom: 5px; }
  .ac-input, .ac-select {
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
  .ac-input::placeholder { color: rgba(243,239,234,0.22); }
  .ac-input:focus, .ac-select:focus { border-color: rgba(212,168,32,0.5); background: rgba(243,239,234,0.06); }
  .ac-select { appearance: none; cursor: pointer; }

  .ac-btn {
    width: 100%;
    padding: 13px;
    background: linear-gradient(135deg, #C89010, #D4A820, #E8C030);
    color: #0A0800;
    border: none;
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.9rem;
    font-weight: 900;
    letter-spacing: 0.02em;
    cursor: pointer;
    transition: transform 0.12s, box-shadow 0.2s;
    margin-bottom: 12px;
  }
  .ac-btn:hover { transform: translateY(-1px); box-shadow: 0 6px 24px rgba(212,168,32,0.3); }
  .ac-btn:disabled { opacity: 0.6; cursor: default; transform: none; box-shadow: none; }

  .ac-cancel { display: block; text-align: center; font-size: 0.8rem; color: rgba(243,239,234,0.4); text-decoration: none; }
  .ac-cancel:hover { color: rgba(243,239,234,0.7); }
`;

export const AddCardPage: React.FC = () => {
  const navigate = useNavigate();
  const [bankName, setBankName] = useState('');
  const [brand, setBrand] = useState(BRANDS[0]);
  const [level, setLevel] = useState(LEVELS[0]);
  const [last4, setLast4] = useState('');
  const [creditLimit, setCreditLimit] = useState('');
  const [availableLimit, setAvailableLimit] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!bankName.trim()) { setError('Informe o nome do banco'); return; }
    if (last4 && !/^\d{4}$/.test(last4)) { setError('Os últimos dígitos devem ter 4 números'); return; }
    setError('');
    setSaving(true);
    try {
      await nexaApi.addManualCard({
        bank_name: bankName.trim(),
        brand,
        level,
        last4: last4 || undefined,
        credit_limit: creditLimit ? Number(creditLimit) : undefined,
        available_credit_limit: availableLimit ? Number(availableLimit) : undefined,
      });
      navigate('/organizar');
    } catch {
      setError('Não deu pra salvar o cartão agora. Tenta de novo em instantes.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="ac-root">
      <style>{css}</style>
      <div className="ac-glow" aria-hidden="true" />

      <div className="ac-card">
        <div className="ac-label">Cartões</div>
        <div className="ac-title">Adicionar cartão</div>
        <p className="ac-sub">Seu banco ainda não conecta via Open Finance? Cadastre o cartão na mão pra acompanhar limite e fatura por aqui.</p>

        <div className="ac-preview">
          <span className="ac-preview-bank">{bankName || 'Banco'}</span>
          <span className="ac-preview-num">•••• •••• •••• {last4 || '····'}</span>
          <span className="ac-preview-brand">{brand.toUpperCase()}</span>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="ac-fields">
            <div>
              <label className="ac-field-label">Banco</label>
              <input className="ac-input" type="text" placeholder="Ex.: Nubank" value={bankName}
                onChange={e => { setBankName(e.target.value); if (error) setError(''); }} autoFocus />
            </div>

            <div className="ac-row2">
              <div>
                <label className="ac-field-label">Bandeira</label>
                <select className="ac-select" value={brand} onChange={e => setBrand(e.target.value)}>
                  {BRANDS.map(b => <option key={b} value={b}>{b}</option>)}
                </select>
              </div>
              <div>
                <label className="ac-field-label">Nível</label>
                <select className="ac-select" value={level} onChange={e => setLevel(e.target.value)}>
                  {LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
                </select>
              </div>
            </div>

            <div>
              <label className="ac-field-label">Últimos 4 dígitos</label>
              <input className="ac-input" type="text" placeholder="0000" inputMode="numeric" maxLength={4}
                value={last4} onChange={e => setLast4(e.target.value.replace(/\D/g, '').slice(0, 4))} />
            </div>

            <div className="ac-row2">
              <div>
                <label className="ac-field-label">Limite total</label>
                <input className="ac-input" type="number" placeholder="R$ 0,00" inputMode="decimal"
                  value={creditLimit} onChange={e => setCreditLimit(e.target.value)} />
              </div>
              <div>
                <label className="ac-field-label">Limite disponível</label>
                <input className="ac-input" type="number" placeholder="R$ 0,00" inputMode="decimal"
                  value={availableLimit} onChange={e => setAvailableLimit(e.target.value)} />
              </div>
            </div>

            {error && <div style={{ fontSize: '0.75rem', color: '#F07A64' }}>{error}</div>}
          </div>

          <button type="submit" className="ac-btn" disabled={saving}>
            {saving ? 'Salvando…' : 'Salvar cartão'}
          </button>
          <Link to="/organizar" className="ac-cancel">Cancelar</Link>
        </form>
      </div>
    </div>
  );
};
