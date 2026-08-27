# HIVE — Relatório de Projeto

> Estado real do projeto, posição competitiva, economia unitária e plano.
> Escrito para sócios e para qualquer pessoa que precise decidir alguma coisa
> sobre este produto.

**Data:** 27 de agosto de 2026 · **Período coberto:** outubro/2025 – agosto/2026 · 812 commits

> **Sobre o nome.** Este documento usa **HIVE**. O código, os testes, as chaves de
> cache e a documentação de funcionalidades ainda usam a marca anterior (`nexa`).
> Renomear identificadores é migração de dados e de infraestrutura, não trabalho
> de produto — e não precisa acontecer antes do aplicativo existir.

---

## Sumário executivo

A HIVE é uma plataforma de inteligência financeira pessoal construída sobre o
Open Finance brasileiro. Ela lê o extrato bancário do usuário e faz o que
nenhum produto de varejo faz hoje no Brasil: **procura ativamente o dinheiro
que os bancos tiram dele** — tarifas indevidas, juros acima do mercado, cartão
errado, dinheiro parado, direitos esquecidos — e entrega o caminho para
recuperar.

A receita vem de assinatura paga pelo usuário. Não há comissão de banco em
nenhuma recomendação, e essa é a estrutura que sustenta a única promessa que o
produto faz: **neutralidade**.

Dez meses de construção produziram um motor analítico profundo, testado e
documentado. O que **não** existe é igualmente importante: **não há aplicativo
oficial, não há um único usuário e não há receita.** Todo o valor construído
está atrás de uma tela que ainda não foi feita.

| | |
|---:|:---|
| **88.757** | linhas de código de domínio |
| **3.477** | testes passando · 79% de cobertura |
| **18** | funcionalidades documentadas e auditadas |
| **143** | assinantes para a empresa inteira se pagar |
| **0** | usuários · receita · telas |

### As notas

| Camada | Nota | Por quê |
|:---|:---:|:---|
| Profundidade analítica | **9,2** | Monte Carlo, VPL, juros contra o CET do BACEN, otimizador com valoração de milhas. Não existe equivalente no varejo brasileiro. |
| Engenharia e testes | **8,5** | 3.477 testes a 79% de cobertura, CI com três jobs, catraca de CVE. Perde pelos 137 tratamentos de erro mudos e pelo buraco em `app/jobs` (25%). |
| Segurança e LGPD | **9,3** | Auditada e corrigida em agosto/2026. |
| Arquitetura | **8,0** | Separação limpa por domínio. Pesa contra: acoplamento a `langchain` 0.2.x e arquivos de 1.500–2.200 linhas. |
| Qualidade da resposta do agente | **—** | **Não medida.** Falta chave de API no ambiente. |
| Produto entregável | **1,5** | O front atual é protótipo descartável. O oficial não começou. |
| Operação | **3,0** | Scheduler e locks prontos; nunca rodou com carga real. |
| Negócio | **1,0** | Zero usuários, zero receita. Stripe implementado e desligado. |
| **Projeto** | **6,5** | Ponderado. Sobe para 8+ com uma tela e 50 usuários. |

O projeto está **invertido** em relação à maioria. O padrão comum é interface
bonita sobre backend raso; aqui é o contrário. É um problema melhor de ter —
telas se constroem em semanas, este motor levou dez meses.

---

## 1. O que é a HIVE

### O problema

O brasileiro paga ao sistema bancário várias camadas de custo que não vê e não
contesta: tarifas que passam despercebidas, juros de rotativo muito acima da
média, cashback e milhas perdidos por usar o cartão errado, dinheiro parado
rendendo zero, saldos esquecidos em contas encerradas.

Quase nada disso é ilegal, e quase nada é visível de forma acionável. A
informação existe — espalhada entre o extrato, as tabelas do Banco Central, o
diretório do Open Finance e a letra miúda dos contratos. **Ninguém junta essas
pontas pelo usuário porque quem tem os dados é justamente quem lucra com a
distância entre elas.**

### A tese

Um produto que cobra do usuário — e apenas dele — pode fazer essa conta sem
conflito de interesse. É a diferença entre um comparador de investimentos que
ganha comissão do banco recomendado e um que ordena por quanto sobra no bolso
depois do imposto.

### Como o produto se apresenta

Duas superfícies, decididas no roadmap e ainda não construídas:

