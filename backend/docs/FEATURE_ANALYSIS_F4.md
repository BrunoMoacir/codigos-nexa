# 📊 Descobertas e Features Selecionadas - F4 Divider PF/PJ

**Data:** February 13, 2026  
**Status:** Subpassos 1.1-1.6 Concluídos ✅  
**Próximo:** Subpasso 1.7 - Treinar modelo Random Forest

## 🎯 Objetivo
Desenvolver classificador automático para distinguir transações **Pessoais (PF)** vs **Empresariais (PJ)** usando Machine Learning, com regras como fallback.

## 📈 Análise Estatística dos Dados Mock (25 transações)

### Distribuição dos Dados
- **Total:** 25 transações (15 PF + 10 PJ)
- **Balanço:** 60% PF, 40% PJ (representativo da realidade brasileira)

### 🔍 Padrões Identificados

#### 1. **Temporal**
- **PF:** Concentrado no período vespertino/noturno (14h-20h)
  - Top horas: 14h, 16h, 19h
  - Mais fins de semana (sábado/domingo)
- **PJ:** Concentrado em horário comercial (6h-15h)
  - Top horas: 6h, 8h, 10h, 14h
  - Predominantemente dias úteis

#### 2. **Monetário**
- **PF:** Valores menores, mais variáveis
  - Média: R$ 1500 (absoluto)
  - 67% abaixo de R$ 100
  - Máximo: R$ 2346
- **PJ:** Valores significativamente maiores
  - Média: R$ 8500 (absoluto)
  - 80% acima de R$ 500
  - Máximo: R$ 8500 (salário)

#### 3. **Textual**
- **Discriminação alta** com keywords específicas
- **PF Keywords:** uber, netflix, restaurante, shopping, etc.
- **PJ Keywords:** empresa, ltda, fornecedor, aluguel, etc.
- Score de keywords: 0-2 matches por transação

#### 4. **Categórico**
- **PF:** ENTERTAINMENT, FOOD, HEALTH, TRANSPORT
- **PJ:** SALARY, OFFICE_SUPPLIES, RENT, SOFTWARE, CONSULTING
- Categorias exclusivas PJ: SALARY, OFFICE_SUPPLIES

## 🛠️ Features Selecionadas para ML

### Temporais (4 features)
- `hour_of_day`: Hora da transação (0-23)
- `day_of_week`: Dia da semana (1=Seg, 7=Dom)
- `is_weekend`: Flag fim de semana (0/1)
- `is_business_hour`: Flag horário comercial 9-17h (0/1)

### Monetárias (5 features)
- `amount`: Valor original (positivo/negativo)
- `amount_abs`: Valor absoluto
- `amount_log`: Log do valor absoluto (+1)
- `transaction_type`: "credit" ou "debit"
- `amount_category`: "very_low", "low", "medium", "high", "very_high"

### Textuais (3 features)
- `pf_keyword_score`: Contagem de keywords PF na descrição
- `pj_keyword_score`: Contagem de keywords PJ na descrição
- `has_business_terms`: Flag presença de termos empresariais

### Categóricas (2 features)
- `category`: Categoria original da transação
- `merchant_category`: Categoria agrupada do merchant

### Recorrência (1 feature)
- `is_recurring`: Flag de transação recorrente (simulado)

## 📊 Dataset de Treinamento
- **Arquivo:** `data/training_dataset_pf_pj.parquet`
- **Formato:** 25 amostras × 19 colunas
- **Target:** `label` ("PF" ou "PJ")
- **Features:** 18 (mix numérico + categórico)

## 🎯 Estratégia de Classificação
1. **ML Primário:** Random Forest com todas as features
2. **Fallback:** Regras baseadas em:
   - Keywords empresariais → PJ
   - Categorias exclusivas PJ → PJ
   - Valores muito altos → PJ
   - Horários não-comerciais + valores baixos → PF

## 📈 Expectativas de Performance
- **Accuracy esperada:** 90-95% nos dados mock
- **Features mais importantes:** amount_abs, pj_keyword_score, category
- **Limitações:** Dataset pequeno (25 amostras) - expansão necessária

## 🚀 Próximos Passos
1. **Subpasso 1.7:** Treinar modelo Random Forest
2. **Subpasso 1.8:** Validar performance e ajustar hiperparâmetros
3. **Subpasso 1.9:** Implementar regras de fallback
4. **Subpasso 1.10:** Integrar no pipeline ETL

---
*Documentação gerada automaticamente em 13/02/2026*