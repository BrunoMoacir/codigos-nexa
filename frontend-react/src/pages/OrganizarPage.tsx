import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { nexaApi } from '../api/nexa';
import { isDemoMode } from '../utils/demoMode';
import type { Transaction, Goal, CreditCard } from '../api/types';

// ─── Gráfico de barras — Receita x Gastos por mês, com glow e tooltip ────────
function BarChart({ income, expense, labels, h = 160 }: { income: number[]; expense: number[]; labels: string[]; h?: number }) {
  const [mounted, setMounted] = useState(false);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  useEffect(() => {
    const t = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(t);
  }, []);

  if (!income.length) return null;
  const max = Math.max(...income, ...expense, 1);

  return (
    <div className="op-bars-wrap">
      <div className="op-bars-legend">
        <span className="op-bars-legend-item"><i className="op-bars-swatch in" />Receita</span>
        <span className="op-bars-legend-item"><i className="op-bars-swatch out" />Gastos</span>
      </div>
      <div className="op-bars-row" style={{ height: h }} onMouseLeave={() => setHoverIdx(null)}>
        {income.map((v, i) => {
          const ev = expense[i] || 0;
          const inPct = (v / max) * 100;
          const outPct = (ev / max) * 100;
          return (
            <div key={i} className="op-bar-group" onMouseEnter={() => setHoverIdx(i)}>
              {hoverIdx === i && (
                <div className="op-bar-tip">
                  <span className="op-bar-tip-label">{labels[i]}</span>
                  <span className="op-bar-tip-in">Receita {fmtBRL(v)}</span>
                  <span className="op-bar-tip-out">Gastos {fmtBRL(ev)}</span>
                </div>
              )}
              <div className="op-bar-pair">
                <div className="op-bar in"  style={{ height: mounted ? `${inPct}%`  : '0%' }} />
                <div className="op-bar out" style={{ height: mounted ? `${outPct}%` : '0%' }} />
              </div>
            </div>
          );
        })}
      </div>
      <div className="op-chart-labels">
        {labels.map(m => <span key={m} className="op-chart-label">{m}</span>)}
      </div>
    </div>
  );
}

// ─── Empty state (honesto — sem banco conectado, sem modo demo) ──────────────
function EmptyPanel({ icon, title, sub }: { icon: string; title: string; sub: string }) {
  return (
    <div className="op-empty">
      <div className="op-empty-icon">{icon}</div>
      <div className="op-empty-title">{title}</div>
      <div className="op-empty-sub">{sub}</div>
    </div>
  );
}

// ─── Cartão de crédito visual ─────────────────────────────────────────────────
function CardVisual({ card }: { card: { bank_name?: string | null; brand?: string | null; level?: string | null; last4?: string | null; credit_limit?: number | null; available_credit_limit?: number | null } }) {
  return (
    <div className="op-card-visual">
      <div className="op-card-visual-top">
        <div className="op-card-visual-bankblock">
          <span className="op-card-visual-bank">{card.bank_name || 'Cartão'}</span>
          <span className="op-card-visual-issuer">{(card.level || 'CRÉDITO').toUpperCase()}</span>
        </div>
        <div className="op-card-visual-nfc">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <path d="M8.5 8.5a5 5 0 0 1 7 0M6 6a9 9 0 0 1 12 0M11 11a1.5 1.5 0 0 1 2 0" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
          </svg>
        </div>
      </div>

      <div className="op-card-visual-chip" />

      <div className="op-card-visual-number">•••• &nbsp; •••• &nbsp; •••• &nbsp; {card.last4 || '····'}</div>

      <div className="op-card-visual-bottom">
        <span className="op-card-visual-avail">Disponível {fmtBRL(card.available_credit_limit ?? 0)}</span>
        <span className="op-card-visual-brand">{(card.brand || 'Cartão').toUpperCase()}</span>
      </div>
    </div>
  );
}

