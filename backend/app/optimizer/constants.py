# app/optimizer/constants.py
# Constantes compartilhadas entre ranking, simulator e insight_generator.
# Centralizar aqui evita drift quando o mesmo threshold é editado em apenas um arquivo.

# BenefitViabilityFilter — gasto mínimo mensal para o benefício ser válido no perfil do usuário
INTL_SPEND_THRESHOLD: float = 500.0   # R$/mês → proxy para uso frequente no exterior
TRAVEL_SPEND_THRESHOLD: float = 800.0  # R$/mês → proxy para ≥4 voos/ano (Lazer + Transporte)

# Bônus anuais adicionados ao score de ranking quando perfil valida o benefício
INTL_RANKING_BONUS: float = 200.0   # R$/ano
LOUNGE_RANKING_BONUS: float = 300.0  # R$/ano

# ── Estágios de Vida (LifeStageDetector) ─────────────────────────────────────
# Identificadores canônicos — usados em detector, ranking, insight_generator e testes.
LIFE_STAGE_FAMILIA_BEBE       = "FAMILIA_BEBE"
LIFE_STAGE_NOMADE_DIGITAL     = "NOMADE_DIGITAL"
LIFE_STAGE_INVESTIDOR_PREMIUM = "INVESTIDOR_PREMIUM"
LIFE_STAGE_SOLTEIRO_URBANO    = "SOLTEIRO_URBANO"
LIFE_STAGE_NAO_IDENTIFICADO   = "NAO_IDENTIFICADO"

# Score mínimo para classificar o estágio primário
LIFE_STAGE_PRIMARY_THRESHOLD: float = 0.40
# Confiança mínima para acionar bônus de ranking e insights hiperpersonalizados
LIFE_STAGE_MIN_CONFIDENCE: float = 0.50
