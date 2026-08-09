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
| FGTS | `guided` | Estimativa heurística + roteiro; não existe API para terceiros |
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
\b(salario|folha|pagamento|holerite|vencimento|remuneracao|clt)\b
```

E estima:

```
estimated = salário_mensal × 0,08 × meses_detectados
```

(8% é a alíquota padrão do FGTS sobre o salário bruto CLT.)

Confiança: `medium` com ≥ 3 meses detectados, `low` abaixo disso, `unknown`
sem salário identificado.

**O aviso acompanha o número, sempre**:

> Estimativa Nexa (R$ X) baseada em N meses de salário detectado × 8%. O saldo
> real inclui correção TR + 3% a.a. e só a Caixa tem o extrato completo.

Roteiro entregue: app FGTS da Caixa → login CPF/GOV.BR → "Meus contratos" →
para empresas extintas, ida presencial à agência com CTPS → avaliar se o
saque-aniversário ainda compensa.

### PIS/PASEP (`services/pis_pasep_checker.py`)

Duas verificações distintas:

**(a) Abono salarial** — renda média dos últimos 365 dias comparada ao teto de
**5 salários mínimos**:

```
se monthly_avg ≤ teto  → provavelmente elegível
senão                  → acima do teto; verificar cotas pré-1988
```

Estimativa do abono (`_estimate_abono`): proporcional aos meses trabalhados
sobre 12 — com renda ≤ 1 salário mínimo, o valor é o próprio salário mínimo
(R$ 1.412,00 na constante atual).

**(b) Cotas PIS/PASEP pré-1988** — roteiro com o telefone oficial da CEF
(0800-726-0207) para quem nunca sacou há mais de 10 anos.

Aviso embutido: *"Cotas PIS/PASEP pré-1988 têm correção especial (BTN + 3%
a.a.). O valor real só pode ser consultado presencialmente ou via app
oficial."*

### Regra de integridade: varredura automática nunca inventa valor

A visão fiscal (`GET /fiscal/forgotten-rights`) reporta status por fonte **sem
inventar valores** — regra codificada em teste: `estimated_amount` em varredura
automática é sempre `0.0`. O mock antigo que fabricava valores por hash do CPF
foi removido.

As estimativas heurísticas (FGTS, abono, IRRF detectado nas transações,
tarifas em múltiplos bancos) existem para **contextualizar relevância**, sempre
com `estimated_confidence` declarada — nunca como promessa de valor a receber.

---

## O que NÃO faz

- **Não mostra o VALOR do SVR** — a consulta pública oficial só responde se
  existe; montante e resgate exigem GOV.BR do titular (limite do BACEN, não
  nosso).
- **Não consulta FGTS/PIS automaticamente** — não existe API para terceiros.
- **Não guarda CPF/data de nascimento** das consultas.
- **Não pede senha GOV.BR** — nunca; os textos repetem isso ao usuário.
- **Não resolve captcha** — por decisão explícita, não por limitação técnica.

## Gaps e limitações

- **A estimativa de FGTS ignora a correção**: `salário × 8% × meses` é o valor
  *depositado*, não o saldo. O real inclui TR + 3% a.a. desde cada depósito —
  o aviso diz isso, mas o número apresentado subestima sistematicamente.
- **A detecção de vínculo CLT é por keyword**, com os mesmos limites do
  IncomeProfiler: PJ que recebe com descrição "pagamento" seria contado.
- **O salário mínimo está hardcoded** em `_estimate_abono` (R$ 1.412,00) — e o
  `months_worked` é fixado em 12, então a proporcionalidade real do abono não é
  modelada.
- **Produção do IR exige contrato pago com o SERPRO** (Loja SERPRO, custo por
  consulta) — o trial já foi validado ponta a ponta.
- **A UI do fluxo** (exibir captcha, campo do token e-CAC) depende do frontend
  oficial — o backend está pronto.
- **A API pública do SVR não é versionada formalmente.** Se o BACEN mudar, o
  conector precisa acompanhar — os erros degradam com 503 e mensagem amigável,
  mas a funcionalidade cai.
