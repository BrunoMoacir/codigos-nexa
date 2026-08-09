# 13 — Inteligência Comportamental

> A camada que faz os mesmos dados gerarem recomendações DIFERENTES por
> pessoa: um pai de família e um viajante de milhas não devem ouvir o mesmo
> conselho.

## Em palavras simples

A Nexa observa 90 dias de transações e forma uma imagem de quem você é
financeiramente: viaja muito? pede muito delivery? está no aperto? é MEI?
Essa imagem (um "cluster" + sinais) muda o tom do chat, o cartão recomendado,
o orçamento sugerido e quais notificações valem a pena te interromper.

---

## Como é calculado

### 1. FSS — Financial Stress Score (`detectors/fss_calculator.py`)

Score **0–100** onde **mais alto = mais estresse** (inverso do health score).
Soma aditiva de componentes, saturada em 100:

**Base (uma das duas):**

```
com resilience_score disponível:
    base_stress = max(0, (100 − resilience_score) × 0,50)

sem resilience_score:
    savings_rate muito negativa      → +15
    savings_rate negativa            → +7
    future_commitment > 40%          → +min((commitment − 0,40) × 100, 20)
```

**Componentes adicionais (sempre somados):**

| Sinal | Fórmula |
|---|---|
| Uso de rotativo | `committed > 50%` **e** `credit_spend_ratio > 70%` → `+min((committed − 0,50) × 60, 30)` |
| Cheque especial | `+ overdraft_usage × 25`, onde `overdraft_usage = meses_com_cheque_especial / meses_totais` (detectado por keyword) |
| Queda de renda | queda `> 15%` nos últimos 3 meses → **+20** |

**Faixas:**

| Nível | FSS |
|---|---|
| SAUDAVEL | ≤ 20 |
| ATENCAO | ≤ 40 |
| ALERTA | ≤ 65 |
| CRITICO | > 65 |

O FSS é consumido pelo OPP (meses de reserva protegida, doc 09), pelo Bank
Match (pesos, doc 09), pelo optimizer (penalidade de anuidade, doc 03) e pelo
tom do agente.

### 2. Os 8 clusters — scores por regra

`classify_rules()` calcula a **afinidade independente** de cada cluster
(0–1). Não são probabilidades: **não somam 1** — de propósito, para que os
thresholds de primário e secundário tenham significado absoluto.

| Cluster | Composição do score |
|---|---|
| `EXPLORADOR_GLOBAL` | `travel_frequency/100 × 0,45` + `intl_spend/500 × 0,30` + `0,15` se perfil FREQUENTE/INTENSO + `0,10` se nômade digital (ou `0,05` se usuário Airbnb) |
| `URBANO_FOODIE` | `foodie_score/100 × 0,60` + `min(%_gasto_alimentação × 2, 1) × 0,40` |
| `INVESTIDOR_CAUTELOSO` | `0,50` × (1,0 se ATIVO/DIVERSIFICADO; 0,5 se CASUAL) + `min(savings_rate/50, 1) × 0,50` |
| `FAMILIA_ESTRUTURADA` | **Se `is_family_with_kids`**: `0,4 + family_score/100 × 0,6` (piso 0,4 porque o detector já usa threshold 40). **Senão** (heurística): `min(%_saúde+educação × 3, 0,6)` + `0,2` se CLT + `0,2` se estabilidade > 0,7 |
| `DIGITAL_NATIVO` | `subscription_burn/200 × 0,40` + `min((1 − credit_ratio) × 1,5, 1) × 0,30` + `merchant_diversity/80 × 0,30` |
| `ESTRESSE_FINANCEIRO` | `savings_rate < −5%` → +0,4 (ou `< 0` → +0,15); `committed > 60%` → +0,3; `estabilidade < 0,3` → +0,3. **Piso pelo FSS**: CRITICO → `max(score, 0,75)`; ALERTA → `max(score, 0,50)` |
| `MICROEMPREENDEDOR` | `0,8` se `is_likely_mei`; `0,5` se renda PJ/MIXED; senão 0 |
| `NAO_CLASSIFICADO` | quando nenhum atinge o threshold primário |

**Thresholds:**

```
_PRIMARY_THRESHOLD   = 0,35    ← primário precisa ganhar E superar 0,35
_SECONDARY_THRESHOLD = 0,30
_MAX_SECONDARY       = 2
```

O `(1 − credit_spend_ratio)` do `DIGITAL_NATIVO` é um proxy de uso de PIX/débito
— quanto menos crédito, mais "nativo digital".

### 3. O motor ML híbrido — e os dois guardrails

