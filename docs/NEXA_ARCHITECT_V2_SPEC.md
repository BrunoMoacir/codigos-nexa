# Nexa Architect v2.0 — Especificação Técnica Completa

> **Motor de Simulação de Conquistas Financeiras — Nível Institucional**
>
> Este documento especifica TODAS as funcionalidades necessárias para um motor de simulação financeira robusto, calibrado e confiável para decisões de alto valor no mercado brasileiro.

---

## Índice Geral

1. [Visão Arquitetural](#1-visão-arquitetural)
2. [Camada 1: Data Layer — Fontes de Dados Reais](#2-camada-1-data-layer)
3. [Camada 2: Modelagem Estocástica](#3-camada-2-modelagem-estocástica)
4. [Camada 3: Engine de Cashflow Completo](#4-camada-3-engine-de-cashflow)
5. [Camada 4: Tributação Brasileira](#5-camada-4-tributação)
6. [Camada 5: Opcionalidades e Derivativos Embutidos](#6-camada-5-opcionalidades)
7. [Camada 6: Risk Engine](#7-camada-6-risk-engine)
8. [Camada 7: Behavioral Finance](#8-camada-7-behavioral-finance)
9. [Camada 8: Location Intelligence](#9-camada-8-location-intelligence)
10. [Camada 9: Lifecycle Planning](#10-camada-9-lifecycle-planning)
11. [Camada 10: ML e Previsões](#11-camada-10-ml-e-previsões)
12. [Camada 11: Backtesting e Calibração](#12-camada-11-backtesting)
13. [Camada 12: API e Integrações](#13-camada-12-api)
14. [Camada 13: Output e Relatórios](#14-camada-13-output)
15. [Roadmap de Implementação](#15-roadmap)
16. [Estimativas de Esforço](#16-estimativas)

---

# 1. Visão Arquitetural

## 1.1 Diagrama de Alto Nível

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           NEXA ARCHITECT v2.0                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │   B3 API    │  │  BACEN SGS  │  │  FIPE ZAP   │  │   IBGE      │            │
│  │  (Curva DI) │  │(SELIC, IPCA)│  │ (Preços m²) │  │(Demográfico)│            │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘            │
│         │                │                │                │                    │
│         └────────────────┴────────────────┴────────────────┘                    │
│                                    │                                            │
│                          ┌─────────▼─────────┐                                  │
│                          │    DATA LAYER     │                                  │
│                          │  Cache + Fallback │                                  │
│                          └─────────┬─────────┘                                  │
│                                    │                                            │
│         ┌──────────────────────────┼──────────────────────────┐                │
│         │                          │                          │                │
│  ┌──────▼──────┐           ┌───────▼───────┐          ┌───────▼───────┐        │
│  │ STOCHASTIC  │           │   CASHFLOW    │          │    LOCATION   │        │
│  │   MODELS    │           │    ENGINE     │          │ INTELLIGENCE  │        │
│  │             │           │               │          │               │        │
│  │ • Vasicek   │           │ • SAC/PRICE   │          │ • Scoring     │        │
│  │ • GBM+Jump  │           │ • Consórcio   │          │ • Tendências  │        │
│  │ • Copulas   │           │ • FIIs        │          │ • Previsões   │        │
│  └──────┬──────┘           └───────┬───────┘          └───────┬───────┘        │
│         │                          │                          │                │
│         └──────────────────────────┼──────────────────────────┘                │
│                                    │                                            │
│                          ┌─────────▼─────────┐                                  │
│                          │   STRATEGY ENGINE │                                  │
│                          │                   │                                  │
│                          │ • NPV Estocástico │                                  │
│                          │ • Opções Reais    │                                  │
│                          │ • Tributação      │                                  │
│                          └─────────┬─────────┘                                  │
│                                    │                                            │
│         ┌──────────────────────────┼──────────────────────────┐                │
│         │                          │                          │                │
│  ┌──────▼──────┐           ┌───────▼───────┐          ┌───────▼───────┐        │
│  │    RISK     │           │  BEHAVIORAL   │          │   LIFECYCLE   │        │
│  │   ENGINE    │           │    LAYER      │          │    PLANNING   │        │
│  │             │           │               │          │               │        │
│  │ • VaR/CVaR  │           │ • Prospecto   │          │ • Fase vida   │        │
│  │ • Stress    │           │ • Aversão     │          │ • Objetivos   │        │
│  │ • Cenários  │           │ • Regret      │          │ • Restrições  │        │
│  └──────┬──────┘           └───────┬───────┘          └───────┬───────┘        │
│         │                          │                          │                │
│         └──────────────────────────┼──────────────────────────┘                │
│                                    │                                            │
│                          ┌─────────▼─────────┐                                  │
│                          │  RECOMMENDATION   │                                  │
│                          │      ENGINE       │                                  │
│                          │                   │                                  │
│                          │ • Ranking final   │                                  │
│                          │ • Intervalos      │                                  │
│                          │ • Action plan     │                                  │
│                          └─────────┬─────────┘                                  │
│                                    │                                            │
│                          ┌─────────▼─────────┐                                  │
│                          │   OUTPUT LAYER    │                                  │
│                          │                   │                                  │
│                          │ • JSON Response   │                                  │
│                          │ • PDF Report      │                                  │
│                          │ • Visualizações   │                                  │
│                          └───────────────────┘                                  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## 1.2 Princípios de Design

| Princípio | Descrição |
|-----------|-----------|
| **Data-Driven** | Nenhuma premissa hardcoded; tudo vem de dados reais ou modelos calibrados |
| **Uncertainty-First** | Outputs são distribuições, não pontos; intervalos de confiança obrigatórios |
| **Graceful Degradation** | Falha em uma camada não quebra o sistema; fallbacks hierárquicos |
| **Auditável** | Cada recomendação rastreável até os dados e modelos que a geraram |
| **Personalizável** | Perfil comportamental do usuário altera a função objetivo |

## 1.3 Stack Tecnológico Recomendado

```yaml
Runtime:
  language: Python 3.11+
  async: asyncio + httpx
  typing: strict (mypy)

Computação Numérica:
  core: NumPy, SciPy
  financeiro: QuantLib-Python
  estatística: statsmodels, arch
  ML: scikit-learn, XGBoost, LightGBM

Dados:
  cache: Redis (TTL por tipo de dado)
  persistência: PostgreSQL + TimescaleDB
  analytics: DuckDB (local), ClickHouse (produção)

APIs Externas:
  mercado: B3, ANBIMA, BACEN SGS
  imobiliário: FIPE ZAP API, VivaReal, QuintoAndar
  geográfico: Google Maps, IBGE

Infraestrutura:
  containers: Docker + Kubernetes
  CI/CD: GitHub Actions
  monitoring: Prometheus + Grafana
  logging: ELK Stack
```

---

# 2. Camada 1: Data Layer

## 2.1 Fontes de Dados Obrigatórias

### 2.1.1 Dados Macroeconômicos

| Dado | Fonte Primária | Fonte Backup | Frequência | TTL Cache |
|------|----------------|--------------|------------|-----------|
| SELIC Meta | BACEN SGS (série 432) | BCB API | Diária | 1 hora |
| SELIC Over | BACEN SGS (série 1178) | BCB API | Diária | 1 hora |
| CDI | BACEN SGS (série 12) | ANBIMA | Diária | 1 hora |
| IPCA | BACEN SGS (série 433) | IBGE SIDRA | Mensal | 24 horas |
| IGP-M | BACEN SGS (série 189) | FGV IBRE | Mensal | 24 horas |
| INCC | FGV IBRE | BACEN SGS | Mensal | 24 horas |
| TR | BACEN SGS (série 226) | — | Diária | 1 hora |
| Curva DI Futura | B3 (contratos DI1) | Bloomberg | Diária | 15 min |
| Curva IPCA Implícita | Tesouro Direto (NTN-B) | ANBIMA | Diária | 1 hora |
| Câmbio USD/BRL | BACEN PTAX | BCB API | Diária | 1 hora |

### 2.1.2 Dados de Crédito Imobiliário

| Dado | Fonte | Frequência | TTL Cache |
|------|-------|------------|-----------|
| Taxa média financiamento PF | BACEN SGS (série 25497) | Mensal | 24 horas |
| Spread bancário imobiliário | BACEN SGS | Mensal | 24 horas |
| LTV médio praticado | ABECIP | Trimestral | 7 dias |
| Inadimplência crédito imob. | BACEN SGS | Mensal | 24 horas |
| Volume de concessões | BACEN SCR | Mensal | 24 horas |

### 2.1.3 Dados do Mercado Imobiliário

| Dado | Fonte Primária | Fonte Backup | Granularidade | TTL Cache |
|------|----------------|--------------|---------------|-----------|
| Preço m² venda | FIPE ZAP | DataZAP+ | Bairro/mês | 24 horas |
| Preço m² aluguel | FIPE ZAP | QuintoAndar | Bairro/mês | 24 horas |
| Índice FipeZAP | FIPE | — | Cidade/mês | 24 horas |
| Vacância comercial | CBRE, JLL | SECOVI | Cidade/trimestre | 7 dias |
| Vacância residencial | SECOVI | Pesquisa própria | Cidade/trimestre | 7 dias |
| Lançamentos | SECOVI, ABRAINC | — | Cidade/mês | 7 dias |
| Estoque disponível | SECOVI | VivaReal scraping | Cidade/mês | 24 horas |
| Velocidade de venda (VSO) | SECOVI | ABRAINC | Cidade/trimestre | 7 dias |

### 2.1.4 Dados de Consórcio

| Dado | Fonte | Frequência | TTL Cache |
|------|-------|------------|-----------|
| Taxa administração média | ABAC | Mensal | 7 dias |
| Probabilidade contemplação | ABAC (histórico) | Mensal | 7 dias |
| Grupos ativos | Administradoras (APIs) | Diária | 1 hora |
| Lance médio vencedor | ABAC, administradoras | Mensal | 7 dias |

### 2.1.5 Dados de FIIs

| Dado | Fonte | Frequência | TTL Cache |
|------|-------|------------|-----------|
| Cotações | B3, Yahoo Finance | Diária | 15 min |
| Dividend Yield | Status Invest, FundsExplorer | Mensal | 24 horas |
| P/VP | Status Invest | Diária | 1 hora |
| Vacância por fundo | Relatórios gerenciais | Mensal | 7 dias |
| IFIX | B3 | Diária | 15 min |

## 2.2 Especificação dos Conectores

### 2.2.1 Interface Base

```python
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
import asyncio
import httpx

T = TypeVar('T')

class DataPoint(BaseModel):
    value: float
    timestamp: datetime
    source: str
    confidence: float  # 0-1
    metadata: dict = {}

class CacheConfig(BaseModel):
    ttl: timedelta
    fallback_ttl: timedelta
    stale_while_revalidate: bool = True

class DataConnector(ABC, Generic[T]):
    """Interface base para todos os conectores de dados"""

    def __init__(self, cache: "RedisCache", config: CacheConfig):
        self.cache = cache
        self.config = config
        self.http = httpx.AsyncClient(timeout=30.0)

    @abstractmethod
    async def fetch_live(self, **params) -> T: ...

    @abstractmethod
    async def fetch_fallback(self, **params) -> T: ...

    @abstractmethod
    def get_cache_key(self, **params) -> str: ...

    @abstractmethod
    def get_hardcoded_fallback(self, **params) -> T: ...

    async def get(self, **params) -> DataPoint:
        """
        Fetch com fallback hierárquico:
        1. Cache válido
        2. Cache stale + revalidate em background
        3. Fetch live
        4. Fetch fallback
        5. Hardcoded
        """
        cache_key = self.get_cache_key(**params)
        cached = await self.cache.get(cache_key)

        if cached and not cached.is_expired:
            return cached.value
        if cached and cached.is_stale and self.config.stale_while_revalidate:
            asyncio.create_task(self._revalidate(cache_key, params))
            return cached.value

        try:
            value = await self.fetch_live(**params)
            confidence, source = 1.0, "live"
        except Exception:
            try:
                value = await self.fetch_fallback(**params)
                confidence, source = 0.8, "fallback"
            except Exception:
                value = self.get_hardcoded_fallback(**params)
                confidence, source = 0.5, "hardcoded"

        data_point = DataPoint(value=value, timestamp=datetime.utcnow(),
                               source=source, confidence=confidence)
        await self.cache.set(cache_key, data_point,
                             ttl=self.config.ttl if source == "live" else self.config.fallback_ttl)
        return data_point
```

### 2.2.2 Conector BACEN SGS

```python
class BacenSGSConnector(DataConnector[float]):
    BASE_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados"

    SERIES = {
        "selic_meta": 432,
        "selic_over": 1178,
        "cdi": 12,
        "ipca": 433,
        "igpm": 189,
        "tr": 226,
        "incc": 7447,
        "taxa_financiamento_imobiliario": 25497,
    }

    FALLBACKS = {
        "selic_meta": 14.25, "selic_over": 14.15, "cdi": 14.15,
        "ipca": 4.50, "igpm": 4.00, "tr": 2.00,
        "incc": 6.50, "taxa_financiamento_imobiliario": 10.50,
    }

    async def fetch_live(self, serie_name: str, **params) -> float:
        serie_id = self.SERIES[serie_name]
        url = self.BASE_URL.format(serie=serie_id)
        params = {
            "formato": "json",
            "dataInicial": (datetime.now() - timedelta(days=60)).strftime("%d/%m/%Y"),
            "dataFinal": datetime.now().strftime("%d/%m/%Y"),
        }
        response = await self.http.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if not data:
            raise ValueError(f"Série {serie_name} sem dados recentes")
        return float(data[-1]["valor"])

    def get_cache_key(self, serie_name: str, **params) -> str:
        return f"bacen:sgs:{serie_name}"

    def get_hardcoded_fallback(self, serie_name: str, **params) -> float:
        return self.FALLBACKS.get(serie_name, 10.0)
```

### 2.2.3 Conector Curva DI (B3)

```python
class B3DIConnector(DataConnector[Dict[str, float]]):
    VENCIMENTOS = ["F25", "F26", "F27", "F28", "F29", "F30", "F31", "F32", "F33", "F34", "F35"]

    def interpolate_curve(self, curve: Dict[str, float], target_months: int) -> float:
        from scipy.interpolate import CubicSpline
        months = []
        rates = []
        for code, rate in sorted(curve.items()):
            months.append(self._code_to_months(code))
            rates.append(rate)
        cs = CubicSpline(months, rates)
        return float(cs(target_months))

    def get_forward_rates(self, curve: Dict[str, float]) -> List[float]:
        """
        f(t1, t2) = [(1 + r2)^t2 / (1 + r1)^t1]^(1/(t2-t1)) - 1
        """
        forward_rates = []
        sorted_curve = sorted(curve.items(), key=lambda x: self._code_to_months(x[0]))
        for i in range(len(sorted_curve) - 1):
            t1 = self._code_to_months(sorted_curve[i][0]) / 12
            t2 = self._code_to_months(sorted_curve[i+1][0]) / 12
            r1 = sorted_curve[i][1] / 100
            r2 = sorted_curve[i+1][1] / 100
            forward = ((1 + r2) ** t2 / (1 + r1) ** t1) ** (1 / (t2 - t1)) - 1
            forward_rates.append(forward * 100)
        return forward_rates
```

---

# 3. Camada 2: Modelagem Estocástica

## 3.1 Modelo de Taxas de Juros — Vasicek/CIR

### 3.1.1 Fundamentação Teórica

**Vasicek** (Ornstein-Uhlenbeck):
```
dr(t) = κ(θ - r(t))dt + σdW(t)
```

**CIR** (garante taxas não-negativas):
```
dr(t) = κ(θ - r(t))dt + σ√r(t)dW(t)
```

Onde `κ` = velocidade de reversão, `θ` = média de longo prazo, `σ` = volatilidade, `W(t)` = processo de Wiener.

### 3.1.2 Implementação

```python
@dataclass
class CIRParams:
    kappa: float   # velocidade de reversão
    theta: float   # média de longo prazo
    sigma: float   # volatilidade
    r0: float      # taxa inicial

class InterestRateModel:
    def __init__(self, model_type: Literal["vasicek", "cir"] = "cir"):
        self.model_type = model_type
        self.params: CIRParams = None

    def calibrate(self, historical_rates: np.ndarray, dt: float = 1/252) -> None:
        """Calibra via MLE (Maximum Likelihood Estimation)"""
        if self.model_type == "vasicek":
            self.params = self._calibrate_vasicek(historical_rates, dt)
        else:
            self.params = self._calibrate_cir(historical_rates, dt)

    def _calibrate_vasicek(self, rates: np.ndarray, dt: float) -> CIRParams:
        """OLS: Δr = α + βr(t) + ε → κ = -β/dt, θ = α/(κ·dt)"""
        dr = np.diff(rates)
        r = rates[:-1]
        X = np.column_stack([np.ones(len(r)), r])
        coeffs, _, _, _ = np.linalg.lstsq(X, dr, rcond=None)
        alpha, beta = coeffs
        kappa = -beta / dt
        theta = alpha / (kappa * dt)
        sigma = np.std(dr - (alpha + beta * r)) / np.sqrt(dt)
        return CIRParams(kappa=kappa, theta=theta, sigma=sigma, r0=rates[-1])

    def simulate(self, n_months: int, n_simulations: int = 10000, seed: int = None) -> np.ndarray:
        """Returns shape (n_simulations, n_months)"""
        if seed:
            np.random.seed(seed)
        dt = 1/12
        paths = np.zeros((n_simulations, n_months))
        paths[:, 0] = self.params.r0
        for t in range(1, n_months):
            r = paths[:, t-1]
            dW = np.random.normal(0, np.sqrt(dt), n_simulations)
            if self.model_type == "vasicek":
                dr = self.params.kappa * (self.params.theta - r) * dt + self.params.sigma * dW
            else:
                dr = self.params.kappa * (self.params.theta - r) * dt + self.params.sigma * np.sqrt(np.maximum(r, 0)) * dW
            paths[:, t] = np.maximum(paths[:, t-1] + dr, 0.001)
        return paths

    def get_expected_rate(self, months_ahead: int) -> float:
        """E[r(t)] = r0·exp(-κt) + θ·(1 - exp(-κt))"""
        t = months_ahead / 12
        return (self.params.r0 * np.exp(-self.params.kappa * t) +
                self.params.theta * (1 - np.exp(-self.params.kappa * t)))
```

## 3.2 Modelo de Preço de Imóvel — GBM com Saltos

### 3.2.1 Fundamentação Teórica

GBM + Jump-Diffusion (Merton):
```
dS/S = μdt + σdW + JdN

S = preço, μ = drift, σ = volatilidade, J = tamanho do salto, N = Poisson
```

### 3.2.2 Implementação

```python
@dataclass
class GBMJumpParams:
    mu: float           # drift anual
    sigma: float        # volatilidade anual
    lambda_: float      # intensidade de saltos (crises/ano)
    jump_mean: float    # média do salto (negativo = crise)
    jump_std: float     # volatilidade do salto

class RealEstatePriceModel:
    DEFAULT_PARAMS = GBMJumpParams(
        mu=0.05, sigma=0.12, lambda_=0.05,
        jump_mean=-0.25, jump_std=0.10
    )

    def calibrate(self, price_history: pd.DataFrame) -> None:
        returns = np.log(price_history['price_m2']).diff().dropna()
        threshold = returns.std() * 2.5
        normal_returns = returns[np.abs(returns) < threshold]
        jump_returns = returns[np.abs(returns) >= threshold]
        self.params.mu = normal_returns.mean() * 12
        self.params.sigma = normal_returns.std() * np.sqrt(12)
        if len(jump_returns) > 0:
            self.params.lambda_ = len(jump_returns) / (len(returns) / 12)
            self.params.jump_mean = jump_returns.mean()
            self.params.jump_std = jump_returns.std()

    def simulate(self, S0: float, n_months: int, n_simulations: int = 10000, seed: int = None) -> np.ndarray:
        if seed:
            np.random.seed(seed)
        dt = 1/12
        paths = np.zeros((n_simulations, n_months + 1))
        paths[:, 0] = S0
        for t in range(1, n_months + 1):
            dW = np.random.normal(0, np.sqrt(dt), n_simulations)
            drift = (self.params.mu - 0.5 * self.params.sigma ** 2) * dt
            diffusion = self.params.sigma * dW
            n_jumps = np.random.poisson(self.params.lambda_ * dt, n_simulations)
            jump_sizes = np.array([
                np.sum(np.random.normal(self.params.jump_mean, self.params.jump_std, n))
                if n > 0 else 0.0
                for n in n_jumps
            ])
            paths[:, t] = paths[:, t-1] * np.exp(drift + diffusion + jump_sizes)
        return paths

    def get_price_distribution(self, S0: float, months_ahead: int) -> Dict[str, float]:
        sims = self.simulate(S0, months_ahead, n_simulations=50000)
        fp = sims[:, -1]
        return {
            "mean": np.mean(fp), "median": np.median(fp), "std": np.std(fp),
            "p5": np.percentile(fp, 5), "p25": np.percentile(fp, 25),
            "p75": np.percentile(fp, 75), "p95": np.percentile(fp, 95),
            "prob_loss": float(np.mean(fp < S0)),
        }
```

## 3.3 Modelo de Aluguel — Mean Reversion com Vacância

```python
@dataclass
class RentalParams:
    yield_mean: float      # yield médio de longo prazo
    yield_vol: float
    vacancy_rate: float    # taxa de vacância média
    vacancy_vol: float
    default_rate: float    # inadimplência
    reajuste_cap: float    # cap de reajuste anual

class RentalIncomeModel:
    DEFAULT_PARAMS = RentalParams(
        yield_mean=0.004, yield_vol=0.0005,
        vacancy_rate=0.08, vacancy_vol=0.03,
        default_rate=0.05, reajuste_cap=0.10
    )

    def simulate(self, aluguel_inicial: float, n_months: int,
                 n_simulations: int = 5000, ipca_model=None) -> np.ndarray:
        """Simula fluxo líquido (após vacância e inadimplência). Returns (n_sims, n_months)"""
        rents = np.zeros((n_simulations, n_months))
        rents[:, 0] = aluguel_inicial
        is_vacant = np.zeros((n_simulations, n_months), dtype=bool)

        for t in range(n_months):
            if t > 0:
                p_to_vacant = self.params.vacancy_rate * 0.1
                p_to_occupied = 1 - (self.params.vacancy_rate * 2)
                rv = np.random.random(n_simulations)
                is_vacant[:, t] = np.where(
                    ~is_vacant[:, t-1], rv < p_to_vacant, rv >= p_to_occupied
                )
                if t % 12 == 0:
                    ipca = ipca_model.get_expected_rate(12) / 100 if ipca_model else np.random.normal(0.045, 0.01)
                    rents[:, t] = rents[:, t-1] * (1 + min(ipca, self.params.reajuste_cap))
                else:
                    rents[:, t] = rents[:, t-1]

            rents[:, t] = np.where(is_vacant[:, t], 0, rents[:, t])
            inadimplente = np.random.random(n_simulations) < self.params.default_rate
            rents[:, t] = np.where(inadimplente & ~is_vacant[:, t], 0, rents[:, t])

        return rents
```

## 3.4 Modelo de Correlações — Cópulas

```python
from scipy.stats import norm, t as t_dist
from scipy.linalg import cholesky

class CorrelationEngine:
    """Engine de correlações usando cópulas t-Student (caudas pesadas)"""

    # Calibrada para Brasil: [SELIC, Preço Imóvel, Aluguel, Vacância, PIB, Desemprego]
    CORRELATION_MATRIX = np.array([
        [ 1.00, -0.45, -0.30,  0.35, -0.50,  0.45],
        [-0.45,  1.00,  0.70, -0.40,  0.60, -0.50],
        [-0.30,  0.70,  1.00, -0.55,  0.45, -0.40],
        [ 0.35, -0.40, -0.55,  1.00, -0.60,  0.70],
        [-0.50,  0.60,  0.45, -0.60,  1.00, -0.75],
        [ 0.45, -0.50, -0.40,  0.70, -0.75,  1.00],
    ])
    VARIABLE_NAMES = ["selic", "preco_imovel", "aluguel", "vacancia", "pib", "desemprego"]

    def __init__(self, copula_type: Literal["gaussian", "t"] = "t", df: int = 5):
        self.copula_type = copula_type
        self.df = df
        self.chol = cholesky(self.CORRELATION_MATRIX, lower=True)

    def generate_correlated_scenarios(self, n_scenarios: int, seed: int = None) -> pd.DataFrame:
        """Retorna DataFrame com quantis uniformes [0,1] por variável"""
        if seed:
            np.random.seed(seed)
        n_vars = len(self.VARIABLE_NAMES)
        if self.copula_type == "gaussian":
            Z = np.random.normal(0, 1, (n_scenarios, n_vars))
            U = norm.cdf(Z @ self.chol.T)
        else:
            Z = t_dist.rvs(self.df, size=(n_scenarios, n_vars))
            U = t_dist.cdf(Z @ self.chol.T, self.df)
        return pd.DataFrame(U, columns=self.VARIABLE_NAMES)
```

---

# 4. Camada 3: Engine de Cashflow

## 4.1 Estrutura Base

```python
class CashflowCategory(Enum):
    # Saídas
    ENTRADA = "entrada"; PARCELA = "parcela"; JUROS = "juros"
    AMORTIZACAO = "amortizacao"; SEGURO = "seguro"; IOF = "iof"
    ITBI = "itbi"; ESCRITURA = "escritura"; CARTORIO = "cartorio"
    CONDOMINIO = "condominio"; IPTU = "iptu"; MANUTENCAO = "manutencao"
    TAXA_ADMIN = "taxa_admin"; IR = "ir"
    # Entradas
    ALUGUEL = "aluguel"; RENDIMENTO = "rendimento"; FGTS = "fgts"
    VENDA = "venda"; DIVIDENDO = "dividendo"

class Cashflow(BaseModel):
    month: int
    amount: float              # positivo = entrada, negativo = saída
    type: CashflowType
    category: CashflowCategory
    description: str
    is_certain: bool = True
    confidence: float = 1.0
    tax_deductible: bool = False

class CashflowSeries(BaseModel):
    strategy_id: str
    cashflows: List[Cashflow]
    start_date: date

    def to_array(self) -> np.ndarray:
        max_month = max(cf.month for cf in self.cashflows)
        result = np.zeros(max_month + 1)
        for cf in self.cashflows:
            result[cf.month] += cf.amount
        return result
```

## 4.2 Calculadora de Financiamento Completa

```python
class FinancingCalculator:
    """SAC, PRICE, SAM com todos os custos: IOF, ITBI, escritura, seguros MIP/DFI"""

    INSURANCE_RATES = {"MIP": 0.00025, "DFI": 0.00010}

    def calculate_iof(self) -> float:
        """Resolução BACEN 3.516/2007: fixo (0,38%) + diário (0,0082%/dia), cap 3%"""
        iof_fixo = self.principal * 0.0038
        iof_diario = sum(
            (self.principal / self.months) * 0.000082 * min(t * 30, 365)
            for t in range(1, self.months + 1)
        )
        return min(iof_fixo + iof_diario, self.principal * 0.03)

    def calculate_acquisition_costs(self, property_value: float) -> Dict[str, float]:
        return {
            "itbi": property_value * 0.03,
            "escritura": property_value * 0.015,
            "registro": property_value * 0.01,
            "avaliacao": 1500,
            "iof": self.calculate_iof(),
        }

    def _generate_price_cashflows(self) -> List[Cashflow]:
        pmt = self.principal * (
            self.monthly_rate * (1 + self.monthly_rate) ** self.months
        ) / ((1 + self.monthly_rate) ** self.months - 1)

        cashflows = []
        saldo = self.principal
        for t in range(1, self.months + 1):
            if self.include_tr:
                saldo *= (1 + self.monthly_tr)
            juros = saldo * self.monthly_rate
            amortizacao = pmt - juros
            seguro_mip = saldo * self.INSURANCE_RATES["MIP"]
            seguro_dfi = saldo * self.INSURANCE_RATES["DFI"]
            saldo -= amortizacao
            cashflows.extend([
                Cashflow(month=t, amount=-amortizacao, type=CashflowType.OUTFLOW,
                         category=CashflowCategory.AMORTIZACAO, description=f"Amortização mês {t}"),
                Cashflow(month=t, amount=-juros, type=CashflowType.OUTFLOW,
                         category=CashflowCategory.JUROS, description=f"Juros mês {t}"),
                Cashflow(month=t, amount=-(seguro_mip + seguro_dfi), type=CashflowType.OUTFLOW,
                         category=CashflowCategory.SEGURO, description=f"Seguros mês {t}"),
            ])
        return cashflows

    def _generate_sac_cashflows(self) -> List[Cashflow]:
        amortizacao_fixa = self.principal / self.months
        cashflows = []
        saldo = self.principal
        for t in range(1, self.months + 1):
            if self.include_tr:
                saldo *= (1 + self.monthly_tr)
            juros = saldo * self.monthly_rate
            seguro_mip = saldo * self.INSURANCE_RATES["MIP"]
            seguro_dfi = saldo * self.INSURANCE_RATES["DFI"]
            saldo -= amortizacao_fixa
            cashflows.extend([
                Cashflow(month=t, amount=-amortizacao_fixa, type=CashflowType.OUTFLOW,
                         category=CashflowCategory.AMORTIZACAO, description=f"Amortização SAC mês {t}"),
                Cashflow(month=t, amount=-juros, type=CashflowType.OUTFLOW,
                         category=CashflowCategory.JUROS, description=f"Juros mês {t}"),
                Cashflow(month=t, amount=-(seguro_mip + seguro_dfi), type=CashflowType.OUTFLOW,
                         category=CashflowCategory.SEGURO, description=f"Seguros mês {t}"),
            ])
        return cashflows
```

---

# 5–16. Camadas Restantes

> **⚠️ Documento parcialmente recebido** — O conteúdo original foi truncado pelo limite de caracteres na transmissão. As seções abaixo estão pendentes de inclusão:
>
> - **Camada 4:** Tributação Brasileira (IR ganho de capital, GCAP imóvel, FIIs isentos PF, ITBI, IPTU)
> - **Camada 5:** Opcionalidades e Derivativos Embutidos (opção de venda antecipada, amortização extraordinária, portabilidade)
> - **Camada 6:** Risk Engine (VaR, CVaR, stress testing, cenários históricos)
> - **Camada 7:** Behavioral Finance (Prospect Theory, aversão à perda, viés de ancoragem)
> - **Camada 8:** Location Intelligence (scoring de bairro, tendências de valorização, FIPE ZAP por micro-região)
> - **Camada 9:** Lifecycle Planning (fase de vida do usuário, horizonte de saída, restrições pessoais)
> - **Camada 10:** ML e Previsões (XGBoost para valorização, LightGBM para inadimplência)
> - **Camada 11:** Backtesting e Calibração (validação histórica dos modelos, métricas de acurácia)
> - **Camada 12:** API e Integrações (endpoints REST, schemas Pydantic, autenticação)
> - **Camada 13:** Output e Relatórios (JSON response completo, PDF, gráficos)
> - **Roadmap de Implementação** (fases, dependências, milestones)
> - **Estimativas de Esforço** (story points, equipe, prazo)
>
> Para adicionar o restante, envie as seções faltantes e este arquivo será atualizado.

---

*Versão: 2.0-draft | Status: Parcial (aguardando complemento) | Referência de implementação atual: [ARCHITECT_F3.md](ARCHITECT_F3.md)*
