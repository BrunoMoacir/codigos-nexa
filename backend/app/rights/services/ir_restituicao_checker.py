"""
app/rights/services/ir_restituicao_checker.py — Restituição de Imposto de Renda

Escaneia o extrato em busca de IRRF retido para dimensionar relevância e
orienta a consulta real. A consulta de verdade existe e está a um endpoint de
distância: `POST /rights/{user_id}/ir/check`, com token do e-CAC (SERPRO).

Três defeitos corrigidos:

1. **IRRF retido não é restituição.** O total retido ia como
   `estimated_amount` com confiança `medium` e entrava em
   `total_estimated_recoverable`. Quem ganha R$ 6.000/mês e teve R$ 9.900
   retidos no ano via "R$ 9.900" num campo chamado "total recuperável" —
   quando o mais provável é que deva exatamente o que foi retido e receba
   R$ 0. Agora vai em `sinal`, com o rótulo correto.

2. **A soma misturava os sinais.** `abs(ir_rows["amount"].sum())` somava
   débito de retenção com crédito de restituição JÁ RECEBIDA: seis retenções
   de R$ 500 mais uma restituição de R$ 4.000 davam "R$ 1.000 de IRRF
   retido". Agora só débitos entram.

3. **A faixa de isenção era de 2024.** `28_559.70` anuais. Desde 01/2026 a
   isenção é de R$ 5.000/mês (Lei 15.270/2025) — quem ganha R$ 3.000/mês era
   informado de que estava "acima do limite de isenção, provável IR retido na
   fonte", com R$ 2.700 estimados. O parâmetro agora vem de
   `parametros_legais`, datado, com um teste que quebra quando o ano vira.

A regex também era duas: `_IR_KEYWORDS` compilada e nunca usada, e uma inline
mais pobre no filtro. A inline não casava "IMPOSTO DE RENDA RETIDO NA FONTE".
Agora há uma só, em `contexto_transacional.PADRAO_IRRF`.
"""

from __future__ import annotations

import logging

from app.rights.models import ForgottenRight, SinalDeRelevancia
from app.rights.parametros_legais import (
    IRPF_FONTE,
    IRPF_ISENCAO_MENSAL,
    irpf_isencao_anual,
)
from app.rights.services.contexto_transacional import ContextoTransacional
from app.core.formatacao import brl

logger = logging.getLogger(__name__)

_DEDUCOES_COMUNS = [
    "Despesas médicas (plano de saúde, consultas, exames)",
    "Previdência privada PGBL (até 12% da renda bruta)",
    "Dependentes (filhos, cônjuge, pais em certas condições)",
    "Despesas educacionais (dentro do teto anual por dependente)",
    "Contribuição ao INSS (automaticamente deduzida)",
]


class IrRestituicaoChecker:
    """Dimensiona o IRRF retido e orienta a consulta real da restituição."""

    def check(self, user_id: str, ctx: ContextoTransacional | None = None) -> ForgottenRight:
        ctx = ctx if ctx is not None else ContextoTransacional.carregar(user_id)
        sinal, motivo = self._sinal(ctx)

        return ForgottenRight(
            category="ir_restituicao",
            title="Restituição de Imposto de Renda (IRPF)",
            description=(
                "IR retido na fonte acima do devido é restituído após a entrega da declaração anual. "
                "Despesas dedutíveis frequentemente esquecidas aumentam a restituição. "
                "Restituições não resgatadas ficam disponíveis por 5 anos."
            ),
            estimated_amount=None,
            estimated_confidence="unknown",
            sinal=sinal,
            relevance_reason=motivo,
            official_channel="App Meu Imposto de Renda (Receita Federal) · e-CAC",
            official_url="https://www.gov.br/receitafederal/pt-br/assuntos/meu-imposto-de-renda",
            action_steps=[
                "Consulte o VALOR REAL pela Nexa: gere uma Autorização de Compartilhamento "
                "no e-CAC (Compartilha Receita Federal) e cole o token no app.",
                "Alternativa: baixe o app 'Meu Imposto de Renda' (iOS/Android) ou acesse o e-CAC.",
                "Consulte o extrato da declaração para ver se há restituição pendente.",
                "Se constar 'em análise' há mais de 60 dias, acesse 'Consultar Impugnação/Autuação'.",
                "Verifique deduções esquecidas: " + " · ".join(_DEDUCOES_COMUNS[:3]) + ".",
                "Restituições de até 5 anos anteriores podem ser recuperadas se a declaração foi entregue.",
            ],
            warning=(
                "O valor acima é o imposto RETIDO, não o que você tem a receber. A "
                "restituição depende das deduções da sua declaração e pode ser zero — ou "
                "pode haver saldo a pagar. O número real está na consulta do e-CAC."
            ) if sinal and sinal.valor else None,
        )

    @staticmethod
    def _sinal(ctx: ContextoTransacional) -> tuple[SinalDeRelevancia | None, str]:
        if not ctx.disponivel:
            return None, (
                "Sem transações disponíveis. Consulte a restituição no app Meu Imposto "
                "de Renda ou pela consulta real da Nexa (token do e-CAC)."
            )

        if ctx.irrf_retido > 0:
            return (
                SinalDeRelevancia(
                    valor=ctx.irrf_retido,
                    rotulo="IRRF retido detectado no período (não é o valor da restituição)",
                    base=(
                        f"Soma de {ctx.irrf_lancamentos} débito(s) com descrição de imposto "
                        f"retido no período {ctx.janela}. Restituição = imposto retido − "
                        f"imposto devido após deduções; pode ser zero."
                    ),
                ),
                (
                    f"Detectados {ctx.irrf_lancamentos} lançamento(s) de IRRF no período "
                    f"{ctx.janela} ({brl(ctx.irrf_retido)} retidos) — vale conferir se "
                    "há restituição."
                ),
            )

        renda_anual = ctx.renda_anual
        if renda_anual and renda_anual > irpf_isencao_anual():
            mensal = round(renda_anual / max(ctx.meses_com_renda, 1), 2)
            return None, (
                f"Renda média de {brl(mensal)}/mês no período {ctx.janela} — acima da "
                f"faixa de isenção ({brl(IRPF_ISENCAO_MENSAL)}/mês). Não detectamos "
                f"IRRF no extrato, mas pode haver retenção na folha. {IRPF_FONTE}"
            )

        return None, (
            f"Nenhum IRRF detectado no período {ctx.janela} e renda dentro da faixa de "
            f"isenção ({brl(IRPF_ISENCAO_MENSAL)}/mês). Se declarou em anos anteriores, "
            "ainda pode haver restituição não resgatada — o prazo é de 5 anos."
        )
