# app/optimizer/constants.py
# Constantes compartilhadas entre ranking, simulator e insight_generator.
# Centralizar aqui evita drift quando o mesmo threshold é editado em apenas um arquivo.

# BenefitViabilityFilter — gasto mínimo mensal para o benefício ser válido no perfil do usuário
INTL_SPEND_THRESHOLD: float = 500.0   # R$/mês → proxy para uso frequente no exterior
TRAVEL_SPEND_THRESHOLD: float = 800.0  # R$/mês → proxy para ≥4 voos/ano (Lazer + Transporte)

# Bônus anuais adicionados ao score de ranking quando perfil valida o benefício
INTL_RANKING_BONUS: float = 200.0   # R$/ano
LOUNGE_RANKING_BONUS: float = 300.0  # R$/ano
