# 📚 DOCUMENTAÇÃO COMPLETA - MÓDULO ETL

## 🎯 OBJETIVO DESTE DOCUMENTO

Este é o **ÍNDICE MESTRE** com a documentação de **TODOS OS 14 ARQUIVOS** do módulo ETL.

Cada arquivo tem explicação detalhada de:
- ✅ **O QUE FAZ**
- ✅ **COMO INTERAGE COM O RESTO**
- ✅ **POR QUE É IMPORTANTE**
- ✅ **FLUXO DE DADOS**
- ✅ **EXEMPLOS DE USO**

---

## 📁 ESTRUTURA COMPLETA (14 Arquivos)

```
etl/
├── 1. __init__.py                    ← Entry point (API pública)
├── 2. ingestor.py                    ← Limpa JSON → DataFrame
├── 3. classifier.py                  ← Categoriza (CatBoost ML)
├── 4. recurring_detector.py          ← Detecta assinaturas
├── 5. data_quality.py                ← Calcula confidence scores
│
└── bank_strategy/
    ├── 6.  __init__.py               ← API pública (get_bank_strategy)
    ├── 7.  base.py                   ← Interface BankStrategy (ABC)
    ├── 8.  profiles.py               ← BankProfile (dataclass config)
    ├── 9.  registry.py               ← Singleton (mapeia banco→strategy)
    │
    ├── config/
    │   └── 10. bank_profiles.yaml    ← Configurações por banco
    │
    └── strategies/
        ├── 11. __init__.py           ← Exports de strategies
        ├── 12. default.py            ← Fallback genérico
        ├── 13. nubank.py             ← Strategy TIER_1 (rigoroso)
        ├── 14. itau.py               ← Strategy TIER_3 (tolerante)
        └── 15. inter.py              ← Strategy TIER_2 (formato US)
```

---

## 📖 DOCUMENTAÇÃO POR ARQUIVO

### ═══════════════════════════════════════════════════════════════
### 📂 MÓDULO PRINCIPAL: etl/
### ═══════════════════════════════════════════════════════════════

---

### 1. `etl/__init__.py`

**FUNÇÃO:** Entry point do módulo ETL, exporta API pública

**O QUE FAZ:**
- Torna `etl/` um módulo Python importável
- Exporta classes principais (TransactionIngestor, TransactionClassifier)
- Centraliza imports (outros módulos importam de `app.etl`)

**INTERAGE COM:**
- **ENTRADA:** Ninguém (é entry point)
- **SAÍDAS:** api/routes/, workers/
- **EXPORTA:**
  - TransactionIngestor
  - TransactionClassifier
  - RecurringDetector
  - DataQualityValidator

**POR QUE É IMPORTANTE:**
- Encapsulamento (esconde detalhes de implementação)
- Descobribilidade (IDE autocomplete)
- Versionamento (deprecar APIs antigas)

**EXEMPLO DE USO:**
```python
from app.etl import TransactionIngestor, TransactionClassifier

ingestor = TransactionIngestor()
classifier = TransactionClassifier()

clean_df = ingestor.process(raw_transactions)
categorized_df = classifier.predict(clean_df)
```

---

### 2. `etl/ingestor.py`

**FUNÇÃO:** Transforma JSON → DataFrame limpo (Polars)

**O QUE FAZ:**
- Converte TransactionWebhook (Pydantic) → pl.DataFrame
- Deduplica (dedup_hash)
- Normaliza textos (lowercase, remove acentos)
- Converte tipos (Decimal → Float64)
- Enriquece (month, day_of_week, transaction_type)
- Calcula métricas de qualidade

**INTERAGE COM:**
- **ENTRADA:** api/routes/transactions.py (TransactionBatchResult)
- **USA:** Polars (DataFrame engine)
- **SAÍDAS:** 
  - pl.DataFrame (transactions_clean)
  - QualityMetrics (métricas de qualidade)
- **DESTINO:** db/models.py (INSERT INTO transactions_clean)

**POR QUE É IMPORTANTE:**
- Remove ruído antes de análise
- Garante tipos corretos (evita bugs)
- Performance (Polars 10-100x mais rápido que pandas)
- Consistência (mesma limpeza para todos os bancos)

**PIPELINE (6 Passos):**
```
1. JSON → DataFrame
   ↓
2. Deduplica (dedup_hash)
   ↓
3. Normaliza textos
   ↓
4. Converte tipos
   ↓
5. Enriquece colunas
   ↓
6. Calcula métricas
```

