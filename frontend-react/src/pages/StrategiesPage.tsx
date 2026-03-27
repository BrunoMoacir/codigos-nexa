import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { AppShell } from '../components/layout/AppShell';
import { nexaApi } from '../api/nexa';

const card: React.CSSProperties = {
  background: 'var(--bg-surface)',
  border: '1px solid #ebebeb',
  borderRadius: 12,
  padding: 16,
};

const sectionTitle: React.CSSProperties = {
  marginBottom: 10,
  fontWeight: 600,
  fontSize: 15,
  color: 'var(--text-primary)',
};

const metricLabel: React.CSSProperties = {
  fontSize: 12,
  color: '#6b7280',
  marginBottom: 4,
};

const metricValue: React.CSSProperties = {
  fontSize: 20,
  color: 'var(--text-primary)',
  fontWeight: 700,
};

function currency(value: number) {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value || 0);
}

function toNumber(value: unknown) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
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
  const portfolioCards = portfolioQuery.data?.cards || [];
  const promotions = promotionsQuery.data?.promotions || [];
  const architectResult = architectMutation.data || {};
  const architectActionPlan = architectResult?.action_plan || [];
  const architectNpv = architectResult?.npv || {};
  const fiscalData = fiscalReport.data || {};
  const mixedUseData = fiscalMixed.data || {};
  const peerData = peerQuery.data || {};
  const notifications = notificationsQuery.data?.notifications || notificationsQuery.data?.results || [];

  const isOptimizerLoading = portfolioQuery.isLoading || cardsQuery.isLoading || promotionsQuery.isLoading;
  const isArchitectLoading = architectHistory.isLoading || architectMetrics.isLoading;
  const isFiscalLoading = fiscalReport.isLoading || fiscalMixed.isLoading;
  const isPeersLoading = peerQuery.isLoading || notificationsQuery.isLoading;

  const topPeerInsights = useMemo(() => {
    const rawInsights = peerData?.insights || peerData?.highlights || [];
    if (Array.isArray(rawInsights) && rawInsights.length > 0) {
      return rawInsights.slice(0, 4).map((v: any) => String(v));
    }

    const expensePosition = peerData?.expense_percentile;
    const savingPosition = peerData?.savings_percentile;
    const generated: string[] = [];
    if (expensePosition != null) {
      generated.push(`Percentil de despesas: ${toNumber(expensePosition).toFixed(0)}.`);
    }
    if (savingPosition != null) {
      generated.push(`Percentil de poupança: ${toNumber(savingPosition).toFixed(0)}.`);
    }
    return generated;
  }, [peerData]);

  return (
    <AppShell
      current="strategies"
      title="Estratégias Nexa"
      subtitle="Optimizer, Architect, Fiscal Intelligence e alertas proativos."
    >
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
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
              background: tab === key ? 'var(--text-primary)' : 'var(--bg-surface)',
              color: tab === key ? 'var(--bg-surface)' : 'var(--text-primary)',
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
          {isOptimizerLoading && (
            <div style={{ ...card, color: 'var(--text-muted)', fontSize: 14 }}>Carregando dados do Optimizer...</div>
          )}
          <div style={card}>
            <div style={sectionTitle}>Portfólio ideal de cartões</div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
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
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10, marginBottom: 10 }}>
              <div style={{ border: '1px solid #eee', borderRadius: 8, padding: 10 }}>
                <div style={metricLabel}>Retorno anual</div>
                <div style={metricValue}>{currency(toNumber(portfolioQuery.data?.total_annual_return))}</div>
              </div>
              <div style={{ border: '1px solid #eee', borderRadius: 8, padding: 10 }}>
                <div style={metricLabel}>Custo anuidade</div>
                <div style={metricValue}>{currency(toNumber(portfolioQuery.data?.total_annuity_cost))}</div>
              </div>
              <div style={{ border: '1px solid #eee', borderRadius: 8, padding: 10 }}>
                <div style={metricLabel}>Ganho líquido</div>
                <div style={metricValue}>{currency(toNumber(portfolioQuery.data?.net_annual_gain))}</div>
              </div>
            </div>

            {portfolioCards.length === 0 && (
              <div style={{ color: 'var(--text-muted)', fontSize: 14 }}>Nenhuma recomendação de portfólio para os parâmetros atuais.</div>
            )}
            {portfolioCards.length > 0 && (
              <div style={{ display: 'grid', gap: 8 }}>
                {portfolioCards.slice(0, 4).map((item: any, idx: number) => (
                  <div
                    key={`${item.card_id || item.id || idx}`}
                    style={{ border: '1px solid #eee', borderRadius: 10, padding: 10, display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto auto', gap: 10 }}
                  >
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 14 }}>{item.name || item.card_name || item.card_id || 'Cartão recomendado'}</div>
                      <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                        Cashback: {toNumber(item.cashback_pct || item.cashback || 0).toFixed(2)}%
                      </div>
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                      {currency(toNumber(item.annual_return || item.estimated_return || 0))}
                    </div>
                    <div style={{ fontSize: 12, color: '#6b7280' }}>ano</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
            <div style={card}>
              <div style={sectionTitle}>Custo de oportunidade</div>
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

              {!currentCard && <div style={{ color: 'var(--text-muted)', fontSize: 14 }}>Selecione um cartão para analisar troca e perda de retorno.</div>}

              {currentCard && (
                <div style={{ display: 'grid', gap: 8 }}>
                  <div style={{ border: '1px solid #eee', borderRadius: 10, padding: 10 }}>
                    <div style={metricLabel}>Perda estimada</div>
                    <div style={metricValue}>{currency(toNumber(opportunityQuery.data?.lost_value || opportunityQuery.data?.opportunity_cost || 0))}</div>
                  </div>
                  <div style={{ border: '1px solid #eee', borderRadius: 10, padding: 10 }}>
                    <div style={metricLabel}>Melhor alternativa</div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
                      {opportunityQuery.data?.best_alternative || opportunityQuery.data?.recommended_card || 'Sem recomendação específica'}
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div style={card}>
              <div style={sectionTitle}>Promoções ativas</div>
              {promotions.length === 0 && <div style={{ color: 'var(--text-muted)', fontSize: 14 }}>Nenhuma promoção ativa no momento.</div>}
              {promotions.slice(0, 5).map((promo: any, idx: number) => (
                <div key={`${promo.id || promo.title || idx}`} style={{ borderBottom: '1px solid #f2f2f2', padding: '8px 0' }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{promo.title || promo.name || 'Promoção'}</div>
                  <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                    {promo.description || promo.details || 'Condição promocional disponível.'}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {tab === 'architect' && (
        <div style={{ display: 'grid', gap: 12 }}>
          {isArchitectLoading && (
            <div style={{ ...card, color: 'var(--text-muted)', fontSize: 14 }}>Carregando histórico e métricas do Architect...</div>
          )}
          <div style={card}>
            <div style={sectionTitle}>Simulação estratégica</div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
              <input type="number" value={targetAmount} onChange={(e) => setTargetAmount(Number(e.target.value || 0))} style={{ border: '1px solid #ddd', borderRadius: 8, padding: 8 }} />
              <input type="number" value={downPayment} onChange={(e) => setDownPayment(Number(e.target.value || 0))} style={{ border: '1px solid #ddd', borderRadius: 8, padding: 8 }} />
              <input type="number" value={months} onChange={(e) => setMonths(Number(e.target.value || 0))} style={{ border: '1px solid #ddd', borderRadius: 8, padding: 8 }} />
              <button
                onClick={() => architectMutation.mutate()}
                style={{ border: '1px solid #111', background: 'var(--text-primary)', color: 'var(--bg-surface)', borderRadius: 8, padding: '8px 12px', cursor: 'pointer' }}
              >
                Simular
              </button>
            </div>

            {architectMutation.isPending && <div style={{ color: 'var(--text-muted)', fontSize: 14 }}>Processando simulação...</div>}

            {!architectMutation.isPending && Object.keys(architectResult).length === 0 && (
              <div style={{ color: 'var(--text-muted)', fontSize: 14 }}>Execute uma simulação para comparar estratégias e custos.</div>
            )}

            {!architectMutation.isPending && Object.keys(architectResult).length > 0 && (
              <div style={{ display: 'grid', gap: 10 }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}>
                  <div style={{ border: '1px solid #eee', borderRadius: 10, padding: 10 }}>
                    <div style={metricLabel}>Estratégia recomendada</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
                      {architectResult.recommended_strategy || 'N/A'}
                    </div>
                  </div>
                  <div style={{ border: '1px solid #eee', borderRadius: 10, padding: 10 }}>
                    <div style={metricLabel}>Confiança</div>
                    <div style={metricValue}>{(toNumber(architectResult.confidence_score) * 100).toFixed(0)}%</div>
                  </div>
                  <div style={{ border: '1px solid #eee', borderRadius: 10, padding: 10 }}>
                    <div style={metricLabel}>Prazo alvo</div>
                    <div style={metricValue}>{toNumber(architectResult.months_to_achieve)} meses</div>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10 }}>
                  <div style={{ border: '1px solid #eee', borderRadius: 10, padding: 10 }}>
                    <div style={metricLabel}>Custo esperado</div>
                    <div style={metricValue}>{currency(toNumber(architectResult?.costs?.expected_cost))}</div>
                  </div>
                  <div style={{ border: '1px solid #eee', borderRadius: 10, padding: 10 }}>
                    <div style={metricLabel}>Liquidez impactada</div>
                    <div style={metricValue}>{(toNumber(architectResult.liquidity_impact) * 100).toFixed(0)}%</div>
                  </div>
                </div>

                <div style={{ border: '1px solid #eee', borderRadius: 10, padding: 10 }}>
                  <div style={{ ...metricLabel, marginBottom: 8 }}>Comparativo NPV</div>
                  <div style={{ display: 'grid', gap: 7 }}>
                    {Object.entries(architectNpv)
                      .filter(([k]) => k !== 'discount_rate_used')
                      .slice(0, 5)
                      .map(([key, value]) => (
                        <div key={key} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                          <span style={{ color: 'var(--text-secondary)', textTransform: 'capitalize' }}>{key.replaceAll('_', ' ')}</span>
                          <strong style={{ color: 'var(--text-primary)' }}>{currency(toNumber(value))}</strong>
                        </div>
                      ))}
                  </div>
                </div>

                <div style={{ border: '1px solid #eee', borderRadius: 10, padding: 10 }}>
                  <div style={{ ...metricLabel, marginBottom: 8 }}>Plano de ação</div>
                  {architectActionPlan.length === 0 && (
                    <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>Sem plano detalhado disponível.</div>
                  )}
                  {architectActionPlan.slice(0, 5).map((step: any, idx: number) => (
                    <div key={`${step.step || idx}`} style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 6 }}>
                      {idx + 1}. {step.action || 'Executar próxima etapa.'}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
            <div style={card}>
              <div style={sectionTitle}>Histórico</div>
              {(!Array.isArray(architectHistory.data) || architectHistory.data.length === 0) && (
                <div style={{ color: 'var(--text-muted)', fontSize: 14 }}>Nenhuma simulação prévia encontrada.</div>
              )}
              {Array.isArray(architectHistory.data) && architectHistory.data.slice(0, 5).map((sim: any, idx: number) => (
                <div key={`${sim.simulation_id || idx}`} style={{ borderBottom: '1px solid #f2f2f2', padding: '8px 0' }}>
                  <div style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 600 }}>{sim.recommended_strategy || 'Estratégia simulada'}</div>
                  <div style={{ fontSize: 12, color: '#6b7280' }}>
                    {sim.created_at ? String(sim.created_at).slice(0, 10) : 'Data indisponível'}
                  </div>
                </div>
              ))}
            </div>
            <div style={card}>
              <div style={sectionTitle}>Métricas</div>
              <div style={{ display: 'grid', gap: 8 }}>
                <div style={{ border: '1px solid #eee', borderRadius: 10, padding: 10 }}>
                  <div style={metricLabel}>Simulações totais</div>
                  <div style={metricValue}>{toNumber(architectMetrics.data?.total_simulations)}</div>
                </div>
                <div style={{ border: '1px solid #eee', borderRadius: 10, padding: 10 }}>
                  <div style={metricLabel}>Estratégia mais usada</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
                    {architectMetrics.data?.most_common_strategy || architectMetrics.data?.top_strategy || 'N/A'}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === 'fiscal' && (
        <div style={{ display: 'grid', gap: 12 }}>
          {isFiscalLoading && (
            <div style={{ ...card, color: 'var(--text-muted)', fontSize: 14 }}>Carregando relatório fiscal...</div>
          )}
          <div style={card}>
            <div style={sectionTitle}>Parâmetros fiscais</div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
              <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value || new Date().getFullYear()))} style={{ border: '1px solid #ddd', borderRadius: 8, padding: 8 }} />
              <select value={month} onChange={(e) => setMonth(e.target.value === '' ? '' : Number(e.target.value))} style={{ border: '1px solid #ddd', borderRadius: 8, padding: 8 }}>
                <option value="">Todos</option>
                {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
            <div style={card}>
              <div style={sectionTitle}>Relatório Fiscal</div>
              <div style={{ display: 'grid', gap: 8 }}>
                <div style={{ border: '1px solid #eee', borderRadius: 10, padding: 10 }}>
                  <div style={metricLabel}>Total dedutível</div>
                  <div style={metricValue}>{currency(toNumber(fiscalData.total_deductible || fiscalData.deductible_total))}</div>
                </div>
                <div style={{ border: '1px solid #eee', borderRadius: 10, padding: 10 }}>
                  <div style={metricLabel}>Economia estimada</div>
                  <div style={metricValue}>{currency(toNumber(fiscalData.estimated_savings || fiscalData.tax_savings))}</div>
                </div>
                <div style={{ fontSize: 13, color: '#6b7280' }}>
                  {fiscalData.summary_text || 'Dados fiscais consolidados para o período selecionado.'}
                </div>
              </div>
            </div>
            <div style={card}>
              <div style={sectionTitle}>Uso Misto PF/PJ</div>
              <div style={{ display: 'grid', gap: 8 }}>
                <div style={{ border: '1px solid #eee', borderRadius: 10, padding: 10 }}>
                  <div style={metricLabel}>Transações com uso misto</div>
                  <div style={metricValue}>{toNumber(mixedUseData.total_mixed_transactions || mixedUseData.count)}</div>
                </div>
                <div style={{ border: '1px solid #eee', borderRadius: 10, padding: 10 }}>
                  <div style={metricLabel}>Percentual misto</div>
                  <div style={metricValue}>{toNumber(mixedUseData.mixed_pct || mixedUseData.percentage).toFixed(1)}%</div>
                </div>
                <div style={{ fontSize: 13, color: '#6b7280' }}>
                  {mixedUseData.summary_text || 'Monitoramento de transações com potencial sobreposição entre PF e PJ.'}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === 'peers' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
          {isPeersLoading && (
            <div style={{ ...card, color: 'var(--text-muted)', fontSize: 14 }}>Carregando benchmark e notificações...</div>
          )}
          <div style={card}>
            <div style={sectionTitle}>Benchmark com pares</div>
            <input
              type="number"
              value={income}
              onChange={(e) => setIncome(Number(e.target.value || 0))}
              style={{ border: '1px solid #ddd', borderRadius: 8, padding: 8, width: 180, marginBottom: 10 }}
            />
            <div style={{ display: 'grid', gap: 8 }}>
              <div style={{ border: '1px solid #eee', borderRadius: 10, padding: 10 }}>
                <div style={metricLabel}>Score de comparação</div>
                <div style={metricValue}>{toNumber(peerData.peer_score || peerData.comparison_score)}</div>
              </div>
              <div style={{ border: '1px solid #eee', borderRadius: 10, padding: 10 }}>
                <div style={metricLabel}>Posição de gastos</div>
                <div style={metricValue}>{toNumber(peerData.expense_percentile).toFixed(0)}%</div>
              </div>
              <div style={{ border: '1px solid #eee', borderRadius: 10, padding: 10 }}>
                <div style={{ ...metricLabel, marginBottom: 8 }}>Insights</div>
                {topPeerInsights.length === 0 && <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>Sem insights disponíveis para a faixa atual.</div>}
                {topPeerInsights.map((insight, idx) => (
                  <div key={`${idx}-${insight}`} style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 5 }}>
                    • {insight}
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div style={card}>
            <div style={sectionTitle}>Notificações</div>
            {notifications.length === 0 && <div style={{ color: 'var(--text-muted)', fontSize: 14 }}>Sem notificações recentes.</div>}
            {notifications.slice(0, 8).map((note: any, idx: number) => (
              <div key={`${note.id || idx}`} style={{ borderBottom: '1px solid #f2f2f2', padding: '8px 0' }}>
                <div style={{ fontSize: 14, color: 'var(--text-primary)', fontWeight: 600 }}>
                  {note.title || note.type || 'Notificação'}
                </div>
                <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                  {note.message || note.description || 'Atualização financeira disponível.'}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </AppShell>
  );
};