const css = `
  .op { display: flex; flex-direction: column; min-height: 100vh; background: #0A0806; padding: 28px 28px 40px; gap: 20px; }

  /* Resumo — um número grande (Saldo) com Receita/Gastos como texto de apoio */
  .op-hero-stat { display: flex; flex-direction: column; gap: 3px; margin-bottom: 22px; }
  .op-hero-label { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: rgba(243,239,234,0.32); }
  .op-hero-val { font-size: 2.4rem; font-weight: 900; letter-spacing: -0.05em; font-variant-numeric: tabular-nums; color: #F3EFEA; line-height: 1.1; }
  .op-hero-val.gold  { color: #D4A820; }
  .op-hero-val.green { color: #2EC8A4; }
  .op-hero-val.red   { color: #F07A64; }
  .op-hero-val.dim   { color: rgba(243,239,234,0.2); }
  .op-hero-sub { font-size: 0.82rem; font-weight: 600; color: rgba(243,239,234,0.4); }
  .op-hero-sub .green { color: #2EC8A4; }
  .op-hero-sub .red   { color: #F07A64; }
  .op-hero-sep { margin: 0 8px; color: rgba(243,239,234,0.18); }

  /* Row */
  .op-row { display: grid; grid-template-columns: 1fr 340px; gap: 14px; align-items: start; }
  .op-row.full { grid-template-columns: 1fr; }

  /* Panels */
  .op-panel {
    background: linear-gradient(165deg, #141210 0%, #100E0B 55%);
    border: 1px solid rgba(243,239,234,0.07);
    border-radius: 16px;
    padding: 20px 22px;
    overflow: hidden;
    position: relative;
  }
  .op-panel::before {
    content: '';
    position: absolute; top: 0; left: 20px; right: 20px; height: 1px;
    background: linear-gradient(90deg, transparent, rgba(243,239,234,0.14), transparent);
  }
  .op-panel-head {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 18px;
  }
  .op-panel-title { font-size: 0.78rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: rgba(243,239,234,0.35); }
  .op-panel-tag { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.04em; color: rgba(243,239,234,0.32); font-style: italic; }

  /* Empty state */
  .op-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 30px 16px; gap: 6px; min-height: 120px; }
  .op-empty-icon { font-size: 1.5rem; opacity: 0.25; margin-bottom: 2px; }
  .op-empty-title { font-size: 0.84rem; font-weight: 700; color: rgba(243,239,234,0.5); }
  .op-empty-sub { font-size: 0.74rem; color: rgba(243,239,234,0.28); max-width: 240px; line-height: 1.5; }

  /* Chart x-axis labels */
  .op-chart-labels { display: flex; justify-content: space-between; margin-top: 6px; }
  .op-chart-label { font-size: 0.62rem; color: rgba(243,239,234,0.2); font-variant-numeric: tabular-nums; }

  /* Gráfico de barras — Receita x Gastos por mês */
  .op-bars-wrap { display: flex; flex-direction: column; }
  .op-bars-legend { display: flex; gap: 16px; margin-bottom: 14px; }
  .op-bars-legend-item { display: flex; align-items: center; gap: 6px; font-size: 0.72rem; font-weight: 600; color: rgba(243,239,234,0.45); }
  .op-bars-swatch { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }
  .op-bars-swatch.in  { background: #2EC8A4; }
  .op-bars-swatch.out { background: #F07A64; }
  .op-bars-row { display: flex; align-items: flex-end; gap: 4px; }
  .op-bar-group { flex: 1; position: relative; display: flex; justify-content: center; align-items: flex-end; height: 100%; cursor: pointer; }
  .op-bar-pair { display: flex; align-items: flex-end; justify-content: center; gap: 3px; width: 100%; height: 100%; }
  .op-bar { width: 34%; max-width: 14px; border-radius: 4px 4px 2px 2px; transition: height 0.8s cubic-bezier(.34,1.4,.4,1), filter 0.15s ease; }
  .op-bar.in  { background: linear-gradient(180deg, #57E6C2, #2EC8A4); box-shadow: 0 0 12px rgba(46,200,164,0.28); }
  .op-bar.out { background: linear-gradient(180deg, #F5987F, #F07A64); box-shadow: 0 0 12px rgba(240,122,100,0.22); }
  .op-bar-group:hover .op-bar { filter: brightness(1.2); }
  .op-bar-tip {
    position: absolute; bottom: 100%; margin-bottom: 10px; left: 50%; transform: translateX(-50%);
    background: #1A1613; border: 1px solid rgba(243,239,234,0.14);
    border-radius: 10px; padding: 8px 12px;
    display: flex; flex-direction: column; gap: 3px;
    white-space: nowrap; z-index: 6; pointer-events: none;
    box-shadow: 0 10px 24px rgba(0,0,0,0.45);
  }
  .op-bar-tip-label { font-size: 0.6rem; font-weight: 700; color: rgba(243,239,234,0.4); text-transform: uppercase; letter-spacing: 0.06em; }
  .op-bar-tip-in  { font-size: 0.76rem; font-weight: 700; color: #2EC8A4; }
  .op-bar-tip-out { font-size: 0.76rem; font-weight: 700; color: #F07A64; }

  /* Categorias — linha simples, sem cartão/pílula por item */
  .op-cats { display: flex; flex-wrap: wrap; column-gap: 22px; row-gap: 10px; padding-top: 14px; border-top: 1px solid rgba(243,239,234,0.06); }
  .op-cat-chip { display: flex; align-items: center; gap: 7px; }
  .op-cat-dot { width: 6px; height: 6px; border-radius: 2px; flex-shrink: 0; }
  .op-cat-name { font-size: 0.78rem; color: rgba(243,239,234,0.5); }
  .op-cat-val  { font-size: 0.78rem; font-weight: 700; color: rgba(243,239,234,0.9); font-variant-numeric: tabular-nums; }

  /* Metas */
  .op-goals { display: flex; flex-direction: column; gap: 16px; }
  .op-goal-row { display: flex; flex-direction: column; gap: 6px; }
  .op-goal-top { display: flex; justify-content: space-between; align-items: center; }
  .op-goal-name { font-size: 0.82rem; font-weight: 600; color: #F3EFEA; }
  .op-goal-pct  { font-size: 0.72rem; font-weight: 800; color: #D4A820; }
  .op-goal-track { height: 6px; background: rgba(243,239,234,0.07); border-radius: 3px; overflow: hidden; }
  .op-goal-fill  { height: 100%; border-radius: 3px; background: linear-gradient(90deg, #D4A820, #F0C840); transition: width 0.6s ease; }
  .op-goal-sub   { font-size: 0.68rem; color: rgba(243,239,234,0.22); font-variant-numeric: tabular-nums; }

  /* Transações */
  .op-txn-list { display: flex; flex-direction: column; }
  .op-txn-row {
    display: flex; align-items: center; gap: 14px;
    padding: 11px 0;
    border-bottom: 1px solid rgba(243,239,234,0.05);
  }
  .op-txn-row:last-child { border-bottom: none; }
  .op-txn-arrow { flex-shrink: 0; display: flex; }
  .op-txn-arrow.in  { color: #2EC8A4; }
  .op-txn-arrow.out { color: rgba(243,239,234,0.3); }
  .op-txn-info { flex: 1; min-width: 0; }
  .op-txn-desc { font-size: 0.83rem; font-weight: 600; color: #F3EFEA; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .op-txn-date { font-size: 0.68rem; color: rgba(243,239,234,0.25); margin-top: 1px; }
  .op-txn-val  { font-size: 0.88rem; font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .op-txn-val.in  { color: #2EC8A4; }
  .op-txn-val.out { color: rgba(243,239,234,0.7); }

  /* Cartões — layout copiado 1:1 da referência (Loftbank): nome+selo em cima
     à esquerda, ícone contactless em cima à direita, número grande no meio,
     disponível + bandeira embaixo. */
  .op-cards-row { display: flex; gap: 16px; overflow-x: auto; padding-bottom: 4px; }
  .op-card-visual {
    min-width: 300px; flex: 1;
    max-width: 360px;
    aspect-ratio: 1.586 / 1;
    border-radius: 18px;
    padding: 22px 24px;
    background:
      radial-gradient(120% 140% at 15% 0%, rgba(255,255,255,0.07), transparent 55%),
      linear-gradient(135deg, #45484D 0%, #2A2C30 45%, #17181B 100%);
    position: relative;
    overflow: hidden;
    display: flex; flex-direction: column;
    box-shadow: 0 4px 10px rgba(0,0,0,0.25), 0 20px 40px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.06);
  }
  .op-card-visual::after {
    content: '';
    position: absolute; inset: 0;
    background: linear-gradient(115deg, transparent 35%, rgba(255,255,255,0.05) 48%, transparent 60%);
    pointer-events: none;
  }
  .op-card-visual-top { display: flex; justify-content: space-between; align-items: flex-start; position: relative; z-index: 1; }
  .op-card-visual-bankblock { display: flex; flex-direction: column; gap: 3px; }
  .op-card-visual-bank { font-size: 1rem; font-weight: 800; color: #F3EFEA; letter-spacing: -0.01em; }
  .op-card-visual-issuer { font-size: 0.58rem; font-weight: 700; letter-spacing: 0.1em; color: rgba(243,239,234,0.42); }
  .op-card-visual-nfc {
    width: 24px; height: 24px;
    display: flex; align-items: center; justify-content: center;
    color: rgba(243,239,234,0.65);
    flex-shrink: 0;
  }
  .op-card-visual-chip {
    width: 34px; height: 25px; border-radius: 5px; margin: 18px 0 14px;
    background: linear-gradient(155deg, #E8D9A8 0%, #C9AE6F 45%, #B08F4E 100%);
    position: relative; z-index: 1;
    box-shadow: inset 0 0 0 1px rgba(0,0,0,0.15);
  }
  .op-card-visual-chip::before, .op-card-visual-chip::after {
    content: ''; position: absolute; background: rgba(0,0,0,0.18);
  }
  .op-card-visual-chip::before { left: 0; right: 0; top: 50%; height: 1px; transform: translateY(-50%); }
  .op-card-visual-chip::after { top: 0; bottom: 0; left: 50%; width: 1px; transform: translateX(-50%); }
  .op-card-visual-number {
    font-size: 1.2rem; font-weight: 500; letter-spacing: 0.1em;
    color: #F3EFEA; font-variant-numeric: tabular-nums;
    position: relative; z-index: 1;
  }
  .op-card-visual-bottom { display: flex; justify-content: space-between; align-items: flex-end; position: relative; z-index: 1; margin-top: auto; }
  .op-card-visual-avail { font-size: 0.68rem; font-weight: 500; color: rgba(243,239,234,0.5); }
  .op-card-visual-brand { font-size: 0.98rem; font-weight: 800; font-style: italic; letter-spacing: 0.02em; color: #F3EFEA; }

  .op-card-add {
    min-width: 200px; flex: 0 0 auto;
    aspect-ratio: 1.586 / 1;
    border-radius: 18px;
    border: 1.5px dashed rgba(243,239,234,0.16);
    background: transparent;
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px;
    color: rgba(243,239,234,0.4);
    font-family: inherit; font-size: 0.82rem; font-weight: 700;
    cursor: pointer;
    transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
  }
  .op-card-add:hover { border-color: rgba(212,168,32,0.5); color: #D4A820; background: rgba(212,168,32,0.04); }
  .op-card-add-icon { font-size: 1.6rem; font-weight: 400; line-height: 1; }

  /* Connect CTA */
  .op-cta {
    display: flex; align-items: center; justify-content: space-between; gap: 20px;
    background: rgba(212,168,32,0.06);
    border: 1px solid rgba(212,168,32,0.14);
    border-radius: 14px; padding: 18px 22px;
  }
  .op-cta-text { font-size: 0.88rem; font-weight: 700; color: rgba(243,239,234,0.7); }
  .op-cta-sub  { font-size: 0.72rem; color: rgba(243,239,234,0.28); margin-top: 3px; }
  .op-cta-btn  { padding: 9px 18px; background: #D4A820; color: #0A0800; border: none; border-radius: 8px; font-family: inherit; font-size: 0.8rem; font-weight: 800; letter-spacing: 0.04em; cursor: pointer; white-space: nowrap; transition: background 0.15s; flex-shrink: 0; }
  .op-cta-btn:hover { background: #E8C030; }

  /* Skeleton */
  .op-skel { background: rgba(243,239,234,0.05); border-radius: 14px; animation: op-pulse 1.4s ease-in-out infinite; }
  @keyframes op-pulse { 0%,100%{opacity:0.35} 50%{opacity:0.7} }

  @media (max-width: 1024px) {
    .op-row  { grid-template-columns: 1fr; }
  }
  @media (max-width: 600px) {
    .op { padding: 16px 14px 32px; }
  }
`;

