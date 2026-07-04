# OPP — Radar de Oportunidades

**Documentação técnica completa de desenvolvimento**

> **Vertical:** OPP (Radar de Oportunidades)
> **Missão:** detectar dinheiro parado rendendo pouco e comparar instituições sem viés, recomendando a troca com o maior retorno líquido real após IR.
> **Status:** ⚠️ **MVP já implementado e em produção** (`backend/app/opportunities/`) — não é módulo greenfield. Esta doc documenta o que existe (marcado **[V1 — implementado]**) e a arquitetura alvo que o expande (marcado **[V2 — planejado]**). Toda seção deixa explícito em qual dos dois estados está.
>
> **Atualização 2026-07-04 (branch feat/opp-radar):** as extensões V2 desta doc foram implementadas —
> OPP.1 a OPP.5 completos. Entregues: `calc_ir_on_tesouro_selic` no `IRPFCalculator` (§5.2), Tesouro
> Selic no ranking e `TreasuryComparatorService` (OPP.3), `steps` práticos por produto (OPP.5),
> `disclaimer`/`data_sources` nas respostas (Gap 5), `issuer_risk.py` + `bank_scorecard.py` +
> `GET /{user_id}/banks` (§8.2), `GET /products` (transparência), `OpenFinanceProductsConnector` +
> job diário `product_catalog_refresh` 02h30 (§3.3/§7), cards de feed `SAVINGS_BELOW_CDI` e
> `IDLE_MONEY_DETECTED` com dedup por TTL (§11.2/OPP4-D), tool `simulate_investment` no agente,
> e card do Radar no dashboard React (Etapa 6). Ver `docs/ROADMAP.md` (seção OPP) para o resumo.
> **Stack:** Python 3.12+, FastAPI, Pydantic v2, Polars, seguindo o padrão `BaseConnector` já existente na F3 (`app/architect/connectors/`).

---

## 1. Visão Geral

O OPP resolve o problema mais concreto que existe em finanças pessoais no Brasil: **milhões de pessoas deixam dinheiro parado na conta corrente rendendo 0%**, enquanto poderiam ter retorno relevante sem risco adicional (produtos com garantia FGC até R$250k). O módulo faz três coisas em sequência:

1. **Detecta** quanto dinheiro está ocioso a partir do histórico de transações do usuário.
2. **Compara** o rendimento desse dinheiro contra um catálogo de produtos de renda fixa, sempre em **retorno líquido real após IR** — nunca taxa bruta.
3. **Recomenda** a troca com maior retorno, com ganho estimado em R$/mês e R$/ano.

O diferencial competitivo é a **neutralidade**: XP e BTG só mostram os produtos deles; a Nexa ranqueia pelo que é melhor para o usuário, sem comissão de nenhuma instituição.

**[V1 — implementado]** hoje isso já funciona ponta a ponta para 12 instituições, com job diário automático, ferramenta de chat e integração ao Wrapped anual. **[V2 — planejado]** a ambição do produto é ampliar cobertura via Open Finance Dados Abertos, adicionar Tesouro Direto, ranquear por banco (não só por produto) e proteger a reserva de emergência do usuário — nada disso está construído ainda.

---

## 2. Estado Atual — O Que Já Está Implementado **[V1]**

### 2.1 Estrutura de arquivos real

```
backend/app/opportunities/
├── __init__.py
├── models.py                          # OpportunityItem, OpportunitiesResponse, Treasury/BankMatch/Scorecard/Catalog models
├── router.py                          # GET /{user_id}, POST /compare, /savings-vs-cdi, /treasury-vs-cdb-vs-savings,
│                                      # /products, /{user_id}/banks, /{user_id}/bank-match
├── services/
│   ├── idle_money_detector.py         # IdleMoneyDetector (com reserva de emergência)
│   ├── bank_comparator.py             # BankComparator (Tesouro Selic, steps, reload de catálogo por mtime/TTL)
│   ├── opportunity_engine.py          # OpportunityEngine (orquestrador)
│   ├── savings_rate.py                # OPP.4 — fórmula oficial da poupança (SELIC + TR)
│   ├── savings_vs_cdi.py              # OPP.4 — comparação genérica poupança vs. CDI
│   ├── treasury_comparator.py         # OPP.3 — Tesouro SELIC vs. CDB vs. poupança
│   ├── switch_steps.py                # OPP.5 — passos práticos de troca
│   ├── bank_scorecard.py              # V2 — agregação por banco (§8.2)
│   └── bank_match.py                  # Bank Match — melhor banco pelo perfil (rendimento+tarifas+cartões+fit)
├── calculators/
│   └── issuer_risk.py                 # tier de risco do emissor, bucket de liquidez
├── connectors/
│   └── open_finance_products.py       # OpenFinanceProductsConnector (Dados Abertos, fallback curado)
└── data/
    └── product_catalog.json           # cache normalizado gravado pelo job product_catalog_refresh (02h30)

backend/data/
└── bank_products.json                 # Catálogo estático curado — 12 bancos, 20 produtos

backend/app/jobs/
└── opportunity_scan.py                # Job diário 03h00 (via app/core/scheduler.py)

backend/app/agent/tools/
└── get_opportunities.py               # Ferramenta do agente ReAct (chat)

backend/app/viral/services/
├── savings_consolidator.py            # Consolidado de economia lê opportunity_snapshots
└── wrapped_generator.py               # Wrapped anual lê opportunity_snapshots
```

