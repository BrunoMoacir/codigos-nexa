"""
app/negotiator/script_generator.py — F13: Gerador de Roteiro de Negociação

Recebe uma NegotiationOpportunity e chama Claude para gerar um NegotiationScript
personalizado com argumentos concretos, baseado nos dados reais do usuário.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from app.negotiator.models import (
    NegotiationChannel,
    NegotiationOpportunity,
    NegotiationScript,
    NegotiationTrigger,
)

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"

# Prompt de sistema fixo — instrui o Claude a agir como especialista em negociação bancária
_SYSTEM_PROMPT = """\
Você é um especialista em negociação bancária com 15 anos de experiência em
finanças pessoais no Brasil. Sua função é criar roteiros de negociação concisos,
diretos e eficazes para clientes que querem reduzir juros, anuidades ou tarifas
com seus bancos.

Responda EXCLUSIVAMENTE em JSON válido, sem markdown, sem explicações fora do JSON.
O JSON deve seguir exatamente o schema fornecido no prompt do usuário.
"""

_USER_PROMPT_TEMPLATE = """\
Gere um roteiro de negociação bancária com base nos dados abaixo.

=== DADOS DO USUÁRIO ===
Banco: {bank_name}
Produto: {product}
Trigger: {trigger}
Health Score Nexa: {health_score}/100
Meses como bom pagador (sem juros rotativos): {months_as_good_payer}
{fee_line}
{market_line}
{saving_line}
Descrição da oportunidade: {description}

=== SCHEMA ESPERADO (JSON puro, sem markdown) ===
{{
  "opening_line": "<frase de abertura para o gerente/atendente — 1 linha>",
  "key_arguments": [
    "<argumento 1 — dado concreto do usuário>",
    "<argumento 2 — comparação com mercado>",
    "<argumento 3 — histórico positivo>",
    "<argumento 4 — intenção de fidelidade ou ameaça de migração suave>"
  ],
  "target_ask": "<pedido principal objetivo e mensurável>",
  "fallback_ask": "<pedido alternativo caso recusem o principal>",
  "closing_line": "<como encerrar profissionalmente a conversa>",
  "recommended_channel": "<APP_CHAT | TELEFONE | AGENCIA | EMAIL>",
  "best_time": "<ex: terça ou quarta-feira, manhã (9h-11h)>",
  "estimated_success_pct": <inteiro 0-100>,
  "warnings": ["<aviso opcional se houver risco ou limitação>"]
}}

