import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { API_BASE_URL } from '../api/client';

// ─── Utils ───────────────────────────────────────────────────────────────────
const fmtCPF = (v: string) => {
  const d = v.replace(/\D/g, '').slice(0, 11);
  return d
    .replace(/(\d{3})(\d)/, '$1.$2')
    .replace(/(\d{3})\.(\d{3})(\d)/, '$1.$2.$3')
    .replace(/(\d{3})\.(\d{3})\.(\d{3})(\d{1,2})/, '$1.$2.$3-$4');
};

const fmtPhone = (v: string) => {
  const d = v.replace(/\D/g, '').slice(0, 11);
  if (d.length <= 2) return d.length ? `(${d}` : '';
  if (d.length <= 7) return `(${d.slice(0,2)}) ${d.slice(2)}`;
  if (d.length <= 10) return `(${d.slice(0,2)}) ${d.slice(2,6)}-${d.slice(6)}`;
  return `(${d.slice(0,2)}) ${d.slice(2,7)}-${d.slice(7)}`;
};

// ─── Dados dos bancos (ícones oficiais via favicon do domínio) ───────────────
const BANKS = [
  { name: 'Nubank',   domain: 'nubank.com.br' },
  { name: 'Itaú',     domain: 'itau.com.br' },
  { name: 'Bradesco', domain: 'bradesco.com.br' },
  { name: 'C6 Bank',  domain: 'c6bank.com.br' },
  { name: 'Inter',    domain: 'bancointer.com.br' },
  { name: 'BTG',      domain: 'btgpactual.com' },
];

