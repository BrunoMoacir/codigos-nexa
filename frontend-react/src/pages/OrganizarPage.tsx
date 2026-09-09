import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { nexaApi } from '../api/nexa';
import { isDemoMode } from '../utils/demoMode';
import type { Transaction, Goal, CreditCard } from '../api/types';

// ─── Gráfico de barras flat — valor acima da barra + eixo com grade ──────────
function fmtShort(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1000) return `${(n / 1000).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}k`;
  return n.toLocaleString('pt-BR', { maximumFractionDigits: 0 });
}

interface BarPoint { key: string; label: string; value: number }

function SingleBarChart({
  series, currentKey, onSelect, color = '#D4A820', currentColor = '#F0C840', h = 190,
}: { series: BarPoint[]; currentKey?: string | null; onSelect?: (key: string) => void; color?: string; currentColor?: string; h?: number }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const t = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(t);
  }, [series.length]);
  if (!series.length) return null;
  const max = Math.max(...series.map(s => s.value), 1);
  const ticks = [1, 0.75, 0.5, 0.25, 0].map(f => Math.round(max * f));

  return (
    <div className="op-sbar-wrap">
      <div className="op-sbar-plot" style={{ height: h }}>
        <div className="op-sbar-axis">
          {ticks.map((t, i) => <span key={i}>{fmtShort(t)}</span>)}
        </div>
        <div className="op-sbar-plotarea">
          <div className="op-sbar-grid">
            {ticks.map((_, i) => <div key={i} />)}
          </div>
          <div className="op-sbar-bars">
            {series.map((s) => {
              const isCurrent = s.key === currentKey;
              return (
                <div key={s.key} className="op-sbar-col">
                  <span className={`op-sbar-val${isCurrent ? ' current' : ''}`}>{fmtShort(s.value)}</span>
                  <button
                    type="button"
                    className={`op-sbar-bar${isCurrent ? ' current' : ''}${onSelect ? ' clickable' : ''}`}
                    style={{ height: mounted ? `${(s.value / max) * 100}%` : '0%', background: isCurrent ? currentColor : color }}
                    onClick={() => onSelect?.(s.key)}
                    disabled={!onSelect}
                    aria-label={s.label}
                  />
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <div className="op-chart-labels">
        <div className="op-sbar-axis-spacer" />
        <div className="op-sbar-labels">
          {series.map(s => (
            <div key={s.key} className="op-sbar-label-col">
              <span className={`op-chart-label${s.key === currentKey ? ' current' : ''}`}>{s.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Série diária sintética pro modo demo (soma ≈ total do mês) ──────────────
function demoDailySeries(total: number, seed: number, days = 30): number[] {
  const base = total / days;
  const raw = Array.from({ length: days }, (_, d) => {
    const wave = Math.sin((d + seed * 7) * 0.9) * 0.4 + Math.sin((d + seed) * 0.35) * 0.3;
    return Math.max(0, base * (1 + wave));
  });
  const sum = raw.reduce((s, v) => s + v, 0) || 1;
  return raw.map(v => Math.round(v * (total / sum)));
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

  /* Resumo — um número grande (Saldo), alinhado à esquerda, com Receita/Gastos de apoio */
  .op-hero-stat { display: flex; flex-direction: column; gap: 6px; padding: 10px 0 28px; }
  .op-hero-val { font-size: 2.6rem; font-weight: 900; letter-spacing: -0.05em; font-variant-numeric: tabular-nums; color: #F3EFEA; line-height: 1.1; }
  .op-hero-val.gold  { color: #D4A820; }
  .op-hero-val.green { color: #2EC8A4; }
  .op-hero-val.red   { color: #F07A64; }
  .op-hero-val.dim   { color: rgba(243,239,234,0.2); }
  .op-hero-sub { font-size: 0.84rem; font-weight: 600; color: rgba(243,239,234,0.4); }
  .op-hero-sub .green { color: #2EC8A4; }
  .op-hero-sub .red   { color: #F07A64; }
  .op-hero-sep { margin: 0 8px; color: rgba(243,239,234,0.18); }

  /* Filtro de período — abas com sublinhado, sem pílula */
  .op-period-tabs { display: flex; gap: 20px; }
  .op-period-tab {
    font-family: inherit; font-size: 0.74rem; font-weight: 700;
    color: rgba(243,239,234,0.35); background: none; border: none;
    padding: 4px 2px 8px; cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: color 0.15s ease, border-color 0.15s ease;
  }
  .op-period-tab:hover { color: rgba(243,239,234,0.65); }
  .op-period-tab.active { color: #D4A820; border-bottom-color: #D4A820; }

  /* Voltar do drill-down diário */
  .op-back-btn {
    display: flex; align-items: center; gap: 8px;
    font-family: inherit; font-size: 0.78rem; font-weight: 700;
    color: #F3EFEA; background: none; border: none; padding: 0; cursor: pointer;
  }
  .op-back-btn:hover { color: #D4A820; }
  .op-chart-hint { font-size: 0.7rem; color: rgba(243,239,234,0.22); margin-top: 10px; }

  /* Navegação de semana dentro do drill-down diário */
  .op-week-nav { display: flex; align-items: center; justify-content: center; gap: 18px; margin-bottom: 20px; }
  .op-week-label { font-size: 1.05rem; font-weight: 800; color: #F3EFEA; min-width: 220px; text-align: center; font-variant-numeric: tabular-nums; }
  .op-week-arrow {
    width: 34px; height: 34px; border-radius: 9px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    background: rgba(243,239,234,0.05); border: 1px solid rgba(243,239,234,0.1);
    color: rgba(243,239,234,0.6); cursor: pointer;
    transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
  }
  .op-week-arrow:hover:not(:disabled) { background: rgba(212,168,32,0.1); border-color: rgba(212,168,32,0.3); color: #D4A820; }
  .op-week-arrow:disabled { opacity: 0.25; cursor: default; }

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

  /* Empty state */
  .op-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 30px 16px; gap: 6px; min-height: 120px; }
  .op-empty-icon { font-size: 1.5rem; opacity: 0.25; margin-bottom: 2px; }
  .op-empty-title { font-size: 0.84rem; font-weight: 700; color: rgba(243,239,234,0.5); }
  .op-empty-sub { font-size: 0.74rem; color: rgba(243,239,234,0.28); max-width: 240px; line-height: 1.5; }

  /* Chart x-axis labels */
  /* Mesma estrutura de colunas/gap das barras — garante alinhamento exato */
  .op-chart-labels { display: flex; gap: 14px; margin-top: 8px; }
  .op-sbar-axis-spacer { width: 34px; flex-shrink: 0; }
  .op-sbar-labels { display: flex; justify-content: center; align-items: flex-start; gap: 14px; flex: 1; min-width: 0; }
  .op-sbar-label-col { flex: 0 1 110px; min-width: 0; display: flex; justify-content: center; }
  .op-chart-label { font-size: 0.7rem; font-weight: 600; color: rgba(243,239,234,0.32); font-variant-numeric: tabular-nums; }

  /* Gráfico de barras flat — uma série, valor acima, eixo com grade */
  .op-sbar-wrap { display: flex; flex-direction: column; }
  .op-sbar-plot { display: flex; gap: 14px; }
  .op-sbar-axis { display: flex; flex-direction: column; justify-content: space-between; width: 34px; flex-shrink: 0; padding-bottom: 1px; }
  .op-sbar-axis span { font-size: 0.68rem; color: rgba(243,239,234,0.28); font-variant-numeric: tabular-nums; }
  .op-sbar-plotarea { position: relative; flex: 1; }
  .op-sbar-grid { position: absolute; inset: 0; display: flex; flex-direction: column; justify-content: space-between; pointer-events: none; }
  .op-sbar-grid div { border-top: 1px solid rgba(243,239,234,0.07); height: 0; }
  .op-sbar-bars { position: relative; display: flex; justify-content: center; align-items: flex-end; gap: 14px; height: 100%; }
  .op-sbar-col { flex: 0 1 110px; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; min-width: 0; }
  .op-sbar-val { font-size: 0.78rem; font-weight: 800; color: rgba(243,239,234,0.65); margin-bottom: 8px; font-variant-numeric: tabular-nums; }
  .op-sbar-val.current { color: #F0C840; font-weight: 900; }
  .op-sbar-bar {
    width: 68%; max-width: 52px; min-height: 2px;
    border: none; padding: 0; border-radius: 5px 5px 2px 2px;
    transition: height 0.8s cubic-bezier(.4,0,.2,1), filter 0.15s ease;
    cursor: default;
  }
  .op-sbar-bar.clickable { cursor: pointer; }
  .op-sbar-bar.clickable:hover { filter: brightness(1.2); }
  .op-sbar-bar.current { box-shadow: 0 0 14px rgba(240,200,64,0.4); }
  .op-chart-label.current { color: #F0C840; font-weight: 800; }

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
const DEMO_MONTHS = ['Set','Out','Nov','Dez','Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago'];
const MONTH_NAMES = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];

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

function monthKeyLabel(key: string): string {
  const idx = parseInt(key.slice(5, 7), 10) - 1;
  return MONTH_NAMES[idx] ?? key;
}

// Agrupa por mês-calendário real (YYYY-MM) — ordenado cronologicamente, não
// pela ordem de chegada da API, pra bater com o mês que o usuário clicar.
function buildMonthlySeries(txns: Transaction[], isMatch: (t: Transaction) => boolean): BarPoint[] {
  const map: Record<string, number> = {};
  for (const t of txns) {
    if (!isMatch(t)) continue;
    const m = t.date?.slice(0, 7) || '';
    if (!m) continue;
    map[m] = (map[m] || 0) + Math.abs(t.amount);
  }
  return Object.entries(map)
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([key, value]) => ({ key, label: monthKeyLabel(key), value }))
    .slice(-12);
}

const PERIODS = [
  { key: '1a', label: '1 Ano',   months: 12 },
  { key: '6m', label: '6 Meses', months: 6  },
];

const WEEKDAYS = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];

export const OrganizarPage: React.FC = () => {
  const navigate = useNavigate();
  const userId = localStorage.getItem('user_id') || '';
  const demo = isDemoMode(userId);
  const [period, setPeriod] = useState('1a');

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

  const monthSeries: BarPoint[] = hasReal
    ? buildMonthlySeries(txns, t => t.amount < 0 || t.type === 'expense')
    : showDemo ? DEMO_SPEND.map((v, i) => ({ key: `demo-${i}`, label: DEMO_MONTHS[i], value: v })) : [];
  const periodMonths = PERIODS.find(p => p.key === period)?.months ?? 12;
  const chartSeries = monthSeries.slice(-Math.min(periodMonths, monthSeries.length));
  const currentMonthKey = monthSeries.length ? monthSeries[monthSeries.length - 1].key : null;

  const [drillKey, setDrillKey] = useState<string | null>(null);
  const [weekIdx, setWeekIdx] = useState(0);
  useEffect(() => { setWeekIdx(0); }, [drillKey]);
  const drillPoint = drillKey ? monthSeries.find(m => m.key === drillKey) || null : null;

  let monthDaily: number[] = [];
  let weekdayOf: (day: number) => number = () => 0;
  if (drillPoint) {
    if (hasReal) {
      const [yStr, mStr] = drillPoint.key.split('-');
      const year = parseInt(yStr, 10);
      const month = parseInt(mStr, 10);
      const daysInMonth = new Date(year, month, 0).getDate();
      monthDaily = new Array(daysInMonth).fill(0);
      for (const t of txns) {
        if ((t.amount < 0 || t.type === 'expense') && t.date?.slice(0, 7) === drillPoint.key) {
          const day = parseInt(t.date.slice(8, 10), 10);
          if (day >= 1 && day <= daysInMonth) monthDaily[day - 1] += Math.abs(t.amount);
        }
      }
      weekdayOf = (day) => new Date(year, month - 1, day).getDay();
    } else {
      const seed = parseInt(drillPoint.key.replace('demo-', ''), 10) || 0;
      monthDaily = demoDailySeries(drillPoint.value, seed, 30);
      weekdayOf = (day) => (day - 1) % 7;
    }
  }

  const weeks: number[][] = [];
  for (let i = 0; i < monthDaily.length; i += 7) weeks.push(monthDaily.slice(i, i + 7));
  const currentWeekDays = weeks[weekIdx] || [];
  const weekSeries: BarPoint[] = currentWeekDays.map((v, i) => {
    const day = weekIdx * 7 + i + 1;
    return { key: `d-${day}`, label: WEEKDAYS[weekdayOf(day)], value: v };
  });
  const weekStart = weekIdx * 7 + 1;
  const weekEnd = weekIdx * 7 + currentWeekDays.length;

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
              {drillPoint ? (
                <button type="button" className="op-back-btn" onClick={() => setDrillKey(null)}>
                  <svg width="13" height="13" viewBox="0 0 14 14" fill="none"><path d="M9 2.5 3.5 7 9 11.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  Gastos em {drillPoint.label}
                </button>
              ) : (
                <span className="op-panel-title">Resumo do mês</span>
              )}
              {!drillPoint && (hasReal || showDemo) && (
                <div className="op-period-tabs">
                  {PERIODS.map(p => (
                    <button key={p.key} type="button" className={`op-period-tab${period === p.key ? ' active' : ''}`} onClick={() => setPeriod(p.key)}>
                      {p.label}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="op-hero-stat">
              <span className={`op-hero-val ${hasReal ? (saldo >= 0 ? 'green' : 'red') : showDemo ? 'gold' : 'dim'}`}>
                {hasReal ? fmtBRL(saldo) : showDemo ? 'R$ 3.000' : '—'}
              </span>
              <span className="op-hero-sub">
                <span className="green">Receita {hasReal ? fmtBRL(totalIn) : showDemo ? 'R$ 7.000' : '—'}</span>
                <span className="op-hero-sep">·</span>
                <span className="red">Gastos {hasReal ? fmtBRL(totalOut) : showDemo ? 'R$ 4.000' : '—'}</span>
              </span>
            </div>

            {drillPoint ? (
              <>
                <div className="op-week-nav">
                  <button type="button" className="op-week-arrow" onClick={() => setWeekIdx(i => i - 1)} disabled={weekIdx === 0}>
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M9 2.5 3.5 7 9 11.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  </button>
                  <span className="op-week-label">Semana {weekIdx + 1} · dia {weekStart} a {weekEnd}</span>
                  <button type="button" className="op-week-arrow" onClick={() => setWeekIdx(i => i + 1)} disabled={weekIdx >= weeks.length - 1}>
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M5 2.5 10.5 7 5 11.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  </button>
                </div>
                <SingleBarChart series={weekSeries} h={250} />
              </>
            ) : monthSeries.length > 0 ? (
              <>
                <SingleBarChart
                  series={chartSeries}
                  currentKey={currentMonthKey}
                  onSelect={setDrillKey}
                  h={190}
                />
                <p className="op-chart-hint">Clique num mês pra ver o gasto por semana.</p>
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
