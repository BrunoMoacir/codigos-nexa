"""
app/rights/services/pis_pasep_checker.py — PIS/PASEP Esquecido

Cotas do fundo PIS (setor privado) ou PASEP (setor público), especialmente
para quem trabalhou com carteira assinada antes de 04/10/1988, e o abono
salarial anual.

Não existe API pública de saldo PIS/PASEP por CPF. O que a Nexa faz é dizer
se a RENDA do usuário cabe no teto do abono — um dos requisitos — e mostrar os
outros três, que dependem de dados que ela não tem.

Três defeitos corrigidos aqui, todos apontando para o mesmo lado (dizer "sim"
para quem não tem direito):

1. **O teto estava 2,6× maior que o real.** `_ABONO_SALARIAL_TETO = 5 * 1412.0`
   = R$ 7.060. O critério nunca foi 5 salários mínimos, e sim 2; e R$ 1.412 é
   o mínimo de 2024. No calendário 2026 o teto é R$ 2.765,93, já desvinculado
   do salário mínimo. Agora vem de `parametros_legais`, com fonte e vigência.

2. **A "renda média mensal" era a média por TRANSAÇÃO.**
   `income["amount"].mean()`. Quem ganhava R$ 12.000/mês e recebia 60 Pix
   pequenos aparecia com "renda média R$ 1.901,41/mês" e era declarado
   elegível. Agora a renda mensal vem do `ContextoTransacional`, somada por
   mês e promediada entre meses.

3. **`_estimate_abono` era uma constante disfarçada de cálculo.** Os dois
   ramos devolviam o salário mínimo cheio, para qualquer renda, porque
   `months_worked` era fixado em 12. O valor entrava em
   `total_estimated_recoverable` com confiança `medium`. Agora o cálculo é
   proporcional de verdade (`abono_proporcional`) e sai como SINAL, com os
   requisitos que não podemos verificar declarados ao lado.
"""

from __future__ import annotations

import logging

from app.rights.models import ForgottenRight, SinalDeRelevancia
from app.rights.parametros_legais import (
    ABONO_ANO_BASE,
    ABONO_FONTE,
    ABONO_REQUISITOS_NAO_VERIFICAVEIS,
    ABONO_TETO_REMUNERACAO_MENSAL,
    abono_proporcional,
)
from app.rights.services.contexto_transacional import ContextoTransacional
from app.core.formatacao import brl

logger = logging.getLogger(__name__)


class PisPasepChecker:
    """Orienta sobre cotas PIS/PASEP e sobre o teto de renda do abono."""

    def check(self, user_id: str, ctx: ContextoTransacional | None = None) -> ForgottenRight:
        ctx = ctx if ctx is not None else ContextoTransacional.carregar(user_id)
        sinal, motivo = self._sinal(ctx)

        return ForgottenRight(
            category="pis_pasep",
            title="PIS/PASEP — Cotas e Abono Salarial",
            description=(
                "PIS (trabalhador setor privado) ou PASEP (setor público): "
                "cotas acumuladas de quem trabalhou com carteira assinada ANTES de 04/10/1988 "
                "podem estar esquecidas. Além disso, quem trabalhou com carteira assinada e teve "
                f"remuneração média mensal de até {brl(ABONO_TETO_REMUNERACAO_MENSAL)} em "
                f"{ABONO_ANO_BASE} pode ter direito ao Abono Salarial."
            ),
            estimated_amount=None,
            estimated_confidence="unknown",
            sinal=sinal,
            relevance_reason=motivo,
            official_channel="Caixa Econômica (PIS) · Banco do Brasil (PASEP) · Gov.br",
            official_url="https://www.gov.br/pt-br/servicos/consultar-pis-pasep",
            action_steps=[
                "Abono Salarial: confirme direito e data no app Carteira de Trabalho Digital "
                "ou no portal gov.br — só lá constam os dados da RAIS/eSocial.",
                "PIS: acesse o app Caixa Tem ou vá a uma agência CEF com CPF e CTPS.",
                "PASEP: acesse o Banco do Brasil (agência ou app) com CPF.",
                "Cotas pré-1988: se trabalhou com carteira assinada antes de 04/10/1988, consulte o BB ou CEF — "
                "esses valores têm correção histórica e podem ser significativos.",
                "Trabalhadores que nunca sacaram há mais de 10 anos devem ligar para 0800-726-0207 (CEF).",
            ],
            warning=(
                "Cotas PIS/PASEP pré-1988 têm correção especial (BTN + 3% a.a.). "
                "O valor real só pode ser consultado presencialmente ou via app oficial."
            ),
        )

    @staticmethod
    def _sinal(ctx: ContextoTransacional) -> tuple[SinalDeRelevancia | None, str]:
        requisitos = " ".join(f"({i+1}) {r}" for i, r in enumerate(ABONO_REQUISITOS_NAO_VERIFICAVEIS))

        if not ctx.disponivel:
            return None, (
                "Sem transações disponíveis para avaliar o teto de renda do abono. "
                f"Confira no gov.br: {requisitos}"
            )

        renda = ctx.renda_mensal_media
        if renda is None:
            return None, "Sem créditos detectados no período analisado."

        if renda > ABONO_TETO_REMUNERACAO_MENSAL:
            return None, (
                f"Renda média de {brl(renda)}/mês no período {ctx.janela} — acima do "
                f"teto do abono ({brl(ABONO_TETO_REMUNERACAO_MENSAL)}). Ainda vale "
                "verificar cotas PIS/PASEP anteriores a 04/10/1988."
            )

        # Cabe no teto de RENDA — que é apenas um dos quatro requisitos. Os
        # meses com salário CLT detectado são o melhor proxy disponível para a
        # proporcionalidade; não são os meses da RAIS.
        meses = ctx.meses_com_salario or ctx.meses_com_renda
        valor = abono_proporcional(meses)
        return (
            SinalDeRelevancia(
                valor=valor,
                rotulo="Valor do abono SE você cumprir os demais requisitos",
                base=(
                    f"{meses}/12 do salário mínimo vigente, proporcional aos meses com "
                    f"vínculo detectado. A Nexa só consegue verificar o teto de renda — "
                    f"os outros requisitos são: {requisitos} {ABONO_FONTE}"
                ),
            ),
            (
                f"Renda média de {brl(renda)}/mês no período {ctx.janela} — dentro do "
                f"teto do abono ({brl(ABONO_TETO_REMUNERACAO_MENSAL)}). Isso é um dos "
                f"quatro requisitos; confirme os outros no gov.br."
            ),
        )
