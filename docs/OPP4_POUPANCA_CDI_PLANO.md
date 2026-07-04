# OPP.4 — Identificação de Poupança Abaixo do CDI — Plano de Desenvolvimento

> **Escopo:** este documento cobre exclusivamente a sub-feature OPP.4 do vertical OPP
> (`docs/ROADMAP.md`, linha "OPP.4 | Identificação de poupança abaixo do CDI | A desenvolver"). Não
> repete `docs/OPP.md` sobre catálogo CDB/LCI/LCA, motor de IR ou scorecard por banco, nem
> `docs/OPP1_DINHEIRO_PARADO_PLANO.md` sobre detecção de dinheiro parado em conta corrente.
> **Status geral:** OPP já tem MVP backend implementado (`backend/app/opportunities/`), mas a
> capacidade específica de poupança vs. CDI ainda é greenfield. O risco principal não é a comparação
> matemática; é a incerteza de dado para personalização com saldo real.
> **Superfícies de produto do roadmap:** OPP.4 deve alimentar somente (1) Feed/Notificações de
> oportunidades e (2) Agente IA com tools financeiras. Não criar tela standalone, dashboard próprio,
> onboarding paralelo ou experiência fora desses canais.
> **Auditado contra o código real em 2026-07-04.**

---

## 1. Especificação alvo

O ROADMAP não detalha a lógica desta sub-feature; ele só diz "Identificação de poupança abaixo do
CDI". A leitura correta dentro da missão do OPP ("detectar dinheiro parado rendendo pouco e comparar
instituições sem viés") é:

> Calcular quanto a poupança rende hoje, comparar contra CDI líquido/alternativas de baixo risco e
> quantificar a perda de oportunidade de forma acionável, sem inventar saldo de usuário quando esse
> dado não existir.

Há duas perguntas de produto, com maturidades diferentes:

| Pergunta | Nome neste plano | Depende de dado do usuário? | Entregável agora? |
|---|---|---:|---:|
| "Quanto a poupança rende hoje e quanto perde para o CDI?" | Comparação genérica | Não | Sim |
| "Eu tenho R$ X na poupança e estou perdendo quanto?" | Comparação personalizada | Sim, saldo real de poupança | Só após spike Pluggy/saldo real |

**Decisão:** entregar primeiro a comparação genérica, porque ela já agrega no agente e no feed sem
depender de saldo real. A personalização entra depois, junto com a iniciativa de persistência de
saldo real já registrada no OPP.1.

---

## 2. Estado real do código — o que existe e o que é aparência

| Peça necessária | Estado real | Onde |
|---|---|---|
| Fórmula oficial da poupança | **Não existe.** Há apenas um número fixo | `backend/app/fiscal/services/tax_radar.py` (`poupanca_rate = 6.17`) |
| SELIC usada pelo protótipo de poupança | Também hardcoded, não vem do `BacenConnector` | `tax_radar.py` (`self._selic_rate_pct = 11.25`) |
| Conector BACEN para TR | **Não existe.** `BacenConnector` só expõe SELIC 432/4390 | `backend/app/architect/connectors/bacen.py` |
| CDI real | Existe e já é usado pelo OPP | `backend/app/architect/connectors/anbima.py` |
| `tax_radar.py` em produção | **Não.** Não está conectado a router/tool do agente; só tem teste próprio com `MockAsset` | `backend/tests/fiscal/test_tax_radar.py` |
| Mapeamento `POUPANCA` em investimentos | Existe, mas não prova que o Pluggy entrega poupança por esse caminho | `backend/app/tax/services/investment_profiler.py` |
| Mock Pluggy com poupança | **Não existe.** O mock atual só cobre conta corrente no exemplo de contas | `backend/app/core/integrations/pluggy_mock.py` |
| Persistência de saldo de conta | **Não existe.** `get_accounts()` retorna `balance`, mas os fluxos atuais descartam/pouco reutilizam isso | `backend/app/core/integrations/pluggy.py`, `backend/app/runner.py` |

**Conclusão:** o projeto tem bons blocos de base (CDI, SELIC, padrão de conector, OPP engine), mas
não tem uma fonte de verdade para "taxa da poupança hoje" nem uma fonte confiável para "saldo real
de poupança do usuário". OPP.4 não deve reaproveitar o hardcode do `tax_radar.py` como se fosse
implementação.