As pastas `connectors/`, `calculators/` e `data/product_catalog.json` (antes só arquitetura alvo da seção 4) **existem e estão em uso** desde a branch `feat/opp-radar` (2026-07-04).

### 2.2 Fluxo de dados real

```
Transações do usuário (Pluggy → DuckDB, via app.core.db.queries)
        │
        ▼
IdleMoneyDetector.detect(user_id)
  → avg_income_3m − avg_expenses_3m = idle_amount (últimos 3 meses completos)
        │
        ▼
AnbimaConnector.get_cdi() → cdi_annual (fallback interno se API falhar)
        │
        ▼
BankComparator.rank(amount, holding_months, cdi_annual)
  → lê backend/data/bank_products.json (catálogo estático)
  → para cada produto, chama IRPFCalculator.calc_ir_on_cdb / calc_ir_on_lci_lca
  → ordena por annual_rate_net_pct (elegíveis primeiro, depois maior taxa líquida)
        │
        ▼
OpportunityEngine.analyze()
  → monta OpportunitiesResponse
  → persiste snapshot em opportunity_snapshots (falha silenciosamente, não derruba a request)
```

O motor de IR **não vive dentro de `app/opportunities/`** — é reaproveitado de `app/fiscal/ir_pf_calculator.py` (`IRPFCalculator`), que já implementa a tabela regressiva (Lei 8.981/1995, art. 65) e é usado por outras verticais fiscais do projeto:

```python
# app/fiscal/ir_pf_calculator.py (já existe, não duplicar)
_IR_BANDS: list[tuple[int, float]] = [
    (180, 0.225), (360, 0.200), (720, 0.175), (math.inf, 0.150),
]
InvestmentType = Literal["CDB", "LCI", "LCA", "CRI", "CRA", "DEBENTURE_INCENTIVADA", "POUPANCA"]

class IRPFCalculator:
    def calc_ir_on_cdb(self, principal, annual_rate_pct, holding_months) -> IRResult: ...
    def calc_ir_on_lci_lca(self, principal, annual_rate_pct, holding_months, investment_type="LCI") -> IRResult: ...
    def calc_breakeven_lci(self, cdb_gross_rate_pct, holding_months, lci_offered_rate_pct=None) -> BreakevenResult: ...
    def compare(self, principal, cdb_rate_pct, lci_rate_pct, holding_months) -> ComparisonResult: ...
```

`IRResult` já entrega tudo que o OPP precisa por produto: `gross_yield_brl`, `ir_rate`, `ir_brl`, `net_yield_brl`, `net_annual_rate_pct`, `is_exempt`. Qualquer extensão do motor de simulação (Tesouro Selic com custódia, gross-up isento↔tributado como método nomeado) deve entrar **neste arquivo**, não em um novo `calculators/fixed_income.py` dentro de `opportunities/` — ver seção 5.

### 2.3 Catálogo de produtos real

`backend/data/bank_products.json` (`updated_at: 2026-06-29`), curado manualmente, sem ETL:

- **12 instituições:** BTG Pactual, Banco Inter, Banco Pan, C6 Bank, Caixa Econômica, Nubank, PagBank, PicPay, Santander, Sicoob, Sofisa Direto, XP Investimentos.
- **20 produtos**, apenas `CDB`, `LCI`, `LCA` (sem RDB, CRI/CRA, debênture, Tesouro).
- Schema por produto: `bank_name`, `product_type`, `cdi_pct`, `min_amount`, `liquidity` (`"daily"` \| `"12m"`), `liquidity_days`, `rating` (curado, não é rating de agência).

`BankComparator._load_catalog()` lê o arquivo do disco a cada instância — sem cache TTL, sem invalidação. Atualizar o catálogo é editar o JSON e fazer deploy.

### 2.4 Integrações já ativas

| Integração | Arquivo | Comportamento real |
|:---|:---|:---|
| Agente de chat (ReAct) | `app/agent/tools/get_opportunities.py` | Ferramenta registrada em `app/agent/graph.py`. **Não chama `OpportunityEngine`** — tem lógica própria duplicada de cálculo de ocioso e formata texto para o chat, incluindo a última recomendação salva. |
| Job diário 03h00 | `app/jobs/opportunity_scan.py` | Registrado em `app/core/scheduler.py` (APScheduler, ativo quando `SCHEDULER_ENABLED=true`). Roda `OpportunityEngine.analyze()` para todos os usuários com transações nos últimos 30 dias. Usa `job_guard` — lock distribuído via Redis (fallback em memória), TTL 2h. |
| Persistência | Tabela `opportunity_snapshots` (migration `e1a2b3c4d5f6_add_nexa_roadmap_tables.py`) | Colunas: `id`, `user_id`, `captured_at`, `idle_amount`, `monthly_loss`, `top_opportunity` (string livre), `top_gain_brl`, `cdi_at_capture`. Índice `(user_id, captured_at)`. |
| Wrapped anual / consolidado de economia | `app/viral/services/savings_consolidator.py`, `wrapped_generator.py` | Leem o snapshot mais recente (`top_gain_brl`) como uma das fontes de "quanto a Nexa te ajudou a render este ano". |
| Frontend | — | **Não existe** tela ou card dedicado ao OPP em `frontend-react`. A única superfície de usuário hoje é o chat. |

