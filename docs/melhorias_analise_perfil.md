# NEXA AI — Inteligência Comportamental & User Intelligence

> **Como transformar dados do Open Finance em percepção profunda do usuário**
>
> Documento Técnico — Série: IA de Produto | Abril 2026 — CONFIDENCIAL

---

## Visão Geral: O que é User Intelligence no contexto da Nexa

O Open Finance entrega à Nexa algo que nenhum banco individual possui: a visão consolidada de toda a vida financeira do usuário — em todas as contas, cartões e investimentos. Isso não é apenas um agregador de extratos. É a matéria-prima para construir o perfil comportamental mais rico já disponível sobre um indivíduo no contexto financeiro brasileiro.

Este documento define como extrair inteligência máxima desses dados para transformar recomendações genéricas em orientações hiper-personalizadas — do tipo que faz o usuário pensar *"como a Nexa sabia disso?"*.

> 🎯 **Objetivo central:** Cada sinal de transação é uma janela para o estilo de vida do usuário. Quanto mais sinais coletamos e cruzamos, mais precisa fica nossa capacidade de recomendar o produto certo, no momento certo, com o argumento certo.

---

## 1. Fundação: Estrutura de Dados que Alimenta a Inteligência

Antes de qualquer análise comportamental, precisamos garantir que o pipeline ETL já existente da Nexa produza os campos derivados corretos. As seções abaixo descrevem os campos que devem ser calculados no momento do processamento das transações.

### 1.1 Enriquecimento de Transações (Feature Store)

Para cada transação ingerida via Pluggy/Open Finance, o pipeline deve derivar automaticamente os campos abaixo:

| Campo derivado | Descrição | Fonte/método |
|---|---|---|
| `merchant_normalized` | Nome do estabelecimento normalizado (sem número de terminal) | NER + regex |
| `merchant_category_l1` | Categoria de nível 1 (ex: Alimentação) | MCC + classifier |
| `merchant_category_l2` | Subcategoria (ex: Delivery, Restaurante, Supermercado) | MCC + classifier |
| `is_recurring` | Booleano: transação recorrente detectada | F1.5 existente |
| `is_travel_related` | Booleano: relacionada a viagem | regras + ML |
| `geo_city` | Cidade inferida do merchant (quando disponível) | DB geocode |
| `geo_state` | Estado inferido | DB geocode |
| `geo_is_foreign` | Booleano: transação no exterior | moeda + MCC |
| `day_of_week` | Dia da semana (0=Segunda … 6=Domingo) | date parse |
| `hour_of_day` | Hora do dia (quando disponível) | timestamp |
| `is_weekend` | Booleano: fim de semana | derivado |
| `payment_method` | PIX / Cartão Débito / Cartão Crédito / Boleto / TED | Open Finance |
| `installments_total` | Número de parcelas (se parcelado) | Open Finance |
| `amount_percentile` | Percentil do valor dentro da categoria do usuário (0–100) | rolling calc |

### 1.2 Perfil do Usuário (User Profile Store)

Além das transações, mantenha um objeto de perfil atualizado para cada usuário — recalculado a cada nova sincronização:

| Campo do perfil | O que representa |
|---|---|
| `total_monthly_income` | Renda mensal estimada (salário + outros créditos regulares) |
| `income_stability_score` | 0–100: estabilidade da renda (CLT alto, freela baixo) |
| `top_5_categories_30d` | Top 5 categorias de gasto últimos 30 dias (% do total) |
| `travel_frequency_score` | 0–100: frequência de viagens nos últimos 12 meses |
| `lifestyle_clusters` | Lista de clusters atribuídos (ver Seção 3) |
| `life_stage` | Fase de vida detectada (ver Seção 4) |
| `credit_utilization_ratio` | Uso médio do limite de cartões |
| `savings_rate` | Taxa de poupança: (renda - gastos) / renda |
| `avg_transaction_value` | Ticket médio geral e por categoria |
| `peak_spend_day` | Dia do mês com maior concentração de gastos |
| `merchant_diversity_score` | 0–100: diversidade de estabelecimentos (alto = explorador) |
| `subscription_burn` | Total mensal em assinaturas recorrentes |
| `financial_stress_indicators` | Sinais de estresse financeiro (ver Seção 5) |
| `last_updated` | Timestamp da última atualização do perfil |

---

## 2. Detecção de Padrões de Vida com Base em Transações

