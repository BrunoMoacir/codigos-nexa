"""
app/architect/services/llm_reasoner.py — LLM como camada de co-raciocínio estruturado

Responsabilidade:
    Usar o LLM em 2 momentos distintos do pipeline da F3:

    Passo 1 — Verificação de consistência:
        Dado o resumo financeiro + recomendação do motor, o LLM age como
        analista sênior: detecta inconsistências entre perfil e estratégia,
        riscos não modelados e sugere ajuste de parâmetros (override_params).

    Passo 3 — Narrativa contextualizada:
        Após o possível reprocessamento, gera 3 parágrafos adaptados ao
        perfil do usuário: por que essa estratégia vence, riscos honestos
        e próximos 3 passos concretos com prazo.

Passo 2 (reprocessamento) fica em ArchitectService.simulate(), não aqui:
    O motor é domínio do serviço; o LLMReasoner recebe o resultado final
    via callback (rerun_fn) e apenas dispara se override_params for não-nulo.

Suporte a provedores:
    - openai   → settings.LLM_MODEL (default: gpt-4o-mini)
    - anthropic → settings.LLM_MODEL (default: claude-haiku-4-5-20251001)

Degradação graciosa:
    Se a chave de API não estiver configurada ou qualquer chamada falhar,
    LLMReasoner.reason() retorna (None, base_response) sem propagar a exceção.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Callable, Dict, Optional

if TYPE_CHECKING:
    from app.architect.models import (
        LLMConsistencyResult,
        LLMNarrative,
        LLMReasoningResult,
        RiskProfile,
        SimulationRequest,
        SimulationResponse,
    )

logger = logging.getLogger(__name__)

# Chaves de override_params aceitas para reprocessamento do motor.
# Outras chaves são ignoradas para evitar manipulação via prompt injection.
_ALLOWED_OVERRIDE_KEYS = {"risk_profile", "financing_months"}

_STYLE_BY_PROFILE = {
    "conservador": "formal e prudente — priorize segurança e clareza sobre riscos",
    "moderado":    "direto e informativo — equilíbrio entre detalhe técnico e acessibilidade",
    "agressivo":   "técnico e objetivo — o usuário valoriza dados e decisões rápidas",
}


class LLMReasoner:
    """
    Co-raciocínio estruturado sobre recomendações do motor financeiro.

    Args:
        provider:  "openai" | "anthropic"  (padrão: settings.LLM_PROVIDER)
        model:     Modelo a usar            (padrão: settings.LLM_MODEL)
        api_key:   Chave de API             (padrão: settings.OPENAI/ANTHROPIC_API_KEY)

    Usage:
        reasoner = LLMReasoner()
        llm_result, final_response = reasoner.reason(
            request, base_response, market_rates, rerun_fn=lambda r: engine.simulate(r, rates)
        )
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        from app.core.config import settings

        self._provider = (provider or settings.LLM_PROVIDER).lower()
        self._model    = model or settings.LLM_MODEL

        if api_key:
            self._api_key = api_key
        elif self._provider == "anthropic":
            self._api_key = settings.ANTHROPIC_API_KEY
        else:
            self._api_key = settings.OPENAI_API_KEY

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PONTO DE ENTRADA PRINCIPAL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def reason(
        self,
        request: "SimulationRequest",
        base_response: "SimulationResponse",
        market_rates: Dict[str, float],
        rerun_fn: Callable[["SimulationRequest"], "SimulationResponse"],
    ) -> tuple[Optional["LLMReasoningResult"], "SimulationResponse"]:
        """
        Executa o raciocínio estruturado em 3 passos e retorna o resultado
        junto com a resposta (possivelmente atualizada pelo rerun).

        Returns:
            (LLMReasoningResult | None, SimulationResponse)
            None quando LLM não está configurado ou falha.
        """
        from app.architect.models import LLMReasoningResult

        if not self._api_key:
            logger.debug("LLMReasoner: sem API key configurada — raciocínio desativado.")
            return None, base_response

        try:
            summary = self._build_summary(request, base_response, market_rates)

            # Passo 1: verificação de consistência
            consistency = self._check_consistency(summary)

            # Passo 2: reprocessamento se override_params presente
            engine_rerun = False
            if consistency.override_params:
                adjusted_request = self._apply_overrides(request, consistency.override_params)
                if adjusted_request is not None:
                    logger.info(
                        "LLMReasoner | override_params=%s → rerun do motor",
                        consistency.override_params,
                    )
                    base_response = rerun_fn(adjusted_request)
                    engine_rerun  = True
                    summary = self._build_summary(adjusted_request, base_response, market_rates)

            # Passo 3: narrativa contextualizada (com contexto pós-override)
            narrative = self._generate_narrative(summary, consistency, request)

            return LLMReasoningResult(
                consistency=consistency,
                narrative=narrative,
                engine_rerun=engine_rerun,
                provider_used=self._provider,
                model_used=self._model,
            ), base_response

        except Exception as exc:
            logger.warning("LLMReasoner | falhou, continuando sem raciocínio LLM: %s", exc)
            return None, base_response

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 1 — CONSISTÊNCIA
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _check_consistency(self, summary: dict) -> "LLMConsistencyResult":
        from app.architect.models import LLMConsistencyResult

        system = (
            "Você é um analista financeiro sênior revisando uma recomendação automatizada. "
            "Responda SOMENTE em JSON válido, sem markdown, sem texto extra."
        )
        user = (
            f"Dados da simulação:\n{json.dumps(summary, ensure_ascii=False, indent=2)}\n\n"
            "Identifique:\n"
            "1. Inconsistência entre perfil de risco e recomendação?\n"
            "2. Estratégia descartada por critério questionável?\n"
            "3. Risco não modelado relevante (ex: bem depreciável com prazo longo, "
            "comprometimento de renda alto, IPCA acima do CDI)?\n\n"
            'Responda em JSON: {"consistent": bool, "flags": ["..."], '
            '"override_suggestion": "texto ou null", '
            '"override_params": {"risk_profile": "conservador|moderado|agressivo"} ou null}\n\n'
            "override_params: use APENAS quando consistent=false E há parâmetro ajustável. "
            "Chaves válidas: 'risk_profile', 'financing_months' (valor inteiro como string)."
        )

        raw = self._call_llm(system=system, user=user, json_mode=True, max_tokens=1024)
        return self._parse_consistency(raw)

    def _parse_consistency(self, raw: str) -> "LLMConsistencyResult":
        from app.architect.models import LLMConsistencyResult

        # Strip markdown code fences that some models add around JSON
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            cleaned = cleaned.rsplit("```", 1)[0].strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("LLMReasoner | JSON inválido na consistência: %.200s", raw)
            return LLMConsistencyResult(consistent=True, flags=["LLM retornou JSON inválido"])

        override_params = data.get("override_params")
        if isinstance(override_params, dict):
            # Sanitize: aceitar apenas chaves permitidas
            override_params = {
                k: str(v) for k, v in override_params.items()
                if k in _ALLOWED_OVERRIDE_KEYS
            } or None

        return LLMConsistencyResult(
            consistent=bool(data.get("consistent", True)),
            flags=[str(f) for f in data.get("flags", [])],
            override_suggestion=data.get("override_suggestion") or None,
            override_params=override_params,
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 3 — NARRATIVA
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _generate_narrative(
        self,
        summary: dict,
        consistency: "LLMConsistencyResult",
        request: "SimulationRequest",
    ) -> "LLMNarrative":
        from app.architect.models import LLMNarrative

        profile_val = summary.get("perfil_risco", "moderado")
        style = _STYLE_BY_PROFILE.get(profile_val, _STYLE_BY_PROFILE["moderado"])

        npv_lines = []
        for k in ("npv_financing", "npv_save_invest", "npv_consortium"):
            v = summary.get(k)
            if v:
                npv_lines.append(f"{k.replace('npv_', '').upper()}: {v}")

        flags_text = ""
        if consistency.flags:
            flags_text = f"\nFlags detectados: {'; '.join(consistency.flags)}"

        system = (
            "Você é um consultor financeiro pessoal falando diretamente com o cliente. "
            f"Tom: {style}. Seja específico, honesto e conciso."
        )
        user = (
            f"Estratégia recomendada: {summary['recomendado']}\n"
            f"Bem: {summary['bem']} — valor R${summary['valor']:,.0f}, entrada R${summary['entrada']:,.0f}\n"
            f"Prazo: {summary['prazo_meses']} meses | CET: {summary['cet']} | SELIC: {summary['selic']}\n"
            f"Comparação NPV: {' | '.join(npv_lines)}\n"
            f"Garantia SSD: {summary.get('ssd_guarantee') or 'nenhuma'}\n"
            f"{flags_text}\n\n"
            "Escreva exatamente 3 parágrafos separados por linha em branco:\n"
            "§1 — Por que esta estratégia vence: intuição financeira, 2-3 frases, sem fórmulas.\n"
            "§2 — O que pode dar errado: 2 riscos específicos e honestos, 2-3 frases.\n"
            "§3 — Próximos 3 passos: ações concretas com prazo (ex: 'nos próximos 30 dias').\n\n"
            "Retorne SOMENTE os 3 parágrafos, sem títulos, sem numeração, sem markdown."
        )

        raw = self._call_llm(system=system, user=user, json_mode=False, max_tokens=500)
        return self._parse_narrative(raw)

    def _parse_narrative(self, raw: str) -> "LLMNarrative":
        from app.architect.models import LLMNarrative

        parts = [p.strip() for p in raw.strip().split("\n\n") if p.strip()]
        if len(parts) >= 3:
            return LLMNarrative(
                why_this_strategy=parts[0],
                risks=parts[1],
                next_steps=parts[2],
            )
        # Fallback: distribui o texto em 3 partes iguais
        third = max(1, len(raw) // 3)
        return LLMNarrative(
            why_this_strategy=raw[:third].strip(),
            risks=raw[third : 2 * third].strip(),
            next_steps=raw[2 * third:].strip(),
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HELPERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _build_summary(
        request: "SimulationRequest",
        response: "SimulationResponse",
        market_rates: Dict[str, float],
    ) -> dict:
        npv = response.npv
        winner_npv = {
            "FINANCING":               npv.financing,
            "SAVE_INVEST":             npv.save_invest,
            "CONSORTIUM":              npv.consortium,
            "FINANCING_RENTAL":        npv.financing_rental,
            "CONSORTIUM_SELIC_RENTAL": npv.consortium_selic_rental,
        }.get(response.recommended_strategy.value, 0.0) or 0.0

        all_npvs = {
            "FINANCING":               npv.financing,
            "SAVE_INVEST":             npv.save_invest,
            "CONSORTIUM":              npv.consortium,
            "FINANCING_RENTAL":        npv.financing_rental,
            "CONSORTIUM_SELIC_RENTAL": npv.consortium_selic_rental,
        }
        discarded: dict[str, str] = {
            strat: f"NPV {winner_npv - val:+,.0f} vs {response.recommended_strategy.value}"
            for strat, val in all_npvs.items()
            if val is not None and strat != response.recommended_strategy.value
        }

        return {
            "bem":            request.asset_type.value,
            "valor":          request.target_amount,
            "entrada":        request.down_payment,
            "prazo_meses":    request.financing_months,
            "perfil_risco":   request.risk_profile.value if request.risk_profile else "não informado",
            "risk_score":     round(request.risk_score, 3) if request.risk_score is not None else None,
            "metodo":         request.amortization_method.value,
            "selic":          f"{market_rates.get('selic_annual', 0.1475):.2%}",
            "cet":            f"{market_rates.get('best_cet_annual', 0.15):.2%}",
            "ipca":           f"{market_rates.get('ipca_annual', 0.045):.2%}",
            "npv_financing":           f"R${npv.financing:,.0f}" if npv.financing is not None else None,
            "npv_save_invest":         f"R${npv.save_invest:,.0f}" if npv.save_invest is not None else None,
            "npv_consortium":          f"R${npv.consortium:,.0f}" if npv.consortium is not None else None,
            "npv_financing_rental":    f"R${npv.financing_rental:,.0f}" if npv.financing_rental is not None else None,
            "npv_consortium_selic":    f"R${npv.consortium_selic_rental:,.0f}" if npv.consortium_selic_rental is not None else None,
            "recomendado":    response.recommended_strategy.value,
            "ssd_guarantee":  response.ssd_guarantee,
            "warnings_motor": [
                w[:150] for w in response.warnings[:5]
                if isinstance(w, str)
            ],
            "descartadas":    discarded,
        }

    @staticmethod
    def _apply_overrides(
        request: "SimulationRequest",
        override_params: Dict[str, str],
    ) -> Optional["SimulationRequest"]:
        """Aplica override_params ao request com validação. Retorna None se inválido."""
        from app.architect.models import RiskProfile

        updates: dict = {}
        for key, value in override_params.items():
            if key == "risk_profile":
                try:
                    updates["risk_profile"] = RiskProfile(value.lower())
                except ValueError:
                    logger.warning("LLMReasoner | risk_profile inválido: %s", value)
            elif key == "financing_months":
                try:
                    months = int(value)
                    if 6 <= months <= 420:
                        updates["financing_months"] = months
                    else:
                        logger.warning("LLMReasoner | financing_months fora do range: %s", value)
                except ValueError:
                    logger.warning("LLMReasoner | financing_months não é int: %s", value)

        if not updates:
            return None
        return request.model_copy(update=updates)

    def _call_llm(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        max_tokens: int = 400,
    ) -> str:
        if self._provider == "anthropic":
            return self._call_anthropic(system, user, max_tokens, json_mode=json_mode)
        return self._call_openai(system, user, json_mode, max_tokens)

    def _call_openai(
        self,
        system: str,
        user: str,
        json_mode: bool,
        max_tokens: int,
    ) -> str:
        import openai

        client = openai.OpenAI(api_key=self._api_key)
        kwargs: dict = {
            "model":      self._model,
            "messages":   [
                {"role": "system",  "content": system},
                {"role": "user",    "content": user},
            ],
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    def _call_anthropic(
        self,
        system: str,
        user: str,
        max_tokens: int,
        json_mode: bool = False,
    ) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self._api_key)
        messages: list = [{"role": "user", "content": user}]
        if json_mode:
            # Prefill technique: force the model to start (and continue) with valid JSON
            messages.append({"role": "assistant", "content": "{"})

        response = client.messages.create(
            model=self._model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
        )
        text = response.content[0].text if response.content else ""
        if json_mode:
            # The prefill "{" is not included in the response text — prepend it
            return "{" + text
        return text
