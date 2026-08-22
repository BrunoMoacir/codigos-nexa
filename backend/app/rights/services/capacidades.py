"""
app/rights/services/capacidades.py — o que a Nexa consegue fazer por fonte

`capability` diz ao cliente se aquela fonte tem consulta REAL disponível
(`assisted_real` com captcha do BACEN, `authorized_real` com token do e-CAC)
ou se é só roteiro (`guided`). Vivia dentro do router, então a tool do agente
— que não passa pelo router — imprimia "guided" para tudo e escondia do
usuário a única parte da funcionalidade que consulta de verdade.
"""

from __future__ import annotations

from app.rights.models import ForgottenRight


def anotar_capacidade(right: ForgottenRight, serpro_configurado: bool) -> ForgottenRight:
    """Marca como a Nexa consegue verificar a fonte (real vs orientativo)."""
    if right.category == "svr_bacen":
        right.capability = "assisted_real"
        right.check_endpoint = "/api/v1/rights/{user_id}/svr/check"
    elif right.category == "ir_restituicao" and serpro_configurado:
        right.capability = "authorized_real"
        right.check_endpoint = "/api/v1/rights/{user_id}/ir/check"
    else:
        right.capability = "guided"
    return right


__all__ = ["anotar_capacidade"]
