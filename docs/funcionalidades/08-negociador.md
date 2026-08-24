# 08 — Negociador (F13)

> Detecta o que dá para negociar com o banco (juros, anuidade) e entrega o
> roteiro pronto da ligação — com números de mercado como argumento.

## Em palavras simples

Negociar com banco funciona muito mais do que as pessoas imaginam — mas
ninguém sabe o que falar. A Nexa detecta seus pontos negociáveis ("você pagou
R$ 240 de juros rotativos em 3 meses; a taxa média de mercado é X%") e gera um
roteiro personalizado: o que pedir, que número citar, o que responder se o
atendente disser não.

---

## Como é calculado

### Constantes que governam a detecção

```python
_MIN_HEALTH_SCORE_FOR_BARGAIN = 60     # score mínimo para ter poder de barganha
_JUROS_WINDOW_MONTHS          = 3      # janela de detecção de juros rotativos
_GOOD_PAYER_WINDOW_MONTHS     = 6      # janela para contar meses sem juros
_ANUIDADE_MARKET_MONTHLY_AVG  = 30.0   # referência: R$ 30/mês ≈ R$ 360/ano
_MIN_JUROS_TO_FLAG            = 20.0   # R$ — ignora IOF de centavos
```

### Gatilho 1 — `JUROS_ROTATIVO_ALTO`

Filtra tarifas do tipo `JUROS_ROTATIVO` (vindas do FeeDetector, doc 06) nos
últimos **3 meses** com `amount ≥ R$ 20`, e **agrupa por banco** — cada banco
com juros detectados vira uma oportunidade separada.

```
monthly_avg = Σ juros_do_banco / 3
potential_saving_monthly = monthly_avg
```

A economia potencial é o **próprio valor pago**, usado como proxy direto. O
código é explícito sobre o porquê: *"não há como saber a taxa exata sem o saldo
devedor"*. Ou seja, o número apresentado é "quanto você pagou", não "quanto
você vai economizar" — e a linguagem do roteiro reflete isso.

O benchmark de mercado (`market_rate`) vem vivo do BacenConnector (SELIC +
séries SGS de crédito) e entra na frase: *"A taxa média CDC de mercado é X% a.m."*

### Gatilho 2 — `ANUIDADE_ALTA`

Filtra tarifas `ANUIDADE_CARTAO` nos últimos 12 meses, converte para
equivalente mensal e compara com a referência:

```
se monthly_equiv ≤ R$ 30  → nenhuma oportunidade
saving = monthly_equiv − R$ 30
```

### Gatilho 3 — `HEALTH_SCORE_ALTO`

Só dispara quando **não há nenhuma outra oportunidade** e o score é **≥ 70**
(threshold mais alto que o mínimo geral de 60). É a negociação proativa: sem
tarifa abusiva para reclamar, o argumento passa a ser o próprio bom histórico.

```
potential_saving_monthly = 0.0
```

Zero de propósito — não há economia mensurável a prometer, apenas poder de
barganha para limites e taxas futuras. O banco citado é o **mais frequente nas
tarifas do usuário**, ou o genérico "seu banco principal".

> **Correção de 2026-08-24: este gatilho nunca disparou.** Os dois chamadores
> do F13 — `negotiator/router.py` e a ferramenta `get_negotiation_script` do
> agente — tinham cópias idênticas de um helper que fazia
> `from app.profile.user_profile_analyzer import UserProfileAnalyzer`.
> `app.profile` **não existe** no projeto. Três erros na mesma linha e meia: o
> módulo (o analisador vive em `app.forecast.etl.profiles`), o parâmetro
> (`analyze()` recebe `df, income_profile, committed_pct` — nunca `user_id`) e
> o campo (é `financial_health_score`). O `ModuleNotFoundError` caía no
> `except` e o score voltava **50 para todo mundo, sempre** — abaixo do piso de
> 70, então `HEALTH_SCORE_ALTO` estava morto para 100% dos usuários, inclusive
> os de score 90.
>
> O 50 fabricado não parava aí: entrava no prompt do Claude ("Health Score
> Nexa: 50/100"), no roteiro de emergência ("meu score é 50/100 — perfil de
> baixo risco", que é o que o usuário levaria ao gerente), no
> `estimated_success_pct` (exatamente 50 para todos) e no `confidence_score`
> do relatório, como um termo constante de 0,15.
>
> `app/negotiator/health_score.py` passa a ser a fonte única, com a renda
> filtrada pelo `IncomeProfiler`, e devolve **`None`** — não 50 — quando o
> perfil não pode ser calculado: sem score o gatilho não dispara, o roteiro
> omite o argumento de score e o termo de confiança vale zero. O relatório
> ganha `user_profile_analyzer` em `data_sources` só quando o score foi
> realmente calculado — é o marcador que teria denunciado o import quebrado.
>
> **O card viral não muda:** `HEALTH_SCORE_ALTO` nasce com
> `potential_saving_monthly = 0.0`, então a soma do `SavingsConsolidator` é a
> mesma. Ver `tests/negotiator/test_score_real.py`.
>
> A guarda estrutural é `tests/test_imports_apontam_para_modulos_que_existem.py`:
> varre a AST de todo `app/` e falha se algum `from app.X import` apontar para
> módulo inexistente — inclusive dentro de `try/except`, que é onde este erro
> se escondeu. Um import assim não quebra a importação do módulo: falha em
> runtime, em silêncio, no caminho que o usuário percorre.

### Gatilho 4 — Cheque especial

`_detect_cheque_especial` aplica a mesma lógica de janela de 3 meses sobre
juros de cheque especial, com normalização de descrição própria.

### Proxy de "bom pagador"

`_count_good_payer_months` conta **meses consecutivos, a partir do mais
recente, sem nenhum `JUROS_ROTATIVO`** dentro da janela de 6 meses. É o
argumento mais forte do roteiro ("sou cliente há X meses sem pagar juros"), e
o código anota honestamente que é um proxy — ausência de juros rotativos não é
o mesmo que score de crédito.

### O loop de calibração — o que torna o número honesto

Este é o mecanismo que diferencia o módulo. O detector **estima** o ganho por
heurística; o usuário reporta o desfecho real
(`PATCH /negotiator/history/{id}`: sucesso / parcial / recusado + ganho). O
job `intelligence_metrics` (05h30) roda `compute_calibration()`:

```
para cada desfecho:
    realized = ganho_reportado        se status ≠ "recusado"
             = 0.0                    se status == "recusado"    ← ponto crítico
    ratio    = clamp(realized / potential,  0.0,  3.0)

realization_factor = mediana(ratios)   por tipo de gatilho
```

Regras de segurança:
- **`MIN_SAMPLES = 5`** — abaixo de 5 desfechos resolvidos, nenhum fator é
  produzido para aquele gatilho;
- **Fator limitado a `[0,2 · 1,2]`** — proteção contra outliers e dados sujos;
- **`recusado` conta como 0**, não é descartado. Isso é o que faz o fator
  refletir a **taxa real de sucesso**, e não a média dos vencedores. Sem essa
  regra, o produto prometeria o resultado dos casos bem-sucedidos como se fosse
  o esperado.

O router do Negociador aplica o fator ao ganho apresentado **e declara a
origem** ao usuário ("estimativa ajustada por 12 negociações reais") — nunca
calibração silenciosa. Persistido em `data/negotiator_calibration.json`
(runtime, gitignored), com cache por mtime.

### Roteiros por IA (`negotiator/script_generator.py`)

Script personalizado por oportunidade: LLM com **fallback de template**. Entram
no prompt os dados do usuário (valor pago, banco, meses como bom pagador,
health score) e o benchmark BACEN como argumento. Sem chave de LLM
configurada, o template funcional é usado.

---

## Como funciona (técnico)

- **Endpoints**: `POST /negotiator/generate-script`,
  `GET /negotiator/history/{user_id}`, `PATCH /negotiator/history/{id}`.
- Cruza FeeDetector (F5) + BACEN + health score.
- Histórico em `negotiation_history`; cada roteiro gerado é registrado e o
  ganho real reportado vira métrica ("você já recuperou R$ X negociando").
- Tool no agente: `get_negotiation_script`. O total de ganho potencial
  alimenta o Placar de Economia (V1).
- Gating: 0 no Free, 1 roteiro/mês no Pro, ilimitado no Total.

## O que NÃO faz

- **Não liga para o banco** — a execução é do usuário (F9, negociação
  assistida/automatizada, é visão de futuro com barreiras regulatórias).
- **Não promete resultado** — linguagem calibrada: "argumentos com base em
  dados", nunca "você vai conseguir".

## Gaps e limitações

- **A economia do rotativo é o valor pago, não a economia real.** Sem o saldo
  devedor e a taxa contratada, o produto não consegue calcular quanto seria
  economizado com uma taxa melhor — usa o pago como proxy, e isso superestima
  o ganho de uma negociação parcial. O fator de calibração corrige isso
  empiricamente **depois** de 5+ desfechos reportados.
- **Anuidade usa média de mercado simplificada** (`_ANUIDADE_MARKET_MONTHLY_AVG
  = 30.0` hardcoded) — o cruzamento com a base de 81 cartões (que tem anuidades
  reais por produto) é a melhoria natural e ainda não foi implementada; o
  próprio módulo declara isso no cabeçalho.
- **"Bom pagador" é ausência de juros rotativos**, não score de crédito real —
  proxy declarado.
- **A calibração é global, não por usuário/banco** — o fator é por tipo de
  gatilho, agregando todos os usuários e todas as instituições.
- **Sem LLM configurado**, o roteiro sai de template: funcional, mas menos
  personalizado.
- **Sem Score Nexa calculável**, `HEALTH_SCORE_ALTO` não é oferecido. É
  deliberado: a oportunidade inteira É a frase "seu score é X/100, use isso
  para negociar" — sem X medido, não há o que afirmar ao gerente.
