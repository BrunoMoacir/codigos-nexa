"""
app/defense/services/evidence_builder.py — D5: Construtor de Dossiê

Monta o dossiê completo de evidências para PROCON/JEC a partir dos achados D1-D4.
Calcula correção monetária via IpcaConnector (SGS 433) ou SELIC como fallback.

Templates: backend/templates/contestation_letter.md
           backend/templates/procon_dossier.md
           backend/templates/jec_petition.md
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from app.defense.models import (
    DefenseFinding,
    EvidenceDossier,
    MonetaryCorrection,
    CorrectionIndex,
)

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parents[4] / "templates"


class EvidenceBuilder:
    """
    D5 — Constrói dossiê de evidências e calcula correção monetária.

    Uso:
        builder = EvidenceBuilder()
        dossier = builder.build_dossier(user_id, findings, charge_date=date(2025, 1, 1))
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

        # Correção monetária sobre o total (opcional — só se charge_date informada)
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

        # Renderiza templates
        ctx = _TemplateContext(
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
            contestation_letter=_render_template("contestation_letter.md", ctx),
            procon_narrative=_render_template("procon_dossier.md", ctx),
            jec_petition=_render_template("jec_petition.md", ctx),
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
        Calcula correção monetária proporcional ao prazo.

        Fórmula: corrected = original × (1 + annual_rate) ^ (days / 365)
        Usa IpcaConnector (SGS 433) para IPCA ou BacenConnector (SELIC) para SELIC.
        INPC não possui conector dedicado — usa IPCA como proxy.
        """
        days = max(0, (reference_date - charge_date).days)
        annual_rate = self._get_annual_rate(index)
        factor = (1 + annual_rate) ** (days / 365) if days > 0 else 1.0
        corrected = round(original_value * factor, 2)

        return MonetaryCorrection(
            original_value=round(original_value, 2),
            charge_date=charge_date,
            reference_date=reference_date,
            index=index,
            correction_factor=round(factor, 6),
            corrected_value=corrected,
            correction_brl=round(corrected - original_value, 2),
        )

    @staticmethod
    def _get_annual_rate(index: CorrectionIndex) -> float:
        if index in ("IPCA", "INPC"):
            try:
                from app.architect.connectors.ipca import IpcaConnector
                return IpcaConnector().get_ipca()
            except Exception as exc:
                logger.debug("[D5] IpcaConnector fallback: %s", exc)
                return 0.0512  # IPCA histórico ~5.1%
        else:  # SELIC
            try:
                from app.architect.connectors.bacen import BacenConnector
                rates = BacenConnector().get_rates()
                return rates.get("selic_annual", 0.1525)
            except Exception as exc:
                logger.debug("[D5] BacenConnector fallback: %s", exc)
                return 0.1525


# ── Template rendering ────────────────────────────────────────────────

class _TemplateContext:
    __slots__ = (
        "user_id", "findings", "total_disputed", "corrected_total",
        "correction", "generated_at",
    )

    def __init__(
        self,
        user_id: str,
        findings: list[DefenseFinding],
        total_disputed: float,
        corrected_total: float,
        correction: MonetaryCorrection | None,
        generated_at: datetime,
    ) -> None:
        self.user_id = user_id
        self.findings = findings
        self.total_disputed = total_disputed
        self.corrected_total = corrected_total
        self.correction = correction
        self.generated_at = generated_at


def _render_template(filename: str, ctx: _TemplateContext) -> str:
    template_path = _TEMPLATES_DIR / filename
    try:
        template = template_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"[Template {filename} não encontrado em {_TEMPLATES_DIR}]"

    # Resumo dos achados para o template
    findings_summary = "\n".join(
        f"- **{f.bank_name}** ({f.detector} — {f.severity}): {f.title} "
        f"| Valor contestado: R$ {f.amount_disputed:.2f}"
        for f in ctx.findings
    ) or "Nenhum achado identificado."

    evidence_detail = "\n\n".join(
        f"**{i+1}. {f.bank_name} — {f.title}**\n"
        f"{f.description}\n\n"
        f"*Evidências:*\n" + "\n".join(f"  - {e}" for e in f.evidence_points if e) + "\n\n"
        f"*Base legal:* {f.legal_basis}\n\n"
        f"*Ação recomendada:*\n{f.recommended_action}"
        for i, f in enumerate(ctx.findings)
    ) or "Sem achados."

    correction_text = ""
    if ctx.correction:
        c = ctx.correction
        correction_text = (
            f"Correção monetária ({c.index}): "
            f"R$ {c.original_value:.2f} × {c.correction_factor:.4f} = "
            f"R$ {c.corrected_value:.2f} "
            f"(acréscimo de R$ {c.correction_brl:.2f} "
            f"para o período de {c.charge_date} a {c.reference_date})"
        )

    return template.format(
        user_id=ctx.user_id,
        generated_at=ctx.generated_at.strftime("%d/%m/%Y"),
        total_findings=len(ctx.findings),
        total_disputed=f"{ctx.total_disputed:.2f}",
        corrected_total=f"{ctx.corrected_total:.2f}",
        findings_summary=findings_summary,
        evidence_detail=evidence_detail,
        correction_text=correction_text or "Correção monetária não calculada.",
        banks_involved=", ".join(dict.fromkeys(f.bank_name for f in ctx.findings)) or "N/A",
    )
