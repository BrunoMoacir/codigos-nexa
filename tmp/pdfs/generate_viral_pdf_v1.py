from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


OUT = Path("output/pdf/VIRAL_COMUNIDADE_NEXA_COMPLETO_V1.pdf")
MD  = Path("output/pdf/VIRAL_COMUNIDADE_NEXA_COMPLETO_V1.md")
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


def clean_md(text: str) -> str:
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
    canvas.drawString(1.6 * cm, 1.0 * cm, "Nexa AI - Viral & Comunidade - V1 - 14/07/2026")
    canvas.drawRightString(PAGE_W - 1.6 * cm, 1.0 * cm, f"Pagina {doc.page}")
    canvas.restoreState()


# ════════════════════════════════════════════════════════════════════
# CAPA
# ════════════════════════════════════════════════════════════════════
story.append(Spacer(1, 4.5 * cm))
story.append(Paragraph("VIRAL & COMUNIDADE", styles["CoverTitle"]))
story.append(Paragraph("Vertical V1-V3 | Nexa AI", styles["CoverSub"]))
story.append(Spacer(1, 0.3 * cm))
story.append(Paragraph("Savings Card - Wrapped Anual - Ranking de Bancos - Gamificacao - LGPD - CDC - CONAR - APIs - Arquitetura - Testes", styles["CoverSub"]))
story.append(Spacer(1, 1.2 * cm))
story.append(Paragraph("Especificacao tecnica completa: arquitetura, fontes de dados, base legal, riscos juridicos, roadmap e criterios de aceite.", styles["CoverSub"]))
story.append(Spacer(1, 0.4 * cm))
story.append(Paragraph("Gerado em 14/07/2026", styles["CoverSub"]))
story.append(PageBreak())
md.append("# VIRAL & COMUNIDADE - NEXA AI - V1\n")

# ════════════════════════════════════════════════════════════════════
h1("0. Como Ler Este Documento")
p("Este PDF especifica o vertical Viral & Comunidade da Nexa em profundidade tecnica, juridica e de produto. Parte do codigo real existente em <b>backend/app/viral</b>, modelos Pydantic, conectores BACEN/Olinda, router FastAPI e tabelas Alembic. O objetivo e ter um plano completo e acionavel: cada secao define regras de negocio, APIs utilizadas, limites juridicos, modelos de dados e criterios de aceite.")
note("<b>Nota juridica:</b> este documento e especificacao de produto e engenharia. A linguagem do app voltada ao usuario deve sempre distinguir 'economia potencial estimada' de 'economia realizada'. Para V3 (ranking publico de bancos), revisao juridica externa e obrigatoria antes do lancamento.")

h1("1. Resumo Executivo")
tbl(["Tema", "Decisao de Produto"], [
    ["Mecanismo de crescimento", "CAC zero via indignacao financeira: o usuario descobre quanto o banco ganhou dele e compartilha espontaneamente."],
    ["V1 - Savings Card", "Card SVG 1080x1080 compartilhavel com total de economia identificada pela Nexa (4 modulos). Status: implementado."],
    ["V2 - Wrapped Anual", "Relatorio anual estilo Spotify Wrapped com 5 highlights financeiros do ano. Status: implementado."],
    ["V3 - Ranking de Bancos", "Relatorio trimestral publico com ranking anonimizado de bancos mais abusivos. Status: pendente (risco juridico alto)."],
    ["Gamificacao", "7 tipos de badge implementados via BadgeService; exibidos no V2. 5 badges adicionais propostos."],
    ["Risco principal", "Afirmacoes sobre savings sem disclaimer de estimativa violam CDC art. 37 par. 1o. V3 pode gerar acao de concorrencia desleal."],
    ["Prioridade tecnica", "Adicionar disclaimers de estimativa no SVG, consent flow LGPD antes do share, exportacao PNG e scheduler."],
    ["Produto minimo viral", "V1 + V2 ja funcionam; adicionar botao de compartilhamento (Web Share API) e UTM tracking completa o loop viral."],
], [3.4 * cm, 13.8 * cm])

h1("2. Estado Real do Projeto Nexa")
p("O modulo viral existe e esta parcialmente integrado. O router esta registrado em <b>backend/app/api/v1/router.py</b>. Os quatro endpoints ativos retornam JSON e SVG. O que falta para fechar o loop viral e a parte de compartilhamento (frontend), os disclaimers legais nos SVGs e o scheduler para automacao.")
tbl(["Componente", "Existe hoje", "Gaps"], [
    ["app/viral/models.py", "SavingsCard, SavingsSource, WrappedReport, WrappedHighlight — todos implementados.", "Sem campo de consent/share_log; sem campo de disclaimer explicitado no schema."],
    ["app/viral/router.py", "4 endpoints ativos: savings-card JSON/SVG, wrapped JSON/SVG.", "Faltam endpoints V3 (bank-ranking) e /png para exportacao."],
    ["app/viral/services/savings_consolidator.py", "Agrega F2/F5/F13/OPP. Nunca propaga excecao.", "Sem cache por usuario; recalcula inteiro a cada request."],
    ["app/viral/services/wrapped_generator.py", "5 highlights: biggest_waste, worst_fee, best_card_missed, idle_money, score_evolution.", "Sem fallback para usuario com < 3 meses de dados; sem disclaimer por highlight."],
    ["app/viral/services/card_renderer.py", "SVG puro sem dependencias externas, 1080x1080.", "Sem disclaimer de estimativa no SVG; sem exportacao PNG."],
    ["app/health_score/badge_service.py", "7 badges implementados com avaliacao pos-health-score.", "5 badges novos propostos mas nao implementados."],
    ["alembic/e1a2b3c4d5f6", "Tabelas: bank_fee_history, user_badges, opportunity_snapshots, negotiation_history, health_score_history.", "Faltam: viral_ranking_snapshots e viral_share_log."],
    ["V3 ranking", "Nao existe.", "Criar servico de agregacao anonimizada, endpoints e scheduler trimestral."],
], [3.8 * cm, 5.4 * cm, 8.0 * cm])