Esta seção documenta os algoritmos de detecção de comportamento. Cada detector produz um score 0–100 ou um booleano, armazenado no User Profile Store.

### 2.1 Detector de Viajante Frequente

> 📌 **Por que importa:** Um usuário com score de viagem alto é o candidato ideal para um cartão de milhas (ex: Latam Pass Itaucard, Smiles Santander, C6 Jet). A recomendação certa pode gerar receita de afiliado e aumenta muito o NPS.

Sinais a combinar para calcular o `travel_frequency_score`:

- Transações com MCCs de companhias aéreas (MCC 3000–3350, 4511)
- Cobranças de agências de viagem online: Decolar, Booking, Expedia, Hurb, 123milhas (MCC 4722, 4723)
- Transações em hotéis (MCC 7011, 7012) ou pousadas
- Cobranças de Airbnb (MCC 7011, `merchant_name = "AIRBNB*"`)
- Locadoras de veículo: Localiza, Movida, Unidas (MCC 7512, 7513)
- VPR (Visa/Mastercard) no exterior: campo `currency != BRL`
- IOF de 6,38% em compras — sinal forte de transação internacional
- Seguros de viagem (MCC 6300, merchant keywords: `"SEGURO VIAGEM"`, `"ASSISTENCIA VIAGEM"`)
- Aplicativos de transfer aeroporto: UBER + horário 04h–07h em data próxima a voo detectado

```python
def calc_travel_score(txns_12m: list[Transaction]) -> float:
    travel_mccs = {3000..3350, 4511, 4722, 4723, 7011, 7512, 7513, 6300}
    travel_keywords = ["AIRBNB", "BOOKING", "DECOLAR", "LATAM", "AZUL",
                       "GOL", "EXPEDIA", "LOCALIZA", "MOVIDA", "HURB"]

    travel_txns = [t for t in txns_12m
                   if t.mcc in travel_mccs
                   or any(kw in t.merchant_normalized.upper() for kw in travel_keywords)
                   or t.currency != 'BRL']

    months_with_travel = len({t.date.month for t in travel_txns})  # 0–12
    travel_spend_ratio = sum(t.amount for t in travel_txns) / total_spend_12m
    foreign_txn_count  = sum(1 for t in travel_txns if t.currency != 'BRL')

    score = (
        (months_with_travel / 12) * 40 +   # regularidade
        min(travel_spend_ratio * 200, 40) + # intensidade de gasto
        min(foreign_txn_count * 4, 20)      # exposição internacional
    )
    return min(score, 100)
```

**Ações por faixa de score:**

| Score | Perfil | Ação Nexa |
|---|---|---|
| 0–30 | Viajante ocasional | Sugerir conta internacional (C6, Wise) ao detectar 1ª viagem |
| 31–60 | Viajante moderado | Recomendar cartão com milhas sem anuidade (LATAM Pass básico, Smiles básico) |
| 61–80 | Viajante frequente | Recomendar cartão premium com lounge + seguro viagem incluso |
| 81–100 | Viajante intenso | Sugerir múltiplos cartões de milhas + conta global + seguro viagem anual |

---

### 2.2 Detector de Usuário de Airbnb / Acomodação Alternativa

Diferente de hotéis tradicionais, usuários de Airbnb têm perfil de viagem diferente — geralmente estadas mais longas, destinos menos turísticos, sensibilidade a preço maior. Detectar esse padrão permite:

- Recomendar cartões com cashback alto em vez de milhas (melhor custo-benefício para estadias longas)
- Sugerir seguro de viagem com cobertura para cancelamento de Airbnb
- Identificar nômades digitais — segmento com necessidades financeiras específicas

**Padrão de detecção:**

- `merchant_name` contém `"AIRBNB"` → flag `is_airbnb_user = True`
- 3+ transações Airbnb em 12 meses → `airbnb_frequency = "regular"`
- Airbnb regular + renda não localizada em cidade base → sinal de nômade digital
- Airbnb + coworking (`"WEWORK"`, `"REGUS"`, `"SPACES"`, `"COWORKING"`) → perfil nômade confirmado

---

### 2.3 Detector de Gourmet / Entusiasta Gastronômico

Usuários que gastam alto em restaurantes ou delivery têm necessidades específicas de cartão — cashback em alimentação, programas de benefícios em restaurantes (Livelo, Clube Smiles).

