import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AppShell } from '../components/layout/AppShell';
import { organizarApi, amanhaISO } from '../api/organizar';
import type { Meta, TipoMeta, StatusMeta } from '../api/organizar';
import { brl, dataLonga } from '../api/painel';
import { getErrorMessage } from '../api/errors';
import { getUserId } from '../api/session';

type GoalType = TipoMeta;
type GoalStatus = StatusMeta;

const cardStyle: React.CSSProperties = {
  background: 'var(--bg-surface)',
  border: '1px solid var(--border-color)',
  borderRadius: 12,
  padding: 18,
  boxShadow: '0 1px 2px rgba(0, 0, 0, 0.04)',
};

// titleStyle removed (unused); DashboardPage provides common title styling

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

const currency = (value: number | null | undefined) => brl(value || 0);

/** Número digitado no padrão brasileiro ("1.234,56") ou com ponto ("1234.56"). */
function lerValor(txt: string): number {
  const t = txt.trim();
  if (!t) return NaN;
  const normal = t.includes(',') ? t.replace(/\./g, '').replace(',', '.') : t;
  return Number(normal);
}

const goalTypeLabels: Record<GoalType, { icon: string; label: string }> = {
  imovel: { icon: '🏠', label: 'Imóvel' },
  viagem: { icon: '✈️', label: 'Viagem' },
  carro: { icon: '🚗', label: 'Carro' },
  educacao: { icon: '🎓', label: 'Educação' },
  emergencia: { icon: '🆘', label: 'Emergência' },
  outros: { icon: '🎯', label: 'Outros' },
};

// SEM_DADOS: ainda não há ritmo de aporte registrado — antes a página caía num
// "Moderada" que ninguém calculou.
const feasibilityConfig = {
  EASY: { label: 'Fácil', color: '#10b981' },
  MODERATE: { label: 'Moderada', color: '#0978F6' },
  HARD: { label: 'Difícil', color: '#F39C12' },
  UNREALISTIC: { label: 'Irrealista', color: '#E74C3C' },
  SEM_DADOS: { label: 'Sem ritmo registrado', color: '#94a3b8' },
};