h1("3. Principios de Produto")
for item in [
    "A Nexa apresenta potencial de economia, nao economia garantida. Todo card e relatorio deve ser rotulado como estimativa.",
    "O loop viral funciona pela emocao real de indignacao: o usuario deve ver quanto o banco ganhou dele, nao valores hipoteticos.",
    "Compartilhamento e sempre opt-in. Nenhum dado e publicado sem acao explicita e consentimento LGPD registrado.",
    "V3 (ranking publico) so existe se a metodologia for transparente, corroborada por dados BACEN publicos e revisada juridicamente.",
    "Gamificacao deve reforcar comportamento financeiro saudavel, nao consumo de credito ou produtos bancarios.",
    "Cards nao devem conter CPF, saldo de conta, numero de cartao ou qualquer dado individualizador. Apenas valores agregados.",
    "O valor exibido no card V1 e sempre anualizado (projecao de 12 meses) para maximizar impacto — isso deve estar explicito.",
]:
    bullet(item)

h1("4. V1 - Placar de Economia Compartilhavel")
h2("4.1 Descricao e Hook")
p("O V1 gera um card grafico (SVG 1080x1080) com a soma de economia identificada por 4 modulos Nexa. O hook e simples e poderoso: o usuario ve um numero grande e quer mostrar para alguem.")
code('Hook: "O Bradesco ganhou R$ 3.200 de mim em 2025. E voce?"')
p("O card e gerado sob demanda via GET /api/v1/viral/savings-card/{user_id}/svg. Sem cron necessario — e sempre atualizado no momento da requisicao.")

h2("4.2 Fontes de Dados")
tbl(["Modulo", "Servico / Query", "Campo", "Formula"], [
    ["F2 Optimizer", "optimizer.queries.get_optimization_reports(user_id)", "best_card.net_gain_expected", "Valor ja em R$/ano; ganho liquido esperado em cashback/pontos."],
    ["F5 Raio-X Tarifas", "costs.bank_fee_analyzer.BankFeeAnalyzer.analyze(df, user_id)", "savings_opportunity x 12", "Tarifas desnecessarias por mes x 12 meses."],
    ["F13 Negociador", "SELECT SUM(potential_gain) FROM negotiation_history WHERE user_id = ? AND result_status != 'recusado'", "SUM(potential_gain)", "Soma de todos os ganhos potenciais de negociacoes pendentes/nao recusadas."],
    ["OPP Radar", "SELECT top_gain_brl, top_opportunity FROM opportunity_snapshots WHERE user_id = ? ORDER BY captured_at DESC LIMIT 1", "top_gain_brl x 12", "Dinheiro parado na conta por mes (mais recente) x 12 meses."],
], [2.5 * cm, 5.5 * cm, 3.8 * cm, 5.4 * cm])
note("<b>Regra de composicao:</b> apenas sources com annual_savings_brl > 0 aparecem no card. O total e a soma de todos os sources positivos. Se todos forem zero (usuario novo), exibir mensagem de incentivo ao inves de R$ 0.")

h2("4.3 Fluxo de dados")
code("GET /api/v1/viral/savings-card/{user_id}\n  -> SavingsConsolidator.consolidate(user_id)\n      -> _optimizer_saving()   # ultimo relatorio\n      -> _costs_saving()       # BankFeeAnalyzer\n      -> _negotiator_saving()  # DB negotiation_history\n      -> _opportunities_saving() # DB opportunity_snapshots\n  <- SavingsCard (JSON)\n\nGET /api/v1/viral/savings-card/{user_id}/svg\n  -> get_savings_card() (JSON acima)\n  -> CardRenderer.render_savings_card(card)\n  <- SVG string (image/svg+xml)")

h2("4.4 Schema JSON de resposta")
code('{\n  "user_id":                  "uuid",\n  "generated_at":             "2026-07-14T10:00:00Z",\n  "total_annual_savings_brl": 3847.20,\n  "months_active":            8,\n  "tagline":                  "A Nexa te ajudou a guardar R$ 3.847,20 em 8 mes(es).",\n  "sources": [\n    { "name": "Otimizador de Cartoes", "module": "optimizer",\n      "annual_savings_brl": 1200.00,\n      "description": "Cartao Nubank Ultravioleta: ganho liquido R$ 1.200/ano..." },\n    { "name": "Raio-X de Tarifas", "module": "costs", ... },\n    { "name": "Negociador",         "module": "negotiator", ... },\n    { "name": "Radar de Oportunidades", "module": "opportunities", ... }\n  ]\n}')

h2("4.5 Card SVG - Layout")
tbl(["Elemento", "Posicao/Font", "Valor tipico"], [
    ["Logotipo NEXA", "x=60 y=120 / Arial 36 bold / cor #8B93FF", "Branding fixo."],
    ["Headline", "x=60 y=220 / Arial 40 / branco", "'A Nexa te ajudou a guardar'"],
    ["Total em destaque", "x=60 y=340 / Arial 96 bold / #4ADE80 (verde)", "R$ 3.847,20"],
    ["Subtitulo meses", "x=60 y=400 / Arial 28 / #A0A8FF", "em 8 mes(es) de uso"],
    ["Linha divisoria", "y=460 / cor #3B4080", "Separador visual"],
    ["Ate 4 sources", "y=520..700 / Arial 26 / nome #C8CCFF / valor verde", "Optimizer / Custos / Negociador / OPP"],
    ["Tagline", "y=1000 / Arial 22 / #6B72A8", "Mensagem personalizada"],
    ["URL Nexa", "y=1040 / Arial 18 / #4A4F80", "nexa.app"],
    ["FALTANTE: disclaimer", "y=1060 / Arial 11 / cinza", "'Potencial estimado. Resultado depende de acao do usuario.'"],
], [4.0 * cm, 6.0 * cm, 7.2 * cm])