// ─── CSS ─────────────────────────────────────────────────────────────────────
const css = `
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  .rp-root {
    font-family: 'Satoshi', system-ui, sans-serif;
    min-height: 100vh;
    background: #0C0A08;
    color: #F3EFEA;
    position: relative;
    overflow: hidden;
  }

  .rp-wm {
    position: fixed;
    left: 50%; top: 50%;
    transform: translate(-50%, -50%);
    font-size: min(48vw, 480px);
    font-weight: 900;
    letter-spacing: -0.06em;
    color: transparent;
    -webkit-text-stroke: 1px rgba(212,168,32,0.03);
    pointer-events: none; z-index: 0;
    user-select: none; line-height: 1; white-space: nowrap;
  }

  /* Vinheta estática — sem forma geométrica, sem animação */
  .rp-glow {
    position: fixed;
    left: 50%; top: 50%;
    transform: translate(-50%, -50%);
    width: 1000px; height: 1000px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(212,168,32,0.22) 0%, rgba(212,168,32,0.08) 42%, transparent 72%);
    pointer-events: none; z-index: 0;
  }

  @keyframes rp-up {
    from { opacity: 0; transform: translateY(16px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes rp-pop {
    0%   { opacity: 0; transform: scale(0.5); }
    65%  { transform: scale(1.1); }
    100% { opacity: 1; transform: scale(1); }
  }
  @keyframes shimmer {
    0%   { background-position: 200% center; }
    100% { background-position: -200% center; }
  }

  /* ── Layout 2 colunas, centralizado como grupo ── */
  .rp-layout {
    position: relative;
    z-index: 2;
    display: flex;
    align-items: stretch;
    justify-content: center;
    gap: 76px;
    min-height: 100vh;
    max-width: 1100px;
    margin: 0 auto;
    padding: 40px 32px;
  }

  /* ── ESQUERDO ── */
  .rp-left {
    width: 440px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    animation: rp-up 0.6s cubic-bezier(.16,1,.3,1) both;
  }

  .rp-logo {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .rp-logo-icon {
    transition: transform 0.25s cubic-bezier(.16,1,.3,1);
    transform-origin: center;
  }
  .rp-logo-icon:hover {
    transform: scale(1.22);
  }
  .rp-logo-word {
    font-size: 1.1rem;
    font-weight: 900;
    letter-spacing: 0.03em;
    color: #D4A820;
  }

  /* Step progress — vertical, números grandes estilo "01" */
  .rp-step-nav {
    display: flex;
    flex-direction: column;
    gap: 0;
    margin: 40px 0;
    flex: 1;
  }
  .rp-step-row {
    display: flex;
    align-items: flex-start;
    gap: 20px;
    position: relative;
  }
  .rp-step-col {
    display: flex;
    flex-direction: column;
    align-items: center;
    width: 62px;
    flex-shrink: 0;
  }
  .rp-step-num {
    font-size: 2.6rem;
    font-weight: 900;
    letter-spacing: -0.04em;
    line-height: 1;
    color: transparent;
    -webkit-text-stroke: 1px rgba(243,239,234,0.16);
    transition: all 0.35s ease;
    user-select: none;
  }
  .rp-step-num.active {
    -webkit-text-stroke: 1.4px #D4A820;
    filter: drop-shadow(0 0 10px rgba(212,168,32,0.3));
  }
  .rp-step-num.done {
    color: #D4A820;
    -webkit-text-stroke: 0;
    opacity: 0.5;
  }
  .rp-step-vline {
    width: 1px;
    height: 34px;
    background: rgba(243,239,234,0.08);
    transition: background 0.4s ease;
    margin: 10px 0;
  }
  .rp-step-vline.done { background: rgba(212,168,32,0.35); }
  .rp-step-info {
    padding-top: 8px;
    padding-bottom: 34px;
  }
  .rp-step-name {
    font-size: 1rem;
    font-weight: 700;
    color: rgba(243,239,234,0.42);
    letter-spacing: 0.01em;
    margin-bottom: 4px;
    transition: color 0.3s;
  }
  .rp-step-name.active { color: #F3EFEA; }
  .rp-step-name.done   { color: rgba(212,168,32,0.7); }
  .rp-step-desc {
    font-size: 0.82rem;
    color: rgba(243,239,234,0.28);
    line-height: 1.5;
  }
  .rp-step-row:last-child .rp-step-vline { display: none; }
  .rp-step-row:last-child .rp-step-info  { padding-bottom: 0; }

  .rp-left-footer {
    font-size: 0.68rem;
    color: rgba(243,239,234,0.25);
    letter-spacing: 0.03em;
  }

  /* ── DIREITO ── */
  .rp-right {
    width: 500px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    animation: rp-up 0.6s cubic-bezier(.16,1,.3,1) 0.1s both;
  }

  .rp-card {
    width: 100%;
    background: rgba(16, 13, 9, 0.95);
    border: 1px solid rgba(212,168,32,0.28);
    border-radius: 20px;
    padding: 22px 22px 20px;
    position: relative;
    overflow: hidden;
    box-shadow: 0 0 0 1px rgba(212,168,32,0.05), 0 8px 40px rgba(0,0,0,0.55);
  }
  .rp-card::before {
    content: '';
    position: absolute;
    top: 0; left: 8%; right: 8%; height: 2px;
    background: linear-gradient(90deg, transparent, rgba(212,168,32,0.82), transparent);
    border-radius: 0 0 2px 2px;
  }

  .rp-card-label {
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: rgba(212,168,32,0.65);
    margin-bottom: 5px;
  }
  .rp-card-title {
    font-size: 1.15rem;
    font-weight: 800;
    color: #F3EFEA;
    letter-spacing: -0.025em;
    margin-bottom: 12px;
  }

  /* ── Google button ── */
  .rp-google {
    width: 100%;
    padding: 12px 16px;
    background: rgba(243,239,234,0.06);
    border: 1px solid rgba(243,239,234,0.13);
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    font-family: inherit;
    font-size: 0.83rem;
    font-weight: 600;
    color: rgba(243,239,234,0.82);
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s;
    margin-bottom: 10px;
  }
  .rp-google:hover { background: rgba(243,239,234,0.1); border-color: rgba(243,239,234,0.2); }

  .rp-or {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 10px;
    font-size: 0.65rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.28);
  }
  .rp-or::before, .rp-or::after {
    content: '';
    flex: 1; height: 1px;
    background: rgba(243,239,234,0.08);
  }

  /* ── Fields ── */
  .rp-fields { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; }
  .rp-row2   { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .rp-field-label {
    display: block;
    font-size: 0.63rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.55);
    margin-bottom: 5px;
  }
  .rp-input {
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
  .rp-input::placeholder { color: rgba(243,239,234,0.28); }
  .rp-input:focus { border-color: rgba(212,168,32,0.5); background: rgba(212,168,32,0.03); }
  .rp-input.err { border-color: rgba(240,122,100,0.55); background: rgba(240,122,100,0.04); }
  /* Navegador pinta autofill de branco por padrão — força manter o escuro */
  .rp-input:-webkit-autofill,
  .rp-input:-webkit-autofill:hover,
  .rp-input:-webkit-autofill:focus,
  .rp-input:-webkit-autofill:active {
    -webkit-box-shadow: 0 0 0 100px #171310 inset !important;
    -webkit-text-fill-color: #F3EFEA !important;
    caret-color: #F3EFEA;
    transition: background-color 9999s ease-in-out 0s;
  }
  .rp-field-err {
    font-size: 0.7rem;
    color: #F07A64;
    margin-top: 4px;
    font-weight: 500;
  }
  .rp-field-err a { color: #D4A820; font-weight: 700; text-decoration: underline; }

  /* ── Botão principal ── */
  .rp-btn {
    width: 100%;
    padding: 13px;
    background: linear-gradient(135deg, #C89010, #D4A820, #E8C030);
    background-size: 200% auto;
    color: #0A0800;
    border: none;
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.83rem;
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


  /* ── Banks — fila de prioridade, não grade de "em breve" ── */
  .rp-bank-eyebrow {
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: rgba(212,168,32,0.7);
    margin-bottom: 6px;
  }
  .rp-bank-info {
    font-size: 0.79rem;
    color: rgba(243,239,234,0.5);
    line-height: 1.65;
    margin-bottom: 20px;
  }
  .rp-banks {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 9px;
    margin-bottom: 14px;
  }
  .rp-bank-card {
    position: relative;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 11px 12px;
    background: rgba(243,239,234,0.03);
    border: 1px solid rgba(243,239,234,0.08);
    border-radius: 12px;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s, transform 0.15s;
    text-align: left;
    font-family: inherit;
  }
  .rp-bank-card:hover {
    border-color: rgba(243,239,234,0.18);
    transform: translateY(-1px);
  }
  .rp-bank-card.picked {
    border-color: rgba(212,168,32,0.55);
    background: rgba(212,168,32,0.07);
    box-shadow: 0 0 0 1px rgba(212,168,32,0.15);
  }
  .rp-bank-icon {
    width: 32px; height: 32px;
    border-radius: 8px;
    background: #F3EFEA;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 6px;
    flex-shrink: 0;
    overflow: hidden;
  }
  .rp-bank-icon img {
    width: 100%;
    height: 100%;
    object-fit: contain;
    border-radius: 4px;
    display: block;
  }
  .rp-bank-name {
    flex: 1;
    min-width: 0;
    font-size: 0.78rem;
    font-weight: 600;
    color: rgba(243,239,234,0.82);
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .rp-bank-check {
    width: 18px; height: 18px;
    border-radius: 50%;
    border: 1.5px solid rgba(243,239,234,0.2);
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;
  }
  .rp-bank-card.picked .rp-bank-check {
    background: #D4A820;
    border-color: #D4A820;
  }
  .rp-bank-note {
    font-size: 0.74rem;
    color: rgba(212,168,32,0.8);
    line-height: 1.5;
    margin-bottom: 16px;
    min-height: 1.1em;
  }
  .rp-bank-note b { color: rgba(212,168,32,0.95); }

  /* ── Termos ── */
  .rp-terms-summary {
    width: 82%;
    margin: 0 auto 16px;
    background: rgba(243,239,234,0.03);
    border: 1px solid rgba(243,239,234,0.08);
    border-radius: 10px;
    padding: 14px 16px;
    font-size: 0.76rem;
    color: rgba(243,239,234,0.52);
    line-height: 1.7;
    max-height: 340px;
    overflow-y: auto;
  }
  .rp-terms-summary::-webkit-scrollbar { width: 4px; }
  .rp-terms-summary::-webkit-scrollbar-track { background: transparent; }
  .rp-terms-summary::-webkit-scrollbar-thumb { background: rgba(212,168,32,0.25); border-radius: 2px; }

  .rp-check-row {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    margin-bottom: 10px;
    cursor: pointer;
  }
  .rp-check-row input[type=checkbox] {
    appearance: none;
    -webkit-appearance: none;
    width: 16px; height: 16px;
    border: 1.5px solid rgba(243,239,234,0.22);
    border-radius: 4px;
    background: transparent;
    cursor: pointer;
    flex-shrink: 0;
    margin-top: 1px;
    transition: all 0.15s;
    position: relative;
  }
  .rp-check-row input[type=checkbox]:checked {
    background: #D4A820;
    border-color: #D4A820;
  }
  .rp-check-row input[type=checkbox]:checked::after {
    content: '';
    position: absolute;
    left: 3px; top: 1px;
    width: 8px; height: 5px;
    border-left: 2px solid #0A0800;
    border-bottom: 2px solid #0A0800;
    transform: rotate(-45deg);
  }
  .rp-check-label {
    font-size: 0.76rem;
    color: rgba(243,239,234,0.6);
    line-height: 1.5;
  }
  .rp-check-label a { color: #D4A820; text-decoration: none; }
  .rp-check-label a:hover { text-decoration: underline; }

  /* ── Sucesso — hero em tela cheia, sem etapas ── */
  .rp-hero {
    position: relative;
    z-index: 2;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 40px 24px;
    animation: rp-up 0.7s cubic-bezier(.16,1,.3,1) both;
  }
  .rp-hero-ring {
    position: relative;
    width: 132px; height: 132px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 40px;
  }
  .rp-hero-ring::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: 50%;
    background: conic-gradient(from 0deg, transparent, rgba(212,168,32,0.75), transparent 55%);
    animation: rp-hero-spin 3.2s linear infinite;
    -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 3px), #000 calc(100% - 3px));
            mask: radial-gradient(farthest-side, transparent calc(100% - 3px), #000 calc(100% - 3px));
  }
  .rp-hero-ring::after {
    content: '';
    position: absolute;
    inset: 16px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(212,168,32,0.2) 0%, transparent 72%);
  }
  .rp-hero-icon {
    position: relative;
    width: 64px; height: 72px;
    animation: rp-hero-pulse 2.6s ease-in-out infinite, rp-pop 0.6s cubic-bezier(.16,1,.3,1) both;
  }
  .rp-hero-title {
    font-size: clamp(2.1rem, 5vw, 3.2rem);
    font-weight: 900;
    letter-spacing: -0.04em;
    color: #F3EFEA;
    line-height: 1.08;
    margin-bottom: 18px;
  }
  .rp-hero-sub {
    font-size: 0.95rem;
    color: rgba(243,239,234,0.5);
    line-height: 1.75;
    max-width: 380px;
    margin-bottom: 40px;
  }
  .rp-hero-btn {
    padding: 16px 56px;
    background: linear-gradient(135deg, #C89010, #D4A820, #E8C030);
    background-size: 200% auto;
    color: #0A0800;
    border: none;
    border-radius: 999px;
    font-family: inherit;
    font-size: 0.86rem;
    font-weight: 900;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    cursor: pointer;
    transition: background-position 0.3s, transform 0.15s, box-shadow 0.25s;
    box-shadow: 0 8px 30px rgba(212,168,32,0.28);
  }
  .rp-hero-btn:hover {
    background-position: right center;
    transform: translateY(-2px) scale(1.03);
    box-shadow: 0 12px 40px rgba(212,168,32,0.42);
  }
  .rp-hero-btn:active { transform: translateY(0) scale(0.98); }

  @keyframes rp-hero-spin { to { transform: rotate(360deg); } }
  @keyframes rp-hero-pulse {
    0%, 100% { filter: drop-shadow(0 0 10px rgba(212,168,32,0.35)); transform: scale(1); }
    50%      { filter: drop-shadow(0 0 22px rgba(212,168,32,0.6)); transform: scale(1.05); }
  }

  /* ── Login link ── */
  .rp-login-link {
    font-size: 0.7rem;
    color: rgba(243,239,234,0.32);
    text-align: center;
    margin-top: 4px;
  }
  .rp-login-link a { color: #D4A820; text-decoration: none; font-weight: 600; margin-left: 6px; }

  /* ── Mobile ── */
  @media (max-width: 900px) {
    .rp-layout { flex-direction: column; min-height: auto; gap: 0; padding: 40px 24px 48px; }
    .rp-left { display: none; }
    .rp-right { width: 100%; max-width: 420px; align-items: flex-start; }
    .rp-root { display: flex; align-items: center; justify-content: center; }
  }
`;

