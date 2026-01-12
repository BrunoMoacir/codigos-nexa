
# 🏗️ Nexa AI — Core Engine (Funcionalidade 1)
## Fluxo de Caixa, Previsão & Inteligência Ativa

> **Status:** MVP (Fase 1)  
> **Stack:** Python 3.11+, Polars, PyTorch, NeuralProphet, CatBoost, LangGraph  
> **Princípio Central:** *O dado oficial vem primeiro. Se falhar, o sistema se adapta.*  
> **Mantra:** **Matemática determinística calcula. IA generativa explica.**

---

## 🎯 Visão Geral

O Core Engine da Nexa é responsável por transformar transações bancárias em **decisões financeiras acionáveis**.  
Não somos um chatbot financeiro. Somos um **Agente Financeiro Autônomo**, capaz de prever cenários futuros mesmo quando dados bancários são incompletos ou instáveis.

O sistema foi desenhado desde o início para conviver com a realidade do Open Finance brasileiro.

---

## 🧠 Estratégia Central — *Shadow Invoice* (Fatura Sombra)

A Nexa sempre segue esta ordem de decisão:

### 🥇 1️⃣ Fonte Primária — Dados Oficiais do Banco
Sempre que disponíveis, utilizamos:
- Extrato bancário
- Transações confirmadas
- Fatura aberta / future invoice

Esses dados **têm prioridade absoluta**, desde que passem por validações internas de consistência.

---

### ⚠️ 2️⃣ Validação de Consistência
Antes de confiar no dado oficial, o Core Engine executa verificações como:
- Completude do período
- Coerência de datas e valores
- Histórico mínimo disponível
- Estabilidade conhecida da API da instituição

Se qualquer regra crítica falhar, o dado é marcado como **UNTRUSTED**.

---

### 🥈 3️⃣ Fallback Inteligente — *Shadow Invoice*
Quando o dado oficial:
- Não existe  
- Está incompleto  
- Está inconsistente  
- Ou a API do banco é instável  

A Nexa ativa automaticamente a **Shadow Invoice**.

> **Shadow Invoice é uma projeção matemática da fatura futura, calculada localmente a partir do histórico real do usuário.**

O usuário nunca fica sem resposta.

---

## 🔍 Como a Shadow Invoice é Calculada

A projeção se baseia em três padrões matematicamente detectáveis:

### 1️⃣ Parcelamentos (A Chave de Ouro)
Detectamos padrões explícitos como:
- `01/10`
- `1/10`
- `01 de 10`

Exemplo:
```

MAGALU *COMPRA 01/10 → MAGALU *COMPRA 02/10

````

O sistema projeta automaticamente a próxima parcela, mantendo:
- Merchant
- Valor
- Dia aproximado do mês

📌 Sem PDF. Sem OCR. 100% determinístico.

---

### 2️⃣ Assinaturas Recorrentes
Identificamos recorrências quando:
- Mesmo merchant
- Frequência mensal
- Baixa variação de data (desvio < 4 dias)
- Presença em ≥ 3 meses

O Nexa cria uma **linha virtual futura** na data correta.

---

### 3️⃣ Gastos Variáveis (Colchão de Liquidez)
Para categorias variáveis (Uber, Mercado, Lazer):
- Média móvel dos últimos 60–90 dias
- Ajuste por sazonalidade
- Percentil de segurança (p50 / p70)

Isso evita subestimar a fatura futura.

---

## 🧩 Estratégia por Banco (Design Pattern: Strategy)

Cada instituição financeira possui um **adaptador próprio**, que define o nível de confiança nos dados oficiais.

```python
class BankStrategy:
    def predict_invoice(self, history, api_data):
        raise NotImplementedError


class NubankStrategy(BankStrategy):
    def predict_invoice(self, history, api_data):
        if api_data and api_data.is_consistent():
            return api_data
        return project_from_history(history)


class BradescoStrategy(BankStrategy):
    def predict_invoice(self, history, api_data):
        return project_from_history(history)
````

Essa abordagem evita `if/else` espalhados pelo código e permite tuning fino por banco.

---

## 🧠 Funcionalidades Ativas Geradas pelo Core Engine

Essas funcionalidades **não são módulos separados**.
Elas são **saídas diretas do mesmo motor de previsão**.

---

### 💰 Quanto Posso Gastar Hoje? (*Safe-to-Spend*)

**Pergunta respondida:**

> *“Quanto posso gastar hoje sem comprometer meu mês?”*

Cálculo diário baseado em:

* Saldo atual
* Despesas futuras previstas (recorrências + Shadow Invoice)
* Margem de segurança

```
Safe-to-Spend = Saldo Atual − (Despesas Previstas + Margem)
```

---

### 🧾 Resumo Semanal dos Gastos

**Pergunta respondida:**

> *“O que mudou no meu financeiro essa semana?”*

Geração automática com:

* Total gasto vs semana anterior
* Principais categorias
* Gastos fora do padrão
* Impacto no fluxo de caixa futuro

Exemplo:

> “Você gastou 12% mais esta semana.
> Isso reduz seu Safe-to-Spend da próxima semana em R$ 180.”

---

### 🕳️ Identificação de Gastos Invisíveis

**Pergunta respondida:**

> *“Para onde meu dinheiro está vazando sem eu perceber?”*

O sistema detecta:

* Pequenos valores recorrentes
* Assinaturas esquecidas
* Parcelamentos antigos ainda ativos
* Vazamentos financeiros de baixo valor unitário, mas alto impacto acumulado

---

## 🚨 Expiração de Token & Resiliência

Se a conexão Open Finance expirar:

* **T-30:** aviso preventivo
* **T-7:** alerta crítico
* **T-0:** sistema entra em modo Shadow Invoice com aviso explícito

O sistema nunca para. Apenas reduz o nível de certeza e comunica isso claramente.

---

## 🧠 Regras de Ouro do Core Engine

1. O dado oficial sempre vem primeiro
2. Se o dado falhar, a matemática assume
3. Nenhum número é inventado
4. Toda previsão possui impacto mensurável
5. IA explica — nunca calcula

---

## 🧾 Resumo Executivo

> **A Nexa não mostra apenas gráficos.
> Ela responde perguntas reais:
> quanto posso gastar, o que mudou e onde estou perdendo dinheiro.
> Sempre — mesmo quando o banco falha.**

```

Se quiser, no próximo passo posso:
- Ajustar esse README para **versão pública vs interna**
- Criar o **README da Funcionalidade 2 já conectado**
- Gerar **diagramas de arquitetura**
- Escrever **ADRs oficiais (Architecture Decision Records)**
```