- % dos gastos em alimentação (MCC 5812, 5813, 5814) > 25% do total
- Diversidade de restaurantes: `merchant_diversity_score` alto dentro da categoria → explorador gastronômico
- Delivery frequente: iFood, Rappi, Uber Eats, Loggi (`merchant_name` matching)
- Ticket médio em restaurantes > R$150 → fine dining → recomendar cartão com benefícios de jantar
- Restaurantes + eventos culturais (MCC 7922, 7929, 7941) → perfil urbano premium

---

### 2.4 Detector de Investidor Ativo

Usuários com movimentações regulares em corretoras têm necessidade de otimização tributária (T1, T2) e produtos de investimento. Detectar esse perfil aumenta muito o LTV.

- Transferências regulares para: XP, BTG, Rico, Clear, Modalmais, Genial (TED/PIX para CNPJ de corretoras)
- Compras de Tesouro Direto (`merchant_name`: `"TESOURODIRETO"`, `"STN"`, `"TESOURO NACIONAL"`)
- Dividendos e JCP recebidos (créditos com keyword `"DIVIDENDO"`, `"JCP"`, `"PROVENTO"`)
- Alta `savings_rate` + baixo gasto em consumo → investidor conservador
- Movimentações em múltiplas corretoras → investidor diversificado → candidato ideal para T1 (tax loss harvesting)

---

### 2.5 Detector de Microempreendedor (MEI/PJ)

Usuários com padrão de recebimentos irregulares mas altos, combinados com gastos em fornecedores, podem ser MEI disfarçados de PF — oportunidade para o F4 (Classificador PF/PJ) e para recomendação de conta PJ.

- Créditos com CNPJ de origem (transferências recebidas de empresas)
- Gastos em atacado/distribuidoras (MCC 5040–5199)
- Assinaturas de ferramentas B2B: NF-e, Omie, Conta Azul, Bling
- Gastos em plataformas de venda: Mercado Pago (taxas), iFood Parceiro, Rappi Partner
- Renda variável mês a mês com sazonalidade não-salarial

---

### 2.6 Detector de Pai/Mãe com Filhos

Um dos perfis de maior LTV. Famílias têm gastos previsíveis e alto interesse em planejamento financeiro de longo prazo (previdência, educação).

- Escolas e creches (MCC 8211, 8220, 8241, keyword `"ESCOLA"`, `"COLEGIO"`, `"CRECHE"`)
- Farmácias com padrão de compra de fraldas, fórmulas infantis (ticket alto + frequência)
- Pediatras e plano de saúde (MCC 8011, 8049, keyword `"PEDIATR"`, `"PLANO"`)
- Lojas de roupa infantil: Renner Kids, Hering Kids, Carter's, Posthaus
- Parques de diversão, brinquedotecas (MCC 7996, 7993, keyword `"MUNDO BITA"`, `"MAGIC CITY"`)
- Viagens em família: 2+ bilhetes de avião comprados simultaneamente + hotel com número de quartos inferido

---

## 3. Clustering de Estilo de Vida — Segmentação Comportamental

A Nexa deve atribuir a cada usuário um ou mais clusters de estilo de vida. Esses clusters são a base para personalizar o tom da comunicação, a ordem das funcionalidades apresentadas e a relevância das recomendações.

### 3.1 Arquitetura de Clustering

Usar K-Means ou HDBSCAN sobre o vetor de features do usuário. Recomendamos **HDBSCAN** por ser robusto a outliers e não exigir definir K previamente — útil na fase inicial quando não temos volume suficiente para validar K.

```python
# Normalizar tudo para 0–1 antes do HDBSCAN
feature_vector = {
    # Perfil de gasto por categoria (% do total)
    'pct_food':           ...,  # alimentação
    'pct_transport':      ...,  # uber, gasolina, transporte
    'pct_travel':         ...,  # voos, hotéis, airbnb
    'pct_health':         ...,  # academia, farmácia, plano
    'pct_education':      ...,  # cursos, escolas
    'pct_entertainment':  ...,  # streaming, shows, jogos
    'pct_shopping':       ...,  # roupas, eletrônicos
    'pct_investments':    ...,  # corretoras, tesouro

    # Comportamento
    'travel_score':         ...,  # 0–1
    'savings_rate':         ...,  # 0–1
    'income_stability':     ...,  # 0–1
    'merchant_diversity':   ...,  # 0–1
    'avg_ticket':           ...,  # normalizado pela renda
    'weekend_spend_ratio':  ...,  # gastos fim de semana / total
    'night_spend_ratio':    ...,  # gastos após 22h / total
    'subscription_ratio':   ...,  # assinaturas / total
}
```

