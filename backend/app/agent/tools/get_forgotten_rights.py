# app/agent/tools/get_forgotten_rights.py
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

    # Verifica histórico de negociações para contextualizar
    existing_gains = _get_total_negotiation_gain(user_id)

    lines = [
        "=== MONITOR DE DIREITOS ESQUECIDOS (T3) ===",
        "",
        "Verifique cada fonte abaixo. A Nexa orienta o caminho — o resgate é feito diretamente nos canais oficiais.",
        "",
        "── 1. SVR BACEN — Valores a Receber de Instituições Financeiras ──",
        "O que é: saldos esquecidos em contas bancárias, cheques não sacados, "
        "quotas de consórcio, tarifas cobradas indevidamente e parcelas restituíveis.",
        "✨ CONSULTA REAL NA NEXA: a Nexa verifica NA HORA se existe valor em seu nome "
        "pela consulta pública oficial do BACEN — você só responde o desafio de segurança "
        "(captcha) oficial. Peça para 'consultar o SVR' na tela de Direitos Esquecidos.",
        "Para ver o montante e resgatar: valoresareceber.bcb.gov.br com sua conta GOV.BR.",
        "⚠️ Atenção: nunca forneça senha GOV.BR a terceiros ou apps não oficiais.",
        "",
        "── 2. FGTS — Fundo de Garantia por Tempo de Serviço ──",
        "O que é: saldo de contas FGTS de empregos anteriores (inclusive de empresas extintas).",
        "Como verificar: app FGTS (CEF) ou agências Caixa Econômica Federal com CTPS.",
        "Casos especiais: FGTS de empresas extintas → atendimento presencial na CEF é necessário.",
        "Saque-aniversário: verifique se optou e se a modalidade ainda é vantajosa para seu perfil.",
        "",
        "── 3. PIS / PASEP ──",
        "O que é: cotas do fundo PIS (trabalhador setor privado) ou PASEP (setor público), "
        "especialmente para trabalhadores com carteira assinada antes de 1988.",
        "Como verificar: Banco do Brasil (PASEP) ou Caixa Econômica (PIS) — presencialmente ou pelo app.",
        "Elegibilidade: nascidos até 1971 têm maior probabilidade de cotas esquecidas.",
        "",
        "── 4. Restituição de Imposto de Renda ──",
        "O que é: IR retido na fonte acima do devido, deduzido na declaração anual.",
        "✨ CONSULTA REAL NA NEXA (quando habilitada): gere uma Autorização de "
        "Compartilhamento no e-CAC (Compartilha Receita Federal) e cole o token na Nexa "
        "para ver valor e situação da restituição em tempo real, via API oficial do SERPRO.",
        "Alternativa: app Meu Imposto de Renda (Receita Federal) ou e-CAC.",
        "Restituição retida: se constar 'em análise' há mais de 60 dias, consulte o CPF no site da Receita.",
        "Dedutíveis comuns esquecidos: plano de saúde, despesas médicas, previdência privada (PGBL), dependentes.",
    ]

    if existing_gains > 0:
        lines += [
            "",
            f"── Contexto Nexa ──",
            f"Você já tem R$ {existing_gains:,.2f} de economia potencial identificada pelo Negociador. "
            "Combine isso com os direitos esquecidos acima para maximizar sua recuperação financeira.",
        ]

    lines += [
        "",
        "Fonte: BACEN, CEF, BB, Receita Federal — dados consultados diretamente pelo usuário nos canais oficiais.",
    ]

    return "\n".join(lines)


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
