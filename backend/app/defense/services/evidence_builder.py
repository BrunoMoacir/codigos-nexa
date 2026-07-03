"""
app/defense/services/evidence_builder.py — D5: Construtor de Dossiê

Monta o dossiê completo de evidências para PROCON/JEC a partir dos achados D1–D6.
Calcula correção monetária acumulando taxas mensais reais (IPCA/INPC/SELIC).

CORREÇÃO v2 (PDF V2 seção 4.1):
  - Série SGS 433 retorna variação MENSAL do IPCA (ex: 0,58%), NÃO acumulado anual.
    O código anterior usava 0,58 como taxa anual — isso subestima/superestima a correção.
  - Solução: acumular N meses de variação mensal para o período charge_date → hoje.
  - INPC: série 188 (mensal). Criar INPCConnector dedicado.
  - SELIC: série 432 (anual) — converter para diária corretamente.

Trilha de canais (escalar nesta ordem):
  SAC (5 du) → Ouvidoria (10 du) → Consumidor.gov.br → PROCON → JEC → Vara Cível
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Literal

from app.defense.models import (
    DefenseFinding,
    EvidenceDossier,
    MonetaryCorrection,
    CorrectionIndex,
)

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "AVISO LEGAL: Este documento foi gerado automaticamente pela Nexa AI com base em dados "
    "financeiros do usuário e fontes públicas do Banco Central do Brasil. "
    "As informações apresentadas constituem INDÍCIOS educacionais e organizacionais, "
    "NÃO constituindo parecer jurídico ou garantia de resultado. "
    "Recomenda-se consulta a advogado especializado antes de protocolar qualquer documento judicial. "
    "Os valores indicados são ESTIMATIVAS — o resultado real depende de análise do caso concreto."
)

_CHANNELS = (
    "TRILHA DE CANAIS — siga nesta ordem:\n"
    "1. SAC do banco (0800): prazo de 5 dias úteis — guarde o número de protocolo.\n"
    "2. Ouvidoria do banco: prazo de 10 dias úteis — exija resposta formal por escrito.\n"
    "3. Consumidor.gov.br: plataforma do Ministério da Justiça, acompanhe online.\n"
    "4. BACEN (bcb.gov.br/meubc): para reclamações sobre tarifas e juros de instituições financeiras.\n"
    "5. PROCON: gratuito, resolução em 30–60 dias.\n"
    "6. Juizado Especial Cível (JEC): gratuito, sem advogado até 20 SM (≈ R$ 28.200), "
    "com advogado até 40 SM (≈ R$ 56.400).\n"
    "7. Vara Cível comum: para valores acima de 40 SM — requer advogado."
)


class EvidenceBuilder:
    """
    D5 — Constrói dossiê de evidências com correção monetária acumulada mensalmente.
    """

    def build_dossier(
        self,
        user_id: str,
        findings: list[DefenseFinding],
        charge_date: date | None = None,
        correction_index: CorrectionIndex = "IPCA",
    ) -> EvidenceDossier:
        now = datetime.now(timezone.utc)
        total_disputed = round(sum(f.amount_disputed for f in findings), 2)

        monetary_correction: MonetaryCorrection | None = None
        if charge_date and total_disputed > 0:
            monetary_correction = self.calc_monetary_correction(
                original_value=total_disputed,
                charge_date=charge_date,
                reference_date=date.today(),
                index=correction_index,
            )
            corrected_total = monetary_correction.corrected_value
        else:
            corrected_total = total_disputed

        ctx = _Ctx(
            user_id=user_id,
            findings=findings,
            total_disputed=total_disputed,
            corrected_total=corrected_total,
            correction=monetary_correction,
            generated_at=now,
        )

        return EvidenceDossier(
            user_id=user_id,
            generated_at=now,
            findings=findings,
            total_findings=len(findings),
            total_disputed_amount=total_disputed,
            monetary_correction=monetary_correction,
            contestation_letter=_render_contestation_letter(ctx),
            procon_narrative=_render_procon_narrative(ctx),
            jec_petition=_render_jec_petition(ctx),
        )

    # ── Correção Monetária ────────────────────────────────────────────

    def calc_monetary_correction(
        self,
        original_value: float,
        charge_date: date,
        reference_date: date,
        index: CorrectionIndex = "IPCA",
    ) -> MonetaryCorrection:
        """
        Calcula correção monetária acumulando taxas mensais reais.

        IPCA/INPC: acumula variações mensais do SGS período a período.
        SELIC: usa taxa anual e converte para o período em dias.
        """
        months_used, factor = self._accumulate_index(index, charge_date, reference_date)
        corrected = round(original_value * factor, 2)

        return MonetaryCorrection(
            original_value=round(original_value, 2),
            charge_date=charge_date,
            reference_date=reference_date,
            index=index,
            correction_factor=round(factor, 6),
            corrected_value=corrected,
            correction_brl=round(corrected - original_value, 2),
            monthly_rates_used=months_used,
        )

    def _accumulate_index(
        self, index: CorrectionIndex, start: date, end: date
    ) -> tuple[int, float]:
        """
        Retorna (meses_acumulados, fator_total).
        IPCA/INPC: acumula taxas mensais reais da API.
        SELIC: converte taxa anual para diária e eleva ao período.
        """
        if index == "SELIC":
            return self._selic_factor(start, end)

        # IPCA ou INPC — acumula mensalmente
        series_id = 433 if index == "IPCA" else 188
        try:
            monthly_rates = _fetch_monthly_rates(series_id, start, end)
            if monthly_rates:
                factor = 1.0
                for r in monthly_rates:
                    factor *= (1 + r / 100)
                return len(monthly_rates), round(factor, 6)
        except Exception as exc:
            logger.debug("[D5] _accumulate_index %s: %s", index, exc)

        # Fallback: taxa anual histórica proporcional em dias
        days = max(0, (end - start).days)
        annual = 0.0512 if index == "IPCA" else 0.0560
        factor = (1 + annual) ** (days / 365) if days > 0 else 1.0
        return 0, round(factor, 6)

    @staticmethod
    def _selic_factor(start: date, end: date) -> tuple[int, float]:
        days = max(0, (end - start).days)
        try:
            from app.architect.connectors.bacen import BacenConnector
            rates = BacenConnector().get_rates()
            annual = rates.get("selic_annual", 0.1425)
        except Exception:
            annual = 0.1425  # fallback ago/2026
        factor = (1 + annual) ** (days / 365) if days > 0 else 1.0
        return 0, round(factor, 6)


    def build_zip_package(
        self,
        user_id: str,
        findings: list[DefenseFinding],
        charge_date: date | None = None,
        correction_index: CorrectionIndex = "IPCA",
    ) -> bytes:
        """
        Gera pacote ZIP com todos os documentos do dossiê (carta, PROCON, JEC, índice).
        Retorna bytes prontos para download.
        """
        import io
        import zipfile

        dossier = self.build_dossier(
            user_id=user_id,
            findings=findings,
            charge_date=charge_date,
            correction_index=correction_index,
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("00_LEIA_ME.txt", _INDEX_TEXT)
            zf.writestr("01_carta_contestacao.txt", dossier.contestation_letter)
            zf.writestr("02_relato_procon.txt", dossier.procon_narrative)
            zf.writestr("03_peticao_jec.txt", dossier.jec_petition)
            zf.writestr("04_resumo_achados.txt", _resumo_achados(dossier))

        buf.seek(0)
        return buf.read()


_INDEX_TEXT = """DOSSIÊ NEXA AI — PACOTE DE EVIDÊNCIAS
======================================
AVISO LEGAL: Documentos gerados como modelo educacional.
Preencha seus dados pessoais antes de protocolar.
Recomenda-se revisão por advogado antes do JEC.

