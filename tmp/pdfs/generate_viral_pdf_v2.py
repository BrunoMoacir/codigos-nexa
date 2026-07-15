from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path("output/pdf/VIRAL_COMUNIDADE_NEXA_COMPLETO_V2.pdf")
MD  = Path("output/pdf/VIRAL_COMUNIDADE_NEXA_COMPLETO_V2.md")
PAGE_W, _ = A4

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=28, leading=34, alignment=TA_CENTER, textColor=colors.HexColor("#0F172A"), spaceAfter=18))
styles.add(ParagraphStyle(name="CoverSub",   parent=styles["Normal"], fontSize=13, leading=18, alignment=TA_CENTER, textColor=colors.HexColor("#334155")))
styles.add(ParagraphStyle(name="H1x",    parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=17, leading=22, textColor=colors.HexColor("#0F172A"), spaceBefore=10, spaceAfter=8))
styles.add(ParagraphStyle(name="H2x",    parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=colors.HexColor("#1E3A8A"), spaceBefore=8,  spaceAfter=6))
styles.add(ParagraphStyle(name="Bodyx",  parent=styles["BodyText"], fontSize=9.2, leading=12.6, textColor=colors.HexColor("#111827"), spaceAfter=5))
styles.add(ParagraphStyle(name="Bulletx",parent=styles["BodyText"], fontSize=9,   leading=12,   leftIndent=10, firstLineIndent=-6, spaceAfter=2))
styles.add(ParagraphStyle(name="TableHead", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=7.2, leading=8.6,  textColor=colors.white))
styles.add(ParagraphStyle(name="TableCell", parent=styles["BodyText"], fontSize=7.0, leading=8.5, textColor=colors.HexColor("#111827")))
styles.add(ParagraphStyle(name="CodexCode",  parent=styles["BodyText"], fontName="Courier", fontSize=7.0, leading=9.0, textColor=colors.HexColor("#111827"), backColor=colors.HexColor("#F1F5F9"), borderPadding=4))
styles.add(ParagraphStyle(name="Note",   parent=styles["BodyText"], fontSize=8.6, leading=11.5, textColor=colors.HexColor("#1F2937"), backColor=colors.HexColor("#EFF6FF"), borderPadding=6, spaceBefore=4, spaceAfter=6))

story = []
md    = []


def clean_md(text):
    return text.replace("<b>", "**").replace("</b>", "**").replace("<br/>", "\n")


def p(text, style="Bodyx"):
    story.append(Paragraph(text, styles[style]))
    md.append(clean_md(text) + "\n")


def h1(text):
    story.append(Paragraph(text, styles["H1x"]))
    md.append("\n# " + text + "\n")


def h2(text):
    story.append(Paragraph(text, styles["H2x"]))
    md.append("\n## " + text + "\n")


def bullet(text):
    story.append(Paragraph("- " + text, styles["Bulletx"]))
    md.append("- " + clean_md(text) + "\n")


def code(text):
    story.append(Paragraph(text.replace("\n", "<br/>"), styles["CodexCode"]))
    md.append("```\n" + text + "\n```\n")


def note(text):
    story.append(Paragraph(text, styles["Note"]))
    md.append("> " + clean_md(text) + "\n")


def sp(h=6):
    story.append(Spacer(1, h))


