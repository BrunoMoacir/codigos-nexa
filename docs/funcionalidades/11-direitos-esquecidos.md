# 11 — Direitos Esquecidos (T3)

> "Existe dinheiro esquecido em seu nome?" — com consulta REAL onde os canais
> oficiais permitem, e roteiro honesto onde não permitem.

## Em palavras simples

Existem bilhões esquecidos no Brasil: saldos de contas encerradas (SVR do
Banco Central), FGTS de empregos antigos, cotas de PIS/PASEP, restituição de
IR não sacada. A Nexa verifica isso em dois níveis: **consulta de verdade**
onde existe API oficial (SVR e restituição de IR), e **roteiro guiado** onde
não existe (FGTS e PIS/PASEP).

---

## Como funciona — as 4 fontes e suas capacidades

`GET /rights/{user_id}` devolve as 4 fontes com um campo `capability`, para o
frontend saber o que pode oferecer:

| Fonte | `capability` | O que a Nexa consegue fazer |
|---|---|---|
| SVR (BACEN) | `assisted_real` | Consulta real (existe/não existe), com captcha oficial no app |
| Restituição IRPF | `authorized_real` | Consulta real via SERPRO, se configurado e autorizado pelo titular |
| FGTS | `guided` | Sinal de relevância + roteiro; não existe API para terceiros |
| PIS/PASEP | `guided` | Idem |

---

## Como é calculado / consultado

### SVR — consulta assistida (`connectors/svr_public.py`)

API pública oficial mapeada do frontend do BACEN:

```
GET /publico/rest/captcha
    → { imagem base64, hash, (áudio base64 para acessibilidade) }

GET /publico/rest/valoresAReceber/{cpf}/{dataISO}/{hash}/{resposta}
    → { temValorAReceber: bool }
```

**HTTP 412 = resposta do captcha incorreta/expirada** → o app gera outro.

**O humano permanece no loop, por design declarado**: o comentário no código é
literal — *"a Nexa NUNCA resolve nem contorna o captcha"*. O captcha oficial é
exibido dentro do app e o usuário digita, exatamente como no portal do BACEN.

**Validação de CPF antes da chamada** (`validate_cpf`) — dígitos verificadores
completos, incluindo a rejeição de CPFs de dígito repetido (`111.111.111-11`):

```python
for i in (9, 10):
    weights = range(i + 1, 1, -1)
    total   = sum(int(d) * w for d, w in zip(digits[:i], weights))
    check   = (total * 10) % 11 % 10
    if check != int(digits[i]): raise ValueError("CPF inválido")
```

Isso evita chamada inútil ao BACEN e é uma proteção de rate limit, não só de
UX.

**Mascaramento LGPD** (`mask_cpf`): `"12345678909"` → `"***.456.***-**"`.
Só a forma mascarada vai para o log; o CPF **nunca é persistido**.

Endpoints: `GET /rights/{user_id}/svr/captcha`, `POST /rights/{user_id}/svr/check`.

### Restituição de IRPF — consulta autorizada (`connectors/serpro_restituicao.py`)

API Consulta Restituição do SERPRO
(`gateway.apiserpro.serpro.gov.br/consulta-restituicao/v1`). Fluxo:

1. **O titular** gera um token de compartilhamento no e-CAC (Compartilha
   Receita Federal) — é o usuário que autoriza, nos termos da LGPD;
