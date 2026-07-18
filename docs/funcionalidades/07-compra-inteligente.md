# 07 — Compra Inteligente (F7 / R1.a)

> No momento de pagar: Pix, débito, crédito à vista, parcelado ou CDC?
> Veredito em uma frase, com o custo líquido de cada opção.

## Em palavras simples

"Parcela em 12x sem juros ou paga no Pix com desconto?" — quase ninguém faz
essa conta, e ela muda com o SEU cartão (cashback), o SEU caixa (margem
segura) e o tamanho da compra. A Nexa responde na hora: "Pague com o cartão X
à vista — custo líquido R$ 2.940, R$ 180 mais barato que a pior opção. Cabe
no seu orçamento".

## O que faz

- **Análise completa** (`POST /purchase/analyze`): compara Pix à vista,
  cartão à vista (com o melhor cartão do usuário via F2), parcelado sem juros
  e crédito pessoal CDC (para compras ≥ R$ 1.000 em 6+ parcelas). Ranking por
  **custo líquido** (custo total − valor das recompensas) + impacto na margem
  segura (F1).
- **Checkout-context** (`GET /purchase/checkout-context/{user_id}`): a mesma
  inteligência em resposta compacta para o momento da compra — veredito em
  uma frase, opção recomendada, risco de liquidez, lista curta de opções.
  Pensado para modal, share-sheet mobile ou extensão de navegador.
- **Revisão retroativa** (`GET /purchase/recent-review/{user_id}`): varre as
  compras à vista ≥ R$ 300 dos últimos 14 dias e calcula quanto o usuário
  perdeu pagando do jeito subótimo — vira card `PURCHASE_FOLLOWUP` no feed e
  tool `review_recent_purchases` no chat ("aprende com o passado").

## Como funciona (técnico)

- `purchase/purchase_advisor.py` monta as opções, consulta o optimizer (melhor
  cartão/categoria), o cashflow (margem segura, risco) e taxas CDC de mercado.
- Confiança: `confidence_score` na resposta reflete a qualidade dos dados
  do usuário (histórico curto → confiança menor, dito explicitamente).
- Gating: 3 consultas/mês no plano Free (contador `purchase_checks`).

## O que NÃO faz

- **Não conhece promoções do lojista** (desconto Pix específico da loja) — o
  usuário informa o preço de cada modalidade se quiser precisão máxima.
- **Não executa o pagamento**.
- **Não recomenda rotativo/parcelamento de fatura** — nunca; se não cabe, o
  veredito é "não cabe", com o impacto mostrado.

## Gaps e limitações

- CDC usa taxa média de mercado (BACEN) — a taxa real do usuário pode ser
  melhor/pior; o Negociador (doc 08) ajuda a melhorar.
- A revisão retroativa olha 14 dias e compras ≥ R$ 300 (constantes de
  produto) — janelas maiores viram ruído.
