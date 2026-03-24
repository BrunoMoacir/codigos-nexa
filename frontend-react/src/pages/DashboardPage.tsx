import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AppShell } from '../components/layout/AppShell';
import { nexaApi } from '../api/nexa';

const cardStyle: React.CSSProperties = {
  background: '#fff',
  border: '1px solid #ebebeb',
  borderRadius: 12,
  padding: 18,
};

const titleStyle: React.CSSProperties = {
  fontSize: 11,
  letterSpacing: 0.8,
  textTransform: 'uppercase',
  color: '#aaa',
  marginBottom: 8,
  fontWeight: 600,
};

function currency(value: number) {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value || 0);
}

export const DashboardPage: React.FC = () => {
  const userId = localStorage.getItem('user_id') || '';

  const forecastQuery = useQuery({
    queryKey: ['forecast', userId],
    queryFn: () => nexaApi.getForecast(userId),
    enabled: !!userId,
  });

  const incomeForBudget = useMemo(() => {
    const rawIncome = Number(forecastQuery.data?.financial_health?.total_income || 0);
    return rawIncome > 0 ? rawIncome : 10000;
  }, [forecastQuery.data]);

  const budgetQuery = useQuery({
    queryKey: ['budget', userId, incomeForBudget],
    queryFn: () => nexaApi.getBudget(userId, incomeForBudget),
    enabled: !!userId,
  });

  const goalsQuery = useQuery({
    queryKey: ['goals', userId],
    queryFn: () => nexaApi.getGoals(userId),
    enabled: !!userId,
  });

  const txQuery = useQuery({
    queryKey: ['transactions', userId],
    queryFn: () => nexaApi.getTransactions(userId, 200),
    enabled: !!userId,
  });

  const alertsQuery = useQuery({
    queryKey: ['alerts', userId],
    queryFn: () => nexaApi.getAlerts(userId),
    enabled: !!userId,
  });

  const subscriptionsQuery = useQuery({
    queryKey: ['subscriptions', userId],
    queryFn: () => nexaApi.getSubscriptions(userId),
    enabled: !!userId,
  });

  const isLoading =
    forecastQuery.isLoading || budgetQuery.isLoading || goalsQuery.isLoading || txQuery.isLoading;

  const financialHealth = forecastQuery.data?.financial_health || {};
  const safeToSpend = forecastQuery.data?.safe_to_spend || {};
  const shadow = forecastQuery.data?.shadow_invoices || {};
  const cashflow = forecastQuery.data?.cashflow || {};

  const goals = goalsQuery.data?.goals || [];
  const transactions = txQuery.data?.transactions || [];
  const alerts = alertsQuery.data?.alerts || [];
  const subscriptions = subscriptionsQuery.data?.subscriptions || [];

  return (
    <AppShell
      current="dashboard"
      title="Meu Dinheiro"
      subtitle="Dados reais via Open Finance com visão executiva do seu fluxo."
    >
      {isLoading && <p style={{ color: '#888', marginBottom: 14 }}>Carregando dados financeiros...</p>}

      {(forecastQuery.isError || budgetQuery.isError) && (
        <div style={{ ...cardStyle, borderColor: '#fecaca', color: '#b91c1c', marginBottom: 16 }}>
          Não foi possível carregar parte dos dados. Verifique se o backend está ativo.
        </div>
      )}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
          gap: 12,
          marginBottom: 14,
        }}
      >
        <div style={cardStyle}>
          <div style={titleStyle}>Renda Mensal</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{currency(financialHealth.total_income || 0)}</div>
          <div style={{ color: '#777', fontSize: 12, marginTop: 6 }}>
            Perfil: {financialHealth.profile_type || 'EQUILIBRADO'}
          </div>
        </div>
        <div style={cardStyle}>
          <div style={titleStyle}>Safe To Spend</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{currency(safeToSpend.safe_to_spend_total || 0)}</div>
          <div style={{ color: '#777', fontSize: 12, marginTop: 6 }}>
            {currency(safeToSpend.safe_to_spend_daily || 0)}/dia
          </div>
        </div>
        <div style={cardStyle}>
          <div style={titleStyle}>Health Score</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{Number(financialHealth.health_score || 0).toFixed(0)} / 100</div>
          <div style={{ color: '#777', fontSize: 12, marginTop: 6 }}>
            Poupança: {((financialHealth.savings_rate || 0) * 100).toFixed(1)}%
          </div>
        </div>
        <div style={cardStyle}>
          <div style={titleStyle}>Gastos Mensais</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{currency(financialHealth.total_expenses || 0)}</div>
          <div style={{ color: '#777', fontSize: 12, marginTop: 6 }}>
            Risco: {safeToSpend.risk_level || 'LOW'}
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: 12, marginBottom: 12 }}>
        <div style={cardStyle}>
          <div style={titleStyle}>Orçamento 50/30/20</div>
          {Number(forecastQuery.data?.financial_health?.total_income || 0) <= 0 && (
            <div style={{ color: '#92400e', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 8, padding: 10, marginBottom: 10, fontSize: 13 }}>
              Renda não detectada nas transações. Usando referência de {currency(10000)} para cálculo do orçamento.
            </div>
          )}
          <div style={{ color: '#444', fontSize: 14, marginBottom: 8 }}>{budgetQuery.data?.summary_text || 'Sem resumo disponível.'}</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
            {(budgetQuery.data?.group_summary || []).slice(0, 3).map((g: any) => (
              <div key={g.group} style={{ border: '1px solid #eee', borderRadius: 8, padding: 10 }}>
                <div style={{ fontWeight: 600, fontSize: 13, textTransform: 'capitalize' }}>{g.group}</div>
                <div style={{ marginTop: 6, fontSize: 18, fontWeight: 700 }}>{Number(g.current_pct || 0).toFixed(1)}%</div>
                <div style={{ color: '#777', fontSize: 12 }}>meta {Number(g.target_pct || 0).toFixed(0)}%</div>
              </div>
            ))}
          </div>
        </div>

        <div style={cardStyle}>
          <div style={titleStyle}>Obrigações Futuras</div>
          <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 8 }}>{currency(Math.abs(Number(shadow.total_monthly_impact || 0)))}/mês</div>
          <div style={{ color: '#666', fontSize: 13, lineHeight: 1.6 }}>
            {Number(shadow.total_count || 0)} itens detectados
            <br />
            {Number(shadow.subscriptions_count || 0)} assinaturas
            <br />
            {Number(shadow.installments_count || 0)} parcelas
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
        <div style={cardStyle}>
          <div style={titleStyle}>Metas Financeiras</div>
          {goals.length === 0 && <div style={{ color: '#777', fontSize: 14 }}>Nenhuma meta cadastrada.</div>}
          {goals.slice(0, 3).map((goal: any) => {
            const pct = Number(goal.progress_pct || 0);
            return (
              <div key={goal.id || goal.name} style={{ marginBottom: 10, paddingBottom: 10, borderBottom: '1px solid #f0f0f0' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <strong style={{ fontSize: 14 }}>{goal.name || 'Meta'}</strong>
                  <span style={{ fontSize: 13, color: '#555' }}>{pct.toFixed(0)}%</span>
                </div>
                <div style={{ height: 7, background: '#f0f0f0', borderRadius: 99, overflow: 'hidden' }}>
                  <div
                    style={{
                      width: `${Math.min(100, pct)}%`,
                      height: '100%',
                      background: '#111',
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>

        <div style={cardStyle}>
          <div style={titleStyle}>Alertas e Assinaturas</div>
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 14, color: '#444', marginBottom: 6 }}>Alertas ativos: {alerts.length}</div>
            {(alerts || []).slice(0, 3).map((alert: any) => (
              <div key={alert.id || alert.title} style={{ fontSize: 13, color: '#666', marginBottom: 5 }}>
                • {alert.title || alert.type || 'Alerta'}
              </div>
            ))}
          </div>
          <div style={{ fontSize: 14, color: '#444', marginBottom: 6 }}>
            Assinaturas: {subscriptionsQuery.data?.total_subscriptions || subscriptions.length}
          </div>
          <div style={{ fontSize: 14, color: '#444' }}>
            Custo mensal: {currency(subscriptionsQuery.data?.total_monthly_cost || 0)}
          </div>
        </div>
      </div>

      <div style={cardStyle}>
        <div style={titleStyle}>Transações Recentes</div>
        {transactions.length === 0 && <div style={{ color: '#777' }}>Sem transações para exibir.</div>}
        {transactions.length > 0 && (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ textAlign: 'left', color: '#888', borderBottom: '1px solid #f0f0f0' }}>
                  <th style={{ padding: '8px 6px' }}>Data</th>
                  <th style={{ padding: '8px 6px' }}>Descrição</th>
                  <th style={{ padding: '8px 6px' }}>Categoria</th>
                  <th style={{ padding: '8px 6px', textAlign: 'right' }}>Valor</th>
                </tr>
              </thead>
              <tbody>
                {transactions.slice(0, 12).map((tx: any) => {
                  const value = Number(tx.amount || 0);
                  return (
                    <tr key={tx.transaction_id || tx.id} style={{ borderBottom: '1px solid #f7f7f7' }}>
                      <td style={{ padding: '8px 6px', color: '#666' }}>{tx.date || '-'}</td>
                      <td style={{ padding: '8px 6px' }}>{tx.description || '-'}</td>
                      <td style={{ padding: '8px 6px', color: '#666' }}>{tx.category || '-'}</td>
                      <td style={{ padding: '8px 6px', textAlign: 'right', color: value < 0 ? '#b91c1c' : '#166534', fontWeight: 600 }}>
                        {currency(value)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div style={{ marginTop: 12, color: '#777', fontSize: 13 }}>
        Saldo projetado 30d: {currency(Number(cashflow.ending_balance || 0))}
      </div>
    </AppShell>
  );
};