---

## 3. Fontes de Dados e APIs

### 3.1 BACEN / ANBIMA — indexadores **[V1 — já em uso]**

`AnbimaConnector.get_cdi()` (em `app/architect/connectors/anbima.py`) já é a fonte do CDI usado pelo OPP, com cache e fallback herdados de `BaseConnector`. `BacenConnector` e `IPCAConnector` existem no mesmo diretório (usados pela F3/Architect) mas **não são chamados pelo OPP hoje** — a poupança e produtos IPCA+ não são calculados nesta vertical ainda.

### 3.2 Pluggy — dados do usuário **[V1 — já em uso, indireto]**

O OPP não chama o Pluggy diretamente: consome `app.core.db.queries.get_transactions_for_user`, que lê as transações já sincronizadas (via Pluggy) no DuckDB. Não há leitura de saldo diário nem da posição de investimentos do usuário — só o extrato de entradas/saídas dos últimos meses.

### 3.3 Open Finance Brasil — Dados Abertos **[V2 — IMPLEMENTADO 2026-07-04]** — `OpenFinanceProductsConnector` + job diário `product_catalog_refresh` (02h30); fallback = catálogo curado

A API de **dados abertos** do Open Finance Brasil (não exige consentimento do usuário — são ofertas públicas das instituições) é o caminho natural para substituir o catálogo estático de 12 bancos por cobertura de mercado real.

| Endpoint | Produtos | Uso alvo no OPP |
|:---|:---|:---|
| `GET /opendata-investments/v1/bank-fixed-incomes` | CDB, RDB, LCI, LCA | Substituir `bank_products.json` por catálogo vivo |
| `GET /opendata-investments/v1/credit-fixed-incomes` | Debêntures, CRI, CRA | Expansão de produtos isentos |

Base: `https://openfinancebrasil.atlassian.net/wiki/spaces/OF/`. É oficial, gratuita, cobre praticamente todos os bancos participantes, e os dados são padronizados por regulação do BACEN — mas a estrutura é verbosa e exige ETL de normalização (competência já existente na F1, ainda não aplicada ao OPP).

### 3.4 Tesouro Direto **[V2 — parcialmente implementado]** — Tesouro SELIC entra no ranking e no OPP.3 usando a SELIC meta do BACEN (aprox. da taxa do papel); conector de preços do Tesouro Transparente segue pendente

Nenhum produto de Tesouro está no catálogo hoje. Caminhos avaliados para quando isso for construído, em ordem de robustez:

1. **Tesouro Transparente (oficial, gratuito):** CSV público em `tesourotransparente.gov.br/ckan`. Pesado, mas é a fonte da verdade — baixar uma vez, pegar a última linha de cada título, cachear.
2. **Agregadores REST (pagos, convenientes):** `brapi.dev/api/v2/treasury`, `api.fintz.com.br/titulos-publicos/tesouro`, `api.dadosdemercado.com.br/v1/treasury`. Acelera um MVP; reavaliar custo ao escalar.
3. **Endpoint JSON não-documentado do Tesouro:** existe mas é instável — não usar em produção.

---

## 4. Arquitetura Alvo do Módulo **[V2 — planejado]**

Extensão da estrutura atual (seção 2.1), não substituição:

```
backend/app/opportunities/
├── models.py                          # [V1] existente — estender, não recriar
├── router.py                          # [V1] existente — adicionar rotas novas
├── services/
│   ├── idle_money_detector.py         # [V1] existente
│   ├── bank_comparator.py             # [V1] existente
│   ├── opportunity_engine.py          # [V1] existente
│   └── bank_scorecard.py              # [V2] NOVO — agregação por banco (seção 8.2)
├── connectors/                        # [V2] NOVO
│   ├── __init__.py
│   └── open_finance_products.py       # OpenFinanceProductsConnector (padrão BaseConnector)
├── calculators/                       # [V2] NOVO — só o que IRPFCalculator não cobre
│   ├── __init__.py
│   └── issuer_risk.py                 # tier de risco do emissor, bucket de liquidez
└── data/
    └── product_catalog.json           # [V2] cache normalizado alimentado pelo ETL — substitui/complementa backend/data/bank_products.json
```

O `product_catalog.json` seria o cache normalizado que o ETL do Open Finance Dados Abertos alimenta periodicamente (reaproveitando o padrão de scheduler já existente em `app/core/scheduler.py`, sem precisar de Celery/Redis novo — esse gap já está resolvido para outros jobs, ver seção 9).

---

## 5. Motor de Simulação

**Regra de ouro, já válida hoje via `IRPFCalculator`:** nunca comparar taxas brutas. Um CDB a 120% do CDI pode render menos líquido que uma LCI a 92% do CDI.

### 5.1 O que já existe **[V1]**

