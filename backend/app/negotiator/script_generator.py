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
from app.core.formatacao import brl, numero

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"

# Por chamada. Sem timeout, um roteiro travado segurava a requisição inteira
# (o frontend desistia aos 15 s e culpava "falta de histórico").
_TIMEOUT_LLM_S = 20.0


def _extrair_json(texto: str) -> dict:
    """
    O modelo às vezes embrulha o JSON em ```json … ``` ou põe uma frase antes,
    mesmo instruído a não fazer: `json.loads` direto falhava ("Expecting value:
    line 1 column 1") e TODO roteiro caía no template local. Pega o primeiro
    objeto {...} do texto.
    """
    t = (texto or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        t = t.rsplit("```", 1)[0]
    ini, fim = t.find("{"), t.rfind("}")
    if ini == -1 or fim <= ini:
        raise json.JSONDecodeError("nenhum objeto JSON na resposta", t, 0)
    return json.loads(t[ini:fim + 1])

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
Health Score Nexa: {health_score}
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
  (quando o score não foi calculado, use só os meses como bom pagador)
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
        self._client = anthropic.Anthropic(timeout=_TIMEOUT_LLM_S, max_retries=1)

    def generate(self, opportunity: NegotiationOpportunity) -> NegotiationScript:
        """
        Chama Claude com o contexto da oportunidade e retorna NegotiationScript.

        Em caso de falha na chamada ou parse do JSON, retorna um script padrão
        (fallback) para não bloquear o usuário.
        """
        prompt = self._build_prompt(opportunity)

        try:
            raw_json = self._call_claude(prompt)
            data = _extrair_json(raw_json)
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
            f"Valor médio mensal pago: {brl(opp.user_fee_monthly)}"
            if opp.user_fee_monthly is not None
            else ""
        )
        market_line = (
            f"Taxa média de mercado: {numero(opp.market_rate_monthly * 100, 2)}% a.m."
            if opp.market_rate_monthly is not None
            else ""
        )
        saving_line = (
            f"Economia potencial estimada: {brl(opp.potential_saving_monthly)}/mês"
            if opp.potential_saving_monthly > 0
            else ""
        )

        return _USER_PROMPT_TEMPLATE.format(
            bank_name=opp.bank_name,
            product=opp.product,
            trigger=opp.trigger.value,
            # "não calculado" em vez de "None/100": o prompt vira argumento de
            # negociação, e o modelo não pode citar um score que não existe.
            health_score=(
                f"{opp.health_score}/100" if opp.health_score is not None
                else "não calculado (não citar score na argumentação)"
            ),
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
            # 1024 cortava o JSON no meio em roteiros mais longos ("Expecting
            # ',' delimiter") e o usuário recebia o template local.
            max_tokens=2048,
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
                arg for arg in (
                    f"Sou cliente há pelo menos {months} meses sem atrasos.",
                    # Sem score calculado, este argumento sai do roteiro: mandar o
                    # usuário afirmar ao gerente um número que a Nexa não mediu é
                    # pior que um argumento a menos.
                    (f"Meu score de relacionamento é {score}/100 — perfil de baixo risco."
                     if score is not None else None),
                    "Pesquisei alternativas no mercado e encontrei condições mais vantajosas.",
                    "Gostaria de resolver isso mantendo minha conta no banco.",
                ) if arg
            ],
            target_ask=f"Redução ou isenção das cobranças referentes a {product}.",
            fallback_ask="Ao menos uma revisão do contrato nos próximos 30 dias.",
            closing_line=(
                "Agradeço pela atenção. Fico aguardando o retorno para decidir sobre "
                "a continuidade do relacionamento."
            ),
            recommended_channel=NegotiationChannel.APP_CHAT,
            best_time="terça ou quarta-feira, manhã (9h-11h)",
            # Sem score, fica na base da faixa em vez de herdar um 50 fabricado.
            estimated_success_pct=max(40, min(80, score)) if score is not None else 40,
            generated_by="fallback",
            warnings=["Roteiro gerado localmente — serviço de IA temporariamente indisponível."],
        )