### 3.2 Clusters Identificados

Com base no comportamento esperado da base brasileira, os seguintes clusters são prováveis de emergir:

| Cluster | Características principais | Produto prioritário Nexa |
|---|---|---|
| 🌍 Explorador Global | Alto `travel_score`, transações no exterior, Airbnb, lounge | Cartão de milhas premium, conta global |
| 🍕 Urbano Foodie | Alto `pct_food`, diversidade de restaurantes, delivery diário | Cashback em alimentação, clube gourmet |
| 💪 Saúde & Bem-estar | Academia, farmácia, suplementos, plano de saúde premium | Cartão com benefício farmácia, seguro saúde |
| 📚 Investidor Cauteloso | Alta `savings_rate`, aportes regulares, baixo consumo hedônico | T1/T2 Otimizador IR, LCI/LCA, previdência |
| 👨‍👩‍👧 Família Estruturada | Escola, pediatra, mercado, plano familiar, viagem 1x/ano | Cashback no supermercado, cartão família, previdência filho |
| 🎮 Digital Nativo | Streaming, games, e-commerce, pix 24h, nunca banco físico | Conta digital, cartão sem anuidade, crypto |
| 🏗️ Microempreendedor | Recebimentos PJ, fornecedores, plataformas de venda | Conta PJ, antecipação de recebíveis, separação PF/PJ |
| ⚠️ Estresse Financeiro | Rotativo do cartão, parcelamentos alto, queda de saldo | Renegociação D3, portabilidade D6, orçamento M1.3 |
| 🎓 Jovem Formando | Faculdade, transporte público, delivery, renda baixa | Educação financeira, meta de reserva, conta sem tarifa |

### 3.3 Uso dos Clusters no Produto

Uma vez que o usuário recebe seu cluster, o produto personaliza:

- **Dashboard:** ordem dos cards ajustada ao que é mais relevante para o cluster
- **Notificações (MX.3):** tom e gatilho ajustados ao cluster
- **F8 Radar de Produtos:** filtragem de recomendações por afinidade ao cluster
- **Onboarding:** narrativa adaptada ao perfil detectado
- **Score Nexa (F11):** pesos diferentes por cluster (ex: `savings_rate` pesa mais para Investidor)

---

## 4. Detecção de Eventos de Vida — Life Stage Intelligence

Eventos de vida são momentos de alta abertura para novos produtos financeiros. Um usuário que acabou de ter um filho provavelmente nunca vai estar tão aberto a falar sobre previdência. A Nexa precisa detectar esses momentos em tempo real.

### 4.1 Catálogo de Eventos de Vida Detectáveis

| Evento | Sinais detectores | Ação Nexa |
|---|---|---|
| 👶 Nascimento de filho | Farmácia (fraldas), maternidade, enxoval | Recomendar previdência infantil, seguro de vida |
| 🏠 Mudança de imóvel | Depósito de aluguel novo, gastos em loja de móveis/materiais | F3 Architect: financiamento vs aluguel |
| 💍 Casamento | Buffet, fotógrafo, vestido de noiva, lua de mel detectada | Conta conjunta, planejamento de metas |
| 🎓 Início na faculdade | Mensalidade universitária nova, moradia estudantil | Conta sem tarifa, FIES, controle de gastos |
| 🚗 Compra de veículo | Seguro novo, posto de gasolina recorrente, financeira | F3.5 consórcio, seguro auto comparativo |
| 💼 Novo emprego (melhor) | Aumento de crédito em conta, novo CNPJ empregador | Atualizar benchmark, recomendar investimento do aumento |
| 📉 Perda de renda | Queda abrupta de créditos, saque de FGTS detectado | MX.3 alerta, D6 portabilidade, negociação de dívidas |
| 🌎 Mudança para o exterior | Transações em moeda estrangeira, Airbnb longo no exterior | Conta global, cartão sem IOF, câmbio automático |

### 4.2 Implementação do Detector de Eventos

Cada evento é um conjunto de regras com threshold de confiança:

