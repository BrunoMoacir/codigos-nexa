# 05 — Classificador PF/PJ (F4 / Divider)

> Para os 15+ milhões de MEIs do Brasil: separa automaticamente o que é gasto
> pessoal e o que é gasto da empresa na mesma conta bancária.

## Em palavras simples

O MEI típico mistura tudo numa conta só: o mercado da família e o insumo do
negócio saem do mesmo cartão. Na hora de declarar o DAS ou entender se o
negócio dá lucro, vira um pesadelo. A Nexa classifica cada transação como
"pessoal" ou "empresa" — e aprende com as correções do usuário.

> ⚠️ **Estado real do código (auditado):** a classificação em produção é
> **100% baseada em regras determinísticas**. O `PFPJClassifier.__init__` seta
> `self.model = None` e nunca carrega os artefatos `.pkl`; o comentário no
> código diz literalmente *"If an ML model is available, use it (not
> implemented here)"*. O Random Forest existe como artefato treinado
> (`models/pf_pj_classifier.pkl`, 80 KB, + `feature_encoders.pkl` e
> `feature_scaler.pkl`) e tem script de treino, mas **não está no caminho de
> inferência**. Ver "Gaps" no fim.

---

## Como é calculado

### As regras, na ordem exata de precedência

`PFPJClassifier.classify_batch` roda **vetorizado em Polars** — uma única
`pl.when(...).then(...)` encadeada, sem loop Python por linha. As keywords são
unidas com `|` em um regex só, para uma passagem por linha.

A ordem importa: **a primeira condição que casar decide**.

| # | Condição | Rótulo |
|---|---|---|
| 1 | `category ∈ pj_categories` | **PJ** |
| 2 | descrição contém uma `pj_keyword` | **PJ** |
| 3 | `\|amount\| > R$ 2.000` | **PJ** |
| 4 | descrição contém uma `pf_keyword` | **PF** |
| 5 | merchant ∈ {microsoft, fornecedor, imobiliaria, cemig, contador} | **PJ** |
| 6 | merchant ∈ {uber, netflix, starbucks, cinepolis, spotify} | **PF** |
| 7 | nenhuma das anteriores | **UNCERTAIN** |

**Vocabulários (`PFPJFallbackClassifier`):**

- `pj_categories` (8): `SALARY`, `OFFICE_SUPPLIES`, `RENT`, `SOFTWARE`,
  `CONSULTING`, `MARKETING`, `UTILITIES`, `TELEPHONE`.
- `pj_keywords` (15): `empresa`, `ltda`, `fornecedor`, `aluguel`, `escritorio`,
  `imobiliaria`, `viagem negocios`, `software`, `corporativo`, `marketing`,
  `cemig empresas`, `consultoria`, `contador`, `salario`, `papelaria`.
- `pf_keywords` (16): `uber`, `netflix`, `carrefour`, `academia`,
  `restaurante`, `drogaria`, `shopping`, `cinepolis`, `padaria`, `spotify`,
  `lavanderia`, `starbucks`, `pet shop`, `livraria`, `pix recebido`, `amigo`.

**A regra do R$ 2.000 é a mais agressiva do conjunto** e vem *antes* das
keywords PF: qualquer transação acima de R$ 2 mil é marcada PJ mesmo que a
descrição diga "restaurante". A racionalização é que gasto grande em conta de
MEI tende a ser do negócio — mas é também a maior fonte de falso positivo
conhecida (ver Gaps).

**Regra adicional só no caminho unitário** (`classify()`, usado em testes de
performance e não na versão vetorizada): `amount < R$ 20` **e** hora `< 8h` ou
`> 18h` → PF (compra pequena fora do horário comercial). Essa regra **não
existe** no `classify_batch`, que é o caminho do pipeline — uma divergência
real entre os dois métodos.

### Subcategorias PJ (`divider/subcategory_classifier.py`)

Só transações rotuladas PJ recebem subcategoria (PF e UNCERTAIN ficam `None`).
São **10 subcategorias**: `receita_servicos`, `receita_produtos`,
`despesa_software`, `despesa_marketing`, `despesa_transporte`,
`despesa_equipamento`, `despesa_pessoal_pj`, `despesa_imposto`,
`despesa_bancaria`, `despesa_outros_pj`.

Cascata de decisão:

1. **Mapa direto de categoria ETL** — `SALARY → despesa_pessoal_pj`,
   `TAX → despesa_imposto`, `BANK_FEE → despesa_bancaria`,
   `SOFTWARE → despesa_software`, `MARKETING → despesa_marketing`,
   `OFFICE_SUPPLIES → despesa_equipamento`, `CONSULTING → receita_servicos`,
   `RENT → despesa_equipamento` (aluguel de escritório).
2. **Receita por sinal positivo + keyword forte** → `receita_servicos`.
3. **Keywords por subcategoria** (aplicadas em descrição + merchant). Exemplos:
   - `despesa_software`: aws, google cloud, azure, github, notion, figma,
     salesforce, openai, anthropic, datadog, vercel, netlify… (~29 termos);
   - `despesa_marketing`: google ads, meta ads, tiktok ads, rd station,
     mailchimp…;
   - `despesa_imposto`: regex com fronteira de palavra — `\bdas\b`, `\biss\b`,
     `\bpis\b`, `simples nacional`, `darf`, `irpj`, `csll`, `cofins`. As
     fronteiras evitam que "das" dentro de outra palavra dispare;
   - `receita_produtos`: mercado livre, shopee, amazon seller, shopify.