- **Feed de oportunidades** — lista ordenada por impacto em R$/mês. Cada card
  diz o que foi encontrado, quanto vale e o que fazer.
- **Chat com o consultor** — pergunta em português; o agente consulta os
  módulos de análise antes de responder.

O resto do valor chega sem o usuário abrir nada: robôs noturnos fotografam
tarifas, atualizam o catálogo de renda fixa do mercado, procuram dinheiro
parado e disparam o resumo matinal.

---

## 2. O que está construído

### Camada 1 · Dados — *funcional*

Conexão bancária via Pluggy e um pipeline de oito etapas que transforma extrato
bruto em transações limpas. É a camada mais paranoica do projeto por um motivo:
se ela erra, todas as outras recomendam bobagem.

> Ingestão · categorização · detecção de recorrência · classificação PF/PJ ·
> fatura sombra · validação de qualidade · perfil do usuário · persistência.
> Webhook assinado processa dados novos sem o usuário abrir o app.

### Camada 2 · Análise — *funcional*

O motor. Projeção de caixa de 30 dias que devolve **um número por dia**;
otimizador sobre base curada de **81 cartões de 37 emissores** que calcula em
R$/mês quanto cada um devolveria no padrão de gasto real; simulador de decisões
grandes — financiamento × consórcio × investir e comprar à vista — com VPL e
Monte Carlo; separação automática PF/PJ para o MEI; radar de renda fixa ordenado
por retorno líquido de imposto, com dados publicados pelas próprias instituições
no Open Finance.

### Camada 3 · Defesa — *pronta, bloqueada em parecer jurídico*

O diferencial que nenhum banco e nenhum app comissionado pode copiar. Seis
detectores procuram no extrato: venda casada, cobrança indevida, juros acima da
média de mercado, alteração unilateral de tarifa, oportunidade de portabilidade.
Quando encontram, montam o dossiê com evidência, base legal e passo a passo —
até o arquivo pronto para o PROCON ou o Juizado Especial.

Somam-se os direitos esquecidos (consulta real ao SVR do Banco Central e à
restituição de IR; roteiro guiado para FGTS e PIS/PASEP) e a camada fiscal
(otimizador de IR, calendário de prazos, relatório do MEI).

> **Ressalva que trava o lançamento:** os modelos de petição e as cartas nunca
> passaram por advogado. O código foi escrito com linguagem deliberadamente
> cautelosa — "forte indício", nunca "você tem direito a R$ X" — mas orientação
> jurídica em massa sem revisão é risco de responsabilidade, não bug.

### Camada 4 · Relacionamento — *funcional, não medida*

90 dias de transações formam um perfil (sete perfis comportamentais — família
estruturada, microempreendedor, estresse financeiro, entre outros) que muda o
tom do chat, o cartão recomendado e quais avisos valem a interrupção.

Sobre isso: score de saúde financeira com histórico, metas com projeção,
desafios com selos, comparação anônima com pares, **17 tipos de notificação**
filtrados por relevância, e o consultor conversacional — um agente com **31
ferramentas** que consulta os módulos antes de responder, com memória de
conversa que sobrevive a deploy.

> **Ressalva:** a qualidade da prosa que o agente escreve nunca foi medida.
> Existe camada de avaliação offline que mede o *contexto* entregue ao modelo;
> falta a chave de API para avaliar a *resposta* que o usuário lê.

### Camada 5 · Plataforma — *funcional*

Nove robôs agendados com trava distribuída (2h tarifas, 2h30 catálogo de renda
fixa, 3h dinheiro parado, 7h resumo diário, entre outros), cache e a máquina de
testes.

Segurança e LGPD foram auditadas e corrigidas em agosto/2026: revogação global
de sessão, apagamento de dados por descoberta de schema, bloqueio de login sem
oráculo de existência, telemetria que descarta o evento se a limpeza de dado
pessoal falhar, e a árvore de dependências saindo de 156 para 33
vulnerabilidades conhecidas.

Cobrança pelo Stripe está implementada e **desligada** — em *dark launch*,
registrando o que *teria* bloqueado. Esse log é a melhor evidência de
precificação que existe, e ninguém leu ainda.

### Duas ressalvas de honestidade

**1.** A classificação PF/PJ é apresentada como aprendizado de máquina. Existe
um modelo treinado no repositório e ele **não está no caminho de produção** — o
que roda são regras determinísticas. Funciona; só não é o que o nome sugere.