---

## 3. O que pode ser reaproveitado com confiança

- `AnbimaConnector.get_cdi()` — CDI real, já usado em `OpportunityEngine`.
- `BacenConnector.get_selic()` — SELIC real via BACEN SGS, com fonte secundária e fallback.
- `BaseConnector` — cache, fallback e contrato de erro já estabelecidos para conectores financeiros.
- `IRPFCalculator` — já modela isenção de `"POUPANCA"` quando necessário, mas não calcula a taxa da
  poupança. Não duplicar tabela de IR nem simulação líquida fora dele sem motivo.
- `backend/app/opportunities/` — módulo correto para expor a comparação no contexto do Radar.
- `app/agent/tools/get_opportunities.py` — superfície natural para o agente falar de poupança vs.
  CDI, sem criar nova tool se a resposta puder ser agregada ao Radar de Oportunidades.
- `notifications/` e futuro Feed — superfícies planejadas para apresentar o insight quando houver
  impacto financeiro relevante.

---

## 4. Decisão de arquitetura

### Opção A — Comparação genérica, agora

Com dados públicos:

1. Buscar CDI atual.
2. Buscar SELIC atual.
3. Buscar TR atual.
4. Calcular taxa da poupança.
5. Comparar poupança vs. CDI/alternativa de referência.
6. Gerar mensagem para agente/feed com exemplo padrão em reais.

Essa opção é útil mesmo sem saber se o usuário tem poupança: ela responde "vale deixar dinheiro na
poupança hoje?" e pode ser usada pelo agente quando a pessoa perguntar sobre poupança, CDI, CDB ou
Tesouro Selic.

### Opção B — Comparação personalizada, depois

Com saldo real:

1. Descobrir se poupança vem de `PluggyClient.get_accounts()` ou `PluggyClient.get_investments()`.
2. Persistir saldo real de conta/investimento com `account_type`/`subtype` confiável.
3. Calcular perda mensal/anual sobre o saldo real.
4. Gerar oportunidade `PERSONALIZED_CONFIRMED` para feed/notificação.

Essa opção converge com a Opção B do OPP.1: persistência de saldo real via Pluggy. Não deve ser
orçada duas vezes nem implementada como atalho específico de OPP.4.

---

## 5. Contrato da Opção A

### 5.1 Contrato de domínio

Criar uma fonte única para taxa da poupança e comparação:

```python
class SavingsRateResult(BaseModel):
    selic_annual: float
    tr_monthly: float
    savings_monthly: float
    savings_annual: float
    rule_branch: Literal["SELIC_GT_8_5", "SELIC_LTE_8_5"]
    source: Literal["BACEN", "FALLBACK"]
    generated_at: datetime


class SavingsVsCdiResult(BaseModel):
    amount_reference_brl: float
    savings_annual_pct: float
    cdi_annual_pct: float
    cdi_reference_annual_pct: float
    spread_pct_points: float
    estimated_loss_monthly_brl: float
    estimated_loss_annual_brl: float
    status: Literal[
        "BELOW_CDI",
        "NEAR_CDI",
        "NO_ADVANTAGE",
        "DATA_UNAVAILABLE",
    ]
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    reason: str
    generated_at: datetime
```

Notas:

- `amount_reference_brl` deve ter default documentado, sugerido: `10_000`.
- `cdi_reference_annual_pct` pode ser CDI bruto ou CDI líquido simulado; a escolha precisa ficar
  explícita no nome, na docstring e na resposta.
- Poupança é isenta de IR; se comparar com CDB/CDI bruto, a mensagem deve dizer que é uma referência
  de mercado, não promessa líquida de produto.
- A taxa da poupança deve ser anualizada a partir da regra mensal. Não misturar taxa mensal com taxa
  anual no mesmo campo.

### 5.2 Regra da poupança

Implementar como função pura, com testes de fronteira:

```python
def calculate_savings_rate(selic_annual: float, tr_monthly: float) -> SavingsRateResult:
    ...
```

Regra esperada, a validar em fonte oficial antes do merge:

- se SELIC meta anual > 8,5%: remuneração mensal = 0,5% + TR;
- se SELIC meta anual <= 8,5%: remuneração mensal = 70% da SELIC meta mensalizada + TR;
- anualizar por composição mensal;
- `tr_monthly` entra como decimal mensal, nunca percentual textual.