const CAT_COLORS = ['#D4A820','#2EC8A4','#60B0F2','#F07A64','#ECB040','#B088E0'];

const DEMO_SPEND  = [3200, 2800, 3600, 3100, 4200, 3800, 4000, 3500, 3900, 4100, 3700, 4000];
const DEMO_INCOME = [6000, 5800, 6200, 6100, 7200, 6800, 7000, 6900, 7100, 7000, 6950, 7000];
const DEMO_MONTHS = ['Set','Out','Nov','Dez','Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago'];

const DEMO_CATS = [
  { name: 'Moradia',     color: '#D4A820', pct: 38, val: 'R$ 1.520' },
  { name: 'Alimentação', color: '#2EC8A4', pct: 22, val: 'R$  880' },
  { name: 'Transporte',  color: '#60B0F2', pct: 14, val: 'R$  560' },
  { name: 'Saúde',       color: '#F07A64', pct: 10, val: 'R$  400' },
  { name: 'Lazer',       color: '#ECB040', pct:  9, val: 'R$  360' },
  { name: 'Outros',      color: '#B088E0', pct:  7, val: 'R$  280' },
];

const DEMO_GOALS = [
  { name: 'Reserva de emergência', curr: 8400,  total: 15000 },
  { name: 'Viagem Europa',         curr: 3200,  total: 12000 },
  { name: 'Notebook novo',         curr: 1800,  total: 2500  },
];