**Artefato real** (`models/lifestyle_classifier_metadata.json`):

```json
{
  "trained_at": "2026-07-19", "samples": 80000, "seed": 42,
  "fidelity_to_rules_holdout": 0.9591, "features_version": "1.0",
  "method": "Destilação das regras do LifestyleClassifier em RandomForest
             sobre perfis sintéticos (55% arquétipos, 25% uniforme, 20% híbridos)"
}
```

**Fidelidade de 95,91%** em holdout, 6 MB (a versão de 97,4% custaria 189 MB —
escolha por sweep fidelidade × tamanho). Features mais importantes:

| Feature | Importância |
|---|---|
| `savings_rate_norm` | 0,1261 |
| `is_likely_mei` | 0,1177 |
| `food_share` | 0,0809 |
| `travel_freq` | 0,0638 |
| `foodie_score` | 0,0620 |
| `edu_health_share` | 0,0560 |
| `investor_level` | 0,0545 |
| `committed_pct` | 0,0515 |

**Guardrail 1 — invariante determinístico:**

```python
fss_critical = profile.fss_level == "CRITICO"
if not fss_critical:
    # só então tenta o ML
```

FSS CRÍTICO **nunca** passa pelo ML. O comentário é explícito: *"o tratamento
de estresse financeiro (empatia, zero sugestão de gasto) não pode depender de
fronteira aprendida"*. É a única classificação com consequência de segurança
do usuário, e ela sai de regra determinística.

**Guardrail 2 — piso de regras (`_apply_rules_floor`):**

Quando o ML **abstém** (primário = `NAO_CLASSIFICADO` por ficar abaixo do
limiar de probabilidade) mas as regras — o *professor* do modelo — têm veredito
com score **≥ 0,60**, as regras vencem, e o resultado é marcado
`classification_source = "ml+rules_floor"`.

O motivo está anotado: o ML espalha probabilidade entre classes correlacionadas
em perfis realistas (*"foodie que também parece esticado pelo aluguel"*) e
acabava abstendo em casos claros. Defeito de calibração **encontrado pelo
harness de teste ponta a ponta** (`backend/demo/`), não por inspeção.

**Semântica preservada**: o primário vem do ML (`predict_proba`, com
`ml_confidence` calibrada), mas **`secondary_clusters` e `cluster_scores`
continuam vindo das afinidades das regras** — porque probabilidades somam 1 e
diluiriam o threshold de 0,30, quebrando o contrato para quem consome.

**Fallback integral**: `try/except` amplo em volta do ML — *"nunca deixa o ML
derrubar a classificação"*. Modelo ausente, corrompido ou com versão de
features incompatível → regras respondem sozinhas.

### 4. Life Events — confiança por evidência, não por regra fixa

`detectors/life_events_detector.py` opera sobre duas janelas:
`txns_recent` (60 dias) e `txns_history` (6–18 meses atrás, baseline).

**A confiança é um score composto de 5 dimensões** (`evidence_scorer.py`):

```
confidence = volume     × 0,30    ← gasto relativo ao threshold de disparo
           + recurrence × 0,25    ← nº de transações / meses distintos com sinal
           + absence    × 0,20    ← ausência do padrão no histórico (novo = mais forte)
           + diversity  × 0,15    ← merchants distintos corroborando
           + quality    × 0,10    ← especificidade intrínseca da keyword
```

**Hard gate contra sinal isolado**: keywords ambíguas marcadas como `soft`
recebem `composite = 0` se não houver corroboração, **independente do volume**.
Keywords específicas (`quality ≥ 0,85`) sofrem apenas penalidade suave.

Exemplos do próprio código:

| Evidência | Composite |
|---|---|
| "BUFFET" isolado (soft, hard gate) | **0,00** — bloqueado |
| "CERIMONIAL" isolado (anchor, sem hard gate) | ≈ 0,50 |
| BUFFET + NOIVAS + FOTÓGRAFO | ≈ 0,80+ |
| "PAMPERS" isolado (quality 0,85) | ≈ 0,43 |
| FRALDA + HUGGIES + CHICCO × 2 meses | ≈ 0,80+ |

`_MIN_EVENT_CONFIDENCE = 0,40` — abaixo disso o evento não é retornado. Uma
única compra num buffet não vira "você vai casar".

**Thresholds escalados por nível de renda** (`_level_ratio`): referência
R$ 3.000/mês → ratio 1,0; rendas maiores exigem gasto proporcionalmente maior
para disparar. Variação de renda: `±20%` (`_SALARY_INCREASE_THRESHOLD` /
`_SALARY_DROP_THRESHOLD`).

