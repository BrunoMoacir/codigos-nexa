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
- **Motor ML híbrido (Fase 3 — implementado 2026-07)**: RandomForest
  **destilado das regras** (professor→aluno) treinado sobre 80 mil perfis
  sintéticos (55% arquétipos, 25% espaço amplo, 20% híbridos), fidelidade
  **95,9%** em holdout (hiperparâmetros escolhidos por sweep fidelidade ×
  tamanho: 97,4% custaria um artefato de 189 MB; o compacto tem 6 MB).
  - **Primário** vem do modelo (`predict_proba` — fronteiras suaves e
    `ml_confidence` calibrada); **secundários e cluster_scores** vêm das
    afinidades independentes das regras (probabilidades somam 1 e diluiriam
    o threshold de 0,30 — semântica preservada para os consumidores);
  - **Invariante determinístico**: FSS CRÍTICO nunca passa pelo ML — o
    tratamento de estresse financeiro não depende de fronteira aprendida;
  - **Piso de regras** (2026-07): quando o ML ABSTÉM (probabilidade do
    primário abaixo do limiar → `NAO_CLASSIFICADO`) mas as regras — o
    professor do modelo — têm veredito confiante (≥ 0,60), o híbrido usa as
    regras (`source = ml+rules_floor`). Sem isso, o ML perdia classificações
    claras em perfis realistas que espalham probabilidade entre classes
    correlacionadas (ex.: foodie que também parece esticado pelo aluguel) —
    defeito de calibração encontrado pelo harness de teste ponta a ponta
    (`backend/demo/`).
  - **Fallback integral**: modelo ausente/corrompido/versão de features
    incompatível → regras respondem sozinhas (padrão ML→regras→default);
  - Artefatos: `models/lifestyle_classifier.pkl` + metadata JSON com
    fidelidade e importâncias; treino reproduzível em
    `scripts/train_lifestyle_classifier.py` (seed fixa) — re-treinável com
    dados reais rotulados quando existirem, sem mudar a inferência.

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

- O modelo atual é **destilado das regras** (bootstrap sem dados reais):
  aprende fronteiras suaves e interações, mas não descobre padrões que as
  regras não conhecem — isso só vem re-treinando com dados reais rotulados
  (correções de usuários/validação manual), o que o script de treino já
  suporta sem mudar a inferência.
- Janela de 90 dias: usuário recém-conectado fica `NAO_CLASSIFICADO`
  (neutro) até acumular histórico.
- Peer comparison (doc 14) usa benchmarks IBGE hardcoded por faixa de renda —
  a comparação com "pares reais da base" espera massa crítica.