h2("4.6 Pendencias V1")
tbl(["#", "Item", "Prioridade", "Esforco"], [
    ["1", "Adicionar disclaimer de estimativa no SVG (linha y=1060)", "Alta (CDC)", "1 dia"],
    ["2", "Consent flow LGPD antes do primeiro share (modal + registro em user_settings)", "Alta (LGPD)", "2 dias"],
    ["3", "Exportacao PNG via canvas browser-side (SVG -> PNG para Stories iOS/Android)", "Media", "1 semana"],
    ["4", "Botao de compartilhamento Web Share API (WhatsApp, Instagram, link)", "Media", "3 dias"],
    ["5", "UTM tracking no link compartilhado: ?utm_source=viral&utm_medium=card_v1&utm_campaign=share", "Media", "1 dia"],
    ["6", "Cache de savings card por usuario (invalida apos health score recalcular)", "Baixa", "2 dias"],
    ["7", "Tabela viral_share_log para analytics de compartilhamento", "Baixa", "1 dia"],
], [0.6 * cm, 7.5 * cm, 3.0 * cm, 2.5 * cm])

h1("5. V2 - Wrapped Anual 'Banco vs. Voce'")
h2("5.1 Descricao e Hook")
p("O V2 e um relatorio anual gerado sob demanda (ou automaticamente em janeiro) com os 5 highlights financeiros mais marcantes do ano. Cada highlight e uma historia curta sobre dinheiro perdido, economizado ou evoluido.")
code('Hook: "Voce perdeu R$ 840 em tarifas que nao deveria ter pago em 2026."')
note("<b>Dependencia critica:</b> o V2 e mais efetivo com 12 meses de dados. Com menos de 3 meses, muitos highlights ficam vazios. O sistema omite automaticamente os highlights sem dados suficientes — mas o produto so atinge o maximo impacto viral em janeiro do ano seguinte.")

h2("5.2 Os 5 Highlights")
tbl(["Categoria", "Titulo", "Fonte de dados", "Query-chave", "Exibe se..."], [
    ["biggest_waste", "Maior desperdicio do ano", "DB bank_fee_history", "GROUP BY fee_type ORDER BY SUM(amount) DESC LIMIT 1 no intervalo ano-01 a ano-12", "Existe pelo menos 1 registro no ano."],
    ["worst_fee", "Tarifa mais absurda", "DB bank_fee_history", "MAX(amount) por bank_name + fee_type no ano", "Existe pelo menos 1 registro no ano."],
    ["best_card_missed", "Cartao que mais renderia", "optimizer.queries.get_optimization_reports()", "best_card.net_gain_expected do relatorio mais recente", "Ganho estimado >= R$ 50/ano."],
    ["idle_money", "Dinheiro parado na conta", "DB opportunity_snapshots", "monthly_loss do snapshot mais recente x 12", "monthly_loss > 0."],
    ["score_evolution", "Sua saude financeira", "DB health_score_history", "Primeiro e ultimo registro do ano (EXTRACT YEAR)", "Pelo menos 2 pontos no ano."],
], [3.2 * cm, 3.5 * cm, 3.5 * cm, 4.0 * cm, 3.0 * cm])

h2("5.3 Schema JSON de resposta")
code('{\n  "user_id":                   "uuid",\n  "year":                      2026,\n  "generated_at":              "2026-07-14T...",\n  "total_fees_paid_year":      1240.00,\n  "total_savings_identified":  3847.20,\n  "score_start":               58,\n  "score_end":                 74,\n  "score_delta":               16,\n  "badges_earned":             ["3_MESES_VERDE", "ECONOMIZOU_500"],\n  "summary_tagline":           "A Nexa identificou R$ 3.847 em oportunidades em 2026...",\n  "highlights": [\n    { "category": "biggest_waste",\n      "title": "Maior desperdicio do ano",\n      "value_formatted": "R$ 480,00",\n      "description": "Voce pagou R$ 480 so em anuidade do cartao em 2026..." }\n    // ... outros 4 highlights\n  ]\n}')
note("<b>Distincao obrigatoria:</b> total_fees_paid_year sao valores COBRADOS (dados reais de transacoes). total_savings_identified sao ESTIMATIVAS de potencial. Misturar sem distingui-los no frontend viola CDC art. 37 par. 1o.")

h2("5.4 Card SVG Wrapped - Layout")
tbl(["Elemento", "Posicao/Font", "Valor tipico"], [
    ["Header NEXA WRAPPED {ano}", "x=60 y=110 / Arial 32 bold / #C39BFF", "NEXA WRAPPED 2026"],
    ["Titulo 'Banco vs. Voce'", "x=60 y=180 / Arial 44 bold / branco", "Banco vs. Voce"],
    ["Linha divisoria", "y=220 / #5B3F8A", "Separador visual"],
    ["Ate 5 highlights (titulo+valor)", "y=290, 420, 550, 680, 810 / Arial 24+42 bold", "Maior desperdicio / R$ 480,00"],
    ["Tagline", "y=980 / Arial 22 / #D9C2FF", "Resumo do ano (truncado 90 chars)"],
    ["URL Nexa", "y=1040 / Arial 18 / #8A6FB0", "nexa.app"],
    ["FALTANTE: badges visuais", "y=820 / icones pequenos", "3_MESES_VERDE / ECONOMIZOU_500"],
    ["FALTANTE: disclaimer", "y=1060 / Arial 11 / cinza", "'Tarifas: valores reais. Savings: estimativas.'"],
], [4.0 * cm, 6.0 * cm, 7.2 * cm])

h2("5.5 Pendencias V2")
tbl(["#", "Item", "Prioridade", "Esforco"], [
    ["1", "Disclaimer distinguindo tarifas cobradas vs. savings estimados no SVG", "Alta (CDC)", "1 dia"],
    ["2", "Cron job: gerar Wrapped automaticamente em 1 de janeiro, 08h00 BRT", "Media", "1 semana + scheduler"],
    ["3", "Notificacao push/email 'Seu Wrapped 2026 esta pronto'", "Media", "3 dias"],
    ["4", "Fallback para usuario com < 3 meses: mensagem educativa em vez de highlights vazios", "Media", "1 dia"],
    ["5", "Badges visuais no SVG (icones/emojis ao lado dos badges_earned)", "Baixa", "2 dias"],
    ["6", "Botao de compartilhamento + UTM tracking", "Media", "2 dias"],
], [0.6 * cm, 7.5 * cm, 3.0 * cm, 2.5 * cm])

