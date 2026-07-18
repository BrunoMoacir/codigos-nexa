# 11 — Direitos Esquecidos (T3)

> "Existe dinheiro esquecido em seu nome?" — com consulta REAL onde os canais
> oficiais permitem, e roteiro honesto onde não permitem.

## Em palavras simples

Existem bilhões esquecidos no Brasil: saldos de contas encerradas (SVR do
Banco Central), FGTS de empregos antigos, cotas de PIS/PASEP, restituição de
IR não sacada. A Nexa verifica isso em dois níveis:

1. **SVR — consulta de verdade, dentro do app**: você digita CPF, data de
   nascimento e responde o desafio de segurança oficial do BACEN (o mesmo
   captcha do site oficial, mostrado dentro da Nexa). A resposta é real e
   imediata: existe ou não existe valor em seu nome. O valor exato e o resgate
   são no portal oficial com sua conta GOV.BR — a Nexa te leva até lá.
2. **Restituição de IR — consulta autorizada em tempo real**: você gera uma
   autorização no e-CAC (é você quem autoriza, nos termos da LGPD), cola o
   token na Nexa, e ela consulta a API oficial do SERPRO: valor, situação
   ("em fila de restituição") e banco do crédito.

FGTS e PIS/PASEP não têm API para terceiros — nesses, a Nexa entrega o
roteiro exato de verificação (orientativo, e assumidamente orientativo).

## Como funciona (técnico)

### Consulta assistida SVR (`app/rights/connectors/svr_public.py`)
- API pública oficial mapeada do frontend do BACEN:
  `GET /publico/rest/captcha` → imagem base64 + hash;
  `GET /publico/rest/valoresAReceber/{cpf}/{dataISO}/{hash}/{resposta}` →
  `{temValorAReceber}`. HTTP 412 = captcha errado (app gera outro).
- **O humano permanece no loop**: a Nexa nunca resolve nem contorna o captcha —
  usa o fluxo público exatamente como o site oficial.
- CPF validado por dígitos verificadores ANTES da chamada; **nunca
  persistido**; logs só com CPF mascarado (`***.982.***-**`).
- Endpoints: `GET /rights/{user_id}/svr/captcha`,
  `POST /rights/{user_id}/svr/check`.

### Consulta autorizada de restituição (`connectors/serpro_restituicao.py`)
- API Consulta Restituição do SERPRO
  (`gateway.apiserpro.serpro.gov.br/consulta-restituicao/v1`), OAuth2
  client_credentials com cache de token; modo **trial** validado ao vivo.
- Resposta criptografada: campos decriptados com RSA PKCS#1 v1.5 (chave do
  e-CNPJ do contratante, env `SERPRO_RESTITUICAO_PRIVATE_KEY_B64`).
- Token de compartilhamento é gerado pelo TITULAR no e-CAC (Compartilha
  Receita Federal) — o aviso legal LGPD vem na própria resposta.
- 404 = sem restituição; 401/403 = token expirado/usado; sem credenciais →
  resposta `nao_configurado` com passo a passo (nunca erro seco).
- Endpoint: `POST /rights/{user_id}/ir/check`.

### Visão geral e capacidades
- `GET /rights/{user_id}` lista as 4 fontes com `capability`:
  `assisted_real` (SVR) · `authorized_real` (IR, se SERPRO configurado) ·
  `guided` (FGTS, PIS/PASEP) — o frontend sabe o que pode oferecer.
- Estimativas heurísticas (IRRF detectado nas transações, tarifas em
  múltiplos bancos) contextualizam a relevância, sempre com confiança
  declarada.
- A visão fiscal (`GET /fiscal/forgotten-rights`) reporta status por fonte
  **sem inventar valores** — regra codificada em teste: `estimated_amount`
  em varredura automática é sempre 0.0. (O mock antigo que fabricava valores
  por hash do CPF foi removido.)

## O que NÃO faz

- **Não mostra o VALOR do SVR** — a consulta pública oficial só responde
  se existe; montante e resgate exigem GOV.BR do titular (limite do BACEN,
  não nosso).
- **Não consulta FGTS/PIS automaticamente** — não existe API para terceiros.
- **Não guarda CPF/data de nascimento** das consultas.
- **Não pede senha GOV.BR** — nunca; os textos repetem isso ao usuário.

## Gaps e limitações

- Produção do IR exige **contrato pago com o SERPRO** (Loja SERPRO, custo por
  consulta) — trial já validado ponta a ponta.
- A UI do fluxo (exibir captcha, campo do token e-CAC) depende do frontend
  oficial — backend pronto.
- Se o BACEN mudar a API pública do SVR (não versionada formalmente), o
  conector precisa acompanhar — erros degradam com 503 e mensagem amigável.
