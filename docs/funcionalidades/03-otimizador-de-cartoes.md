# 03 — Otimizador de Cartões (F2)

> Descobre quanto dinheiro o usuário deixa na mesa usando o cartão errado — e
> recomenda o cartão certo para o perfil real de gastos dele.

## Em palavras simples

A maioria das pessoas escolhe cartão por propaganda, não por matemática. A
Nexa olha onde você realmente gasta (mercado? iFood? viagem?) e calcula, em
R$/mês, quanto cada cartão do mercado devolveria em cashback ou milhas — 
descontando anuidade e considerando se você é elegível (renda mínima). O
resultado: "trocando para o cartão X você recupera R$ 84/mês".

## O que faz

- **Base de conhecimento**: 81 cartões de 37 emissores
  (`data/cards/knowledge_cards.json`) — dos digitais gratuitos (Nubank,
  PagBank, Will) aos premium (Visa Infinite, Elo Nanquim), co-branded aéreos
  (Azul Itaú, LATAM Pass, Smiles), varejo (Magalu, Carrefour, Stix), inclusive
  cartão garantido (secured) e consignado. Cada registro: anuidade, regras de
  isenção, cashback flat e **por categoria** (com tetos), pontos/R$, programa
  de fidelidade, juros do rotativo, `data_trust_score`.
- **Ranking personalizado** (`optimizer/ranking.py`): ganho líquido anual
  esperado por cartão = recompensas sobre o gasto real do usuário − anuidade
  efetiva (considerando regras de isenção) + bônus por tendência de categoria.
- **Valoração de milhas** (`miles_valuator.py`): 11 programas com cenários
  P25/P50/P75 (pessimista/esperado/otimista) — ranking usa o conservador,
  usuário vê o esperado.
- **Multi-cartão** (`multi_card_strategy.py`): qual combinação de 2 cartões
  maximiza retorno por categoria.
- **Custo de oportunidade** (`opportunity_cost.py`): quanto foi perdido nos
  últimos meses por usar o cartão errado.
- **Elegibilidade** (`card_loader.py::compute_eligibility_score`): renda
  mínima, estabilidade de gastos, relacionamento prévio com o emissor.
- **Explicabilidade forte** (`RecommendationExplanation`): por que ESTE cartão
  — categoria dominante, taxa aplicada, breakdown por categoria, confiança da
  classificação.
- **Insights acionáveis** (`insight_generator.py`): cards WAIVER_ALERT
  ("faltam R$ X para isentar a anuidade"), MUDAR_CATEGORIA, CARD_OPPORTUNITY.
- **Promoções de transferência** (`promotion_tracker.py`, parcial): bônus
  ≥20% em transferências de pontos.

## Como funciona (técnico)

- **Endpoints**: `POST /optimizer/recommend`, `/simulate`, `/multi_card`,
  `/opportunity_cost`; `GET /optimizer/cards`, `GET /optimizer/roi/{card_id}`.
- Fluxo do `optimizer_service.py`: enriquece transações
  (`TransactionFeatureEnricher` — categoria canônica, merchant normalizado) →
  `profiler.py` constrói `UserProfile` → simulador calcula retorno por cartão
  (`simulator.py`, regras por categoria M2.5) → ranking + explicações.
- Feedback loop: `models_orm.py` persiste relatórios; `recommendation_feedback`
  registra aceite/rejeição para calibração futura.
- Categorias de cashback usam o vocabulário canônico do classificador
  (`alimentacao`, `supermercado`, `farmacia`, `viagem`, `transporte`,
  `streaming`...) — regra de integridade: categoria fora do vocabulário nunca
  casaria com gasto real.

## O que NÃO faz

- **Não solicita o cartão pelo usuário** — recomenda e explica; a contratação
  é no canal do emissor (`request_link` quando disponível).
- **Não conhece o limite aprovado** que o usuário teria — elegibilidade é
  estimativa por renda/estabilidade, não consulta ao bureau.
- **Não rastreia pontos acumulados** nos programas (saldo de milhas do
  usuário não é lido — Open Finance não expõe).

## Gaps e limitações

- **Base curada manualmente**: benefícios de cartão mudam com frequência;
  cada registro tem `last_updated` e `data_trust_score`, mas não há job de
  revisão automática (recomendado: revisão trimestral; não existe API pública
  de metadados de cartões no Brasil).
- **PromotionTracker parcial** (R4.b): estrutura existe, cobertura de
  promoções é manual.
- Cobertura: 81 cartões cobre o mercado relevante, mas não a cauda longa
  (regionais pequenos, variantes corporativas).