**EXEMPLO DE USO:**
```python
ingestor = TransactionIngestor()
clean_df, metrics = ingestor.process(valid_transactions)

# clean_df: pl.DataFrame limpo
# metrics: QualityMetrics (total_records, duplicates_removed, quality_score)
```

---

### 3. `etl/classifier.py`

**FUNÇÃO:** Classifica transações (CatBoost ML)

**O QUE FAZ:**
- Carrega modelo CatBoost (ml/models/category_classifier.cbm)
- Extrai features (merchant, description, amount)
- Predição ML → categoria (ex: "Transporte")
- Prioriza: banco > ml > heurísticas
- Retorna categoria + confidence

**INTERAGE COM:**
- **ENTRADA:** etl/ingestor.py (DataFrame limpo)
- **USA:** 
  - CatBoost (ML model)
  - Regras heurísticas (fallback)
- **SAÍDAS:**
  - DataFrame com predicted_category
  - ml_confidence (0.0 - 1.0)
  - category_source ("bank" | "ml" | "heuristic")

**POR QUE É IMPORTANTE:**
- UX (usuário não categoriza manualmente)
- Análise financeira (gastos por categoria)
- Inteligência progressiva (aprende com o tempo)

**3 NÍVEIS DE PRIORIDADE:**
```
1. PRIORIDADE 1: Categoria do banco (se confiável)
   ↓
2. PRIORIDADE 2: CatBoost ML (se confidence > 0.6)
   ↓
3. PRIORIDADE 3: Heurísticas (fallback sempre funciona)
```

**EXEMPLO DE USO:**
```python
classifier = TransactionClassifier()
categorized_df = classifier.predict(clean_df)

# Output:
# ┌──────────────┬───────────────┬──────────────┬─────────────────┐
# │ description  │ final_category│ ml_confidence│ category_source │
# ├──────────────┼───────────────┼──────────────┼─────────────────┤
# │ uber viagem  │ Transporte    │ 0.92         │ ml              │
# │ netflix      │ Assinaturas   │ 0.88         │ ml              │
# └──────────────┴───────────────┴──────────────┴─────────────────┘
```

---

### 4. `etl/recurring_detector.py`

**FUNÇÃO:** Detecta assinaturas e parcelamentos

**O QUE FAZ:**
- Analisa padrões temporais (recorrências mensais)
- Detecta valores similares + mesmo merchant
- Identifica parcelamentos (via regex ou sequência)
- Marca transações: is_recurring, is_installment

**INTERAGE COM:**
- **ENTRADA:** etl/ingestor.py (DataFrame limpo)
- **USA:** Polars (window functions, group_by)
- **SAÍDAS:**
  - DataFrame com:
    - is_recurring: bool
    - is_installment: bool
    - installment_info: str ("3/12")

**POR QUE É IMPORTANTE:**
- Previsibilidade (gastos recorrentes são estáveis)
- Safe-to-Spend (considera assinaturas futuras)
- Shadow Invoice (projeta recorrências)
- UX (usuário vê assinaturas agrupadas)

**EXEMPLO DE USO:**
```python
detector = RecurringDetector()
enriched_df = detector.detect(clean_df)

# Output:
# ┌──────────┬────────────┬───────────────┬─────────────────┐
# │ merchant │ is_recurring│ is_installment│ installment_info│
# ├──────────┼────────────┼───────────────┼─────────────────┤
# │ Netflix  │ True       │ False         │ None            │
# │ iPhone   │ False      │ True          │ 3/12            │
# └──────────┴────────────┴───────────────┴─────────────────┘
```

---

### 5. `etl/data_quality.py`

**FUNÇÃO:** Valida qualidade e calcula confidence scores

**O QUE FAZ:**
- Calcula cobertura temporal (% de dias com transações)
- Detecta lacunas temporais
- Calcula confidence score (0.0 - 1.0)
- Define data_status (TRUSTED/DEGRADED/UNTRUSTED)
- Integra com BankStrategy (futuro)

**INTERAGE COM:**
- **ENTRADA:** etl/ingestor.py (DataFrame limpo)
- **USA:** Polars (análise temporal)
- **SAÍDAS:**
  - QualityReport:
    - confidence: float
    - data_status: DataStatus
    - coverage: float
    - gaps: List[DateRange]

**POR QUE É IMPORTANTE:**
- Transparência (usuário sabe qualidade dos dados)
- Fallback inteligente (aciona Shadow Invoice se baixa)
- Explainability (confidence → UI)

