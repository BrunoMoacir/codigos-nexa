# 10 — Defesa do Consumidor (D1–D6)

> O diferencial que nenhum banco ou app comissionado pode copiar: procurar
> ativamente cobranças ilegais/abusivas e montar o dossiê para o usuário
> reclamar — com base legal citada.

## Em palavras simples

Seguro que você nunca contratou, tarifa cobrada duas vezes, juros de rotativo
muito acima da média de mercado, tarifa que subiu sem aviso. A Nexa varre seu
extrato atrás desses padrões e, quando encontra, não só avisa: monta o dossiê
com as evidências, a base legal e o passo a passo — do "ligue e conteste" ao
ZIP pronto para o PROCON ou Juizado Especial Cível.

**Linguagem importa**: o sistema fala "forte indício", "acima da média",
"pode contestar" — nunca "você tem direito a R$ X" ou "é ilegal". Indício não
é sentença, e o código foi escrito para nunca prometer o que só um juiz decide.

---

## Como é calculado — os 6 detectores

### D1 — Venda casada (`tied_sale_detector.py`)

Três caminhos independentes de detecção:

**(a) Correlação temporal** — o mais forte. Procura um lançamento de produto
vinculado dentro de **7 dias** (`_CORRELATION_WINDOW_DAYS`) após a liberação de
um crédito **do mesmo banco**. Dois regex governam:

```
crédito:  \b(emprestimo|financiamento|credito|liberacao|credconsig|consig|pessoal|veicular|imob)\b
vinculado: \b(seguro|prestamista|capitalizacao|capitaliz|assistencia|protect|assisten|garantia)\b
```

Severidade `high`; a evidência registra o intervalo exato em dias.

A correlação é por **conta** (`account_id`), não por nome de banco. Crédito
caindo na conta X e débito saindo da conta X é um vínculo mais apertado que
"mesmo banco", e `account_id` está disponível — `bank_name` não. O nome legível
vem do enriquecimento do F5 (`institution_id` via `account_balances`) quando dá
para resolver; quando não dá, o achado sai com rótulo genérico em vez de não
sair.

> **Correção de 2026-08.** A guarda exigia a coluna `bank_name`, que
> `transactions_clean` não tem e `get_transactions_for_user` não devolve —
> `if not all([...]): return []`. D1a, o caminho mais forte, era **inteiramente
> morto em produção**: o caso de manual do Tema 972 (empréstimo de R$ 15 mil
> seguido de seguro prestamista três dias depois) não gerava achado nenhum.

**(b) Tipos de tarifa suspeitos** vindos do FeeDetector (doc 06):
`SEGURO_EMBUTIDO`, `SEGURO_PRESTAMISTA`, `TARIFA_CADASTRO`.

**(c) Histórico de tarifas** (`bank_fee_history`).

**Base legal citada**: CDC art. 39, I (venda casada) · CDC art. 51 (nulidade
de pleno direito) · **Tema 972/STJ** (abusividade do seguro prestamista sem
liberdade de escolha da seguradora) · Res. CMN 3.919/2010, art. 2º · Súmula
297/STJ + ADI 2.591/STF (CDC aplica-se a instituições financeiras).

**Disclaimer específico do D1**, embutido no achado:

> ⚠️ Este achado é um PRÉ-INDÍCIO que requer confirmação. Se você contratou
> livremente este produto, arquive este achado.

A ação recomendada começa por *"confirme se você escolheu livremente"* — o
detector não pode saber se houve imposição, só que houve correlação.

### D2 — Cobranças indevidas (`wrongful_charge_detector.py`)

Quatro verificações:

**(a) Duplicidade** — lida das `FeeEntry` do F5, não do histórico agregado:

> **Correção de 2026-08.** A verificação era um SQL sobre `bank_fee_history`
> com `GROUP BY bank_name, fee_type HAVING COUNT(*) > 1` — sobre uma tabela cuja
> constraint é `UNIQUE(user_id, month, bank_name, fee_type)`. O grupo é único
> por construção: **`COUNT(*) > 1` nunca retornava linha**. E o escritor
> confirma a intenção por escrito — o docstring de
> `BankFeeAnalyzer.persist_snapshot` diz que agrega por essas mesmas chaves
> "para respeitar a constraint UNIQUE". Escritor colapsava as ocorrências de
> propósito; leitor procurava por elas. A verificação principal do D2, a que
> carrega a regra do dobro, era estruturalmente impossível.
>
> A contagem só existe onde as cobranças ainda são individuais: nas `FeeEntry`.
> E ali há a DATA de cada uma — que o histórico agregado não guarda, que o
> dossiê precisa como evidência, e que permite aplicar a regra do dobro pela
> data REAL da cobrança em vez do primeiro dia do mês corrente.

```
excedente   = total × (cnt − 1) / cnt        ← só o que passou de 1 cobrança
contestável = excedente × multiplicador
```

**A regra do dobro é datada** (`_multiplicador_dobro`), seguindo o **EAREsp
676.608/STJ**:

```
cobrança ≥ 30/03/2021  → multiplicador 2,0  ("em dobro")
cobrança  < 30/03/2021 → multiplicador 1,0  ("simples, sem dobro")
```

O rótulo apresentado ao usuário explicita qual regra se aplicou e por quê.
Esse tipo de precisão é o que separa um dossiê utilizável de um chute.

**(b) Serviços essenciais** — cobranças que deveriam ser gratuitas.

**(c) Bancos "stale"** — tarifa cobrada por banco **sem nenhuma transação nos
últimos 60 dias** (`_STALE_DAYS`): conta inativa continuando a gerar tarifa.

**(d) Tarifas novas** sem histórico anterior (severidade `medium`).

**Base legal**: CDC art. 42, parágrafo único (repetição do indébito).

### D3 — Juros abusivos (`abusive_interest_detector.py`)

Compara a taxa do usuário com a média de mercado **como múltiplo**:

```
multiple = taxa_usuário / taxa_mercado
```

| Múltiplo | Severidade | Rótulo apresentado |
|---|---|---|
| ≥ 3,0× | `high` | **"forte indício"** |
| ≥ 1,5× | `medium` | **"indício relevante"** |
| ≥ 1,0× | `low` | **"atenção"** |
| < 1,0× | — | nenhum achado |

Os rótulos são o vocabulário calibrado do produto — nunca "ilegal", nunca
"você tem direito a".