**2.** Dois robôs — relatório trimestral (`app/jobs/quarterly_report.py`) e
campanha de recuperação de cancelamento (`app/jobs/win_back.py`) — estão
escritos, testados e **nunca são executados**: ninguém os registrou em
`app/core/scheduler.py`, que importa 9 jobs e ignora esses 2. São 121 linhas
com testes verdes que nunca rodaram na vida real.

---

## 3. Estado técnico, medido

Contado no repositório em 27/08/2026, não extraído da documentação.

| Dimensão | Hoje | Leitura |
|:---|---:|:---|
| Código de aplicação | 88.757 linhas | 31 módulos de domínio |
| Código de teste | 47.810 linhas | 0,54 linha de teste por linha de código |
| Testes | 3.498 | 3.477 passam, 21 pulam, nenhum falha |
| Cobertura | 79% | 23.091 de 29.316 linhas — primeira medição do projeto |
| Endpoints de API | 141 | Superfície grande para um produto sem tela |
| Integrações externas reais | 8 | BACEN (SGS, Olinda, SVR), SERPRO, diretório Open Finance, Pluggy, IBGE, FipeZap |
| Ferramentas do agente | 31 | Cada uma declara confiança e origem do dado ao modelo |
| Migrações de banco | 19 | Schema versionado |
| Documentação | 11.317 linhas | 18 funcionalidades auditadas contra o código |
| Vulnerabilidades conhecidas | 33 | Eram 156 em 25/08. As 33 são quase todas `langchain` 0.2.x |
| Falhas engolidas em silêncio | 137 de 691 | **20%** dos tratamentos de erro não registram nem propagam |

### O que 79% de cobertura não quer dizer

Cobertura mede o que foi **executado**, não o que foi **verificado**. A auditoria
destes meses encontrou dezenas de testes que passavam sobre código quebrado:
varreduras vazias, asserções sobre listas vazias, testes verdes *porque* o
mecanismo estava morto.

A distribuição importa mais que a média:

| Módulo | Cobertura |
|:---|---:|
| `app/jobs` | **25,3%** |
| `app/viral` | 55,2% |
| `app/tax` | 64,0% |
| `app/agent` | 71,8% |
| `app/architect` | 73,7% |
| `app/optimizer` | 88,4% |
| `app/rights` | 91,7% |

`app/jobs` é a camada que entrega valor sem ninguém olhando — e é a menos
verificada. Os dois robôs nunca agendados saíram exatamente daí.

### Como sabemos que os testes valem alguma coisa

A auditoria não confiou na suíte: cada correção destes meses foi validada por
**mutação** — quebrar o código de propósito e exigir que um teste específico
falhe. Onde nenhum falhava, o teste era o problema, não o código. Foi assim que
apareceram os defeitos mais caros, incluindo funcionalidades inteiras que
estavam mortas para 100% dos usuários sem ninguém saber.

---

## 4. Mercado e concorrência

O Open Finance brasileiro é o maior do mundo: mais de **100 milhões de contas
conectadas** e **154 milhões de consentimentos ativos** em fevereiro de 2026,
cinco anos após o início. O trilho sobre o qual a HIVE roda cresce e é regulado
pelo Banco Central. Risco de plataforma: baixo.

### 4.1 A geração recente — e a correção que ela impõe

Entre 2025 e 2026 apareceu no Brasil uma safra de produtos de finanças pessoais
nativos de IA sobre Open Finance. **O mais relevante é o Pierre.**

| Produto | Quem está atrás | Lançado | O que é | Preço |
|:---|:---|:---|:---|:---|
| **Pierre** | **CloudWalk** (InfinitePay) — adquirido 1 mês após o lançamento | jul/2025 | Assistente conversacional multiagente sobre Open Finance. Interface é só chat. | Free · **R$ 39/mês** · **R$ 199/mês** |
| **Muuney** | independente | 2025–26 | Dashboard visual + alertas automáticos no WhatsApp | n/d |
| **Jota** | independente | 2025–26 | Assistente no WhatsApp, Pix grátis, Open Finance 20+ bancos, suporte a PJ | n/d |
| **Magie** | independente | — | Banking conversacional no WhatsApp | n/d |
| Mobills | — | 2014 | Controle de gastos | R$ 119,90/ano |
| Organizze | — | 2012 | Controle de gastos | R$ 35–69/mês |