const DEMO_TXNS = [
  { desc: 'Salário',       date: 'Hoje',   type: 'in',  val: '+R$ 6.200,00' },
  { desc: 'Aluguel',       date: 'Ontem',  type: 'out', val:  'R$ 1.400,00' },
  { desc: 'iFood',         date: '26 ago', type: 'out', val:    'R$  87,50' },
  { desc: 'Supermercado',  date: '25 ago', type: 'out', val:   'R$  312,00' },
  { desc: 'Freelance',     date: '24 ago', type: 'in',  val:  '+R$  800,00' },
  { desc: 'Netflix',       date: '22 ago', type: 'out', val:    'R$   55,90' },
  { desc: 'Farmácia',      date: '21 ago', type: 'out', val:    'R$   43,20' },
  { desc: 'Combustível',   date: '20 ago', type: 'out', val:   'R$  180,00' },
];

const DEMO_CARDS = [
  { bank_name: 'Nubank', brand: 'Mastercard', level: 'Platinum', last4: '4532', credit_limit: 8500, available_credit_limit: 3180 },
  { bank_name: 'Itaú',   brand: 'Visa',        level: 'Gold',     last4: '1187', credit_limit: 5000, available_credit_limit: 4260 },
];

function fmtBRL(n: number) {
  return `R$ ${Math.abs(n).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`;
}

