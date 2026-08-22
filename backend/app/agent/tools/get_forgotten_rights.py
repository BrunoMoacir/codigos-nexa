"""
app/agent/tools/get_forgotten_rights.py — T3 no agente

A tool era um bloco de texto fixo: imprimia as mesmas quatro seções para todo
mundo e nunca chamava os verificadores. Era a terceira implementação paralela
da mesma funcionalidade — com uma terceira política — ao lado do
`app/rights/router.py` (que estimava e somava) e do
`app/fiscal/rights_monitor` (que nunca fabricava). Agora lê os verificadores,
como a tool do D3 passou a ler a referência de mercado do detector.

O que a tool NUNCA imprime é um total a receber. Os sinais heurísticos saem
com o rótulo do que medem — "depósitos estimados", "IRRF retido" — porque
nenhum deles é dinheiro que alguém deve ao usuário.
"""

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def get_forgotten_rights(user_id: str) -> str:
    """
    Verifica direitos financeiros esquecidos: SVR BACEN, FGTS, PIS/PASEP e Restituição IR.

    Use esta ferramenta SEMPRE que o usuário perguntar sobre:
    - "Tenho dinheiro esquecido em algum banco?"
    - "Como verifico meu SVR BACEN / valores a receber?"
    - "Tenho FGTS esquecido de empregos antigos?"
    - "Tenho PIS ou PASEP a receber?"
    - "Como verifico minha restituição do Imposto de Renda?"
    - "Tenho direitos financeiros que esqueci?"
    - Qualquer pergunta sobre dinheiro esquecido ou direitos financeiros não resgatados.

    Args:
        user_id: ID do usuário (obrigatório).
    """
    logger.info("[Tool] get_forgotten_rights | user=%s", user_id)

    direitos = _analisar(user_id)

    lines = [
        "=== MONITOR DE DIREITOS ESQUECIDOS (T3) ===",
        "",
        "A Nexa aponta onde olhar e faz a consulta real onde os canais oficiais permitem.",
        "Nenhum número abaixo é uma promessa de valor a receber.",
        "",
    ]

    if not direitos:
        lines += [
            "Não foi possível analisar suas fontes agora. Verifique diretamente:",
            "• SVR BACEN: valoresareceber.bcb.gov.br (login GOV.BR)",
            "• FGTS: app FGTS da Caixa",
            "• PIS/PASEP: gov.br ou Carteira de Trabalho Digital",
            "• Restituição IR: app Meu Imposto de Renda",
        ]
        return "\n".join(lines)

    _CAPACIDADE = {
        "assisted_real": "✨ CONSULTA REAL NA NEXA (você responde o captcha oficial do BACEN)",
        "authorized_real": "✨ CONSULTA REAL NA NEXA (com token do e-CAC)",
        "guided": "Verificação pelo canal oficial — não existe API para terceiros",
    }

    for i, d in enumerate(direitos, start=1):
        lines.append(f"── {i}. {d.title} ──")
        lines.append(_CAPACIDADE.get(d.capability, ""))
        lines.append(f"Por que olhar: {d.relevance_reason}")
        if d.sinal and d.sinal.valor:
            lines.append(
                f"Sinal (NÃO é valor a receber) — {d.sinal.rotulo}: "
                f"R$ {d.sinal.valor:,.2f}"
            )
            lines.append(f"  Como foi obtido: {d.sinal.base}")
        if d.estimated_amount:
            lines.append(f"VALOR CONFIRMADO em consulta real: R$ {d.estimated_amount:,.2f}")
        if d.warning:
            lines.append(f"⚠️ {d.warning}")
        lines.append(f"Canal oficial: {d.official_channel} — {d.official_url}")
        lines.append("")

    lines += [
        "── O que fazer ──",
        "1. Peça para 'consultar o SVR' — a Nexa responde na hora se existe valor em seu nome.",
        "2. Para a restituição, gere a Autorização de Compartilhamento no e-CAC e cole o token.",
        "3. FGTS e PIS/PASEP só o titular consulta, nos apps oficiais.",
        "⚠️ A Nexa nunca pede sua senha GOV.BR.",
        "",
        "Fonte: BACEN, CEF, BB, Receita Federal.",
    ]

    ganho = _get_total_negotiation_gain(user_id)
    if ganho > 0:
        lines += [
            "",
            f"── Contexto Nexa ──",
            f"O Negociador já identificou R$ {ganho:,.2f} de economia potencial com seus "
            "bancos atuais — esse é um ganho estimado sobre contratos existentes, "
            "diferente dos direitos acima.",
        ]

    return "\n".join(lines)


def _analisar(user_id: str) -> list:
    """Roda os quatro verificadores com uma leitura só do extrato."""
    try:
        from app.rights.services.contexto_transacional import ContextoTransacional
        from app.rights.services.fgts_checker import FgtsChecker
        from app.rights.services.ir_restituicao_checker import IrRestituicaoChecker
        from app.rights.services.pis_pasep_checker import PisPasepChecker
        from app.rights.services.svr_bacen_client import SvrBacenClient
        from app.rights.connectors.serpro_restituicao import SerproRestituicaoConnector
        from app.rights.services.capacidades import anotar_capacidade

        ctx = ContextoTransacional.carregar(user_id)
        serpro_ok = SerproRestituicaoConnector().is_configured
        saida = []
        for checker in (SvrBacenClient(), FgtsChecker(), PisPasepChecker(), IrRestituicaoChecker()):
            try:
                saida.append(anotar_capacidade(checker.check(user_id, ctx), serpro_ok))
            except Exception as exc:
                logger.warning("[Tool] get_forgotten_rights checker: %s", exc)
        return saida
    except Exception as exc:
        logger.warning("[Tool] get_forgotten_rights: %s", exc)
        return []


def _get_total_negotiation_gain(user_id: str) -> float:
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            row = db.execute(
                text(
                    "SELECT COALESCE(SUM(potential_gain), 0)"
                    " FROM negotiation_history WHERE user_id = :uid"
                ),
                {"uid": user_id},
            ).fetchone()
        return float(row[0]) if row else 0.0
    except Exception:
        return 0.0