**Números públicos do Pierre (agosto/2026):** 165 mil usuários, 1,2 milhão de
mensagens trocadas, 70+ milhões de transações processadas, R$ 800 milhões sob
acompanhamento. Três agentes nomeados (Albert, Marie, Galileu) que monitoram
padrões, sinalizam cobranças fora do normal e projetam cenários.

Fora do Brasil, a mesma safra: **Copilot Money** (US$ 95/ano), **Monarch Money**
(US$ 99,99/ano), **Cleo** (US$ 5,99–14,99/mês), **Rocket Money**
(US$ 6,99/mês).

> ### A correção
>
> Uma leitura anterior deste projeto afirmava que o consultor conversacional era
> um diferencial. **Não é mais, e é preciso registrar isso sem rodeios:** o
> Pierre faz exatamente isso, é brasileiro, roda sobre Open Finance, tem 165 mil
> usuários e está financiado por uma das fintechs mais capitalizadas do país.
>
> Uma disputa por distribuição contra a CloudWalk não é uma disputa que a HIVE
> ganha.

Isso **não** invalida o produto — reposiciona. Nenhum dos produtos acima faz
defesa do consumidor bancário. Pierre "identifica cobranças fora do padrão", o
que é detecção de anomalia estatística; não é conferir juros contra a série do
Banco Central, citar base legal e montar dossiê para o Juizado. Essa faixa
continua vazia.

### 4.2 A comparação completa

| Capacidade | HIVE | Pierre | Muuney / Jota | Mobills · Organizze | App do banco | Advogado |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| Categoriza gastos | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| Conecta via Open Finance | ✅ | ✅ | ✅ | ✅ | o próprio | — |
| Consultor conversacional | ✅ 31 tools | ✅ multiagente | ✅ WhatsApp | — | chatbot | humano |
| Projeta fluxo de caixa | ✅ | ✅ | parcial | básico | — | — |
| Sinaliza gasto fora do padrão | ✅ | ✅ | ✅ | — | — | — |
| **Detecta tarifa indevida** | ✅ | — | — | — | — | manual |
| **Confere juros contra o BACEN** | ✅ | — | — | — | — | manual |
| **Cita base legal (CDC, BACEN, STJ)** | ✅ | — | — | — | — | ✅ |
| **Monta dossiê para PROCON/JEC** | ✅ | — | — | — | — | ✅ |
| **Roteiro de negociação com o banco** | ✅ | — | — | — | — | substitui |
| **Procura dinheiro esquecido (SVR)** | ✅ | — | — | — | — | cobra por isso |
| Simula financiamento sem viés | ✅ Monte Carlo | — | — | — | viesado | — |
| Otimiza IR e calendário fiscal | ✅ | — | — | — | — | contador |
| Separa PF/PJ para MEI | ✅ | — | parcial (Jota) | — | — | contador |
| **Usuários reais** | **zero** | 165 mil | — | milhões | dezenas de milhões | o mercado |
| **Marca e capital** | **zero** | CloudWalk | independente | alta | alta | OAB |

Capacidades da HIVE conferidas no código; concorrentes conforme material
público de agosto/2026.

### 4.3 A conclusão que define o posicionamento

As linhas **em negrito** da tabela acima são as únicas onde a HIVE está sozinha.
Elas são a empresa. Todo o resto é paridade competitiva contra empresas com
marca, capital e usuários.

- **A camada de conversa não é mais diferencial.** É requisito de entrada.
- **A camada de defesa não tem concorrente de varejo.** O substituto é um
  escritório de direito bancário, que cobra honorário de êxito.

Procuramos um aplicativo brasileiro que detecte tarifa indevida e juros
abusivos automaticamente. Não existe. O espaço é atendido por escritórios,
calculadoras de laudo e plataformas de reclamação — todos manuais, todos caros,
todos acionados só depois que o usuário já desconfia de alguma coisa.

> **Isso é oportunidade e alerta ao mesmo tempo.** O espaço está aberto porque
> ninguém provou que dá para vender defesa bancária em assinatura de aplicativo.
> A HIVE seria a primeira — a validação de mercado é *nossa* tarefa, não algo
> herdado de um concorrente que já validou.

---

## 5. Modelo de negócio e economia unitária

### O chão de custo

Acessar o Open Finance sem ser instituição autorizada exige um agregador. O
plano de dados da Pluggy parte de **R$ 2.500/mês**; a Belvo, de patamar mais
alto. É o preço de entrada da categoria no Brasil.