Conteúdo:
  01_carta_contestacao.txt — carta para SAC/Ouvidoria do banco
  02_relato_procon.txt     — relato para PROCON ou Consumidor.gov.br
  03_peticao_jec.txt       — modelo de petição para Juizado Especial Cível
  04_resumo_achados.txt    — resumo dos indícios detectados

Trilha de canais recomendada:
  1. SAC (5 dias úteis)
  2. Ouvidoria (10 dias úteis)
  3. Consumidor.gov.br
  4. BACEN (bcb.gov.br/meubc)
  5. PROCON
  6. JEC (sem advogado até R$ 28.200)
"""


def _resumo_achados(dossier) -> str:
    lines = [
        "RESUMO DOS ACHADOS",
        f"Total de achados: {dossier.total_findings}",
        f"Valor estimado contestável: R$ {dossier.total_disputed_amount:.2f}",
        "",
    ]
    for f in dossier.findings:
        lines.append(
            f"[{f.detector} | {f.severity.upper()}] {f.bank_name}: {f.title} "
            f"— R$ {f.amount_disputed:.2f}"
        )
    return "\n".join(lines)


def _fetch_monthly_rates(series_id: int, start: date, end: date) -> list[float]:
    """Busca variações mensais do SGS BACEN para o período."""
    import httpx
    url = (
        f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series_id}/dados"
        f"?formato=json"
        f"&dataInicial={start.strftime('%d/%m/%Y')}"
        f"&dataFinal={end.strftime('%d/%m/%Y')}"
    )
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return [float(item["valor"]) for item in data if item.get("valor") not in (None, "")]


# ── Renderização dos documentos ───────────────────────────────────────

class _Ctx:
    __slots__ = (
        "user_id", "findings", "total_disputed", "corrected_total",
        "correction", "generated_at",
    )

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _findings_summary(ctx: _Ctx) -> str:
    if not ctx.findings:
        return "Nenhuma irregularidade identificada."
    return "\n".join(
        f"- [{f.detector} | {f.severity.upper()}] {f.bank_name}: {f.title} "
        f"— Estimativa contestável: R$ {f.amount_disputed:.2f}"
        for f in ctx.findings
    )


def _evidence_detail(ctx: _Ctx) -> str:
    if not ctx.findings:
        return "Sem achados."
    parts = []
    for i, f in enumerate(ctx.findings, 1):
        evs = "\n".join(f"    • {e}" for e in f.evidence_points if e)
        parts.append(
            f"{i}. {f.bank_name} — {f.title}\n"
            f"   Detector: {f.detector} | Severidade: {f.severity}\n"
            f"   {f.description}\n"
            f"   Evidências:\n{evs}\n"
            f"   Base legal: {f.legal_basis}\n"
            f"   Ação recomendada:\n   {f.recommended_action}"
        )
    return "\n\n".join(parts)


def _correction_text(ctx: _Ctx) -> str:
    if not ctx.correction:
        return "Correção monetária não solicitada."
    c = ctx.correction
    months_info = f" ({c.monthly_rates_used} meses acumulados)" if c.monthly_rates_used else ""
    return (
        f"Correção monetária ({c.index}{months_info}): "
        f"R$ {c.original_value:.2f} × {c.correction_factor:.4f} = "
        f"R$ {c.corrected_value:.2f} "
        f"(acréscimo de R$ {c.correction_brl:.2f} "
        f"no período de {c.charge_date.strftime('%d/%m/%Y')} "
        f"a {c.reference_date.strftime('%d/%m/%Y')})"
    )


def _banks(ctx: _Ctx) -> str:
    return ", ".join(dict.fromkeys(f.bank_name for f in ctx.findings)) or "N/A"


def _render_contestation_letter(ctx: _Ctx) -> str:
    return f"""CARTA DE CONTESTAÇÃO — IRREGULARIDADES BANCÁRIAS
