# 🏦 Nexa AI: The Autonomous Financial Agent

> **Status:** MVP Development 🚧
> **Mission:** Democratizar a inteligência financeira de "Family Offices" para o brasileiro comum através de IA Generativa e Matemática Determinística.

A Nexa não é apenas um organizador financeiro. É um **Agente Ativo** que prevê o futuro (Fluxo de Caixa) e otimiza o presente (Cartões e Taxas) conversando naturalmente com o usuário.

---

## 📚 Documentação Técnica (Specs)

A documentação de engenharia está dividida por módulos funcionais. Time de desenvolvimento, sigam a ordem abaixo:

### 1. [Core Engine & Ingestão (Funcionalidade 1)](docs/specs/01_CORE_ENGINE.md)
* **Foco:** Ingestão de dados (Open Finance), Limpeza (Polars), Classificação Waterfall e a Interface do Chat (LangGraph).
* **Stack:** Polars, CatBoost, LangGraph.
* **Foco:** O "GPS Financeiro". Algoritmos híbridos (NeuralProphet + Determinístico) para projetar o saldo dos próximos 30 dias.
* **Stack:** PyTorch, NeuralProphet.

### 2. [Otimizador de Crédito (Funcionalidade 2)](docs/specs/03_OPTIMIZER.md)
* **Foco:** Sistema de recomendação que analisa gastos e sugere cartões com melhor retorno (Milhas/Cashback).
* **Stack:** Scikit-learn, Rule-based Engine.

---

## 🛠️ Tech Stack Principal

| Área | Tecnologia | Motivo |
| :--- | :--- | :--- |
| **Backend** | Python 3.11+ | Ecossistema de IA robusto. |
| **Data Processing** | Polars (Rust) | Performance extrema para ETL financeiro. |
| **Agent Orchestration** | LangGraph | Controle de estado e loops complexos de conversa. |
| **ML Models** | CatBoost & NeuralProphet | O melhor para dados tabulares e séries temporais. |
| **Database** | PostgreSQL | Relacional robusto para transações financeiras. |

## 🚀 Como Rodar Localmente

1. Clone o repositório.
2. Instale as dependências: `pip install -r requirements.txt`
3. Configure o `.env` (veja `.env.example`).
4. Suba o banco: `docker-compose up -d`
5. Inicie a API: `uvicorn app.main:app --reload`

---
*Nexa AI Engineering Team © 2026*