```
Pluggy — plano de dados (mínimo mensal)      R$ 2.500
Infraestrutura (API, banco, cache)           R$ 200 – 600
E-mail transacional                          R$   0 – 120
Telemetria                                   R$   0 – 150
─────────────────────────────────────────────────────────
Custo mensal antes do primeiro usuário     ≈ R$ 2.700 – 3.400
```

### Quantos assinantes pagam a empresa inteira

| Plano | Preço | Stripe | IA/usuário | Contribuição | Equilíbrio |
|:---|---:|---:|---:|---:|---:|
| Pro | R$ 19,90 | −1,18 | −1,50 | R$ 17,22 | 174 |
| Total | R$ 39,90 | −1,98 | −2,00 | R$ 35,92 | 84 |
| Mistura 80/20 | — | — | — | R$ 20,96 | **143** |

*Sobre chão de R$ 3.000/mês. Stripe a 3,99% + R$ 0,39. Custo de IA estimado
sobre os modelos econômicos já configurados por padrão.*

> **143 assinantes pagam a empresa inteira.** Isso é meta de beta fechado, não
> de campanha de marketing. A 4% de conversão, são ~3.600 cadastros. É o número
> mais encorajador deste relatório, e muda a natureza da decisão: *a HIVE não
> precisa de escala para existir; precisa de escala para valer muito.*

### A armadilha do plano gratuito

O plano gratuito hoje permite um banco conectado. Cada conexão viva é um item
cobrado pela Pluggy acima do mínimo — **usuário gratuito tem custo marginal
recorrente e receita zero**. Com dez mil gratuitos conectados, a conta do
agregador deixa de ser R$ 2.500 e vira a maior linha da empresa.

Resolve-se no desenho do plano, não no orçamento: o gratuito continua provando
valor — inclusive o SVR, que é o gancho mais forte — sem carregar uma conexão
permanente.

### Preço recomendado

O Pierre cobra **R$ 39/mês** no plano intermediário e **R$ 199/mês** no
superior, por um produto que faz menos. Isso é evidência direta de disposição a
pagar, e torna o preço atual da HIVE difícil de justificar.

| Plano | Hoje | Recomendado | Anual | Racional |
|:---|---:|---:|---:|:---|
| Gratuito | 1 banco | sem conexão viva | — | Diagnóstico: SVR, importação de extrato, primeira análise. A conexão permanente é o que custa. |
| Pro | R$ 19,90 | **R$ 29,90** | R$ 249 | Ainda 23% abaixo do Pierre Pro. O anual devolve o preço antigo a quem se compromete. |
| Total | R$ 39,90 | **R$ 59,90** | R$ 499 | Defesa completa, dossiê, portabilidade, IR. Muito abaixo do Pierre Premium e de honorário de êxito. |
| Família | — | R$ 89,90 | R$ 749 | Até 4 membros. Maior receita por conta e maior barreira de saída. |

**Lançar com plano anual é a mudança de maior retorno e a mais barata** — é
preço no Stripe, não código. Resolve o cancelamento mensal antes que ele exista
e alinha a HIVE ao formato que o brasileiro já compra em finanças pessoais
(Mobills vende R$ 119,90/ano; Copilot e Monarch são anuais).

> **Sobre cobrar percentual do que a HIVE recupera.** É o modelo que melhor casa
> com a entrega e o que carrega mais risco: envolve honorário sobre direito do
> consumidor, e há restrição real sobre quem pode cobrar por isso sem ser
> advogado. **Não implementar antes de parecer jurídico.** Se viável, é o maior
> desbloqueio de receita que este produto tem.

---

## 6. Crescimento

Com zero usuários, qualquer projeção é cenário, não previsão. O relógio começa
no **lançamento do aplicativo oficial**, não hoje.

| Em 18 meses | Conservador | Base | Agressivo |
|:---|---:|---:|---:|
| Motor de aquisição | Orgânico, conteúdo | Orgânico + mídia + imprensa | Capital + canal corporativo |
| Cadastros | 8.000 | 40.000 | 150.000 |
| Conversão | 3% | 4% | 5% |
| Assinantes | 240 | 1.600 | 7.500 |
| Ticket médio | R$ 22 | R$ 26 | R$ 28 |
| Receita mensal | R$ 5,3 mil | R$ 41,6 mil | R$ 210 mil |
| Receita anualizada | R$ 63 mil | R$ 500 mil | R$ 2,5 mi |
| Cancelamento mensal | 9% | 7% | 6% |
| Resultado | Se paga, não cresce sozinho | Negócio real, financiável | Exige capital e time |