h1("6. Gamificacao - Badges e Progressao")
h2("6.1 Badges Implementados")
p("O BadgeService avalia e persiste badges apos cada recalculo de health score. Badges sao idempotentes (ON CONFLICT DO NOTHING). Ficam na tabela <b>user_badges</b> e sao lidos pelo WrappedGenerator._get_badges().")
tbl(["Badge", "Condicao de conquista", "Motivacao de produto"], [
    ["PRIMEIRO_INSIGHT", "Primeiro snapshot de health score registrado.", "Badge de ativacao: recompensa o primeiro uso."],
    ["3_MESES_VERDE", "Health score >= 70 por 3 meses consecutivos.", "Reforco de comportamento saudavel de curto prazo."],
    ["6_MESES_VERDE", "Health score >= 70 por 6 meses consecutivos.", "Reforco de comportamento saudavel de medio prazo."],
    ["NEGOCIADOR", "Pelo menos 1 registro em negotiation_history.", "Recompensa quem agiu apos uma recomendacao Nexa."],
    ["ECONOMIZOU_100", "Potencial de economia acumulado >= R$ 100.", "Primeiro marco de valor percebido."],
    ["ECONOMIZOU_500", "Potencial de economia acumulado >= R$ 500.", "Marco significativo — share organico esperado."],
    ["ECONOMIZOU_1000", "Potencial de economia acumulado >= R$ 1.000.", "Marco premium — viral forte."],
], [3.5 * cm, 5.5 * cm, 8.2 * cm])

h2("6.2 Badges Propostos")
tbl(["Badge", "Condicao proposta", "Tabela/campo necessario"], [
    ["DEFENSOR", "Dossiê D5 gerado pelo menos 1 vez.", "defense_findings: contar WHERE status = 'confirmed'"],
    ["PORTABILIDADE", "Portabilidade D6 solicitada ao banco.", "portability_cases: status = 'submitted'"],
    ["VIRAL_SHARE", "Card V1 ou V2 compartilhado pelo menos 1 vez.", "viral_share_log (tabela a criar)"],
    ["SCORE_RECORD", "Health score atingiu 90 ou mais em qualquer momento.", "health_score_history: MAX(health_score) >= 90"],
    ["ECONOMIZOU_5000", "Potencial de economia acumulado >= R$ 5.000.", "negotiation_history: SUM(potential_gain) >= 5000"],
], [3.5 * cm, 6.5 * cm, 7.2 * cm])

h2("6.3 Arquitetura do BadgeService")
code("class BadgeService:\n    def evaluate_badges(self, user_id, current_score, history) -> list[Badge]:\n        existing = self._get_existing_badges(user_id)  # evita duplicatas\n        new_badges = []\n        if not existing:                             # PRIMEIRO_INSIGHT\n            new_badges.append(Badge('PRIMEIRO_INSIGHT', now))\n        consecutive = _count_consecutive_verde(history)\n        if consecutive >= 6: new_badges.append(Badge('6_MESES_VERDE', now))\n        elif consecutive >= 3: new_badges.append(Badge('3_MESES_VERDE', now))\n        # ... NEGOCIADOR, ECONOMIZOU_*\n        self._persist(user_id, new_badges)           # ON CONFLICT DO NOTHING\n        return new_badges                            # apenas os NOVOS")

h1("7. V3 - Ranking de Bancos Mais Abusivos")
h2("7.1 Descricao e Hook")
p("V3 e o relatorio publico trimestral que classifica bancos por volume e frequencia de cobranças irregulares detectadas entre usuarios Nexa, cruzado com dados publicos do BACEN. E a feature de maior alcance viral e de maior risco juridico.")
code('Hook: "Banco X e o mais caro do Brasil pelo 3o trimestre consecutivo\n— segundo dados do Banco Central e 12.000 usuarios Nexa."')

h2("7.2 Fontes de dados planejadas")
tbl(["Fonte", "Dados", "Acesso", "Restricao LGPD"], [
    ["Base Nexa D1+D2+D3 findings", "Frequencia de achados por banco, valor disputado medio, taxa de resolucao SAC", "DB interno (defense_findings)", "Obrigatorio anonimizar. k-anonimato minimo 50 usuarios por banco."],
    ["BACEN Olinda taxaJuros v2", "Taxas medias mensais por IF e modalidade", "https://olinda.bcb.gov.br/olinda/servico/taxaJuros/versao/v2/odata/TaxasJurosMensalPorMes?$filter=anoMes eq '2026-05'", "Dados publicos — sem restricao."],
    ["BACEN Olinda Tarifas", "Teto de tarifas autorizadas por IF e CNPJ8", "OlindaBankFeeConnector (implementado)", "Dados publicos — sem restricao."],
    ["BACEN Ranking Reclamacoes", "Posicao das IFs por volume de reclamacoes procedentes", "https://www.bcb.gov.br/ranking/ (CSV publico)", "Dados publicos — sem restricao."],
    ["Consumidor.gov.br", "Taxa de resolucao e prazo medio por banco", "Dados abertos do Ministerio da Justica (CSV periodico)", "Dados publicos anonimizados — sem restricao."],
], [3.5 * cm, 4.5 * cm, 5.5 * cm, 4.0 * cm])