Diretrizes:
- key_arguments deve ter entre 3 e 5 itens
- Use valores em R$ e % concretos quando disponíveis nos dados
- estimated_success_pct deve refletir o health_score e meses como bom pagador
- recommended_channel: prefira APP_CHAT (gera registro escrito) exceto para produtos de crédito complexos
- warnings pode ser lista vazia [] se não houver ressalvas
- NÃO inclua nada fora do JSON
"""


class NegotiationScriptGenerator:
    """
    Gera roteiros de negociação personalizados via Claude.

    Usage:
        generator = NegotiationScriptGenerator()
        script = generator.generate(opportunity)
    """

    def __init__(self, model: str = _MODEL) -> None:
        self._model = model
        import anthropic
        self._client = anthropic.Anthropic()

    def generate(self, opportunity: NegotiationOpportunity) -> NegotiationScript:
        """
        Chama Claude com o contexto da oportunidade e retorna NegotiationScript.

        Em caso de falha na chamada ou parse do JSON, retorna um script padrão
        (fallback) para não bloquear o usuário.
        """
        prompt = self._build_prompt(opportunity)

        try:
            raw_json = self._call_claude(prompt)
            data = json.loads(raw_json)
            return self._parse_script(data, opportunity)
        except json.JSONDecodeError as exc:
            logger.error(
                "NegotiationScriptGenerator | JSON inválido da LLM: %s", exc
            )
            return self._fallback_script(opportunity)
        except Exception as exc:
            logger.error(
                "NegotiationScriptGenerator | Erro ao gerar script: %s", exc, exc_info=True
            )
            return self._fallback_script(opportunity)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PRIVADOS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _build_prompt(self, opp: NegotiationOpportunity) -> str:
        fee_line = (
            f"Valor médio mensal pago: R$ {opp.user_fee_monthly:.2f}"
            if opp.user_fee_monthly is not None
            else ""
        )
        market_line = (
            f"Taxa média de mercado: {opp.market_rate_monthly * 100:.2f}% a.m."
            if opp.market_rate_monthly is not None
            else ""
        )
        saving_line = (
            f"Economia potencial estimada: R$ {opp.potential_saving_monthly:.2f}/mês"
            if opp.potential_saving_monthly > 0
            else ""
        )

        return _USER_PROMPT_TEMPLATE.format(
            bank_name=opp.bank_name,
            product=opp.product,
            trigger=opp.trigger.value,
            health_score=opp.health_score,
            months_as_good_payer=opp.months_as_good_payer,
            fee_line=fee_line,
            market_line=market_line,
            saving_line=saving_line,
            description=opp.description,
        )

    def _call_claude(self, user_prompt: str) -> str:
        """Chama a API da Anthropic e retorna o texto bruto da resposta."""
        message = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text

    @staticmethod
    def _parse_script(
        data: dict,
        opportunity: NegotiationOpportunity,
    ) -> NegotiationScript:
        """Constrói NegotiationScript a partir do dict retornado por Claude."""

        # Normaliza channel — Claude pode retornar string fora do enum
        raw_channel = data.get("recommended_channel", "APP_CHAT")
        try:
            channel = NegotiationChannel(raw_channel)
        except ValueError:
            channel = NegotiationChannel.APP_CHAT

        # Clamp estimated_success_pct para garantir 0-100
        success_pct = max(0, min(100, int(data.get("estimated_success_pct", 50))))

        return NegotiationScript(
            opportunity=opportunity,
            opening_line=data.get("opening_line", ""),
            key_arguments=data.get("key_arguments", []),
            target_ask=data.get("target_ask", ""),
            fallback_ask=data.get("fallback_ask", ""),
            closing_line=data.get("closing_line", ""),
            recommended_channel=channel,
            best_time=data.get("best_time", "terça ou quarta-feira, manhã (9h-11h)"),
            estimated_success_pct=success_pct,
            warnings=data.get("warnings", []),
        )

    @staticmethod
    def _fallback_script(opportunity: NegotiationOpportunity) -> NegotiationScript:
        """
        Script genérico de emergência quando Claude não está disponível.
        Garante que o usuário sempre receba algo útil.
        """
        bank = opportunity.bank_name
        product = opportunity.product
        score = opportunity.health_score
        months = opportunity.months_as_good_payer

        return NegotiationScript(
            opportunity=opportunity,
            opening_line=(
                f"Olá, gostaria de falar com um gerente sobre meu {product} no {bank}."
            ),
            key_arguments=[
                f"Sou cliente há pelo menos {months} meses sem atrasos.",
                f"Meu score de relacionamento é {score}/100 — perfil de baixo risco.",
                "Pesquisei alternativas no mercado e encontrei condições mais vantajosas.",
                "Gostaria de resolver isso mantendo minha conta no banco.",
            ],
            target_ask=f"Redução ou isenção das cobranças referentes a {product}.",
            fallback_ask="Ao menos uma revisão do contrato nos próximos 30 dias.",
            closing_line=(
                "Agradeço pela atenção. Fico aguardando o retorno para decidir sobre "
                "a continuidade do relacionamento."
            ),
            recommended_channel=NegotiationChannel.APP_CHAT,
            best_time="terça ou quarta-feira, manhã (9h-11h)",
            estimated_success_pct=max(40, min(80, score)),
            generated_by="fallback",
            warnings=["Roteiro gerado localmente — serviço de IA temporariamente indisponível."],
        )