`IRPFCalculator.calc_ir_on_cdb` e `calc_ir_on_lci_lca` (seção 2.2) cobrem CDB/LCI/LCA tributados e isentos com a tabela regressiva completa. `calc_breakeven_lci` já calcula a taxa mínima de LCI que supera um CDB de taxa bruta conhecida — é o equivalente funcional ao "gross-up" que uma versão anterior desta doc propunha reimplementar do zero dentro de `opportunities/calculators/`. **Não recriar essa lógica em `app/opportunities/`.**

### 5.2 Extensões planejadas **[V2]** — como novos métodos de `IRPFCalculator`

**Tesouro SELIC com custódia B3** (0,20% a.a., isenta até R$10k desde 2020) — hoje nenhum produto de Tesouro está no catálogo, então isso não existe:

```python
# extensão proposta em app/fiscal/ir_pf_calculator.py
def calc_ir_on_tesouro_selic(
    self,
    principal: float,
    selic_annual: float,
    holding_months: int,
    custody_fee_annual: float = 0.0020,
    custody_exempt_limit: float = 10_000.0,
) -> IRResult:
    """Tesouro SELIC: IR regressivo (igual CDB) + custódia B3 sobre o excedente de R$10k."""
```

**Poupança** — hoje `IRPFCalculator` já trata `"POUPANCA"` como isenta em `calc_ir_on_lci_lca`, mas quem calcula a *taxa* da poupança (0,5%/mês + TR quando SELIC > 8,5% a.a.; 70% da SELIC quando ≤ 8,5%) ainda não existe em lugar nenhum do projeto — é uma extensão necessária antes de comparar poupança na prática, não só assumir a taxa como input.

### 5.3 Cenário de referência (validado com os números atuais do catálogo)

Com CDI 14,65% (SELIC 15%), R$10.000 por 360 dias, usando `IRPFCalculator` como está hoje:

| Produto | Rendimento líquido | vs Poupança* |
|:---|:---:|:---:|
| Poupança (taxa assumida, não calculada pelo sistema) | R$ 616,78 | — |
| CDB 100% CDI | R$ 1.154,84 | +R$ 538 |
| CDB 110% CDI | R$ 1.270,21 | +R$ 653 |
| LCI 90% CDI (isento) | R$ 1.299,31 | +R$ 682 |

\* A linha da poupança usa uma taxa calculada manualmente para referência — o sistema não tem hoje uma função que produza esse número (ver 5.2).

A LCI 90% (isenta) vence o CDB 100% mesmo tendo taxa bruta menor — essa é a mensagem central que `annual_rate_net_pct` já entrega corretamente na V1.

---

## 6. Detecção de Dinheiro Parado

### 6.1 O que já existe **[V1]**

```python
# app/opportunities/services/idle_money_detector.py (real, resumido)
@dataclass
class IdleMoneyResult:
    idle_amount: float
    avg_income_3m: float
    avg_expenses_3m: float
    months_analyzed: int
    has_sufficient_data: bool   # False quando < 2 meses de histórico

class IdleMoneyDetector:
    _MIN_MONTHS = 2
    def detect(self, user_id: str) -> IdleMoneyResult:
        # idle_amount = avg_income_3m − avg_expenses_3m, últimos 3 meses completos
        ...
```

Isso é **puramente fluxo de caixa** — não olha saldo diário em conta, não tem conceito de reserva de emergência e não distingue "dinheiro que sobrou este mês" de "reserva que o usuário está construindo de propósito". Não há hoje nenhuma trava que impeça o OPP de sugerir investir em produto de baixa liquidez um valor que na prática é reserva do usuário.

### 6.2 Extensão planejada — proteção de reserva **[V2]**

O projeto já tem um perfil comportamental real e maduro: `app.optimizer.profiler.ConsumptionProfiler.build()` retorna um `UserProfile` (`app/optimizer/profiler.py`) com campos relevantes já calculados a partir de 90 dias de transações:

- `fss_level: str` — `"SAUDAVEL" | "ATENCAO" | "ALERTA" | "CRITICO"` (Financial Stress Score). É o sinal real mais próximo do que uma versão anterior desta doc chamava de cluster "ESTRESSE_FINANCEIRO" — não existe esse valor literal no enum; o sinal correto é `fss_level in {"ALERTA", "CRITICO"}`.
- `investor_type: str` — `"NONE" | "CASUAL" | "ATIVO" | "DIVERSIFICADO"`.
- `lifestyle_cluster` / `secondary_clusters` — clusters comportamentais (ex.: presença esperada de perfis com maior aversão a risco).

Extensão proposta em `idle_money_detector.py` (sem quebrar a assinatura atual de `detect`):

```python
@dataclass
class IdleMoneyResult:
    idle_amount: float
    avg_income_3m: float
    avg_expenses_3m: float
    months_analyzed: int
    has_sufficient_data: bool
    # ── novos campos [V2] ──
    emergency_reserve: float = 0.0     # meses de gasto reservados, nunca contam como ocioso
    reserve_months_applied: int = 6    # ajustável por fss_level

def detect(self, user_id: str, user_profile: "UserProfile | None" = None) -> IdleMoneyResult:
    """
    [V2] Quando user_profile é passado, a reserva de emergência (padrão 6x
    avg_expenses_3m, ajustável para 9x quando fss_level in {"ALERTA","CRITICO"})
    é subtraída do idle_amount antes de retornar.
    """
```