Taxas de mercado vivas em duas fontes, cada uma no papel em que é autoridade:
as **médias** vêm do SGS (ponderadas pelo volume das concessões — é a "taxa
média apurada pelo BACEN" a que o Tema 27/STJ se refere) e a **distribuição por
instituição**, de onde sai a taxa máxima praticada, vem do Olinda `taxaJuros`.

| Modalidade | Série SGS (% a.m.) | Jun/2026 |
|---|---|---|
| Cartão rotativo | 25477 | 15,13% |
| Cartão parcelado | 25478 | 9,32% |
| Cheque especial | 25463 | 7,56% |
| Crédito pessoal não consignado | 25464 | 7,08% |
| Consignado INSS | 25468 | 1,83% |
| Rotativo — máximo praticado | Olinda, maior IF | 24,99% |

**Teto legal do cheque especial: 8% a.m.** (Res. CMN 4.765/2019, art. 2º,
vigente desde 06/01/2020). Está em `bacen_credit.TETO_CHEQUE_ESPECIAL_MENSAL`,
aparece no painel da tool do agente e entra no `legal_basis` do D3.

> **A unidade e a identidade das séries foram confirmadas** contra o catálogo
> de dados abertos do BACEN em 22/08/2026, e `tests/defense/test_series_bacen.py`
> refaz essa conferência a cada execução — ele pergunta ao BACEN o título
> oficial de cada código e exige que contenha "Taxa média **mensal**" e
> "Pessoas físicas". O alerta que o código carregava (*"validar unidade da
> série 20714 antes de usar em produção"*) está resolvido, e a resposta foi
> pior do que o alerta supunha: ver a seção de correções abaixo.

> **Três correções de 2026-08 no D3.**
>
> 1. `_INTEREST_PATTERN` procurava `\bjuro\b` e `\bencargo\b` no **singular**.
>    Extrato escreve "JUROS", "ENCARGOS" — "JUROS EMPRESTIMO", "ENCARGOS FATURA"
>    e "JUROS SOBRE SALDO DEVEDOR" não casavam. Só passava quando havia
>    "rotativo" na mesma descrição.
>
>    O padrão é deliberadamente **mais largo** que o `JUROS_ROTATIVO` do F5 e os
>    dois não devem ser unificados: lá o objetivo é classificar uma *tarifa* de
>    rotativo (e por isso exige contexto de cartão/fatura, para não capturar
>    juro de empréstimo, que é custo legítimo); aqui é encontrar *qualquer*
>    encargo para comparar com o mercado.
>
> 2. As três fontes de taxa falavam vocabulários diferentes: o Olinda devolve
>    `rotativo`, o BacenCredit e o fallback devolvem `rotativo_monthly`, e o
>    consumidor lia `market["rotativo_monthly"]`. Com o Olinda respondendo, o
>    KeyError era engolido pelo `except` e o detector devolvia lista vazia — ou
>    seja, **o D3 só funcionava quando o dado de mercado falhava**. Agora
>    `_normalizar_taxas()` põe tudo no mesmo sufixo na fronteira.
>
> 3. **A unidade das séries está errada, e agora há guarda.** Em 20/08/2026,
>    tratadas como % a.m., as séries devolviam rotativo 33,44% (3.087% a.a.),
>    rotativo máximo 20,80% — **menor que a média, o que é impossível** — e
>    cheque especial 80,00%. A contradição interna prova que estão mal
>    atribuídas, sem precisar resolver a unidade de cada uma.
>
>    O custo era silencioso: com referência de 33,44% a.m., um usuário pagando
>    os ~15% a.m. que são a taxa REAL de rotativo sai com múltiplo 0,45× e o D3
>    **não gera achado** — a comparação de juros abusivos ficava desligada
>    justamente para quem paga a taxa de mercado. `_validar_plausibilidade()`
>    rejeita taxa fora da ordem de grandeza da modalidade e o fallback
>    versionado assume, como já era feito com a série do IPCA no Architect.
>
> **Pendência jurídica:** a Res. CMN 4.765/2019 estabeleceu teto para o cheque
> especial de PF, e o número citado é 8% a.m. Se for isso, o próprio fallback
> versionado do projeto (10,80% a.m.) está acima do teto e precisa ser revisto.
> Não foi alterado — é constante versionada e a confirmação é de quem cuida da
> parte jurídica.

**Base legal**: CDC art. 51, IV · Tema 27/STJ (REsp 1.061.530/RS) · STJ 3ª
Turma 2023 · Súmula 297/STJ · ADI 2.591.

### D4 — Mudança unilateral de tarifa (`unilateral_change_detector.py`)

Compara mês a mês a mesma `(user, banco, fee_type)` em `bank_fee_history`:

```
se cur_amt ≤ prev_amt  → não é achado
increase_pct = (cur_amt − prev_amt) / prev_amt
disputed     = cur_amt − prev_amt
```

| Aumento | Severidade |
|---|---|
| ≥ 25% | `high` |
| ≥ 10% | `medium` |
| > 0% | `low` |

O docstring é explícito sobre a semântica: *"o percentual decide SEVERIDADE,
não existência do achado. Qualquer aumento sem aviso prévio é contestável."*

Verificação adicional: tarifa **acima do teto BACEN** (`high`).

### D5 — Central de Evidências (`evidence_builder.py`)

Consolida D1–D4 num dossiê e gera **4 documentos**, empacotados num ZIP:

```
00_LEIA_ME.txt            — aviso legal + trilha de canais
01_carta_contestacao.txt  — carta para SAC/Ouvidoria
02_relato_procon.txt      — relato para PROCON / Consumidor.gov.br
03_peticao_jec.txt        — modelo de petição para o JEC
04_resumo_achados.txt     — resumo dos indícios
```

**Trilha de escalonamento embutida no LEIA-ME:**

1. SAC (5 dias úteis) → 2. Ouvidoria (10 dias úteis) → 3. Consumidor.gov.br →
4. BACEN (bcb.gov.br/meubc) → 5. PROCON → 6. **JEC sem advogado até R$ 28.200**

**Correção monetária** (`calc_monetary_correction`) — não é estimativa:

- **IPCA (SGS 433) / INPC (SGS 188)**: busca as taxas mensais reais da API e
  acumula período a período —
  `fator = Π (1 + taxa_mensal_i / 100)`;
- **SELIC**: taxa anual do BacenConnector elevada ao período em dias —
  `fator = (1 + selic_anual)^(dias/365)`;
- **Fallback** quando a API falha: taxa anual histórica proporcional aos dias
  (IPCA 5,12% a.a., INPC 5,60% a.a., SELIC 14,25% a.a.).

O resultado reporta `monthly_rates_used` — quantos meses reais entraram no
cálculo. Zero significa que o fallback foi usado, e isso fica visível.

### D6 — Portabilidade total (`portability_detector.py`)

Simula a economia de migrar conta + cartão + crédito para outro banco,
cruzando F5 (tarifas) + F2 (cartões) + OPP (rendimento). Duas entradas: os
empréstimos ativos do usuário (`_check_from_loans`, com inferência de
modalidade) e o histórico de negociação. Economia estimada por diferença
simples de juros contra a melhor taxa de mercado da modalidade.

**Base legal**: Res. CMN 5.057/2022 (portabilidade gratuita).

### F9/F10 — Simulação de portabilidade e pagamento otimizado

Quando o usuário recebe uma proposta de outro banco, pode comparar o cenário
sem iniciar uma portabilidade:

```http
POST /api/v1/defense/portability/simulate
```

O corpo informa `balance`, `current_monthly_rate`, `target_monthly_rate` e
`remaining_months`. O serviço calcula as parcelas e o custo remanescente pelo
sistema PRICE e retorna a economia estimada, ou informa quando a taxa proposta
não traz vantagem. `current_payment` é opcional para preservar a parcela real
quando ela já é conhecida.

Essa rota é apenas uma simulação autenticada do plano Total. Ela não consulta
o banco destino, não solicita portabilidade e não executa pagamentos. Antes de
decidir, o usuário deve comparar o CET completo, tarifas, seguros, prazo e
condições da proposta formal.

---

## Como funciona (técnico)

- **Endpoints**: `GET /defense/{user_id}` (análise consolidada),
  `/{user_id}/dossier`, `/{user_id}/zip` (download), `/{user_id}/portability`
  e `POST /defense/portability/simulate` (simulação F9/F10).
- 6 tools no agente (`detect_abusive_fees`, `detect_wrongful_charges`,
  `detect_abusive_interest`, `get_defense_analysis`, `get_evidence_dossier`,
  `get_portability_analysis`).
- Cada `DefenseFinding` carrega: `detector`, `severity`, `bank_name`, título,
  descrição, valor em discussão, **base legal**, disclaimer educacional e ação
  recomendada em 3 níveis (negociar → reclamar no BACEN → advogado/JEC).
- Gating: plano Total.

## O que NÃO faz

- **Não protocola nada** — o usuário leva o dossiê ao PROCON/JEC; a Nexa não
  peticiona nem representa juridicamente.
- **Não afirma ilegalidade** — entrega indícios documentados e orienta
  validação por advogado quando o caso é grande.
- **Não detecta fraude de terceiros** (cartão clonado) — o foco é a relação
  usuário × banco.

### As séries de referência estavam trocadas (2026-08-22)

Fechando a pendência que a rodada anterior deixou aberta. Conferido contra o
catálogo de dados abertos do BACEN:

| código | usado como | nome oficial da série |
|---|---|---|
| 20714 | rotativo PF (% a.m.) | Taxa média de juros — **Total** (SFN inteiro: PF+PJ, livres+direcionados), em **% a.a.** |
| 20715 | rotativo máximo PF | Taxa média — **Pessoas jurídicas** — Total |
| 20706 | cheque especial PF | **Concessões** de crédito direcionado PF — BNDES. Não é taxa: é R$ milhões |
| 25433 | consignado INSS | Taxa média mensal — **Total** (SFN inteiro) |

Nenhuma das quatro media o que o código dizia. Os sintomas eram visíveis sem
consultar o catálogo: a "taxa máxima" (20,80) saía **menor** que a "média"
(33,44) porque eram PJ e SFN-total; o "cheque especial" oscilava 32 → 772 → 55
entre meses porque era volume; e 20714 e 25433 são a **mesma série** em
unidades diferentes — em 20 meses seguidos, `(1 + 25433/100)^12 − 1 == 20714/100`
dentro do arredondamento.

O custo, em termos do usuário:

| situação | referência antiga | referência corrigida |
|---|---|---|
| paga 8,28% a.m. de cheque especial (o **teto legal**, o que BB, Santander, Inter, C6 e BTG cobram) | 0,77× → **nenhum achado** | 1,10× → `low` |
| paga 40% a.m. de rotativo | 1,20× → `low` | 2,64× → `medium` |

O aglomerado dos grandes bancos em 8,26–8,28% a.m. no Olinda não é acaso: é
`1,08^(31/30) − 1 = 8,2774%`, o teto de 8% a.m. convertido para um mês de 31
dias. Serve de confirmação empírica do teto — e mostra que a referência de
10,80% deixava o D3 desligado exatamente para quem paga o máximo que a lei
permite.

**Duas fontes mortas no mesmo caminho.** O `OlindaInterestRateConnector`
consultava `TaxasJurosMensalPorMes`, que só publica financiamento imobiliário.
`get_market_averages()` devolvia `{"imovel": …}` — e como não era vazio, passava
por sucesso: o D3 nunca chegava ao BACEN, e o **D6 lia `market.get("rotativo")`
→ `None` → `continue`, sem gerar achado de portabilidade para nenhuma
modalidade de crédito**. Agora usa `ConsultaUnificada`, seleciona por
`codigoModalidade` (código estável) em vez de substring do nome, e corta pelo
período de apuração mais recente. E `get_best_rate()` filtrava por
`NumeroDeContratos`, campo que não existe na v2: `int(None or 0) = 0 < 100`
descartava todo candidato e a função devolvia `None` em toda chamada.

**Uma tabela só para cada número.** A tool do agente mantinha a própria tabela
de fallback e continuava imprimindo "Cheque Especial (média mercado): 10,80%
a.m." na tela do usuário depois que o detector já tinha sido corrigido. O D6
tinha uma terceira, com `pessoal` em 3,20% a.m. — metade da taxa real e a
modalidade **default** de `_infer_modality`. Ambas passaram a ler a referência
do D3.

**A guarda ganhou uma segunda checagem.** Além da faixa por modalidade, a ordem
entre produtos: consignado < cheque especial < rotativo. É invariante da
estrutura do crédito (desconto em folha × dívida sem garantia) e pega uma troca
de códigos que passa por todas as faixas individuais.

### Duas subverificações devolviam lista vazia desde sempre (2026-08-24)

Achado na revalidação do agente de IA, não numa auditoria da Defesa. Duas
linhas, nos dois detectores mais usados:

```
tied_sale_detector.py:270        for entry in report.entries
wrongful_charge_detector.py:449  detect_new_fees(user_id, report.entries)
```

`BankCostReport` não tem `.entries` — a lista de tarifas individuais chama-se
`fees_detected`. Nos dois casos o `AttributeError` caía num `except` que
devolve `[]`, então **`D1._check_fee_analyzer` e `D2._check_new_fees` nunca
produziram um achado**, para nenhum usuário. Como o `get_defense_analysis`
agrega D1–D4 e o dossiê D5 consome os achados, a ausência aparecia como
"nenhuma irregularidade detectada".

Medido depois da correção, com extrato contendo seguro prestamista pontual e
uma TED avulsa: D1 passa a apontar o seguro (venda casada, o caso-símbolo do
detector) e D2 a TED.

### "Sem histórico" não é "primeira vez"

Corrigir o atributo trouxe à tona o defeito seguinte, e este era pior que o
silêncio. `detect_new_fees` devolvia **toda `FeeEntry`** cujo par
(banco, tipo) não estivesse em `bank_fee_history` — sem agrupar. Uma tarifa
mensal de R$ 34,90 cobrada em seis meses virava:

```
🆕 6 tarifa(s) nova(s) sem histórico anterior:
  • Nubank — PACOTE_SERVICOS: R$ 34,90     (×6, a mesma cobrança mensal)
  → Exija do banco comprovante do contrato...
```

Duas afirmações falsas de uma vez — o número e o "primeira vez" — numa feature
que redige carta, reclamação no PROCON e modelo de JEC. A ausência em
`bank_fee_history` é fato sobre os **nossos registros**, não sobre o
comportamento do banco.

Agora `detect_new_fees` devolve **uma entrada por par** e exclui pares que
aparecem em mais de um mês da janela analisada: se a evidência que já temos em
mãos mostra a cobrança se repetindo, "primeira vez" está errado
independentemente do histórico persistido. Ver
`tests/defense/test_subverificacoes_de_tarifa.py`.

## Gaps e limitações

- **⚠️ Bloqueador de lançamento**: D5/D6 têm código pronto, mas os templates
  de dossiê/petição **nunca passaram por revisão de advogado** — política do
  projeto é não lançar D5 sem parecer jurídico (responsabilidade por
  orientação incorreta).
- ~~**⚠️ Unidade da série BACEN 20714 não validada**~~ — **resolvido em
  2026-08-22**. Não era só a unidade: as quatro séries estavam trocadas. Ver a
  correção abaixo. O teste de catálogo mantém a conferência viva.
- **A média do Olinda é simples, não ponderada por volume** — a v2 não publica
  volume por IF. Por isso o SGS continua sendo a fonte da média citada em
  documento jurídico, e o Olinda só entra para comparar bancos entre si e para
  a taxa máxima.
- **D1 é correlação, não prova.** Sete dias entre crédito e seguro é um
  indício estatístico; o usuário pode ter contratado o seguro por vontade
  própria. Daí o disclaimer de "pré-indício" e a ação começando por
  "confirme".
- **D2 e D4 dependem de `bank_fee_history` populado** pelo job das 02h00 — um
  usuário novo não tem baseline pessoal e os dois detectores ficam mudos.
- **A correção monetária cai em fallback anual** quando a API do SGS falha,
  perdendo precisão mensal — o campo `monthly_rates_used = 0` denuncia isso,
  mas o valor ainda é apresentado.
- **D4 e o futuro ranking público de bancos (V3)** dependem de massa de dados
  em `bank_fee_trends`; com poucos usuários, o baseline é o curado.
- **Recuperações não são rastreadas automaticamente** — o usuário reporta o
  desfecho; não há integração com a resposta do banco.
