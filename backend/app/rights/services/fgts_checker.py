"""
app/rights/services/fgts_checker.py — FGTS Esquecido

Não existe API pública para consultar saldo FGTS por CPF sem autenticação
via GOV.BR / app FGTS (CEF). Este verificador é orientativo: detecta vínculo
CLT no extrato, dimensiona o DEPÓSITO mensal teórico como sinal de relevância
e manda o usuário ao canal oficial.

O que mudou, e por quê:

**O número não é mais valor a receber.** `salário × 8% × meses` é o depósito
do emprego ATIVO no período analisado — não é saldo, não é dinheiro esquecido
e, com contrato em vigor, não é sacável fora das hipóteses legais. Ia como
`estimated_amount` com confiança `medium`, entrava em
`total_estimated_recoverable` e virava promessa: uma pessoa de R$ 6.000/mês
via "R$ 2.400" num campo chamado "total recuperável". Agora vai em `sinal`,
com o rótulo do que é.

**O cálculo dependia de como o patrão parcelava o pagamento.** `months` era
`salary_rows.height` — o número de LINHAS — e a média era por lançamento. Com
a mesma renda de R$ 4.000/mês, quem recebia de uma vez via R$ 1.600 e quem
recebia adiantamento + salário via R$ 960. Agora a agregação é por mês, no
`ContextoTransacional`.

**A regex morta era a documentada.** `_CLT_KEYWORDS` era compilada e nunca
usada; o filtro real era uma regex inline diferente e mais pobre. Agora existe
uma só, em `contexto_transacional.PADRAO_SALARIO`.
"""

from __future__ import annotations

import logging

from app.rights.models import ForgottenRight, SinalDeRelevancia
from app.rights.parametros_legais import FGTS_ALIQUOTA_MENSAL, FGTS_FONTE
from app.rights.services.contexto_transacional import ContextoTransacional
from app.core.formatacao import brl

logger = logging.getLogger(__name__)


class FgtsChecker:
    """Detecta vínculo CLT e dimensiona o depósito de FGTS do período."""

    def check(self, user_id: str, ctx: ContextoTransacional | None = None) -> ForgottenRight:
        ctx = ctx if ctx is not None else ContextoTransacional.carregar(user_id)
        sinal, motivo = self._sinal(ctx)

        return ForgottenRight(
            category="fgts",
            title="FGTS — Fundo de Garantia por Tempo de Serviço",
            description=(
                "Saldo de contas FGTS de empregos anteriores (inclusive empresas extintas ou falidas). "
                "O FGTS pode ser sacado em demissão sem justa causa, aposentadoria, compra do imóvel "
                "ou doenças graves. Contas de empregos anteriores ficam ativas indefinidamente."
            ),
            estimated_amount=None,   # só consulta real preenche
            estimated_confidence="unknown",
            sinal=sinal,
            relevance_reason=motivo,
            official_channel="App FGTS (CEF) ou agência Caixa Econômica Federal",
            official_url="https://www.fgts.gov.br",
            action_steps=[
                "Baixe o app 'FGTS' da Caixa Econômica Federal (iOS/Android).",
                "Faça login com CPF e senha Caixa ou GOV.BR.",
                "Consulte 'Meus contratos' para ver contas ativas de empregos antigos.",
                "Para empresas extintas: vá presencialmente à agência CEF com CTPS e documentos.",
                "Saque-aniversário: avalie se a modalidade atual ainda é vantajosa para seu perfil.",
            ],
            warning=(
                "O valor acima é o DEPÓSITO estimado do seu vínculo atual no período "
                "analisado — não é saldo, não é dinheiro esquecido e, com contrato em "
                "vigor, o saque só ocorre nas hipóteses previstas em lei. O saldo real "
                "inclui correção (TR + 3% a.a.) desde cada depósito e só a Caixa tem o "
                "extrato completo."
            ) if sinal and sinal.valor else None,
        )

    @staticmethod
    def _sinal(ctx: ContextoTransacional) -> tuple[SinalDeRelevancia | None, str]:
        if not ctx.disponivel:
            return None, (
                "Sem transações disponíveis. Se teve empregos anteriores, consulte o "
                "app FGTS mesmo assim — contas antigas ficam ativas indefinidamente."
            )

        salario = ctx.salario_mensal_medio
        meses = ctx.meses_com_salario
        if not salario or meses == 0:
            return None, (
                "Padrão de salário CLT não identificado no extrato. Isso não significa "
                "que não haja FGTS: empregos anteriores continuam com conta ativa."
            )

        valor = round(salario * FGTS_ALIQUOTA_MENSAL * meses, 2)
        return (
            SinalDeRelevancia(
                valor=valor,
                rotulo="Depósitos de FGTS estimados no período analisado (não é saldo)",
                base=(
                    f"{brl(salario)}/mês × {FGTS_ALIQUOTA_MENSAL:.0%} × {meses} "
                    f"mês(es) com salário detectado ({ctx.janela}). {FGTS_FONTE}"
                ),
            ),
            (
                f"Salário CLT detectado em {meses} mês(es) do período {ctx.janela} "
                f"(média {brl(salario)}/mês) — vínculo formal gera depósito de FGTS."
            ),
        )