h2("7.3 Metodologia de Classificacao")
p("O score final de abusividade de cada banco e calculado como media ponderada de 5 indicadores. Bancos com menos de 50 usuarios Nexa sao excluidos automaticamente.")
tbl(["Indicador", "Peso", "Formula", "Fonte"], [
    ["% usuarios com achado D2 (cobranca indevida)", "30%", "usuarios_com_d2 / total_usuarios_banco", "Nexa D2 findings"],
    ["Multiplo de taxa vs. media BACEN D3", "25%", "taxa_banco / taxa_media_nacional (SGS 20714)", "Olinda taxaJuros + D3"],
    ["% usuarios com achado D4 (aumento unilateral)", "20%", "usuarios_com_d4 / total_usuarios_banco", "Nexa D4 findings"],
    ["Posicao no ranking oficial de reclamacoes BACEN", "15%", "posicao_bacen / total_IFs (normalizado 0-1)", "BACEN ranking publico"],
    ["Taxa de nao-resolucao no SAC (Consumidor.gov)", "10%", "1 - taxa_resolucao_consumidor_gov", "Consumidor.gov dados abertos"],
], [4.5 * cm, 1.5 * cm, 5.5 * cm, 5.7 * cm])
code("score_final = (\n    d2_rate       * 0.30 +\n    d3_multiple   * 0.25 +  # normalizado 0-1 (ex: 1.5x -> 0.5)\n    d4_rate       * 0.20 +\n    bacen_rank_n  * 0.15 +  # 1.0 = pior posicao no ranking\n    nao_resolucao * 0.10\n) * 100  # 0-100, maior = mais abusivo")

h2("7.4 Anonimizacao LGPD")
p("Para que os dados Nexa se enquadrem na excecao de dados anonimizados do Art. 12 da LGPD, a anonimizacao deve ser genuina e tecnicamente robusta.")
tbl(["Tecnica", "Criterio minimo", "Implementacao"], [
    ["k-anonimato", "Minimo 50 usuarios Nexa por banco antes de incluir no ranking", "WHERE sample_size >= 50 antes de publicar resultado"],
    ["Supressao de identificadores", "Nenhum user_id, CPF ou dado individual no resultado final", "GROUP BY bank_name SEM user_id no SELECT"],
    ["Perturbacao de ruido", "Para amostras < 200, adicionar ruido Laplaciano epsilon=0.1 as taxas", "numpy.random.laplace(0, 1/epsilon, size) aplicado a d2_rate e d3_multiple"],
    ["Divulgacao controlada", "Publicar apenas metricas agregadas — nunca findings individuais", "Output: score, d2_rate, d3_multiple, d4_rate — sem details[]"],
    ["Timestamp de geracao", "Publicar data exata da coleta dos dados para rastreabilidade", "Campo generated_at e data_referencia_bacen no JSON"],
], [4.0 * cm, 5.5 * cm, 7.7 * cm])

h2("7.5 Endpoints a criar")
code("GET /api/v1/viral/bank-ranking               # ranking mais recente (publico, sem auth)\nGET /api/v1/viral/bank-ranking/{quarter}    # ex: '2026-Q2' (publico)\nGET /api/v1/viral/bank-ranking/methodology  # disclosure obrigatorio da metodologia (publico)\n\nResposta /bank-ranking:\n{\n  'quarter': '2026-Q2',\n  'generated_at': '2026-07-01T06:00:00Z',\n  'banks': [\n    { 'rank': 1, 'bank_name': '...', 'score': 72.4,\n      'd2_rate': 0.38, 'd3_multiple': 2.1, 'd4_rate': 0.22,\n      'bacen_rank': 3, 'sample_size': 1240 },\n    ...\n  ],\n  'methodology_url': '/api/v1/viral/bank-ranking/methodology',\n  'disclaimer': 'Dados de usuarios Nexa anonimizados + BACEN publico. Nao representa todos os clientes.'\n}")

h2("7.6 Tabela a criar: viral_ranking_snapshots")
code("CREATE TABLE viral_ranking_snapshots (\n  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n  quarter      VARCHAR(7) NOT NULL,     -- '2026-Q3'\n  bank_name    VARCHAR    NOT NULL,\n  cnpj8        VARCHAR(8),\n  score        NUMERIC(5,2),            -- 0.00 a 100.00\n  d2_rate      NUMERIC(5,4),\n  d3_multiple  NUMERIC(5,2),\n  d4_rate      NUMERIC(5,4),\n  bacen_rank   INTEGER,\n  nao_resolucao NUMERIC(5,4),\n  sample_size  INTEGER,\n  generated_at TIMESTAMPTZ DEFAULT now(),\n  UNIQUE(quarter, bank_name)\n);")

h1("8. Framework Legal Completo")
h2("8.1 LGPD - Lei 13.709/2018")
tbl(["Artigo", "Aplicacao no Viral", "Acao tecnica necessaria"], [
    ["Art. 7o, I — Consentimento", "Base legal para compartilhamento de dados financeiros em card publico.", "Modal de consentimento antes do primeiro share. Registrar em user_settings."],
    ["Art. 8o — Forma do consentimento", "Deve ser livre, informado, inequivoco e especifico para a finalidade de compartilhamento.", "Consentimento separado para: (a) gerar card internamente, (b) compartilhar externamente."],
    ["Art. 12 — Dados anonimizados", "Dados anonimizados ficam fora do escopo da LGPD. Permite V3 com anonimizacao genuina.", "Implementar k-anonimato + supressao + perturbacao antes de publicar ranking V3."],
    ["Art. 14 — Menores", "Verificar maioridade antes de processar dados financeiros.", "Verificacao de idade no onboarding (ja implicita em servicos financeiros PF)."],
    ["Art. 18, I-IX — Direitos do titular", "Usuario pode acessar, corrigir, excluir dados que aparecem no card.", "Endpoint de exclusao de historico; garantir que card nao seja cacheado apos opt-out."],
    ["Art. 46 — Seguranca", "Medidas tecnicas de protecao dos dados pessoais usados para gerar o card.", "Card nao pode conter CPF, saldo, numero de cartao. Apenas valores agregados."],
], [3.5 * cm, 5.5 * cm, 8.2 * cm])

