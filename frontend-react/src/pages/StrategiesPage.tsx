import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { Markdown } from '../components/Markdown';
import { painelApi, brl, dataCurta, dataLonga } from '../api/painel';
import {
  estrategiasApi, ROTULO_CANAL, ROTULO_ESTRATEGIA, ROTULO_EVENTO, ROTULO_RECOMENDACAO, ROTULO_VEREDICTO,
} from '../api/estrategias';
import type { Estrategia, PerfilDeRisco, ResultadoNegociacao, TipoDeBem } from '../api/estrategias';
import { describeError } from '../api/errors';
import { getUserId } from '../api/session';

const card: React.CSSProperties = {
  background: 'var(--bg-surface)',
  border: '1px solid var(--border-color)',
  borderRadius: 12,
  padding: 16,
};
const sectionTitle: React.CSSProperties = { marginBottom: 10, fontWeight: 600, fontSize: 15, color: 'var(--text-primary)' };
const metricLabel: React.CSSProperties = { fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 };
const metricValue: React.CSSProperties = { fontSize: 20, color: 'var(--text-primary)', fontWeight: 700 };
const box: React.CSSProperties = { border: '1px solid var(--border-color)', borderRadius: 10, padding: 10 };
const grid = (min: number): React.CSSProperties => ({ display: 'grid', gridTemplateColumns: `repeat(auto-fit, minmax(${min}px, 1fr))`, gap: 10 });
const input: React.CSSProperties = { border: '1px solid var(--border-color)', borderRadius: 8, padding: 8 };
const botao: React.CSSProperties = { border: '1px solid #111', background: 'var(--text-primary)', color: 'var(--bg-surface)', borderRadius: 8, padding: '8px 12px', cursor: 'pointer' };
const botaoSec: React.CSSProperties = { border: '1px solid var(--border-color)', background: 'var(--bg-surface)', color: 'var(--text-primary)', borderRadius: 8, padding: '6px 10px', cursor: 'pointer', fontSize: 12 };
const nota: React.CSSProperties = { fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 };
const aviso: React.CSSProperties = { fontSize: 12, color: '#92400e' };

const pct = (v: number | null | undefined, casas = 1) => (v == null ? '—' : `${Number(v).toFixed(casas).replace('.', ',')}%`);
const lerValor = (t: string) => {
  const s = t.trim();
  return Number(s.includes(',') ? s.replace(/\./g, '').replace(',', '.') : s);
};

/** Erro em linguagem de gente; 402 vira convite para o plano, não "falha". */
function Erro({ erro, fallback }: { erro: unknown; fallback: string }) {
  const e = describeError(erro, fallback);
  return (
    <div style={{ fontSize: 12, color: '#991b1b', margin: '6px 0' }}>
      {e.message}
      {e.kind === 'upgrade_required' && <> · <Link to="/planos">Ver planos</Link></>}
    </div>
  );
}