*Conversão de 3–5% é a faixa usual de freemium de consumo; cancelamento de
6–10%/mês é a faixa de assinatura de consumo no Brasil. O plano anual desloca o
cancelamento para a renovação e melhora os três cenários.*

### A alavanca que já está no código

Existem **R$ 5,12 bilhões** parados no Sistema de Valores a Receber do Banco
Central, pertencentes a **22,66 milhões de CPFs**. A consulta assistida já está
implementada.

"Existe dinheiro esquecido no seu nome" é o melhor gancho de conversão que este
produto tem: é verificável, é gratuito de descobrir e transforma o cadastro num
evento com desfecho concreto no primeiro minuto. **Nenhum concorrente da tabela
da seção 4 tem isso.** No cenário Base, é essa alavanca que separa 40 mil
cadastros de 8 mil.

O SVR é público e gratuito, e cobrar pela consulta seria insustentável. O papel
dele é ser porta de entrada: descobre-se de graça, vende-se o que vem depois.

---

## 7. Quanto vale

| Leitura | Faixa | Base do cálculo |
|:---|---:|:---|
| Custo de reconstrução | R$ 700 mil – 1,3 mi | ~48 pessoa-mês sênior no Brasil para refazer 88 mil linhas de domínio, 47 mil de teste e a pesquisa regulatória embutida |
| Venda como ativo hoje | R$ 120 – 400 mil | Sem usuários, aplicativo ou receita, o comprador assume todo o risco de integração |
| Cenário Base (ARR R$ 500 mil) | R$ 1 – 2 mi | Assinatura de consumo no Brasil, 2–4× receita anualizada, ajustado por cancelamento |
| Cenário Agressivo (ARR R$ 2,5 mi, churn <6%) | R$ 7,5 – 12,5 mi | 3–5× receita. Vertical financeiro com IA embarcada negocia com prêmio sobre a mediana |

Faixas com margem de erro larga.

> **O mesmo código vale de R$ 120 mil a R$ 2 milhões dependendo apenas de
> existirem um aplicativo e mil e seiscentos assinantes.** Não há nenhuma tarefa
> de backend nesta lista que mude esse número.

---

## 8. Riscos

| Risco | Grau | Situação e mitigação |
|:---|:---:|:---|
| **Concorrente capitalizado** | Alto | O Pierre ocupa a camada conversacional com 165 mil usuários e o capital da CloudWalk. Mitigar: **não competir nessa camada** — vencer em profundidade na faixa de defesa, que ele não ocupa. |
| **Fornecedor único de dados** | Alto | Todo o produto depende da Pluggy, com R$ 2.500/mês de piso. Sem plano B implementado. Mitigar: manter a ingestão agnóstica e cotar alternativas antes de precisar. |
| **Responsabilidade jurídica** | Alto | A camada de defesa gera petição para o JEC e orienta sobre direitos, sem revisão de advogado. **Não lançar sem parecer.** |
| **Nenhum usuário jamais usou** | Alto | Dezoito funcionalidades construídas sem um ciclo de feedback real. Só se descobre com gente usando. |
| **Falhas silenciosas** | Médio | 137 tratamentos de erro que não registram nada. Foi assim que a primeira ferramenta do agente ficou quebrada para todos os usuários com dados. Mitigar: proibir no lint. |
| **Dívida de `langchain`** | Médio | 28 das 33 vulnerabilidades restantes e uma migração de major pendente. |
| **Concentração no fundador** | Médio | Todo o conhecimento de domínio em uma pessoa. As 11 mil linhas de documentação auditada são a mitigação parcial. |
| **Plataforma Open Finance** | Baixo | Regulada pelo BACEN e em crescimento: 100 milhões de contas conectadas. |

---

## 9. Plano dos próximos 90 dias

Em ordem, porque cada passo depende do anterior.

1. **Congelar o backend.** Nenhuma funcionalidade nova. O motor está à frente do
   produto por uma distância grande demais, e cada módulo novo aumenta a dívida
   de tela. Só correção do que o piloto expuser.

2. **Aplicativo oficial, duas telas.** Feed de oportunidades e chat. Nada além.
   A tentação será reexpor os 141 endpoints, e é ela que precisa ser resistida.