Isso conecta o OPP à inteligência comportamental que já existe no projeto, em vez de inventar um `ConsumptionProfiler` paralelo.

---

## 7. Conector de Produtos **[V2 — IMPLEMENTADO 2026-07-04]** (ver `connectors/open_finance_products.py`; o esqueleto abaixo era a proposta original)

Seguindo o padrão real de `BaseConnector` (`app/architect/connectors/base.py`: `fetch_rates()`, `get_fallback_rates()`, cache/TTL herdados, `get_rates()` como entrypoint):

```python
# app/opportunities/connectors/open_finance_products.py [V2]
import logging
from typing import Any
from app.architect.connectors.base import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)

class OpenFinanceProductsConnector(BaseConnector):
    """
    Conector para os Dados Abertos de investimentos do Open Finance Brasil.
    Não requer consentimento — são ofertas públicas das instituições.
    Alimentaria app/opportunities/data/product_catalog.json, substituindo
    (ou complementando) backend/data/bank_products.json.
    """
    _BASE_URL = "https://<host-open-finance>/opendata-investments/v1"
    _CACHE_TTL = 6 * 3600  # 6h — ofertas não mudam a cada minuto

    def __init__(self, **kwargs):
        kwargs.setdefault("cache_ttl_seconds", self._CACHE_TTL)
        super().__init__(**kwargs)

    def fetch_rates(self) -> dict[str, Any]:
        """GET /bank-fixed-incomes → normalizar para o schema interno. Não implementado."""
        raise ConnectorError("Implementar chamada real; usar fallback por enquanto")

    def get_fallback_rates(self) -> dict[str, Any]:
        """Fallback = catálogo curado atual (backend/data/bank_products.json)."""
        return self._load_local_catalog()

    def get_products(self, product_type: str | None = None) -> list[dict]:
        catalog = self.get_rates()
        products = catalog.get("products", [])
        if product_type:
            products = [p for p in products if p["type"] == product_type]
        return products
```

Schema alvo — **estende os nomes de campo já usados em `bank_products.json`** (não inventa nomes novos como `institution`/`type`/`rate_pct` de uma versão anterior desta doc, que não batiam com o catálogo real):

```python
from pydantic import BaseModel

class FixedIncomeProduct(BaseModel):
    bank_name: str             # já existe no catálogo real
    product_type: str          # CDB | RDB | LCI | LCA | CRI | CRA — hoje só CDB/LCI/LCA
    cdi_pct: float              # já existe — % do CDI
    min_amount: float          # já existe
    liquidity: str              # já existe ("daily" | "12m" | ...)
    liquidity_days: int         # já existe
    rating: str                  # já existe (curado, não é rating de agência)
    # ── campos novos [V2] ──
    index: str = "CDI"          # CDI | PREFIXADO | IPCA — hoje implícito, sempre CDI
    is_tax_exempt: bool         # hoje derivado em runtime (product_type in {"LCI","LCA"}) — tornar explícito
    fgc_covered: bool = True    # garantia FGC até R$250k — hoje não modelado em lugar nenhum
```

---

## 8. Serviço Comparador

### 8.1 O que já existe **[V1]**

```python
# app/opportunities/services/bank_comparator.py (real, resumido)
class BankComparator:
    def rank(self, amount: float, holding_months: int, cdi_annual: float) -> list[OpportunityItem]:
        """
        Carrega backend/data/bank_products.json, chama IRPFCalculator por produto,
        marca eligible=False quando amount < min_amount (produto ainda aparece,
        vai para o fim do ranking), ordena por annual_rate_net_pct.
        """
```

Isso responde "qual o melhor produto?" — não responde "qual o melhor banco?" (ranking agregado por instituição não existe hoje).

### 8.2 Scorecard por banco **[V2 — IMPLEMENTADO 2026-07-04]** (`bank_scorecard.py` + `issuer_risk.py`; generalizado pelo Bank Match em `bank_match.py`, que soma tarifas, cartões e fit de perfil)

Comparar produtos soltos responde "qual o melhor CDB?". Comparar **por banco** responde "de todos os bancos, qual paga mais pelo meu perfil?", "meu banco principal está entre os piores?", "vale abrir conta em outro banco só pela taxa?" — nenhuma corretora responde isso porque nenhuma tem visão neutra de todos os bancos ao mesmo tempo.

Pré-requisito: o catálogo precisa vir do conector do Open Finance (seção 7), já marcado por instituição — a agregação seria uma camada de `group_by` sobre esse catálogo, não um módulo novo.

**Ajuste a risco por tier do emissor** — hoje o catálogo tem `rating` textual mas nada usa isso para penalizar yield:

```python
# app/opportunities/calculators/issuer_risk.py [V2]
_ISSUER_RISK_TIER: dict[str, int] = {
    "Itaú": 1, "Bradesco": 1, "Banco do Brasil": 1, "Santander": 1, "Caixa Econômica": 1,
    "BTG Pactual": 2, "Nubank": 2, "Banco Inter": 2, "C6 Bank": 2, "XP Investimentos": 2,
    "Banco Pan": 3, "Sofisa Direto": 3, "Sicoob": 3, "PagBank": 3, "PicPay": 3,
}
_RISK_PENALTY: dict[int, float] = {1: 0.0, 2: 0.005, 3: 0.015}

def issuer_tier(bank_name: str) -> int:
    return _ISSUER_RISK_TIER.get(bank_name, 3)  # desconhecido → conservador

def liquidity_bucket(liquidity_days: int, liquidity: str) -> str:
    if liquidity == "daily":
        return "diaria"
    return "ate_12m" if liquidity_days <= 365 else "longo_prazo"
```