// ─── RegisterPage ─────────────────────────────────────────────────────────────
export const RegisterPage: React.FC = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);

  // Step 1
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [cpf, setCpf] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errs1, setErrs1] = useState({ name: '', email: '', cpf: '', phone: '', password: '', confirm: '' });
  const [checkingEmail, setCheckingEmail] = useState(false);
  const [emailTaken, setEmailTaken] = useState(false);

  const [loading, setLoading] = useState(false);

  // Step 2
  const [pickedBanks, setPickedBanks] = useState<string[]>([]);
  const toggleBank = (name: string) =>
    setPickedBanks(p => p.includes(name) ? p.filter(n => n !== name) : [...p, name]);

  // Step 3
  const [termAccepted, setTermAccepted] = useState(false);
  const [privAccepted, setPrivAccepted] = useState(false);
  const [termErr, setTermErr] = useState(false);

  const firstName = name.trim().split(' ')[0] || '';

  const validate1 = () => {
    const e = { name: '', email: '', cpf: '', phone: '', password: '', confirm: '' };
    if (!name.trim()) e.name = 'Preencha seu nome';
    if (!email.trim()) e.email = 'Preencha o e-mail';
    else if (!/\S+@\S+\.\S+/.test(email)) e.email = 'E-mail inválido';
    // CPF e telefone são opcionais — backend não armazena ainda
    if (cpf && cpf.replace(/\D/g, '').length < 11) e.cpf = 'CPF incompleto';
    if (phone && phone.replace(/\D/g, '').length < 10) e.phone = 'Telefone incompleto';
    if (!password) e.password = 'Preencha a senha';
    else if (password.length < 8) e.password = 'Mínimo 8 caracteres';
    if (!confirm) e.confirm = 'Confirme a senha';
    else if (confirm !== password) e.confirm = 'Senhas não coincidem';
    setErrs1(e);
    return !Object.values(e).some(Boolean);
  };

  const handleStep1 = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setEmailTaken(false);
    if (!validate1()) return;

    setCheckingEmail(true);
    try {
      const res = await fetch(`${API_BASE_URL}/auth/check-email?email=${encodeURIComponent(email.trim())}`);
      if (res.ok) {
        const data = await res.json();
        if (!data.available) {
          setEmailTaken(true);
          return;
        }
      }
      // Se a verificação falhar por erro de rede, segue em frente —
      // o /auth/register do passo 3 ainda pega um e-mail duplicado.
      setStep(2);
    } catch {
      setStep(2);
    } finally {
      setCheckingEmail(false);
    }
  };

  const handleStep3 = async () => {
    if (!termAccepted || !privAccepted) { setTermErr(true); return; }
    setLoading(true);
    try {
      // Registrar
      const res = await fetch(`${API_BASE_URL}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // accepted_terms: o backend exige o aceite e grava o instante (LGPD); só
        // chega aqui com os dois termos marcados. Telefone vai só os dígitos.
        body: JSON.stringify({
          email: email.trim(), password, full_name: name.trim(), accepted_terms: true,
          ...(phone.replace(/\D/g, '') ? { phone: `55${phone.replace(/\D/g, '')}` } : {}),
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        toast.error(data.detail || 'Erro ao criar conta. Tente novamente.');
        return;
      }

      // Auto-login
      const params = new URLSearchParams();
      params.append('username', email.trim());
      params.append('password', password);
      const loginRes = await fetch(`${API_BASE_URL}/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: params.toString(),
      });
      if (loginRes.ok) {
        const loginData = await loginRes.json();
        localStorage.setItem('jwt_token', loginData.access_token);
        if (loginData.user_id)      localStorage.setItem('user_id', loginData.user_id);
        if (loginData.refresh_token) localStorage.setItem('refresh_token', loginData.refresh_token);
        localStorage.setItem('user_name', loginData.full_name || name.trim());
        localStorage.setItem('user_email', email.trim());
      }

      setStep(4);
    } catch {
      toast.error('Erro de conexão. Verifique sua internet.');
    } finally {
      setLoading(false);
    }
  };

  const dot = (n: number) => step > n ? 'done' : step === n ? 'active' : '';

  const STEPS = ['Criar conta', 'Conectar banco', 'Termos de uso'];
  const STEP_DESC = [
    'Dados e credenciais de acesso',
    'Vincule sua conta bancária',
    'Leitura e aceite dos termos',
  ];

  return (
    <>
      <style>{css}</style>
      <div className="rp-root">
        <div className="rp-glow" aria-hidden="true" />
        <div className="rp-wm" aria-hidden="true">HIVE</div>

        {step === 4 ? (
          <div className="rp-hero">
            <div className="rp-hero-ring">
              <svg className="rp-hero-icon" viewBox="0 0 180 200" fill="none">
                <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="#7A5002"/>
                <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="#D4A820"/>
                <polygon points="100,16 110,22 110,178 100,184" fill="#090500"/>
                <path d="M58 100 L78 120 L122 78" stroke="#0A0800" strokeWidth="11" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <h1 className="rp-hero-title">{firstName ? `Bem-vindo, ${firstName}.` : 'Tudo certo.'}</h1>
            <p className="rp-hero-sub">
              Sua conta está criada. Agora você tem acesso à inteligência financeira que os bancos não querem que você veja.
            </p>
            <button className="rp-hero-btn" onClick={() => navigate('/chat')}>Entrar</button>
          </div>
        ) : (
        <div className="rp-layout">
          {/* ── ESQUERDO ── */}
          <div className="rp-left">
            <div className="rp-logo">
              <svg className="rp-logo-icon" width="24" height="28" viewBox="0 0 180 200" fill="none">
                <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="#7A5002"/>
                <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="#D4A820"/>
                <polygon points="100,16 110,22 110,178 100,184" fill="#090500"/>
              </svg>
              <span className="rp-logo-word">HIVE</span>
            </div>

            {/* Progress vertical — números grandes estilo "01" */}
            <div className="rp-step-nav">
              {STEPS.map((s, i) => (
                <div key={i} className="rp-step-row">
                  <div className="rp-step-col">
                    <div className={`rp-step-num ${dot(i + 1)}`}>{String(i + 1).padStart(2, '0')}</div>
                    <div className={`rp-step-vline ${step > i + 1 ? 'done' : ''}`} />
                  </div>
                  <div className="rp-step-info">
                    <div className={`rp-step-name ${dot(i + 1)}`}>{s}</div>
                    <div className="rp-step-desc">{STEP_DESC[i]}</div>
                  </div>
                </div>
              ))}
            </div>

            <div className="rp-left-footer">© 2025 HIVE · Todos os direitos reservados</div>
          </div>

          {/* ── DIREITO — card ── */}
          <div className="rp-right">
            <div style={{ width: '100%' }}>
              <div className="rp-card">
                {/* ── Step 1: Conta ── */}
                {step === 1 && (
                  <>
                    <div className="rp-card-label">Passo 1 de 3</div>
                    <div className="rp-card-title">Crie sua conta</div>

                    {/* Google */}
                    <button type="button" className="rp-google" onClick={() => alert('OAuth Google em breve')}>
                      <svg width="16" height="16" viewBox="0 0 24 24">
                        <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                        <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                        <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
                        <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                      </svg>
                      Continuar com Google
                    </button>
                    <div className="rp-or">ou</div>

                    <form onSubmit={handleStep1} noValidate>
                      <div className="rp-fields">
                        <div>
                          <label className="rp-field-label">Nome completo</label>
                          <input className={`rp-input${errs1.name ? ' err' : ''}`} type="text" placeholder="Seu nome completo"
                            value={name} onChange={e => { setName(e.target.value); if (errs1.name) setErrs1(p => ({...p, name: ''})); }}
                            autoComplete="name" autoFocus />
                          {errs1.name && <div className="rp-field-err">{errs1.name}</div>}
                        </div>

                        <div>
                          <label className="rp-field-label">E-mail</label>
                          <input className={`rp-input${errs1.email || emailTaken ? ' err' : ''}`} type="email" placeholder="seu@email.com"
                            value={email} onChange={e => { setEmail(e.target.value); if (errs1.email) setErrs1(p => ({...p, email: ''})); setEmailTaken(false); }}
                            autoComplete="email" />
                          {errs1.email && <div className="rp-field-err">{errs1.email}</div>}
                          {emailTaken && (
                            <div className="rp-field-err">
                              Este e-mail já tem uma conta. <Link to="/login">Entrar</Link>
                            </div>
                          )}
                        </div>

                        <div className="rp-row2">
                          <div>
                            <label className="rp-field-label">CPF</label>
                            <input className={`rp-input${errs1.cpf ? ' err' : ''}`} type="text" placeholder="000.000.000-00"
                              value={cpf} onChange={e => { setCpf(fmtCPF(e.target.value)); if (errs1.cpf) setErrs1(p => ({...p, cpf: ''})); }}
                              inputMode="numeric" />
                            {errs1.cpf && <div className="rp-field-err">{errs1.cpf}</div>}
                          </div>
                          <div>
                            <label className="rp-field-label">Telefone</label>
                            <input className={`rp-input${errs1.phone ? ' err' : ''}`} type="tel" placeholder="(00) 00000-0000"
                              value={phone} onChange={e => { setPhone(fmtPhone(e.target.value)); if (errs1.phone) setErrs1(p => ({...p, phone: ''})); }}
                              inputMode="numeric" />
                            {errs1.phone && <div className="rp-field-err">{errs1.phone}</div>}
                          </div>
                        </div>

                        <div>
                          <label className="rp-field-label">Senha</label>
                          <input className={`rp-input${errs1.password ? ' err' : ''}`} type="password" placeholder="Mínimo 8 caracteres"
                            value={password} onChange={e => { setPassword(e.target.value); if (errs1.password) setErrs1(p => ({...p, password: ''})); }}
                            autoComplete="new-password" />
                          {errs1.password && <div className="rp-field-err">{errs1.password}</div>}
                        </div>

                        <div>
                          <label className="rp-field-label">Confirmar senha</label>
                          <input className={`rp-input${errs1.confirm ? ' err' : ''}`} type="password" placeholder="Repita a senha"
                            value={confirm} onChange={e => { setConfirm(e.target.value); if (errs1.confirm) setErrs1(p => ({...p, confirm: ''})); }}
                            autoComplete="new-password" />
                          {errs1.confirm && <div className="rp-field-err">{errs1.confirm}</div>}
                        </div>
                      </div>

                      <button type="submit" className="rp-btn" disabled={checkingEmail}>
                        {checkingEmail ? 'Verificando…' : 'Continuar'}
                      </button>
                    </form>
                  </>
                )}

                {/* ── Step 2: Banco — vira fila de prioridade, não grade morta ── */}
                {step === 2 && (
                  <>
                    <div className="rp-card-label">Passo 2 de 3</div>
                    <div className="rp-bank-eyebrow">Open Banking em construção</div>
                    <div className="rp-card-title">Qual banco a gente conecta primeiro?</div>
                    <p className="rp-bank-info">
                      Ainda estamos construindo a conexão real via Open Banking. Marque o(s) banco(s) que você usa — isso entra direto na fila de prioridade de quem estamos construindo agora.
                    </p>
                    <div className="rp-banks">
                      {BANKS.map(b => {
                        const picked = pickedBanks.includes(b.name);
                        return (
                          <button key={b.name} type="button" className={`rp-bank-card${picked ? ' picked' : ''}`} onClick={() => toggleBank(b.name)}>
                            <div className="rp-bank-icon">
                              <img src={`https://www.google.com/s2/favicons?sz=128&domain=${b.domain}`} alt={b.name} />
                            </div>
                            <div className="rp-bank-name">{b.name}</div>
                            <span className="rp-bank-check">
                              {picked && <svg width="9" height="9" viewBox="0 0 10 10" fill="none"><path d="M1.5 5l2.5 2.5 4.5-4.5" stroke="#0A0800" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                    <p className="rp-bank-note">
                      {pickedBanks.length > 0
                        ? <>Beleza — assim que <b>{pickedBanks.join(', ')}</b> estiver pronto, você é avisado primeiro.</>
                        : 'Nenhum banco marcado ainda — tudo bem seguir sem escolher.'}
                    </p>
                    <button className="rp-btn" onClick={() => setStep(3)}>Continuar</button>
                  </>
                )}

                {/* ── Step 3: Termos ── */}
                {step === 3 && (
                  <>
                    <div className="rp-card-label">Passo 3 de 3</div>
                    <div className="rp-card-title">Termos e privacidade</div>
                    <div className="rp-terms-summary">
                      <strong style={{ color: 'rgba(243,239,234,0.75)', display: 'block', marginBottom: 6 }}>Termos de Uso</strong>
                      O HIVE é uma plataforma de análise financeira pessoal. Ao utilizar nossos serviços, você concorda que seus dados financeiros serão usados exclusivamente para gerar insights personalizados dentro da plataforma. Não vendemos, alugamos ou compartilhamos seus dados com terceiros para fins comerciais. Você pode revogar o acesso e solicitar a exclusão da conta a qualquer momento.
                      <br /><br />
                      <strong style={{ color: 'rgba(243,239,234,0.75)', display: 'block', marginBottom: 6 }}>Política de Privacidade</strong>
                      Todos os dados pessoais coletados são tratados em conformidade com a Lei Geral de Proteção de Dados (LGPD — Lei 13.709/2018). Suas senhas são armazenadas com hash criptográfico. Seus dados financeiros são transmitidos e armazenados com criptografia TLS/AES-256. O HIVE não acessa sua conta bancária diretamente — apenas analisa os dados que você autoriza a compartilhar via Open Banking.
                    </div>

                    <label className="rp-check-row">
                      <input type="checkbox" checked={termAccepted} onChange={e => { setTermAccepted(e.target.checked); setTermErr(false); }} />
                      <span className="rp-check-label">Li e aceito os <a href="#">Termos de Uso</a></span>
                    </label>
                    <label className="rp-check-row">
                      <input type="checkbox" checked={privAccepted} onChange={e => { setPrivAccepted(e.target.checked); setTermErr(false); }} />
                      <span className="rp-check-label">Li e aceito a <a href="#">Política de Privacidade</a></span>
                    </label>

                    {termErr && (
                      <div className="rp-field-err" style={{ marginBottom: 10 }}>
                        Aceite os termos para continuar
                      </div>
                    )}

                    <button className="rp-btn" style={{ marginTop: 14 }} onClick={handleStep3} disabled={loading}>
                      {loading ? 'Criando conta…' : 'Confirmar e entrar'}
                    </button>
                  </>
                )}
              </div>

              {step === 1 && (
                <div className="rp-login-link" style={{ marginTop: 14 }}>
                  Já tem uma conta? <Link to="/login">Entrar</Link>
                </div>
              )}
            </div>
          </div>
        </div>
        )}
      </div>
    </>
  );
};