h2("8.2 CDC - Codigo de Defesa do Consumidor")
tbl(["Dispositivo", "Risco para Viral", "Mitigacao obrigatoria"], [
    ["Art. 6o, III — Direito a informacao adequada", "Valores no card devem ser reais ou claramente identificados como estimativa.", "Label obrigatorio: 'Potencial estimado - nao garantido'"],
    ["Art. 37, par. 1o — Publicidade enganosa", "Mostrar 'R$ 3.200 economizados' sem dizer que e estimativa e enganoso.", "Sempre usar 'identificados', 'potencial de' ou 'estimativa de', nunca 'economizados' como fato."],
    ["Art. 37, par. 2o — Publicidade abusiva", "Usar medo excessivo ('voce esta perdendo dinheiro todo mes') pode ser abusivo.", "Linguagem factual: 'Detectamos R$ X em cobranças acima da media'. Evitar alarmismo."],
    ["Art. 39, IV — Enviar produto sem solicitacao", "Enviar cards ou relatorios sem acao explicita do usuario.", "Wrapped automatico so com notificacao previa e opt-out disponivel."],
], [3.5 * cm, 5.5 * cm, 8.2 * cm])

h2("8.3 CONAR - Autorregulamentacao Publicitaria")
p("O Codigo CONAR exige <b>substantiacao previa</b>: toda afirmacao de natureza objetiva (valores, percentuais, rankings) deve ser comprovada antes da publicacao. Para V1 e V2, o valor do card deve derivar diretamente dos dados do usuario. Para V3, a metodologia deve estar disponivel publicamente antes da divulgacao do ranking.")
for item in [
    "V1: os valores de cada source devem ser rastreados ao dado de origem (optimizer_reports, bank_fee_history, etc.). Documentar a trilha de calculo.",
    "V2: highlights com valores como 'Maior desperdicio do ano' devem citar explicitamente o tipo de tarifa e o banco.",
    "V3: publicar pagina de metodologia (/bank-ranking/methodology) antes do lancamento do ranking.",
    "Todos: salvar versao de cada card gerado para poder comprovar o dado em caso de questionamento.",
]:
    bullet(item)

h2("8.4 Marco Civil da Internet - Lei 12.965/2014")
p("O Art. 19 protege plataformas intermediarias de responsabilidade por conteudo gerado por usuarios. O card viral e gerado pela Nexa, nao pelo usuario — portanto a Nexa e diretamente responsavel pelo conteudo dos cards. O compartilhamento posterior pelo usuario nao transfere essa responsabilidade.")

h2("8.5 Open Finance - Res. BCB 32/2020")
p("Dados vindos do Open Finance via Pluggy tem regras especificas de compartilhamento. O consentimento para uso dos dados do Open Finance nao implica automaticamente consentimento para compartilhar derivados publicamente. O modal de consentimento do V1/V2 deve ser especifico sobre isso.")

h1("9. Riscos Juridicos - V3 Ranking Publico")
tbl(["Risco", "Base juridica", "Probabilidade", "Impacto", "Mitigacao"], [
    ["Acao de concorrencia desleal por banco listado", "Lei 9.279/1996, art. 195, I — publicar afirmacao falsa em detrimento de concorrente", "Media", "Alto", "Dados BACEN publico + metodologia aberta + linguagem factual sem adjetivos ('maior frequencia de cobranças' vs. 'banco mais abusivo')"],
    ["Responsabilidade civil por dano a reputacao", "Codigo Civil arts. 186/187 — ato ilicito e abuso de direito", "Baixa", "Alto", "Revisao juridica pre-lancamento + canal de contestacao para bancos + erro maximo documentado"],
    ["Reclamacao CONAR por publicidade enganosa", "CONAR — substantiacao previa nao atendida", "Baixa", "Medio", "Publicar metodologia antes do ranking + citar fontes BACEN para cada indicador"],
    ["ANPD — uso indevido de dados pessoais no ranking", "LGPD Art. 12 — anonimizacao insuficiente", "Media", "Alto", "k-anonimato >= 50 + perturbacao de ruido + supressao de identificadores + auditoria interna"],
    ["Erros de dados por amostra insuficiente", "Nenhum especifico — risco operacional e reputacional", "Alta", "Medio", "Filtro sample_size >= 50 + revisao manual antes de publicar + versao beta com aviso"],
    ["Injuncao judicial pre-lancamento", "Possivel liminar em acao cautelar do banco", "Baixa", "Alto", "Lancamento em beta fechado + disclaimers fortes antes de comunicacao massiva"],
], [3.8 * cm, 3.5 * cm, 2.0 * cm, 1.5 * cm, 6.4 * cm])
note("<b>Precedente favoravel:</b> o proprio BACEN publica oficialmente o Ranking de Instituicoes com Mais Reclamacoes (bcb.gov.br/ranking). A Nexa basicamente replica e enriquece informacao que o regulador ja torna publica — isso fortalece a defesa de que o ranking V3 e de interesse publico e jornalistico.")

h1("10. Arquitetura Tecnica")
h2("10.1 Modulos e responsabilidades")
tbl(["Modulo", "Arquivo", "Responsabilidade"], [
    ["SavingsConsolidator", "app/viral/services/savings_consolidator.py", "Agrega economia de 4 modulos. Retorna sources + total. Nunca propaga excecao."],
    ["WrappedGenerator", "app/viral/services/wrapped_generator.py", "Gera 5 highlights do ano, badges e tagline. Cada metodo e independente."],
    ["CardRenderer", "app/viral/services/card_renderer.py", "Renderiza SavingsCard e WrappedReport como SVG puro. Sem dependencias externas."],
    ["BadgeService", "app/health_score/badge_service.py", "Avalia e persiste badges. Chamado apos calculo de health score. Idempotente."],
    ["BankRankingService", "app/viral/services/bank_ranking_service.py (a criar)", "Agrega findings D1/D2/D3/D4 anonimizados + BACEN publico para V3."],
    ["ViralRouter", "app/viral/router.py", "Endpoints FastAPI. Autenticacao require_owner em V1/V2; publico em V3."],
], [3.5 * cm, 5.0 * cm, 8.7 * cm])

