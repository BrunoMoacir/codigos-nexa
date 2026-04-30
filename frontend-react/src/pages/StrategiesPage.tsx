import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { AppShell } from '../components/layout/AppShell';
import { nexaApi } from '../api/nexa';

const card: React.CSSProperties = {
  background: 'var(--bg-surface)',
  border: '1px solid var(--border-color)',
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
  color: 'var(--text-muted)',
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

function getErrorMessage(error: unknown, fallback: string) {
  const detail = (error as any)?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }
  return fallback;
}

export const StrategiesPage: React.FC = () => {
  const userId = localStorage.getItem('user_id') || '';
  const [tab, setTab] = useState<'optimizer' | 'cards' | 'architect' | 'fiscal' | 'peers' | 'advanced'>('optimizer');

  const [income, setIncome] = useState(0);
  const [maxCards, setMaxCards] = useState(3);

  const [targetAmount, setTargetAmount] = useState(120000);
  const [downPayment, setDownPayment] = useState(20000);
  const [months, setMonths] = useState(48);

  const [year, setYear] = useState(new Date().getFullYear());
  const [month, setMonth] = useState<number | ''>('');
  const [purchaseAmount, setPurchaseAmount] = useState(3000);
  const [purchaseCategory, setPurchaseCategory] = useState('Eletronicos');
  const [purchaseInstallments, setPurchaseInstallments] = useState(6);
  const [autoInstallments, setAutoInstallments] = useState(true);
  const [negotiationBank, setNegotiationBank] = useState('');

  const forecastContextQuery = useQuery({
    queryKey: ['forecast-context', userId],
    queryFn: () => nexaApi.getForecast(userId),
    enabled: !!userId && (tab === 'advanced' || tab === 'peers'),
  });

  const contextIncome = useMemo(() => {
    const fromInput = toNumber(income);
    if (fromInput > 0) return fromInput;
    const fromForecast = toNumber(forecastContextQuery.data?.financial_health?.total_income);
    return fromForecast > 0 ? fromForecast : 0;
  }, [income, forecastContextQuery.data]);

  const contextSafeToSpend = useMemo(
    () => toNumber(forecastContextQuery.data?.safe_to_spend?.safe_to_spend_total),
    [forecastContextQuery.data]
  );

  const contextHealthScore = useMemo(
    () => toNumber(forecastContextQuery.data?.financial_health?.health_score),
    [forecastContextQuery.data]
  );

  const contextRiskProfile = useMemo(() => {
    const profileType = String(forecastContextQuery.data?.financial_health?.profile_type || '').toUpperCase();
    if (profileType.includes('CONSERV')) return 'conservador';
    if (profileType.includes('GAST')) return 'agressivo';
    if (contextHealthScore > 0) {
      if (contextHealthScore >= 75) return 'agressivo';
      if (contextHealthScore <= 45) return 'conservador';
    }
    return 'moderado';
  }, [forecastContextQuery.data, contextHealthScore]);

  const suggestedInstallments = useMemo(() => {
    const amount = toNumber(purchaseAmount);
    if (amount <= 0) return 1;
    const incomeRef = contextIncome;
    if (incomeRef > 0) {
      const pressure = amount / incomeRef;
      if (pressure <= 0.2) return 1;
      if (pressure <= 0.4) return 3;
      if (pressure <= 0.8) return 6;
      if (pressure <= 1.5) return 12;
      return 18;
    }
    if (amount <= 500) return 1;
    if (amount <= 2000) return 3;
    if (amount <= 5000) return 6;
    if (amount <= 15000) return 12;
    return 18;
  }, [purchaseAmount, contextIncome]);

  useEffect(() => {
    if (autoInstallments) {
      setPurchaseInstallments(suggestedInstallments);
    }
  }, [autoInstallments, suggestedInstallments]);

  const portfolioQuery = useQuery({
    queryKey: ['optimizer-portfolio', userId, income, maxCards],
    queryFn: () => nexaApi.getOptimizerPortfolio(userId, maxCards, income > 0 ? income : undefined),
    enabled: !!userId && tab === 'optimizer',
  });

  const cardsQuery = useQuery({
    queryKey: ['optimizer-cards'],
    queryFn: () => nexaApi.getOptimizerCards(),
    enabled: tab === 'optimizer',
  });

  const accountCardsQuery = useQuery({
    queryKey: ['cards-transactions', userId],
    queryFn: () => nexaApi.getTransactions(userId, 500),
    enabled: !!userId && tab === 'cards',
  });

  const promotionsQuery = useQuery({
    queryKey: ['optimizer-promotions'],
    queryFn: () => nexaApi.getOptimizerPromotions(),
    enabled: tab === 'optimizer',
  });

  const optimizerReportsQuery = useQuery({
    queryKey: ['optimizer-reports', userId],
    queryFn: () => nexaApi.getOptimizerReports(userId),
    enabled: !!userId && tab === 'optimizer',
  });

  const [currentCard, setCurrentCard] = useState('');
  const opportunityQuery = useQuery({
    queryKey: ['optimizer-opportunity', userId, currentCard],
    queryFn: () => nexaApi.getOptimizerOpportunityCost(userId, currentCard, 3),
    enabled: !!userId && !!currentCard && tab === 'optimizer',
  });

  const roiQuery = useQuery({
    queryKey: ['optimizer-roi', userId, currentCard],
    queryFn: () => nexaApi.getOptimizerRoi(userId, currentCard),
    enabled: !!userId && !!currentCard && tab === 'optimizer',
  });

  const promotionOpportunitiesQuery = useQuery({
    queryKey: [
      'optimizer-promo-opportunities',
      userId,
      currentCard,
      tab,
      portfolioQuery.data?.cards?.length || 0,
      cardsQuery.data?.cards?.length || cardsQuery.data?.results?.length || 0,
    ],
    queryFn: () => {
      const cardsFromPortfolio = (portfolioQuery.data?.cards || [])
        .map((c: any) => String(c.card_name || c.name || c.card_id || '').trim())
        .filter(Boolean)
        .slice(0, 4);

      const apiCards = cardsQuery.data?.cards || cardsQuery.data?.results || [];
      const selectedCard = apiCards.find((c: any) => (c.card_id || c.id) === currentCard);
      const selectedName = String(selectedCard?.name || selectedCard?.card_name || currentCard || '').trim();

      const candidateCards = Array.from(new Set([...cardsFromPortfolio, selectedName].filter(Boolean))).slice(0, 5);
      if (candidateCards.length === 0) {
        return Promise.resolve({ opportunities: [], alerted_count: 0 });
      }

      return nexaApi.getOptimizerPromotionOpportunities(userId, candidateCards);
    },
    enabled: !!userId && tab === 'optimizer',
  });

  const optimizerAnalysisMutation = useMutation({
    mutationFn: () =>
      nexaApi.analyzeOptimizer({
        user_id: userId,
        current_cards: currentCard ? [currentCard] : [],
        safe_to_spend: contextSafeToSpend > 0 ? contextSafeToSpend : undefined,
        monthly_income: contextIncome > 0 ? contextIncome : undefined,
      }),
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
    queryKey: ['peers', userId, contextIncome],
    queryFn: () => nexaApi.getPeerComparison(userId, contextIncome > 0 ? contextIncome : undefined, 3),
    enabled: !!userId && tab === 'peers',
  });

  const notificationsQuery = useQuery({
    queryKey: ['notifications', userId, contextIncome],
    queryFn: () => nexaApi.getNotifications(userId, contextIncome > 0 ? contextIncome : undefined, true),
    enabled: !!userId && tab === 'peers',
  });

  const costsQuery = useQuery({
    queryKey: ['costs-raio-x', userId],
    queryFn: () => nexaApi.getBankCosts(userId),
    enabled: !!userId && tab === 'advanced',
  });

  const purchaseMutation = useMutation({
    mutationFn: () =>
      nexaApi.analyzePurchase({
        user_id: userId,
        amount: purchaseAmount,
        category: purchaseCategory,
        installments: purchaseInstallments,
        monthly_income: contextIncome > 0 ? contextIncome : undefined,
        risk_profile: contextRiskProfile,
        apply_opportunity_cost: true,
      }),
  });

  const negotiatorMutation = useMutation({
    mutationFn: () =>
      nexaApi.generateNegotiationScript({
        user_id: userId,
        bank_name: negotiationBank.trim() || undefined,
      }),
  });

  const optimizerCards = cardsQuery.data?.cards || cardsQuery.data?.results || [];
  const portfolioCards = portfolioQuery.data?.cards || [];
  const promotions = promotionsQuery.data?.promotions || [];
  const optimizerReports = optimizerReportsQuery.data?.reports || [];
  const transactionCards = accountCardsQuery.data?.transactions || [];
  const architectResult = architectMutation.data || {};
  const architectActionPlan = architectResult?.action_plan || [];
  const architectNpv = architectResult?.npv || {};
  const fiscalData = fiscalReport.data || {};
  const mixedUseData = fiscalMixed.data || {};
  const peerData = peerQuery.data || {};
  const notifications = notificationsQuery.data?.notifications || notificationsQuery.data?.results || [];
  const costsData = costsQuery.data || {};
  const purchaseData = purchaseMutation.data || {};
  const negotiationData = negotiatorMutation.data || {};
  const optimizerAnalysis = optimizerAnalysisMutation.data || {};
  const optimizerBestCard = optimizerAnalysis.best_card || {};
  const optimizerInsights = Array.isArray(optimizerAnalysis.insights) ? optimizerAnalysis.insights : [];
  const optimizerLifeEvents = Array.isArray(optimizerAnalysis.life_events) ? optimizerAnalysis.life_events : [];
  const optimizerWarnings = Array.isArray(optimizerAnalysis.warnings) ? optimizerAnalysis.warnings : [];
  const optimizerProfileSummary = optimizerAnalysis.user_profile_summary || {};

  const isOptimizerLoading =
    portfolioQuery.isLoading ||
    cardsQuery.isLoading ||
    promotionsQuery.isLoading ||
    optimizerReportsQuery.isLoading;
  const isCardsLoading = accountCardsQuery.isLoading;
  const isArchitectLoading = architectHistory.isLoading || architectMetrics.isLoading;
  const isFiscalLoading = fiscalReport.isLoading || fiscalMixed.isLoading;
  const isPeersLoading = peerQuery.isLoading || notificationsQuery.isLoading;
  const isAdvancedLoading = costsQuery.isLoading;

  const accountCardSummaries = useMemo(() => {
    const groups = new Map<string, {
      account_id: string;
      label: string;
      transaction_count: number;
      total_spent: number;
      total_income: number;
      net_total: number;
      last_activity: string;
      categories: Record<string, number>;
      sample_descriptions: string[];
    }>();

    transactionCards.forEach((tx: any, index: number) => {
      const accountId = String(tx.account_id || 'sem_account_id').trim() || 'sem_account_id';
      if (!groups.has(accountId)) {
        groups.set(accountId, {
          account_id: accountId,
          label: accountId === 'sem_account_id' ? `Conta ${index + 1}` : `Conta ${groups.size + 1}`,
          transaction_count: 0,
          total_spent: 0,
          total_income: 0,
          net_total: 0,
          last_activity: '',
          categories: {},
          sample_descriptions: [],
        });
      }

      const entry = groups.get(accountId)!;
      const amount = toNumber(tx.amount);
      const category = String(tx.category || 'Sem categoria');
      const date = String(tx.date || '');
      const description = String(tx.description || '').trim();

      entry.transaction_count += 1;
      entry.net_total += amount;
      entry.categories[category] = (entry.categories[category] || 0) + Math.abs(amount);
      if (amount >= 0) {
        entry.total_income += amount;
      } else {
        entry.total_spent += Math.abs(amount);
      }
      if (date && (!entry.last_activity || date > entry.last_activity)) {
        entry.last_activity = date;
      }
      if (description && entry.sample_descriptions.length < 3) {
        entry.sample_descriptions.push(description);
      }
    });

    return Array.from(groups.values()).sort((a, b) => {
      if (b.transaction_count !== a.transaction_count) return b.transaction_count - a.transaction_count;
      return b.total_spent - a.total_spent;
    });
  }, [transactionCards]);

  const topPeerInsights = useMemo(() => {
    const highlightsAbove = Array.isArray(peerData?.highlights_above) ? peerData.highlights_above : [];
    const highlightsBelow = Array.isArray(peerData?.highlights_below) ? peerData.highlights_below : [];
    const rawHighlights = [...highlightsAbove, ...highlightsBelow].filter(Boolean);
    if (rawHighlights.length > 0) {
      return rawHighlights.slice(0, 4).map((v: any) => String(v));
    }

    if (peerData?.summary_text) {
      return [String(peerData.summary_text)];
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
          ['cards', 'Cartões'],
          ['architect', 'Architect'],
          ['fiscal', 'Fiscal'],
          ['peers', 'Peers & Alertas'],
          ['advanced', 'F5/F7/F13'],
        ].map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key as any)}
            style={{
              border: '1px solid var(--border-color)',
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
                style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 8, width: 180 }}
              />
              <select value={maxCards} onChange={(e) => setMaxCards(Number(e.target.value))} style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 8 }}>
                <option value={1}>1 cartão</option>
                <option value={2}>2 cartões</option>
                <option value={3}>3 cartões</option>
                <option value={4}>4 cartões</option>
              </select>
            </div>
            {income <= 0 && (
              <div style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 10 }}>
                Informe sua renda mensal para calcular o portfólio ideal.
              </div>
            )}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10, marginBottom: 10 }}>
              <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 10 }}>
                <div style={metricLabel}>Retorno anual</div>
                <div style={metricValue}>{currency(toNumber(portfolioQuery.data?.total_annual_return))}</div>
              </div>
              <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 10 }}>
                <div style={metricLabel}>Custo anuidade</div>
                <div style={metricValue}>{currency(toNumber(portfolioQuery.data?.total_annuity_cost))}</div>
              </div>
              <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 10 }}>
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
                    style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10, display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto auto', gap: 10 }}
                  >
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 14 }}>{item.name || item.card_name || item.card_id || 'Cartão recomendado'}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                        Cashback: {toNumber(item.cashback_pct || item.cashback || 0).toFixed(2)}%
                      </div>
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                      {currency(toNumber(item.annual_return || item.estimated_return || 0))}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>ano</div>
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
                style={{ width: '100%', border: '1px solid var(--border-color)', borderRadius: 8, padding: 8, marginBottom: 10 }}
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
                  <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                    <div style={metricLabel}>Perda estimada</div>
                    <div style={metricValue}>{currency(toNumber(opportunityQuery.data?.lost_value || opportunityQuery.data?.opportunity_cost || 0))}</div>
                  </div>
                  <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                    <div style={metricLabel}>Melhor alternativa</div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
                      {opportunityQuery.data?.best_alternative || opportunityQuery.data?.recommended_card || 'Sem recomendação específica'}
                    </div>
                  </div>
                  <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                    <div style={metricLabel}>ROI do cartão atual</div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
                      {roiQuery.data?.verdict || roiQuery.data?.diagnosis || 'Sem diagnóstico'}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                      Retorno anual: {currency(toNumber(roiQuery.data?.annual_return_value || roiQuery.data?.annual_return || 0))}
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div style={card}>
              <div style={sectionTitle}>Promoções ativas</div>
              {promotions.length === 0 && <div style={{ color: 'var(--text-muted)', fontSize: 14 }}>Nenhuma promoção ativa no momento.</div>}
              {promotions.slice(0, 5).map((promo: any, idx: number) => (
                <div key={`${promo.id || promo.title || idx}`} style={{ borderBottom: '1px solid var(--border-color)', padding: '8px 0' }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{promo.title || promo.name || 'Promoção'}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                    {promo.description || promo.details || 'Condição promocional disponível.'}
                  </div>
                </div>
              ))}
              <div style={{ marginTop: 10, borderTop: '1px solid var(--border-color)', paddingTop: 10 }}>
                <div style={{ ...metricLabel, marginBottom: 6 }}>Oportunidades para o portfólio</div>
                {(promotionOpportunitiesQuery.data?.opportunities || []).length === 0 && (
                  <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>Sem oportunidades personalizadas no momento.</div>
                )}
                {(promotionOpportunitiesQuery.data?.opportunities || []).slice(0, 3).map((item: any, idx: number) => (
                  <div key={`${item.user_card || idx}`} style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>
                    • {item.user_card || 'Cartão'}: {item.alert_text || 'Promoção disponível'}
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div style={card}>
            <div style={sectionTitle}>Optimizer Intelligence</div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
              <button
                onClick={() => optimizerAnalysisMutation.mutate()}
                style={{ border: '1px solid #111', background: 'var(--text-primary)', color: 'var(--bg-surface)', borderRadius: 8, padding: '8px 12px', cursor: 'pointer' }}
              >
                Rodar análise completa
              </button>
              {currentCard && (
                <div style={{ fontSize: 12, color: 'var(--text-muted)', alignSelf: 'center' }}>
                  Usando o cartão selecionado como referência atual.
                </div>
              )}
            </div>

            {optimizerAnalysisMutation.isPending && (
              <div style={{ color: 'var(--text-muted)', fontSize: 14 }}>Gerando relatório inteligente...</div>
            )}
            {optimizerAnalysisMutation.isError && (
              <div style={{ fontSize: 12, color: '#991b1b', marginBottom: 8 }}>
                {getErrorMessage(optimizerAnalysisMutation.error, 'Falha ao gerar análise completa do Optimizer.')}
              </div>
            )}

            {!optimizerAnalysisMutation.isPending && Object.keys(optimizerAnalysis).length > 0 && (
              <div style={{ display: 'grid', gap: 12 }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}>
                  <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                    <div style={metricLabel}>Recomendação</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
                      {optimizerAnalysis.recommendation_type || 'N/A'}
                    </div>
                  </div>
                  <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                    <div style={metricLabel}>Estratégia</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
                      {optimizerAnalysis.strategy_text || 'N/A'}
                    </div>
                  </div>
                  <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                    <div style={metricLabel}>Melhor cartão</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
                      {optimizerBestCard.card_name || optimizerBestCard.name || optimizerBestCard.card_id || 'Sem cartão'}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                      Ganho líquido: {currency(toNumber(optimizerBestCard.net_gain_expected || optimizerBestCard.net_gain || 0))}
                    </div>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10 }}>
                  <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                    <div style={{ ...metricLabel, marginBottom: 8 }}>Resumo do perfil</div>
                    <div style={{ display: 'grid', gap: 6, fontSize: 12, color: 'var(--text-secondary)' }}>
                      <div>Cluster: {optimizerProfileSummary.lifestyle_cluster || optimizerProfileSummary.cluster || 'N/A'}</div>
                      <div>FSS: {optimizerProfileSummary.fss ?? 'N/A'} {optimizerProfileSummary.fss_level ? `(${optimizerProfileSummary.fss_level})` : ''}</div>
                      <div>Família com filhos: {optimizerProfileSummary.is_family_with_kids ? 'Sim' : 'Não'}</div>
                      <div>Dia ideal de notificação: {optimizerProfileSummary.best_notification_day ?? 'N/A'}</div>
                    </div>
                  </div>

                  <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                    <div style={{ ...metricLabel, marginBottom: 8 }}>Eventos de vida detectados</div>
                    {optimizerLifeEvents.length === 0 && (
                      <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>Nenhum evento relevante encontrado.</div>
                    )}
                    {optimizerLifeEvents.slice(0, 4).map((event: any, idx: number) => (
                      <div key={`${event.event || idx}`} style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>
                        • {event.event || 'Evento'} - {event.trigger_action || 'Ação sugerida'}
                      </div>
                    ))}
                  </div>
                </div>

                <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                  <div style={{ ...metricLabel, marginBottom: 8 }}>Insights acionáveis</div>
                  {optimizerInsights.length === 0 && (
                    <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>Nenhum insight acionável disponível.</div>
                  )}
                  {optimizerInsights.slice(0, 4).map((insight: any, idx: number) => (
                    <div key={`${insight.type || idx}`} style={{ borderBottom: idx < Math.min(3, optimizerInsights.length - 1) ? '1px solid var(--border-color)' : 'none', padding: '8px 0' }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
                        {insight.title || insight.type || 'Insight'}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                        {insight.description || 'Sem descrição disponível.'}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                        Ganho: {insight.gain_interval?.expected ? currency(toNumber(insight.gain_interval.expected)) : 'N/A'}
                      </div>
                    </div>
                  ))}
                </div>

                {optimizerWarnings.length > 0 && (
                  <div style={{ fontSize: 12, color: '#92400e' }}>
                    {optimizerWarnings.slice(0, 3).map((warn: string, idx: number) => (
                      <div key={`${idx}-${warn}`}>• {warn}</div>
                    ))}
                  </div>
                )}

                <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                  <div style={{ ...metricLabel, marginBottom: 8 }}>Histórico de relatórios</div>
                  {optimizerReports.length === 0 && (
                    <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>Nenhum relatório salvo encontrado.</div>
                  )}
                  {optimizerReports.slice(0, 4).map((report: any, idx: number) => (
                    <div key={`${report.report_id || idx}`} style={{ borderBottom: idx < Math.min(3, optimizerReports.length - 1) ? '1px solid var(--border-color)' : 'none', padding: '8px 0' }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
                        {report.best_card?.card_name || report.best_card_name || report.recommendation_type || 'Relatório'}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                        {report.generated_at ? String(report.generated_at).slice(0, 10) : 'Data indisponível'}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                        {report.strategy_text || 'Sem descrição resumida.'}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {tab === 'cards' && (
        <div style={{ display: 'grid', gap: 12 }}>
          {isCardsLoading && (
            <div style={{ ...card, color: 'var(--text-muted)', fontSize: 14 }}>Carregando cartões detectados nas transações...</div>
          )}

          <div style={card}>
            <div style={sectionTitle}>Cartões cadastrados na conta</div>
            <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12 }}>
              Esta visão usa diretamente as transações injetadas no backend para agrupar as contas/cartões do seu `user_id`.
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10, marginBottom: 12 }}>
              <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                <div style={metricLabel}>Cartões/contas detectados</div>
                <div style={metricValue}>{accountCardSummaries.length}</div>
              </div>
              <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                <div style={metricLabel}>Transações carregadas</div>
                <div style={metricValue}>{transactionCards.length}</div>
              </div>
              <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                <div style={metricLabel}>Total de despesas</div>
                <div style={metricValue}>{currency(transactionCards.reduce((sum: number, tx: any) => sum + (toNumber(tx.amount) < 0 ? Math.abs(toNumber(tx.amount)) : 0), 0))}</div>
              </div>
            </div>

            {accountCardSummaries.length === 0 && (
              <div style={{ color: 'var(--text-muted)', fontSize: 14 }}>
                Nenhuma conta/cartão encontrado nas transações atuais.
              </div>
            )}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
            {accountCardSummaries.map((item: any) => {
              const topCategory = Object.entries(item.categories || {})
                .sort((a, b) => Number(b[1]) - Number(a[1]))[0];

              return (
                <div key={item.account_id} style={card}>
                  <div style={sectionTitle}>{item.label}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10 }}>
                    ID da conta/cartão: {item.account_id}
                  </div>
                  <div style={{ display: 'grid', gap: 8 }}>
                    <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                      <div style={metricLabel}>Movimentações</div>
                      <div style={metricValue}>{item.transaction_count}</div>
                    </div>
                    <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                      <div style={metricLabel}>Despesas</div>
                      <div style={metricValue}>{currency(item.total_spent)}</div>
                    </div>
                    <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                      <div style={metricLabel}>Receitas</div>
                      <div style={metricValue}>{currency(item.total_income)}</div>
                    </div>
                    <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                      <div style={metricLabel}>Categoria dominante</div>
                      <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
                        {topCategory ? `${topCategory[0]} (${currency(toNumber(topCategory[1]))})` : 'Sem categoria'}
                      </div>
                    </div>
                    <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                      <div style={metricLabel}>Última movimentação</div>
                      <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
                        {item.last_activity ? String(item.last_activity).slice(0, 10) : 'Sem data'}
                      </div>
                    </div>
                    <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                      <div style={metricLabel}>Exemplos</div>
                      <div style={{ display: 'grid', gap: 4 }}>
                        {(item.sample_descriptions || []).slice(0, 3).map((desc: string, idx: number) => (
                          <div key={`${item.account_id}-${idx}`} style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                            • {desc}
                          </div>
                        ))}
                      </div>
                    </div>
                    <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                      <div style={metricLabel}>Saldo líquido nas transações</div>
                      <div style={metricValue}>{currency(item.net_total)}</div>
                    </div>
                  </div>
                </div>
              );
            })}
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
              <input type="number" value={targetAmount} onChange={(e) => setTargetAmount(Number(e.target.value || 0))} style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 8 }} />
              <input type="number" value={downPayment} onChange={(e) => setDownPayment(Number(e.target.value || 0))} style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 8 }} />
              <input type="number" value={months} onChange={(e) => setMonths(Number(e.target.value || 0))} style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 8 }} />
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
                  <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                    <div style={metricLabel}>Estratégia recomendada</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
                      {architectResult.recommended_strategy || 'N/A'}
                    </div>
                  </div>
                  <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                    <div style={metricLabel}>Confiança</div>
                    <div style={metricValue}>{(toNumber(architectResult.confidence_score) * 100).toFixed(0)}%</div>
                  </div>
                  <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                    <div style={metricLabel}>Prazo alvo</div>
                    <div style={metricValue}>{toNumber(architectResult.months_to_achieve)} meses</div>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10 }}>
                  <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                    <div style={metricLabel}>Custo esperado</div>
                    <div style={metricValue}>{currency(toNumber(architectResult?.costs?.expected_cost))}</div>
                  </div>
                  <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                    <div style={metricLabel}>Liquidez impactada</div>
                    <div style={metricValue}>{(toNumber(architectResult.liquidity_impact) * 100).toFixed(0)}%</div>
                  </div>
                </div>

                <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
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

                <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
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
                <div key={`${sim.simulation_id || idx}`} style={{ borderBottom: '1px solid var(--border-color)', padding: '8px 0' }}>
                  <div style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 600 }}>{sim.recommended_strategy || 'Estratégia simulada'}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    {sim.created_at ? String(sim.created_at).slice(0, 10) : 'Data indisponível'}
                  </div>
                </div>
              ))}
            </div>
            <div style={card}>
              <div style={sectionTitle}>Métricas</div>
              <div style={{ display: 'grid', gap: 8 }}>
                <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                  <div style={metricLabel}>Simulações totais</div>
                  <div style={metricValue}>{toNumber(architectMetrics.data?.total_simulations)}</div>
                </div>
                <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
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
              <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value || new Date().getFullYear()))} style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 8 }} />
              <select value={month} onChange={(e) => setMonth(e.target.value === '' ? '' : Number(e.target.value))} style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 8 }}>
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
                <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                  <div style={metricLabel}>Total dedutível</div>
                  <div style={metricValue}>{currency(toNumber(fiscalData.total_deductible || fiscalData.deductible_total))}</div>
                </div>
                <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                  <div style={metricLabel}>Economia estimada</div>
                  <div style={metricValue}>{currency(toNumber(fiscalData.estimated_savings || fiscalData.tax_savings))}</div>
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                  {fiscalData.summary_text || 'Dados fiscais consolidados para o período selecionado.'}
                </div>
              </div>
            </div>
            <div style={card}>
              <div style={sectionTitle}>Uso Misto PF/PJ</div>
              <div style={{ display: 'grid', gap: 8 }}>
                <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                  <div style={metricLabel}>Transações com uso misto</div>
                  <div style={metricValue}>{toNumber(mixedUseData.total_mixed_transactions || mixedUseData.count)}</div>
                </div>
                <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                  <div style={metricLabel}>Percentual misto</div>
                  <div style={metricValue}>{toNumber(mixedUseData.mixed_pct || mixedUseData.percentage).toFixed(1)}%</div>
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
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
              style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 8, width: 180, marginBottom: 10 }}
            />
            {income <= 0 && (
              <div style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 10 }}>
                Informe a renda mensal para habilitar benchmark e notificações.
              </div>
            )}
            <div style={{ display: 'grid', gap: 8 }}>
              <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                <div style={metricLabel}>Score de comparação</div>
                <div style={metricValue}>{toNumber(peerData.peer_score || peerData.comparison_score)}</div>
              </div>
              <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                <div style={metricLabel}>Posição de gastos</div>
                <div style={metricValue}>{toNumber(peerData.expense_percentile).toFixed(0)}%</div>
              </div>
              <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
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
              <div key={`${note.id || idx}`} style={{ borderBottom: '1px solid var(--border-color)', padding: '8px 0' }}>
                <div style={{ fontSize: 14, color: 'var(--text-primary)', fontWeight: 600 }}>
                  {note.title || note.type || 'Notificação'}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                  {note.message || note.description || 'Atualização financeira disponível.'}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'advanced' && (
        <div style={{ display: 'grid', gap: 12 }}>
          {isAdvancedLoading && (
            <div style={{ ...card, color: 'var(--text-muted)', fontSize: 14 }}>Carregando análise de custos bancários...</div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
            <div style={card}>
              <div style={sectionTitle}>F5 • Raio-X de Custos Bancários</div>
              {costsQuery.isError && (
                <div style={{ fontSize: 12, color: '#991b1b', marginBottom: 8 }}>
                  {getErrorMessage(costsQuery.error, 'Falha ao carregar custos bancários. Verifique se o usuário possui extratos no backend.')}
                </div>
              )}
              <div style={{ display: 'grid', gap: 8 }}>
                <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                  <div style={metricLabel}>Total pago no período</div>
                  <div style={metricValue}>{currency(toNumber(costsData.total_paid))}</div>
                </div>
                <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                  <div style={metricLabel}>Média mensal</div>
                  <div style={metricValue}>{currency(toNumber(costsData.monthly_avg))}</div>
                </div>
                <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                  <div style={metricLabel}>Economia potencial/mês</div>
                  <div style={metricValue}>{currency(toNumber(costsData.savings_opportunity))}</div>
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                  {Array.isArray(costsData.by_bank) && costsData.by_bank.length > 0
                    ? `${costsData.by_bank.length} bancos analisados.`
                    : 'Sem dados suficientes para análise de tarifas.'}
                </div>
              </div>
            </div>

            <div style={card}>
              <div style={sectionTitle}>F7 • Modo Compra Inteligente</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10 }}>
                Contexto atual: renda {contextIncome > 0 ? currency(contextIncome) : 'não detectada'} • safe-to-spend {currency(contextSafeToSpend)} • score {contextHealthScore.toFixed(0)}/100 • perfil {contextRiskProfile}
              </div>
              <div style={{ display: 'grid', gap: 8, marginBottom: 10 }}>
                <input
                  type="number"
                  value={purchaseAmount}
                  onChange={(e) => setPurchaseAmount(Number(e.target.value || 0))}
                  style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 8 }}
                />
                <input
                  value={purchaseCategory}
                  onChange={(e) => setPurchaseCategory(e.target.value)}
                  placeholder="Categoria"
                  style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 8 }}
                />
                <input
                  type="number"
                  value={purchaseInstallments}
                  min={1}
                  max={48}
                  onChange={(e) => {
                    setAutoInstallments(false);
                    setPurchaseInstallments(Number(e.target.value || 1));
                  }}
                  style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 8 }}
                />
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    Sugestão inteligente: {suggestedInstallments}x
                  </span>
                  <button
                    onClick={() => {
                      setAutoInstallments(true);
                      setPurchaseInstallments(suggestedInstallments);
                    }}
                    style={{ border: '1px solid var(--border-color)', background: 'var(--bg-surface)', color: 'var(--text-primary)', borderRadius: 8, padding: '6px 10px', cursor: 'pointer', fontSize: 12 }}
                  >
                    Usar sugestão
                  </button>
                </div>
                <button
                  onClick={() => purchaseMutation.mutate()}
                  style={{ border: '1px solid #111', background: 'var(--text-primary)', color: 'var(--bg-surface)', borderRadius: 8, padding: '8px 12px', cursor: 'pointer' }}
                >
                  Analisar compra
                </button>
              </div>

              {purchaseMutation.isPending && <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>Calculando melhores opções...</div>}
              {purchaseMutation.isError && (
                <div style={{ fontSize: 12, color: '#991b1b', marginBottom: 8 }}>
                  {getErrorMessage(purchaseMutation.error, 'Falha ao analisar compra. Verifique autenticação e dados disponíveis no backend.')}
                </div>
              )}
              {!purchaseMutation.isPending && Object.keys(purchaseData).length > 0 && (
                <div style={{ display: 'grid', gap: 8 }}>
                  <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                    <div style={metricLabel}>Método recomendado</div>
                    <div style={{ fontSize: 14, color: 'var(--text-primary)', fontWeight: 700 }}>{purchaseData.recommended_label || purchaseData.recommended_method || 'N/A'}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                      Custo líquido: {currency(toNumber(purchaseData.recommended_net_cost))}
                    </div>
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    {purchaseData.reasoning || 'Sem justificativa detalhada para este cenário.'}
                  </div>
                  {Array.isArray(purchaseData.options) && purchaseData.options.length > 0 && (
                    <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                      <div style={{ ...metricLabel, marginBottom: 8 }}>Comparativo de opções</div>
                      {purchaseData.options.slice(0, 4).map((option: any, idx: number) => (
                        <div key={`${option.method || idx}`} style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 8, borderBottom: idx < Math.min(3, purchaseData.options.length - 1) ? '1px solid var(--border-color)' : 'none', padding: '6px 0' }}>
                          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                            {option.label || option.method || 'Opção'}
                          </div>
                          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)' }}>
                            {currency(toNumber(option.net_cost_real ?? option.net_cost ?? option.total_cost))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  {Array.isArray(purchaseData.warnings) && purchaseData.warnings.length > 0 && (
                    <div style={{ fontSize: 12, color: '#92400e' }}>
                      {purchaseData.warnings.slice(0, 3).map((warn: string, idx: number) => (
                        <div key={`${idx}-${warn}`}>• {warn}</div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          <div style={card}>
            <div style={sectionTitle}>F13 • Negotiator Bot</div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
              <input
                value={negotiationBank}
                onChange={(e) => setNegotiationBank(e.target.value)}
                placeholder="Banco (opcional, ex: Itaú)"
                style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 8, minWidth: 240 }}
              />
              <button
                onClick={() => negotiatorMutation.mutate()}
                style={{ border: '1px solid #111', background: 'var(--text-primary)', color: 'var(--bg-surface)', borderRadius: 8, padding: '8px 12px', cursor: 'pointer' }}
              >
                Gerar roteiro
              </button>
            </div>

            {negotiatorMutation.isPending && <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>Gerando scripts de negociação...</div>}
            {negotiatorMutation.isError && (
              <div style={{ fontSize: 12, color: '#991b1b', marginBottom: 8 }}>
                {getErrorMessage(negotiatorMutation.error, 'Falha ao gerar roteiro. Verifique se há histórico de transações no backend para este usuário.')}
              </div>
            )}

            {!negotiatorMutation.isPending && Object.keys(negotiationData).length > 0 && (
              <div style={{ display: 'grid', gap: 10 }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
                  <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                    <div style={metricLabel}>Oportunidades</div>
                    <div style={metricValue}>{toNumber(negotiationData.opportunities_found)}</div>
                  </div>
                  <div style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                    <div style={metricLabel}>Confiança</div>
                    <div style={metricValue}>{(toNumber(negotiationData.confidence_score) * 100).toFixed(0)}%</div>
                  </div>
                </div>

                <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                  {negotiationData.summary || 'Sem resumo disponível para negociação neste momento.'}
                </div>

                {(negotiationData.scripts || []).slice(0, 3).map((script: any, idx: number) => (
                  <div key={`${idx}-${script?.opportunity?.bank_name || 'bank'}`} style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
                      {script?.opportunity?.bank_name || 'Banco'} • {script?.opportunity?.product || 'Produto'}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>
                      Meta: {script?.target_ask || 'Negociar condições melhores'}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                      {script?.opening_line || 'Sem script gerado para esta oportunidade.'}
                    </div>
                  </div>
                ))}
                {Array.isArray(negotiationData.warnings) && negotiationData.warnings.length > 0 && (
                  <div style={{ fontSize: 12, color: '#92400e' }}>
                    {negotiationData.warnings.slice(0, 3).map((warn: string, idx: number) => (
                      <div key={`${idx}-${warn}`}>• {warn}</div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </AppShell>
  );
};