def tbl(headers, rows, widths=None):
    data = [[Paragraph(str(x), styles["TableHead"]) for x in headers]]
    for row in rows:
        data.append([Paragraph(str(x), styles["TableCell"]) for x in row])
    if widths is None:
        widths = [(PAGE_W - 3.2 * cm) / len(headers)] * len(headers)
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("GRID",       (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("LEFTPADDING",    (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 4),
        ("TOPPADDING",     (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 3),
    ]))
    story.append(table)
    story.append(Spacer(1, 6))
    md.append("| " + " | ".join(headers) + " |\n")
    md.append("| " + " | ".join(["---"] * len(headers)) + " |\n")
    for row in rows:
        md.append("| " + " | ".join(str(x).replace("\n", " ") for x in row) + " |\n")


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.drawString(1.6 * cm, 1.0 * cm, "Nexa AI - Viral & Comunidade - V2 - 14/07/2026")
    canvas.drawRightString(PAGE_W - 1.6 * cm, 1.0 * cm, f"Pagina {doc.page}")
    canvas.restoreState()


# ════════════════════════════════════════════════════════
# CAPA
# ════════════════════════════════════════════════════════
story.append(Spacer(1, 4.5 * cm))
story.append(Paragraph("VIRAL & COMUNIDADE", styles["CoverTitle"]))
story.append(Paragraph("Vertical V1-V3 + Comunidade | Nexa AI", styles["CoverSub"]))
story.append(Spacer(1, 0.3 * cm))
story.append(Paragraph("Produto - APIs - Arquitetura - Dados - Growth - Moderacao - Seguranca - LGPD - CDC - CONAR - Open Finance - Testes", styles["CoverSub"]))
story.append(Spacer(1, 1.0 * cm))
story.append(Paragraph("Especificacao consolidada e corrigida a partir do roadmap e do codigo real do repositorio. Versao pronta para revisao tecnica, de produto e juridica.", styles["CoverSub"]))
story.append(Spacer(1, 0.4 * cm))
story.append(Paragraph("Versao 2.0 | 14/07/2026", styles["CoverSub"]))
story.append(PageBreak())
md.append("# VIRAL & COMUNIDADE - NEXA AI - V2\n")

# ════════════════════════════════════════════════════════
h1("0. Controle do documento")
tbl(["Campo", "Valor"], [
    ["Versao", "2.0"],
    ["Data-base", "14/07/2026"],
    ["Escopo", "V1 Savings Card, V2 Wrapped, V3 Ranking e camada de Comunidade"],
    ["Fontes internas", "docs/ROADMAP.md, backend/app/viral, health_score, migrations e frontend-react"],
    ["Status", "Especificacao para validacao; nao substitui parecer juridico"],
], [4.0 * cm, 13.2 * cm])
note("Legenda: IMPLEMENTADO = existe no codigo; PARCIAL = existe tecnicamente, mas o fluxo de produto esta incompleto; PROPOSTO = ainda nao existe; BLOQUEADO = depende de validacao juridica, dados ou infraestrutura.")

h2("0.1 Correcoes incorporadas nesta V2")
for item in [
    "Correcao do CDC art. 39: produto ou servico nao solicitado pertence ao inciso III; o inciso IV trata de vulnerabilidade do consumidor.",
    "Correcao da leitura da LGPD art. 14: regula dados de criancas e adolescentes; nao cria, sozinho, exigencia universal de maioridade.",
    "Separacao entre processamento interno, geracao privada, compartilhamento externo, analytics e publicacao agregada.",
    "Metodologia V3 redesenhada com normalizacao, intervalo de confianca, amostra minima e governanca de versao.",
    "Remocao da afirmacao de que k-anonimato e ruido, isoladamente, garantem anonimato.",
    "Inclusao de comunidade real: feed, desafios, reacoes, moderacao, denuncias, reputacao e governanca.",
    "Correcao das divergencias com o banco real: metadata, tabelas da migration e ausencia atual de testes e frontend viral.",
]:
    bullet(item)

h1("1. Resumo executivo")
tbl(["Capacidade", "Objetivo", "Estado real", "Proxima decisao"], [
    ["V1 Savings Card", "Gerar card compartilhavel de economia potencial", "PARCIAL: JSON e SVG existem", "Disclaimer, share, PNG, consentimento e analytics"],
    ["V2 Wrapped", "Resumo anual com cinco highlights", "PARCIAL: JSON e SVG existem", "Fallback, badges visuais, scheduler e notificacao"],
    ["V3 Ranking", "Relatorio trimestral publico por instituicao", "PROPOSTO / BLOQUEADO", "Validar metodologia, dados, anonimizacao e juridico"],
    ["Comunidade", "Engajamento recorrente e aprendizado coletivo", "NAO EXISTE", "Definir MVP seguro, moderacao e governanca"],
], [3.2 * cm, 4.2 * cm, 4.0 * cm, 5.8 * cm])
note("Tese de crescimento: transformar insights financeiros individuais, comprovaveis e explicaveis em artefatos compartilhaveis, sem expor dados sensiveis e sem apresentar estimativas como resultados realizados.")

h1("2. Estado real do repositorio")
tbl(["Componente", "Constatacao", "Status"], [
    ["backend/app/viral/models.py", "SavingsSource, SavingsCard, WrappedHighlight e WrappedReport", "IMPLEMENTADO"],
    ["backend/app/viral/router.py", "Quatro endpoints JSON/SVG com require_owner", "IMPLEMENTADO"],
    ["savings_consolidator.py", "Agrega optimizer, costs, negotiation_history e opportunity_snapshots", "IMPLEMENTADO"],
    ["wrapped_generator.py", "Gera ate cinco highlights e le badges", "IMPLEMENTADO"],
    ["card_renderer.py", "SVG 1080x1080; sem disclaimer ou PNG", "PARCIAL"],
    ["frontend-react", "Sem pagina Viral, modal, share ou Wrapped", "A CONSTRUIR"],
    ["backend/tests", "Sem suite especifica localizada para viral/wrapped/badges", "A CONSTRUIR"],
    ["Scheduler", "Sem Celery/APScheduler operacional para a vertical", "A CONSTRUIR"],
    ["V3 e Comunidade", "Sem servicos, tabelas, endpoints ou frontend", "A CONSTRUIR"],
], [4.5 * cm, 7.5 * cm, 5.2 * cm])

h2("2.1 Banco de dados confirmado")
tbl(["Tabela", "Uso", "Observacao"], [
    ["bank_fee_history", "V2 e futura defesa", "Criada na migration e1a2b3c4d5f6"],
    ["negotiation_history", "V1 e badges", "potential_gain e result_status"],
    ["opportunity_snapshots", "V1/V2", "top_gain_brl, monthly_loss e captured_at"],
    ["user_badges", "V2/gamificacao", "Coluna real: metadata, nao metadata_json"],
    ["health_score_history", "V2/badges", "Nao e criada pela migration e1a2b3c4d5f6"],
    ["viral_share_log", "Share e CAC", "Nao existe"],
    ["viral_ranking_snapshots", "V3", "Nao existe"],
], [4.5 * cm, 4.5 * cm, 8.2 * cm])

h1("3. Principios obrigatorios")
for item in [
    "Verdade mensuravel: cada numero deve ter origem, periodo, formula e versao rastreaveis.",
    "Estimativa nao e economia realizada: rotulos, textos, schemas e SVGs devem preservar a distincao.",
    "Privacidade por padrao: nenhum compartilhamento externo ocorre automaticamente.",
    "Minimizacao: cards nao exibem CPF, conta, cartao, saldo, transacoes ou identificadores desnecessarios.",
    "Explicabilidade: o usuario consegue abrir a memoria de calculo antes de compartilhar.",
    "Seguranca emocional: evitar medo, vergonha, comparacao toxica ou incentivo a credito/consumo.",
    "Contestabilidade: usuario e instituicao podem reportar erro e solicitar revisao.",
    "Acessibilidade: contraste, texto alternativo, linguagem simples e alternativa textual ao card.",
]:
    bullet(item)

h1("4. V1 - Placar de economia compartilhavel")
h2("4.1 Resultado de produto")
p("O V1 consolida oportunidades financeiras e gera uma visualizacao privada. O usuario revisa o valor, consulta a memoria de calculo, escolhe o formato e somente entao compartilha.")
note("Copy recomendada: 'A Nexa identificou ate R$ X em oportunidades anuais. Potencial estimado; depende das condicoes e das acoes do usuario.'")

h2("4.2 Fontes e regras")
tbl(["Fonte", "Regra atual", "Correcao necessaria"], [
    ["F2 Optimizer", "best_card.net_gain_expected", "Registrar data, cartao-base, premissas e validade"],
    ["F5 Costs", "savings_opportunity x 12", "Separar tarifa real de projecao anual"],
    ["F13 Negotiator", "SUM potential_gain nao recusado", "Evitar somar oportunidades duplicadas ou expiradas"],
    ["OPP", "top_gain_brl x 12", "Definir se campo e mensal; registrar CDI, IR e horizonte"],
], [3.5 * cm, 5.5 * cm, 8.2 * cm])

h2("4.3 API V1 revisada")
tbl(["Endpoint", "Acesso", "Resposta"], [
    ["GET /viral/savings-card/{user_id}", "Dono", "JSON + calculation_version + disclaimer"],
    ["GET /viral/savings-card/{user_id}/svg", "Dono", "SVG privado, sem cache publico"],
    ["GET /viral/savings-card/{user_id}/png", "Dono", "PNG pronto para redes"],
    ["POST /viral/shares", "Dono", "Registra evento, finalidade, canal, versao e UTM"],
    ["DELETE /viral/shares/{id}", "Dono", "Revoga link hospedado quando aplicavel"],
], [6.2 * cm, 2.5 * cm, 8.5 * cm])

h2("4.4 Campos adicionais")
for item in [
    "calculation_version, reference_period_start, reference_period_end e expires_at.",
    "amount_type: estimated_potential, actual_fee ou realized_saving.",
    "disclaimer e calculation_details_url.",
    "share_token opaco, com expiracao, quando houver pagina hospedada.",
    "consent_receipt_id apenas quando a base e o desenho juridico exigirem esse registro.",
]:
    bullet(item)

h1("5. V2 - Wrapped anual")
h2("5.1 Highlights")
tbl(["Highlight", "Natureza", "Criterio minimo"], [
    ["biggest_waste", "Valor historico cobrado", "Ao menos um registro validado no ano"],
    ["worst_fee", "Maior tarifa individual", "Informar banco, tipo, mes e fonte"],
    ["best_card_missed", "Estimativa", "Premissas e ganho anual >= R$ 50"],
    ["idle_money", "Estimativa", "Snapshot valido e periodo de referencia"],
    ["score_evolution", "Indicador Nexa", "Dois pontos comparaveis no ano"],
], [4.0 * cm, 4.0 * cm, 9.2 * cm])

h2("5.2 Regras de experiencia")
for item in [
    "Com menos de tres meses, exibir versao educativa e nao simular um ano cheio sem aviso.",
    "Separar visualmente valores cobrados, potenciais estimados e economia comprovadamente realizada.",
    "Geracao automatica nao implica compartilhamento automatico.",
    "Notificacao deve respeitar preferencias, opt-out, quiet hours e log de entrega.",
    "Cada Wrapped permanece reproduzivel por calculation_version e snapshot das fontes.",
]:
    bullet(item)

h1("6. Gamificacao responsavel")
tbl(["Grupo", "Badges", "Controle"], [
    ["Ativacao", "PRIMEIRO_INSIGHT", "Nao expor dados sensiveis"],
    ["Consistencia", "3_MESES_VERDE, 6_MESES_VERDE", "Nao punir sazonalidade ou renda irregular"],
    ["Acao", "NEGOCIADOR, DEFENSOR, PORTABILIDADE", "Premiar acao informada, nao confronto"],
    ["Valor", "ECONOMIZOU_100/500/1000/5000", "Rotular potencial versus realizado"],
    ["Participacao", "VIRAL_SHARE", "Nao incentivar spam ou compartilhamento excessivo"],
], [3.5 * cm, 6.5 * cm, 7.2 * cm])
note("Badges nunca devem influenciar score de credito, elegibilidade bancaria ou recomendacoes financeiras. O usuario deve poder ocultar badges e sair de desafios.")

h1("7. V3 - Relatorio publico de indicadores bancarios")
h2("7.1 Posicionamento seguro")
p("Nome recomendado: <b>Observatorio Nexa de Tarifas, Juros e Resolucao</b>. Evitar o rotulo conclusivo 'banco mais abusivo' ate que fatos, metodologia e revisao juridica sustentem cada afirmacao.")

h2("7.2 Fontes")
tbl(["Fonte", "Dado", "Validacao"], [
    ["Nexa D2/D3/D4", "Achados agregados", "Amostra, duplicidade, qualidade e risco de reidentificacao"],
    ["BACEN taxas", "Taxas por IF/modalidade", "Competencia, CNPJ8, modalidade e schema"],
    ["BACEN reclamacoes", "Indice/posicao oficial", "Confirmar semantica: posicao 1 e direcao do indicador"],
    ["Consumidor.gov.br", "Resolucao e prazo", "Periodo, universo e correspondencia de marca/CNPJ"],
], [4.0 * cm, 4.0 * cm, 9.2 * cm])

h2("7.3 Metodologia revisada")
for item in [
    "Definir universo, janela temporal e unidade de analise antes do calculo.",
    "Normalizar cada indicador para 0-1, documentando direcao, winsorizacao e limites.",
    "Calcular intervalo de confianca; nao ordenar bancos cujos intervalos sejam materialmente sobrepostos sem aviso.",
    "Usar amostra minima definida por analise estatistica e risco de privacidade, nao apenas um numero fixo arbitrario.",
    "Executar testes de sensibilidade dos pesos e publicar metodologia versionada antes do ranking.",
    "Tratar indicador ausente com regra publica; nunca substituir silenciosamente por zero.",
    "Realizar revisao humana, juridica e de qualidade antes de cada publicacao.",
]:
    bullet(item)
code("score = 100 x soma(peso_i x indicador_normalizado_i) / soma(pesos_disponiveis)\n\nPesos iniciais sao hipoteses de produto e somente podem virar ranking\napos validacao estatistica, juridica e editorial.")

h2("7.4 Privacidade e publicacao")
for item in [
    "Supressao de identificadores diretos e indiretos no resultado.",
    "Avaliacao de singularidade, vinculabilidade e inferencia; teste de reidentificacao antes da publicacao.",
    "Protecao contra diferenca entre versoes/trimestres e contra grupos pequenos.",
    "Ruido estatistico somente com sensibilidade, clipping, epsilon, composicao e utilidade documentados.",
    "RIPD/DPIA, registro das decisoes, politica de retencao e aprovacao do encarregado/juridico.",
]:
    bullet(item)

h1("8. Comunidade - escopo completo")
h2("8.1 Objetivo")
p("Criar aprendizado financeiro coletivo sem transformar o produto em aconselhamento entre desconhecidos, exposicao de dados pessoais ou competicao por consumo e credito.")

h2("8.2 MVP recomendado")
tbl(["Funcao", "MVP", "Risco/controle"], [
    ["Feed educativo", "Posts Nexa e especialistas verificados", "Revisao editorial e fontes"],
    ["Reacoes", "Util, aprendi, quero entender", "Sem contagem publica manipulavel no inicio"],
    ["Desafios", "Reduzir tarifa, revisar assinatura, formar reserva", "Opt-in; sem ranking por patrimonio"],
    ["Relatos", "Templates estruturados e pseudonimos", "Moderacao e remocao de dados pessoais"],
    ["Perguntas", "Pergunta e resposta com avisos", "Nao substituir profissional habilitado"],
    ["Denuncia", "Reportar spam, fraude, assedio e dado pessoal", "SLA e trilha de decisao"],
], [3.5 * cm, 5.5 * cm, 8.2 * cm])

h2("8.3 Fora do MVP")
for item in [
    "Mensagens privadas, grupos fechados e upload livre de documentos financeiros.",
    "Ranking por saldo, renda, score, investimento ou economia.",
    "Recomendacao de ativos ou produtos por usuarios sem controles de suitability e publicidade.",
    "Venda, afiliacao ou captacao de clientes dentro da comunidade.",
]:
    bullet(item)

h2("8.4 Entidades e APIs")
tbl(["Entidade", "Campos essenciais"], [
    ["community_posts", "id, author_type, pseudonym_id, body, topic, status, created_at"],
    ["community_reactions", "post_id, user_id_hash, reaction_type, created_at"],
    ["community_reports", "content_id, reporter_id, reason, evidence, status, decided_at"],
    ["community_moderation_log", "content_id, rule_version, action, reason, actor, timestamp"],
    ["community_challenges", "title, behavior, start/end, eligibility, privacy_mode"],
    ["community_memberships", "user_id, pseudonym_id, terms_version, joined_at, status"],
], [4.8 * cm, 12.4 * cm])

h2("8.5 Moderacao e governanca")
for item in [
    "Regras publicas: fraude, assedio, discriminacao, dados pessoais, spam, publicidade e desinformacao financeira.",
    "Moderacao em camadas: filtros preventivos, fila humana, recurso e auditoria.",
    "SLA por gravidade e protocolo de preservacao de evidencia.",
    "Canal de recurso para autores e canal juridico para ordens validas.",
    "Relatorio de transparencia com volume de denuncias, remocoes, recursos e tempo de resposta.",
]:
    bullet(item)

h1("9. Framework juridico e regulatorio")
note("Esta secao organiza requisitos de engenharia e produto. A aplicacao ao caso concreto e a aprovacao de textos publicos exigem revisao juridica externa.")

h2("9.1 LGPD")
tbl(["Tema", "Requisito de produto/engenharia"], [
    ["Finalidade e base legal", "Mapear separadamente geracao privada, share, analytics, notificacao, comunidade e V3"],
    ["Consentimento", "Quando usado: livre, informado, inequivoco, granular, comprovavel e revogavel"],
    ["Criancas/adolescentes", "Melhor interesse, politica de idade e controles proporcionais; art. 14 nao equivale a maioridade obrigatoria"],
    ["Direitos", "Acesso, correcao, exclusao, oposicao/revogacao e informacao sobre compartilhamentos"],
    ["Anonimizacao", "Avaliar reversibilidade e risco real; art. 12 nao cria salvo-conduto automatico"],
    ["Seguranca", "Controle de acesso, criptografia, logs, retencao, resposta a incidentes e fornecedores"],
], [4.5 * cm, 12.7 * cm])

h2("9.2 CDC e publicidade")
tbl(["Dispositivo", "Aplicacao"], [
    ["Art. 6o, III", "Informacao adequada, clara e suficiente sobre calculo e limitacoes"],
    ["Art. 37", "Nao apresentar estimativa como economia realizada; substanciar afirmacoes objetivas"],
    ["Art. 39, III", "Nao fornecer/enviar produto ou servico sem solicitacao"],
    ["Art. 39, IV", "Nao explorar fraqueza ou ignorancia por idade, saude, conhecimento ou condicao social"],
], [4.0 * cm, 13.2 * cm])

h2("9.3 CONAR, Marco Civil e comunidade")
for item in [
    "Substanciar valores, percentuais e rankings antes da comunicacao publica.",
    "Distinguir conteudo produzido pela Nexa de conteudo de terceiros; o art. 19 do Marco Civil nao elimina deveres proprios sobre cards gerados pela plataforma.",
    "Criar fluxo juridico para ordens, identificacao de URL/conteudo, preservacao e remocao.",
    "Politica de publicidade e influenciadores deve proibir recomendacao disfarcada e conflito de interesses.",
]:
    bullet(item)

h2("9.4 Open Finance")
for item in [
    "Documentar papeis de Nexa, Pluggy, instituicao transmissora e receptora.",
    "Nao presumir que autorizacao de Open Finance autoriza publicacao de derivados.",
    "Respeitar finalidade, prazo, revogacao e contratos aplicaveis.",
    "Validar Res. Conjunta 1/2020, Res. BCB 32/2020 e alteracoes vigentes antes do lancamento.",
]:
    bullet(item)

h1("10. Arquitetura alvo")
tbl(["Camada", "Componentes"], [
    ["API privada", "V1/V2, memoria de calculo, PNG, preferencias e shares"],
    ["API publica", "V3 versionado, metodologia, correcoes e health endpoint"],
    ["Servicos", "Consolidator, Wrapped, Renderer, Ranking, Privacy, Moderation e Share"],
    ["Jobs", "Wrapped anual, ranking trimestral, expiracao, notificacoes e moderacao"],
    ["Dados", "Snapshots imutaveis, shares, ranking, comunidade e logs de decisao"],
    ["Infra", "PostgreSQL, Redis, Celery/beat, storage, CDN privada/publica e observabilidade"],
], [3.5 * cm, 13.7 * cm])

h2("10.1 Controles de seguranca")
for item in [
    "require_owner em recursos privados e tokens opacos em links compartilhados.",
    "Rate limiting, protecao contra scraping, enumeracao e abuso dos endpoints publicos.",
    "Escape de texto no SVG, CSP, content-type correto e proibicao de conteudo ativo externo.",
    "Criptografia em transito e repouso; segregacao de dados identificados e agregados.",
    "Logs sem dados financeiros desnecessarios; alertas de acesso anomalo.",
    "Threat modeling para share, comunidade, moderacao e pipeline V3.",
]:
    bullet(item)

h1("11. Modelo de dados novo")
tbl(["Tabela", "Finalidade", "Retencao inicial"], [
    ["viral_share_log", "Analytics, prova de versao e canal", "Definir com juridico; minimizar user_id"],
    ["viral_calculation_snapshots", "Reproducao do valor publicado", "Prazo de contestacao + obrigacoes"],
    ["viral_ranking_snapshots", "Ranking trimestral versionado", "Historico publico e correcoes"],
    ["viral_consent_receipts", "Prova quando consentimento for base", "Enquanto necessario para prova/defesa"],
    ["community_*", "Conteudo, reacoes, denuncias e moderacao", "Por classe e finalidade"],
], [5.0 * cm, 5.5 * cm, 6.7 * cm])
note("Prazos acima sao categorias de decisao, nao valores finais. A politica de retencao deve considerar finalidade, minimizacao, obrigacoes legais, defesa de direitos e expectativa do titular.")

h1("12. Testes e criterios de aceite")
tbl(["Area", "Criterios obrigatorios"], [
    ["V1 calculo", "Fontes positivas/zero, excecoes, duplicidade, expiracao, arredondamento e rastreabilidade"],
    ["V1/V2 render", "SVG/PNG valido, acentos, texto longo, zero dados, disclaimer, contraste e sem injection"],
    ["Autorizacao", "Usuario A nao acessa B; token expirado; revogacao; cache invalidado"],
    ["V2", "12 meses, menos de 3 meses, fontes faltantes, periodos e tipos de valores"],
    ["V3", "Normalizacao, direcao, missing, pesos, intervalos, amostra, reproducao e correcao"],
    ["Privacidade", "Ataques de diferenca, grupos pequenos, inferencia, logs e exclusao"],
    ["Comunidade", "Spam, assedio, PII, denuncia, recurso, bloqueio e auditoria"],
    ["Resiliencia", "Timeout BACEN, retry, cache anterior, idempotencia e job duplicado"],
], [3.5 * cm, 13.7 * cm])

h2("12.1 Definicao de pronto")
for item in [
    "Testes unitarios, integracao e E2E aprovados; cobertura da vertical acompanhada.",
    "Revisao de seguranca e privacidade concluida.",
    "Copy e disclaimers aprovados por produto e juridico.",
    "Dashboards, alertas, rollback e runbook operacional disponiveis.",
    "Metodologia e fontes publicadas antes do V3.",
]:
    bullet(item)

h1("13. Metricas")
tbl(["Dimensao", "Metrica", "Protecao"], [
    ["Viral", "share rate, conversao UTM e novos usuarios", "Nao incentivar spam"],
    ["Valor", "potencial identificado e economia confirmada", "Medir separadamente"],
    ["Qualidade", "erro/contestacao e reproducibilidade", "Meta de reducao continua"],
    ["Privacidade", "opt-out, incidentes e grupos suprimidos", "Sem meta que pressione divulgacao"],
    ["Comunidade", "conteudo util, denuncias e SLA", "Nao usar tempo de tela como unico norte"],
    ["V3", "cobertura, estabilidade e mencoes qualificadas", "Sem sacrificar rigor por alcance"],
], [3.5 * cm, 6.5 * cm, 7.2 * cm])

h1("14. Plano de implementacao")
tbl(["Fase", "Entregas", "Gate"], [
    ["0 - Correcoes", "Copy, disclaimer, schemas, testes basicos e docs", "Revisao tecnica/produto"],
    ["1 - V1", "Pagina, memoria de calculo, PNG, share, UTM e log", "Privacidade + seguranca"],
    ["2 - V2", "Fallback, badges, scheduler, notificacoes e E2E", "Operacao e preferencia"],
    ["3 - Comunidade beta", "Feed curado, reacoes, desafios e denuncia", "Moderacao e termos"],
    ["4 - V3 fechado", "Pipeline, metodologia, teste de reidentificacao e contestacao", "Juridico + estatistica"],
    ["5 - V3 publico", "Metodologia, relatorio, press kit e plano de crise", "Aprovacao executiva"],
], [3.5 * cm, 8.5 * cm, 5.2 * cm])

h1("15. Backlog priorizado")
tbl(["Prioridade", "Entrega"], [
    ["P0", "Corrigir copies e adicionar disclaimer em V1/V2; criar testes de regressao"],
    ["P0", "Adicionar calculation_version, amount_type, periodos e memoria de calculo"],
    ["P0", "Definir bases legais/finalidades e fluxo de privacidade com juridico"],
    ["P1", "Frontend V1/V2, PNG, Web Share, UTM e viral_share_log"],
    ["P1", "Fallback V2, badges visuais, preferencias e notificacoes"],
    ["P2", "Celery/beat, idempotencia, observabilidade e runbooks"],
    ["P2", "MVP comunidade com moderacao e denuncia"],
    ["P3", "V3: dados, metodologia estatistica, snapshots e testes de privacidade"],
    ["P4", "V3 publico somente apos gates juridico, estatistico e editorial"],
], [2.5 * cm, 14.7 * cm])

h1("16. Matriz de rastreabilidade")
tbl(["Requisito", "Codigo atual", "Artefato faltante", "Teste"], [
    ["V1 JSON/SVG", "viral/router.py e services", "Disclaimer/schema", "Unit + API + render"],
    ["V1 share", "Nao existe", "Frontend, POST shares e tabela", "E2E + seguranca"],
    ["V2", "wrapped_generator.py", "Fallback/scheduler/frontend", "Unit + job + E2E"],
    ["Badges", "badge_service.py", "5 badges e regras revisadas", "Limites e idempotencia"],
    ["V3", "Nao existe", "Pipeline completo", "Dados + estatistica + privacy"],
    ["Comunidade", "Nao existe", "Modulo completo", "Moderacao + abuso + E2E"],
], [3.5 * cm, 4.0 * cm, 4.5 * cm, 5.2 * cm])

h1("17. Fontes oficiais")
tbl(["Fonte", "URL"], [
    ["LGPD - Lei 13.709/2018", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm"],
    ["CDC - Lei 8.078/1990", "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm"],
    ["Marco Civil - Lei 12.965/2014", "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2014/lei/l12965.htm"],
    ["Res. Conjunta 1/2020 - Open Finance", "https://www.bcb.gov.br/pre/normativos/busca/downloadNormativo.asp?arquivo=/Lists/Normativos/Attachments/51028/Res_Conj_0001_v1_O.pdf"],
    ["Res. BCB 32/2020 e alteracoes", "https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?tipo=Resolucao%20BCB&numero=32"],
    ["FAQ oficial Open Finance", "https://www.bcb.gov.br/meubc/faqs/s/open-finance"],
    ["BACEN Ranking de Reclamacoes", "https://www.bcb.gov.br/ranking/"],
    ["Consumidor.gov.br dados abertos", "https://dados.gov.br/dados/conjuntos-dados/consumidorgovbr"],
    ["CONAR", "https://www.conar.org.br/codigo/codigo.php"],
], [5.5 * cm, 11.7 * cm])

h1("18. Conclusao e gates de lancamento")
p("V1 e V2 possuem base tecnica, mas ainda nao constituem um loop viral de producao. O trabalho imediato e transformar APIs e SVGs em uma experiencia explicavel, privada por padrao, compartilhavel por escolha e mensuravel com seguranca.")
p("V3 deve ser tratado como produto de dados, editorial e juridico, nao apenas como um endpoint. Comunidade deve nascer pequena, curada e moderavel, expandindo somente quando os controles operacionais estiverem comprovados.")
h2("Gates obrigatorios")
for item in [
    "V1/V2: testes, copy, disclaimer, privacidade, frontend, observabilidade e rollback.",
    "Comunidade: termos, regras, denuncia, moderacao, recurso, seguranca e SLA.",
    "V3: metodologia publicada, qualidade dos dados, teste de privacidade, canal de contestacao e aprovacao juridica externa.",
]:
    bullet(item)

h1("19. Plano executivo 30/60/90 dias")
tbl(["Horizonte", "Objetivo", "Saida verificavel"], [
    ["0-30 dias", "Eliminar risco imediato de V1/V2", "Copy corrigida, disclaimer, schema versionado, memoria de calculo e testes"],
    ["31-60 dias", "Fechar o loop viral", "Frontend, PNG, Web Share, UTM, share log, preferencias e observabilidade"],
    ["61-90 dias", "Automacao e comunidade beta", "Scheduler V2, notificacoes, feed curado, reacoes, denuncia e moderacao"],
    ["Apos 90 dias", "Preparar V3 fechado", "Metodologia, pipeline, qualidade, privacidade, contestacao e revisao juridica"],
], [3.0 * cm, 4.5 * cm, 9.7 * cm])

h2("Checklist de aprovacao executiva")
for item in [
    "Produto confirma escopo, copies, metricas e limites de gamificacao.",
    "Engenharia confirma schemas, jobs, idempotencia, observabilidade e capacidade operacional.",
    "Seguranca e privacidade aprovam threat model, retencao, acessos e resposta a incidentes.",
    "Juridico aprova bases legais, termos, disclaimers, comunidade e gates do V3.",
    "Dados valida metodologia, normalizacao, amostra, intervalos e reproducibilidade do V3.",
]:
    bullet(item)
note("Proxima acao recomendada: executar a Fase 0 e abrir uma especificacao tecnica curta para V1, com schema revisado, memoria de calculo e testes. O V3 permanece bloqueado para publicacao ate concluir os gates juridico, estatistico e de privacidade.")

# ════════════════════════════════════════════════════════
OUT.parent.mkdir(parents=True, exist_ok=True)
SimpleDocTemplate(
    str(OUT),
    pagesize=A4,
    rightMargin=1.55 * cm,
    leftMargin=1.55 * cm,
    topMargin=1.55 * cm,
    bottomMargin=1.55 * cm,
).build(story, onFirstPage=footer, onLaterPages=footer)
MD.write_text("\n".join(md), encoding="utf-8")
print(OUT.resolve())