h2("10.2 Dependencias entre modulos")
code("V1 SavingsCard\n  |-- F2 optimizer.queries.get_optimization_reports()\n  |-- F5 costs.bank_fee_analyzer.BankFeeAnalyzer\n  |-- F13 DB negotiation_history\n  |-- OPP DB opportunity_snapshots\n\nV2 WrappedReport\n  |-- DB bank_fee_history      (biggest_waste, worst_fee)\n  |-- F2 optimizer reports     (best_card_missed)\n  |-- DB opportunity_snapshots (idle_money)\n  |-- DB health_score_history  (score_evolution)\n  |-- DB user_badges           (badges_earned)\n\nV3 BankRanking (a criar)\n  |-- DB defense_findings      (D2, D3, D4 aggregated)\n  |-- BACEN Olinda taxaJuros   (taxa_media por IF)\n  |-- BACEN Ranking            (reclamacoes publicas)\n  |-- DB viral_ranking_snapshots (cache trimestral)")

h2("10.3 Scheduler (falta implementar)")
tbl(["Job", "Cadencia", "Acao", "Infraestrutura"], [
    ["Wrapped anual automatico", "1o de Janeiro, 08h00 BRT", "Para cada usuario ativo: gerar WrappedReport(user_id, year=ano_anterior) + enviar notificacao", "Celery + celery-beat (Redis ja existe)"],
    ["Ranking trimestral V3", "1o de Jan/Abr/Jul/Out, 06h00 BRT", "Agregar findings D1/D2/D3/D4 anonimizados + BACEN Olinda + salvar em viral_ranking_snapshots", "Celery + celery-beat"],
    ["Invalidacao de cache V1", "Apos cada calculo de health score", "Invalidar cache do savings-card/{user_id} para forcar recalculo na proxima requisicao", "Redis EXPIRE ou event hook"],
], [3.5 * cm, 4.5 * cm, 5.5 * cm, 4.0 * cm])
note("<b>Recomendacao:</b> usar Celery + celery-beat. Redis ja esta na infra. Alternativa mais simples: APScheduler embarcado no FastAPI (menor esforco, menos robusto para multiplas instancias). Em producao com multiplas instancias, Celery e o correto.")

h1("11. Banco de Dados")
tbl(["Tabela", "Campos principais", "Usado por", "Status"], [
    ["bank_fee_history", "user_id, month, bank_name, fee_type, amount", "V2 biggest_waste, worst_fee; D4 baseline", "Criada (migration e1a2b3c4d5f6)"],
    ["negotiation_history", "user_id, bank_name, trigger_type, potential_gain, result_status", "V1 F13; badge NEGOCIADOR; D3", "Criada (migration e1a2b3c4d5f6)"],
    ["opportunity_snapshots", "user_id, monthly_loss, top_gain_brl, top_opportunity, captured_at", "V1 OPP; V2 idle_money", "Criada (migration e1a2b3c4d5f6)"],
    ["health_score_history", "user_id, date, health_score", "V2 score_evolution; badges 3/6 meses verde", "Criada (ORM model)"],
    ["user_badges", "user_id, badge_type, earned_at, metadata_json (UNIQUE user_id+badge_type)", "V2 badges_earned; BadgeService", "Criada (migration e1a2b3c4d5f6)"],
    ["viral_ranking_snapshots", "quarter, bank_name, score, d2_rate, d3_multiple, d4_rate, bacen_rank, sample_size", "V3 ranking trimestral", "A criar (nova migration)"],
    ["viral_share_log", "user_id, share_type, shared_at, card_version, utm_campaign", "Badge VIRAL_SHARE; analytics de CAC viral", "A criar (nova migration)"],
], [4.0 * cm, 5.5 * cm, 4.0 * cm, 3.7 * cm])

h1("12. Testes e Criterios de Aceite")
tbl(["Area", "Casos de teste obrigatorios"], [
    ["V1 SavingsConsolidator", "Todos os 4 sources com valor positivo; todos zerados (usuario novo); 2 sources zerados; excecao no optimizer; excecao no DB; total = soma dos positivos."],
    ["V1 CardRenderer SVG", "SVG valido com total > 0; SVG com 0 sources (usuario novo); caracteres especiais no tagline; total = 0."],
    ["V2 WrappedGenerator", "Usuario com 12 meses de dados (todos os 5 highlights); usuario com 2 meses (highlights vazios omitidos); highlight score_evolution com 1 ponto (omitido); best_card_missed < R$ 50 (omitido)."],
    ["V2 Card SVG Wrapped", "SVG valido com 5 highlights; SVG com 0 highlights; texto longo truncado a 90 chars."],
    ["Badges", "PRIMEIRO_INSIGHT ao criar primeiro score; 3_MESES_VERDE exatamente com 3 meses >= 70; 6_MESES_VERDE com 6; interrompido no 4o mes (nao conquista 6); ECONOMIZOU_1000 exatamente ao atingir."],
    ["V3 Anonimizacao", "Banco com < 50 usuarios Nexa nao aparece no ranking; query de agregacao nao retorna user_id; k-anonimato verificado."],
    ["Seguranca", "Usuario A nao acessa card/wrapped de usuario B (require_owner); V3 endpoint publico funciona sem autenticacao."],
    ["Conectores externos (V3)", "Timeout na Olinda: usar fallback ou excluir indicador com flag; schema diferente: log + skip; BACEN ranking indisponivel: usar cache do trimestre anterior."],
], [3.5 * cm, 13.7 * cm])