**EXEMPLO DE USO:**
```python
validator = DataQualityValidator()
report = validator.validate(clean_df, institution_id="nubank")

# report.confidence: 0.95 (95% confiança)
# report.data_status: TRUSTED
# report.coverage: 0.98 (98% dos dias cobertos)
```

---

### ═══════════════════════════════════════════════════════════════
### 📂 SUBMÓDULO: etl/bank_strategy/
### ═══════════════════════════════════════════════════════════════

---

### 6. `etl/bank_strategy/__init__.py`

**FUNÇÃO:** API pública do módulo bank_strategy

**O QUE FAZ:**
- Exporta `get_bank_strategy()` (função principal)
- Esconde registry singleton (implementação privada)
- Exporta tipos: BankProfile, BankStrategy

**INTERAGE COM:**
- **ENTRADA:** transaction.py (Pydantic validators)
- **USA:** registry.py (delega get_strategy)
- **SAÍDAS:** BankStrategy (strategy apropriada)

**POR QUE É IMPORTANTE:**
- Interface estável (não muda mesmo que registry mude)
- Simplicidade (usuário só conhece get_bank_strategy)
- Encapsulamento (registry é detalhe de implementação)

**EXEMPLO DE USO:**
```python
from app.etl.bank_strategy import get_bank_strategy

strategy = get_bank_strategy("nubank")  # ← API simples
normalized = strategy.normalize_transaction(raw_data)
```

---

### 7. `etl/bank_strategy/base.py`

**FUNÇÃO:** Interface BankStrategy (ABC)

**O QUE FAZ:**
- Define contrato (todos os strategies seguem)
- Template Method Pattern (fluxo fixo de normalização)
- Hooks abstratos (_normalize_amount, _normalize_date)
- Hooks opcionais (_apply_defaults, _validate_required_fields)