Data: {ctx.generated_at.strftime('%d/%m/%Y')}
Referência: Análise Nexa AI | Usuário: {ctx.user_id}

{_DISCLAIMER}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ao [NOME DA INSTITUIÇÃO FINANCEIRA],
Setor: SAC / Ouvidoria
Assunto: Contestação de cobranças e irregularidades identificadas

Eu, [NOME COMPLETO], CPF [000.000.000-00], cliente desta instituição,
venho por meio desta carta contestar formalmente as seguintes
irregularidades identificadas em minha conta:

━━━━ RESUMO DOS ACHADOS ━━━━

{_findings_summary(ctx)}

Total estimado contestável: R$ {ctx.total_disputed:.2f}
{_correction_text(ctx)}
Total com correção monetária: R$ {ctx.corrected_total:.2f}

━━━━ DETALHAMENTO DAS IRREGULARIDADES ━━━━

{_evidence_detail(ctx)}

━━━━ FUNDAMENTO LEGAL ━━━━

Código de Defesa do Consumidor (Lei 8.078/1990), arts. 39, 42 e 51.
Súmula 297/STJ — CDC aplica-se às instituições financeiras.
Resolução CMN 3.919/2010 — tarifas e serviços bancários.
EAREsp 676.608/STJ — devolução em dobro para cobranças pós-30/03/2021.

━━━━ PEDIDOS ━━━━

1. Estorno imediato dos valores indevidamente cobrados.
2. Comprovante de notificação prévia de 30 dias para tarifas alteradas.
3. Contrato com assinatura para produtos contratados (seguros, etc.).
4. Resposta formal no prazo de 5 dias úteis (SAC) ou 10 dias úteis (Ouvidoria).

Em caso de não atendimento, registrarei reclamação no Banco Central
(bcb.gov.br/meubc), PROCON e, se necessário, no Juizado Especial Cível.

