import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AppShell } from '../components/layout/AppShell';
import { nexaApi } from '../api/nexa';
import type { GoalType, GoalStatus } from '../api/types';

const cardStyle: React.CSSProperties = {
  background: 'var(--bg-surface)',
  border: '1px solid var(--border-color)',
  borderRadius: 12,
  padding: 18,
  boxShadow: '0 1px 2px rgba(0, 0, 0, 0.04)',
};

const titleStyle: React.CSSProperties = {
  fontSize: 11,
  letterSpacing: 0.8,
  textTransform: 'uppercase',
  color: 'var(--text-muted)',
  marginBottom: 8,
  fontWeight: 600,
};

const buttonStyle: React.CSSProperties = {
  padding: '10px 16px',
  borderRadius: 8,
  border: 'none',
  fontSize: 14,
  fontWeight: 600,
  cursor: 'pointer',
  transition: 'all 0.2s',
};

const primaryButtonStyle: React.CSSProperties = {
  ...buttonStyle,
  background: '#0978F6',
  color: 'white',
};

const secondaryButtonStyle: React.CSSProperties = {
  ...buttonStyle,
  background: 'var(--bg-hover)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-color)',
};

const dangerButtonStyle: React.CSSProperties = {
  ...buttonStyle,
  background: '#fee',
  color: '#b91c1c',
  border: '1px solid #fecaca',
};

function currency(value: number) {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value || 0);
}

const goalTypeLabels: Record<GoalType, { icon: string; label: string }> = {
  imovel: { icon: '🏠', label: 'Imóvel' },
  viagem: { icon: '✈️', label: 'Viagem' },
  carro: { icon: '🚗', label: 'Carro' },
  educacao: { icon: '🎓', label: 'Educação' },
  emergencia: { icon: '🆘', label: 'Emergência' },
  outros: { icon: '🎯', label: 'Outros' },
};

const feasibilityConfig = {
  EASY: { label: 'Fácil', color: '#10b981' },
  MODERATE: { label: 'Moderada', color: '#0978F6' },
  HARD: { label: 'Difícil', color: '#F39C12' },
  UNREALISTIC: { label: 'Irrealista', color: '#E74C3C' },
};

