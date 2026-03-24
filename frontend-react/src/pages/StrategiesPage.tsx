import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { AppShell } from '../components/layout/AppShell';
import { nexaApi } from '../api/nexa';

const card: React.CSSProperties = {
  background: '#fff',
  border: '1px solid #ebebeb',
  borderRadius: 12,
  padding: 16,
};

function currency(value: number) {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value || 0);
}

export const StrategiesPage: React.FC = () => {
  const userId = localStorage.getItem('user_id') || '';
  const [tab, setTab] = useState<'optimizer' | 'architect' | 'fiscal' | 'peers'>('optimizer');

  const [income, setIncome] = useState(10000);
  const [maxCards, setMaxCards] = useState(3);

  const [targetAmount, setTargetAmount] = useState(120000);
  const [downPayment, setDownPayment] = useState(20000);
  const [months, setMonths] = useState(48);

  const [year, setYear] = useState(new Date().getFullYear());
  const [month, setMonth] = useState<number | ''>('');

  const portfolioQuery = useQuery({
    queryKey: ['optimizer-portfolio', userId, income, maxCards],
    queryFn: () => nexaApi.getOptimizerPortfolio(userId, maxCards, income),
    enabled: !!userId && tab === 'optimizer',
  });

  const cardsQuery = useQuery({
    queryKey: ['optimizer-cards'],
    queryFn: () => nexaApi.getOptimizerCards(),
    enabled: tab === 'optimizer',
  });

  const promotionsQuery = useQuery({
    queryKey: ['optimizer-promotions'],
    queryFn: () => nexaApi.getOptimizerPromotions(),
    enabled: tab === 'optimizer',
  });

  const [currentCard, setCurrentCard] = useState('');
  const opportunityQuery = useQuery({
    queryKey: ['optimizer-opportunity', userId, currentCard],
    queryFn: () => nexaApi.getOptimizerOpportunityCost(userId, currentCard, 3),
    enabled: !!userId && !!currentCard && tab === 'optimizer',
  });

  const architectMutation = useMutation({
    mutationFn: () =>
      nexaApi.architectSimulate({
        user_id: userId,
        target_amount: targetAmount,
        down_payment: downPayment,
        risk_profile: 'moderado',
        asset_type: 'VEICULO',
        financing_months: months,
        include_consortium: true,
        prefers_consortium: false,
      }),
  });

  const architectHistory = useQuery({
    queryKey: ['architect-history', userId],
    queryFn: () => nexaApi.architectListSimulations(userId, 8),
    enabled: !!userId && tab === 'architect',
  });

  const architectMetrics = useQuery({
    queryKey: ['architect-metrics', userId],
    queryFn: () => nexaApi.architectMetrics(userId),
    enabled: !!userId && tab === 'architect',
  });

  const fiscalReport = useQuery({
    queryKey: ['fiscal-report', userId, year, month],
    queryFn: () => nexaApi.getFiscalReport(userId, year, month === '' ? undefined : month),
    enabled: !!userId && tab === 'fiscal',
  });

  const fiscalMixed = useQuery({
    queryKey: ['fiscal-mixed', userId, year, month],
    queryFn: () => nexaApi.getFiscalMixedUse(userId, year, month === '' ? undefined : month),
    enabled: !!userId && tab === 'fiscal',
  });

  const peerQuery = useQuery({
    queryKey: ['peers', userId, income],
    queryFn: () => nexaApi.getPeerComparison(userId, income, 3),
    enabled: !!userId && tab === 'peers',
  });

  const notificationsQuery = useQuery({
    queryKey: ['notifications', userId, income],
    queryFn: () => nexaApi.getNotifications(userId, income, true),
    enabled: !!userId && tab === 'peers',
  });

  const optimizerCards = cardsQuery.data?.cards || cardsQuery.data?.results || [];

  return (
    <AppShell
      current="strategies"
      title="Estratégias Nexa"
      subtitle="Optimizer, Architect, Fiscal Intelligence e alertas proativos."
    >
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        {[
          ['optimizer', 'Optimizer'],
          ['architect', 'Architect'],
          ['fiscal', 'Fiscal'],
          ['peers', 'Peers & Alertas'],
        ].map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key as any)}
            style={{
              border: '1px solid #ddd',
              background: tab === key ? '#111' : '#fff',
              color: tab === key ? '#fff' : '#111',
              borderRadius: 8,
              padding: '8px 12px',
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'optimizer' && (
        <div style={{ display: 'grid', gap: 12 }}>
          <div style={card}>
            <div style={{ marginBottom: 8, fontWeight: 600 }}>Portfólio ideal de cartões</div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
              <input
                type="number"
                value={income}
                onChange={(e) => setIncome(Number(e.target.value || 0))}
                style={{ border: '1px solid #ddd', borderRadius: 8, padding: 8, width: 180 }}
              />
              <select value={maxCards} onChange={(e) => setMaxCards(Number(e.target.value))} style={{ border: '1px solid #ddd', borderRadius: 8, padding: 8 }}>
                <option value={1}>1 cartão</option>
                <option value={2}>2 cartões</option>
                <option value={3}>3 cartões</option>
                <option value={4}>4 cartões</option>
              </select>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, marginBottom: 10 }}>
              <div style={{ border: '1px solid #eee', borderRadius: 8, padding: 10 }}>
                <div style={{ fontSize: 12, color: '#777' }}>Retorno anual</div>
                <div style={{ fontWeight: 700, fontSize: 18 }}>{currency(Number(portfolioQuery.data?.total_annual_return || 0))}</div>
              </div>
              <div style={{ border: '1px solid #eee', borderRadius: 8, padding: 10 }}>
                <div style={{ fontSize: 12, color: '#777' }}>Custo anuidade</div>
                <div style={{ fontWeight: 700, fontSize: 18 }}>{currency(Number(portfolioQuery.data?.total_annuity_cost || 0))}</div>
              </div>
              <div style={{ border: '1px solid #eee', borderRadius: 8, padding: 10 }}>
                <div style={{ fontSize: 12, color: '#777' }}>Ganho líquido</div>
                <div style={{ fontWeight: 700, fontSize: 18 }}>{currency(Number(portfolioQuery.data?.net_annual_gain || 0))}</div>
              </div>
            </div>
            <pre style={{ background: '#fafafa', border: '1px solid #eee', borderRadius: 8, padding: 10, maxHeight: 240, overflow: 'auto', fontSize: 12 }}>
              {JSON.stringify(portfolioQuery.data?.cards || [], null, 2)}
            </pre>
          </div>

          <div style={card}>
            <div style={{ marginBottom: 8, fontWeight: 600 }}>Custo de oportunidade</div>
            <select
              value={currentCard}
              onChange={(e) => setCurrentCard(e.target.value)}
              style={{ width: '100%', border: '1px solid #ddd', borderRadius: 8, padding: 8, marginBottom: 10 }}
            >
              <option value="">Selecione seu cartão atual</option>
              {optimizerCards.map((c: any) => (
                <option key={c.card_id || c.id} value={c.card_id || c.id}>
                  {c.name || c.card_id || c.id}
                </option>
              ))}
            </select>
            <pre style={{ background: '#fafafa', border: '1px solid #eee', borderRadius: 8, padding: 10, maxHeight: 180, overflow: 'auto', fontSize: 12 }}>
              {JSON.stringify(opportunityQuery.data || {}, null, 2)}
            </pre>
          </div>

          <div style={card}>
            <div style={{ marginBottom: 8, fontWeight: 600 }}>Promoções ativas</div>
            <pre style={{ background: '#fafafa', border: '1px solid #eee', borderRadius: 8, padding: 10, maxHeight: 180, overflow: 'auto', fontSize: 12 }}>
              {JSON.stringify(promotionsQuery.data?.promotions || [], null, 2)}
            </pre>
          </div>
        </div>
      )}

      {tab === 'architect' && (
        <div style={{ display: 'grid', gap: 12 }}>
          <div style={card}>
            <div style={{ marginBottom: 8, fontWeight: 600 }}>Simulação estratégica</div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
              <input type="number" value={targetAmount} onChange={(e) => setTargetAmount(Number(e.target.value || 0))} style={{ border: '1px solid #ddd', borderRadius: 8, padding: 8 }} />
              <input type="number" value={downPayment} onChange={(e) => setDownPayment(Number(e.target.value || 0))} style={{ border: '1px solid #ddd', borderRadius: 8, padding: 8 }} />
              <input type="number" value={months} onChange={(e) => setMonths(Number(e.target.value || 0))} style={{ border: '1px solid #ddd', borderRadius: 8, padding: 8 }} />
              <button
                onClick={() => architectMutation.mutate()}
                style={{ border: '1px solid #111', background: '#111', color: '#fff', borderRadius: 8, padding: '8px 12px', cursor: 'pointer' }}
              >
                Simular
              </button>
            </div>
            <pre style={{ background: '#fafafa', border: '1px solid #eee', borderRadius: 8, padding: 10, maxHeight: 260, overflow: 'auto', fontSize: 12 }}>
              {JSON.stringify(architectMutation.data || {}, null, 2)}
            </pre>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div style={card}>
              <div style={{ marginBottom: 8, fontWeight: 600 }}>Histórico</div>
              <pre style={{ background: '#fafafa', border: '1px solid #eee', borderRadius: 8, padding: 10, maxHeight: 220, overflow: 'auto', fontSize: 12 }}>
                {JSON.stringify(architectHistory.data || [], null, 2)}
              </pre>
            </div>
            <div style={card}>
              <div style={{ marginBottom: 8, fontWeight: 600 }}>Métricas</div>
              <pre style={{ background: '#fafafa', border: '1px solid #eee', borderRadius: 8, padding: 10, maxHeight: 220, overflow: 'auto', fontSize: 12 }}>
                {JSON.stringify(architectMetrics.data || {}, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}

      {tab === 'fiscal' && (
        <div style={{ display: 'grid', gap: 12 }}>
          <div style={card}>
            <div style={{ marginBottom: 8, fontWeight: 600 }}>Parâmetros fiscais</div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
              <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value || new Date().getFullYear()))} style={{ border: '1px solid #ddd', borderRadius: 8, padding: 8 }} />
              <select value={month} onChange={(e) => setMonth(e.target.value === '' ? '' : Number(e.target.value))} style={{ border: '1px solid #ddd', borderRadius: 8, padding: 8 }}>
                <option value="">Todos</option>
                {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div style={card}>
              <div style={{ marginBottom: 8, fontWeight: 600 }}>Relatório Fiscal</div>
              <pre style={{ background: '#fafafa', border: '1px solid #eee', borderRadius: 8, padding: 10, maxHeight: 280, overflow: 'auto', fontSize: 12 }}>
                {JSON.stringify(fiscalReport.data || {}, null, 2)}
              </pre>
            </div>
            <div style={card}>
              <div style={{ marginBottom: 8, fontWeight: 600 }}>Uso Misto PF/PJ</div>
              <pre style={{ background: '#fafafa', border: '1px solid #eee', borderRadius: 8, padding: 10, maxHeight: 280, overflow: 'auto', fontSize: 12 }}>
                {JSON.stringify(fiscalMixed.data || {}, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}

      {tab === 'peers' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div style={card}>
            <div style={{ marginBottom: 8, fontWeight: 600 }}>Benchmark com pares</div>
            <input
              type="number"
              value={income}
              onChange={(e) => setIncome(Number(e.target.value || 0))}
              style={{ border: '1px solid #ddd', borderRadius: 8, padding: 8, width: 180, marginBottom: 10 }}
            />
            <pre style={{ background: '#fafafa', border: '1px solid #eee', borderRadius: 8, padding: 10, maxHeight: 320, overflow: 'auto', fontSize: 12 }}>
              {JSON.stringify(peerQuery.data || {}, null, 2)}
            </pre>
          </div>
          <div style={card}>
            <div style={{ marginBottom: 8, fontWeight: 600 }}>Notificações</div>
            <pre style={{ background: '#fafafa', border: '1px solid #eee', borderRadius: 8, padding: 10, maxHeight: 360, overflow: 'auto', fontSize: 12 }}>
              {JSON.stringify(notificationsQuery.data || {}, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </AppShell>
  );
};
