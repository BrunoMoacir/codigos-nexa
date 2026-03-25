import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Bar,
  BarChart,
  Cell,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
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

function getGaugeColor(pct: number) {
  if (pct > 100) return '#E74C3C';
  if (pct >= 86) return '#0762C7';
  if (pct >= 61) return '#0978F6';
  return '#6BAEFA';
}

function getCategoryColor(pct: number) {
  if (pct > 90) return '#0762C7';
  if (pct >= 71) return '#0978F6';
  return '#6BAEFA';
}

function getPaceColor(pct: number) {
  if (pct > 120) return '#E74C3C';
  if (pct > 105) return '#0762C7';
  if (pct >= 80) return '#0978F6';
  return '#6BAEFA';
}

function getUrgencyMeta(daysUntil: number) {
  if (daysUntil <= 1) {
    return { label: daysUntil <= 0 ? 'Hoje' : 'Amanhã', color: '#E74C3C', icon: '!' };
  }
  if (daysUntil <= 5) {
    return { label: `Em ${daysUntil} dias`, color: '#F39C12', icon: '!' };
  }
  if (daysUntil <= 14) {
    return { label: `Em ${daysUntil} dias`, color: '#0978F6', icon: 'i' };
  }
  return { label: `Em ${daysUntil} dias`, color: '#6B7280', icon: 'i' };
}