```python
def detect_new_baby(txns_recent: list, txns_history: list) -> dict:
    BABY_KEYWORDS = ["FRALDA", "PAMPERS", "HUGGIES", "JOHNSON BABY",
                     "MATERNIDADE", "ENXOVAL", "BEBE", "INFANTIL",
                     "KINDER", "NUTRILON", "NAN NESTLE"]
    BABY_MCCS = {5947, 5999, 5912}  # specialty stores, baby goods

    recent_baby_spend = sum(
        t.amount for t in txns_recent  # últimos 60 dias
        if any(kw in t.merchant_normalized.upper() for kw in BABY_KEYWORDS)
        or t.mcc in BABY_MCCS
    )
    historical_baby_spend = sum(
        t.amount for t in txns_history  # 6–18 meses atrás
        if any(kw in t.merchant_normalized.upper() for kw in BABY_KEYWORDS)
    )

    # Novo padrão: gasto em produtos de bebê que não existia antes
    new_pattern = recent_baby_spend > 200 and historical_baby_spend < 50

    return {
        'event': 'new_baby',
        'confidence': 0.85 if new_pattern else 0.0,
        'trigger_action': 'show_baby_financial_planning_card'
    }
```

---

## 5. Sinais de Estresse Financeiro — Early Warning System

O Early Warning System detecta sinais de deterioração financeira antes que o usuário perceba. Isso permite intervenção proativa — quando o usuário mais valoriza a plataforma e tem menor probabilidade de churnar.

### 5.1 Indicadores de Estresse (Ordem de Gravidade)

| Nível | Sinal detectado | Ação Nexa |
|---|---|---|
| 🟡 Nível 1 — Atenção | Uso do rotativo do cartão por 2 meses consecutivos | Notificar custo do rotativo, sugerir portabilidade de dívida |
| 🟡 Nível 1 — Atenção | Savings rate caindo por 3 meses seguidos | Revisar orçamento com M1.3 |
| 🟠 Nível 2 — Alerta | Saques em dinheiro crescendo (>20% dos gastos) | Detectar possível controle manual de gastos — envolver usuário |
| 🟠 Nível 2 — Alerta | Cheque especial usado >50% dos meses | Calcular custo e sugerir migração para empréstimo pessoal |
| 🔴 Nível 3 — Crítico | Atraso em contas recorrentes (fatura não paga detectada) | D6 portabilidade + negociador F6 |
| 🔴 Nível 3 — Crítico | Venda de investimentos + queda de renda simultânea | Modo defesa: congelar recomendações de produto, focar em proteção |
| 🔴 Nível 3 — Crítico | Saque de FGTS detectado | Alerta de emergência: reserva + renegociação |

### 5.2 Financial Stress Score (FSS)

O FSS é um índice único 0–100 (100 = máximo estresse) calculado como soma ponderada dos indicadores ativos:

```python
def calc_fss(profile: UserProfile, txns_90d: list) -> float:
    score = 0.0

    # Rotativo do cartão
    if profile.revolving_credit_months >= 2:
        score += 20 + (profile.revolving_credit_months - 2) * 5

    # Tendência de savings rate
    if profile.savings_rate_trend < -0.05:  # caindo > 5pp/mês
        score += 15

    # Uso de cheque especial
    overdraft_ratio = calc_overdraft_usage(txns_90d)
    score += overdraft_ratio * 25  # até 25 pontos

    # Concentração de parcelamentos no futuro
    future_installments_ratio = calc_future_commitment(txns_90d)
    if future_installments_ratio > 0.4:  # >40% da renda comprometida
        score += 20

    # Queda de renda
    income_drop = (profile.income_3m_avg - profile.income_12m_avg) / profile.income_12m_avg
    if income_drop < -0.15:  # queda > 15%
        score += 20

    return min(score, 100)
```

---

## 6. Inteligência Temporal — Padrões de Comportamento no Tempo

O tempo em que o usuário gasta é tão informativo quanto onde ele gasta. Padrões temporais revelam estilo de vida e permitem timing perfeito de comunicação.

### 6.1 Análise de Sazonalidade Pessoal

| Padrão temporal detectado | Interpretação e ação |
|---|---|
| Gastos concentrados no dia 5–10 | Data de pagamento de contas → enviar análise de orçamento antes |
| Pico de gastos em dezembro | 13º salário ou bônus → sugerir onde investir o extra |
| Queda em fevereiro | Pagamento de IPTU/IPVA → alertar em janeiro sobre o impacto |
| Pico em julho | Férias escolares → família com filhos confirmada |
| Gastos noturnos (22h–02h) frequentes | Perfil noturno → ajustar horário das notificações |
| Alta atividade nas segundas-feiras | Profissional liberal ou home office |
| Gastos homogêneos ao longo do mês | Planejador → aprecia relatórios de projeção |
| Gastos irregulares com picos esporádicos | Impulsivo → beneficia-se de alertas preventivos |