export const GoalsPage: React.FC = () => {
  const userId = localStorage.getItem('user_id') || '';
  const queryClient = useQueryClient();

  const [statusFilter, setStatusFilter] = useState<GoalStatus>('ACTIVE');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [selectedGoal, setSelectedGoal] = useState<string | null>(null);
  const [showProgressModal, setShowProgressModal] = useState(false);

  // Form states
  const [formData, setFormData] = useState({
    name: '',
    goal_type: 'outros' as GoalType,
    target_amount: '',
    current_amount: '',
    target_date: '',
  });

  const [progressAmount, setProgressAmount] = useState('');

  const goalsQuery = useQuery({
    queryKey: ['goals', userId, statusFilter],
    queryFn: () => nexaApi.getGoals(userId, statusFilter),
    enabled: !!userId,
  });

  const createMutation = useMutation({
    mutationFn: (data: typeof formData) =>
      nexaApi.createGoal(userId, {
        name: data.name,
        goal_type: data.goal_type,
        target_amount: Number(data.target_amount),
        current_amount: data.current_amount ? Number(data.current_amount) : 0,
        target_date: data.target_date || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals', userId] });
      setShowCreateModal(false);
      setFormData({
        name: '',
        goal_type: 'outros',
        target_amount: '',
        current_amount: '',
        target_date: '',
      });
    },
  });

  const updateProgressMutation = useMutation({
    mutationFn: ({ goalId, amount }: { goalId: string; amount: number }) =>
      nexaApi.updateGoalProgress(userId, goalId, { amount_to_add: amount }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals', userId] });
      setShowProgressModal(false);
      setSelectedGoal(null);
      setProgressAmount('');
    },
  });

  const abandonMutation = useMutation({
    mutationFn: (goalId: string) => nexaApi.abandonGoal(userId, goalId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals', userId] });
    },
  });

  const goals = goalsQuery.data?.goals || [];

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.target_amount) return;
    createMutation.mutate(formData);
  };

  const handleProgressSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedGoal || !progressAmount) return;
    updateProgressMutation.mutate({
      goalId: selectedGoal,
      amount: Number(progressAmount),
    });
  };

  const handleAbandon = (goalId: string, goalName: string) => {
    if (confirm(`Tem certeza que deseja abandonar a meta "${goalName}"?`)) {
      abandonMutation.mutate(goalId);
    }
  };

  return (
    <AppShell
      current="goals"
      title="Metas Financeiras"
      subtitle="Gerencie suas metas e acompanhe seu progresso"
    >
      {/* Header com filtros e botão de criar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 8 }}>
          {(['ACTIVE', 'COMPLETED', 'ABANDONED'] as GoalStatus[]).map((status) => (
            <button
              key={status}
              onClick={() => setStatusFilter(status)}
              style={{
                ...buttonStyle,
                background: statusFilter === status ? '#0978F6' : 'var(--bg-hover)',
                color: statusFilter === status ? 'white' : 'var(--text-primary)',
                border: statusFilter === status ? 'none' : '1px solid var(--border-color)',
              }}
            >
              {status === 'ACTIVE' ? 'Ativas' : status === 'COMPLETED' ? 'Concluídas' : 'Abandonadas'}
            </button>
          ))}
        </div>

        <button onClick={() => setShowCreateModal(true)} style={primaryButtonStyle}>
          + Nova Meta
        </button>
      </div>

      {/* Loading */}
      {goalsQuery.isLoading && (
        <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: 40 }}>
          Carregando metas...
        </div>
      )}

      {/* Empty state */}
      {!goalsQuery.isLoading && goals.length === 0 && (
        <div style={{ ...cardStyle, textAlign: 'center', padding: 60 }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🎯</div>
          <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 8, color: 'var(--text-primary)' }}>
            Nenhuma meta {statusFilter === 'ACTIVE' ? 'ativa' : statusFilter === 'COMPLETED' ? 'concluída' : 'abandonada'}
          </div>
          <div style={{ color: 'var(--text-muted)', marginBottom: 20 }}>
            {statusFilter === 'ACTIVE' && 'Comece criando uma nova meta financeira para acompanhar seus objetivos.'}
            {statusFilter === 'COMPLETED' && 'Você ainda não concluiu nenhuma meta.'}
            {statusFilter === 'ABANDONED' && 'Você não abandonou nenhuma meta.'}
          </div>
          {statusFilter === 'ACTIVE' && (
            <button onClick={() => setShowCreateModal(true)} style={primaryButtonStyle}>
              Criar Primeira Meta
            </button>
          )}
        </div>
      )}

      {/* Goals grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 16 }}>
        {goals.map((goal: any) => {
          const pct = goal.target_amount > 0 ? (goal.current_amount / goal.target_amount) * 100 : 0;
          const typeInfo = goalTypeLabels[goal.goal_type as GoalType] || goalTypeLabels.outros;
          const feasibility = goal.projection?.feasibility || 'MODERATE';
          const feasibilityInfo = feasibilityConfig[feasibility as keyof typeof feasibilityConfig];

          return (
            <div key={goal.goal_id} style={{ ...cardStyle, position: 'relative' }}>
              {/* Header */}
              <div style={{ display: 'flex', alignItems: 'start', gap: 12, marginBottom: 16 }}>
                <div
                  style={{
                    fontSize: 32,
                    width: 56,
                    height: 56,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: 'var(--bg-hover)',
                    borderRadius: 12,
                  }}
                >
                  {typeInfo.icon}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 4, color: 'var(--text-primary)' }}>
                    {goal.name}
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>{typeInfo.label}</div>
                </div>
              </div>

              {/* Progress bar */}
              <div style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Progresso</span>
                  <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
                    {pct.toFixed(1)}%
                  </span>
                </div>
                <div style={{ height: 10, background: 'var(--bg-hover)', borderRadius: 999, overflow: 'hidden' }}>
                  <div
                    style={{
                      width: `${Math.min(100, pct)}%`,
                      height: '100%',
                      background: `linear-gradient(90deg, #0978F6, #0762C7)`,
                      transition: 'width 0.3s ease',
                    }}
                  />
                </div>
              </div>

              {/* Values */}
              <div style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                  <div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>Acumulado</div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: '#10b981' }}>
                      {currency(goal.current_amount)}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>Meta</div>
                    <div style={{ fontSize: 16, fontWeight: 700 }}>{currency(goal.target_amount)}</div>
                  </div>
                </div>

                {goal.target_date && (
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    📅 Prazo: {new Date(goal.target_date).toLocaleDateString('pt-BR')}
                  </div>
                )}
              </div>

              {/* Projection info */}
              {goal.projection && statusFilter === 'ACTIVE' && (
                <div
                  style={{
                    background: 'var(--bg-hover)',
                    borderRadius: 8,
                    padding: 12,
                    marginBottom: 16,
                  }}
                >
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>PROJEÇÃO</div>
                  {goal.projection.months_to_complete && (
                    <div style={{ fontSize: 13, marginBottom: 4 }}>
                      ⏱️ {goal.projection.months_to_complete} meses para conclusão
                    </div>
                  )}
                  <div style={{ fontSize: 13, marginBottom: 4 }}>
                    💰 {currency(goal.projection.monthly_contribution_needed)}/mês necessários
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
                    <div
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: feasibilityInfo.color,
                      }}
                    />
                    <span style={{ fontSize: 12, fontWeight: 600, color: feasibilityInfo.color }}>
                      {feasibilityInfo.label}
                    </span>
                  </div>
                </div>
              )}

              {/* Alerts */}
              {goal.projection?.alerts && goal.projection.alerts.length > 0 && (
                <div
                  style={{
                    background: '#fffbeb',
                    border: '1px solid #fde68a',
                    borderRadius: 8,
                    padding: 10,
                    marginBottom: 16,
                  }}
                >
                  {goal.projection.alerts.slice(0, 2).map((alert: string, idx: number) => (
                    <div key={idx} style={{ fontSize: 12, color: '#92400e', marginBottom: 4 }}>
                      ⚠️ {alert}
                    </div>
                  ))}
                </div>
              )}

              {/* Actions */}
              {statusFilter === 'ACTIVE' && (
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    onClick={() => {
                      setSelectedGoal(goal.goal_id);
                      setShowProgressModal(true);
                    }}
                    style={{ ...secondaryButtonStyle, flex: 1 }}
                  >
                    💵 Adicionar Progresso
                  </button>
                  <button
                    onClick={() => handleAbandon(goal.goal_id, goal.name)}
                    style={dangerButtonStyle}
                    disabled={abandonMutation.isPending}
                  >
                    🗑️
                  </button>
                </div>
              )}

              {/* Status badge */}
              {statusFilter !== 'ACTIVE' && (
                <div
                  style={{
                    position: 'absolute',
                    top: 12,
                    right: 12,
                    padding: '4px 10px',
                    borderRadius: 6,
                    fontSize: 11,
                    fontWeight: 600,
                    background: statusFilter === 'COMPLETED' ? '#d1fae5' : '#fee',
                    color: statusFilter === 'COMPLETED' ? '#065f46' : '#991b1b',
                  }}
                >
                  {statusFilter === 'COMPLETED' ? '✓ Concluída' : '✗ Abandonada'}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Create Modal */}
      {showCreateModal && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setShowCreateModal(false)}
        >
          <div
            style={{
              background: 'white',
              borderRadius: 16,
              padding: 24,
              width: '90%',
              maxWidth: 500,
              maxHeight: '90vh',
              overflow: 'auto',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 20 }}>Nova Meta Financeira</h2>

            <form onSubmit={handleCreateSubmit}>
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                  Nome da Meta *
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="Ex: Casa própria, Viagem para Europa..."
                  required
                  style={{
                    width: '100%',
                    padding: 10,
                    borderRadius: 8,
                    border: '1px solid var(--border-color)',
                    fontSize: 14,
                  }}
                />
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                  Tipo de Meta
                </label>
                <select
                  value={formData.goal_type}
                  onChange={(e) => setFormData({ ...formData, goal_type: e.target.value as GoalType })}
                  style={{
                    width: '100%',
                    padding: 10,
                    borderRadius: 8,
                    border: '1px solid var(--border-color)',
                    fontSize: 14,
                  }}
                >
                  {Object.entries(goalTypeLabels).map(([key, { icon, label }]) => (
                    <option key={key} value={key}>
                      {icon} {label}
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                  Valor da Meta (R$) *
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={formData.target_amount}
                  onChange={(e) => setFormData({ ...formData, target_amount: e.target.value })}
                  placeholder="Valor alvo da meta"
                  required
                  style={{
                    width: '100%',
                    padding: 10,
                    borderRadius: 8,
                    border: '1px solid var(--border-color)',
                    fontSize: 14,
                  }}
                />
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                  Valor Já Acumulado (R$)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={formData.current_amount}
                  onChange={(e) => setFormData({ ...formData, current_amount: e.target.value })}
                  placeholder="0.00"
                  style={{
                    width: '100%',
                    padding: 10,
                    borderRadius: 8,
                    border: '1px solid var(--border-color)',
                    fontSize: 14,
                  }}
                />
              </div>

              <div style={{ marginBottom: 20 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                  Data Alvo (opcional)
                </label>
                <input
                  type="date"
                  value={formData.target_date}
                  onChange={(e) => setFormData({ ...formData, target_date: e.target.value })}
                  min={new Date().toISOString().split('T')[0]}
                  style={{
                    width: '100%',
                    padding: 10,
                    borderRadius: 8,
                    border: '1px solid var(--border-color)',
                    fontSize: 14,
                  }}
                />
              </div>

              <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  style={secondaryButtonStyle}
                  disabled={createMutation.isPending}
                >
                  Cancelar
                </button>
                <button type="submit" style={primaryButtonStyle} disabled={createMutation.isPending}>
                  {createMutation.isPending ? 'Criando...' : 'Criar Meta'}
                </button>
              </div>

              {createMutation.isError && (
                <div style={{ marginTop: 12, padding: 10, background: '#fee', borderRadius: 8, color: '#b91c1c', fontSize: 13 }}>
                  Erro ao criar meta. Tente novamente.
                </div>
              )}
            </form>
          </div>
        </div>
      )}

      {/* Progress Modal */}
      {showProgressModal && selectedGoal && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => {
            setShowProgressModal(false);
            setSelectedGoal(null);
            setProgressAmount('');
          }}
        >
          <div
            style={{
              background: 'white',
              borderRadius: 16,
              padding: 24,
              width: '90%',
              maxWidth: 400,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 20 }}>Adicionar Progresso</h2>

            <form onSubmit={handleProgressSubmit}>
              <div style={{ marginBottom: 20 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                  Valor a Adicionar (R$) *
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={progressAmount}
                  onChange={(e) => setProgressAmount(e.target.value)}
                  placeholder="500.00"
                  required
                  autoFocus
                  style={{
                    width: '100%',
                    padding: 12,
                    borderRadius: 8,
                    border: '1px solid var(--border-color)',
                    fontSize: 16,
                  }}
                />
              </div>

              <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  onClick={() => {
                    setShowProgressModal(false);
                    setSelectedGoal(null);
                    setProgressAmount('');
                  }}
                  style={secondaryButtonStyle}
                  disabled={updateProgressMutation.isPending}
                >
                  Cancelar
                </button>
                <button type="submit" style={primaryButtonStyle} disabled={updateProgressMutation.isPending}>
                  {updateProgressMutation.isPending ? 'Salvando...' : 'Adicionar'}
                </button>
              </div>

              {updateProgressMutation.isError && (
                <div style={{ marginTop: 12, padding: 10, background: '#fee', borderRadius: 8, color: '#b91c1c', fontSize: 13 }}>
                  Erro ao atualizar progresso. Tente novamente.
                </div>
              )}
            </form>
          </div>
        </div>
      )}
    </AppShell>
  );
};