4. **Heurística por valor** (só chega aqui quem não casou nenhuma keyword):
   crédito alto → `receita_servicos`; débito muito alto →
   `despesa_pessoal_pj`; resto → `despesa_outros_pj`.

### Detector de MEI (`optimizer/detectors/mei_detector.py`)

Não classifica transações — decide se **o usuário** é microempreendedor, o que
ativa o cluster `MICROEMPREENDEDOR` e o relatório fiscal. Quatro sinais
independentes:

| Sinal | Condição |
|---|---|
| `income_pattern_pj` | `IncomeProfiler` classificou como PJ ou MIXED |
| `b2b_tools` | gasto total em ferramentas B2B (`is_b2b`) > R$ 50 |
| `multiple_cnpj_payers` | recebimentos de **CNPJs distintos** ≥ limiar — conta CNPJs únicos, não transações ("1 empresa pagando 10× não é 10 clientes") |
| `unstable_income` | `income_stability < 0,45` |

```
is_likely_mei  = (nº de sinais ≥ 2)
mei_confidence = min(nº de sinais / 4, 1,0)
```

A saída inclui `missing_signals` (quais dos 4 faltaram) e
`false_positive_risk` — ou seja, o detector reporta o que **não** viu, não só
o que viu.

### Correção manual (`context_overrides`)

O usuário corrige uma classificação e ela fica gravada. `apply_user_overrides`
roda no runner do ETL **depois** do estágio 4, sobrescrevendo o rótulo — a
correção vence as regras em todas as execuções seguintes.

### O modelo que existe mas não roda

`scripts/ml/train_pf_pj_classifier.py` treina um `RandomForestClassifier`
com `n_estimators=100`, **18 features** (temporais, monetárias, textuais,
categóricas e de recorrência), `test_size=0.2` estratificado, `random_state=42`
e validação cruzada 5-fold. Persiste três artefatos: modelo, encoders
categóricos e scaler numérico. Base versionada em
`data/training_dataset_pf_pj.csv/.parquet`; resultados de validação em
`docs/pf_pj_validation_results.json` (última validação: 2026-02-13, casos
sintéticos rotulados).

Para colocá-lo em produção faltaria: carregar os `.pkl` no `__init__`,
extrair as 18 features no `classify_batch` e definir o limiar de confiança
abaixo do qual as regras assumem — a arquitetura multi-layer fallback já está
descrita, mas não implementada.

---

## Como funciona (técnico)

- Roda como **estágio 4 do pipeline ETL** (`app/forecast/etl/runner.py:157`) e
  também no `app/runner.py:288`. Toda transação nova já sai classificada.
- Saída: colunas `pf_pj_label` (PF/PJ/UNCERTAIN) e `pj_subcategory`.
- O runner loga a partição (`PF=x, PJ=y, UNCERTAIN=z`) a cada execução.
- Alimenta o Relatório Fiscal MEI (doc 12) e o cluster comportamental (doc 13).
- Mixed-use: estabelecimentos ambíguos (atacadão que é estoque) passam pelo
  `etl/mixed_use_detector.py` antes.

## O que NÃO faz

- **Não substitui contador** — a classificação é gerencial; a obrigação
  fiscal formal continua do usuário/contador.
- **Não re-treina online** — correções do usuário valem imediatamente via
  override, mas nenhum modelo é atualizado.
- **Não usa ML hoje** (ver acima).

## Gaps e limitações

- **⚠️ O ML documentado não está ativo.** Os `.pkl` existem, o script de treino
  existe, a inferência não. Toda a classificação sai das regras. Onde a
  documentação anterior dizia "ML → regras → default", o comportamento real é
  "regras → UNCERTAIN".
- **A regra `> R$ 2.000 → PJ` precede as keywords PF.** Um MEI que gasta
  R$ 2.500 num supermercado para a família tem a transação marcada como
  empresa. É a maior fonte de falso positivo do classificador, e o
  `context_overrides` existe justamente por isso.
- **Vocabulário pequeno e enviesado**: 15 keywords PJ e 16 PF, com marcas
  específicas (Netflix, Starbucks, Cinépolis, Cemig). Nichos — produtor rural,
  profissional liberal, e-commerce — caem em `UNCERTAIN`.
- **`classify()` e `classify_batch()` divergem**: a regra de valor baixo fora
  do horário comercial só existe na versão unitária.
- **`UNCERTAIN` não tem tratamento downstream declarado** — não vira "pessoal
  por padrão" no classificador; quem consome precisa decidir.
- **Sem métrica de acurácia em produção**: existe validação offline com casos
  sintéticos; monitorar drift com dados reais é melhoria futura.
- **`multiple_cnpj_payers` depende de `payer_document_type`/`payer_document`**,
  campos opcionais do Open Finance. Sem eles, o detector de MEI conta
  transações como proxy (declaradamente menos preciso) ou perde o sinal.