**Não aceitar PR** que copie `poupanca_rate = 6.17` ou `self._selic_rate_pct = 11.25`.

### 5.3 Contrato de API/backend

Preferência: criar serviço dedicado em `backend/app/opportunities/services/savings_vs_cdi.py` e expor
um endpoint leve em `opportunities/router.py`, por exemplo:

```http
GET /api/v1/opportunities/savings-vs-cdi?amount_reference_brl=10000
```

Resposta mínima:

```json
{
  "amount_reference_brl": 10000,
  "savings_annual_pct": 0.0,
  "cdi_annual_pct": 0.0,
  "spread_pct_points": 0.0,
  "estimated_loss_monthly_brl": 0.0,
  "estimated_loss_annual_brl": 0.0,
  "status": "BELOW_CDI",
  "severity": "MEDIUM",
  "reason": "Para cada R$ 10.000 na poupança, a diferença estimada para CDI é de R$ X/ano.",
  "generated_at": "2026-07-04T00:00:00Z"
}
```

Não precisa entrar no `OpportunitiesResponse` do OPP.1, porque poupança vs. CDI é um insight de
mercado, não depende do `idle_amount` calculado do usuário. Pode ser agregado pelo agente quando
fizer sentido.

### 5.4 Canais de consumo

| Canal | Comportamento esperado | Guardrail |
|---|---|---|
| Agente IA | Responde perguntas sobre "poupança", "CDI", "meu dinheiro rende pouco", "melhor que poupança" usando o contrato acima | Não afirmar que o usuário tem saldo em poupança sem dado real |
| Feed/Notificações | Card educativo/oportunidade genérica quando `severity >= MEDIUM`; card personalizado só após OPP4-D | Não enviar push agressivo sem saldo real confirmado |
| Notificações por e-mail/digest | Entrar apenas como insight de baixo atrito, com exemplo por R$10k | Não prometer rentabilidade nem recomendar resgate imediato |

Texto recomendado:

- Genérico: "Hoje a poupança tende a render menos que o CDI. Para cada R$10.000, a diferença
  estimada é de R$X/ano."
- Personalizado futuro: "Detectei R$X em poupança e estimei perda de R$Y/ano contra alternativa de
  liquidez semelhante."
- Sem dado: "Posso comparar poupança e CDI com um exemplo, mas ainda não tenho saldo de poupança
  confirmado para personalizar."

### 5.5 Severidade e elegibilidade

Para evitar ruído em feed/notificações:

| Condição | Status | Severidade | Uso |
|---|---|---|---|
| APIs/fallback indisponíveis ou incoerentes | `DATA_UNAVAILABLE` | `LOW` | Não gerar card; agente explica indisponibilidade |
| Diferença anual < R$30 no valor de referência | `NEAR_CDI` ou `NO_ADVANTAGE` | `LOW` | Responder só se perguntado |
| Diferença anual entre R$30 e R$150 | `BELOW_CDI` | `MEDIUM` | Card discreto/feed; sem push agressivo |
| Diferença anual >= R$150 | `BELOW_CDI` | `HIGH` | Card priorizável; push apenas se personalizado no futuro |

Esses thresholds são produto, não lei. Se mudarem, devem ficar centralizados em constantes testadas.

### 5.6 Fixtures obrigatórias

| Fixture | Entrada | Esperado |
|---|---|---|
| `selic_high_tr_zero` | SELIC > 8,5%, TR = 0 | branch `SELIC_GT_8_5`, poupança anualizada por 0,5% a.m. |
| `selic_high_tr_positive` | SELIC > 8,5%, TR > 0 | TR aumenta a taxa mensal antes da anualização |
| `selic_low_boundary` | SELIC = 8,5% | branch `SELIC_LTE_8_5` |
| `selic_low_tr_zero` | SELIC < 8,5%, TR = 0 | 70% da SELIC mensalizada |
| `cdi_close_to_savings` | CDI próximo da poupança | `NEAR_CDI`, não força narrativa de perda alta |
| `cdi_below_savings` | CDI artificialmente menor | `NO_ADVANTAGE`, sem recomendação de troca |
| `fallback_rates` | BACEN/ANBIMA falham | resposta marcada com `source="FALLBACK"` ou `DATA_UNAVAILABLE` |

