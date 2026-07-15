import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { nexaApi } from '../api/nexa';

/**
 * OPP — Card do Radar de Oportunidades (docs/OPP.md, Etapa 6).
 *
 * Mostra o dinheiro parado detectado, o custo de não investir (R$/ano em
 * destaque), a melhor alternativa do ranking líquido pós-IR e os passos
 * práticos da troca (OPP.5). Inclui o comparativo poupança vs. CDI (OPP.4)
 * quando relevante e o disclaimer regulatório obrigatório.
 */

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

const badgeStyle = (bg: string, fg: string): React.CSSProperties => ({
  display: 'inline-block',
  fontSize: 11,
  fontWeight: 600,
  padding: '2px 8px',
  borderRadius: 999,
  background: bg,
  color: fg,
});

function currency(value: number) {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value || 0);
}

const STATUS_BADGES: Record<string, { label: string; bg: string; fg: string }> = {
  CONFIRMED: { label: 'Confirmado (30 dias)', bg: '#dcfce7', fg: '#166534' },
  PRELIMINARY: { label: 'Estimativa preliminar', bg: '#fef9c3', fg: '#854d0e' },
  NO_IDLE_MONEY: { label: 'Sem dinheiro parado', bg: '#e0f2fe', fg: '#075985' },
  NO_DATA: { label: 'Dados insuficientes', bg: '#f3f4f6', fg: '#4b5563' },
};

export const OpportunityRadarCard: React.FC<{ userId: string }> = ({ userId }) => {
  const [showSteps, setShowSteps] = useState(false);

  const oppQuery = useQuery({
    queryKey: ['opportunities', userId],
    queryFn: () => nexaApi.getOpportunities(userId),
    enabled: !!userId,
    staleTime: 30 * 60 * 1000,
  });

  const savingsQuery = useQuery({
    queryKey: ['savings-vs-cdi'],
    queryFn: () => nexaApi.getSavingsVsCdi(),
    staleTime: 60 * 60 * 1000,
  });

  if (oppQuery.isLoading) {
    return (
      <div style={cardStyle}>
        <div style={titleStyle}>Radar de Oportunidades</div>
        <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>Analisando seu dinheiro parado…</div>
      </div>
    );
  }

  if (oppQuery.isError || !oppQuery.data) {
    return null; // sem dados suficientes — não polui o feed com um card vazio
  }

  const opp = oppQuery.data;
  const top = opp.top_opportunity;
  const status = STATUS_BADGES[opp.idle_detection_status] || STATUS_BADGES.NO_DATA;
  const annualLoss = Number(opp.monthly_loss_in_checking || 0) * 12;
  const savings = savingsQuery.data;
  const showSavings = savings && savings.status === 'BELOW_CDI' && savings.severity !== 'LOW';

  return (
    <div style={cardStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <div style={titleStyle}>Radar de Oportunidades</div>
        <span style={badgeStyle(status.bg, status.fg)}>{status.label}</span>
      </div>

      {opp.idle_amount > 0 ? (
        <>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{currency(opp.idle_amount)} parados</div>
          <div style={{ color: '#b91c1c', fontSize: 14, fontWeight: 600, marginTop: 4 }}>
            −{currency(annualLoss)}/ano deixando na conta corrente
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
            {opp.idle_source === 'REAL_BALANCE'
              ? '🔗 Baseado no saldo real das suas contas conectadas'
              : 'Estimado a partir do seu histórico de transações'}
          </div>

          {top && (
            <div
              style={{
                marginTop: 12,
                padding: 12,
                borderRadius: 10,
                background: 'var(--bg-hover)',
                border: '1px solid var(--border-color)',
              }}
            >
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>
                Melhor alternativa (líquido pós-IR)
              </div>
              <div style={{ fontWeight: 600, fontSize: 14 }}>
                {top.bank_name} {top.product_type} {Number(top.cdi_pct).toFixed(0)}% CDI
                {top.is_exempt ? ' · isento de IR' : ''}
                {top.fgc_covered === false ? ' · garantia do Tesouro' : ' · FGC até R$250k'}
              </div>
              <div style={{ color: '#166534', fontWeight: 700, fontSize: 16, marginTop: 4 }}>
                +{currency(top.annual_gain_brl)}/ano ({Number(top.annual_rate_net_pct).toFixed(2)}% a.a. líquido)
              </div>

              {Array.isArray(top.steps) && top.steps.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <button
                    onClick={() => setShowSteps((v) => !v)}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: 'var(--accent-color, #0762C7)',
                      fontSize: 13,
                      fontWeight: 600,
                      cursor: 'pointer',
                      padding: 0,
                    }}
                  >
                    {showSteps ? 'Ocultar passo a passo ▲' : 'Como fazer a troca ▼'}
                  </button>
                  {showSteps && (
                    <ol style={{ margin: '8px 0 0', paddingLeft: 18, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                      {top.steps.map((step: string, i: number) => (
                        <li key={i}>{step}</li>
                      ))}
                    </ol>
                  )}
                </div>
              )}
            </div>
          )}
        </>
      ) : (
        <div style={{ color: 'var(--text-secondary)', fontSize: 14, lineHeight: 1.6 }}>
          {opp.recommendation}
        </div>
      )}

      {showSavings && (
        <div
          style={{
            marginTop: 12,
            padding: 10,
            borderRadius: 10,
            background: '#fff7ed',
            border: '1px solid #fed7aa',
            fontSize: 13,
            color: '#9a3412',
          }}
        >
          🐷 Poupança hoje rende {Number(savings.savings_annual_pct).toFixed(2)}% a.a. contra{' '}
          {Number(savings.cdi_annual_pct).toFixed(2)}% do CDI — {currency(savings.estimated_loss_annual_brl)}
          /ano de diferença a cada {currency(savings.amount_reference_brl)}.
        </div>
      )}

      {opp.emergency_reserve > 0 && (
        <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-muted)' }}>
          🛡️ {currency(opp.emergency_reserve)} protegidos como reserva de emergência (
          {opp.reserve_months_applied} meses de gastos) — fora da recomendação.
        </div>
      )}

      {opp.disclaimer && (
        <div style={{ marginTop: 10, fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.5 }}>
          {opp.disclaimer}
        </div>
      )}
    </div>
  );
};
