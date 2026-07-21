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

## O que faz (os 6 detectores — `app/defense/services/`)

| ID | Detector | Como detecta | Base legal citada no código |
|----|----------|--------------|------------------------------|
| D1 | **Venda casada** (`tied_sale_detector.py`) | Seguros/capitalização/pacotes debitados que aparecem junto de contratação de crédito | CDC art. 39, I |
| D2 | **Cobranças indevidas** (`wrongful_charge_detector.py`) | Duplicidade (mesmo valor+descrição em janela curta) e tarifa nova sem histórico (baseline pessoal) | CDC art. 42, parágrafo único (repetição em dobro) |
| D3 | **Juros abusivos** (`abusive_interest_detector.py`) | Compara juros pagos (rotativo/cheque especial) com séries oficiais BACEN — Olinda taxaJuros por instituição, fallback SGS 20714/20706 | Tema 27/STJ (REsp 1.061.530/RS), STJ 3ª Turma 2023, Súmula 297/STJ, ADI 2.591 |
| D4 | **Mudança unilateral de tarifa** (`unilateral_change_detector.py`) | Baseline por banco (`bank_fee_history`): tarifa subiu sem contrapartida → alerta | Res. CMN sobre reajuste com aviso prévio |
| D5 | **Central de Evidências** (`evidence_builder.py`) | Consolida D1–D3 em dossiê estruturado + export ZIP com evidências para PROCON/JEC | — (formato de protocolo) |
| D6 | **Portabilidade total** (`portability_detector.py`) | Simula a economia migrando conta+cartão+crédito para outro banco (cruza F5+F2+OPP) | Res. CMN 5.057/2022 (portabilidade gratuita) |

## Como funciona (técnico)

- **Endpoints**: `GET /defense/{user_id}` (análise consolidada),
  `/{user_id}/dossier`, `/{user_id}/zip` (download), `/{user_id}/portability`.
- 6 tools no agente (`detect_abusive_fees`, `detect_wrongful_charges`,
  `detect_abusive_interest`, `get_defense_analysis`, `get_evidence_dossier`,
  `get_portability_analysis`).
- Cada achado (`DefenseFinding`) carrega: severidade, valor estimado em
  discussão, base legal, disclaimer educacional e ação recomendada em 3
  níveis (negociar → reclamar no BACEN → advogado/JEC).
- Gating: plano Total.

## O que NÃO faz

- **Não protocola nada** — o usuário leva o dossiê ao PROCON/JEC; a Nexa não
  peticiona nem representa juridicamente.
- **Não afirma ilegalidade** — entrega indícios documentados e orienta
  validação por advogado quando o caso é grande.
- **Não detecta fraude de terceiros** (cartão clonado) — o foco é a relação
  usuário × banco.

## Gaps e limitações

- **⚠️ Bloqueador de lançamento**: D5/D6 têm código pronto, mas os templates
  de dossiê/petição **nunca passaram por revisão de advogado** — política do
  projeto é não lançar D5 sem parecer jurídico (responsabilidade por
  orientação incorreta).
- D4 e o futuro ranking público de bancos (V3) dependem de massa de dados em
  `bank_fee_trends` — com poucos usuários, o baseline é o curado.
- Recuperações não são rastreadas automaticamente (o usuário reporta o
  desfecho; integração com resposta do banco não existe).
