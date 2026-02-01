# profiles py
"""
app/etl/bank_strategy/profiles.py - BankProfile (Configuração por Banco)

╔══════════════════════════════════════════════════════════════════════╗
║ O QUE ESTE ARQUIVO FAZ                                               ║
╚══════════════════════════════════════════════════════════════════════╝

Define a estrutura de configuração de cada banco:
    - Tier de confiabilidade (TIER_1, TIER_2, TIER_3, TIER_4)
    - Formatos de data aceitos (ISO 8601, dd/mm/yyyy, etc)
    - Formato de valores (BR ou US)
    - Campos obrigatórios
    - Aliases de campos (ex: "valor" → "amount")
    - Thresholds de qualidade

╔══════════════════════════════════════════════════════════════════════╗
║ EXEMPLO DE USO                                                       ║
╚══════════════════════════════════════════════════════════════════════╝

# Carregar perfil de um banco
nubank_profile = BankProfile.from_yaml("nubank", yaml_data)

# Acessar configurações
print(nubank_profile.tier)              # TIER_1
print(nubank_profile.date_formats)      # ["%Y-%m-%dT%H:%M:%S", ...]
print(nubank_profile.required_fields)   # ["transaction_id", "amount", ...]
"""

from dataclasses import dataclass
from typing import Any

from app.schemas.enums import BankTier


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATACLASS: BANK PROFILE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass(frozen=True)  # Immutable (thread-safe, cacheable)
class BankProfile:
    """
    Configuração de um banco específico.
    
    Carregado de bank_profiles.yaml e usado pelas BankStrategies.
    
    Attributes:
        institution_id: ID único do banco (ex: "nubank", "itau")
        display_name: Nome amigável (ex: "Nubank", "Itaú")
        tier: Nível de confiabilidade (TIER_1 a TIER_4)
        locale: Formato regional ("BR" ou "US")
        date_formats: Lista de formatos de data aceitos
        amount_format: Formato de valores monetários ("BR" ou "US")
        required_fields: Lista de campos obrigatórios
        field_aliases: Mapa de aliases (ex: {"valor": "amount"})
        quality_thresholds: Thresholds de qualidade
    
    Example:
        >>> nubank = BankProfile(
        ...     institution_id="nubank",
        ...     display_name="Nubank",
        ...     tier=BankTier.TIER_1,
        ...     locale="BR",
        ...     date_formats=["%Y-%m-%dT%H:%M:%S"],
        ...     amount_format="BR",
        ...     required_fields=["transaction_id", "amount", "balance"],
        ...     field_aliases={"id": "transaction_id"},
        ...     quality_thresholds={"min_history_days": 90}
        ... )
    """
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # IDENTIFICAÇÃO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    institution_id: str
    """ID único do banco (usado no código)"""
    
    display_name: str
    """Nome amigável para exibir ao usuário"""
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CONFIABILIDADE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    tier: BankTier
    """
    Tier de confiabilidade:
        - TIER_1: Excelente (Nubank, C6, BTG)
        - TIER_2: Bom (Inter, XP, Original)
        - TIER_3: Problemático (Itaú, Bradesco, Santander)
        - TIER_4: Muito instável (PicPay, Mercado Pago)
    """
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # FORMATOS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    locale: str
    """Formato regional: "BR" ou "US" """
    
    date_formats: list[str]
    """
    Lista de formatos de data aceitos (strptime).
    Ex: ["%Y-%m-%dT%H:%M:%S", "%d/%m/%Y"]
    """
    
    amount_format: str
    """
    Formato de valores monetários:
        - "BR": 1.500,00 (ponto = milhar, vírgula = decimal)
        - "US": 1,500.00 (vírgula = milhar, ponto = decimal)
    """
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # VALIDAÇÃO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    required_fields: list[str]
    """
    Campos obrigatórios que este banco sempre envia.
    Ex: ["transaction_id", "amount", "date", "balance"]
    
    Se um campo obrigatório estiver faltando, a transação é rejeitada.
    """
    
    field_aliases: dict[str, str]
    """
    Mapa de aliases de campos.
    Ex: {"id": "transaction_id", "valor": "amount"}
    
    Usado para normalizar nomes de campos que variam entre bancos.
    """
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # QUALIDADE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    quality_thresholds: dict[str, Any]
    """
    Thresholds de qualidade específicos do banco.
    
    Campos comuns:
        - min_history_days: Dias mínimos de histórico
        - max_missing_rate: Taxa máxima de dados faltando (0.0 - 1.0)
        - min_trust_score: Score mínimo para TRUSTED (0.0 - 1.0)
    
    Example:
        {
            "min_history_days": 90,
            "max_missing_rate": 0.05,  # 5%
            "min_trust_score": 0.9
        }
    """
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # FACTORY METHOD
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    @classmethod
    def from_yaml(
        cls,
        institution_id: str,
        yaml_data: dict[str, Any]
    ) -> "BankProfile":
        """
        Cria BankProfile a partir de dados do YAML.
        
        Args:
            institution_id: ID do banco
            yaml_data: Dados carregados do bank_profiles.yaml
        
        Returns:
            BankProfile instanciado
        
        Raises:
            KeyError: Se campos obrigatórios estiverem faltando
            ValueError: Se tier for inválido
        
        Example:
            >>> yaml_data = {
            ...     "display_name": "Nubank",
            ...     "tier": "TIER_1",
            ...     "locale": "BR",
            ...     ...
            ... }
            >>> profile = BankProfile.from_yaml("nubank", yaml_data)
        """
        # Parse tier (string → BankTier enum)
        tier_str = yaml_data["tier"]
        tier = BankTier(tier_str)  # Converte "TIER_1" → BankTier.TIER_1
        
        return cls(
            institution_id=institution_id,
            display_name=yaml_data["display_name"],
            tier=tier,
            locale=yaml_data["locale"],
            date_formats=yaml_data["date_formats"],
            amount_format=yaml_data["amount_format"],
            required_fields=yaml_data["required_fields"],
            field_aliases=yaml_data.get("field_aliases", {}),
            quality_thresholds=yaml_data.get("quality_thresholds", {})
        )