```python
# app/opportunities/services/bank_scorecard.py [V2]
import polars as pl

def build_bank_scorecard(
    catalog: pl.DataFrame,   # bank_name, product_type, cdi_pct, is_tax_exempt, min_amount, liquidity, liquidity_days
    principal: float,
    cdi_annual: float,
    horizon_days: int,
) -> dict[str, pl.DataFrame]:
    """
    Retorna 'scorecard' (ranking por banco, bruto e ajustado a risco),
    'por_bucket' (melhor banco por bucket de liquidez) e 'risk_adjusted'.
    Reaproveita IRPFCalculator para o net_return_brl de cada linha —
    não recalcula IR manualmente dentro do Polars.
    """
```

Modelos de resposta alvo:

```python
class BankScorecardEntry(BaseModel):
    bank_name: str
    best_net_return_brl: float
    best_risk_adjusted_brl: float
    risk_tier: int              # 1=bancão, 2=digital consolidado, 3=médio/pequeno
    product_count: int
    fgc_covered: bool
    is_user_current_bank: bool  # cruza com o banco atual do usuário (via Pluggy)

class BankComparisonResponse(BaseModel):
    scorecard: list[BankScorecardEntry]
    best_by_liquidity: dict[str, str]
    user_current_bank_rank: int | None
    switch_gain_brl: float
    open_account_suggestion: str | None
```

---

## 9. Modelos de Dados (consolidado)

### 9.1 `OpportunityItem` **[V1 — implementado]**

| Campo | Tipo | Descrição |
|:---|:---|:---|
| `rank` | `int` | Posição no ranking (elegíveis primeiro, depois maior taxa líquida) |
| `bank_name` | `str` | Nome da instituição |
| `product_type` | `str` | `"CDB"` \| `"LCI"` \| `"LCA"` |
| `rating` | `str` | Rating textual curado manualmente (`"AAA"`/`"AA"`/`"A"`/`"N/A"`) |
| `cdi_pct` | `float` | % do CDI, ex. `110.0` = 110% CDI |
| `annual_rate_gross_pct` | `float` | Taxa bruta anual (%) |
| `annual_rate_net_pct` | `float` | Taxa líquida anual (%) após IR — **critério de ranking** |
| `ir_rate` | `float` | Alíquota de IR aplicada (`0.0` para isentos) |
| `is_exempt` | `bool` | `True` para LCI/LCA |
| `min_amount` | `float` | Aplicação mínima (R$) |
| `liquidity` | `str` | `"daily"` \| `"12m"` |
| `liquidity_days` | `int` | Prazo de liquidez em dias |
| `monthly_gain_brl` | `float` | Ganho mensal estimado |
| `annual_gain_brl` | `float` | Ganho anual estimado |
| `eligible` | `bool` | `False` quando `idle_amount < min_amount` |

**[V2 — campos propostos para adicionar]:** `fgc_covered: bool`, `index: str` (hoje sempre CDI, implícito), `steps: list[str]` (passos práticos para executar a troca).

### 9.2 `OpportunitiesResponse` **[V1 — implementado]**

| Campo | Tipo | Descrição |
|:---|:---|:---|
| `user_id` | `str` | Identificador do usuário |
| `idle_amount` | `float` | Dinheiro ocioso estimado (R$) |
| `avg_income_3m` | `float` | Renda média mensal (3 meses completos) |
| `avg_expenses_3m` | `float` | Despesa média mensal (3 meses completos) |
| `monthly_loss_in_checking` | `float` | Custo mensal de manter `idle_amount` parado, ao CDI atual |
| `cdi_annual_pct` | `float` | CDI anual usado (%) |
| `top_opportunity` | `OpportunityItem \| None` | Melhor opção elegível |
| `opportunities` | `list[OpportunityItem]` | Ranking completo |
| `recommendation` | `str` | Texto humano da recomendação |
| `generated_at` | `datetime` | Timestamp UTC |

**[V2 — campos propostos para adicionar]:** `emergency_reserve_kept: float` (depende da extensão da seção 6.2), `disclaimer: str` (obrigatório — ver Gaps), `data_sources: list[str]`.

### 9.3 `CompareRequest` / `CompareResponse` **[V1 — implementado]**

| Campo | Tipo | Descrição |
|:---|:---|:---|
| `amount` | `float` | Valor a simular (> 0) |
| `holding_months` | `int` | Prazo em meses (padrão `12`) |
| `cdi_annual_pct` | `float` | CDI anual usado (echo) |
| `opportunities` | `list[OpportunityItem]` | Ranking completo para o valor/prazo |

### 9.4 Nota sobre nomenclatura