export const GoalsPage: React.FC = () => {
  const userId = getUserId();
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
  const [monthlyRhythm, setMonthlyRhythm] = useState('');
  const [abandonError, setAbandonError] = useState<string | null>(null);

  const goalsQuery = useQuery({
    queryKey: ['goals', userId, statusFilter],
    queryFn: () => organizarApi.metas(userId, statusFilter),
    enabled: !!userId,
  });

  const createMutation = useMutation({
    mutationFn: (data: typeof formData) =>
      organizarApi.criarMeta(userId, {
        name: data.name.trim(),
        goal_type: data.goal_type,
        target_amount: lerValor(data.target_amount),
        current_amount: data.current_amount ? lerValor(data.current_amount) : 0,
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
    mutationFn: ({ goalId, amount, rhythm }: { goalId: string; amount: number; rhythm?: number }) =>
      organizarApi.aportar(userId, goalId, amount, rhythm),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals', userId] });
      queryClient.invalidateQueries({ queryKey: ['metas', userId] });
      fecharAporte();
    },
  });

  const abandonMutation = useMutation({
    mutationFn: (goalId: string) => organizarApi.abandonar(userId, goalId),
    onMutate: () => setAbandonError(null),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals', userId] });
      queryClient.invalidateQueries({ queryKey: ['metas', userId] });
    },
    // antes a falha era silenciosa: o card continuava ali e nada dizia por quê
    onError: (err) => setAbandonError(getErrorMessage(err, 'Não foi possível encerrar a meta.')),
  });

  const goals: Meta[] = goalsQuery.data?.goals || [];

  function fecharAporte() {
    setShowProgressModal(false);
    setSelectedGoal(null);
    setProgressAmount('');
    setMonthlyRhythm('');
  }

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name.trim() || !(lerValor(formData.target_amount) > 0)) return;
    createMutation.mutate(formData);
  };

  const handleProgressSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const amount = lerValor(progressAmount);
    if (!selectedGoal || !(amount > 0)) return;
    const rhythm = lerValor(monthlyRhythm);
    updateProgressMutation.mutate({
      goalId: selectedGoal,
      amount,
      rhythm: rhythm > 0 ? rhythm : undefined,
    });
  };

  const handleAbandon = (goalId: string, goalName: string) => {
    if (confirm(`Encerrar a meta "${goalName}"? Ela vai para "Abandonadas" e sai das projeções.`)) {
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

      {goalsQuery.isError && (
        <div style={{ ...cardStyle, color: '#b91c1c', marginBottom: 16 }}>
          {getErrorMessage(goalsQuery.error, 'Não foi possível carregar suas metas.')}{' '}
          <button onClick={() => goalsQuery.refetch()} style={{ ...secondaryButtonStyle, padding: '4px 10px', marginLeft: 8 }}>
            Tentar de novo
          </button>
        </div>
      )}
      {abandonError && (
        <div style={{ ...cardStyle, color: '#b91c1c', marginBottom: 16 }}>{abandonError}</div>
      )}

      {/* Empty state — só quando a lista veio e está vazia (erro não é "nenhuma meta") */}
      {goalsQuery.isSuccess && goals.length === 0 && (
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
        {goals.map((goal) => {
          const pct = goal.progress_pct ?? (goal.target_amount > 0 ? (goal.current_amount / goal.target_amount) * 100 : 0);
          const typeInfo = goalTypeLabels[goal.goal_type] || goalTypeLabels.outros;
          const feasibilityInfo = goal.projection ? feasibilityConfig[goal.projection.feasibility] : null;

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
                    {pct.toFixed(1).replace('.', ',')}%
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
                    📅 Prazo: {dataLonga(goal.target_date)}
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
                  {goal.projection.months_to_complete != null && goal.projection.months_to_complete > 0 && (
                    <div style={{ fontSize: 13, marginBottom: 4 }}>
                      ⏱️ {goal.projection.months_to_complete} {goal.projection.months_to_complete === 1 ? 'mês' : 'meses'} para conclusão no ritmo atual
                    </div>
                  )}
                  {goal.projection.monthly_contribution_needed > 0 && (
                    <div style={{ fontSize: 13, marginBottom: 4 }}>
                      💰 {currency(goal.projection.monthly_contribution_needed)}/mês necessários
                    </div>
                  )}
                  {goal.projection.current_monthly_actual > 0 && (
                    <div style={{ fontSize: 13, marginBottom: 4 }}>
                      📈 Você aporta {currency(goal.projection.current_monthly_actual)}/mês
                    </div>
                  )}
                  {feasibilityInfo && <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
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
                  </div>}
                  {goal.projection.suggestion && (
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8 }}>{goal.projection.suggestion}</div>
                  )}
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
                  {goal.projection.alerts.slice(0, 2).map((alert, idx) => (
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
                    💵 Registrar aporte
                  </button>
                  <button
                    onClick={() => handleAbandon(goal.goal_id, goal.name)}
                    style={dangerButtonStyle}
                    disabled={abandonMutation.isPending}
                    title="Encerrar meta"
                    aria-label={`Encerrar a meta ${goal.name}`}
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
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-color)',
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
                  type="text"
                  inputMode="decimal"
                  value={formData.target_amount}
                  onChange={(e) => setFormData({ ...formData, target_amount: e.target.value })}
                  placeholder="Ex.: 25.000,00"
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
                  type="text"
                  inputMode="decimal"
                  value={formData.current_amount}
                  onChange={(e) => setFormData({ ...formData, current_amount: e.target.value })}
                  placeholder="0,00"
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
                  min={amanhaISO()}
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
                  {getErrorMessage(createMutation.error, 'Erro ao criar meta. Tente novamente.')}
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
          onClick={fecharAporte}
        >
          <div
            style={{
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-color)',
              borderRadius: 16,
              padding: 24,
              width: '90%',
              maxWidth: 400,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 20 }}>Registrar aporte</h2>

            <form onSubmit={handleProgressSubmit}>
              <div style={{ marginBottom: 20 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                  Valor a Adicionar (R$) *
                </label>
                <input
                  type="text"
                  inputMode="decimal"
                  value={progressAmount}
                  onChange={(e) => setProgressAmount(e.target.value)}
                  placeholder="500,00"
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

              {/* Sem o ritmo mensal a projeção não tem como dizer quando a meta
                  fecha — é o que deixa a viabilidade em "Sem ritmo registrado". */}
              <div style={{ marginBottom: 20 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                  Quanto você costuma guardar por mês para ela? (opcional)
                </label>
                <input
                  type="text"
                  inputMode="decimal"
                  value={monthlyRhythm}
                  onChange={(e) => setMonthlyRhythm(e.target.value)}
                  placeholder="Ex.: 300,00"
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
                  onClick={fecharAporte}
                  style={secondaryButtonStyle}
                  disabled={updateProgressMutation.isPending}
                >
                  Cancelar
                </button>
                <button type="submit" style={primaryButtonStyle} disabled={updateProgressMutation.isPending}>
                  {updateProgressMutation.isPending ? 'Salvando...' : 'Registrar'}
                </button>
              </div>

              {updateProgressMutation.isError && (
                <div style={{ marginTop: 12, padding: 10, background: '#fee', borderRadius: 8, color: '#b91c1c', fontSize: 13 }}>
                  {getErrorMessage(updateProgressMutation.error, 'Erro ao registrar o aporte. Tente novamente.')}
                </div>
              )}
            </form>
          </div>
        </div>
      )}
    </AppShell>
  );
};
