"""
app/architect/validators/input_validator.py - Validador de regras de negócio

Feature: F3 - Nexa Architect
Version: 1.0.0

Responsabilidade:
    Validar o SimulationRequest com regras de negócio que vão além
    do que o Pydantic consegue checar nos campos isolados.

    O Pydantic garante tipos e limites por campo.
    Este módulo garante que os campos fazem sentido JUNTOS
    e que a simulação tem chances reais de produzir um resultado útil.

Regras implementadas:
    1. principal mínimo de R$ 1.000
    2. down_payment não pode representar mais de 90% do target_amount
    3. max_monthly_budget mínimo de R$ 100
    4. financing_months coerente com o asset_type
    5. target_amount mínimo por tipo de bem
    6. prefers_consortium e include_consortium não podem ser contraditórios
    7. target_date vs financing_months: aviso se horizonte é inconsistente

Usage:
    from app.architect.validators.input_validator import InputValidator

    result = InputValidator.validate(request)
    if not result.is_valid:
        raise ValueError(result.errors)
"""

from dataclasses import dataclass, field
from datetime import date

from app.architect.models import AssetType, SimulationRequest
from app.architect.utils.date_helpers import months_between
from app.core.formatacao import brl


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULTADO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class ValidationResult:
    """
    Resultado da validação de um SimulationRequest.

    Attributes:
        is_valid: False se qualquer regra bloqueante falhou.
        errors:   Lista de mensagens de erro (bloqueantes).
        warnings: Lista de alertas não-bloqueantes.
    """
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.is_valid = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LIMITES POR TIPO DE BEM
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Prazo máximo razoável de financiamento por tipo de bem (meses)
_MAX_FINANCING_MONTHS: dict[AssetType, int] = {
    AssetType.IMOVEL:  420,   # 35 anos (SFH/SFI)
    AssetType.VEICULO:  84,   # 7 anos (limite prático de mercado)
    AssetType.REFORMA: 120,   # 10 anos
    AssetType.VIAGEM:   60,   # 5 anos (crédito pessoal)
    AssetType.OUTRO:   120,   # 10 anos (default conservador)
}

