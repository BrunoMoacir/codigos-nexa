# 13 — Inteligência Comportamental

> A camada que faz os mesmos dados gerarem recomendações DIFERENTES por
> pessoa: um pai de família e um viajante de milhas não devem ouvir o mesmo
> conselho.

## Em palavras simples

A Nexa observa 90 dias de transações e forma uma imagem de quem você é
financeiramente: viaja muito? pede muito delivery? está no aperto? é MEI?
Essa imagem (um "cluster" + sinais) muda o tom do chat, o cartão recomendado,
o orçamento sugerido e quais notificações valem a pena te interromper. É a
diferença entre um app genérico e um consultor que te conhece.

## O que faz

### 8 clusters de estilo de vida (`optimizer/detectors/lifestyle_classifier.py`)
`EXPLORADOR_GLOBAL` (milhas/lounge) · `URBANO_FOODIE` (cashback alimentação) ·
`INVESTIDOR_CAUTELOSO` (precisão numérica) · `FAMILIA_ESTRUTURADA`
(segurança/educação) · `DIGITAL_NATIVO` (PIX/fintechs) · `ESTRESSE_FINANCEIRO`
(empatia, cortes, **zero sugestão de gasto**) · `MICROEMPREENDEDOR` (PF/PJ,
DAS) · `NAO_CLASSIFICADO` (neutro).

- Scores 0–1 por cluster vindos de detectores dedicados
  (`travel_detector`, `foodie_detector`, `investor_detector`,
  `family_detector`, `mei_detector`, `fss_calculator`...); primário exige
  score ≥ 0,35 "ganhando claramente"; até 2 secundários ≥ 0,30.
- **Honestidade técnica**: são regras determinísticas calibradas — NÃO é ML
  (substituição por modelo de clustering está planejada; as regras têm a
  vantagem de serem explicáveis).

### Sinais transversais
| Sinal | Onde | Efeito |
|---|---|---|
| **FSS** (Financial Stress Score, `fss_calculator.py`) | perfil frágil | OPP prioriza liquidez diária; tom do agente muda; nunca sugerir gasto |
| **Life Events** (`life_events_detector.py`) | bebê, mudança, casamento, faculdade, ±20% de renda | Cards `LIFE_EVENT` com ação sugerida ("revisar seguro de vida") |
| **IncomeProfiler** (ETL) | renda real (filtra transferências) | Base de TODOS os thresholds do produto |
| **Personal baseline** (`personal_baseline.py`) | padrão histórico próprio | Anomalias medidas contra VOCÊ, não contra a média |
| **Life stage / temporal / trend detectors** | fase de vida, padrões temporais, tendências de categoria | Bônus de ranking no optimizer, contexto do agente |

### Filtro de Relevância de Notificações (`notifications/relevance_filter.py`)
Pipeline de 3 etapas que decide o que MERECE interromper o usuário:
1. Threshold por tipo de card, **escalado pela renda** (R$ 50 de tarifa é
   crítico para quem ganha R$ 2k e ruído para quem ganha R$ 15k);
2. Cap de ≤2 cards por tipo;
3. Cap global de ≤4 não-críticos por ciclo.
CRITICAL nunca é descartado.

## Como funciona (técnico)

- `optimizer/profiler.py` constrói o `UserProfile` consumido por 6+ módulos
  (agente, optimizer, budget, notificações, OPP, purchase).
- A primeira tool de toda sessão de chat é `get_user_profile_context` — o
  cluster adapta o tom da conversa inteira.
- Enriquecimento de features (`feature_store.py`): categoria canônica com
  score de confiança, merchant normalizado, método de pagamento, viagem,
  features temporais.

## O que NÃO faz

- Não infere dados sensíveis (saúde, religião, orientação) — clusters são
  padrões de CONSUMO; o detector de eventos de vida olha categorias de gasto,
  não conteúdo.
- Não vende/compartilha o perfil — uso exclusivamente interno (LGPD, doc 17).
- Não decide sozinho — personaliza recomendações; nunca executa.

## Gaps e limitações

- Clusters por regras não capturam perfis híbridos raros; o plano de evoluir
  para clustering ML (K-Means/HDBSCAN) precisa de massa de dados.
- Janela de 90 dias: usuário recém-conectado fica `NAO_CLASSIFICADO`
  (neutro) até acumular histórico.
- Peer comparison (doc 14) usa benchmarks IBGE hardcoded por faixa de renda —
  a comparação com "pares reais da base" espera massa crítica.