**INTERAGE COM:**
- **ENTRADA:** Ninguém (é interface abstrata)
- **HERANÇA:** strategies/*.py (implementam hooks)
- **USA:** profiles.py (recebe BankProfile)

**POR QUE É IMPORTANTE:**
- Consistência (todos os bancos seguem mesmo fluxo)
- Extensibilidade (fácil adicionar novo banco)
- Comportamento padrão (herança de métodos comuns)

**TEMPLATE METHOD (5 Passos):**
```
normalize_transaction()  ← TEMPLATE (não sobrescrever)
    ↓
1. _apply_field_aliases()     (hook - pode sobrescrever)
    ↓
2. _normalize_amount()        (hook - DEVE sobrescrever)
    ↓
3. _normalize_date()          (hook - DEVE sobrescrever)
    ↓
4. _apply_defaults()          (hook - pode sobrescrever)
    ↓
5. _validate_required_fields() (hook - pode sobrescrever)
```

---

### 8. `etl/bank_strategy/profiles.py`

**FUNÇÃO:** BankProfile (dataclass de configuração)

**O QUE FAZ:**
- Define estrutura de configuração por banco
- Carregado de bank_profiles.yaml
- Immutable (frozen=True) → thread-safe
- Factory method: from_yaml()

**CAMPOS:**
```python
@dataclass(frozen=True)
class BankProfile:
    institution_id: str        # "nubank"
    display_name: str          # "Nubank"
    tier: BankTier             # TIER_1
    locale: str                # "BR" ou "US"
    date_formats: list[str]    # ["%Y-%m-%d", "%d/%m/%Y"]
    amount_format: str         # "BR" ou "US"
    required_fields: list[str] # ["amount", "date", "balance"]
    field_aliases: dict        # {"valor": "amount"}
    quality_thresholds: dict   # min_history_days, max_missing_rate
```

**INTERAGE COM:**
- **ENTRADA:** config/bank_profiles.yaml
- **USA:** enums.py (BankTier)
- **USADO POR:** BankStrategy (recebe no __init__)

**POR QUE É IMPORTANTE:**
- Configuração centralizada (um lugar só)
- Type-safe (dataclass valida tipos)
- Imutável (cacheable, thread-safe)

---

### 9. `etl/bank_strategy/registry.py`

**FUNÇÃO:** Singleton de registro (mapeia banco → strategy)

**O QUE FAZ:**
- Singleton (instância única no sistema)
- Factory (cria strategies sob demanda)
- Cache (strategies cacheadas)
- Fallback (sempre retorna strategy válida)

**FLUXO:**
```
INICIALIZAÇÃO (Startup - 1x):
  bank_profiles.yaml → BankProfile objects → _profiles dict

PRIMEIRA CHAMADA (por banco):
  get_strategy("nubank")
    ↓ (cache miss)
  _STRATEGY_MAP["nubank"] → NubankStrategy
    ↓ (instancia)
  NubankStrategy(nubank_profile)
    ↓ (cacheia)
  strategy

CHAMADAS SUBSEQUENTES:
  get_strategy("nubank")
    ↓ (cache hit - O(1))
  cached strategy
```

**INTERAGE COM:**
- **ENTRADA:** bank_strategy/__init__.py
- **USA:**
  - config/bank_profiles.yaml
  - profiles.py
  - strategies/*.py
- **SAÍDAS:** BankStrategy (instância cacheada)

**POR QUE É IMPORTANTE:**
- Performance (YAML carregado 1x)
- Flexibilidade (adicionar banco = editar YAML + mapa)
- Resiliência (fallback automático)

---

### ═══════════════════════════════════════════════════════════════
### 📂 CONFIGURAÇÃO: etl/bank_strategy/config/
### ═══════════════════════════════════════════════════════════════

---

### 10. `etl/bank_strategy/config/bank_profiles.yaml`

**FUNÇÃO:** Configurações de todos os bancos (YAML)

**O QUE CONTÉM:**
```yaml
nubank:
  display_name: "Nubank"
  tier: "TIER_1"              # Excelente
  locale: "BR"
  date_formats:
    - "%Y-%m-%dT%H:%M:%S"     # ISO 8601
    - "%Y-%m-%d"
  amount_format: "BR"         # 1.500,00
  required_fields:
    - transaction_id
    - amount
    - date
    - balance                 # ← Nubank SEMPRE envia
  field_aliases:
    id: transaction_id
  quality_thresholds:
    min_history_days: 90
    max_missing_rate: 0.05    # 5%
    min_trust_score: 0.9

itau:
  display_name: "Itaú"
  tier: "TIER_3"              # Problemático
  locale: "BR"
  date_formats:
    - "%d/%m/%Y %H:%M:%S"     # BR clássico
    - "%d/%m/%Y"
  amount_format: "BR"
  required_fields:
    - transaction_id
    - amount
    - date
    # balance OPCIONAL (Itaú às vezes não envia)
  field_aliases:
    valor: amount             # ← Itaú chama "valor"
    data: date
  quality_thresholds:
    min_history_days: 60
    max_missing_rate: 0.20    # 20% (mais tolerante)
    min_trust_score: 0.7

inter:
  display_name: "Banco Inter"
  tier: "TIER_2"              # Bom
  locale: "US"                # ← Formato US
  date_formats:
    - "%Y-%m-%d %H:%M:%S"
    - "%m/%d/%Y"
  amount_format: "US"         # 1,500.00
  required_fields:
    - transaction_id
    - amount
    - date
    - balance
  field_aliases:
    value: amount
  quality_thresholds:
    min_history_days: 75
    max_missing_rate: 0.10
    min_trust_score: 0.8
```

**INTERAGE COM:**
- **CARREGADO POR:** registry.py (_load_yaml)
- **PARSEADO POR:** profiles.py (BankProfile.from_yaml)

**POR QUE É IMPORTANTE:**
- Ops-friendly (editar sem código)
- Versionável (Git track)
- Documentação clara (comentários explicam decisões)
- Testável (fixtures fáceis)

---

### ═══════════════════════════════════════════════════════════════
### 📂 STRATEGIES: etl/bank_strategy/strategies/
### ═══════════════════════════════════════════════════════════════

---

### 11. `etl/bank_strategy/strategies/__init__.py`

**FUNÇÃO:** Exporta strategies (para registry)

**O QUE FAZ:**
- Torna `strategies/` um módulo Python
- Exporta classes: DefaultBankStrategy, NubankStrategy, etc

**CONTEÚDO:**
```python
from .default import DefaultBankStrategy
from .nubank import NubankStrategy
from .itau import ItauStrategy
from .inter import InterStrategy

__all__ = [
    "DefaultBankStrategy",
    "NubankStrategy",
    "ItauStrategy",
    "InterStrategy",
]
```

---

### 12. `etl/bank_strategy/strategies/default.py`

**FUNÇÃO:** Strategy genérica (fallback universal)

**O QUE FAZ:**
- Implementa hooks abstratos (BankStrategy)
- Parser HÍBRIDO (aceita BR E US)
- Sem validações rigorosas (tolerante)
- Usado quando banco desconhecido

**QUANDO USADO:**
- Banco não reconhecido
- Perfil não encontrado no YAML
- Testes com dados sintéticos

**PARSER HÍBRIDO (amount):**
```
Se tem vírgula E ponto:
  → Última ocorrência = decimal

Se só vírgula:
  → Assume BR (vírgula = decimal)

Se só ponto:
  → Heurística:
    "1.000" (3 dígitos) = milhar
    "1.50" (2 dígitos) = decimal
```

**POR QUE É IMPORTANTE:**
- Fallback seguro (sistema NUNCA para)
- Robustez (aceita múltiplos formatos)
- Testes (estratégia genérica para mocks)

---

### 13. `etl/bank_strategy/strategies/nubank.py`

**FUNÇÃO:** Strategy TIER_1 (Nubank - rigoroso)

**O QUE FAZ:**
- Parser otimizado (formato previsível)
- Validações estritas (fail fast se inválido)
- Sem fallbacks tolerantes
- EXIGE balance (Nubank sempre envia)

**CARACTERÍSTICAS:**
- Formato: "1.500,00" (BR consistente)
- Data: ISO 8601 ("2024-01-15T10:30:00")
- Balance: SEMPRE presente

**POR QUE RIGOROSO:**
- Nubank tem dados excelentes (TIER_1)
- Formato previsível (otimização fast path)
- Erro indica problema real (não dados ruins)

---

### 14. `etl/bank_strategy/strategies/itau.py`

**FUNÇÃO:** Strategy TIER_3 (Itaú - tolerante)

**O QUE FAZ:**
- Parser tolerante (aceita variações)
- Aliases obrigatórios ("valor" → "amount")
- Balance OPCIONAL (às vezes não envia)
- Validações relaxadas

**PROBLEMAS CONHECIDOS:**
- Usa nomes não-padrão ("valor", "data")
- Balance ausente frequentemente
- Formato BR clássico (dd/mm/YYYY)

**POR QUE TOLERANTE:**
- Itaú tem dados inconsistentes (TIER_3)
- Melhor processar com ressalvas que rejeitar
- Fallback para Shadow Invoice se muito ruim

---

### 15. `etl/bank_strategy/strategies/inter.py`

**FUNÇÃO:** Strategy TIER_2 (Inter - formato US)

**O QUE FAZ:**
- Parser formato US (1,500.00)
- Datas SQL (YYYY-MM-DD HH:MM:SS)
- Qualidade intermediária

**CARACTERÍSTICAS:**
- Amount: "1,500.00" (vírgula = milhar, ponto = decimal)
- Date: "2024-01-15 10:30:00" ou "01/15/2024"
- Balance: Sempre presente

---

## 🔄 FLUXO COMPLETO DE DADOS

```
┌─────────────────────────────────────────────────────────────┐
│ 1. WEBHOOK CHEGA (api/routes/transactions.py)              │
├─────────────────────────────────────────────────────────────┤
│ raw_data = {"id": "txn_1", "valor": "1.500,00", ...}       │
│ institution_id = "itau"                                     │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. ENRICHMENT (adiciona contexto)                          │
├─────────────────────────────────────────────────────────────┤
│ enriched = {**raw_data, "institution_id": "itau", ...}     │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. BANK STRATEGY (etl/bank_strategy/)                      │
├─────────────────────────────────────────────────────────────┤
│ strategy = get_bank_strategy("itau")                       │
│ normalized = strategy.normalize_transaction(enriched)      │
│                                                             │
│ Output:                                                     │
│   transaction_id: "txn_1"  (id → transaction_id)           │
│   amount: "1500.00"        (1.500,00 → canônico)           │
│   date: "2024-01-15T..."   (ISO 8601 UTC)                  │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. PYDANTIC (schemas/transaction.py)                       │
├─────────────────────────────────────────────────────────────┤
│ transaction = TransactionWebhook(**normalized)             │
│                                                             │
│ Field validators (SIMPLIFICADOS):                          │
│   - parse_amount("1500.00") → Decimal(1500.00)             │
│   - parse_date("2024-01-15...") → datetime(...)            │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. INGESTOR (etl/ingestor.py)                              │
├─────────────────────────────────────────────────────────────┤
│ ingestor = TransactionIngestor()                           │
│ clean_df = ingestor.process([transaction])                 │
│                                                             │
│ Pipeline:                                                   │
│   1. JSON → DataFrame                                       │
│   2. Deduplica                                              │
│   3. Normaliza textos                                       │
│   4. Converte tipos                                         │
│   5. Enriquece colunas                                      │
│   6. Calcula métricas                                       │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. CLASSIFIER (etl/classifier.py)                          │
├─────────────────────────────────────────────────────────────┤
│ classifier = TransactionClassifier()                       │
│ categorized_df = classifier.predict(clean_df)              │
│                                                             │
│ Adiciona:                                                   │
│   - final_category: "Transporte"                           │
│   - ml_confidence: 0.92                                     │
│   - category_source: "ml"                                   │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. RECURRING DETECTOR (etl/recurring_detector.py)          │
├─────────────────────────────────────────────────────────────┤
│ detector = RecurringDetector()                             │
│ enriched_df = detector.detect(categorized_df)              │
│                                                             │
│ Adiciona:                                                   │
│   - is_recurring: False                                     │
│   - is_installment: False                                   │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ 8. DATA QUALITY (etl/data_quality.py)                      │
├─────────────────────────────────────────────────────────────┤
│ validator = DataQualityValidator()                         │
│ report = validator.validate(enriched_df, "itau")           │
│                                                             │
│ Output:                                                     │
│   - confidence: 0.75                                        │
│   - data_status: DEGRADED                                   │
│   - coverage: 0.85                                          │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ 9. PERSISTÊNCIA (db/models.py)                             │
├─────────────────────────────────────────────────────────────┤
│ await save_to_postgres(enriched_df)                        │
│                                                             │
│ INSERT INTO transactions_clean (...)                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 RESUMO EXECUTIVO

### **COMPONENTES PRINCIPAIS**

| Arquivo | Função | Entrada | Saída |
|---------|--------|---------|-------|
| `ingestor.py` | Limpa e normaliza | JSON | DataFrame limpo |
| `classifier.py` | Categoriza | DataFrame | DataFrame + categoria |
| `recurring_detector.py` | Detecta padrões | DataFrame | DataFrame + flags |
| `data_quality.py` | Valida qualidade | DataFrame | QualityReport |
| `bank_strategy/` | Normaliza formatos | JSON cru | JSON canônico |

### **FLUXO SIMPLIFICADO**

```
Webhook → BankStrategy → Pydantic → Ingestor → Classifier → Detector → Quality → DB
```

### **PRÓXIMOS PASSOS**

1. ✅ Ler documentação de cada arquivo
2. ✅ Entender fluxo completo
3. ✅ Implementar código (seguir comentários)
4. ✅ Testar componente por componente
5. ✅ Integrar tudo

---

## 📚 DOCUMENTAÇÃO DETALHADA

Cada arquivo tem documentação completa em:
- `etl_docs/etl__init__.md`
- `etl_docs/ingestor.md`
- `etl_docs/classifier.md`
- `etl_docs/bank_strategy_registry.md`
- ... (outros arquivos)

---

**Total de arquivos documentados: 15**
**Linhas de documentação: ~3000**

## 🏗️ ORDEM DE CRIAÇÃO - etl/bank_strategy/

### **Arquivos (em ordem de dependência):**

1. **profiles.py** (Dataclass de configuração)
   - Depende de: Nada
   - Usado por: base.py, registry.py
   - Testar: Criar BankProfile manualmente, testar factory method

2. **base.py** (Interface ABC)
   - Depende de: profiles.py
   - Usado por: default.py, nubank.py, itau.py
   - Testar: Verificar que não pode instanciar diretamente (é abstrata)

3. **strategies/default.py** (Implementação base)
   - Depende de: base.py, profiles.py, schemas/transaction.py
   - Usado por: nubank.py, itau.py (herança), registry.py (fallback)
   - Testar: Normalizar transação genérica

4. **config/bank_profiles.yaml** (Configurações)
   - Depende de: Nada (arquivo de dados)
   - Usado por: registry.py
   - Testar: Validar YAML (syntax check)

5. **strategies/nubank.py, strategies/itau.py** (Strategies específicas)
   - Depende de: default.py, base.py, profiles.py
   - Usado por: registry.py
   - Testar: Normalizar transação específica do banco

6. **registry.py + __init__.py** (Singleton + API pública)
   - Depende de: TODOS os arquivos acima
   - Usado por: schemas/transaction.py
   - Testar: get_bank_strategy("nubank"), get_bank_strategy("unknown")