3. **Parecer jurídico sobre a camada de defesa.** Roda em paralelo com o
   aplicativo, não depende dele, e bloqueia o lançamento. Começar imediatamente.

4. **Piloto fechado com 50 pessoas reais.** Conexão de verdade, dinheiro de
   verdade. Mede o que dez meses de teste não mediram: se a análise importa para
   quem a recebe.

5. **Stripe, plano anual e ligar a cobrança.** Antes de fixar preço, ler o
   registro do *dark launch* — ele guarda meses de evidência sobre o que teria
   sido bloqueado.

6. **Instrumentar o funil.** Sem medir cadastro → conexão → primeira análise →
   assinatura, o cenário Base é ficção. A ferramenta já está instalada e
   desligada.

7. **Medir a qualidade da resposta do agente.** É a métrica que importa num
   produto conversacional, e é a única nota deste relatório que está em branco.

### A recomendação, em uma frase

Dez meses construíram um motor que custa de R$ 700 mil a R$ 1,3 milhão para
refazer e que hoje se venderia por uma fração disso, por um motivo só:
**ninguém consegue ligá-lo.** Pela primeira vez desde outubro, a próxima tarefa
certa não está no backend — e o custo de continuar construindo motor é adiar a
única coisa que multiplica o valor de tudo o que já existe.

---

## Nota de método

Os números de código, testes, cobertura, endpoints e falhas silenciosas foram
**contados no repositório** em 27/08/2026 com ferramentas de análise (`wc`,
`grep`, AST, `pytest --collect-only`, `pytest --cov`), não extraídos da
documentação. As descrições de funcionalidade foram conferidas contra o código
durante a auditoria módulo a módulo dos últimos meses — as ressalvas da seção 2
(o classificador que não usa o modelo treinado, os dois robôs nunca agendados)
foram encontradas assim.

Preços de concorrentes, métricas do Pierre, custo do agregador de Open Finance,
saldo do SVR e estatísticas do Open Finance são **fontes públicas**, listadas
abaixo. Cenários de crescimento, faixas de avaliação e recomendação de preço são
**modelagem**, com as premissas declaradas em cada tabela.

### Fontes

- [Pierre — CloudWalk newsroom](https://www.cloudwalk.io/newsroom/pierre-turns-financial-management-into-a-simple-conversation----no-spreadsheets-no-confusing-charts) · [Exame — Pierre vira aposta da CloudWalk](https://exame.com/inteligencia-artificial/pierre-assistente-de-ia-para-financas-vira-aposta-da-cloudwalk-para-crescer-no-consumo/) · [Pierre na Google Play](https://play.google.com/store/apps/details?id=io.cloudwalk.pierre)
- [Muuney × Pierre — comparativo](https://muuney.com.br/blog/muuney-vs-pierre-comparativo) · [Ranking de assistentes financeiros no WhatsApp 2026](https://blog.jota.ai/ranking-assessor-financeiro-aplicativos-2026/)
- [Comparativo de apps de orçamento com IA 2026](https://budget-calm.com/blog/best-ai-budgeting-apps-2026) (Copilot, Monarch, Cleo, Rocket Money)
- [Pluggy — planos e preços](https://www.pluggy.ai/precos) · [custo comparado de agregadores](https://www.tabnews.com.br/GuilhermeVieira/estou-desenvolvendo-um-app-de-financas-pessoais-e-nao-consigo-pagar-o-open-finance-pluggy-r2-5k-mes-belvo-r6k-mes-tecnospeed-r1-5k-de-entrada-r540)
- [Mobills — preços](https://www.mobills.com.br/pricing/) · [comparativo Mobills × Organizze 2026](https://gazetabrasilia.com.br/melhores-aplicativos-de-controle-financeiro-2026/)
- [SVR — R$ 5,12 bi para 22,66 milhões de CPFs](https://www.suno.com.br/noticias/dinheiro-esquecido-svr-junho-2026-r5-bilhoes-fgo-desenrola-go/amp/)
- [Open Finance Brasil — 100 milhões de clientes conectados](https://finsidersbrasil.com.br/economia-open/brasil-lidera-open-finance-no-mundo-com-100-milhoes-de-clientes/)
- [Múltiplos de avaliação de SaaS no Brasil, 2026](https://negociosbrasil.com.br/quanto-vale-uma-empresa-saas-no-brasil/)