h1("13. Metricas de Sucesso")
tbl(["Metrica", "Meta 6 meses", "Como medir"], [
    ["Taxa de share V1 (% de usuarios ativos que compartilham o card)", ">= 15%", "viral_share_log / MAU"],
    ["Novos usuarios via link viral (utm_source=viral)", ">= 20% do total de novos usuarios", "Analytics UTM"],
    ["Valor medio identificado por usuario ativo", ">= R$ 50/mes", "SUM(total_annual_savings_brl) / MAU / 12"],
    ["Taxa de abertura do Wrapped (% de notificados que abrem)", ">= 60%", "notification_delivery_log.status = 'opened'"],
    ["Badges conquistados por usuario medio em 6 meses", ">= 3 badges", "user_badges: COUNT(badge_type) / usuarios"],
    ["Custo de aquisicao via viral", "R$ 0 (organico)", "CAC = 0 para usuarios vindos de link viral"],
    ["V3: cobertura de bancos no ranking (% bancos com sample >= 50)", ">= 10 bancos no primeiro relatorio", "COUNT(DISTINCT bank_name) em viral_ranking_snapshots"],
    ["V3: engajamento da midia/imprensa no lancamento", ">= 3 mencoes na midia especializada", "Monitoramento de marca"],
], [5.0 * cm, 4.5 * cm, 7.7 * cm])

h1("14. Plano de Implementacao")
tbl(["Sprint", "Objetivo", "Entregas"], [
    ["Sprint 2 (atual) - Fechar V1/V2", "Tornar V1/V2 prontos para viral sem risco legal.", "Disclaimer SVG; consent LGPD; Web Share API; UTM tracking; exportacao PNG."],
    ["Sprint 3 - Automacao e Engajamento", "Fechar o loop de retencao via Wrapped e badges.", "Celery scheduler; Wrapped automatico em janeiro; notificacoes; 5 badges novos."],
    ["Sprint 4 - V3 Beta Fechado", "Construir ranking sem risco antes de exposicao publica.", "Migration + servico de agregacao; anonimizacao validada; endpoints; revisao juridica."],
    ["Sprint 5 - V3 Lancamento Publico", "Lancar ranking com cobertura de midia.", "Pagina de metodologia; press kit; monitoramento de resposta dos bancos; plano de crise PR."],
], [3.0 * cm, 5.0 * cm, 9.2 * cm])

h1("15. Backlog Tecnico Detalhado")
tbl(["Prioridade", "Arquivo/Endpoint", "Mudanca"], [
    ["P0", "app/viral/services/card_renderer.py", "Adicionar linha de disclaimer de estimativa no SVG de V1 e V2."],
    ["P0", "app/viral/router.py + frontend", "Implementar consent flow LGPD antes do share (modal + registro em user_settings)."],
    ["P1", "frontend", "Botao de compartilhamento usando Web Share API (WhatsApp, Instagram, link)."],
    ["P1", "frontend", "Exportacao PNG via canvas: SVG -> PNG para Stories iOS/Android."],
    ["P1", "app/viral/router.py", "UTM tracking: adicionar ?utm_source=viral&utm_medium=card_v1 no link compartilhado."],
    ["P1", "app/health_score/badge_service.py", "Adicionar 5 novos badges: DEFENSOR, PORTABILIDADE, VIRAL_SHARE, SCORE_RECORD, ECONOMIZOU_5000."],
    ["P2", "alembic + app/viral/", "Nova migration + tabela viral_share_log para analytics."],
    ["P2", "infra", "Celery + celery-beat: scheduler para Wrapped automatico em 1o de janeiro."],
    ["P2", "app/viral/services/wrapped_generator.py", "Fallback para usuario com < 3 meses de dados (mensagem educativa)."],
    ["P3", "alembic + app/viral/services/bank_ranking_service.py", "Nova migration viral_ranking_snapshots + servico de agregacao anonimizada."],
    ["P3", "app/viral/router.py", "Novos endpoints: /bank-ranking, /bank-ranking/{quarter}, /bank-ranking/methodology."],
    ["P3", "celery tasks", "Job trimestral de geracao do ranking V3."],
    ["P4", "externa", "Revisao juridica da metodologia V3 e dos disclaimers antes do lancamento publico."],
], [2.2 * cm, 5.8 * cm, 9.2 * cm])

h1("16. Fontes e Links Uteis")
tbl(["Fonte", "Link"], [
    ["BACEN Olinda taxaJuros v2", "https://olinda.bcb.gov.br/olinda/servico/taxaJuros/versao/v2/odata/TaxasJurosMensalPorMes"],
    ["BACEN Olinda Tarifas metadata", "https://olinda.bcb.gov.br/olinda/servico/Informes_ListaTarifasPorInstituicaoFinanceira/versao/v1/odata/$metadata"],
    ["BACEN Ranking de Reclamacoes", "https://www.bcb.gov.br/ranking/index.asp"],
    ["Consumidor.gov.br dados abertos", "https://dados.gov.br/dados/conjuntos-dados/consumidorgovbr"],
    ["LGPD - Lei 13.709/2018", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm"],
    ["Codigo de Defesa do Consumidor", "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm"],
    ["CONAR - Codigo de Autorregulamentacao", "https://www.conar.org.br/codigo/codigo.php"],
    ["Marco Civil da Internet", "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2014/lei/l12965.htm"],
    ["Res. BCB 32/2020 - Open Finance", "https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?tipo=Resolucao%20BCB&numero=32"],
    ["Lei de Concorrencia Desleal", "https://www.planalto.gov.br/ccivil_03/leis/l9279.htm"],
], [5.3 * cm, 11.9 * cm])

h1("17. Conclusao")
p("O vertical Viral & Comunidade tem potencial de ser o maior diferencial de crescimento organico da Nexa. V1 e V2 estao implementados e funcionam; o que falta para fechar o loop viral e o botao de compartilhamento, o consent LGPD e os disclaimers de estimativa. V3 tem o maior impacto potencial de alcance e relacoes publicas, mas requer anonimizacao rigorosa, revisao juridica e lancamento gradual para minimizar risco de acao judicial de bancos.")
note("<b>Proxima acao recomendada:</b> Sprint 2 — adicionar disclaimers de estimativa nos SVGs e implementar o consent flow LGPD antes do share. Essas duas acoes eliminam os maiores riscos legais do V1/V2 em producao. Apos isso, o botao de share pode ser ativado com seguranca.")

# ════════════════════════════════════════════════════════════════════
# GERAR PDF + MD
# ════════════════════════════════════════════════════════════════════
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
print(MD.resolve())