Uma versão anterior desta doc descrevia modelos `FixedIncomeProduct`, `ProductRanking`, `OpportunityRequest`/`Response` com nomes de campo (`institution`, `type`, `rate_pct`) que **não existem no código**. Os nomes corretos e já em produção são os das seções 9.1–9.3 (`bank_name`, `product_type`, `cdi_pct`, etc.). Qualquer extensão nova deve seguir essa convenção para não fragmentar o schema.

---

## 10. Endpoints REST

| Método | Rota | Status | Auth | Descrição |
|:---:|:---|:---:|:---|:---|
| `GET` | `/api/v1/opportunities/{user_id}` | **[V1]** | `require_owner` | Radar completo: dinheiro parado + ranking. Query `holding_months` (1–360, padrão 12). Persiste snapshot. |
| `POST` | `/api/v1/opportunities/compare` | **[V1]** | `get_current_user` | Simula valor/prazo específico, sem histórico do usuário. |
| `GET` | `/api/v1/opportunities/savings-vs-cdi` | **[V1]** | `get_current_user` | OPP.4 — poupança vs. CDI genérico (valor de referência). |
| `GET` | `/api/v1/opportunities/treasury-vs-cdb-vs-savings` | **[V1]** | `get_current_user` | OPP.3 — Tesouro SELIC vs. melhor CDB vs. poupança, líquido. |
| `GET` | `/api/v1/opportunities/{user_id}/banks` | **[V1]** | `require_owner` | Scorecard por banco (seção 8.2), banco atual do usuário destacado. |
| `GET` | `/api/v1/opportunities/{user_id}/bank-match` | **[V1]** | `require_owner` | Bank Match — melhor banco pelo perfil (rendimento+tarifas+cartões+fit). |
| `GET` | `/api/v1/opportunities/products` | **[V1]** | público | Catálogo de produtos com origem (curado/Open Finance), para transparência. |

`/simulate` de uma versão anterior desta doc é, na prática, o `/compare` que já existe — não criar rota duplicada.

```python
# app/opportunities/router.py (real, resumido)
router = APIRouter(prefix="/opportunities", tags=["Opportunities (OPP)"])

@router.get("/{user_id}", response_model=OpportunitiesResponse)
def get_opportunities(
    user_id: str = Depends(require_owner),
    holding_months: int = Query(default=12, ge=1, le=360),
) -> OpportunitiesResponse:
    return _engine.analyze(user_id=user_id, holding_months=holding_months, persist_snapshot=True)
```

---

## 11. Integração com o Agente e o Feed

### 11.1 O que já existe **[V1]**

`get_opportunities(user_id)` está registrado em `app/agent/graph.py` como ferramenta do agente ReAct, acionada quando o usuário pergunta sobre dinheiro parado, CDB/LCI/LCA, ou "radar de oportunidades". Ela roda em paralelo à API — tem sua própria lógica de cálculo de ocioso, duplicada com `IdleMoneyDetector` (ver Gaps).

### 11.2 O que não existe **[V2]**

**[Atualizado 2026-07-04]** O card existe: `OpportunityRadarCard` no dashboard React, cards de feed `SAVINGS_BELOW_CDI` e `IDLE_MONEY_DETECTED` no pipeline de notificações (com relevância, fingerprint e TTL), e a lógica de ocioso está unificada no `OpportunityEngine` (chat, API e job usam o mesmo motor). Tools do agente: `get_opportunities`, `simulate_investment`, `get_best_bank`.

---

## 12. Plano de Desenvolvimento

Sequenciado por dependência técnica e valor de conversão.

### Etapa 0 — Já entregue **[V1]**
`IdleMoneyDetector`, `BankComparator` (via `IRPFCalculator`), `OpportunityEngine`, 2 endpoints REST, ferramenta de chat, job diário, persistência em `opportunity_snapshots`, integração com Wrapped/consolidado de economia. Catálogo estático de 12 bancos / 20 produtos.

### Etapa 1 — Consolidação (1 semana)
Unificar a lógica de ocioso entre `get_opportunities.py` (chat) e `IdleMoneyDetector` (API/job) — hoje duplicada e sujeita a divergir. Adicionar `tests/opportunities/` (não existe nenhum teste dedicado hoje).

### Etapa 2 — Proteção de reserva de emergência (1 semana)
Estender `IdleMoneyDetector.detect()` para aceitar `UserProfile` (via `ConsumptionProfiler` real) e subtrair a reserva de emergência antes de considerar o valor ocioso (seção 6.2).

### Etapa 3 — Catálogo vivo via Open Finance (2–3 semanas)
`OpenFinanceProductsConnector` + ETL de normalização, substituindo/complementando `bank_products.json`. Maior alavanca de cobertura de mercado do módulo inteiro.

### Etapa 4 — Scorecard por banco (1–2 semanas)
`bank_scorecard.py` + `issuer_risk.py`, endpoint `/opportunities/{user_id}/banks`. Depende da Etapa 3 para ter cobertura suficiente de instituições para o scorecard ser relevante.

### Etapa 5 — Tesouro Direto e disclaimer regulatório (1 semana)
Conector de Tesouro (seção 3.4), extensão de `IRPFCalculator` para custódia B3, e `disclaimer` obrigatório em `OpportunitiesResponse` — avaliar com jurídico antes de aumentar a exposição do produto (feed, notificações).