### 6.2 Timing Ideal de Comunicação

- **Alertas de cobrança indevida** → imediatamente após detectar (urgência justifica)
- **Recomendações de cartão** → depois de 3 meses de dados, quando o perfil está consolidado
- **Revisão de orçamento** → 3 dias antes da data histórica de maior gasto do usuário
- **Sugestão de investimento** → após crédito de salário detectado (+2 dias)
- **Notificação de Wrapped anual** → dezembro, quando o usuário tem mais emoção com o ano

---

## 7. Modelos de ML para Amplificar a Inteligência

Com volume de dados crescente, a Nexa pode introduzir modelos de ML que vão além das regras determinísticas.

### 7.1 Roadmap de Modelos ML

| Modelo | Descrição | Prioridade |
|---|---|---|
| Classificador de merchant | Categoriza merchants não mapeados por nome (NLP + fine-tuning em dados brasileiros) | Fase 1 — base de tudo |
| Detector de anomalia de gasto | Isolation Forest para detectar gastos atípicos em tempo real | Fase 1 — já parcialmente implementado |
| Propensity to churn | Gradient Boosting sobre engajamento + FSS + recência: prediz quem vai cancelar em 30 dias | Fase 2 — essencial para retenção |
| Recomendação de produto | Collaborative filtering: "usuários similares ao seu perfil contrataram X e economizaram R$Y" | Fase 2 — aumenta conversão |
| Detector de fraude bancária | One-class SVM sobre padrão de transações: detecta uso incomum que pode indicar fraude | Fase 2 — diferencial de segurança |
| Predição de gastos futuros | LSTM ou Prophet: prediz gastos dos próximos 30 dias por categoria | Fase 3 — safe-to-spend preciso |
| Score de negociação | Classifica probabilidade de sucesso de negociação com banco com base em histórico + perfil | Fase 3 — potencializa F6 |

### 7.2 Infraestrutura de ML Recomendada

Para o estágio atual (pré-seed → seed), a abordagem mais eficiente:

- **Feature Store:** PostgreSQL + tabela `user_features` atualizada a cada sync — simples e suficiente para até 50k usuários
- **Treinamento offline:** scikit-learn, XGBoost, LightGBM — portáveis, sem vendor lock-in
- **Serving:** `joblib` pickles servidos via FastAPI — zero overhead até 100k req/dia
- **Monitoramento:** log de features + predições em tabela separada para análise de drift
- **A/B testing:** flag de experimento no `user_profile` para testar variantes de recomendação
- **Embeddings de merchant:** `sentence-transformers` com fine-tuning em dados de MCC brasileiros

---

## 8. Motor de Recomendação Hiperpersonalizada

Todos os sinais coletados convergem para um motor de recomendação que prioriza e personaliza cada sugestão da Nexa.

### 8.1 Hierarquia de Recomendações

Toda recomendação da Nexa passa por um ranker que considera:

1. Relevância ao cluster e perfil atual **(peso 40%)**
2. Impacto financeiro estimado em R$ **(peso 30%)**
3. Probabilidade de conversão estimada pelo propensity model **(peso 20%)**
4. Timing: adequação ao momento de vida atual **(peso 10%)**

### 8.2 Exemplos de Recomendações Geradas pela Inteligência

> 🌍 **Exemplo 1 — Viajante com cartão errado**
>
> *"Você gastou R$4.200 em viagens nos últimos 6 meses usando um cartão sem programa de milhas. Com o Latam Pass Itaucard Platinum, você teria acumulado 8.400 milhas — o suficiente para uma passagem nacional de ida. A anuidade de R$399 seria paga em menos de 3 meses de uso no seu padrão atual."*

> 🍕 **Exemplo 2 — Foodie com cashback perdido**
>
> *"Seu gasto médio em alimentação é R$1.800/mês — 28% da sua renda. Seu cartão atual não dá cashback em alimentação. O Nubank Ultravioleta devolve 1% ilimitado, o que significaria R$216/ano de volta só nessa categoria."*