function fmtDate(d: string) {
  try { return new Date(d).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' }); }
  catch { return d; }
}

function buildCats(txns: Transaction[]) {
  const map: Record<string, number> = {};
  for (const t of txns) {
    if (t.amount < 0 || t.type === 'expense') {
      const k = t.category || 'Outros';
      map[k] = (map[k] || 0) + Math.abs(t.amount);
    }
  }
  const entries = Object.entries(map).sort((a, b) => b[1] - a[1]).slice(0, 6);
  const total = entries.reduce((s, [, v]) => s + v, 0) || 1;
  return entries.map(([name, val], i) => ({
    name, color: CAT_COLORS[i] || '#947060',
    pct: Math.round((val / total) * 100), val: fmtBRL(val),
  }));
}

function buildSpend(txns: Transaction[]) {
  const map: Record<string, number> = {};
  for (const t of txns) {
    if (t.amount < 0 || t.type === 'expense') {
      const m = t.date?.slice(0, 7) || '';
      map[m] = (map[m] || 0) + Math.abs(t.amount);
    }
  }
  const vals = Object.values(map);
  return vals.length >= 2 ? vals.slice(-12) : [];
}

function buildIncome(txns: Transaction[]) {
  const map: Record<string, number> = {};
  for (const t of txns) {
    if (t.amount > 0 || t.type === 'income') {
      const m = t.date?.slice(0, 7) || '';
      map[m] = (map[m] || 0) + Math.abs(t.amount);
    }
  }
  const vals = Object.values(map);
  return vals.length >= 2 ? vals.slice(-12) : [];
}

export const OrganizarPage: React.FC = () => {
  const navigate = useNavigate();
  const userId = localStorage.getItem('user_id') || '';
  const demo = isDemoMode(userId);

  const txnsQ = useQuery({
    queryKey: ['transactions', userId],
    queryFn: () => nexaApi.getTransactions(userId, 100),
    enabled: !!userId,
    retry: 1, staleTime: 2 * 60 * 1000,
  });

  const goalsQ = useQuery({
    queryKey: ['goals', userId],
    queryFn: () => nexaApi.getGoals(userId),
    enabled: !!userId,
    retry: 1, staleTime: 2 * 60 * 1000,
  });

  const cardsQ = useQuery({
    queryKey: ['cards', userId],
    queryFn: () => nexaApi.getCards(),
    enabled: !!userId,
    retry: 1, staleTime: 2 * 60 * 1000,
  });

  const loading = txnsQ.isLoading || goalsQ.isLoading || cardsQ.isLoading;
  const txns: Transaction[] = txnsQ.data?.transactions || [];
  const goals: Goal[] = goalsQ.data?.goals || [];
  const realCards: CreditCard[] = cardsQ.data || [];

  // "Real" aqui = banco conectado com transações sincronizadas. Metas e
  // cartões têm suas próprias fontes (goals é manual; cards vem do sync do
  // Pluggy) — cada seção decide sozinha entre real / demo / vazio honesto.
  const hasReal = txns.length > 0;
  const hasRealGoals = goals.length > 0;
  const hasRealCards = realCards.length > 0;
  const showDemo = !hasReal && demo;
  const showEmpty = !hasReal && !demo;

  const cats: { name: string; color: string; pct: number; val: string }[] =
    hasReal ? buildCats(txns) : showDemo ? DEMO_CATS : [];
  const spendData  = hasReal ? buildSpend(txns)  : showDemo ? DEMO_SPEND  : [];
  const incomeData = hasReal ? buildIncome(txns) : showDemo ? DEMO_INCOME : [];
  const chartLen = Math.min(spendData.length, incomeData.length);
  const displayGoals = hasRealGoals ? goals : (!hasRealGoals && demo ? DEMO_GOALS : []);
  const displayCards: { bank_name?: string | null; brand?: string | null; level?: string | null; last4?: string | null; credit_limit?: number | null; available_credit_limit?: number | null }[] =
    hasRealCards ? realCards : (!hasRealCards && demo ? DEMO_CARDS : []);

  const totalIn  = txns.filter(t => t.amount > 0 || t.type === 'income').reduce((s, t) => s + Math.abs(t.amount), 0);
  const totalOut = txns.filter(t => t.amount < 0 || t.type === 'expense').reduce((s, t) => s + Math.abs(t.amount), 0);
  const saldo    = totalIn - totalOut;

  const displayTxns = hasReal
    ? txns.slice(0, 8).map(t => ({
        desc: t.description,
        date: fmtDate(t.date),
        type: t.amount > 0 || t.type === 'income' ? 'in' : 'out',
        val:  (t.amount > 0 || t.type === 'income' ? '+' : '') + fmtBRL(t.amount),
      }))
    : showDemo ? DEMO_TXNS : [];

  return (
    <AppShell current="organizar">
      <style>{css}</style>
      <div className="op">

        {/* ── Resumo + finanças por mês (um painel só) ── */}
        {loading ? (
          <div className="op-panel"><div className="op-skel" style={{ height: 240 }} /></div>
        ) : (
          <div className="op-panel">
            <div className="op-panel-head">
              <span className="op-panel-title">Resumo do mês</span>
              {showDemo && <span className="op-panel-tag">exemplo</span>}
            </div>

            <div className="op-hero-stat">
              <span className="op-hero-label">Saldo do mês</span>
              <span className={`op-hero-val ${hasReal ? (saldo >= 0 ? 'green' : 'red') : showDemo ? 'gold' : 'dim'}`}>
                {hasReal ? fmtBRL(saldo) : showDemo ? 'R$ 3.000' : '—'}
              </span>
              <span className="op-hero-sub">
                <span className="green">Receita {hasReal ? fmtBRL(totalIn) : showDemo ? 'R$ 7.000' : '—'}</span>
                <span className="op-hero-sep">·</span>
                <span className="red">Gastos {hasReal ? fmtBRL(totalOut) : showDemo ? 'R$ 4.000' : '—'}</span>
              </span>
            </div>

            {chartLen > 0 ? (
              <>
                <BarChart
                  income={incomeData.slice(-chartLen)}
                  expense={spendData.slice(-chartLen)}
                  labels={DEMO_MONTHS.slice(-chartLen)}
                  h={160}
                />
                {cats.length > 0 && (
                  <div className="op-cats">
                    {cats.map(c => (
                      <div key={c.name} className="op-cat-chip">
                        <div className="op-cat-dot" style={{ background: c.color }} />
                        <span className="op-cat-name">{c.name}</span>
                        <span className="op-cat-val">{c.val}</span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <EmptyPanel icon="📈" title="Nenhum gasto registrado ainda" sub="Conecte seu banco pra ver a evolução dos seus gastos mês a mês." />
            )}
          </div>
        )}

        {/* ── Cartões ── */}
        {!loading && (
          <div className="op-panel">
            <div className="op-panel-head">
              <span className="op-panel-title">Cartões</span>
              {showDemo && !hasRealCards && <span className="op-panel-tag">exemplo</span>}
            </div>
            {displayCards.length === 0 && (
              <div className="op-empty" style={{ paddingBottom: 6 }}>
                <div className="op-empty-icon">💳</div>
                <div className="op-empty-title">Nenhum cartão ainda</div>
                <div className="op-empty-sub">Conecte seu banco ou cadastre um cartão na mão.</div>
              </div>
            )}
            <div className="op-cards-row">
              {displayCards.map((c, i) => <CardVisual key={i} card={c} />)}
              <button type="button" className="op-card-add" onClick={() => navigate('/organizar/cartao/novo')}>
                <span className="op-card-add-icon">+</span>
                Adicionar cartão
              </button>
            </div>
          </div>
        )}

        {/* ── Transações + Metas ── */}
        {!loading && (
          <div className="op-row">
            <div className="op-panel">
              <div className="op-panel-head">
                <span className="op-panel-title">Movimentações recentes</span>
                {showDemo && <span className="op-panel-tag">exemplo</span>}
              </div>
              {displayTxns.length > 0 ? (
                <div className="op-txn-list">
                  {displayTxns.map((t, i) => (
                    <div key={i} className="op-txn-row">
                      <svg className={`op-txn-arrow ${t.type}`} width="14" height="14" viewBox="0 0 14 14" fill="none">
                        {t.type === 'in'
                          ? <path d="M7 11V3M3.5 6.5 7 3l3.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
                          : <path d="M7 3v8M3.5 7.5 7 11l3.5-3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>}
                      </svg>
                      <div className="op-txn-info">
                        <div className="op-txn-desc">{t.desc}</div>
                        <div className="op-txn-date">{t.date}</div>
                      </div>
                      <div className={`op-txn-val ${t.type}`}>{t.val}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyPanel icon="↔" title="Nenhuma movimentação ainda" sub="Suas transações aparecem aqui assim que você conectar uma conta." />
              )}
            </div>

            <div className="op-panel">
              <div className="op-panel-head">
                <span className="op-panel-title">Metas</span>
                {!hasRealGoals && demo && <span className="op-panel-tag">exemplo</span>}
              </div>
              {displayGoals.length > 0 ? (
                <div className="op-goals">
                  {displayGoals.map((g: Goal | typeof DEMO_GOALS[0]) => {
                    const curr  = 'current_amount' in g ? g.current_amount : (g as { curr: number }).curr;
                    const total = 'target_amount'  in g ? g.target_amount  : (g as { total: number }).total;
                    const pct   = Math.min(100, Math.round((curr / total) * 100));
                    return (
                      <div key={g.name} className="op-goal-row">
                        <div className="op-goal-top">
                          <span className="op-goal-name">{g.name}</span>
                          <span className="op-goal-pct">{pct}%</span>
                        </div>
                        <div className="op-goal-track">
                          <div className="op-goal-fill" style={{ width: `${pct}%` }} />
                        </div>
                        <div className="op-goal-sub">{fmtBRL(curr)} de {fmtBRL(total)}</div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <EmptyPanel icon="🎯" title="Nenhuma meta ainda" sub="Crie sua primeira meta financeira e acompanhe o progresso por aqui." />
              )}
            </div>
          </div>
        )}

        {/* ── CTA banco ── */}
        {showEmpty && !loading && (
          <div className="op-cta">
            <div>
              <div className="op-cta-text">Conecte seu banco para dados reais</div>
              <div className="op-cta-sub">Open Finance · leitura apenas · criptografado</div>
            </div>
            <button className="op-cta-btn" onClick={() => navigate('/connections')}>Conectar banco →</button>
          </div>
        )}
      </div>
    </AppShell>
  );
};
