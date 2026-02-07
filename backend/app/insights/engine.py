"""
Engine de geração de insights financeiros.
Transforma números em mensagens úteis para o usuário.
"""

class InsightsEngine:

    def generate(self, *, forecast, safe_to_spend, profile, shadow_invoices):
        insights = []

        # Risco de saldo negativo
        if forecast.negative_day:
            insights.append(
                f"⚠️ Seu saldo ficará negativo em {forecast.negative_day} dias."
            )

        # Safe to spend
        if safe_to_spend.safe_to_spend > 0:
            insights.append(
                f"💡 Você pode gastar até R$ {safe_to_spend.safe_to_spend:.2f} sem comprometer sua segurança financeira."
            )
        else:
            insights.append(
                "🚨 Você não tem margem segura para gastos no momento."
            )

        # Perfil financeiro
        insights.append(
            f"📊 Seu perfil financeiro atual é: {profile.profile_type}."
        )

        # Shadow invoices
        if shadow_invoices.total > 0:
            insights.append(
                f"📌 Você possui {shadow_invoices.total} obrigações futuras mapeadas."
            )

        return insights