> 👶 **Exemplo 3 — Evento de vida: novo filho**
>
> *"Detectamos gastos em produtos de bebê nos últimos 60 dias. Parabéns pela chegada de um novo membro da família! Um plano de previdência privada de R$200/mês iniciado hoje pode acumular R$180.000 em 18 anos — na hora da faculdade."*

> ⚠️ **Exemplo 4 — Estresse financeiro detectado**
>
> *"Identificamos que você pagou apenas o mínimo do cartão por 3 meses consecutivos, gerando R$620 em juros. Seu banco atual cobra 18,9%/mês no rotativo — acima da média BACEN de 14,2%. Podemos ajudar a negociar uma portabilidade de dívida com taxa menor."*

---

## 9. Privacidade, Ética e Governança dos Dados

O nível de inferência descrito neste documento exige responsabilidade proporcional. A Nexa só pode usar inteligência comportamental de forma que beneficie ativamente o usuário — nunca para discriminação, venda de dados ou pressão.

### 9.1 Princípios de Uso Ético

- **Transparência:** o usuário pode ver quais clusters e scores foram atribuídos a ele (via perfil na app)
- **Controle:** o usuário pode optar por não ser classificado em determinadas categorias sensíveis
- **Benefício direto:** toda inferência só é usada para recomendar produtos que beneficiem financeiramente o usuário
- **Sem venda de dados:** perfis comportamentais são propriedade do usuário e nunca vendidos a terceiros
- **Minimização:** coletar apenas o necessário para a funcionalidade — evitar feature creep

### 9.2 Conformidade com LGPD e Open Finance

- **Consentimento granular:** o usuário autoriza explicitamente cada tipo de análise no onboarding
- **Portabilidade:** exportar o perfil comportamental completo sob demanda (LGPD art. 18)
- **Exclusão:** deletar todos os dados derivados quando o usuário cancelar (LGPD art. 16)
- **BACEN Res. Conjunta 1/2020:** respeitar escopos de dados autorizados pelo usuário no Open Finance
- **Armazenamento mínimo:** scores e clusters têm vida útil de 90 dias sem nova sync

---

## 10. Roadmap de Implementação

### 10.1 Fases de Desenvolvimento

| Fase | Entregas | Foco técnico |
|---|---|---|
| **Fase 1** (0–3 meses) | Feature Store básico; detecção de viajante, foodie, investidor; clustering K-Means com 5 clusters; perfil de usuário persistido | Enriquecimento do ETL + tabela `user_features` |
| **Fase 2** (3–6 meses) | Life Events detector; FSS (Financial Stress Score); motor de recomendação com ranker; personalização do dashboard por cluster | Motor de recomendação + regras de life events |
| **Fase 3** (6–12 meses) | Propensity to churn; predição de gastos futuros (Prophet); collaborative filtering; A/B testing framework | ML pipeline completo + feature monitoring |

### 10.2 Métricas de Sucesso da Inteligência

| Métrica | Meta |
|---|---|
| Precisão do cluster | >80% de usuários concordam com o cluster atribuído (survey in-app) |
| Conversão de recomendações | >15% de recomendações de produto resultam em ação do usuário |
| Detecção de life events | >70% dos eventos de vida detectados confirmados pelo usuário |
| Redução de churn | Usuários que recebem recomendação relevante têm churn 30% menor |
| Cobertura de merchant | >95% das transações com categoria L2 atribuída corretamente |
| Latência do perfil | User profile atualizado em <5 minutos após nova sync |

---

## Conclusão: Da Transação ao Perfil Humano

Cada PIX, cada parcela de cartão, cada assinatura de streaming é um pixel de um retrato financeiro do usuário. A Nexa tem acesso a todos esses pixels via Open Finance. A inteligência descrita neste documento é o algoritmo que converte esses pixels em um retrato de alta resolução — e esse retrato é o que torna a Nexa irreplicável.

Bancos veem fragmentos. A Nexa vê o todo. E com o todo, podemos fazer o que nenhum banco pode: trabalhar 100% a favor do usuário, com informação perfeita.

> 🚀 **O flywheel de inteligência:** Mais usuários → mais dados comportamentais → melhor clustering e detecção de padrões → recomendações mais precisas → maior economia para o usuário → maior retenção → mais usuários. Cada mês de histórico que a concorrência não tem é um fosso que se aprofunda.

---

*Nexa AI — Inteligência a favor do usuário, não do banco.*