function Metrica({ rotulo, valor, sub }: { rotulo: string; valor: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div style={box}>
      <div style={metricLabel}>{rotulo}</div>
      <div style={metricValue}>{valor}</div>
      {sub && <div style={{ ...nota, marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
const ROTULO_TARIFA: Record<string, string> = {
  JUROS_ROTATIVO: 'Juros do rotativo', ANUIDADE_CARTAO: 'Anuidade do cartão', SEGURO_PRESTAMISTA: 'Seguro prestamista',
  PACOTE_SERVICOS: 'Pacote de serviços', TED_DOC: 'TED/DOC', SAQUE: 'Saque', CHEQUE_ESPECIAL: 'Cheque especial', IOF: 'IOF',
};
const ROTULO_RESULTADO: Record<ResultadoNegociacao, string> = {
  sucesso: 'Funcionou', parcial: 'Em parte', recusado: 'Recusaram', nao_tentou: 'Não tentei',
};

type Aba = 'optimizer' | 'cards' | 'architect' | 'fiscal' | 'peers' | 'advanced';

export const StrategiesPage: React.FC = () => {
  const userId = getUserId();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Aba>('optimizer');

  const [rendaTexto, setRendaTexto] = useState('');
  const rendaInformada = lerValor(rendaTexto) > 0 ? lerValor(rendaTexto) : undefined;
  const [maxCards, setMaxCards] = useState(3);
  const [currentCard, setCurrentCard] = useState('');

  const [bem, setBem] = useState({ valor: '120000', entrada: '20000', meses: '48', tipo: 'VEICULO' as TipoDeBem, risco: 'moderado' as PerfilDeRisco });

  const [year, setYear] = useState(new Date().getFullYear());
  const [month, setMonth] = useState<number | ''>('');

  const [compra, setCompra] = useState({ valor: '3000', aVista: '', categoria: 'Eletrônicos', parcelas: 6 });
  const [autoParcelas, setAutoParcelas] = useState(true);
  const [banco, setBanco] = useState('');

  // Contexto do /forecast para TODAS as abas — só peers/advanced buscavam, e
  // a análise do Optimizer ia sem renda nem margem.
  const contextoQ = useQuery({
    queryKey: ['painel', 'previsao', userId],
    queryFn: () => painelApi.previsao(userId),
    enabled: !!userId, staleTime: 5 * 60 * 1000, retry: false,
  });
  const rendaEstimada = contextoQ.data?.financial_health?.income_profile?.monthly_net_income || undefined;
  const renda = rendaInformada ?? rendaEstimada;
  const margem = contextoQ.data?.safe_to_spend?.safe_to_spend_total;

  const ativo = (aba: Aba) => !!userId && tab === aba;

  // ── Optimizer ─────────────────────────────────────────────────────────────
  const carteiraQ = useQuery({
    queryKey: ['optimizer', 'carteira', userId, maxCards, rendaInformada ?? 'estimada'],
    queryFn: () => estrategiasApi.carteira(userId, maxCards, rendaInformada),
    enabled: ativo('optimizer'),
  });
  const cartoesQ = useQuery({ queryKey: ['optimizer', 'cartoes'], queryFn: estrategiasApi.cartoes, enabled: tab === 'optimizer', staleTime: Infinity });
  const promocoesQ = useQuery({ queryKey: ['optimizer', 'promocoes'], queryFn: estrategiasApi.promocoes, enabled: tab === 'optimizer' });
  const relatoriosQ = useQuery({ queryKey: ['optimizer', 'relatorios', userId], queryFn: () => estrategiasApi.relatorios(userId), enabled: ativo('optimizer') });
  const custoQ = useQuery({
    queryKey: ['optimizer', 'custo', userId, currentCard],
    queryFn: () => estrategiasApi.custoDeOportunidade(userId, currentCard, 3),
    enabled: ativo('optimizer') && !!currentCard,
  });
  const roiQ = useQuery({
    queryKey: ['optimizer', 'roi', userId, currentCard],
    queryFn: () => estrategiasApi.roi(userId, currentCard),
    enabled: ativo('optimizer') && !!currentCard,
  });
  const analiseM = useMutation({
    mutationFn: () => estrategiasApi.analisar(userId, currentCard || undefined, {
      ...(margem != null && margem >= 0 ? { safe_to_spend: margem } : {}),
      ...(renda ? { monthly_income: renda } : {}),
    }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['optimizer', 'relatorios', userId] }),
  });

  // ── Cartões e contas ──────────────────────────────────────────────────────
  const lancamentosQ = useQuery({
    queryKey: ['estrategias', 'lancamentos', userId],
    queryFn: () => painelApi.lancamentos(userId, 500, 0),
    enabled: ativo('cards'),
  });

  // ── Architect ─────────────────────────────────────────────────────────────
  const simularM = useMutation({
    mutationFn: () => estrategiasApi.simular({
      user_id: userId,
      target_amount: lerValor(bem.valor),
      down_payment: lerValor(bem.entrada) || 0,
      asset_type: bem.tipo,
      financing_months: Math.round(lerValor(bem.meses)) || 48,
      risk_profile: bem.risco,
      include_consortium: true,
      prefers_consortium: false,
    }),
    // histórico e métricas não eram invalidados: a simulação nova não aparecia
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['architect'] }),
  });
  const pendentesQ = useQuery({ queryKey: ['architect', 'pendentes', userId], queryFn: estrategiasApi.simulacoesPendentes, enabled: ativo('architect') });
  const responderSimM = useMutation({
    mutationFn: ({ id, seguiu, estrategia }: { id: string; seguiu: boolean; estrategia: Estrategia }) => estrategiasApi.responderSimulacao(id, seguiu, estrategia),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['architect', 'pendentes', userId] }),
  });
  const [respondidos, setRespondidos] = useState<Record<string, 'ACCEPTED' | 'REJECTED'>>({});
  const responderInsightM = useMutation({
    mutationFn: ({ reportId, insightId, r }: { reportId: string; insightId: string; r: 'ACCEPTED' | 'REJECTED' }) => estrategiasApi.responderInsight(reportId, insightId, r),
    onSuccess: (_d, v) => setRespondidos(prev => ({ ...prev, [v.insightId]: v.r })),
  });
  const simulacoesQ = useQuery({ queryKey: ['architect', 'simulacoes', userId], queryFn: () => estrategiasApi.simulacoes(userId, 8), enabled: ativo('architect') });
  const metricasQ = useQuery({ queryKey: ['architect', 'metricas', userId], queryFn: () => estrategiasApi.metricasArchitect(userId), enabled: ativo('architect') });

  // ── Fiscal ────────────────────────────────────────────────────────────────
  const mesParam = month === '' ? undefined : month;
  const fiscalQ = useQuery({ queryKey: ['fiscal', 'relatorio', userId, year, mesParam], queryFn: () => estrategiasApi.fiscal(userId, year, mesParam), enabled: ativo('fiscal') });
  const mistoQ = useQuery({ queryKey: ['fiscal', 'misto', userId, year, mesParam], queryFn: () => estrategiasApi.usoMisto(userId, year, mesParam), enabled: ativo('fiscal') });
  const corrigirM = useMutation({
    mutationFn: ({ id, ctx }: { id: string; ctx: 'PF' | 'PJ' }) => estrategiasApi.corrigirContexto(userId, id, ctx),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['fiscal'] }),
  });

  // ── Comparação ────────────────────────────────────────────────────────────
  const pares = useQuery({
    queryKey: ['peers', userId, rendaInformada ?? 'estimada'],
    queryFn: () => estrategiasApi.comparar(userId, rendaInformada),
    enabled: ativo('peers'),
  });

  // ── F5 · F7 · F13 ─────────────────────────────────────────────────────────
  const raioXQ = useQuery({ queryKey: ['costs', 'raio-x', userId], queryFn: () => estrategiasApi.raioX(userId), enabled: ativo('advanced') });
  const revisaoQ = useQuery({ queryKey: ['purchase', 'revisao', userId], queryFn: () => estrategiasApi.revisaoDeCompras(userId), enabled: ativo('advanced') });
  const historicoNegQ = useQuery({ queryKey: ['negotiator', 'historico', userId], queryFn: () => estrategiasApi.historicoDeNegociacao(userId), enabled: ativo('advanced') });

  const valorCompra = lerValor(compra.valor);
  const parcelasSugeridas = useMemo(() => {
    if (!(valorCompra > 0)) return 1;
    if (renda && renda > 0) {
      const pressao = valorCompra / renda;
      if (pressao <= 0.2) return 1;
      if (pressao <= 0.4) return 3;
      if (pressao <= 0.8) return 6;
      if (pressao <= 1.5) return 12;
      return 18;
    }
    if (valorCompra <= 500) return 1;
    if (valorCompra <= 2000) return 3;
    if (valorCompra <= 5000) return 6;
    if (valorCompra <= 15000) return 12;
    return 18;
  }, [valorCompra, renda]);
  const parcelas = autoParcelas ? parcelasSugeridas : compra.parcelas;

  const compraM = useMutation({
    mutationFn: () => estrategiasApi.analisarCompra({
      user_id: userId,
      amount: valorCompra,
      category: compra.categoria || 'Outros',
      installments: parcelas,
      ...(lerValor(compra.aVista) > 0 ? { cash_price: lerValor(compra.aVista) } : {}),
      // a margem que a tela mostra é a que a análise usa (antes: "indisponível")
      ...(margem != null && margem >= 0 ? { safe_to_spend: margem } : {}),
      ...(renda ? { monthly_income: renda } : {}),
    }),
  });
  const negociarM = useMutation({
    mutationFn: () => estrategiasApi.negociar(userId, banco.trim() || undefined),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['negotiator', 'historico', userId] }),
  });
  const resultadoM = useMutation({
    mutationFn: ({ id, r }: { id: string; r: ResultadoNegociacao }) => estrategiasApi.registrarResultado(id, r),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['negotiator', 'historico', userId] }),
  });

  const contas = useMemo(() => {
    const grupos = new Map<string, { id: string; n: number; gasto: number; entrada: number; ultima: string; cats: Record<string, number> }>();
    for (const t of lancamentosQ.data?.transactions || []) {
      const id = t.account_id || 'conta';
      const g = grupos.get(id) || { id, n: 0, gasto: 0, entrada: 0, ultima: '', cats: {} };
      g.n += 1;
      if (t.amount >= 0) g.entrada += t.amount; else g.gasto += -t.amount;
      const c = t.category || 'Outros';
      g.cats[c] = (g.cats[c] || 0) + Math.abs(t.amount);
      if (t.date > g.ultima) g.ultima = t.date;
      grupos.set(id, g);
    }
    return [...grupos.values()].sort((a, b) => b.n - a.n);
  }, [lancamentosQ.data]);

  const contextoTexto = contextoQ.isError
    ? 'contexto do extrato indisponível'
    : `renda ${renda ? brl(renda) : 'não detectada'}${rendaInformada ? ' (informada)' : rendaEstimada ? ' (estimada pelo extrato)' : ''} · margem segura do mês ${margem != null ? brl(margem) : '—'}`;

  const campoRenda = (
    <label style={{ display: 'grid', gap: 4, fontSize: 12, color: 'var(--text-muted)' }}>
      Renda mensal (opcional — sem ela usamos a estimada pelo extrato)
      <input value={rendaTexto} onChange={e => setRendaTexto(e.target.value)} inputMode="decimal"
        placeholder={rendaEstimada ? `estimada: ${brl(rendaEstimada, 0)}` : 'R$'} style={{ ...input, width: 220 }} />
    </label>
  );

  return (
    <AppShell current="strategies" title="Estratégias" subtitle="Cartões, grandes compras, MEI, comparação com pares e negociação com o banco.">
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        {([
          ['optimizer', 'Cartões ideais'],
          ['cards', 'Contas e cartões'],
          ['architect', 'Grande compra'],
          ['fiscal', 'MEI / Fiscal'],
          ['peers', 'Comparação'],
          ['advanced', 'Tarifas, compra e negociação'],
        ] as [Aba, string][]).map(([key, label]) => (
          <button key={key} onClick={() => setTab(key)} style={{
            border: '1px solid var(--border-color)', borderRadius: 8, padding: '8px 12px', cursor: 'pointer', fontSize: 13,
            background: tab === key ? 'var(--text-primary)' : 'var(--bg-surface)', color: tab === key ? 'var(--bg-surface)' : 'var(--text-primary)',
          }}>{label}</button>
        ))}
      </div>
      <div style={{ ...nota, marginBottom: 12 }}>Contexto usado: {contextoTexto}</div>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━ OPTIMIZER ━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      {tab === 'optimizer' && (
        <div style={{ display: 'grid', gap: 12 }}>
          <div style={card}>
            <div style={sectionTitle}>Carteira ideal de cartões</div>
            <div style={{ display: 'flex', gap: 12, marginBottom: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
              {campoRenda}
              <select value={maxCards} onChange={e => setMaxCards(Number(e.target.value))} style={input} aria-label="Máximo de cartões">
                {[1, 2, 3, 4].map(n => <option key={n} value={n}>até {n} {n > 1 ? 'cartões' : 'cartão'}</option>)}
              </select>
            </div>
            {carteiraQ.isLoading && <div style={nota}>Montando a carteira…</div>}
            {carteiraQ.isError && <Erro erro={carteiraQ.error} fallback="Não foi possível montar a carteira." />}
            {carteiraQ.data && (
              <>
                <div style={{ ...grid(170), marginBottom: 10 }}>
                  <Metrica rotulo="Retorno por ano" valor={brl(carteiraQ.data.total_annual_return)} />
                  <Metrica rotulo="Anuidades" valor={brl(carteiraQ.data.total_annuity_cost)} />
                  <Metrica rotulo="Ganho líquido por ano" valor={brl(carteiraQ.data.net_annual_gain)} />
                  <Metrica rotulo="vs. melhor cartão único" valor={brl(carteiraQ.data.vs_single_best)}
                    sub={carteiraQ.data.vs_single_best <= 0 ? 'um cartão só basta neste perfil' : 'a mais com a carteira'} />
                </div>
                {carteiraQ.data.cards.length === 0 && <div style={nota}>Nenhum cartão elegível rende neste perfil.</div>}
                <div style={{ display: 'grid', gap: 8 }}>
                  {carteiraQ.data.cards.map(c => (
                    <div key={c.card_id} style={{ ...box, display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto', gap: 10 }}>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 14 }}>{c.card_name} <span style={nota}>· {c.issuer}</span></div>
                        <div style={nota}>{c.reason}</div>
                        <div style={nota}>Use para: {c.assigned_categories.join(', ')} · {brl(c.monthly_spend_directed, 0)}/mês</div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: 14, fontWeight: 700 }}>{brl(c.net_annual)}/ano</div>
                        <div style={nota}>{c.effective_annuity > 0 ? `anuidade ${brl(c.effective_annuity, 0)}` : 'sem anuidade'}</div>
                      </div>
                    </div>
                  ))}
                </div>
                <div style={{ ...nota, marginTop: 8 }}>
                  Base: todo o gasto elegível passando pelo cartão indicado. A análise completa, abaixo, considera só a parte que você já gasta no crédito — por isso os valores diferem.
                </div>
              </>
            )}
          </div>

          <div style={grid(280)}>
            <div style={card}>
              <div style={sectionTitle}>Quanto o seu cartão atual deixa na mesa</div>
              <select value={currentCard} onChange={e => setCurrentCard(e.target.value)} style={{ ...input, width: '100%', marginBottom: 10 }} aria-label="Seu cartão atual">
                <option value="">Selecione seu cartão atual</option>
                {(cartoesQ.data?.cards || []).map(c => <option key={c.card_id} value={c.card_id}>{c.name} · {c.issuer}</option>)}
              </select>
              {!currentCard && <div style={nota}>Escolha o cartão que você usa hoje para comparar com as alternativas que você consegue contratar.</div>}
              {currentCard && (
                <div style={{ display: 'grid', gap: 8 }}>
                  {custoQ.isLoading && <div style={nota}>Calculando…</div>}
                  {custoQ.isError && <Erro erro={custoQ.error} fallback="Não foi possível calcular o custo de oportunidade." />}
                  {custoQ.data && (custoQ.data.best_opportunity ? (
                    <div style={box}>
                      <div style={metricLabel}>Você deixou de ganhar (últimos {custoQ.data.period_months} meses, já sem anuidade)</div>
                      <div style={metricValue}>{brl(custoQ.data.best_opportunity.difference)}</div>
                      <div style={nota}>≈ {brl(custoQ.data.best_opportunity.difference_annualized, 0)}/ano com o {custoQ.data.best_opportunity.card_name}</div>
                      <div style={{ ...nota, marginTop: 6 }}>{custoQ.data.best_opportunity.explanation}</div>
                    </div>
                  ) : <div style={nota}>Nenhum cartão que você pode contratar rende mais que o {custoQ.data.current_card_name} no seu gasto.</div>)}
                  {roiQ.isError && <Erro erro={roiQ.error} fallback="Não foi possível calcular o retorno do cartão." />}
                  {roiQ.data && (
                    <div style={box}>
                      <div style={metricLabel}>O seu cartão compensa?</div>
                      <div style={{ fontSize: 14, fontWeight: 700 }}>{ROTULO_VEREDICTO[roiQ.data.verdict] || roiQ.data.verdict}</div>
                      <div style={nota}>
                        Recompensa {brl(roiQ.data.reward_value_generated)}/ano − anuidade {brl(roiQ.data.annuity_paid)} = {brl(roiQ.data.net_roi)}
                      </div>
                      <div style={{ ...nota, marginTop: 4 }}><Markdown texto={roiQ.data.explanation} /></div>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div style={card}>
              <div style={sectionTitle}>Promoções de transferência de pontos</div>
              {promocoesQ.isError && <Erro erro={promocoesQ.error} fallback="Não foi possível carregar as promoções." />}
              {promocoesQ.data && promocoesQ.data.promotions.length === 0 && (
                <div style={nota}>Nenhuma promoção ativa agora. As da curadoria venceram — aparecem aqui quando houver nova.</div>
              )}
              {(promocoesQ.data?.promotions || []).slice(0, 5).map(p => (
                <div key={p.id} style={{ borderBottom: '1px solid var(--border-color)', padding: '8px 0' }}>
                  {/* o item não tem title/name: era sempre "Promoção" */}
                  <div style={{ fontSize: 14, fontWeight: 600 }}>{p.loyalty_program} → {p.partner} (+{p.bonus_pct.toFixed(0)}%)</div>
                  <div style={nota}>até {dataLonga(p.end_date)}{p.days_remaining > 0 ? ` · faltam ${p.days_remaining} dia(s)` : ''}{p.min_points ? ` · mínimo ${p.min_points.toLocaleString('pt-BR')} pontos` : ''}</div>
                  <div style={nota}>{p.description}</div>
                </div>
              ))}
            </div>
          </div>

          <div style={card}>
            <div style={sectionTitle}>Análise completa do seu perfil</div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap', alignItems: 'center' }}>
              <button onClick={() => analiseM.mutate()} disabled={analiseM.isPending} style={botao}>
                {analiseM.isPending ? 'Analisando…' : 'Rodar análise completa'}
              </button>
              {currentCard && <span style={nota}>Usando o cartão selecionado como o atual.</span>}
            </div>
            {analiseM.isError && <Erro erro={analiseM.error} fallback="Não foi possível gerar a análise." />}
            {analiseM.data && (
              <div style={{ display: 'grid', gap: 12 }}>
                <div style={grid(200)}>
                  <Metrica rotulo="Recomendação" valor={<span style={{ fontSize: 15 }}>{ROTULO_RECOMENDACAO[analiseM.data.recommendation_type] || analiseM.data.recommendation_type}</span>} />
                  {analiseM.data.best_card && (
                    <Metrica rotulo="Melhor cartão" valor={<span style={{ fontSize: 15 }}>{analiseM.data.best_card.card_name}</span>}
                      sub={`ganho líquido ${brl(analiseM.data.best_card.net_gain_min, 0)} a ${brl(analiseM.data.best_card.net_gain_max, 0)}/ano (esperado ${brl(analiseM.data.best_card.net_gain_expected, 0)})`} />
                  )}
                </div>
                <div style={nota}>{analiseM.data.strategy_text}</div>
                {!!analiseM.data.best_card?.eligibility_reasons?.length && (
                  <div style={nota}>Por que você deve ser aprovado: {analiseM.data.best_card.eligibility_reasons.join(' · ')}</div>
                )}
                <div style={grid(220)}>
                  <div style={box}>
                    <div style={{ ...metricLabel, marginBottom: 8 }}>Seu perfil</div>
                    <div style={{ display: 'grid', gap: 4, fontSize: 12, color: 'var(--text-secondary)' }}>
                      <div>Gasto médio: {brl(analiseM.data.user_profile_summary.monthly_avg_spend || 0, 0)}/mês</div>
                      <div>Estresse financeiro (FSS): {analiseM.data.user_profile_summary.fss ?? '—'}{analiseM.data.user_profile_summary.fss_level ? ` (${analiseM.data.user_profile_summary.fss_level.toLowerCase()})` : ''}</div>
                      <div>Provável MEI: {analiseM.data.user_profile_summary.is_likely_mei ? 'sim' : 'não'}</div>
                    </div>
                  </div>
                  <div style={box}>
                    <div style={{ ...metricLabel, marginBottom: 8 }}>Mudanças de vida detectadas</div>
                    {analiseM.data.life_events.length === 0 && <div style={nota}>Nenhuma.</div>}
                    {analiseM.data.life_events.map(ev => (
                      <div key={ev.event} style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
                        • {ROTULO_EVENTO[ev.event] || ev.event} <span style={nota}>({Math.round(ev.confidence * 100)}% de confiança)</span>
                      </div>
                    ))}
                  </div>
                </div>
                {analiseM.data.insights.length > 0 && (
                  <div style={box}>
                    <div style={{ ...metricLabel, marginBottom: 8 }}>O que fazer</div>
                    {analiseM.data.insights.slice(0, 4).map((ins, i) => (
                      <div key={`${ins.type}-${i}`} style={{ padding: '6px 0' }}>
                        <div style={{ fontSize: 13, fontWeight: 700 }}>{ins.title}</div>
                        <div style={nota}>{ins.description}</div>
                        {ins.gain_interval?.expected != null && <div style={nota}>Ganho estimado: {brl(ins.gain_interval.expected)}</div>}
                        {ins.insight_id && (respondidos[ins.insight_id]
                          ? <div style={nota}>{respondidos[ins.insight_id] === 'ACCEPTED' ? 'Anotado: você vai fazer.' : 'Anotado: não se aplica a você.'}</div>
                          : <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                              <button style={botaoSec} disabled={responderInsightM.isPending} onClick={() => responderInsightM.mutate({ reportId: analiseM.data!.report_id, insightId: ins.insight_id, r: 'ACCEPTED' })}>Vou fazer</button>
                              <button style={botaoSec} disabled={responderInsightM.isPending} onClick={() => responderInsightM.mutate({ reportId: analiseM.data!.report_id, insightId: ins.insight_id, r: 'REJECTED' })}>Não se aplica</button>
                            </div>)}
                      </div>
                    ))}
                  </div>
                )}
                {analiseM.data.warnings.length > 0 && <div style={aviso}>{analiseM.data.warnings.slice(0, 3).map((w, i) => <div key={i}>• {w}</div>)}</div>}
              </div>
            )}

            {/* fora do resultado: o histórico só aparecia depois de rodar uma análise nova */}
            <div style={{ ...box, marginTop: 12 }}>
              <div style={{ ...metricLabel, marginBottom: 8 }}>Análises anteriores</div>
              {relatoriosQ.isError && <Erro erro={relatoriosQ.error} fallback="Não foi possível carregar o histórico." />}
              {relatoriosQ.data && relatoriosQ.data.reports.length === 0 && <div style={nota}>Nenhuma análise salva ainda.</div>}
              {(relatoriosQ.data?.reports || []).slice(0, 4).map(r => (
                <div key={r.report_id} style={{ padding: '6px 0', borderBottom: '1px solid var(--border-color)' }}>
                  <div style={{ fontSize: 13, fontWeight: 700 }}>{r.best_card_name || ROTULO_RECOMENDACAO[r.recommendation_type] || 'Análise'}</div>
                  <div style={nota}>{dataLonga(r.generated_at?.slice(0, 10))}{r.net_gain_expected != null ? ` · ganho esperado ${brl(r.net_gain_expected, 0)}/ano` : ''}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━ CONTAS E CARTÕES ━━━━━━━━━━━━━━━━━━━━━━━━ */}
      {tab === 'cards' && (
        <div style={{ display: 'grid', gap: 12 }}>
          <div style={card}>
            <div style={sectionTitle}>Contas e cartões no seu extrato</div>
            {lancamentosQ.isLoading && <div style={nota}>Carregando lançamentos…</div>}
            {lancamentosQ.isError && <Erro erro={lancamentosQ.error} fallback="Não foi possível carregar os lançamentos." />}
            {lancamentosQ.data && (
              <>
                <div style={{ ...grid(180), marginBottom: 8 }}>
                  <Metrica rotulo="Contas/cartões" valor={contas.length} />
                  <Metrica rotulo="Lançamentos analisados" valor={lancamentosQ.data.transactions.length.toLocaleString('pt-BR')}
                    sub={lancamentosQ.data.has_more ? `os mais recentes de ${lancamentosQ.data.total.toLocaleString('pt-BR')}` : 'todos'} />
                </div>
                {contas.length === 0 && <div style={nota}>Nenhum lançamento ainda.</div>}
              </>
            )}
          </div>
          <div style={grid(280)}>
            {contas.map(c => {
              const top = Object.entries(c.cats).sort((a, b) => b[1] - a[1])[0];
              return (
                <div key={c.id} style={card}>
                  <div style={sectionTitle}>{c.id}</div>
                  <div style={grid(120)}>
                    <Metrica rotulo="Lançamentos" valor={c.n} />
                    <Metrica rotulo="Saídas" valor={brl(c.gasto, 0)} />
                    <Metrica rotulo="Entradas" valor={brl(c.entrada, 0)} />
                  </div>
                  <div style={{ ...nota, marginTop: 8 }}>
                    Maior categoria: {top ? `${top[0]} (${brl(top[1], 0)})` : '—'} · último lançamento em {dataCurta(c.ultima)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━ GRANDE COMPRA ━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      {tab === 'architect' && (
        <div style={{ display: 'grid', gap: 12 }}>
          <div style={card}>
            <div style={sectionTitle}>Financiar, consórcio ou juntar e pagar à vista?</div>
            <div style={{ ...grid(150), marginBottom: 10, alignItems: 'end' }}>
              {([['valor', 'Valor do bem (R$)'], ['entrada', 'Entrada (R$)'], ['meses', 'Prazo (meses)']] as const).map(([k, rot]) => (
                <label key={k} style={{ display: 'grid', gap: 4, fontSize: 12, color: 'var(--text-muted)' }}>{rot}
                  <input value={bem[k]} inputMode="decimal" onChange={e => setBem({ ...bem, [k]: e.target.value })} style={input} />
                </label>
              ))}
              <label style={{ display: 'grid', gap: 4, fontSize: 12, color: 'var(--text-muted)' }}>Tipo
                <select value={bem.tipo} onChange={e => setBem({ ...bem, tipo: e.target.value as TipoDeBem })} style={input}>
                  {(['VEICULO', 'IMOVEL', 'REFORMA', 'VIAGEM', 'OUTRO'] as TipoDeBem[]).map(t => (
                    <option key={t} value={t}>{({ VEICULO: 'Veículo', IMOVEL: 'Imóvel', REFORMA: 'Reforma', VIAGEM: 'Viagem', OUTRO: 'Outro' })[t]}</option>
                  ))}
                </select>
              </label>
              <label style={{ display: 'grid', gap: 4, fontSize: 12, color: 'var(--text-muted)' }}>Perfil de risco
                <select value={bem.risco} onChange={e => setBem({ ...bem, risco: e.target.value as PerfilDeRisco })} style={input}>
                  <option value="conservador">Conservador</option><option value="moderado">Moderado</option><option value="agressivo">Arrojado</option>
                </select>
              </label>
              <button onClick={() => simularM.mutate()} disabled={simularM.isPending || !(lerValor(bem.valor) > 0)} style={botao}>
                {simularM.isPending ? 'Simulando… (até 30 s)' : 'Simular'}
              </button>
            </div>

            {/* erro aparece como erro — timeout e 422 voltavam para "Execute uma simulação…" */}
            {simularM.isError && <Erro erro={simularM.error} fallback="A simulação falhou." />}
            {!simularM.data && !simularM.isPending && !simularM.isError && <div style={nota}>Compara as estratégias pelo custo em valor presente e pelo impacto na sua liquidez.</div>}
            {simularM.data && (() => {
              const r = simularM.data;
              const npv: [string, number | null | undefined][] = [
                ['Financiamento', r.npv.financing], ['Consórcio', r.npv.consortium], ['Juntar e comprar à vista', r.npv.save_invest],
                ...(typeof r.npv.financing_rental === 'number' ? [['Financiar e alugar', r.npv.financing_rental] as [string, number]] : []),
                ...(typeof r.npv.consortium_selic_rental === 'number' ? [['Consórcio + renda fixa + aluguel', r.npv.consortium_selic_rental] as [string, number]] : []),
              ];
              return (
                <div style={{ display: 'grid', gap: 10 }}>
                  <div style={grid(180)}>
                    <Metrica rotulo="Estratégia recomendada" valor={<span style={{ fontSize: 15 }}>{ROTULO_ESTRATEGIA[r.recommended_strategy] || r.recommended_strategy}</span>} />
                    <Metrica rotulo="Confiança" valor={pct(r.confidence_score * 100, 0)} />
                    <Metrica rotulo="Prazo até ter o bem" valor={`${r.months_to_achieve} meses`} />
                    <Metrica rotulo="Custo total esperado" valor={brl(r.costs.expected_cost, 0)} />
                    <Metrica rotulo="Impacto na liquidez" valor={pct(r.liquidity_impact * 100, 0)} />
                  </div>
                  <div style={box}>
                    <div style={{ ...metricLabel, marginBottom: 8 }}>Custo em valor presente (quanto menos negativo, melhor)</div>
                    {npv.map(([rot, v]) => (
                      <div key={rot} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, padding: '2px 0' }}>
                        <span style={{ color: 'var(--text-secondary)' }}>{rot}</span>
                        {/* null era R$ 0,00 — parecia o melhor ao lado de valores negativos */}
                        <strong>{typeof v === 'number' ? brl(v, 0) : 'não calculado'}</strong>
                      </div>
                    ))}
                    {r.ssd_guarantee && <div style={{ ...nota, marginTop: 6 }}>{r.ssd_guarantee}</div>}
                  </div>
                  <div style={box}>
                    <div style={{ ...metricLabel, marginBottom: 8 }}>Plano de ação</div>
                    {r.action_plan.length === 0 && <div style={nota}>Sem plano detalhado.</div>}
                    {r.action_plan.map(p => <div key={p.step} style={{ fontSize: 13, marginBottom: 4 }}>{p.step}. {p.action}</div>)}
                  </div>
                  {r.warnings.length > 0 && <div style={aviso}>{r.warnings.slice(0, 3).map((w, i) => <div key={i}>• {w}</div>)}</div>}
                </div>
              );
            })()}
          </div>

          <div style={grid(280)}>
            <div style={card}>
              <div style={sectionTitle}>Simulações anteriores</div>
              {(pendentesQ.data || []).length > 0 && (
                <div style={{ ...box, marginBottom: 8 }}>
                  <div style={{ ...metricLabel, marginBottom: 6 }}>Passados alguns meses: o que você fez? (deixa as próximas simulações mais certeiras)</div>
                  {responderSimM.isError && <Erro erro={responderSimM.error} fallback="Não foi possível registrar." />}
                  {(pendentesQ.data || []).map(p => (
                    <div key={p.simulation_id} style={{ fontSize: 12, padding: '4px 0', display: 'grid', gap: 4 }}>
                      <span>{dataLonga(p.created_at.slice(0, 10))}: recomendamos {ROTULO_ESTRATEGIA[p.recommended_strategy] || p.recommended_strategy}.</span>
                      <span style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        <button style={botaoSec} disabled={responderSimM.isPending} onClick={() => responderSimM.mutate({ id: p.simulation_id, seguiu: true, estrategia: p.recommended_strategy })}>Segui</button>
                        {(['FINANCING', 'CONSORTIUM', 'SAVE_INVEST'] as Estrategia[]).filter(e => e !== p.recommended_strategy).map(e => (
                          <button key={e} style={botaoSec} disabled={responderSimM.isPending} onClick={() => responderSimM.mutate({ id: p.simulation_id, seguiu: false, estrategia: e })}>Fiz {ROTULO_ESTRATEGIA[e].toLowerCase()}</button>
                        ))}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              {simulacoesQ.isError && <Erro erro={simulacoesQ.error} fallback="Não foi possível carregar o histórico." />}
              {simulacoesQ.data && simulacoesQ.data.length === 0 && <div style={nota}>Nenhuma simulação ainda.</div>}
              {(simulacoesQ.data || []).slice(0, 5).map(sim => (
                <div key={sim.id} style={{ borderBottom: '1px solid var(--border-color)', padding: '8px 0' }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{ROTULO_ESTRATEGIA[sim.recommended_strategy] || sim.recommended_strategy} · {brl(sim.target_amount, 0)}</div>
                  <div style={nota}>{dataLonga(sim.created_at?.slice(0, 10))} · {sim.months_to_achieve} meses · custo {brl(sim.expected_cost, 0)}</div>
                </div>
              ))}
            </div>
            <div style={card}>
              <div style={sectionTitle}>Resumo</div>
              {metricasQ.isError && <Erro erro={metricasQ.error} fallback="Não foi possível carregar as métricas." />}
              {metricasQ.data && (
                <div style={{ display: 'grid', gap: 8 }}>
                  <Metrica rotulo="Simulações feitas" valor={metricasQ.data.total_simulations} />
                  <Metrica rotulo="Estratégia mais recomendada" valor={<span style={{ fontSize: 15 }}>{metricasQ.data.favorite_strategy ? ROTULO_ESTRATEGIA[metricasQ.data.favorite_strategy] || metricasQ.data.favorite_strategy : '—'}</span>}
                    sub={metricasQ.data.avg_confidence_score != null ? `confiança média ${pct(metricasQ.data.avg_confidence_score * 100, 0)}` : undefined} />
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━ MEI / FISCAL ━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      {tab === 'fiscal' && (
        <div style={{ display: 'grid', gap: 12 }}>
          <div style={card}>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={nota}>Período:</span>
              <input type="number" value={year} onChange={e => setYear(Number(e.target.value || new Date().getFullYear()))} style={{ ...input, width: 100 }} aria-label="Ano" />
              <select value={month} onChange={e => setMonth(e.target.value === '' ? '' : Number(e.target.value))} style={input} aria-label="Mês">
                <option value="">Ano inteiro</option>
                {MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
              </select>
            </div>
            <div style={{ ...nota, marginTop: 6 }}>Só entra o que o extrato classificou como da empresa (PJ). Corrija abaixo o que estiver errado.</div>
          </div>
          <div style={grid(300)}>
            <div style={card}>
              <div style={sectionTitle}>Relatório do negócio</div>
              {fiscalQ.isLoading && <div style={nota}>Carregando…</div>}
              {fiscalQ.isError && <Erro erro={fiscalQ.error} fallback="Não foi possível gerar o relatório fiscal." />}
              {fiscalQ.data && (
                <div style={{ display: 'grid', gap: 8 }}>
                  <div style={grid(130)}>
                    <Metrica rotulo="Receita" valor={brl(fiscalQ.data.total_receita, 0)} />
                    <Metrica rotulo="Despesas" valor={brl(fiscalQ.data.total_despesa, 0)} />
                    <Metrica rotulo="Lucro estimado" valor={brl(fiscalQ.data.lucro_estimado, 0)} />
                  </div>
                  <Metrica rotulo={`DAS estimado (${fiscalQ.data.period_label})`} valor={brl(fiscalQ.data.das_estimado)}
                    sub={`${fiscalQ.data.das_faixa || '—'} · alíquota efetiva ${pct(fiscalQ.data.das_aliquota_efetiva, 2)}${fiscalQ.data.fator_r != null ? ` · Fator R ${pct(fiscalQ.data.fator_r * 100)}` : ''}`} />
                  {fiscalQ.data.das_observacao && <div style={nota}>{fiscalQ.data.das_observacao}</div>}
                  {[['Receitas', fiscalQ.data.receitas], ['Despesas', fiscalQ.data.despesas]].map(([rot, linhas]) => (
                    (linhas as typeof fiscalQ.data.receitas).length > 0 && (
                      <div key={rot as string} style={box}>
                        <div style={{ ...metricLabel, marginBottom: 6 }}>{rot as string}</div>
                        {(linhas as typeof fiscalQ.data.receitas).map(l => (
                          <div key={l.subcategory} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '2px 0' }}>
                            <span>{l.label} <span style={nota}>({l.count})</span></span><strong>{brl(l.total, 0)}</strong>
                          </div>
                        ))}
                      </div>
                    )
                  ))}
                </div>
              )}
            </div>
            <div style={card}>
              <div style={sectionTitle}>Gastos de uso misto (casa e empresa)</div>
              {mistoQ.isError && <Erro erro={mistoQ.error} fallback="Não foi possível detectar uso misto." />}
              {mistoQ.data && (
                <div style={{ display: 'grid', gap: 8 }}>
                  <div style={grid(130)}>
                    <Metrica rotulo="Lançamentos" valor={mistoQ.data.candidates.length} />
                    <Metrica rotulo="Gasto misto" valor={brl(mistoQ.data.total_mixed_spend, 0)} />
                    <Metrica rotulo="Parte dedutível (PJ)" valor={brl(mistoQ.data.total_pj_deductible, 0)}
                      sub={mistoQ.data.total_mixed_spend > 0 ? `${pct((mistoQ.data.total_pj_deductible / mistoQ.data.total_mixed_spend) * 100, 0)} do gasto misto` : undefined} />
                  </div>
                  {corrigirM.isError && <Erro erro={corrigirM.error} fallback="Não foi possível salvar a correção." />}
                  {mistoQ.data.candidates.slice(0, 8).map(c => (
                    <div key={c.transaction_id} style={{ ...box, display: 'grid', gap: 4 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                        <span>{c.description}</span><strong>{brl(Math.abs(c.amount))}</strong>
                      </div>
                      <div style={nota}>{dataCurta(c.date)} · {c.explanation}</div>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button style={botaoSec} disabled={corrigirM.isPending} onClick={() => corrigirM.mutate({ id: c.transaction_id, ctx: 'PJ' })}>É da empresa</button>
                        <button style={botaoSec} disabled={corrigirM.isPending} onClick={() => corrigirM.mutate({ id: c.transaction_id, ctx: 'PF' })}>É pessoal</button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ COMPARAÇÃO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      {tab === 'peers' && (
        <div style={card}>
          <div style={sectionTitle}>Você comparado a pessoas com renda parecida</div>
          <div style={{ marginBottom: 10 }}>{campoRenda}</div>
          {pares.isLoading && <div style={nota}>Comparando…</div>}
          {pares.isError && <Erro erro={pares.error} fallback="Não foi possível comparar." />}
          {pares.data && (
            <div style={{ display: 'grid', gap: 10 }}>
              {/* score/percentil de gasto não existem na resposta: eram sempre 0 */}
              <div style={grid(180)}>
                <Metrica rotulo="Quanto você poupa" valor={pct(pares.data.user_savings_rate)} sub={`pessoas parecidas: ${pct(pares.data.benchmark_savings_rate)}`} />
                <Metrica rotulo="Sua posição" valor={<span style={{ fontSize: 15 }}>{pares.data.savings_percentile_label}</span>} sub={pares.data.bracket_label} />
              </div>
              {pares.data.highlights_above.length > 0 && <div style={{ fontSize: 13 }}>Gasta <strong>acima</strong> do esperado em: {pares.data.highlights_above.join(', ')}</div>}
              {pares.data.highlights_below.length > 0 && <div style={{ fontSize: 13 }}>Gasta <strong>abaixo</strong> do esperado em: {pares.data.highlights_below.join(', ')}</div>}
              <div style={box}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr auto auto', gap: '4px 16px', fontSize: 12 }}>
                  <span style={metricLabel}>Categoria</span><span style={metricLabel}>Você</span><span style={metricLabel}>Parecidos</span>
                  {pares.data.categories.map(c => (
                    <div key={c.category} style={{ display: 'contents' }}>
                      <span title={c.insight}>{c.label}</span>
                      <strong style={{ color: c.user_pct > c.benchmark_pct * 1.2 ? '#b91c1c' : undefined }}>{pct(c.user_pct, 0)}</strong>
                      <span>{pct(c.benchmark_pct, 0)}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div style={nota}>Percentual da renda por categoria. Fonte: {pares.data.benchmark_source}.</div>
            </div>
          )}
        </div>
      )}

      {/* ━━━━━━━━━━━━━━━━━━━━ TARIFAS · COMPRA · NEGOCIAÇÃO ━━━━━━━━━━━━━━━━━━━━ */}
      {tab === 'advanced' && (
        <div style={{ display: 'grid', gap: 12 }}>
          <div style={grid(300)}>
            <div style={card}>
              <div style={sectionTitle}>Raio-X do que o banco te cobra</div>
              {raioXQ.isLoading && <div style={nota}>Analisando tarifas…</div>}
              {raioXQ.isError && <Erro erro={raioXQ.error} fallback="Não foi possível analisar as tarifas." />}
              {raioXQ.data && (
                <div style={{ display: 'grid', gap: 8 }}>
                  <div style={grid(130)}>
                    <Metrica rotulo={`Pago em ${raioXQ.data.analysis_months} meses`} valor={brl(raioXQ.data.total_paid, 0)} sub={`${dataCurta(raioXQ.data.period_start)} a ${dataCurta(raioXQ.data.period_end)}`} />
                    <Metrica rotulo="Por mês" valor={brl(raioXQ.data.monthly_avg)} />
                    <Metrica rotulo="Dá para economizar" valor={`${brl(raioXQ.data.savings_opportunity)}/mês`} />
                  </div>
                  {Object.entries(raioXQ.data.by_fee_type).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                    <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                      <span>{ROTULO_TARIFA[k] || k}</span><strong>{brl(v, 0)}</strong>
                    </div>
                  ))}
                  {raioXQ.data.by_bank.length > 0 && <div style={nota}>Bancos: {raioXQ.data.by_bank.map(b => `${b.bank_name} (${brl(b.monthly_avg)}/mês)`).join(' · ')}</div>}
                  {raioXQ.data.total_paid === 0 && <div style={nota}>Nenhuma tarifa encontrada no extrato.</div>}
                </div>
              )}
            </div>

            <div style={card}>
              <div style={sectionTitle}>Compra inteligente: como pagar?</div>
              <div style={{ display: 'grid', gap: 8, marginBottom: 10 }}>
                <div style={grid(130)}>
                  <label style={{ display: 'grid', gap: 4, fontSize: 12, color: 'var(--text-muted)' }}>Valor (R$)
                    <input value={compra.valor} inputMode="decimal" onChange={e => setCompra({ ...compra, valor: e.target.value })} style={input} />
                  </label>
                  <label style={{ display: 'grid', gap: 4, fontSize: 12, color: 'var(--text-muted)' }}>Preço à vista, se tiver desconto
                    <input value={compra.aVista} inputMode="decimal" placeholder="opcional" onChange={e => setCompra({ ...compra, aVista: e.target.value })} style={input} />
                  </label>
                  <label style={{ display: 'grid', gap: 4, fontSize: 12, color: 'var(--text-muted)' }}>Categoria
                    <input value={compra.categoria} onChange={e => setCompra({ ...compra, categoria: e.target.value })} style={input} />
                  </label>
                  <label style={{ display: 'grid', gap: 4, fontSize: 12, color: 'var(--text-muted)' }}>Parcelas
                    <input type="number" min={1} max={48} value={parcelas}
                      onChange={e => { setAutoParcelas(false); setCompra({ ...compra, parcelas: Number(e.target.value || 1) }); }} style={input} />
                  </label>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <span style={nota}>Sugestão para o seu orçamento: {parcelasSugeridas}x</span>
                  <button style={botaoSec} onClick={() => setAutoParcelas(true)}>Usar sugestão</button>
                  <button style={botao} disabled={compraM.isPending || !(valorCompra > 0)} onClick={() => compraM.mutate()}>
                    {compraM.isPending ? 'Calculando…' : 'Analisar compra'}
                  </button>
                </div>
              </div>
              {compraM.isError && <Erro erro={compraM.error} fallback="Não foi possível analisar a compra." />}
              {compraM.data && (
                <div style={{ display: 'grid', gap: 8 }}>
                  <Metrica rotulo="Melhor forma de pagar" valor={<span style={{ fontSize: 15 }}>{compraM.data.recommended_label}</span>}
                    sub={`custo líquido ${brl(compraM.data.recommended_net_cost_real ?? compraM.data.recommended_net_cost)}`} />
                  <div style={{ ...nota, color: 'var(--text-secondary)' }}><Markdown texto={compraM.data.reasoning} /></div>
                  <div style={box}>
                    <div style={{ ...metricLabel, marginBottom: 6 }}>Todas as opções (custo líquido, já com o rendimento do dinheiro parado)</div>
                    {compraM.data.options.map(o => (
                      <div key={`${o.method}-${o.label}`} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '3px 0' }}>
                        <span>{o.label}</span><strong>{brl(o.net_cost_real ?? o.net_cost)}</strong>
                      </div>
                    ))}
                  </div>
                  <div style={nota}>
                    {compraM.data.liquidity_impact.affordable === null
                      ? 'Margem segura do mês não calculada — confira o saldo antes de pagar à vista.'
                      : `Margem segura: ${brl(compraM.data.liquidity_impact.safe_to_spend_before)} → ${brl(compraM.data.liquidity_impact.safe_to_spend_after)} depois da compra${compraM.data.liquidity_impact.affordable ? '' : ' (estoura a margem)'}.`}
                  </div>
                  {compraM.data.warnings.length > 0 && <div style={aviso}>{compraM.data.warnings.slice(0, 3).map((w, i) => <div key={i}>• {w}</div>)}</div>}
                </div>
              )}
              <div style={{ ...box, marginTop: 10 }}>
                <div style={{ ...metricLabel, marginBottom: 6 }}>Suas compras das últimas 2 semanas</div>
                {revisaoQ.isError && <Erro erro={revisaoQ.error} fallback="Não foi possível revisar as compras recentes." />}
                {revisaoQ.data && revisaoQ.data.total === 0 && <div style={nota}>Nada a revisar — nenhuma compra recente que tivesse forma de pagamento melhor.</div>}
                {(revisaoQ.data?.reviews || []).slice(0, 4).map(r => (
                  <div key={r.transaction_id} style={{ fontSize: 12, padding: '3px 0' }}>
                    {r.merchant} ({brl(r.amount)}, {dataCurta(r.purchase_date)}): pagou com {r.paid_method_label}; {r.best_method_label} teria economizado {brl(r.potential_savings_brl)}.
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div style={card}>
            <div style={sectionTitle}>Negociar com o banco</div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
              <input value={banco} onChange={e => setBanco(e.target.value)} placeholder="Banco (opcional, ex.: Itaú)" style={{ ...input, minWidth: 240 }} />
              <button onClick={() => negociarM.mutate()} disabled={negociarM.isPending} style={botao}>
                {negociarM.isPending ? 'Gerando roteiros…' : 'Gerar roteiro'}
              </button>
            </div>
            {negociarM.isError && <Erro erro={negociarM.error} fallback="Não foi possível gerar o roteiro." />}
            {negociarM.data && (
              <div style={{ display: 'grid', gap: 10 }}>
                <div style={{ fontSize: 13 }}>{negociarM.data.summary}</div>
                {negociarM.data.scripts.map((s, i) => (
                  <div key={i} style={{ ...box, display: 'grid', gap: 6 }}>
                    <div style={{ fontSize: 13, fontWeight: 700 }}>{s.opportunity.bank_name} · {s.opportunity.product}</div>
                    <div style={nota}>{s.opportunity.description}</div>
                    <div style={{ fontSize: 12 }}><strong>Comece com:</strong> {s.opening_line}</div>
                    {s.key_arguments.length > 0 && <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>{s.key_arguments.map((a, j) => <li key={j}>{a}</li>)}</ul>}
                    <div style={{ fontSize: 12 }}><strong>Peça:</strong> {s.target_ask}</div>
                    <div style={{ fontSize: 12 }}><strong>Se recusarem:</strong> {s.fallback_ask}</div>
                    <div style={nota}>
                      {ROTULO_CANAL[s.recommended_channel] || s.recommended_channel} · {s.best_time} · chance estimada {s.estimated_success_pct}%
                      {s.generated_by === 'fallback' ? ' · roteiro padrão (a IA não respondeu)' : ''}
                    </div>
                  </div>
                ))}
                {negociarM.data.warnings.length > 0 && <div style={aviso}>{negociarM.data.warnings.slice(0, 3).map((w, i) => <div key={i}>• {w}</div>)}</div>}
              </div>
            )}
            <div style={{ ...box, marginTop: 10 }}>
              <div style={{ ...metricLabel, marginBottom: 6 }}>Como foram suas negociações? (calibra as próximas estimativas)</div>
              {historicoNegQ.isError && <Erro erro={historicoNegQ.error} fallback="Não foi possível carregar o histórico." />}
              {resultadoM.isError && <Erro erro={resultadoM.error} fallback="Não foi possível registrar o resultado." />}
              {historicoNegQ.data && historicoNegQ.data.items.length === 0 && <div style={nota}>Nenhum roteiro gerado ainda.</div>}
              {(historicoNegQ.data?.items || []).slice(0, 5).map(it => (
                <div key={it.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', padding: '4px 0', fontSize: 12 }}>
                  <span>{it.bank_name} · {dataCurta(it.generated_at?.slice(0, 10))}{it.potential_gain ? ` · até ${brl(it.potential_gain)}/mês` : ''}</span>
                  {it.result_status
                    ? <strong>{ROTULO_RESULTADO[it.result_status as ResultadoNegociacao] || it.result_status}</strong>
                    : <span style={{ display: 'flex', gap: 4 }}>
                        {(Object.keys(ROTULO_RESULTADO) as ResultadoNegociacao[]).map(r => (
                          <button key={r} style={botaoSec} disabled={resultadoM.isPending} onClick={() => resultadoM.mutate({ id: it.id, r })}>{ROTULO_RESULTADO[r]}</button>
                        ))}
                      </span>}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
};