2. Cola o token na Nexa;
3. A Nexa chama `GET /Consultar/{token}` e **decripta os campos** com
   **RSA/ECB/PKCS#1 v1.5**, usando a chave privada do e-CNPJ do contratante
   (`SERPRO_RESTITUICAO_PRIVATE_KEY_B64`, DER PKCS#8 em base64).

OAuth2 `client_credentials` com **cache de token em memória**, com margem de
segurança de 30 segundos antes do vencimento (`expires_in − 30`, mínimo 30s) —
para nunca usar um token à beira de expirar.

**Semântica dos códigos de erro**, mapeada e traduzida ao usuário:

| Código | Significado |
|---|---|
| 404 | CPF sem restituição disponível no exercício atual |
| 403 | token de autorização expirado, já utilizado ou revogado |
| 401 | token de outra API / versão / contratante |
| sem credenciais | resposta `nao_configurado` com passo a passo — **nunca erro seco** |

Endpoint: `POST /rights/{user_id}/ir/check`. Modo **trial** validado ao vivo.

### FGTS — estimativa heurística + roteiro (`services/fgts_checker.py`)

Não há API para terceiros. A Nexa detecta vínculo CLT por keyword na descrição
dos créditos:

```
\b(salario|salário|folha|holerite|vencimento|remuneracao|remuneração|clt|
   pagamento\s+de\s+salario|adiantamento\s+salarial)\b
```

O padrão mora em `services/contexto_transacional.PADRAO_SALARIO` — um só. Havia
duas: uma constante compilada (`_CLT_KEYWORDS`) que ninguém usava, e uma regex
inline diferente no meio do filtro. A documentada era a morta.

E dimensiona o **depósito** do período — nunca o saldo:

```
sinal.valor = salário_mensal_médio × 0,08 × meses_com_salário
```

(8% é a alíquota do art. 15 da Lei 8.036/1990.)

O número sai em `sinal`, não em `estimated_amount`, com o rótulo do que ele é:
*"Depósitos de FGTS estimados no período analisado (não é saldo)"*.

**O aviso acompanha o número, sempre**:

> O valor acima é o DEPÓSITO estimado do seu vínculo atual no período
> analisado — não é saldo, não é dinheiro esquecido e, com contrato em vigor,
> o saque só ocorre nas hipóteses previstas em lei.

Roteiro entregue: app FGTS da Caixa → login CPF/GOV.BR → "Meus contratos" →
para empresas extintas, ida presencial à agência com CTPS → avaliar se o
saque-aniversário ainda compensa.

### PIS/PASEP (`services/pis_pasep_checker.py`)

Duas verificações distintas:

**(a) Abono salarial** — renda média mensal comparada ao teto legal
(**R$ 2.765,93** no calendário 2026, ano-base 2024 — ver
`app/rights/parametros_legais.py`):

```
se renda_mensal_média ≤ teto  → cabe no teto de RENDA (um dos quatro requisitos)
senão                         → acima do teto; verificar cotas pré-1988
```

O valor do abono é proporcional de verdade: `meses/12 × salário mínimo`. E vem
acompanhado dos **três requisitos que a Nexa não consegue verificar** — 5 anos
de inscrição no PIS/PASEP, 30 dias de atividade no ano-base, dados na
RAIS/eSocial — porque caber no teto de renda não é ter direito.

**(b) Cotas PIS/PASEP pré-1988** — roteiro com o telefone oficial da CEF
(0800-726-0207) para quem nunca sacou há mais de 10 anos.

Aviso embutido: *"Cotas PIS/PASEP pré-1988 têm correção especial (BTN + 3%
a.a.). O valor real só pode ser consultado presencialmente ou via app
oficial."*

### Regra de integridade: varredura automática nunca inventa valor

Vale para os **dois** endpoints e para a tool do agente:

- `estimated_amount` só é preenchido por **consulta real** (hoje, a restituição
  via SERPRO). Heurística nunca preenche.
- `total_estimated_recoverable` soma apenas valores confirmados — numa
  varredura automática, que não faz consulta nenhuma, é sempre `0.0`.
- As heurísticas saem em `sinal`, com `rotulo` (o que o número mede) e `base`
  (como foi obtido), e `nao_e_valor_a_receber = true`.

Até 2026-08 essa regra valia só para `GET /fiscal/forgotten-rights`.
`GET /rights/{user_id}`, que é a porta de entrada, somava as heurísticas com
confiança `medium` num campo chamado "total recuperável" — ver a seção de
correções.

---

## O que NÃO faz

- **Não mostra o VALOR do SVR** — a consulta pública oficial só responde se
  existe; montante e resgate exigem GOV.BR do titular (limite do BACEN, não
  nosso).
- **Não consulta FGTS/PIS automaticamente** — não existe API para terceiros.
- **Não guarda CPF/data de nascimento** das consultas.
- **Não pede senha GOV.BR** — nunca; os textos repetem isso ao usuário.
- **Não resolve captcha** — por decisão explícita, não por limitação técnica.

### As correções de 2026-08-22

A metade "consulta real" (SVR público e SERPRO) não precisou de nada — é o
melhor trabalho de integração externa do projeto, com 46 testes verdes. O
defeito estava inteiro na porta de entrada.

**O número da capa era fabricado nas três parcelas.** Um usuário de
R$ 6.000/mês, com salário e IRRF normais, lia:

```
TOTAL 'RECUPERÁVEL' ANUNCIADO: R$ 13.712,00
  fgts            2400.0  medium
  pis_pasep       1412.0  medium
  ir_restituicao  9900.0  medium
```

- FGTS: 8% do salário do emprego **ativo**. Não é esquecido nem sacável fora
  das hipóteses legais.
- PIS: `_estimate_abono` devolvia o salário mínimo cheio para **qualquer**
  renda — os dois ramos da função davam o mesmo número, porque
  `months_worked` era fixado em 12.