### 5.7 Definition of Done

OPP.4 Opção A só deve ser marcada como concluída quando:

- existir uma única função testada para calcular taxa da poupança;
- TR vier de conector BACEN/SGS com cache e fallback documentado;
- SELIC e CDI não estiverem hardcoded na lógica nova;
- `tax_radar.py` tiver sido migrado para a nova fonte ou explicitamente isolado/depreciado;
- existir contrato Pydantic para a comparação poupança vs. CDI;
- o agente IA consumir o mesmo contrato, sem cálculo duplicado;
- feed/notificações tiverem regra de severidade/eligibilidade documentada;
- nenhuma mensagem afirmar saldo de poupança do usuário sem OPP4-D;
- existirem testes unitários para fórmula, comparação e fallback;
- existir ao menos um teste de paridade agente/serviço ou endpoint/serviço;
- a documentação final indicar que não há tela standalone para OPP.4.

---

## 6. Plano de desenvolvimento

### Ticket OPP4-A — Conector BACEN para TR

- Adicionar método em `BacenConnector`, sugerido `get_tr_monthly()`, seguindo `BaseConnector`.
- Usar a mesma infraestrutura SGS do conector atual, sem criar cliente HTTP paralelo.
- Retornar decimal mensal (`0.001` = 0,1% a.m.), nunca percentual textual.
- Documentar fallback, fonte e data de referência do fallback.
- Testar sucesso, payload vazio, payload malformado e fallback.

**Critério de aceite:** `BacenConnector().get_tr_monthly()` funciona com cache/fallback e não quebra
`get_selic()`.

**Arquivos esperados:** `backend/app/architect/connectors/bacen.py`,
`backend/tests/architect/test_connectors_fallback.py` ou teste dedicado equivalente.

### Ticket OPP4-B — Fórmula oficial da poupança

- Criar função pura `calculate_savings_rate(selic_annual, tr_monthly)`.
- Local recomendado: `backend/app/opportunities/services/savings_rate.py`, porque a fórmula é de
  oportunidade/rendimento, não de IR. Se a equipe decidir colocar no `IRPFCalculator`, registrar a
  razão na docstring.
- Remover dependência de qualquer hardcode do `tax_radar.py`.
- Validar a regra em fonte oficial antes do merge.

**Critério de aceite:** todos os ramos da regra e fronteira de 8,5% cobertos por teste; resultado
anualizado por composição mensal; sem número fixo de poupança no caminho novo.

**Arquivos esperados:** `backend/app/opportunities/services/savings_rate.py`,
`backend/tests/opportunities/test_savings_rate.py`.

### Ticket OPP4-C — Comparação genérica poupança vs. CDI

- Criar `SavingsVsCdiService` ou equivalente.
- Reaproveitar `AnbimaConnector.get_cdi()` e `BacenConnector.get_selic()/get_tr_monthly()`.
- Expor endpoint leve ou método integrado ao router de oportunidades.
- Gerar `SavingsVsCdiResult` com status, severidade, impacto mensal/anual e reason.
- A resposta deve ser cacheável por TTL de taxa, já que não depende do usuário.

**Critério de aceite:** serviço retorna comparação com números calculados na hora, sem saldo real, e
classifica corretamente `BELOW_CDI`, `NEAR_CDI`, `NO_ADVANTAGE` e `DATA_UNAVAILABLE`.

**Arquivos esperados:** `backend/app/opportunities/services/savings_vs_cdi.py`,
`backend/app/opportunities/models.py`, `backend/app/opportunities/router.py`,
`backend/tests/opportunities/test_savings_vs_cdi.py`.

### Ticket OPP4-D — Agente IA e feed/notificações

- Agente: plugar a comparação no fluxo existente do Radar de Oportunidades ou em tool específica só
  se a tool existente ficar semanticamente confusa.
- Feed/notificações: produzir evento/card apenas quando `severity >= MEDIUM`; push só deve esperar a
  fase personalizada, salvo decisão explícita de produto.
- Garantir que textos genéricos usam exemplo de R$10k, não saldo presumido do usuário.

**Critério de aceite:** agente e feed consomem o mesmo contrato do serviço; não há cálculo duplicado
nem tela nova.