Atenciosamente,
[NOME COMPLETO]
[ENDEREÇO COMPLETO]
[E-MAIL]
[TELEFONE]
Data: {ctx.generated_at.strftime('%d/%m/%Y')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{_CHANNELS}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{_DISCLAIMER}
"""


def _render_procon_narrative(ctx: _Ctx) -> str:
    return f"""RELATO PARA PROCON / CONSUMIDOR.GOV.BR
Data: {ctx.generated_at.strftime('%d/%m/%Y')}
Usuário: {ctx.user_id} | Instituição(ões): {_banks(ctx)}

{_DISCLAIMER}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DESCRIÇÃO DO PROBLEMA:

Identifiquei as seguintes irregularidades em minha(s) conta(s) bancária(s):

{_findings_summary(ctx)}

VALOR TOTAL ESTIMADO: R$ {ctx.total_disputed:.2f}
{_correction_text(ctx)}
COM CORREÇÃO MONETÁRIA: R$ {ctx.corrected_total:.2f}

DETALHAMENTO:

{_evidence_detail(ctx)}

O QUE SOLICITEI À INSTITUIÇÃO:

Entrei em contato com o SAC/Ouvidoria da instituição financeira em [DATA],
protocolo nº [NÚMERO], e não obtive resposta satisfatória / não obtive resposta
no prazo legal.

O QUE PEÇO AO PROCON:

1. Instauração de procedimento administrativo contra a instituição.
2. Determinação de estorno dos valores indevidos com correção monetária.
3. Aplicação de multa conforme CDC art. 57, se cabível.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{_DISCLAIMER}
"""


def _render_jec_petition(ctx: _Ctx) -> str:
    # Valor da causa = total corrigido + juros de mora estimados (1% a.m. × meses estimados)
    estimated_months = 6
    mora = round(ctx.corrected_total * 0.01 * estimated_months, 2)
    valor_causa = round(ctx.corrected_total + mora, 2)

    return f"""MODELO DE PETIÇÃO INICIAL — JUIZADO ESPECIAL CÍVEL
(MODELO EDUCACIONAL — REVISAR COM ADVOGADO ANTES DE PROTOCOLAR)
Data: {ctx.generated_at.strftime('%d/%m/%Y')}

{_DISCLAIMER}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EXCELENTÍSSIMO(A) SENHOR(A) JUIZ(A) DO JUIZADO ESPECIAL CÍVEL
DA COMARCA DE [CIDADE/UF]

[NOME COMPLETO], [NACIONALIDADE], [ESTADO CIVIL], [PROFISSÃO],
portador(a) do RG nº [RG], inscrito(a) no CPF sob o nº [CPF],
residente e domiciliado(a) em [ENDEREÇO COMPLETO], CEP [CEP],
vem, respeitosamente, à presença de Vossa Excelência propor a presente

AÇÃO DE COBRANÇA COM PEDIDO DE REPETIÇÃO DO INDÉBITO
EM FACE DE [NOME DO BANCO], CNPJ nº [CNPJ DO BANCO],
com sede em [CIDADE/UF],

pelos fatos e fundamentos a seguir:

━━━━ I. DOS FATOS ━━━━

O(a) autor(a) é cliente da instituição ré e identificou as seguintes
irregularidades em seus extratos bancários:

{_findings_summary(ctx)}

{_evidence_detail(ctx)}

━━━━ II. DO DIREITO ━━━━

O Código de Defesa do Consumidor (Lei 8.078/1990) aplica-se às
instituições financeiras, conforme Súmula 297/STJ e ADI 2.591/STF.

O art. 42, parágrafo único, do CDC determina que o consumidor cobrado
em quantia indevida tem direito à repetição do indébito, por valor igual
ao dobro do que pagou em excesso, acrescido de correção monetária e
juros legais (para cobranças a partir de 30/03/2021 — EAREsp 676.608/STJ).

{_correction_text(ctx)}

━━━━ III. DO PEDIDO ━━━━

Ante o exposto, requer:

a) A condenação da ré ao pagamento de R$ {ctx.corrected_total:.2f} (total corrigido),
   acrescido de juros de mora de 1% ao mês a partir da citação;
b) Estimativa de juros de mora ({estimated_months} meses): R$ {mora:.2f};
c) VALOR DA CAUSA: R$ {valor_causa:.2f};
d) Condenação em honorários advocatícios e custas processuais, se cabível.

Dá-se à causa o valor de R$ {valor_causa:.2f}.

Termos em que, pede deferimento.
[CIDADE/UF], {ctx.generated_at.strftime('%d de %B de %Y')}

[ASSINATURA]
[NOME COMPLETO]
CPF: [CPF]

━━━━ DOCUMENTOS A ANEXAR ━━━━
□ Cópias dos extratos com as cobranças contestadas
□ Comprovante de tentativa de solução extrajudicial (protocolo SAC/Ouvidoria)
□ Cópia do RG e CPF
□ Comprovante de residência
□ Este dossiê Nexa AI (organização das evidências)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{_CHANNELS}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{_DISCLAIMER}
"""