- IR: o IRRF **retido**, não a restituição. Quem deve o que reteve recebe zero.

**O teto do abono estava 2,6× maior que o legal.** `5 * 1412.0` = R$ 7.060. O
critério nunca foi 5 salários mínimos, e sim 2 — e desde 2026 é um valor
corrigido pelo INPC (R$ 2.765,93 no calendário 2026), desvinculado do mínimo.

**A "renda média mensal" era a média por transação.** `income["amount"].mean()`.
Quem ganhava R$ 12.000/mês e recebia 60 Pix pequenos aparecia com "renda média
R$ 1.901,41/mês" e virava elegível ao abono.

**O FGTS dependia de como o patrão parcelava o pagamento.** `months` contava
LINHAS: com a mesma renda de R$ 4.000/mês, quem recebia de uma vez via
R$ 1.600 e quem recebia adiantamento + salário via R$ 960.

**A soma do IRRF misturava os sinais.** `abs(sum(amount))`: seis retenções de
R$ 500 mais uma restituição **já recebida** de R$ 4.000 davam "R$ 1.000 de
IRRF retido".

**A faixa de isenção era de 2024.** `28_559.70` anuais, contra R$ 5.000/mês
desde 01/2026 (Lei 15.270/2025). Quem ganha R$ 3.000/mês era informado de que
estava "acima do limite de isenção", com R$ 2.700 estimados.

**Duas regexes por verificador, e a morta era a certa.** `_CLT_KEYWORDS` e
`_IR_KEYWORDS` eram compiladas e nunca usadas; o filtro real era uma inline
mais pobre. A do IRRF não casava `IMPOSTO DE RENDA RETIDO NA FONTE` — a forma
mais literal que um extrato escreve.

**Três implementações paralelas com três políticas.** O router estimava e
somava; o `rights_monitor` nunca fabricava; a tool do agente era **texto
estático** que nunca chamava os verificadores. A tool agora lê os
verificadores e mostra a `capability` real — antes escondia do usuário a única
parte da funcionalidade que consulta de verdade.

**CPF obrigatório na query string de `GET /fiscal/forgotten-rights`** — e
nenhum dos três conectores usava. Parâmetro removido: CPF em URL vai para
access log, proxy, histórico e header `Referer`, numa funcionalidade cujo
compromisso declarado é registrar só CPF mascarado.

**Uma leitura do extrato em vez de cinco.** Cada verificador lia por conta
própria, cada um com a sua versão da janela e da regex. Agora há
`ContextoTransacional`, que também trouxe o limite superior da janela (o mês
corrente pela metade diluía a média — o mesmo defeito já corrigido no Radar de
Oportunidades).

**Rate limit de 10/min** nos três endpoints que fazem proxy de API oficial de
terceiro. O risco era o IP da Nexa ser bloqueado pelo BACEN — o que derruba
justamente a única consulta de verdade que a funcionalidade tem.

**40 testes novos.** Não havia nenhum para os quatro verificadores, e
`total_estimated_recoverable` não tinha asserção em lugar algum.

## Gaps e limitações

- **O sinal de FGTS é o depósito, não o saldo**: `salário × 8% × meses` ignora
  a correção (TR + 3% a.a. desde cada depósito) e cobre só a janela analisada.
  Está rotulado como tal e não entra em soma de valor a receber.
- **A detecção de vínculo CLT é por keyword**, com os mesmos limites do
  IncomeProfiler: PJ que recebe com descrição "pagamento de salário" seria
  contado.
- **A elegibilidade ao abono não é determinável pela Nexa.** O teto de renda é
  um dos quatro requisitos; os outros três dependem da RAIS/eSocial e do tempo
  de inscrição no PIS. A resposta mostra os três em vez de afirmar direito.
- **Os parâmetros legais mudam em janeiro.** Ficam em
  `app/rights/parametros_legais.py`, datados e com fonte, e
  `tests/rights/test_parametros_legais.py` **falha quando o ano vira** — é a
  guarda que faltava quando o salário mínimo de 2024 e a faixa de IR de 2024
  seguiram em produção em 2026.
- **Produção do IR exige contrato pago com o SERPRO** (Loja SERPRO, custo por
  consulta) — o trial já foi validado ponta a ponta.
- **A UI do fluxo** (exibir captcha, campo do token e-CAC) depende do frontend
  oficial — o backend está pronto.
- **A API pública do SVR não é versionada formalmente.** Se o BACEN mudar, o
  conector precisa acompanhar — os erros degradam com 503 e mensagem amigável,
  mas a funcionalidade cai.