**Arquivos esperados:** `backend/app/agent/tools/get_opportunities.py` ou nova tool justificada,
`backend/app/notifications/`, testes de apresentação/paridade.

### Ticket OPP4-E — Spike: saldo real de poupança do usuário

- Confirmar na documentação oficial/sandbox do Pluggy se poupança chega por `get_accounts()` ou
  `get_investments()`.
- Se vier como conta: conectar com a iniciativa de saldo real do OPP.1; não criar persistência
  isolada só para OPP.4.
- Se vier como investimento: adicionar fixture e testes para `InvestmentProfiler` antes de confiar
  no mapeamento `POUPANCA`.
- Saída esperada: decisão técnica curta com fonte, payload real/sandbox e recomendação de arquitetura.

**Critério de aceite:** nenhuma implementação personalizada começa antes da decisão do spike.

---

## 7. Riscos e decisões em aberto

- **Regra oficial da poupança:** validar fonte oficial antes do merge. A doc descreve a regra alvo,
  mas o PR deve apontar a fonte consultada.
- **Taxa mensal vs. anual:** maior risco de bug. Campos e testes devem deixar claro quando a taxa é
  mensal, anual, percentual ou decimal.
- **Narrativa inadequada:** sem saldo real, OPP.4 não pode dizer "você tem dinheiro na poupança".
  Deve dizer "para cada R$10.000" ou "se você tiver saldo em poupança".
- **`tax_radar.py` órfão:** manter hardcodes divergentes cria armadilha. Migrar ou marcar como
  legado/depreciado.
- **Saldo real via Pluggy:** mesma infraestrutura do OPP.1 Opção B. Não duplicar tabelas, sync ou
  interpretação de contas.
- **Comparação injusta:** poupança tem liquidez e isenção; comparar com CDI bruto pode ser útil, mas
  o texto deve explicar a referência. Para recomendação forte, comparar com alternativa de liquidez
  semelhante e retorno líquido.
- **Fonte indisponível:** fallback precisa ficar observável no resultado (`source`/`reason`), para o
  agente não apresentar número como se fosse dado fresco.

---

## 8. Backlog futuro

| Ticket | Ideia | Quando entra |
|---|---|---|
| OPP4-F | Comparação personalizada com saldo real de poupança | Após OPP4-E e infra de saldo real |
| OPP4-G | Comparar poupança vs. Tesouro Selic líquido de IR/custódia | Quando OPP.3/Tesouro for implementado |
| OPP4-H | Card de feed com impacto real por banco/conta | Após saldo real persistido |
| OPP4-I | Experimento de copy para reduzir risco de recomendação agressiva | Após primeiro uso em feed/agente |

---

## 9. Resumo e estimativa

| Ticket | Entrega | Esforço | Bloqueia |
|---|---|---:|---|
| OPP4-A | Conector BACEN TR | 1–2 dias | B |
| OPP4-B | Fórmula oficial da poupança | 1–2 dias | C |
| OPP4-C | Comparação genérica poupança vs. CDI | 1–2 dias | D |
| OPP4-D | Consumo por agente + feed/notificações | 1–2 dias | — |
| **Total Opção A** | Sem saldo real, alto valor educativo/acionável | **4–8 dias** | — |
| OPP4-E | Spike saldo real Pluggy | não estimar como implementação | F/G/H |

---

## 10. Checklist final antes de marcar OPP.4 como concluído

- [ ] `BacenConnector` expõe TR sem quebrar SELIC.
- [ ] Fórmula da poupança tem fonte oficial registrada no PR.
- [ ] Taxas mensais/anuais e decimal/percentual estão nomeadas sem ambiguidade.
- [ ] Serviço de comparação tem contrato Pydantic.
- [ ] Agente IA usa o serviço, não reimplementa a conta.
- [ ] Feed/notificações usam status/severidade, sem nova tela standalone.
- [ ] Textos genéricos não presumem saldo real do usuário.
- [ ] `tax_radar.py` não mantém hardcode divergente como fonte ativa.
- [ ] Testes cobrem SELIC alta, SELIC baixa, fronteira 8,5%, TR zero, TR positiva, CDI próximo,
      CDI abaixo e fallback.
- [ ] OPP4-E documenta a decisão Pluggy antes de qualquer personalização.