### 5. Filtro de Relevância de Notificações (`notifications/relevance_filter.py`)

Pipeline de 3 etapas, com **CRITICAL imune em todas**:

**Etapa 1 — threshold por tipo, escalado pela renda:**

```python
def _income_scaled(income, pct, floor, cap):
    if income <= 0: return floor        # sem renda → threshold conservador
    return max(floor, min(cap, income * pct))
```

| Tipo de card | pct da renda | piso | teto |
|---|---|---|---|
| Anomalia | 2,0% | R$ 30 | R$ 200 |
| Assinatura | 0,2% | R$ 5 | R$ 30 |
| Oportunidade de cartão | 0,5% | R$ 15 | R$ 100 |
| Safe-to-spend baixo | 5,0% | R$ 100 | R$ 400 |
| Dinheiro parado | 0,2% | R$ 5 | R$ 50 |

Exemplo do docstring: renda R$ 2k → threshold de anomalia R$ 40; R$ 5k →
R$ 100; R$ 15k → R$ 200 (batendo no teto). O mesmo evento é ruído para um e
relevante para o outro.

Alguns tipos são **income-neutral** por natureza: variação de score exige
delta mínimo de **5 pontos** (score é 0–100).

**Etapa 2 — cap por tipo**: `_MAX_PER_TYPE = 2`.
**Etapa 3 — cap global**: `_MAX_NON_CRITICAL = 4` slots para WARNING + INFO.

A lista de entrada já vem ordenada CRITICAL → WARNING → INFO, e o filtro
preserva essa ordem.

### 6. Outros sinais transversais

| Sinal | Onde | Efeito |
|---|---|---|
| `IncomeProfiler` | ETL (doc 01) | Renda real; base de TODOS os thresholds do produto |
| `personal_baseline.py` | detectors | Anomalias medidas contra VOCÊ, não contra a média |
| `life_stage_detector.py` | detectors | 4 estágios + `NAO_IDENTIFICADO`; primário ≥ 0,40, bônus de ranking só com confiança ≥ 0,50 |
| `trend_detector.py` | detectors | Direção por categoria (SUBINDO/CAINDO/ESTAVEL/REEMERGINDO) → bônus no optimizer |
| `temporal_detector.py` | detectors | Padrões por hora/dia da semana |
| `mei_detector.py` | detectors | 4 sinais → cluster MICROEMPREENDEDOR (doc 05) |

---

## Como funciona (técnico)

- `optimizer/profiler.py` constrói o `UserProfile` consumido por 6+ módulos
  (agente, optimizer, budget, notificações, OPP, purchase).
- A primeira tool de toda sessão de chat é `get_user_profile_context` — o
  cluster adapta o tom da conversa inteira.
- Enriquecimento de features (`feature_store.py`): categoria canônica com score
  de confiança, merchant normalizado, método de pagamento, viagem, features
  temporais.
- Treino reproduzível: `scripts/train_lifestyle_classifier.py` (seed 42).

## O que NÃO faz

- Não infere dados sensíveis (saúde, religião, orientação) — clusters são
  padrões de CONSUMO; o detector de eventos de vida olha categorias de gasto,
  não conteúdo.
- Não vende/compartilha o perfil — uso exclusivamente interno (LGPD, doc 17).
- Não decide sozinho — personaliza recomendações; nunca executa.

## Gaps e limitações

- **O modelo é destilado das regras, treinado em 80 mil perfis sintéticos.**
  Ele aprende fronteiras suaves e interações, mas **não descobre padrões que as
  regras não conhecem** — o teto de qualidade é o próprio conjunto de regras.
  Isso só muda com re-treino sobre dados reais rotulados (o script já
  suporta, sem mudar a inferência).
- **Fidelidade de 95,91% significa ~4% de divergência das regras** — e como as
  regras são a referência de corretude, cada divergência é, por definição, um
  erro do modelo. O piso de regras cobre o caso da abstenção, mas não o caso
  de o ML classificar **confiantemente errado**.
- **Os pesos dos clusters e do FSS são calibrados por julgamento**, não
  ajustados a desfechos observados. Não há validação de que
  `travel_frequency × 0,45` seja melhor que `× 0,40`.
- **Janela de 90 dias**: usuário recém-conectado fica `NAO_CLASSIFICADO`
  (neutro) até acumular histórico.
- **Detecção de cheque especial é por keyword** na descrição — banco que não
  descreve explicitamente passa despercebido, subestimando o FSS.
- **Peer comparison (doc 14) usa benchmarks IBGE hardcoded** por faixa de
  renda — a comparação com "pares reais da base" espera massa crítica.
