# 05 — Classificador PF/PJ (F4 / Divider)

> Para os 15+ milhões de MEIs do Brasil: separa automaticamente o que é gasto
> pessoal e o que é gasto da empresa na mesma conta bancária.

## Em palavras simples

O MEI típico mistura tudo numa conta só: o mercado da família e o insumo do
negócio saem do mesmo cartão. Na hora de declarar o DAS ou entender se o
negócio dá lucro, vira um pesadelo. A Nexa classifica cada transação como
"pessoal" ou "empresa" automaticamente — e aprende com as correções do
usuário.

## O que faz

- **Classificação híbrida** (`app/divider/classifier.py` + estágio 4 do ETL):
  modelo **Random Forest treinado** (`models/pf_pj_classifier.pkl`, com
  `feature_encoders.pkl` e `feature_scaler.pkl`) + camada de regras
  determinísticas + defaults — padrão multi-layer fallback: se o ML não tem
  confiança, regras decidem; se nada decide, marca como pessoal (conservador).
- **Correção manual** (`context_overrides`): o usuário corrige uma
  classificação e ela fica gravada — a correção vence o modelo nas próximas.
- **Subcategorias** (`divider/subcategory_classifier.py`): refinamento por
  tipo de despesa.
- **Detector MEI** (`optimizer/detectors/mei_detector.py`): identifica pelo
  padrão de transações que o usuário é microempreendedor (recebimentos via
  maquininha, DAS pago, fornecedores) — ativa o cluster MICROEMPREENDEDOR e o
  relatório fiscal.
- **Base de treino versionada**: `data/training_dataset_pf_pj.csv/.parquet` +
  resultados de validação em `backend/docs/pf_pj_validation_results.json`.

## Como funciona (técnico)

- Features do modelo: descrição normalizada, valor, dia/hora, recorrência,
  MCC/categoria, contraparte. Encoders e scaler persistidos junto ao `.pkl`.
- Integração: roda dentro do pipeline ETL (toda transação nova já sai
  classificada); alimenta o Relatório Fiscal MEI (doc 12) e o cluster
  comportamental.
- Mixed-use: transações de estabelecimentos ambíguos (atacadão que é estoque)
  passam pelo `mixed_use_detector` do ETL antes.

## O que NÃO faz

- **Não substitui contador** — a classificação é gerencial; a obrigação
  fiscal formal continua do usuário/contador.
- **Não re-treina online** — correções do usuário valem imediatamente via
  override, mas o modelo em si só melhora em re-treino offline com o dataset
  atualizado.

## Gaps e limitações

- O modelo foi treinado com dataset interno limitado — generaliza bem para
  padrões comuns de MEI, mas nichos (produtor rural, profissional liberal com
  CNPJ) têm acurácia menor; o fallback de regras segura esses casos.
- Não há métrica de acurácia em produção exposta (existe validação offline em
  `docs/pf_pj_validation_results.json`); monitorar drift é melhoria futura.
