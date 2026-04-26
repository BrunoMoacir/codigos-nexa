# Nexa AI — Plano de Implementação: User Intelligence
## Documento Técnico de Execução — Fase a Fase, Tarefa a Tarefa

> **Baseado em:** `docs/melhorias_analise_perfil.md` + auditoria completa do optimizer (Abril 2026)
>
> **Escopo:** Transformar o profiler atual (11 campos, 90 dias, análise de consumo) em um motor de inteligência comportamental completo — detectando padrões de vida, clusters de estilo, eventos de vida e sinais de estresse financeiro.
>
> **Arquitetura atual relevante:**
> - `ConsumptionProfiler` → `UserProfile` (11 campos)
> - `IncomeProfiler` → `IncomeProfile` (renda filtrada, CLT/PJ/MIXED)
> - Pipeline: Profiler → Simulator → Ranking → InsightGenerator → Report
> - Dados brutos: `transactions_clean` (Polars DataFrame) via Pluggy/Open Finance

---

## Índice

- [Fase 1 — Feature Store & Detecção Básica (0–3 meses)](#fase-1)
  - [T1.1 — Enriquecimento do Feature Store de Transações](#t11) ✅
  - [T1.2 — Detector de Viajante Frequente (`travel_frequency_score`)](#t12) ✅
  - [T1.3 — Detector de Foodie Gastronômico](#t13) ✅
  - [T1.4 — Detector de Investidor Ativo](#t14) ✅
  - [T1.5 — Detector de MEI/Microempreendedor](#t15) ✅
  - [T1.6 — Expansão do `UserProfile` com novos campos](#t16) ✅
  - [T1.7 — Clustering K-Means com 5 clusters básicos](#t17) ✅
  - [T1.8 — Integração dos detectors no pipeline do Optimizer](#t18) ✅
- [Fase 2 — Life Events, FSS e Motor de Recomendação (3–6 meses)](#fase-2)
  - [T2.1 — Detector de Eventos de Vida (Life Stage Intelligence)](#t21) ✅
  - [T2.2 — Financial Stress Score (FSS)](#t22) ✅
  - [T2.3 — Detector de Pai/Mãe com Filhos](#t23) ✅
  - [T2.4 — Motor de Recomendação Hiperpersonalizada (4-weight ranker)](#t24) ✅
  - [T2.5 — Detector de Usuário Airbnb / Nômade Digital](#t25) ✅
  - [T2.6 — Personalização de Insights por Cluster](#t26) ✅
  - [T2.7 — Inteligência Temporal (peak_spend_day, notification timing)](#t27) ✅
- [Fase 3 — ML Pipeline (6–12 meses)](#fase-3)
  - [T3.1 — Classificador de Merchant (NLP + MCC)](#t31)
  - [T3.2 — Predição de Gastos (Prophet)](#t32) ✅
  - [T3.3 — Propensity to Churn](#t33)
  - [T3.4 — Collaborative Filtering para Recomendação](#t34)
  - [T3.5 — A/B Testing Framework](#t35) ✅
- [Pré-requisitos transversais](#prereqs)
- [Métricas de Sucesso por Fase](#metricas)

---

<a name="fase-1"></a>
## FASE 1 — Feature Store & Detecção Básica (0–3 meses)

**Meta:** Enriquecer o pipeline de transações com campos derivados necessários para todos os detectores subsequentes, e implementar os 4 detectores comportamentais de maior impacto no ranking do optimizer.

---

<a name="t11"></a>
### T1.1 — Enriquecimento do Feature Store de Transações ✅

**O que implementar:** Adicionar campos derivados ao DataFrame de transações que alimentam TODOS os detectores desta fase e das fases seguintes. Sem isso, nenhum outro detector funciona.

**Contexto atual:** O `transactions_clean` da F1 já possui `date`, `amount`, `category`, `description`, `transaction_type`, `context_type`. Não possui `merchant_category_l2`, `is_travel_related`, `payment_method` granular, nem `installments_total`.

**Arquivo a criar:** `backend/app/optimizer/feature_store.py`

> **Nota sobre geocoding:** Os campos `geo_city`, `geo_state` da doc original exigem banco de geocoding externo que o projeto não possui. **Fora de escopo para Fase 1.** O campo `is_foreign` é implementado como proxy via keyword/moeda (cobre ~90% dos casos). Implementar geocoding completo é tarefa separada dependente de fornecedor externo (ex: OpenCage, HERE).

```python
# app/optimizer/feature_store.py
# TransactionFeatureEnricher — deriva campos comportamentais do transactions_clean
# Alimenta: detectors de viagem, foodie, MEI, investor, FSS, life events

import re
import polars as pl

# MCCs de viagem agrupados por subcategoria
_MCC_AIRLINES = set(range(3000, 3351)) | {4511}
_MCC_TRAVEL_AGENCIES = {4722, 4723}
_MCC_HOTELS = {7011, 7012}
_MCC_CAR_RENTAL = {7512, 7513}
_MCC_TRAVEL_INSURANCE = {6300}
_MCC_RESTAURANTS = {5812, 5813, 5814}
_MCC_DELIVERY = {5812}  # iFood/Rappi usam este MCC
_MCC_EDUCATION = {8211, 8220, 8241}
_MCC_HEALTH = {8011, 8049}
_MCC_BABY_GOODS = {5947, 5999, 5912}
_MCC_WHOLESALE = set(range(5040, 5200))
_MCC_ENTERTAINMENT = {7922, 7929, 7941, 7993, 7996}
_MCC_INVESTMENT_BROKERS = {6211}

_TRAVEL_KEYWORDS = [
    "AIRBNB", "BOOKING", "DECOLAR", "LATAM", "AZUL", "GOL",
    "EXPEDIA", "LOCALIZA", "MOVIDA", "UNIDAS", "HURB", "123MILHAS",
    "VIAJANET", "MAX MILHAS", "SUBMARINO VIAG", "CVC", "FLYTOUR",
]
_DELIVERY_KEYWORDS = ["IFOOD", "RAPPI", "UBER EATS", "LOGGI", "JAMES"]
_BROKER_KEYWORDS = [
    "XP INVESTIMENTOS", "BTG", "RICO CORRETORA", "CLEAR CORRETORA",
    "MODALMAIS", "GENIAL", "INTER INVEST", "NUINVEST",
    "TESOURODIRETO", "STN ", "TESOURO NACIONAL",
]
_B2B_KEYWORDS = [
    "OMIE", "CONTA AZUL", "BLING", "NFSE", "NOTA FISCAL",
    "MERCADO PAGO", "IFOOD PARCEIRO", "RAPPI PARTNER",
]
_COWORKING_KEYWORDS = ["WEWORK", "REGUS", "SPACES", "COWORKING", "ROOMO"]


class TransactionFeatureEnricher:
    """
    Enriquece o transactions_clean com campos derivados necessários para todos os
    detectores comportamentais.

    Chamado pelo ConsumptionProfiler.build() logo após _prepare_df().
    Retorna o mesmo DataFrame com colunas extras adicionadas (não altera schema original).
    """

    def enrich(self, df: pl.DataFrame) -> pl.DataFrame:
        df = self._add_payment_method(df)
        df = self._add_is_travel_related(df)
        df = self._add_is_delivery(df)
        df = self._add_is_broker(df)
        df = self._add_is_b2b(df)
        df = self._add_merchant_category_l2(df)
        df = self._add_is_foreign(df)
        df = self._add_temporal_features(df)
        return df

    def _add_payment_method(self, df: pl.DataFrame) -> pl.DataFrame:
        """PIX / DEBIT / CREDIT / BOLETO / TED — mais granular que transaction_type."""
        if "transaction_type" not in df.columns:
            return df.with_columns(pl.lit("UNKNOWN").alias("payment_method"))

        desc_col = pl.col("description").str.to_uppercase() if "description" in df.columns else pl.lit("")

        return df.with_columns(
            pl.when(desc_col.str.contains("PIX"))
            .then(pl.lit("PIX"))
            .when(desc_col.str.contains("BOLETO"))
            .then(pl.lit("BOLETO"))
            .when(desc_col.str.contains("TED|DOC"))
            .then(pl.lit("TED"))
            .when(pl.col("transaction_type").str.to_uppercase() == "DEBIT")
            .then(pl.lit("DEBIT"))
            .otherwise(pl.lit("CREDIT"))
            .alias("payment_method")
        )

    def _add_is_travel_related(self, df: pl.DataFrame) -> pl.DataFrame:
        """Booleano: transação relacionada a viagem (MCC + keywords)."""
        conditions = []

        if "mcc" in df.columns:
            all_travel_mccs = (
                _MCC_AIRLINES | _MCC_TRAVEL_AGENCIES | _MCC_HOTELS |
                _MCC_CAR_RENTAL | _MCC_TRAVEL_INSURANCE
            )
            conditions.append(pl.col("mcc").is_in(list(all_travel_mccs)))

        if "description" in df.columns:
            pattern = "|".join(_TRAVEL_KEYWORDS)
            conditions.append(
                pl.col("description").str.to_uppercase().str.contains(pattern)
            )

        if not conditions:
            return df.with_columns(pl.lit(False).alias("is_travel_related"))

        expr = conditions[0]
        for c in conditions[1:]:
            expr = expr | c

        return df.with_columns(expr.alias("is_travel_related"))

    def _add_is_delivery(self, df: pl.DataFrame) -> pl.DataFrame:
        """Booleano: pedido em app de delivery."""
        if "description" not in df.columns:
            return df.with_columns(pl.lit(False).alias("is_delivery"))
        pattern = "|".join(_DELIVERY_KEYWORDS)
        return df.with_columns(
            pl.col("description").str.to_uppercase().str.contains(pattern).alias("is_delivery")
        )

    def _add_is_broker(self, df: pl.DataFrame) -> pl.DataFrame:
        """Booleano: transação para corretora ou tesouro direto."""
        conditions = []
        if "mcc" in df.columns:
            conditions.append(pl.col("mcc").is_in(list(_MCC_INVESTMENT_BROKERS)))
        if "description" in df.columns:
            pattern = "|".join(_BROKER_KEYWORDS)
            conditions.append(
                pl.col("description").str.to_uppercase().str.contains(pattern)
            )
        if not conditions:
            return df.with_columns(pl.lit(False).alias("is_broker_txn"))

        expr = conditions[0]
        for c in conditions[1:]:
            expr = expr | c
        return df.with_columns(expr.alias("is_broker_txn"))

    def _add_is_b2b(self, df: pl.DataFrame) -> pl.DataFrame:
        """Booleano: gasto em ferramenta B2B (sinal de MEI/PJ)."""
        if "description" not in df.columns:
            return df.with_columns(pl.lit(False).alias("is_b2b"))
        pattern = "|".join(_B2B_KEYWORDS)
        return df.with_columns(
            pl.col("description").str.to_uppercase().str.contains(pattern).alias("is_b2b")
        )

    def _add_merchant_category_l2(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Subcategoria L2 baseada em MCC + keywords na descrição.
        Valores: DELIVERY, RESTAURANTE, SUPERMERCADO, FARMACIA, ACADEMIA,
                 VOO, HOTEL, AIRBNB, LOCADORA, CORRETORA, ESCOLA, PEDIATRA, ...
        """
        if "description" not in df.columns:
            return df.with_columns(pl.lit(None).cast(pl.Utf8).alias("merchant_category_l2"))

        desc = pl.col("description").str.to_uppercase()

        expr = (
            pl.when(desc.str.contains("|".join(_DELIVERY_KEYWORDS)))
            .then(pl.lit("DELIVERY"))
            .when(desc.str.contains("AIRBNB"))
            .then(pl.lit("AIRBNB"))
            .when(desc.str.contains("LOCALIZA|MOVIDA|UNIDAS|HERTZ"))
            .then(pl.lit("LOCADORA"))
            .when(desc.str.contains("LATAM|GOL|AZUL|AVIANCA|TAM"))
            .then(pl.lit("VOO"))
            .when(desc.str.contains("HOTEL|POUSADA|INN|RESORT"))
            .then(pl.lit("HOTEL"))
            .when(desc.str.contains("FARMACIA|DROGASIL|DROGA RAIA|PACHECO|ULTRAFARMA"))
            .then(pl.lit("FARMACIA"))
            .when(desc.str.contains("ACADEMIA|SMARTFIT|BLUEFIT|BODYTECH"))
            .then(pl.lit("ACADEMIA"))
            .when(desc.str.contains("ESCOLA|COLEGIO|CRECHE|UNIVERSIDADE|FACULDADE"))
            .then(pl.lit("ESCOLA"))
            .when(desc.str.contains("PEDIATR|CLINICA|HOSPITAL|UPA|PLANO SAUDE"))
            .then(pl.lit("SAUDE"))
            .when(desc.str.contains("|".join(_BROKER_KEYWORDS)))
            .then(pl.lit("CORRETORA"))
            .when(desc.str.contains("SUPERMERCADO|CARREFOUR|EXTRA|PÃO DE ACUCAR|MERCADO"))
            .then(pl.lit("SUPERMERCADO"))
            .when(desc.str.contains("RESTAURANTE|LANCHONETE|PIZZARIA|HAMBURGER|SUSHI"))
            .then(pl.lit("RESTAURANTE"))
            .when(desc.str.contains("NETFLIX|SPOTIFY|AMAZON PRIME|DISNEY|HBO|GLOBOPLAY"))
            .then(pl.lit("STREAMING"))
            .when(desc.str.contains("|".join(_COWORKING_KEYWORDS)))
            .then(pl.lit("COWORKING"))
            .otherwise(pl.lit(None))
        )

        return df.with_columns(expr.alias("merchant_category_l2"))

    def _add_is_foreign(self, df: pl.DataFrame) -> pl.DataFrame:
        """Booleano: transação no exterior (moeda != BRL ou IOF detectado)."""
        conditions = []

        if "currency" in df.columns:
            conditions.append(
                pl.col("currency").is_not_null() & (pl.col("currency") != "BRL")
            )

        if "description" in df.columns:
            conditions.append(
                pl.col("description").str.to_uppercase().str.contains(
                    r"IOF|USD|EUR|GBP|\bDOLLAR\b|\bEURO\b|EXTERIOR|INTERNATIONAL"
                )
            )

        if not conditions:
            return df.with_columns(pl.lit(False).alias("is_foreign"))

        expr = conditions[0]
        for c in conditions[1:]:
            expr = expr | c
        return df.with_columns(expr.alias("is_foreign"))

    def _add_temporal_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Adiciona day_of_week, is_weekend derivados de date.

        NOTA: `ingestor.py:159` já deriva `day_of_week` de `transaction_date`
        para o pipeline ETL (F1). O optimizer recebe DataFrames com coluna `date`
        (não `transaction_date`), então este método é necessário na camada do optimizer.
        Se o DataFrame já contiver `day_of_week`, não sobrescreve.
        """
        if "day_of_week" not in df.columns:
            df = df.with_columns(
                pl.col("date").dt.weekday().alias("day_of_week"),
            )
        if "is_weekend" not in df.columns:
            df = df.with_columns(
                (pl.col("date").dt.weekday() >= 5).alias("is_weekend"),
            )
        return df
```

**Arquivo a modificar:** `backend/app/optimizer/profiler.py`

No método `build()`, após `df = self._prepare_df(transactions_df, cutoff)`, adicionar:

```python
# Enriquecimento de features comportamentais
from app.optimizer.feature_store import TransactionFeatureEnricher
df = TransactionFeatureEnricher().enrich(df)
```

**Testes de aceitação:**
- Dado um DataFrame com `description="IFOOD*RESTAURANTE"`, `is_delivery=True`, `merchant_category_l2="DELIVERY"`
- Dado `description="AIRBNB 3 NOITES NYC", currency="USD"`, `is_travel_related=True`, `is_foreign=True`, `merchant_category_l2="AIRBNB"`
- Dado `description="PIX ENVIADO"`, `payment_method="PIX"`
- 100% das colunas obrigatórias presentes após `enrich()` mesmo sem colunas opcionais (`mcc`, `currency`)

**Estimativa:** 2–3 dias de dev + 1 dia de testes

---

<a name="t12"></a>
### T1.2 — Detector de Viajante Frequente (`travel_frequency_score`) ✅

**O que implementar:** Score 0–100 que quantifica frequência, intensidade e exposição internacional de viagens nos últimos 12 meses.

**Depende de:** T1.1 (campo `is_travel_related`, `is_foreign`)

**Arquivo a criar:** `backend/app/optimizer/detectors/travel_detector.py`

```python
# app/optimizer/detectors/travel_detector.py

from __future__ import annotations
import polars as pl


class TravelDetector:
    """
    Calcula travel_frequency_score (0–100) e travel_profile string.

    Fórmula (alinhada com melhorias_analise_perfil.md §2.1):
        score = regularidade(0–40) + intensidade(0–40) + internacional(0–20)

    regularidade = (meses_com_gasto_viagem / 12) × 40
    intensidade  = min(travel_spend_ratio × 200, 40)
    internacional = min(foreign_txn_count × 4, 20)
    """

    def calc_travel_score(
        self,
        df: pl.DataFrame,            # transactions enriquecidas (12 meses recomendado)
        total_spend_12m: float,
    ) -> dict:
        if total_spend_12m <= 0:
            return {"travel_frequency_score": 0.0, "travel_profile": "OCASIONAL"}

        # Garantir que campos enriquecidos existem
        has_travel = "is_travel_related" in df.columns
        has_foreign = "is_foreign" in df.columns

        if not has_travel:
            return {"travel_frequency_score": 0.0, "travel_profile": "SEM_DADOS"}

        travel_df = df.filter(pl.col("is_travel_related") & (pl.col("amount") < 0))

        # Regularidade: quantos meses distintos tiveram gasto de viagem
        if travel_df.is_empty():
            return {"travel_frequency_score": 0.0, "travel_profile": "OCASIONAL"}

        months_with_travel = (
            travel_df
            .with_columns(
                (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
            )
            .select("ym").unique().height
        )

        travel_spend = float(travel_df["amount"].sum()) * -1
        travel_spend_ratio = travel_spend / total_spend_12m

        foreign_count = 0
        if has_foreign:
            foreign_count = df.filter(pl.col("is_foreign")).height

        score = (
            (min(months_with_travel, 12) / 12) * 40
            + min(travel_spend_ratio * 200, 40)
            + min(foreign_count * 4, 20)
        )
        score = round(min(score, 100.0), 1)

        if score <= 30:
            profile = "OCASIONAL"
        elif score <= 60:
            profile = "MODERADO"
        elif score <= 80:
            profile = "FREQUENTE"
        else:
            profile = "INTENSO"

        return {
            "travel_frequency_score": score,
            "travel_profile": profile,
            "travel_spend_monthly": round(travel_spend / 12, 2),
            "months_with_travel_12m": months_with_travel,
            "foreign_txn_count_12m": foreign_count,
        }
```

**Integração com o Optimizer:**

O `travel_frequency_score` substitui/complementa o `travel_spend_monthly` atual no `UserProfile`. Enquanto `travel_spend_monthly` é um valor monetário (R$/mês), o score dá contexto qualitativo ao `CardRanking` e `InsightGenerator`.

No `ranking.py`, a condição atual:
```python
if profile.travel_spend_monthly > _TRAVEL_SPEND_THRESHOLD and BenefitTag.LOUNGE in result.benefit_tags:
    benefits_bonus += _LOUNGE_BONUS
```

Pode ser enriquecida — se `travel_frequency_score >= 61`, o `LOUNGE_BONUS` pode ser aumentado em 30% (viajante frequente usa mais o benefício de sala VIP):
```python
# No ranking.py — somente após T1.6 adicionar travel_frequency_score ao UserProfile
if profile.travel_spend_monthly > _TRAVEL_SPEND_THRESHOLD and BenefitTag.LOUNGE in result.benefit_tags:
    lounge_bonus = _LOUNGE_BONUS
    if getattr(profile, "travel_frequency_score", 0) >= 61:
        lounge_bonus *= 1.30  # viajante frequente usa mais o lounge
    benefits_bonus += lounge_bonus
```

**Testes de aceitação:**
- Usuário com 8/12 meses com gastos de viagem, 40% do gasto em viagem, 5 transações internacionais → score ~82 (INTENSO)
- Usuário com 0 transações de viagem → score 0.0 (OCASIONAL)
- Usuário com 1 voo nacional/ano → score ~12 (OCASIONAL)

**Estimativa:** 1–2 dias

---

<a name="t13"></a>
### T1.3 — Detector de Foodie Gastronômico ✅

**O que implementar:** Score 0–100 que detecta intensidade do perfil gastronômico, combinando percentual de gastos em alimentação, diversidade de restaurantes e ticket médio.

**Depende de:** T1.1 (campo `merchant_category_l2`, `is_delivery`)

**Arquivo a criar:** `backend/app/optimizer/detectors/foodie_detector.py`

```python
# app/optimizer/detectors/foodie_detector.py

from __future__ import annotations
import polars as pl


class FoodieDetector:
    """
    Detecta perfil gastronômico do usuário.

    foodie_score (0–100):
        - pct_food_spend (peso 40): % dos gastos em alimentação (L1: Alimentação, delivery, restaurante)
        - restaurant_diversity (peso 30): nº merchants únicos em restaurante/delivery
        - avg_restaurant_ticket (peso 20): ticket médio em restaurantes (normalizado)
        - fine_dining_flag (peso 10): ticket > R$150 em restaurante → fine dining
    """

    # Categorias que compõem o "gasto alimentação"
    _FOOD_CATEGORIES = {"Alimentação", "alimentacao"}
    _FOOD_L2 = {"DELIVERY", "RESTAURANTE", "SUPERMERCADO"}

    def calc_foodie_score(self, df: pl.DataFrame, total_spend_monthly: float) -> dict:
        if total_spend_monthly <= 0 or df.is_empty():
            return {"foodie_score": 0.0, "foodie_profile": "BASICO"}

        expenses = df.filter(pl.col("amount") < 0)

        # Gastos em alimentação (por categoria L1 ou L2)
        food_filter = pl.lit(False)
        if "category" in df.columns:
            food_filter = food_filter | pl.col("category").is_in(list(self._FOOD_CATEGORIES))
        if "merchant_category_l2" in df.columns:
            food_filter = food_filter | pl.col("merchant_category_l2").is_in(list(self._FOOD_L2))

        food_df = expenses.filter(food_filter)
        food_spend = float(food_df["amount"].sum()) * -1 if not food_df.is_empty() else 0.0
        pct_food = food_spend / (total_spend_monthly * max(df["date"].dt.month().n_unique(), 1)) if total_spend_monthly > 0 else 0.0

        # Diversidade de restaurantes (merchants únicos)
        restaurant_diversity = 0
        if "description" in df.columns and "merchant_category_l2" in df.columns:
            rest_df = expenses.filter(
                pl.col("merchant_category_l2").is_in({"RESTAURANTE", "DELIVERY"})
            )
            if not rest_df.is_empty():
                restaurant_diversity = rest_df["description"].n_unique()

        # Ticket médio em restaurantes
        avg_ticket = 0.0
        fine_dining = False
        if not food_df.is_empty():
            avg_ticket = food_spend / len(food_df)
            fine_dining = avg_ticket > 150.0

        # Calcular score
        pct_score = min(pct_food * 160, 40)          # 25% gasto em food = 40 pts
        diversity_score = min(restaurant_diversity * 1.5, 30)  # 20 restaurantes = 30 pts
        ticket_score = min((avg_ticket / 200) * 20, 20)        # R$200 ticket = 20 pts
        fine_dining_bonus = 10 if fine_dining else 0

        foodie_score = round(min(pct_score + diversity_score + ticket_score + fine_dining_bonus, 100), 1)

        if foodie_score <= 25:
            profile = "BASICO"
        elif foodie_score <= 55:
            profile = "APRECIADOR"
        elif foodie_score <= 75:
            profile = "GOURMET"
        else:
            profile = "ENTUSIASTA"

        return {
            "foodie_score": foodie_score,
            "foodie_profile": profile,
            "pct_food_spend": round(pct_food, 3),
            "restaurant_diversity": restaurant_diversity,
            "avg_restaurant_ticket": round(avg_ticket, 2),
            "is_fine_dining": fine_dining,
        }
```

**Uso no InsightGenerator:**

Quando `foodie_score >= 55` e o cartão atual não possui `BenefitTag.CASHBACK` em alimentação, gerar insight `MUDAR_CATEGORIA` com texto personalizado mencionando o percentual de gasto em alimentação.

**Estimativa:** 1 dia

---

<a name="t14"></a>
### T1.4 — Detector de Investidor Ativo ✅

**O que implementar:** Detectar usuários com movimentações regulares em corretoras, distinguindo investidor casual de ativo de diversificado.

**Depende de:** T1.1 (campo `is_broker_txn`)

**Arquivo a criar:** `backend/app/optimizer/detectors/investor_detector.py`

```python
# app/optimizer/detectors/investor_detector.py

from __future__ import annotations
import polars as pl


class InvestorDetector:
    """
    Detecta perfil de investidor e calcula savings_rate real.

    investor_type: NONE | CASUAL | ATIVO | DIVERSIFICADO
    savings_rate: (receitas - despesas) / receitas — calculado sobre o período disponível
    """

    # Keywords de dividendos/proventos (créditos) — indica investidor com carteira ativa
    _INCOME_INVESTMENT_KEYWORDS = ["DIVIDENDO", "JCP", "PROVENTO", "RENDIMENTO CDB", "RENDIMENTO LCI"]

    def calc_investor_profile(self, df: pl.DataFrame) -> dict:
        if df.is_empty():
            return {"investor_type": "NONE", "savings_rate": 0.0, "investment_transfers_monthly": 0.0}

        broker_txns = 0
        investment_transfers_monthly = 0.0

        if "is_broker_txn" in df.columns:
            broker_df = df.filter(pl.col("is_broker_txn") & (pl.col("amount") < 0))
            broker_txns = len(broker_df)
            if broker_txns > 0:
                months = max(df["date"].dt.month().n_unique(), 1)
                investment_transfers_monthly = float(broker_df["amount"].sum()) * -1 / months

        # Recebimento de dividendos (investidor com carteira existente)
        has_dividends = False
        if "description" in df.columns:
            pattern = "|".join(self._INCOME_INVESTMENT_KEYWORDS)
            has_dividends = df.filter(
                (pl.col("amount") > 0) &
                pl.col("description").str.to_uppercase().str.contains(pattern)
            ).height > 0

        # Diversificação: corretoras distintas
        broker_diversity = 0
        if "description" in df.columns and "is_broker_txn" in df.columns:
            broker_diversity = df.filter(pl.col("is_broker_txn"))["description"].n_unique()

        # Classificar tipo
        if broker_txns == 0 and not has_dividends:
            investor_type = "NONE"
        elif broker_txns <= 3 and not has_dividends:
            investor_type = "CASUAL"
        elif broker_diversity >= 2 or has_dividends:
            investor_type = "DIVERSIFICADO"
        else:
            investor_type = "ATIVO"

        return {
            "investor_type": investor_type,
            "investment_transfers_monthly": round(investment_transfers_monthly, 2),
            "has_dividends": has_dividends,
            "broker_diversity": broker_diversity,
        }
```

**Uso no Optimizer:** `investor_type` != "NONE" → penalizar cartões com anuidade alta sem benefício de investimento.

**Sobre `savings_rate`:** **Não recalcular aqui.** `profiles.py::UserProfileAnalyzer` já calcula `savings_rate` completo com `behavior_tier` e `resilience_score` (6 fatores: savings, equilíbrio, proporção, tendência, committed_pct, income_stability). No `ConsumptionProfiler.build()`, o `savings_rate` do `UserProfile` deve ser lido de `UserProfileAnalyzer(df, income_profile).savings_rate` em vez de recalculado. Ver T1.6.

**Estimativa:** 1 dia

---

<a name="t15"></a>
### T1.5 — Detector de MEI/Microempreendedor ✅

**O que implementar:** Identificar usuários PF que têm padrão de gasto/renda de MEI, para eventual recomendação de conta PJ + separação de fluxos.

**Depende de:** T1.1 (campo `is_b2b`), `IncomeProfile.income_pattern` (já existente)

**Arquivo a criar:** `backend/app/optimizer/detectors/mei_detector.py`

```python
# app/optimizer/detectors/mei_detector.py

from __future__ import annotations
import polars as pl
from app.forecast.etl.income_profiler import IncomeProfile


class MEIDetector:
    """
    Detecta padrão de microempreendedor em contas PF.
    Complementa o IncomeProfiler (que já detecta MIXED/PJ).
    """

    def detect_mei_pattern(
        self,
        df: pl.DataFrame,
        income_profile: IncomeProfile | None,
    ) -> dict:

        signals = []

        # Sinal 1: IncomeProfiler já classificou como MIXED ou PJ
        if income_profile and income_profile.income_pattern in ("MIXED", "PJ"):
            signals.append("income_pattern_pj")

        # Sinal 2: gastos em ferramentas B2B
        b2b_spend = 0.0
        if "is_b2b" in df.columns:
            b2b_df = df.filter(pl.col("is_b2b") & (pl.col("amount") < 0))
            b2b_spend = float(b2b_df["amount"].sum()) * -1
            if b2b_spend > 50:
                signals.append("b2b_tools")

        # Sinal 3: recebimentos de múltiplos CNPJs (Open Finance fornece o campo payer_document)
        pj_credits = 0
        if "payer_document_type" in df.columns:
            pj_credits = df.filter(
                (pl.col("amount") > 0) &
                (pl.col("payer_document_type") == "CNPJ")
            ).height
            if pj_credits >= 3:
                signals.append("multiple_cnpj_payers")

        # Sinal 4: renda irregular com variância alta (já calculada no income_profile)
        # Campo correto: income_stability (float 0.0–1.0), não income_stability_score
        # Definido em income_profiler.py:132 — CLT bem detectado → ~0.9, PJ variável → ~0.3
        if income_profile and income_profile.income_stability < 0.4:
            signals.append("unstable_income")

        is_mei = len(signals) >= 2
        confidence = min(len(signals) / 4, 1.0)

        return {
            "is_likely_mei": is_mei,
            "mei_confidence": round(confidence, 2),
            "mei_signals": signals,
            "b2b_spend_monthly": round(b2b_spend / max(df["date"].dt.month().n_unique(), 1), 2),
        }
```

**Uso no Produto:** Se `is_likely_mei=True`, inserir no relatório do optimizer uma seção de "Otimização para Empreendedores" — sugerindo separação de fluxo PF/PJ e cartão empresarial.

**Estimativa:** 1 dia

---

<a name="t16"></a>
### T1.6 — Expansão do `UserProfile` com novos campos ✅

**O que implementar:** Adicionar os campos dos detectors ao `UserProfile` existente sem quebrar a interface atual.

**Arquivo a modificar:** `backend/app/optimizer/profiler.py`

**Mudança no dataclass `UserProfile`:**

```python
# Adicionar após credit_spend_ratio: float = 1.0

# ── Campos de Inteligência Comportamental (Fase 1) ────────────────────────
# Todos com default para compatibilidade retroativa

travel_frequency_score: float = 0.0          # 0–100 (TravelDetector)
travel_profile: str = "OCASIONAL"            # OCASIONAL | MODERADO | FREQUENTE | INTENSO
foodie_score: float = 0.0                    # 0–100 (FoodieDetector)
foodie_profile: str = "BASICO"               # BASICO | APRECIADOR | GOURMET | ENTUSIASTA

# savings_rate: FONTE = profiles.py::UserProfileAnalyzer.savings_rate (já calculado com
# income_profile filtrado, behavior_tier e resilience_score de 6 fatores).
# NÃO recalcular aqui — ler de UserProfileAnalyzer(df, income_profile).savings_rate
# Valor em % (ex: 22.5 = 22.5%). profiles.py usa porcentagem, não fração.
savings_rate: float = 0.0

investor_type: str = "NONE"                  # NONE | CASUAL | ATIVO | DIVERSIFICADO
is_likely_mei: bool = False                  # sinal de microempreendedor
lifestyle_cluster: str = "NAO_CLASSIFICADO"  # ver T1.7
merchant_diversity_score: float = 0.0        # 0–100: diversidade de merchants únicos

# subscription_burn_monthly: R$/mês em assinaturas de streaming (STREAMING L2).
# DISTINTO de committed_percentage: committed_pct cobre TODAS as obrigações recorrentes
# (shadow_invoices = parcelas + assinaturas), normalizado pelo gasto mensal total.
# subscription_burn_monthly é apenas streaming (Netflix, Spotify, etc.), em R$/mês absoluto.
subscription_burn_monthly: float = 0.0
```

**Mudança no método `build()` do `ConsumptionProfiler`:**

```python
# Após calcular income_profile e credit_spend_ratio:

# Detectors comportamentais
from app.optimizer.detectors.travel_detector import TravelDetector
from app.optimizer.detectors.foodie_detector import FoodieDetector
from app.optimizer.detectors.investor_detector import InvestorDetector
from app.optimizer.detectors.mei_detector import MEIDetector

total_spend_12m = monthly_avg_spend * data_coverage_months

travel_result = TravelDetector().calc_travel_score(df, total_spend_12m)
foodie_result = FoodieDetector().calc_foodie_score(df, monthly_avg_spend)
investor_result = InvestorDetector().calc_investor_profile(df)
mei_result = MEIDetector().detect_mei_pattern(df, income_profile)
merchant_diversity = _calc_merchant_diversity(df)
subscription_burn = _calc_subscription_burn(df, data_coverage_months)

# savings_rate: LIDO de UserProfileAnalyzer — não recalcular.
# profiles.py::UserProfileAnalyzer já calcula com income filtrado (IncomeProfiler)
# e produz behavior_tier + resilience_score. Reutilizar aqui.
from app.forecast.etl.profiles import UserProfileAnalyzer as _UPA
_etl_profile = _UPA().analyze(df, income_profile, committed_percentage)
savings_rate_pct = _etl_profile.savings_rate      # em % (ex: 22.5)
resilience_score = _etl_profile.resilience_score  # 0–100, usado pelo FSS em T2.2
```

**Helpers adicionais em `profiler.py`:**

```python
def _calc_merchant_diversity(df: pl.DataFrame) -> float:
    """Score 0–100: quanto mais merchants únicos, mais diversificado."""
    if "description" not in df.columns:
        return 0.0
    unique_merchants = df.filter(pl.col("amount") < 0)["description"].n_unique()
    # 100 merchants únicos = 100 pts (floor em 0, teto em 100)
    return round(min(unique_merchants, 100), 1)


def _calc_subscription_burn(df: pl.DataFrame, coverage_months: int) -> float:
    """R$/mês em assinaturas (streaming + serviços recorrentes detectados)."""
    if "merchant_category_l2" not in df.columns:
        return 0.0
    streaming_df = df.filter(
        pl.col("merchant_category_l2").is_in({"STREAMING"}) & (pl.col("amount") < 0)
    )
    if streaming_df.is_empty():
        return 0.0
    total = float(streaming_df["amount"].sum()) * -1
    return round(total / max(coverage_months, 1), 2)
```

**Testes de aceitação:**
- `UserProfile` construído com transações mistas → todos novos campos populados
- `UserProfile` construído com DataFrame vazio → todos novos campos têm valores default (sem exceção)
- Serialização JSON do UserProfile não quebra (verificar `to_dict()` se existir)

**Estimativa:** 1–2 dias

---

<a name="t17"></a>
### T1.7 — Clustering K-Means com 5 Clusters Básicos ✅

**O que implementar:** Classificar cada UserProfile em um dos 5 clusters principais. Sem dependência de banco de dados — clustering heurístico baseado em regras de score (ML real na Fase 3).

**Justificativa para abordagem heurística na Fase 1:** Com < 50k usuários, treinar HDBSCAN não é estatisticamente robusto. Usar regras de score garante consistência e explicabilidade.

**Arquivo a criar:** `backend/app/optimizer/detectors/lifestyle_classifier.py`

```python
# app/optimizer/detectors/lifestyle_classifier.py

from __future__ import annotations
from app.optimizer.profiler import UserProfile


# Clusters disponíveis (subconjunto dos 9 do doc — os 5 com maior impacto no optimizer)
CLUSTER_EXPLORER_GLOBAL    = "EXPLORADOR_GLOBAL"
CLUSTER_URBAN_FOODIE       = "URBANO_FOODIE"
CLUSTER_INVESTOR           = "INVESTIDOR_CAUTELOSO"
CLUSTER_FAMILY             = "FAMILIA_ESTRUTURADA"
CLUSTER_DIGITAL_NATIVE     = "DIGITAL_NATIVO"
CLUSTER_FINANCIAL_STRESS   = "ESTRESSE_FINANCEIRO"
CLUSTER_MICROEMPREENDEDOR  = "MICROEMPREENDEDOR"
CLUSTER_UNCLASSIFIED       = "NAO_CLASSIFICADO"


class LifestyleClassifier:
    """
    Classifica o UserProfile em um dos clusters de estilo de vida.

    Fase 1: regras determinísticas baseadas em scores dos detectors.
    Fase 3: substituir por modelo ML (HDBSCAN ou K-Means treinado).

    Retorna o cluster primário (string) e um dict de scores de afinidade
    para todos os clusters (0.0–1.0) para uso futuro.
    """

    def classify(self, profile: UserProfile) -> dict:
        scores = {
            CLUSTER_EXPLORER_GLOBAL:   self._score_explorer(profile),
            CLUSTER_URBAN_FOODIE:      self._score_foodie(profile),
            CLUSTER_INVESTOR:          self._score_investor(profile),
            CLUSTER_FAMILY:            self._score_family(profile),
            CLUSTER_DIGITAL_NATIVE:    self._score_digital_native(profile),
            CLUSTER_FINANCIAL_STRESS:  self._score_financial_stress(profile),
            CLUSTER_MICROEMPREENDEDOR: self._score_mei(profile),
        }

        primary = max(scores, key=lambda k: scores[k])

        # Threshold mínimo — se nenhum cluster tem afinidade > 0.35, não classificar
        if scores[primary] < 0.35:
            primary = CLUSTER_UNCLASSIFIED

        return {
            "lifestyle_cluster": primary,
            "cluster_scores": {k: round(v, 3) for k, v in scores.items()},
        }

    def _score_explorer(self, p: UserProfile) -> float:
        score = 0.0
        score += min(p.travel_frequency_score / 100, 1.0) * 0.50
        score += min(p.international_spend_monthly / 500, 1.0) * 0.30
        score += (1.0 if p.travel_profile in ("FREQUENTE", "INTENSO") else 0.0) * 0.20
        return score

    def _score_foodie(self, p: UserProfile) -> float:
        score = 0.0
        score += min(p.foodie_score / 100, 1.0) * 0.60
        food_spend = p.spend_by_category.get("Alimentação", 0) + p.spend_by_category.get("alimentacao", 0)
        pct_food = food_spend / p.monthly_avg_spend if p.monthly_avg_spend > 0 else 0
        score += min(pct_food * 2, 1.0) * 0.40
        return score

    def _score_investor(self, p: UserProfile) -> float:
        score = 0.0
        score += (1.0 if p.investor_type in ("ATIVO", "DIVERSIFICADO") else
                  0.5 if p.investor_type == "CASUAL" else 0.0) * 0.50
        score += min(p.savings_rate * 2, 1.0) * 0.50
        return score

    def _score_family(self, p: UserProfile) -> float:
        # Família: gasto alto em saúde + educação + supermercado, renda estável
        edu_health = (
            p.spend_by_category.get("Saúde", 0)
            + p.spend_by_category.get("Educação", 0)
        )
        edu_health_pct = edu_health / p.monthly_avg_spend if p.monthly_avg_spend > 0 else 0
        score = min(edu_health_pct * 3, 0.6)

        if p.income_profile and p.income_profile.income_pattern == "CLT":
            score += 0.2
        if p.spending_stability > 0.7:
            score += 0.2
        return score

    def _score_digital_native(self, p: UserProfile) -> float:
        score = 0.0
        score += min(p.subscription_burn_monthly / 200, 1.0) * 0.40
        # Alto uso de PIX/débito, sem banco físico (proxy: baixo uso de crédito e alto PIX)
        pix_proxy = 1.0 - p.credit_spend_ratio
        score += min(pix_proxy * 1.5, 1.0) * 0.30
        score += min(p.merchant_diversity_score / 80, 1.0) * 0.30
        return score

    def _score_financial_stress(self, p: UserProfile) -> float:
        score = 0.0
        if p.savings_rate < -0.05:
            score += 0.4
        if p.committed_percentage > 0.6:
            score += 0.3
        if p.spending_stability < 0.3:
            score += 0.3
        return score

    def _score_mei(self, p: UserProfile) -> float:
        if p.is_likely_mei:
            return 0.8
        if p.income_profile and p.income_profile.income_pattern in ("PJ", "MIXED"):
            return 0.5
        return 0.0
```

**Integração no `ConsumptionProfiler.build()`:**

```python
# Após calcular todos os detectors:
from app.optimizer.detectors.lifestyle_classifier import LifestyleClassifier
cluster_result = LifestyleClassifier().classify(profile_parcial)
profile.lifestyle_cluster = cluster_result["lifestyle_cluster"]
```

**Testes de aceitação:**
- Usuário com `travel_frequency_score=85`, `international_spend_monthly=700` → cluster `EXPLORADOR_GLOBAL`
- Usuário com `savings_rate=0.35`, `investor_type=ATIVO` → cluster `INVESTIDOR_CAUTELOSO`
- Usuário com todos os scores < 0.35 → cluster `NAO_CLASSIFICADO`

**Estimativa:** 2 dias

---

<a name="t18"></a>
### T1.8 — Integração dos Detectors no Pipeline do Optimizer ✅

**O que implementar:** Garantir que os novos campos do `UserProfile` são consumidos pelo `CardRanking` e `InsightGenerator` com melhorias concretas na qualidade das recomendações.

**Arquivo a modificar:** `backend/app/optimizer/ranking.py`

Adicionar ao `_compute_score()`:

```python
# Após o bloco de benefits_bonus existente:

# Bônus por cluster — ajusta relevância de benefícios ao estilo de vida
cluster = getattr(profile, "lifestyle_cluster", "NAO_CLASSIFICADO")

if cluster == "EXPLORADOR_GLOBAL":
    # Para exploradores, lounge e travel valem mais
    if BenefitTag.LOUNGE in result.benefit_tags or BenefitTag.TRAVEL in result.benefit_tags:
        benefits_bonus *= 1.25  # +25% no bonus de benefícios de viagem

elif cluster == "URBANO_FOODIE":
    # Para foodies, cashback em alimentação vale mais
    if BenefitTag.CASHBACK in result.benefit_tags:
        food_spend = profile.spend_by_category.get("Alimentação", 0)
        if food_spend > 500:
            benefits_bonus += food_spend * 0.005  # R$5/mês por R$1k em alimentação

elif cluster == "INVESTIDOR_CAUTELOSO":
    # Para investidores, cartões com rendimento ou cashback direto valem mais
    # (penalizar anuidades altas — o investidor calcula custo de oportunidade)
    if result.annual_fee > 500:
        score *= 0.90
```

**Arquivo a modificar:** `backend/app/optimizer/insight_generator.py`

Adicionar insights baseados em cluster:

```python
# Novo método: _generate_cluster_insights()
def _generate_cluster_insights(
    self,
    ranked: list[CardSimulationResult],
    profile: UserProfile,
) -> list[ActionableInsight]:
    """Insights específicos por cluster de estilo de vida."""
    insights = []
    cluster = getattr(profile, "lifestyle_cluster", "NAO_CLASSIFICADO")

    if cluster == "EXPLORADOR_GLOBAL" and profile.travel_spend_monthly > 500:
        # Verificar se o top cartão tem milhas
        top_card = ranked[0] if ranked else None
        if top_card and BenefitTag.TRAVEL not in top_card.benefit_tags:
            insights.append(ActionableInsight(
                type=InsightType.MUDAR_CATEGORIA,
                title="Seu perfil de viajante merece milhas",
                description=(
                    f"Você gastou R${profile.travel_spend_monthly * 12:.0f}/ano em viagens "
                    f"sem acumular milhas. Um cartão de milhas premium poderia gerar "
                    f"uma passagem gratuita por ano no seu padrão de uso."
                ),
                effort=InsightEffort.MEDIO,
                ...
            ))

    return insights
```

**Estimativa:** 2–3 dias

---

<a name="fase-2"></a>
## FASE 2 — Life Events, FSS e Motor de Recomendação (3–6 meses)

**Meta:** Detectar momentos de vida críticos (nascimento de filho, mudança, novo emprego), calcular o Financial Stress Score para intervenção proativa, e montar o motor de recomendação hiperpersonalizada com 4 pesos.

**Pré-requisito:** Fase 1 completa (feature store enriquecido + UserProfile expandido).

---

<a name="t21"></a>
### T2.1 — Detector de Eventos de Vida (Life Stage Intelligence) ✅

**O que implementar:** Sistema de detecção de eventos de vida baseado em padrões de transações. Cada evento tem um conjunto de sinais, threshold de confiança e ação associada.

**Arquivo a criar:** `backend/app/optimizer/detectors/life_events_detector.py`

```python
# app/optimizer/detectors/life_events_detector.py
"""
LifeEventsDetector — detecta eventos de vida de alta relevância financeira.

Cada detector retorna:
    {
        "event": str,          # identificador do evento
        "confidence": float,   # 0.0–1.0
        "detected_at": date,   # data aproximada do evento
        "trigger_action": str, # ação a ser tomada pelo produto
    }

O detector opera sobre dois DataFrames:
    - txns_recent: transações dos últimos 60 dias (janela de detecção)
    - txns_history: transações de 6–18 meses atrás (baseline para comparação)
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date
import polars as pl


@dataclass
class LifeEvent:
    event: str
    confidence: float
    detected_at: date
    trigger_action: str
    supporting_signals: list[str]


_BABY_KEYWORDS = [
    "FRALDA", "PAMPERS", "HUGGIES", "JOHNSON BABY", "MATERNIDADE",
    "ENXOVAL", "BEBE", "INFANTIL", "KINDER", "NUTRILON", "NAN NESTLE",
    "NENUCO", "CHICCO", "BRINQUEDO BEBE",
]

_MOVING_KEYWORDS = [
    "DEPOSITO ALUGUEL", "ALUGUEL", "MUDANCA", "LEROY MERLIN",
    "TOKSTOK", "ETNA", "MADEIRAMADEIRA", "CASA SHOW", "TELHANORTE",
    "CONSTRUTORA", "IMOVEL",
]

_WEDDING_KEYWORDS = [
    "BUFFET", "CERIMONIAL", "FOTOGRAFO CASAMENTO", "NOIVAS", "FESTAS",
    "MUITO PELO RISO", "ALUGUEL VESTIDO", "DECORAÇÃO FESTA",
]

_EDUCATION_KEYWORDS = [
    "FACULDADE", "UNIVERSIDADE", "MENSALIDADE EAD", "ESTACIO",
    "ANHANGUERA", "UNIP", "SENAC", "FIES", "PROUNI",
]

_SALARY_INCREASE_THRESHOLD = 0.20  # 20% de aumento de renda = novo emprego/promoção
_SALARY_DROP_THRESHOLD = -0.20     # 20% de queda = perda de renda


class LifeEventsDetector:

    def detect_all(
        self,
        txns_recent: pl.DataFrame,    # últimos 60 dias
        txns_history: pl.DataFrame,   # 6–18 meses atrás
        income_recent: float,
        income_historical: float,
    ) -> list[LifeEvent]:
        events = []

        baby = self._detect_new_baby(txns_recent, txns_history)
        if baby:
            events.append(baby)

        moving = self._detect_moving(txns_recent, txns_history)
        if moving:
            events.append(moving)

        wedding = self._detect_wedding(txns_recent, txns_history)
        if wedding:
            events.append(wedding)

        education = self._detect_new_education(txns_recent, txns_history)
        if education:
            events.append(education)

        income_event = self._detect_income_change(income_recent, income_historical)
        if income_event:
            events.append(income_event)

        return events

    def _keyword_spend(self, df: pl.DataFrame, keywords: list[str]) -> float:
        if df.is_empty() or "description" not in df.columns:
            return 0.0
        pattern = "|".join(keywords)
        filtered = df.filter(
            (pl.col("amount") < 0) &
            pl.col("description").str.to_uppercase().str.contains(pattern)
        )
        return float(filtered["amount"].sum()) * -1 if not filtered.is_empty() else 0.0

    def _detect_new_baby(
        self, recent: pl.DataFrame, history: pl.DataFrame
    ) -> LifeEvent | None:
        recent_spend = self._keyword_spend(recent, _BABY_KEYWORDS)
        historical_spend = self._keyword_spend(history, _BABY_KEYWORDS)

        new_pattern = recent_spend > 200 and historical_spend < 50

        if new_pattern:
            signals = [f"baby_spend_recent=R${recent_spend:.0f}", f"baby_spend_historical=R${historical_spend:.0f}"]
            confidence = 0.85 if recent_spend > 500 else 0.65
            return LifeEvent(
                event="new_baby",
                confidence=confidence,
                detected_at=date.today(),
                trigger_action="show_baby_financial_planning",
                supporting_signals=signals,
            )
        return None

    def _detect_moving(
        self, recent: pl.DataFrame, history: pl.DataFrame
    ) -> LifeEvent | None:
        recent_spend = self._keyword_spend(recent, _MOVING_KEYWORDS)
        historical_spend = self._keyword_spend(history, _MOVING_KEYWORDS)

        # Novo padrão de aluguel ou gasto alto em móveis que não existia antes
        is_new_pattern = recent_spend > 500 and recent_spend > historical_spend * 3

        if is_new_pattern:
            return LifeEvent(
                event="home_change",
                confidence=0.70,
                detected_at=date.today(),
                trigger_action="show_financing_vs_rent_analysis",
                supporting_signals=[f"moving_spend=R${recent_spend:.0f}"],
            )
        return None

    def _detect_wedding(
        self, recent: pl.DataFrame, history: pl.DataFrame
    ) -> LifeEvent | None:
        recent_spend = self._keyword_spend(recent, _WEDDING_KEYWORDS)
        if recent_spend > 1000:
            return LifeEvent(
                event="wedding",
                confidence=0.75,
                detected_at=date.today(),
                trigger_action="show_couple_financial_planning",
                supporting_signals=[f"wedding_spend=R${recent_spend:.0f}"],
            )
        return None

    def _detect_new_education(
        self, recent: pl.DataFrame, history: pl.DataFrame
    ) -> LifeEvent | None:
        recent_spend = self._keyword_spend(recent, _EDUCATION_KEYWORDS)
        historical_spend = self._keyword_spend(history, _EDUCATION_KEYWORDS)

        if recent_spend > 300 and historical_spend < 100:
            return LifeEvent(
                event="new_education",
                confidence=0.80,
                detected_at=date.today(),
                trigger_action="show_student_account_options",
                supporting_signals=[f"edu_spend_recent=R${recent_spend:.0f}"],
            )
        return None

    def _detect_income_change(
        self, income_recent: float, income_historical: float
    ) -> LifeEvent | None:
        if income_historical <= 0:
            return None

        change_ratio = (income_recent - income_historical) / income_historical

        if change_ratio > _SALARY_INCREASE_THRESHOLD:
            return LifeEvent(
                event="income_increase",
                confidence=0.80,
                detected_at=date.today(),
                trigger_action="suggest_investment_of_raise",
                supporting_signals=[f"income_change={change_ratio:.1%}"],
            )

        if change_ratio < _SALARY_DROP_THRESHOLD:
            return LifeEvent(
                event="income_drop",
                confidence=0.85,
                detected_at=date.today(),
                trigger_action="activate_defense_mode",
                supporting_signals=[f"income_change={change_ratio:.1%}"],
            )

        return None
```

**Integração:** Chamar `LifeEventsDetector.detect_all()` no `optimizer_service.py` após construir o perfil. Os eventos detectados devem:
1. Ser incluídos no `OptimizationReport` como campo `life_events: list[dict]`
2. Acionar modificadores no ranker (p.ex.: `income_drop` ativa "modo defesa" — penalizar cartões com anuidade > R$400)

**Arquivo a modificar:** `backend/app/optimizer/models.py` — adicionar `life_events` ao `OptimizationReport`.

**Estimativa:** 3–4 dias

---

<a name="t22"></a>
### T2.2 — Financial Stress Score (FSS) ✅

**O que implementar:** Índice único 0–100 (100 = máximo estresse) que combina múltiplos indicadores de deterioração financeira. Trigger para intervenção proativa.

**IMPORTANTE — Relação com `resilience_score` de `profiles.py`:**

`profiles.py::UserProfileAnalyzer._calculate_resilience_score()` já calcula um score de resiliência financeira com 6 fatores (savings_rate, equilíbrio renda/gasto, proporção despesa/renda, tendência, committed_pct, income_stability). O FSS **não duplica esses fatores** — ele os converte para escala de estresse e adiciona os componentes que o `resilience_score` não cobre: rotativo do cartão, cheque especial e queda abrupta de renda.

**Relação:** `fss ≈ 100 - resilience_score` como aproximação grosseira. Formalmente: o FSS é construído **sobre** o `resilience_score` existente, adicionando sinais de espiral de dívida que o resilience_score não detecta.

**Arquivo a criar:** `backend/app/optimizer/detectors/fss_calculator.py`

```python
# app/optimizer/detectors/fss_calculator.py

from __future__ import annotations
import polars as pl
from app.optimizer.profiler import UserProfile
from app.forecast.etl.profiles import UserProfileAnalyzer


class FSSCalculator:
    """
    Financial Stress Score — índice 0–100 (100 = máximo estresse).

    ARQUITETURA: O FSS complementa (não duplica) o resilience_score de profiles.py.
    Componentes exclusivos do FSS (não cobertos pelo resilience_score):
    - Rotativo do cartão detectado por proxy:  até 30 pts
    - Uso de cheque especial por keyword:      até 25 pts
    - Queda abrupta de renda (>15%):          até 20 pts

    Componentes compartilhados com resilience_score (convertidos de escala):
    - Tendência de savings rate:               até 15 pts
    - Comprometimento futuro (>40%):           até 20 pts

    Para evitar duplicação, quando resilience_score já está disponível no perfil,
    usar: fss_base = max(0, 100 - resilience_score) e adicionar apenas os sinais
    exclusivos (rotativo, cheque especial, queda de renda).

    Teto: 100 pts
    """

    def calc_fss(
        self,
        profile: UserProfile,
        txns_90d: pl.DataFrame,
        income_3m_avg: float | None = None,
        income_12m_avg: float | None = None,
        resilience_score: int | None = None,  # se disponível, usar como base
    ) -> dict:
        score = 0.0
        signals = []

        # Base: se resilience_score disponível (de profiles.py), converter para escala FSS
        # Isso evita recalcular savings_rate, tendência e committed_pct do zero
        if resilience_score is not None:
            # resilience 0–100 → stress 0–50 (componentes básicos)
            base_stress = max(0, (100 - resilience_score) * 0.50)
            score += base_stress
            if resilience_score < 35:
                signals.append(f"low_resilience={resilience_score}")
        else:
            # Fallback sem resilience_score: calcular components básicos manualmente
            # 1a. Tendência de savings rate (profile.savings_rate em %)
            savings_pct = getattr(profile, "savings_rate", 0.0)
            if savings_pct < -5:  # deficit > 5%
                score += 15
                signals.append(f"negative_savings_rate={savings_pct:.1f}%")
            elif savings_pct < 5:
                score += 7
                signals.append("low_savings_rate")

            # 1b. Comprometimento futuro
            future_commitment = profile.committed_percentage
            if future_commitment > 0.4:
                score += min((future_commitment - 0.4) * 100, 20)
                signals.append(f"future_commitment={future_commitment:.1%}")

        # 2. Rotativo do cartão — EXCLUSIVO FSS (não está no resilience_score)
        # Proxy: committed_percentage alto + credit_spend_ratio alto
        if profile.committed_percentage > 0.5 and profile.credit_spend_ratio > 0.7:
            revolving_score = min((profile.committed_percentage - 0.5) * 60, 30)
            score += revolving_score
            signals.append(f"likely_revolving={profile.committed_percentage:.1%}")

        # 3. Cheque especial — EXCLUSIVO FSS
        overdraft_score = self._calc_overdraft_usage(txns_90d)
        score += overdraft_score * 25
        if overdraft_score > 0.1:
            signals.append(f"overdraft_usage={overdraft_score:.1%}")

        # 4. Queda abrupta de renda — EXCLUSIVO FSS
        if income_3m_avg and income_12m_avg and income_12m_avg > 0:
            income_drop = (income_3m_avg - income_12m_avg) / income_12m_avg
            if income_drop < -0.15:
                score += 20
                signals.append(f"income_drop={income_drop:.1%}")

        fss = round(min(score, 100.0), 1)

        if fss <= 20:
            level = "SAUDAVEL"
        elif fss <= 40:
            level = "ATENCAO"
        elif fss <= 65:
            level = "ALERTA"
        else:
            level = "CRITICO"

        return {
            "fss": fss,
            "fss_level": level,
            "fss_signals": signals,
        }

    def _calc_overdraft_usage(self, df: pl.DataFrame) -> float:
        """Estima uso de cheque especial por keywords na descrição (0.0–1.0)."""
        if df.is_empty() or "description" not in df.columns:
            return 0.0

        overdraft_patterns = ["CHEQUE ESPECIAL", "LIMITE ESPECIAL", "IOF ESPECIAL", "JUROS ESPECIAL"]
        pattern = "|".join(overdraft_patterns)

        overdraft_months = df.filter(
            pl.col("description").str.to_uppercase().str.contains(pattern)
        ).with_columns(
            (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
        ).select("ym").unique().height

        total_months = df.with_columns(
            (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
        ).select("ym").unique().height

        return overdraft_months / total_months if total_months > 0 else 0.0
```

**Integração com o Optimizer:**

No `optimizer_service.py`, após construir o perfil:

```python
from app.optimizer.detectors.fss_calculator import FSSCalculator

fss_result = FSSCalculator().calc_fss(profile, transactions_df)
profile.fss = fss_result["fss"]
profile.fss_level = fss_result["fss_level"]

# Modo defesa: FSS crítico → suspender recomendações de produtos novos
if fss_result["fss_level"] == "CRITICO":
    logger.warning(
        "FSS CRÍTICO (score=%.0f) para usuário — ativando modo defesa. "
        "Recomendações de novos produtos suspensas.",
        fss_result["fss"],
    )
    # Filtrar apenas insights de renegociação e portabilidade
    # (InsightType.CANCELAR_CARTAO e alertas de custo)
```

**Adicionar ao `UserProfile`:**
```python
fss: float = 0.0
fss_level: str = "SAUDAVEL"  # SAUDAVEL | ATENCAO | ALERTA | CRITICO
```

**Estimativa:** 2 dias

---

<a name="t23"></a>
### T2.3 — Detector de Pai/Mãe com Filhos ✅

**O que implementar:** Identificar famílias com filhos — um dos perfis de maior LTV e com necessidades financeiras específicas (previdência, educação, saúde).

**Arquivo a criar:** `backend/app/optimizer/detectors/family_detector.py`

```python
# app/optimizer/detectors/family_detector.py

from __future__ import annotations
import polars as pl

_SCHOOL_KEYWORDS = ["ESCOLA", "COLEGIO", "CRECHE", "MATERNAL", "ENSINO INFANTIL"]
_BABY_PRODUCT_KEYWORDS = ["FRALDA", "PAMPERS", "HUGGIES", "CHICCO", "FISHER PRICE"]
_PEDIATRIC_KEYWORDS = ["PEDIATR", "INFANTIL CLINICA", "PLANO SAUDE CRIANÇA", "PLANO FAMILIAR"]
_KIDS_CLOTHING_KEYWORDS = ["RENNER KIDS", "HERING KIDS", "CARTER", "POSTHAUS", "ZARA KIDS"]
_ENTERTAINMENT_KIDS_KEYWORDS = ["MUNDO BITA", "MAGIC CITY", "HOPI HARI", "PARQUE", "BRINQUEDOTECA"]
_PHARMACY_KEYWORDS = ["FARMACIA", "DROGASIL", "PACHECO", "DROGA RAIA"]


class FamilyDetector:
    """
    Detecta perfil de pai/mãe com filhos pequenos.

    family_score (0–100), is_family_with_kids (bool)
    """

    def detect_family_profile(self, df: pl.DataFrame) -> dict:
        if df.is_empty() or "description" not in df.columns:
            return {"is_family_with_kids": False, "family_score": 0.0}

        score = 0.0
        signals = []

        expenses = df.filter(pl.col("amount") < 0)

        def keyword_count(keywords: list[str]) -> int:
            if expenses.is_empty():
                return 0
            pattern = "|".join(keywords)
            return expenses.filter(
                pl.col("description").str.to_uppercase().str.contains(pattern)
            ).height

        def keyword_spend(keywords: list[str]) -> float:
            if expenses.is_empty():
                return 0.0
            pattern = "|".join(keywords)
            filtered = expenses.filter(
                pl.col("description").str.to_uppercase().str.contains(pattern)
            )
            return float(filtered["amount"].sum()) * -1 if not filtered.is_empty() else 0.0

        # Escola/creche
        school_spend = keyword_spend(_SCHOOL_KEYWORDS)
        if school_spend > 200:
            score += 30
            signals.append(f"school_spend=R${school_spend:.0f}")

        # Produtos de bebê
        baby_spend = keyword_spend(_BABY_PRODUCT_KEYWORDS)
        if baby_spend > 100:
            score += 25
            signals.append(f"baby_products=R${baby_spend:.0f}")

        # Pediatra/plano infantil
        pediatric_count = keyword_count(_PEDIATRIC_KEYWORDS)
        if pediatric_count >= 2:
            score += 20
            signals.append(f"pediatric_visits={pediatric_count}")

        # Roupas infantis
        kids_clothing = keyword_spend(_KIDS_CLOTHING_KEYWORDS)
        if kids_clothing > 100:
            score += 15
            signals.append(f"kids_clothing=R${kids_clothing:.0f}")

        # Entretenimento infantil
        kids_entertainment = keyword_count(_ENTERTAINMENT_KIDS_KEYWORDS)
        if kids_entertainment >= 2:
            score += 10
            signals.append(f"kids_entertainment={kids_entertainment}")

        family_score = round(min(score, 100.0), 1)
        is_family = family_score >= 40

        return {
            "is_family_with_kids": is_family,
            "family_score": family_score,
            "family_signals": signals,
        }
```

**Uso:** No `LifestyleClassifier`, usar `family_score >= 40` para reforçar o cluster `FAMILIA_ESTRUTURADA`. No `InsightGenerator`, se `is_family_with_kids=True`, priorizar insights sobre cashback em supermercado e farmácia.

**Estimativa:** 1 dia

---

<a name="t24"></a>
### T2.4 — Motor de Recomendação Hiperpersonalizada (4-weight ranker) ✅

**O que implementar:** Substituir o ranker atual (baseado apenas em `net_gain`) por um motor com 4 pesos que considera cluster, impacto financeiro, conversão estimada e timing.

**Contexto atual:** `CardRanking._compute_score()` usa: `net_gain_expected × liquidity_multiplier + benefits_bonus`, com penalidades de confiança e elegibilidade.

**Arquivo a modificar:** `backend/app/optimizer/ranking.py`

Adicionar método `rank_hyperpersonalized()` que pode conviver com o `rank()` atual:

```python
# ranking.py — novo método (não substitui rank() atual, é adicionado)

def rank_hyperpersonalized(
    self,
    results: list[CardSimulationResult],
    profile: UserProfile,
) -> list[CardSimulationResult]:
    """
    Ranker hiperpersonalizado com 4 pesos (melhorias_analise_perfil.md §8.1):
        W1 = relevância ao cluster (40%)
        W2 = impacto financeiro em R$ (30%)
        W3 = propensity estimada (20%)  — Fase 1: heurística, Fase 3: modelo ML
        W4 = timing/adequação momento (10%)

    Backward compatible: se UserProfile não tem campos de Fase 1, recai no rank() clássico.
    """
    if not results:
        return []

    has_cluster = hasattr(profile, "lifestyle_cluster") and profile.lifestyle_cluster != "NAO_CLASSIFICADO"
    if not has_cluster:
        return self.rank(results, profile)  # fallback para ranker clássico

    scored = [(r, self._compute_hyperscore(r, profile)) for r in results]
    scored.sort(key=lambda x: x[1], reverse=True)
    ranked = [r for r, _ in scored]

    # Regra de elegibilidade (preservada do ranker clássico)
    if ranked and ranked[0].eligibility_score < 0.4:
        next_eligible = next(
            (r for r in ranked[1:] if r.eligibility_score >= 0.6), None
        )
        if next_eligible:
            ranked.remove(next_eligible)
            ranked.insert(0, next_eligible)

    return ranked

def _compute_hyperscore(
    self,
    result: CardSimulationResult,
    profile: UserProfile,
) -> float:
    """Score composto pelos 4 pesos."""
    cluster = getattr(profile, "lifestyle_cluster", "NAO_CLASSIFICADO")

    # W2: impacto financeiro (normalizado — base = ganho clássico já calculado)
    w2_financial = self._compute_score(result, profile)  # usa score clássico como base

    # W1: relevância ao cluster (0.0–1.0 × 200 — escala similar ao w2 típico)
    w1_cluster = self._cluster_relevance(result, profile, cluster) * 200

    # W3: propensity heurística (Fase 1 = regras; Fase 3 = modelo ML)
    w3_propensity = self._estimate_propensity(result, profile) * 100

    # W4: timing (0.0–1.0 — baseado em life events e FSS)
    w4_timing = self._calc_timing_score(result, profile) * 50

    composite = (
        0.40 * w1_cluster
        + 0.30 * w2_financial
        + 0.20 * w3_propensity
        + 0.10 * w4_timing
    )

    return composite

def _cluster_relevance(
    self,
    result: CardSimulationResult,
    profile: UserProfile,
    cluster: str,
) -> float:
    """Quão relevante é este cartão para o cluster do usuário (0.0–1.0)."""
    relevance = 0.5  # neutro por padrão

    if cluster == "EXPLORADOR_GLOBAL":
        travel_tags = {BenefitTag.LOUNGE, BenefitTag.TRAVEL, BenefitTag.INSURANCE}
        tag_overlap = len(travel_tags & set(result.benefit_tags)) / len(travel_tags)
        relevance = 0.3 + tag_overlap * 0.7

    elif cluster == "URBANO_FOODIE":
        relevance = 0.8 if BenefitTag.CASHBACK in result.benefit_tags else 0.3

    elif cluster == "INVESTIDOR_CAUTELOSO":
        # Investidor prefere cartão sem anuidade ou com cashback direto
        if result.annual_fee == 0:
            relevance = 0.9
        elif result.annual_fee <= 300:
            relevance = 0.65
        else:
            relevance = 0.3

    elif cluster == "ESTRESSE_FINANCEIRO":
        # Para usuário em stress, só cartões sem anuidade ou com isenção são relevantes
        relevance = 0.9 if result.annual_fee == 0 else 0.2

    return relevance

def _estimate_propensity(
    self,
    result: CardSimulationResult,
    profile: UserProfile,
) -> float:
    """
    Estima probabilidade de conversão (0.0–1.0).
    Fase 1: heurística. Fase 3: modelo de propensity treinado.
    """
    propensity = 0.5

    # Alta elegibilidade → alta propensity
    propensity += (result.eligibility_score - 0.5) * 0.4

    # Confiança alta → usuário confia na recomendação
    if result.confidence_score >= 0.8:
        propensity += 0.1

    # Ganho expressivo (> R$100/mês) → motivação alta
    if result.net_gain_expected > 1200:  # R$/ano
        propensity += 0.15

    return round(min(max(propensity, 0.0), 1.0), 3)

def _calc_timing_score(
    self,
    result: CardSimulationResult,
    profile: UserProfile,
) -> float:
    """Adequação do cartão ao momento de vida atual (0.0–1.0)."""
    timing = 0.5

    fss_level = getattr(profile, "fss_level", "SAUDAVEL")
    if fss_level in ("ALERTA", "CRITICO"):
        # Mal momento para recomendar cartão novo com anuidade alta
        if result.annual_fee > 300:
            timing = 0.1
        else:
            timing = 0.6  # cartão sem anuidade em momento de stress é relevante

    return timing
```

**Ativação:** No `optimizer_service.py`, substituir `self.ranker.rank(results, profile)` por `self.ranker.rank_hyperpersonalized(results, profile)`.

**Estimativa:** 3–4 dias

---

<a name="t25"></a>
### T2.5 — Detector de Usuário Airbnb / Nômade Digital ✅

**O que implementar:** Identificar o perfil específico de usuário Airbnb (preferência por acomodação alternativa) vs. nômade digital.

**Arquivo a modificar:** `backend/app/optimizer/detectors/travel_detector.py` (adicionar método)

```python
def detect_airbnb_profile(self, df: pl.DataFrame) -> dict:
    """Detecta uso de Airbnb e sinal de nômade digital."""
    if "description" not in df.columns:
        return {"is_airbnb_user": False, "airbnb_frequency": "NUNCA", "is_digital_nomad": False}

    airbnb_df = df.filter(
        pl.col("description").str.to_uppercase().str.contains("AIRBNB")
        & (pl.col("amount") < 0)
    )

    airbnb_count = len(airbnb_df)

    if airbnb_count == 0:
        return {"is_airbnb_user": False, "airbnb_frequency": "NUNCA", "is_digital_nomad": False}

    airbnb_frequency = "OCASIONAL" if airbnb_count < 3 else "REGULAR"
    is_airbnb_user = True

    # Nômade digital: Airbnb regular + coworking
    is_digital_nomad = False
    if airbnb_frequency == "REGULAR" and "merchant_category_l2" in df.columns:
        coworking_count = df.filter(
            pl.col("merchant_category_l2") == "COWORKING"
        ).height
        is_digital_nomad = coworking_count >= 2

    return {
        "is_airbnb_user": is_airbnb_user,
        "airbnb_frequency": airbnb_frequency,
        "is_digital_nomad": is_digital_nomad,
        "airbnb_txn_count": airbnb_count,
    }
```

**Estimativa:** 0.5 dia

---

<a name="t26"></a>
### T2.6 — Personalização de Insights por Cluster ✅

**O que implementar:** Adaptar o texto dos 7 tipos de insights existentes para incorporar linguagem personalizada pelo cluster do usuário.

**Arquivo a modificar:** `backend/app/optimizer/insight_generator.py`

Criar dicionário de templates de linguagem por cluster:

```python
# insight_generator.py — adicionar

_CLUSTER_TONE: dict[str, dict] = {
    "EXPLORADOR_GLOBAL": {
        "prefix": "Para quem viaja como você",
        "emphasis": "milhas e lounge",
        "currency_framing": "passagem grátis",
    },
    "URBANO_FOODIE": {
        "prefix": "Com seu gasto em alimentação",
        "emphasis": "cashback e benefícios em restaurantes",
        "currency_framing": "refeição grátis",
    },
    "INVESTIDOR_CAUTELOSO": {
        "prefix": "Calculando o custo de oportunidade",
        "emphasis": "retorno líquido sobre anuidade",
        "currency_framing": "rendimento no investimento",
    },
    "FAMILIA_ESTRUTURADA": {
        "prefix": "Para sua família",
        "emphasis": "cashback em supermercado e farmácia",
        "currency_framing": "mês de compras grátis",
    },
}

def _personalize_description(
    self,
    base_description: str,
    profile: UserProfile,
    gain_annual: float,
) -> str:
    """Enriquece o texto do insight com contexto do cluster."""
    cluster = getattr(profile, "lifestyle_cluster", "NAO_CLASSIFICADO")
    tone = _CLUSTER_TONE.get(cluster)
    if not tone:
        return base_description

    return (
        f"{tone['prefix']}, {base_description.lower()} "
        f"Foco em {tone['emphasis']} — equivale a R${gain_annual:.0f}/ano."
    )
```

**Estimativa:** 1–2 dias

---

<a name="t27"></a>
### T2.7 — Inteligência Temporal (peak_spend_day, notification timing) ✅

**O que implementar:** Calcular padrões temporais de gasto para personalizar o timing de notificações e recomendações.

**Nota sobre `hour_of_day`:** O campo `hour_of_day` existe em `divider/classifier.py` (pipeline de divisão de uso PF/PJ), mas **não chega ao optimizer** via `transactions_clean`. Para Fase 1, o `TemporalDetector` usa apenas `date` (dia do mês, dia da semana). A análise por hora do dia fica como melhoria futura quando o campo for propagado até o profiler.

**Arquivo a criar:** `backend/app/optimizer/detectors/temporal_detector.py`

```python
# app/optimizer/detectors/temporal_detector.py

from __future__ import annotations
import polars as pl


class TemporalDetector:
    """
    Extrai padrões temporais de gasto para personalizar timing de notificações.

    Nota: usa apenas `date` (sem `hour_of_day`) pois o campo de hora não
    está disponível no transactions_clean que chega ao optimizer.
    """

    def analyze(self, df: pl.DataFrame) -> dict:
        if df.is_empty():
            return {
                "peak_spend_day_of_month": None,
                "peak_spend_day_of_week": None,
                "is_weekend_spender": False,
                "spending_pattern": "IRREGULAR",
                "best_notification_day": 5,
            }

        expenses = df.filter(pl.col("amount") < 0)
        if expenses.is_empty():
            return self.analyze(df.head(0))

        # Dia do mês com maior concentração de gastos
        by_day = (
            expenses
            .with_columns(pl.col("date").dt.day().alias("dom"))
            .group_by("dom")
            .agg(pl.col("amount").sum().abs().alias("total"))
            .sort("total", descending=True)
        )
        peak_day = int(by_day[0]["dom"][0]) if len(by_day) > 0 else 1

        # Dia da semana com maior gasto
        by_weekday = (
            expenses
            .with_columns(pl.col("date").dt.weekday().alias("dow"))
            .group_by("dow")
            .agg(pl.col("amount").sum().abs().alias("total"))
            .sort("total", descending=True)
        )
        peak_weekday = int(by_weekday[0]["dow"][0]) if len(by_weekday) > 0 else 0

        # Percentual de gasto no fim de semana
        total_spend = float(expenses["amount"].sum()) * -1
        weekend_spend = float(
            expenses.filter(pl.col("date").dt.weekday() >= 5)["amount"].sum()
        ) * -1
        is_weekend_spender = (weekend_spend / total_spend) > 0.45 if total_spend > 0 else False

        # Padrão de gasto
        monthly_totals = (
            expenses
            .with_columns(
                (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
            )
            .group_by("ym")
            .agg(pl.col("amount").sum().abs())
        )
        if len(monthly_totals) >= 2:
            mean = float(monthly_totals["amount"].mean())
            std = float(monthly_totals["amount"].std())
            cv = std / mean if mean > 0 else 1.0
            spending_pattern = "REGULAR" if cv < 0.15 else "MODERADO" if cv < 0.35 else "IRREGULAR"
        else:
            spending_pattern = "SEM_DADOS"

        # Melhor dia para enviar notificação = 3 dias antes do pico de gastos
        best_notification_day = max(1, peak_day - 3)

        return {
            "peak_spend_day_of_month": peak_day,
            "peak_spend_day_of_week": peak_weekday,
            "is_weekend_spender": is_weekend_spender,
            "spending_pattern": spending_pattern,
            "best_notification_day": best_notification_day,
        }
```

**Estimativa:** 1 dia

---

<a name="fase-3"></a>
## FASE 3 — ML Pipeline (6–12 meses)

**Meta:** Substituir heurísticas de clustering e propensity por modelos ML treinados. Adicionar predição de gastos futuros (Prophet) e detecção de churn.

**Pré-requisito:** Fase 2 completa + tabela `user_features` no banco com pelo menos 3 meses de histórico acumulado.

---

<a name="t31"></a>
### T3.1 — Classificador de Merchant (NLP + MCC)

**O que implementar:** Modelo de NLP para categorizar merchants não mapeados com base no nome normalizado, complementando as regras de Fase 1.

**Arquivo a criar:** `backend/app/ml/merchant_classifier.py`

**Stack:** `sentence-transformers` com fine-tuning em dados de MCC brasileiros. Serving via `joblib` pickle carregado no startup da API.

```python
# app/ml/merchant_classifier.py

from __future__ import annotations
import joblib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_MODEL_PATH = Path("backend/models/merchant_classifier.pkl")


class MerchantClassifier:
    """
    Classifica merchants em categoria L1/L2 por nome normalizado.

    Fase 1 (T1.1): regras determinísticas (keyword matching).
    Fase 3 (T3.1): modelo ML substituindo/complementando as regras.

    Interface compatível com TransactionFeatureEnricher — retorna o mesmo
    schema de merchant_category_l2.
    """

    def __init__(self):
        self._model = None
        self._load_model()

    def _load_model(self):
        if _MODEL_PATH.exists():
            try:
                self._model = joblib.load(_MODEL_PATH)
                logger.info("MerchantClassifier: modelo carregado de %s", _MODEL_PATH)
            except Exception as e:
                logger.warning("MerchantClassifier: falha ao carregar modelo — fallback para regras: %s", e)
        else:
            logger.info("MerchantClassifier: modelo não encontrado — usando apenas regras")

    def predict_l2(self, merchant_name: str) -> str | None:
        """Classifica merchant em categoria L2. Retorna None se confiança < 0.70."""
        if self._model is None:
            return None
        try:
            pred, confidence = self._model.predict_with_confidence([merchant_name])
            return pred[0] if confidence[0] >= 0.70 else None
        except Exception:
            return None
```

**Dados de treino necessários:**
- Exportar todas as transações da base com `merchant_name` e `category` já classificada (labels)
- Fine-tune de `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` em português
- Mínimo 10k exemplos rotulados por categoria L2

**Métricas de aceitação:**
- Accuracy L2 ≥ 85% no hold-out
- Cobertura ≥ 95% das transações com L2 atribuída (manual + ML)
- Latência de predição < 10ms por merchant (serving via pickle)

**Estimativa:** 3–4 semanas (incluindo coleta de dados e fine-tuning)

---

<a name="t32"></a>
### T3.2 — Predição de Gastos Futuros (Prophet) ✅

> **Implementado em:** `backend/app/ml/spend_predictor.py`
> **Diferenças da spec:** Interface aprimorada com `SpendPrediction` (dataclass frozen com `confidence_interval` property), método `predict_by_category()` para todas as categorias de uma vez, e campo `months_of_data` no resultado. Prophet importado de forma lazy (não quebra se não instalado). Testes: `tests/optimizer/test_spend_predictor.py` (31 testes).

**O que implementar:** Modelo Prophet para prever gastos dos próximos 30 dias por categoria, habilitando "safe-to-spend" preciso e alertas antecipados.

**Arquivo a criar:** `backend/app/ml/spend_predictor.py`

```python
# app/ml/spend_predictor.py

from __future__ import annotations
import logging
from datetime import date, timedelta

import polars as pl

logger = logging.getLogger(__name__)


class SpendPredictor:
    """
    Prediz gastos futuros por categoria usando Prophet.

    Requisito: usuário com ≥ 6 meses de histórico.
    Fallback (< 6 meses): média móvel dos últimos 3 meses.
    """

    _MIN_MONTHS_FOR_PROPHET = 6

    def predict_next_30d(
        self,
        transactions_df: pl.DataFrame,
        category: str | None = None,
    ) -> dict:
        """
        Retorna previsão de gasto para os próximos 30 dias.

        Returns:
            {
                "predicted_spend": float,
                "confidence_interval": (float, float),  # P10–P90
                "method": "prophet" | "moving_average",
                "category": str | "total",
            }
        """
        if transactions_df.is_empty():
            return self._fallback_prediction(0.0, category)

        # Filtrar por categoria se especificada
        df = transactions_df.filter(pl.col("amount") < 0)
        if category:
            df = df.filter(pl.col("category") == category)

        # Contar meses de histórico
        months_available = df.with_columns(
            (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
        ).select("ym").unique().height

        if months_available < self._MIN_MONTHS_FOR_PROPHET:
            monthly_avg = float(df["amount"].sum()) * -1 / max(months_available, 1)
            return self._fallback_prediction(monthly_avg, category)

        try:
            return self._prophet_predict(df, category)
        except ImportError:
            logger.warning("Prophet não instalado — usando média móvel")
            monthly_avg = float(df["amount"].sum()) * -1 / months_available
            return self._fallback_prediction(monthly_avg, category)

    def _prophet_predict(self, df: pl.DataFrame, category: str | None) -> dict:
        from prophet import Prophet  # import lazy — não quebra se não instalado

        # Preparar série temporal diária
        daily = (
            df.with_columns(pl.col("date").alias("ds"))
            .group_by("ds")
            .agg(pl.col("amount").sum().abs().alias("y"))
            .sort("ds")
        )

        pdf = daily.to_pandas()
        pdf["ds"] = pd.to_datetime(pdf["ds"])

        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            interval_width=0.80,
        )
        model.fit(pdf)

        future = model.make_future_dataframe(periods=30)
        forecast = model.predict(future)

        next_30d = forecast.tail(30)
        predicted = float(next_30d["yhat"].sum())
        lower = float(next_30d["yhat_lower"].sum())
        upper = float(next_30d["yhat_upper"].sum())

        return {
            "predicted_spend": round(max(predicted, 0), 2),
            "confidence_interval": (round(max(lower, 0), 2), round(upper, 2)),
            "method": "prophet",
            "category": category or "total",
        }

    def _fallback_prediction(self, monthly_avg: float, category: str | None) -> dict:
        predicted = monthly_avg * (30 / 30)  # para 30 dias
        return {
            "predicted_spend": round(predicted, 2),
            "confidence_interval": (round(predicted * 0.80, 2), round(predicted * 1.20, 2)),
            "method": "moving_average",
            "category": category or "total",
        }
```

**Dependência a adicionar** em `pyproject.toml`:
```toml
prophet = "^1.1.5"
```

**Estimativa:** 2–3 semanas (incluindo validação de acurácia)

---

<a name="t33"></a>
### T3.3 — Propensity to Churn

**O que implementar:** Modelo Gradient Boosting que prediz, com 30 dias de antecedência, quais usuários têm alta probabilidade de cancelar.

**Arquivo a criar:** `backend/app/ml/churn_predictor.py`

**Features de entrada:**
- Recência: dias desde última sessão / última transação sincronizada
- FSS (T2.2): estresse financeiro atual
- Engajamento: número de acessos nos últimos 30 dias (dado de produto)
- Valor percebido: número de insights gerados e aceitos no último trimestre
- Tempo de vida: meses como usuário ativo

**Output:** `churn_probability` (0.0–1.0) e `churn_risk_level` (LOW/MEDIUM/HIGH/CRITICAL)

**Ação:** Se `churn_probability > 0.70`, ativar campanha de retenção automaticamente e logar para a equipe de Customer Success.

**Dados de treino necessários:**
- Histórico de usuários cancelados (label=1) e ativos (label=0)
- Mínimo de 500 churners para treino confiável

**Métricas de aceitação:**
- AUC-ROC ≥ 0.80
- Precision@TOP10% ≥ 0.65 (dos 10% mais propensos, 65% realmente churnam em 30 dias)

**Estimativa:** 4–6 semanas (incluindo pipeline de dados e validação)

---

<a name="t34"></a>
### T3.4 — Collaborative Filtering para Recomendação

**O que implementar:** "Usuários similares ao seu perfil contrataram X e economizaram R$Y" — recomendação social prova de que o produto funciona.

**Abordagem:** Matrix factorization (ALS ou SVD) sobre matriz `usuário × cartão_contratado` com pesos pelo ganho realizado.

**Arquivo a criar:** `backend/app/ml/collaborative_recommender.py`

**Integração com o Optimizer:**

Adicionar ao `OptimizationReport`:
```json
{
  "social_proof": {
    "similar_users_count": 127,
    "top_card_among_similar": "latam-pass-itaucard-platinum",
    "avg_gain_similar_users": 1840.0,
    "top_card_adoption_rate": 0.34
  }
}
```

**Estimativa:** 3–4 semanas

---

<a name="t35"></a>
### T3.5 — A/B Testing Framework ✅

> **Implementado em:** `backend/app/core/ab_testing.py`
> **Diferenças da spec:** `get_variant()` recebe `experiment_name` e consulta o registry `EXPERIMENTS` (dict de `Experiment` dataclasses), lançando `ValueError` para experimentos não registrados. Adicionado `log_exposure()` para rastreamento. Os 3 experimentos iniciais (`ranker_v2_hyperpersonalized`, `cluster_tone_personalization`, `life_events_nudge`) já estão cabeados no `optimizer_service.py` e `insight_generator.py`. Testes: `tests/optimizer/test_ab_testing.py` (31 testes, incluindo integração).

**O que implementar:** Infraestrutura para testar variantes de recomendação e medir impacto real.

**Arquivo a criar:** `backend/app/core/ab_testing.py`

```python
# app/core/ab_testing.py

import hashlib
from enum import Enum


class ABVariant(str, Enum):
    CONTROL = "control"
    TREATMENT = "treatment"


def get_variant(user_id: str, experiment_name: str, traffic_pct: float = 0.50) -> ABVariant:
    """
    Determina a variante de um experimento para um usuário.
    Determinístico: mesmo user_id + experiment_name → sempre a mesma variante.
    """
    hash_input = f"{user_id}:{experiment_name}"
    hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
    normalized = (hash_value % 10000) / 10000.0
    return ABVariant.TREATMENT if normalized < traffic_pct else ABVariant.CONTROL
```

**Experimentos iniciais a rodar:**
1. `ranker_v2_hyperpersonalized`: ranker clássico vs. ranker com 4 pesos (T2.4)
2. `cluster_tone_personalization`: texto genérico vs. texto por cluster (T2.6)
3. `life_events_nudge`: sem life events vs. com nudge baseado em evento detectado (T2.1)

**Métricas a coletar por experimento:**
- CTR do insight (usuário clicou no insight?)
- Conversion rate (usuário solicitou o cartão após ver o insight?)
- 7-day retention (usuário voltou em 7 dias?)

**Estimativa:** 1 semana

---

<a name="prereqs"></a>
## Pré-requisitos Transversais

### Banco de Dados

Criar tabela `user_intelligence_profile` para persistir os campos calculados entre sessões:

```sql
CREATE TABLE user_intelligence_profile (
    user_id          UUID PRIMARY KEY REFERENCES users(id),
    lifestyle_cluster          VARCHAR(50),
    travel_frequency_score     FLOAT,
    foodie_score               FLOAT,
    savings_rate               FLOAT,
    investor_type              VARCHAR(20),
    is_likely_mei              BOOLEAN,
    fss                        FLOAT,
    fss_level                  VARCHAR(20),
    merchant_diversity_score   FLOAT,
    subscription_burn_monthly  FLOAT,
    peak_spend_day_of_month    INT,
    spending_pattern           VARCHAR(20),
    life_events_json           JSONB,        -- lista de LifeEvent detectados
    cluster_scores_json        JSONB,        -- dict de afinidade por cluster
    last_calculated_at         TIMESTAMPTZ DEFAULT NOW(),
    data_coverage_months       INT,
    created_at                 TIMESTAMPTZ DEFAULT NOW(),
    updated_at                 TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_uip_cluster ON user_intelligence_profile(lifestyle_cluster);
CREATE INDEX idx_uip_fss_level ON user_intelligence_profile(fss_level);
CREATE INDEX idx_uip_updated ON user_intelligence_profile(last_calculated_at);
```

**Arquivo a criar:** `backend/app/optimizer/queries.py` (adicionar função `upsert_user_intelligence_profile`)

### Estrutura de Pastas

```
backend/app/optimizer/
├── detectors/
│   ├── __init__.py
│   ├── travel_detector.py        # T1.2
│   ├── foodie_detector.py        # T1.3
│   ├── investor_detector.py      # T1.4
│   ├── mei_detector.py           # T1.5
│   ├── family_detector.py        # T2.3
│   ├── life_events_detector.py   # T2.1
│   ├── fss_calculator.py         # T2.2
│   ├── temporal_detector.py      # T2.7
│   └── lifestyle_classifier.py   # T1.7
├── feature_store.py              # T1.1
└── ... (arquivos existentes)

backend/app/ml/
├── __init__.py
├── merchant_classifier.py        # T3.1
├── spend_predictor.py            # T3.2
├── churn_predictor.py            # T3.3
└── collaborative_recommender.py  # T3.4

backend/models/                   # modelos ML treinados (*.pkl)
```

### Dependências a Adicionar

```toml
# pyproject.toml

# Fase 1 (sem ML — puro Python/Polars):
# sem dependências novas — Polars já é dependência atual

# Fase 3:
prophet = "^1.1.5"
scikit-learn = "^1.4.0"
lightgbm = "^4.3.0"
sentence-transformers = "^2.7.0"
joblib = "^1.4.0"
```

### Compatibilidade com Pipeline Atual

**Nenhuma interface pública muda na Fase 1.** O `UserProfile` é um dataclass com campos opcionais. O `ConsumptionProfiler.build()` continua retornando `UserProfile` — apenas com mais campos. Todos os campos novos têm `default` definido, então código existente que constrói `UserProfile` manualmente continua funcionando.

**Testes de não-regressão obrigatórios antes de cada merge:**
```bash
cd backend && python -m pytest tests/test_optimizer/ -v
cd backend && streamlit run streamlit_f2_f3_test.py --server.headless true
```

---

<a name="metricas"></a>
## Métricas de Sucesso por Fase

### Fase 1 (0–3 meses)

| Métrica | Meta | Como medir |
|---|---|---|
| Cobertura de merchant com L2 | ≥ 85% das transações | `transactions.merchant_category_l2.notnull().mean()` |
| Usuários classificados em cluster | ≥ 70% (não-UNCLASSIFIED) | `user_intelligence_profile.lifestyle_cluster != 'NAO_CLASSIFICADO'` |
| travel_score precision | ≥ 80% concordância em survey | Survey in-app amostra 100 usuários |
| Latência do profiler após Fase 1 | < 200ms (P95) | APM no endpoint `/optimize` |
| Nenhuma regressão nos testes existentes | 100% pass | CI/CD automatizado |

### Fase 2 (3–6 meses)

| Métrica | Meta | Como medir |
|---|---|---|
| Life events detectados corretamente | ≥ 70% confirmação usuário | Push notification "detectamos X — está correto?" |
| FSS correlação com inadimplência | ≥ 0.65 Pearson | Retrospectivo 90 dias |
| CTR de insight cluster-personalizado vs. genérico | +20% (A/B test T3.5) | Analytics de produto |
| Conversão de recomendação de produto | ≥ 15% | Funil: insight → solicitação cartão |

### Fase 3 (6–12 meses)

| Métrica | Meta | Como medir |
|---|---|---|
| AUC-ROC do churn predictor | ≥ 0.80 | Hold-out 20% dos dados |
| Cobertura de merchant com L2 via ML | ≥ 95% | Post-model evaluation |
| Retenção de usuários com nudge de churn | +30% vs. controle | A/B test |
| Acurácia Prophet next-30d | MAE ≤ 15% do gasto real | Backtesting últimos 6 meses |

---

## Sumário de Esforço por Fase

| Fase | Duração | Tarefas | Dev estimado |
|---|---|---|---|
| Fase 1 | 0–3 meses | T1.1–T1.8 | ~15 dias dev |
| Fase 2 | 3–6 meses | T2.1–T2.7 | ~20 dias dev |
| Fase 3 | 6–12 meses | T3.1–T3.5 | ~40 dias dev (inclui ML) |
| **Total** | **12 meses** | **20 tarefas** | **~75 dias dev** |

---

## Ganho de Inteligência Estimado

| Capacidade atual | Após Fase 1 | Após Fase 2 | Após Fase 3 |
|---|---|---|---|
| Detecção de perfil de viagem | Gasto em "Lazer+Transporte" | Score 0–100 + 5 MCCs | Prophet de sazonalidade de viagem |
| Personalização de recomendação | Net gain + anuidade | Cluster + timing + life events | Collaborative filtering social |
| Detecção de estresse | `committed_percentage` (parcial) | FSS com 5 componentes | Predição 30d de risco |
| Segmentação de usuário | Nenhuma | 7 clusters com afinidade | HDBSCAN com N clusters dinâmicos |
| Cobertura de merchant | ~60% (L1 keyword) | ~85% (L2 regras) | ~95% (L2 ML) |

---

---

## Integrações de Perfil nas Funcionalidades do Produto (Abril 2026)

> **Contexto:** Auditoria identificou que `ConsumptionProfiler` produzia um perfil comportamental rico (lifestyle_cluster, FSS, life_events, investor_type, etc.) mas as funcionalidades do produto (Agent, Budget, Metas) eram completamente agnósticas a ele. Esta seção documenta as 4 integrações realizadas para fechar esse gap.

---

### I1 — Agent System Prompt: REGRA ZERO + Personalização por Cluster

**Arquivo:** `backend/app/agent/graph.py`

**Problema:** O agente LangChain iniciava toda sessão sem contexto comportamental do usuário, gerando respostas genéricas independente do cluster.

**Solução:**
- Criada nova tool `get_user_profile_context` (ver I2) e adicionada como ferramenta #0 na lista do agente.
- Adicionada **REGRA ZERO** ao `SYSTEM_PROMPT`: na primeira mensagem de qualquer sessão, chamar `get_user_profile_context` antes de qualquer outra ferramenta.
- Adicionada seção **COMO USAR O PERFIL** com regras por cluster:

| Cluster | Regra de comportamento do agente |
|---|---|
| `EXPLORADOR_GLOBAL` | Destaque milhas, lounge, benefícios internacionais |
| `FAMILIA_ESTRUTURADA` | Foco em segurança, educação dos filhos, seguro de vida |
| `MICROEMPREENDEDOR` | Sempre distinguir fluxo PJ de PF |
| `INVESTIDOR_CAUTELOSO` | Tom técnico, retornos, indexadores |
| `ESTRESSE_FINANCEIRO` | Empático, não sugerir produtos com custo adicional |
| FSS `CRITICO`/`ALERTA` | Priorizar dívidas antes de qualquer nova meta |
| Life event `new_baby` | Sugerir meta de educação e cobertura de seguro |
| Life event `income_drop` | Revisão de orçamento urgente |

---

### I2 — Nova Tool: `get_user_profile_context`

**Arquivo:** `backend/app/agent/tools/get_user_profile_context.py` *(novo)*

**Responsabilidade:** Retorna o perfil comportamental completo do usuário em texto LLM-consumível, com cache em memória de 30 minutos para evitar re-execução dos 12 detectores a cada mensagem.

**Output inclui:**
- Cluster de estilo de vida com "tom" associado (ex: "Viajante global, experiências e aventura")
- FSS com emoji e nível (`SAUDAVEL` ✅ / `ATENCAO` ⚠️ / `ALERTA` 🔴 / `CRITICO` 🆘)
- Sinais comportamentais: `is_likely_mei`, `is_family_with_kids`, `investor_type`, `travel_frequency_score`, `foodie_score`
- `savings_rate`, `subscription_burn`, `peak_spend_day_of_month`, `best_notification_day`

```python
@tool
def get_user_profile_context(user_id: str) -> str:
    """Retorna o perfil comportamental completo do usuário para personalização do agente."""
    cached = _get_cached(user_id)
    if cached:
        return cached
    transactions_df = get_transactions_for_user(user_id)
    profile = ConsumptionProfiler().build(transactions_df)
    text = _format_profile(user_id, profile)
    _set_cached(user_id, text)
    return text
```

---

### I3 — `get_financial_forecast`: Correção + ConsumptionProfiler + LifeEventsDetector

**Arquivo:** `backend/app/agent/tools/get_financial_forecast.py`

**Problema 1 (bug):** `result.get("user_profile")` sempre retornava `None` porque `run_from_db()` não inclui essa chave no dict de retorno. O bloco de health score nunca executava.

**Correção:** Extrair `transactions_df` do `result["transactions"]["pf_pj_classified_df"]` (já em memória, sem I/O extra) e chamar `UserProfileAnalyzer().analyze()` diretamente.

**Problema 2 (gap):** A tool não expunha cluster comportamental, FSS nem eventos de vida — deixando o agente sem contexto para personalizar respostas sobre saúde financeira.

**Adições:**
- `ConsumptionProfiler().build(transactions_df)` → cluster, FSS (com emoji), savings_rate no output
- `LifeEventsDetector().detect_all(txns_recent, txns_history, ...)` com splits de 60 dias (recente) e 6 meses (histórico) → eventos com confiança e trigger_action

Ambas as chamadas falham silenciosamente com `logger.debug` se indisponíveis.

**Seções novas no output:**
```
🧠 **Perfil Comportamental:**
   • Cluster: EXPLORADOR_GLOBAL
   • Estresse Financeiro: ✅ SAUDAVEL (FSS 82/100)
   • Taxa de poupança: 18.3%

🔔 **Eventos de Vida Detectados:**
   • new_education (confiança 78%) → Sugerir meta de educação
```

---

### I4 — Budget M1.3: Metas 50/30/20 Cluster-Aware

**Arquivos:** `backend/app/budget/budget_advisor.py` + `backend/app/budget/router.py`

**Problema:** `BudgetAdvisor` sugeria sempre 50/30/20 independente do comportamento real do usuário.

**Solução:**

Adicionado `_CLUSTER_TARGETS` em `budget_advisor.py`:

| Cluster | Regra | Nota |
|---|---|---|
| `EXPLORADOR_GLOBAL` | 47/35/18 | Viajante: mais margem em desejos |
| `INVESTIDOR_CAUTELOSO` | 50/20/30 | Investidor: poupança elevada para 30% |
| `ESTRESSE_FINANCEIRO` | 55/15/30 | Foco em estabilidade + redução de dívidas |
| `FAMILIA_ESTRUTURADA` | 55/25/20 | Família: essenciais maiores, desejos contidos |
| `MICROEMPREENDEDOR` | 50/30/20 | Padrão, mas com nota sobre fluxo PJ |
| outros | 50/30/20 | Regra padrão |

`BudgetSuggestion` ganhou campos `lifestyle_cluster` e `cluster_note` (retornados em `to_dict()`).

Em `router.py`, foi adicionado um Step 2 que chama `ConsumptionProfiler` **antes** do rename de coluna (`date` → `transaction_date`) e passa `lifestyle_cluster` para `advisor.suggest()`.

---

### I5 — Metas MX.2: `GoalProfileAdvisor` + Wiring no Router

**Arquivos:** `backend/app/goals/profile_advisor.py` *(novo)* + `backend/app/goals/router.py`

**Problema:** O sistema de metas era completamente agnóstico ao perfil: não sugeria metas por cluster, não detectava incompatibilidade entre meta e FSS atual, não calculava viabilidade de ritmo de poupança.

**Solução — `GoalProfileAdvisor`:**

```python
@dataclass
class GoalProfileContext:
    profile_alerts: list[str]       # avisos por FSS / cluster
    suggested_goals: list[dict]     # sugestões de novos tipos de meta
    goal_warnings: dict[str, str]   # aviso por goal_id (inviabilidade)
```

**`_add_fss_alerts()`:** gera alertas textuais para CRITICO / ALERTA / ATENCAO com emoji.

**`_add_cluster_suggestions()`:** sugere automaticamente:
- Reserva de emergência quando FSS não é SAUDAVEL ou usuário é investidor ativo
- `EXPLORADOR_GLOBAL` → Fundo de Viagens (R$8.000)
- `FAMILIA_ESTRUTURADA` → Fundo de Educação (R$30.000)
- `MICROEMPREENDEDOR` → Capital de Giro PJ (3× gasto médio)
- `INVESTIDOR_CAUTELOSO` sem meta de longo prazo → Previdência/Aposentadoria (R$500.000)

**`_add_goal_warnings()`:** por meta ativa:
- FSS CRITICO + meta não-emergência → alerta para pausar
- `needed > savings × 1.5` → alerta de inviabilidade de ritmo
- Sem poupança detectada + prazo definido → alerta de contribuição necessária

**Router (`list_goals_public`):** adicionado bloco pós-lista de metas:
```python
transactions_df = get_transactions_for_user(user_id)
user_profile    = ConsumptionProfiler().build(transactions_df)
active_goals    = [g for g in goals if g.status == "ACTIVE"]
profile_context = GoalProfileAdvisor().analyze(user_profile, active_goals).to_dict()
# → retornado em "profile_context" no response dict
```

**Response de `GET /goals/{user_id}` passou a incluir:**
```json
{
  "goals": [...],
  "profile_context": {
    "lifestyle_cluster": "FAMILIA_ESTRUTURADA",
    "fss_level": "ATENCAO",
    "fss_score": 62.0,
    "investor_type": "CONSERVADOR",
    "savings_rate": 11.5,
    "profile_alerts": ["⚠️ FSS em Atenção (62/100): ..."],
    "suggested_goals": [{"goal_type": "educacao", "name": "Fundo de Educação", ...}],
    "goal_warnings": {"abc-123": "⚠️ Esta meta exige R$ 1.200/mês..."}
  }
}
```

Toda a lógica do `GoalProfileAdvisor` falha silenciosamente com `logger.debug` se `ConsumptionProfiler` estiver indisponível, mantendo a resposta de metas funcionando normalmente.

---

*Nexa AI — Documento de Implementação v1.0 — Abril 2026*
*Baseado em: `docs/melhorias_analise_perfil.md` + auditoria do optimizer*