# Valor mínimo por tipo de bem para que a simulação faça sentido
_MIN_TARGET_AMOUNT: dict[AssetType, float] = {
    AssetType.IMOVEL:  50_000.0,   # Imóvel < R$ 50k não existe no Brasil
    AssetType.VEICULO:  5_000.0,   # Veículo > R$ 5k (motocicleta básica)
    AssetType.REFORMA:  2_000.0,   # Reforma mínima relevante
    AssetType.VIAGEM:   1_000.0,   # Pacote mínimo
    AssetType.OUTRO:    1_000.0,
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# VALIDADOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class InputValidator:
    """
    Validador de regras de negócio para SimulationRequest.

    Todas as regras são métodos estáticos privados.
    O ponto de entrada público é `validate()`.

    Example:
        >>> result = InputValidator.validate(request)
        >>> if not result.is_valid:
        ...     print(result.errors)
    """

    @staticmethod
    def validate(request: SimulationRequest) -> ValidationResult:
        """
        Executa todas as regras de validação sobre o request.

        Args:
            request: SimulationRequest já validado pelo Pydantic.

        Returns:
            ValidationResult com is_valid, errors e warnings.
        """
        result = ValidationResult()

        InputValidator._check_principal_minimo(request, result)
        InputValidator._check_down_payment_proporcional(request, result)
        InputValidator._check_budget_minimo(request, result)
        InputValidator._check_financing_months_por_asset(request, result)
        InputValidator._check_target_amount_por_asset(request, result)
        InputValidator._check_consortium_flags(request, result)
        InputValidator._check_target_date_vs_financing(request, result)

        return result

    # ── Regras bloqueantes ───────────────────────────────────────────

    @staticmethod
    def _check_principal_minimo(
        req: SimulationRequest, result: ValidationResult
    ) -> None:
        """
        O valor financiado (target - entrada) deve ser >= R$ 1.000.

        Abaixo disso a simulação não produz resultados úteis e o
        overhead do consórcio ou financiamento não faz sentido econômico.
        """
        MIN_PRINCIPAL = 1_000.0
        if req.principal < MIN_PRINCIPAL:
            result.add_error(
                f"O valor a financiar ({brl(req.principal)}) é muito baixo. "
                f"Mínimo: {brl(MIN_PRINCIPAL)}. "
                "Reduza o down_payment ou aumente o target_amount."
            )

    @staticmethod
    def _check_down_payment_proporcional(
        req: SimulationRequest, result: ValidationResult
    ) -> None:
        """
        A entrada não pode representar mais de 90% do target_amount.

        Acima de 90%, o principal é tão pequeno que o financiamento e o
        consórcio são economicamente irrelevantes. O usuário provavelmente
        está próximo de comprar à vista e não precisa de simulação.
        """
        MAX_DOWN_PAYMENT_RATIO = 0.90
        ratio = req.down_payment / req.target_amount
        if ratio > MAX_DOWN_PAYMENT_RATIO:
            result.add_error(
                f"A entrada ({ratio:.0%} do valor total) ultrapassa o limite de "
                f"{MAX_DOWN_PAYMENT_RATIO:.0%}. Com esse percentual de entrada, "
                "uma compra à vista pode ser mais simples."
            )

    @staticmethod
    def _check_budget_minimo(
        req: SimulationRequest, result: ValidationResult
    ) -> None:
        """
        Se informado, max_monthly_budget deve ser >= R$ 100.

        Um orçamento menor que R$ 100/mês inviabiliza qualquer estratégia
        de aquisição em prazo razoável.
        """
        MIN_BUDGET = 100.0
        if req.max_monthly_budget is not None and req.max_monthly_budget < MIN_BUDGET:
            result.add_error(
                f"max_monthly_budget ({brl(req.max_monthly_budget)}) é muito baixo. "
                f"Mínimo aceito: {brl(MIN_BUDGET)}/mês."
            )

    @staticmethod
    def _check_financing_months_por_asset(
        req: SimulationRequest, result: ValidationResult
    ) -> None:
        """
        O prazo de financiamento deve ser compatível com o tipo de bem.

        Ex: financiar uma viagem por 35 anos não faz sentido econômico.
        Prazos muito longos para ativos depreciativos (veículo, viagem)
        geram NPV distorcido.
        """
        max_months = _MAX_FINANCING_MONTHS[req.asset_type]
        if req.financing_months > max_months:
            result.add_error(
                f"financing_months ({req.financing_months}) excede o máximo "
                f"recomendado para {req.asset_type.value} ({max_months} meses / "
                f"{max_months // 12} anos)."
            )

    @staticmethod
    def _check_target_amount_por_asset(
        req: SimulationRequest, result: ValidationResult
    ) -> None:
        """
        O valor alvo deve ser compatível com o tipo de bem.

        Evita simulações com valores que não fazem sentido para o mercado
        (ex: imóvel de R$ 500).
        """
        min_amount = _MIN_TARGET_AMOUNT[req.asset_type]
        if req.target_amount < min_amount:
            result.add_error(
                f"target_amount ({brl(req.target_amount)}) é muito baixo para "
                f"o tipo de bem '{req.asset_type.value}'. "
                f"Mínimo esperado: {brl(min_amount)}."
            )

    # ── Avisos não-bloqueantes ───────────────────────────────────────

    @staticmethod
    def _check_consortium_flags(
        req: SimulationRequest, result: ValidationResult
    ) -> None:
        """
        Alerta quando prefers_consortium=True mas include_consortium=False.

        Situação contraditória: o usuário diz preferir consórcio mas
        pediu para não incluí-lo na simulação.
        """
        if req.prefers_consortium and not req.include_consortium:
            result.add_warning(
                "prefers_consortium=True mas include_consortium=False. "
                "O consórcio não será calculado apesar da preferência declarada."
            )

    @staticmethod
    def _check_target_date_vs_financing(
        req: SimulationRequest, result: ValidationResult
    ) -> None:
        """
        Alerta quando target_date implica prazo incompatível com financing_months.

        Se o usuário quer o bem em 12 meses mas configurou 48 meses de
        financiamento, o plano de ação pode ser confuso. Apenas aviso —
        o engine usa financing_months para o cálculo e target_date para
        o plano de ação.
        """
        if req.target_date is None:
            return

        months_until_target = months_between(date.today(), req.target_date)

        if months_until_target <= 0:
            return

        # Financiamento dura mais que o dobro do prazo desejado
        if req.financing_months > months_until_target * 2:
            result.add_warning(
                f"financing_months ({req.financing_months} meses) é mais que o dobro "
                f"do prazo até target_date ({months_until_target} meses). "
                "Considere reduzir o prazo do financiamento."
            )

        # Data alvo muito próxima mas prazo longo
        if months_until_target < 6 and req.financing_months > 12:
            result.add_warning(
                f"target_date está em {months_until_target} meses, mas financing_months "
                f"é {req.financing_months}. Para aquisição tão próxima, avalie se "
                "financiamento é a melhor opção."
            )


__all__ = ["InputValidator", "ValidationResult"]