### Etapa 6 — Card no feed (1 semana)
Frontend: card dedicado com valor em R$/ano em destaque, consumindo os endpoints já existentes ou expandidos.

---

## 13. Estratégia de Testes

Hoje **não existe** `tests/opportunities/` — este é o gap mais simples de fechar antes de qualquer expansão.

```python
# tests/opportunities/test_idle_money_detector.py [a criar]
def test_idle_amount_e_renda_menos_despesa():
    # Cobrir IdleMoneyDetector._calculate com um DataFrame Polars sintético
    ...

def test_has_sufficient_data_falso_com_menos_de_2_meses():
    ...


# tests/opportunities/test_bank_comparator.py [a criar]
def test_rank_ordena_por_taxa_liquida_desc():
    # LCI 90% CDI deve ranquear acima de CDB 100% CDI no líquido, mesmo
    # com taxa bruta menor — usa IRPFCalculator internamente
    ...

def test_produto_abaixo_do_minimo_fica_eligible_false_no_fim():
    ...


# tests/opportunities/test_opportunity_engine.py [a criar]
def test_analyze_persiste_snapshot_quando_idle_amount_positivo():
    ...

def test_analyze_nao_falha_quando_persist_snapshot_lanca_excecao():
    # _persist_snapshot deve falhar silenciosamente (comportamento real do código)
    ...
```

Testes de IR/equivalência (tabela regressiva, gross-up) já deveriam existir em `tests/fiscal/` cobrindo `IRPFCalculator` diretamente — não recriar esses casos dentro de `tests/opportunities/`.

---

## 14. Gaps e Decisões Técnicas

**Gap 1 — Duas implementações de "dinheiro ocioso" divergentes (impacto: alto).** `IdleMoneyDetector` (API/job) e `_calc_idle_amount` dentro de `get_opportunities.py` (chat) calculam a mesma coisa com código duplicado. Risco real de divergência silenciosa. Correção: o tool do agente deveria chamar `IdleMoneyDetector` diretamente.

**Gap 2 — Sem proteção de reserva de emergência (impacto: alto).** `idle_amount` não distingue reserva de "sobra". Ver seção 6.2 para o caminho de correção usando `ConsumptionProfiler` real.

**Gap 3 — [FECHADO 2026-07-04]** Catálogo vivo via Open Finance com job diário e reload por mtime/TTL no BankComparator; o curado vira fallback. Texto original: catálogo estático e manual, cobertura limitada (impacto: médio). 12 bancos, 20 produtos, atualizados por edição manual de JSON, sem CDB de bancões (Itaú/Bradesco/BB estão listados no exemplo de `issuer_risk.py` da seção 8.2 mas **não existem no catálogo real hoje**). Ver seção 3.3/Etapa 3.

**Gap 4 — [FECHADO]** `tests/opportunities/` existe (130+ testes). Texto original: sem testes dedicados (impacto: médio). Ver seção 13.

**Gap 5 — [PARCIALMENTE FECHADO]** `DISCLAIMER` presente em API, chat, feed e card; falta validação formal do texto com jurídico. Texto original: sem disclaimer regulatório (impacto: médio, jurídico). Nem a resposta da API nem o texto do chat avisam explicitamente que a Nexa não presta consultoria de valores mobiliários regulada pela CVM. Avaliar antes da Etapa 6 (card no feed) — mais exposição do produto aumenta o risco de omissão.

**Decisão — Scheduler já resolvido, não é gap.** Uma versão anterior desta doc listava "scheduler para o ETL" como gap exigindo Celery+Redis novo. Isso já existe: `app/core/scheduler.py` (APScheduler) + `job_guard` (lock Redis com fallback em memória) já rodam `opportunity_scan` diariamente. Qualquer job novo (ex.: refresh do catálogo do Open Finance) reaproveita esse mesmo padrão.

**Decisão — Motor de IR não deve ser duplicado.** `IRPFCalculator` (`app/fiscal/`) é a fonte única de verdade para cálculo de IR sobre renda fixa, usada por outras verticais além do OPP. Extensões (Tesouro, poupança) entram lá, não em um `calculators/` novo dentro de `opportunities/`.

---

## 15. Por Que Isso Compete com XP e BTG

XP e BTG são marketplaces de produtos próprios — o assessor ganha comissão sobre o que vende, então nunca vai dizer "tire seu dinheiro daqui e coloque no banco X que paga mais". O OPP faz exatamente isso, porque a Nexa não ganha comissão de banco nenhum. O ranking por `annual_rate_net_pct` já é, hoje, a prova matemática dessa neutralidade — mesmo limitado a 12 instituições.

O golpe decisivo, ainda não construído (**[V2]**, seção 8.2), é o **scorecard por banco**: mostrar o ranking de todos os bancos, marcar onde o dinheiro do usuário está hoje, e calcular quanto ele perde por lealdade. É a diferença entre um vendedor mostrando o catálogo da loja e um consultor comparando todas as lojas da rua — mas depende primeiro de sair de um catálogo de 12 bancos curados manualmente para cobertura real via Open Finance (Etapa 3). Até lá, o OPP já entrega o núcleo da tese — retorno líquido real, sem viés — só que em escala menor do que a visão final do produto.