function parseDaysUntil(dateValue: string) {
  const due = new Date(dateValue);
  if (Number.isNaN(due.getTime())) {
    return 999;
  }
  const now = new Date();
  const dueOnly = new Date(due.getFullYear(), due.getMonth(), due.getDate());
  const nowOnly = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const diffMs = dueOnly.getTime() - nowOnly.getTime();
  return Math.floor(diffMs / (1000 * 60 * 60 * 24));
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
  const shadowInvoices = forecastQuery.data?.shadow_invoices?.invoices || [];

  const monthlyBudget = Number(safeToSpend.safe_to_spend_total || 0);

  const spentToDate = useMemo(() => {
    const now = new Date();
    const currentMonth = now.getMonth();
    const currentYear = now.getFullYear();

    return transactions.reduce((sum: number, tx: any) => {
      const amount = Number(tx.amount || 0);
      const parsed = new Date(tx.date);
      if (Number.isNaN(parsed.getTime())) {
        return sum;
      }
      if (parsed.getMonth() !== currentMonth || parsed.getFullYear() !== currentYear) {
        return sum;
      }
      return amount < 0 ? sum + Math.abs(amount) : sum;
    }, 0);
  }, [transactions]);

  const consumedPct = monthlyBudget > 0 ? (spentToDate / monthlyBudget) * 100 : 0;
  const clampedConsumedPct = Math.max(0, Math.min(consumedPct, 100));
  const gaugeColor = getGaugeColor(consumedPct);

  const categoryBreakdown = useMemo(() => {
    const allocations = budgetQuery.data?.allocations || [];
    return allocations
      .map((item: any) => {
        const spent = Number(item.current_amount || 0);
        const budget = Number(item.suggested_amount || 0);
        const pct = budget > 0 ? (spent / budget) * 100 : 0;
        return {
          category: item.category || 'Categoria',
          spent,
          budget,
          pct,
        };
      })
      .sort((a: any, b: any) => b.pct - a.pct)
      .slice(0, 8);
  }, [budgetQuery.data]);

  const dailySpendData = useMemo(() => {
    const byDate = new Map<string, number>();

    transactions.forEach((tx: any) => {
      const amount = Number(tx.amount || 0);
      const date = String(tx.date || '');
      if (!date) return;
      if (amount >= 0) return;

      byDate.set(date, (byDate.get(date) || 0) + Math.abs(amount));
    });

    return Array.from(byDate.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .slice(-14)
      .map(([date, total]) => ({
        date: date.slice(5),
        total,
      }));
  }, [transactions]);

  const dailySpendWithColor = useMemo(
    () =>
      dailySpendData.map((d) => ({
        ...d,
        fill: d.total < 10 ? '#6BAEFA' : d.total <= 50 ? '#0978F6' : '#0762C7',
      })),
    [dailySpendData]
  );

  const currentDate = new Date();
  const daysInMonth = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0).getDate();
  const dayOfMonth = currentDate.getDate();
  const monthProgress = dayOfMonth / daysInMonth;
  const expectedSpendToDate = monthlyBudget * monthProgress;
  const pacePct = expectedSpendToDate > 0 ? (spentToDate / expectedSpendToDate) * 100 : 0;
  const paceColor = getPaceColor(pacePct);

  const agendaItems = useMemo(() => {
    return shadowInvoices
      .map((invoice: any) => {
        const dueDate = String(invoice.next_due_date || invoice.due_date || '');
        const daysUntil = parseDaysUntil(dueDate);
        return {
          description: invoice.description || 'Compromisso financeiro',
          amount: Math.abs(Number(invoice.amount || 0)),
          dueDate,
          daysUntil,
          type: invoice.type || 'ITEM',
        };
      })
      .filter((item: any) => item.dueDate)
      .sort((a: any, b: any) => a.daysUntil - b.daysUntil)
      .slice(0, 6);
  }, [shadowInvoices]);

  const showSkeleton = isLoading && !forecastQuery.data && !budgetQuery.data && !txQuery.data;

  const renderSkeletonBlock = (height = 80) => (
    <div
      style={{
        height,
        borderRadius: 10,
        background: 'linear-gradient(90deg, #f3f4f6 20%, #f8fafc 50%, #f3f4f6 80%)',
        border: '1px solid #edf0f2',
      }}
    />
  );

  return (
    <AppShell
      current="dashboard"
      title="Meu Dinheiro"
      subtitle="Dados reais via Open Finance com visão executiva do seu fluxo."
    >
      {isLoading && <p style={{ color: '#888', marginBottom: 14 }}>Carregando dados financeiros...</p>}

      {showSkeleton && (
        <div style={{ display: 'grid', gap: 12, marginBottom: 14 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
            {renderSkeletonBlock()}
            {renderSkeletonBlock()}
            {renderSkeletonBlock()}
            {renderSkeletonBlock()}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {renderSkeletonBlock(220)}
            {renderSkeletonBlock(220)}
          </div>
        </div>
      )}

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
          <div style={titleStyle}>Safe-to-Spend (Consumo do Orçamento)</div>
          <div style={{ display: 'grid', gridTemplateColumns: '210px 1fr', gap: 10, alignItems: 'center' }}>
            <div style={{ height: 180 }}>
              <ResponsiveContainer width="100%" height="100%">
                <RadialBarChart
                  innerRadius="72%"
                  outerRadius="100%"
                  data={[{ name: 'consumido', value: clampedConsumedPct }]}
                  startAngle={90}
                  endAngle={-270}
                >
                  <RadialBar dataKey="value" cornerRadius={10} background fill={gaugeColor} />
                </RadialBarChart>
              </ResponsiveContainer>
            </div>
            <div>
              <div style={{ fontSize: 22, fontWeight: 700, color: '#1a1a2e' }}>{consumedPct.toFixed(0)}%</div>
              <div style={{ color: '#666', fontSize: 13, marginTop: 4 }}>
                De {currency(monthlyBudget)} você já gastou {currency(spentToDate)}
              </div>
              <div style={{ color: '#666', fontSize: 13, marginTop: 4 }}>
                Limite diário sugerido: {currency(Number(safeToSpend.safe_to_spend_daily || 0))}
              </div>
              <div style={{ color: '#666', fontSize: 13, marginTop: 4 }}>
                Nível de risco: {safeToSpend.risk_level || 'LOW'}
              </div>
            </div>
          </div>
        </div>

        <div style={cardStyle}>
          <div style={titleStyle}>Ritmo de Gastos no Mês</div>
          <div style={{ color: '#666', fontSize: 13, marginBottom: 6 }}>
            Dia {dayOfMonth} de {daysInMonth} ({(monthProgress * 100).toFixed(0)}% do mês)
          </div>
          <div style={{ color: '#444', fontSize: 13, marginBottom: 4 }}>
            Esperado até hoje: {currency(expectedSpendToDate)}
          </div>
          <div style={{ color: '#444', fontSize: 13, marginBottom: 10 }}>
            Gasto real até hoje: {currency(spentToDate)}
          </div>
          <div style={{ height: 12, width: '100%', background: '#f4f6f9', borderRadius: 999, overflow: 'hidden' }}>
            <div
              style={{
                height: '100%',
                width: `${Math.min(160, Math.max(0, pacePct))}%`,
                background: paceColor,
              }}
            />
          </div>
          <div style={{ marginTop: 8, fontSize: 13, color: '#666' }}>Ritmo atual: {pacePct.toFixed(0)}%</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
        <div style={cardStyle}>
          <div style={titleStyle}>Categorias (Mais estouradas primeiro)</div>
          {categoryBreakdown.length === 0 && <div style={{ color: '#777' }}>Sem dados de categorias no período.</div>}
          {categoryBreakdown.map((row: any) => {
            const pct = Math.max(0, row.pct);
            const width = Math.min(100, pct);
            const color = getCategoryColor(pct);

            return (
              <div key={row.category} style={{ marginBottom: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <div style={{ fontSize: 13, color: '#1a1a2e', fontWeight: 600 }}>{row.category}</div>
                  <div style={{ fontSize: 12, color: '#6b7280' }}>{pct.toFixed(0)}%</div>
                </div>
                <div style={{ height: 8, borderRadius: 99, background: '#f4f6f9', overflow: 'hidden' }}>
                  <div style={{ width: `${width}%`, height: '100%', background: color }} />
                </div>
                <div style={{ fontSize: 12, color: '#6b7280', marginTop: 3 }}>
                  {currency(row.spent)} de {currency(row.budget)}
                </div>
              </div>
            );
          })}
        </div>

        <div style={cardStyle}>
          <div style={titleStyle}>Gastos Diários (últimos 14 dias)</div>
          {dailySpendWithColor.length === 0 && <div style={{ color: '#777' }}>Sem transações de débito para o gráfico.</div>}
          {dailySpendWithColor.length > 0 && (
            <div style={{ height: 240 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={dailySpendWithColor}>
                  <XAxis dataKey="date" fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis fontSize={11} tickLine={false} axisLine={false} width={44} />
                  <Tooltip
                    formatter={(value) => currency(Number(value || 0))}
                    labelFormatter={(label) => `Data: ${label}`}
                  />
                  <Bar dataKey="total" radius={[4, 4, 0, 0]}>
                    {dailySpendWithColor.map((entry, idx) => (
                      <Cell key={`cell-${entry.date}-${idx}`} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
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
          <div style={titleStyle}>Agenda Financeira</div>
          {agendaItems.length === 0 && (
            <div style={{ color: '#777', fontSize: 14 }}>
              Sem compromissos futuros detectados no momento.
            </div>
          )}
          {agendaItems.map((item: any, idx: number) => {
            const urgency = getUrgencyMeta(item.daysUntil);
            return (
              <div
                key={`${item.description}-${item.dueDate}-${idx}`}
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'auto 1fr auto',
                  gap: 10,
                  alignItems: 'center',
                  borderBottom: '1px solid #f2f2f2',
                  padding: '9px 0',
                }}
              >
                <div
                  style={{
                    width: 22,
                    height: 22,
                    borderRadius: 999,
                    background: `${urgency.color}20`,
                    color: urgency.color,
                    fontSize: 11,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 700,
                  }}
                >
                  {urgency.icon}
                </div>
                <div>
                  <div style={{ fontSize: 13, color: '#1a1a2e', fontWeight: 600 }}>{item.description}</div>
                  <div style={{ fontSize: 12, color: urgency.color, marginTop: 2 }}>{urgency.label}</div>
                </div>
                <div style={{ fontSize: 13, color: '#444', fontWeight: 600 }}>{currency(item.amount)}</div>
              </div>
            );
          })}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
        <div style={cardStyle}>
          <div style={titleStyle}>Alertas Ativos</div>
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 14, color: '#444', marginBottom: 6 }}>Alertas ativos: {alerts.length}</div>
            {(alerts || []).slice(0, 3).map((alert: any) => (
              <div key={alert.id || alert.title} style={{ fontSize: 13, color: '#666', marginBottom: 5 }}>
                • {alert.title || alert.type || 'Alerta'}
              </div>
            ))}
            {alerts.length === 0 && <div style={{ color: '#777', fontSize: 14 }}>Nenhum alerta no momento.</div>}
          </div>
        </div>

        <div style={cardStyle}>
          <div style={titleStyle}>Assinaturas Ativas</div>
          <div style={{ fontSize: 14, color: '#444', marginBottom: 6 }}>
            Assinaturas: {subscriptionsQuery.data?.total_subscriptions || subscriptions.length}
          </div>
          <div style={{ fontSize: 14, color: '#444', marginBottom: 8 }}>
            Custo mensal: {currency(subscriptionsQuery.data?.total_monthly_cost || 0)}
          </div>
          {subscriptions.slice(0, 4).map((sub: any, idx: number) => (
            <div
              key={`${sub.merchant || sub.name || 'sub'}-${idx}`}
              style={{
                display: 'grid',
                gridTemplateColumns: 'auto 1fr auto',
                gap: 10,
                alignItems: 'center',
                borderBottom: '1px solid #f2f2f2',
                padding: '8px 0',
              }}
            >
              <div
                style={{
                  width: 26,
                  height: 26,
                  borderRadius: 8,
                  background: '#eef4ff',
                  color: '#0978F6',
                  fontSize: 11,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 700,
                }}
              >
                S
              </div>
              <div>
                <div style={{ fontSize: 13, color: '#1a1a2e', fontWeight: 600 }}>
                  {sub.merchant || sub.name || 'Assinatura'}
                </div>
                <div style={{ fontSize: 12, color: '#6b7280' }}>
                  {(sub.subscription_category || sub.category || 'serviço').toString().replaceAll('_', ' ')}
                </div>
              </div>
              <div style={{ fontSize: 13, color: '#444', fontWeight: 600 }}>
                {currency(Number(sub.monthly_amount || sub.amount || 0))}
              </div>
            </div>
          ))}
          {subscriptions.length === 0 && (
            <div style={{ color: '#777', fontSize: 14 }}>Nenhuma assinatura detectada.</div>
          )}
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
