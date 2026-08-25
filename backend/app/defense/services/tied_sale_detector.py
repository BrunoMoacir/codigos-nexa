"""
app/defense/services/tied_sale_detector.py — D1: Venda Casada

Detecta seguros embutidos e outros produtos vinculados ilegalmente a crédito.

Base legal:
  CDC art. 39, I — proíbe condicionar fornecimento de produto/serviço a outro.
  CDC art. 51 — nulidade de pleno direito de cláusulas abusivas.
  Súmula 297/STJ + ADI 2.591/STF — CDC aplica-se integralmente a bancos.
  Tema 972/STJ — abusividade do seguro prestamista quando não há liberdade
    de escolha da seguradora pelo consumidor.
  Res. CMN 3.919/2010, art. 2º — vedada a exigência ou vinculação de qualquer
    produto ou serviço como condição para concessão de crédito.

Detecção principal: correlação temporal entre crédito recebido e débito de
produto vinculado (seguro/capitalização/assistência) do mesmo banco em até 7 dias.
Exige confirmação do usuário antes de gerar achado definitivo.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date, timedelta

from app.defense.models import DefenseFinding

logger = logging.getLogger(__name__)

# Janela de correlação temporal crédito → produto vinculado (dias)
_CORRELATION_WINDOW_DAYS = 7

_TIED_FEE_TYPES = {
    "SEGURO_EMBUTIDO":    "Seguro embutido em produto de crédito (possível venda casada)",
    "SEGURO_PRESTAMISTA": "Seguro prestamista vinculado a crédito sem liberdade de escolha",
    "TARIFA_CADASTRO":    "Tarifa de cadastro sem contratação explícita",
}

_LEGAL_BASIS = (
    "CDC art. 39, I — proibida a venda casada (condicionar produto/serviço a outro). "
    "CDC art. 51 — nulidade de pleno direito de cláusulas abusivas. "
    "Tema 972/STJ — abusividade do seguro prestamista quando não há liberdade de escolha da seguradora. "
    "Res. CMN 3.919/2010, art. 2º — vedada vinculação de qualquer produto a crédito. "
    "Súmula 297/STJ + ADI 2.591/STF — CDC aplica-se às instituições financeiras."
)

_ACTION = (
    "1. Confirme se você escolheu livremente esse seguro/produto (pergunta no app).\n"
    "2. Solicite ao banco: contrato com sua assinatura e comprovante de liberdade de escolha da seguradora.\n"
    "3. Se não houver prova de adesão livre, solicite cancelamento imediato e reembolso retroativo.\n"
    "4. Se o banco negar, registre no Banco Central: bcb.gov.br/meubc.\n"
    "5. Para valores acumulados, acione o PROCON ou Juizado Especial Cível (gratuito até 20 SM, sem advogado)."
)

_DISCLAIMER_D1 = (
    "⚠️ Este achado é um PRÉ-INDÍCIO que requer confirmação. "
    "Se você contratou livremente este produto, arquive este achado."
)

# Palavras-chave de produtos vinculados a crédito
_CREDIT_PATTERNS = re.compile(
    r"\b(emprestimo|financiamento|credito|liberacao|credconsig|consig|pessoal|veicular|imob)\b",
    re.IGNORECASE,
)

_TIED_PRODUCT_PATTERNS = re.compile(
    r"\b(seguro|prestamista|capitalizacao|capitaliz|assistencia|protect|assisten|garantia)\b",
    re.IGNORECASE,
)


def _normalize(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


class TiedSaleDetector:
    """
    D1 — Detecta venda casada com duas estratégias:
    1. Correlação temporal: crédito recebido → produto vinculado do mesmo banco em ≤ 7 dias.
    2. Fee type: SEGURO_EMBUTIDO / SEGURO_PRESTAMISTA / TARIFA_CADASTRO no BankFeeAnalyzer.
    """

    def detect(self, user_id: str) -> list[DefenseFinding]:
        findings: list[DefenseFinding] = []
        findings.extend(self._check_temporal_correlation(user_id))
        findings.extend(self._check_fee_analyzer(user_id))
        findings.extend(self._check_fee_history(user_id))

        # Deduplica por banco + título
        seen: set[tuple[str, str]] = set()
        unique: list[DefenseFinding] = []
        for f in findings:
            key = (f.bank_name, f.title)
            if key not in seen:
                seen.add(key)
                unique.append(f)

        logger.info("[D1] user=%s → %d achados", user_id, len(unique))
        return unique

    # ── D1a: Correlação temporal crédito→produto vinculado ────────────

    def _check_temporal_correlation(self, user_id: str) -> list[DefenseFinding]:
        """
        Detecta: crédito positivo de banco X → débito de seguro/capitalização
        do mesmo banco X dentro de _CORRELATION_WINDOW_DAYS dias.
        Gera pré-finding com confidence 0.75 que exige confirmação do usuário.
        """
        try:
            from app.core.db.queries import get_transactions_for_user
            import polars as pl
            from collections import defaultdict

            df = get_transactions_for_user(user_id)
            if df.is_empty():
                return []

            desc_col  = "description" if "description" in df.columns else None
            date_col  = next((c for c in ("transaction_date", "date") if c in df.columns), None)
            amt_col   = "amount"      if "amount"      in df.columns else None

            if not all([desc_col, date_col, amt_col]):
                return []

            # `bank_name` NÃO existe em transactions_clean nem é devolvido por
            # get_transactions_for_user — a guarda que exigia essa coluna
            # zerava D1a em produção, e D1a é o caminho mais forte do detector:
            # um empréstimo de R$ 15 mil seguido de seguro prestamista três
            # dias depois (o caso do Tema 972/STJ) não gerava achado nenhum.
            #
            # A correlação é feita por CONTA, não por banco. Crédito caindo na
            # conta X e débito saindo da conta X é um vínculo mais apertado que
            # "mesmo banco" — e `account_id` está disponível. O nome legível vem
            # do enriquecimento do F5 quando dá para resolver; quando não dá, o
            # achado sai com rótulo genérico em vez de não sair.
            df = self._resolver_conta_e_banco(user_id, df)

            rows = df.iter_rows(named=True)
            credits: list[dict] = []
            debits:  list[dict] = []

            for row in rows:
                desc  = _normalize(row.get(desc_col, "") or "")
                chave = row.get("_chave_correlacao") or "conta"
                bank  = row.get("_banco_label") or "seu banco"
                amt   = row.get(amt_col, 0.0) or 0.0
                dt    = row.get(date_col)
                if not isinstance(dt, date):
                    continue

                if amt > 0 and _CREDIT_PATTERNS.search(desc):
                    credits.append({"chave": chave, "bank": bank, "date": dt,
                                    "amount": amt, "desc": desc[:80]})
                elif amt < 0 and _TIED_PRODUCT_PATTERNS.search(desc):
                    debits.append({"chave": chave, "bank": bank, "date": dt,
                                   "amount": abs(amt), "desc": desc[:80]})

            if not credits or not debits:
                return []

            findings = []
            seen_pairs: set[tuple[str, str, str]] = set()

            for credit in credits:
                window_end = credit["date"] + timedelta(days=_CORRELATION_WINDOW_DAYS)
                for debit in debits:
                    if debit["chave"] != credit["chave"]:
                        continue
                    if not (credit["date"] <= debit["date"] <= window_end):
                        continue

                    pair_key = (credit["chave"], str(credit["date"]), str(debit["date"]))
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)

                    days_diff = (debit["date"] - credit["date"]).days
                    annual_estimate = round(debit["amount"] * 12, 2)

                    findings.append(DefenseFinding(
                        detector="D1",
                        severity="high",
                        bank_name=credit["bank"],
                        title=f"Possível venda casada — seguro/produto vinculado a crédito ({credit['bank']})",
                        description=(
                            f"Detectamos crédito de R$ {credit['amount']:.2f} em {credit['date']} "
                            f"seguido de débito de produto vinculado (R$ {debit['amount']:.2f}) "
                            f"{days_diff} dia(s) depois — mesmo banco ({credit['bank']}). "
                            f"Isso é um indício de venda casada (Tema 972/STJ). "
                            f"CONFIRME: você escolheu livremente esse produto? "
                            f"{_DISCLAIMER_D1}"
                        ),
                        amount_disputed=annual_estimate,
                        legal_basis=_LEGAL_BASIS,
                        recommended_action=_ACTION,
                        evidence_points=[
                            f"Banco: {credit['bank']}",
                            f"Crédito: R$ {credit['amount']:.2f} em {credit['date']} — '{credit['desc']}'",
                            f"Produto vinculado: R$ {debit['amount']:.2f} em {debit['date']} — '{debit['desc']}'",
                            f"Intervalo: {days_diff} dia(s) (janela de correlação: {_CORRELATION_WINDOW_DAYS} dias)",
                            f"Estimativa anual do produto vinculado: R$ {annual_estimate:.2f}",
                            "Base: Tema 972/STJ — abusividade sem liberdade de escolha da seguradora",
                            "PRÉ-INDÍCIO — requer confirmação do usuário.",
                        ],
                    ))

            return findings
        except Exception as exc:
            logger.debug("[D1] _check_temporal_correlation: %s", exc)
            return []

    @staticmethod
    def _resolver_conta_e_banco(user_id: str, df):
        """
        Acrescenta `_chave_correlacao` (conta ou instituição) e `_banco_label`.

        A chave sai de `institution_id` quando o enriquecimento do F5 consegue
        resolver, e de `account_id` caso contrário. As duas amarram o crédito
        ao débito; a instituição só é melhor quando o usuário tem várias contas
        no mesmo banco.
        """
        import polars as pl

        from app.costs.fee_detector import INSTITUTION_ID_MAP, enriquecer_institution_id

        try:
            df = enriquecer_institution_id(user_id, df)
        except Exception as exc:
            logger.debug("[D1] enriquecimento de instituição: %s", exc)

        tem_inst = "institution_id" in df.columns
        tem_conta = "account_id" in df.columns

        if tem_inst:
            chave = pl.col("institution_id").cast(pl.Utf8).fill_null("")
            if tem_conta:
                chave = pl.when(chave == "").then(
                    pl.col("account_id").cast(pl.Utf8).fill_null("conta")
                ).otherwise(chave)
        elif tem_conta:
            chave = pl.col("account_id").cast(pl.Utf8).fill_null("conta")
        else:
            chave = pl.lit("conta")

        df = df.with_columns(chave.alias("_chave_correlacao"))

        if tem_inst:
            label = pl.col("institution_id").cast(pl.Utf8).str.to_lowercase().replace_strict(
                INSTITUTION_ID_MAP, default="seu banco"
            )
        else:
            label = pl.lit("seu banco")

        return df.with_columns(label.alias("_banco_label"))

    # ── D1b: Fee analyzer (snapshot atual) ───────────────────────────

    def _check_fee_analyzer(self, user_id: str) -> list[DefenseFinding]:
        try:
            from app.core.db.queries import get_transactions_for_user
            from app.costs.bank_fee_analyzer import BankFeeAnalyzer

            df = get_transactions_for_user(user_id)
            if df.is_empty():
                return []

            report = BankFeeAnalyzer().analyze(df, user_id=user_id)
            findings = []
            # `BankCostReport.entries` não existe — a lista de tarifas
            # individuais chama-se `fees_detected`. O AttributeError caía no
            # `except` deste método, que devolve [], então esta subverificação
            # NUNCA produziu um achado. Mesmo defeito que estava nas tools
            # `detect_abusive_fees`/`detect_wrongful_charges` do agente.
            for entry in report.fees_detected:
                fee_key = entry.fee_type.value
                if fee_key not in _TIED_FEE_TYPES:
                    continue
                findings.append(DefenseFinding(
                    detector="D1",
                    severity="high",
                    bank_name=entry.bank_name,
                    title=_TIED_FEE_TYPES[fee_key],
                    description=(
                        f"{entry.bank_name} cobrou R$ {entry.amount:.2f} "
                        f"em '{fee_key.replace('_', ' ').lower()}' detectado na análise de tarifas. "
                        f"{_DISCLAIMER_D1}"
                    ),
                    amount_disputed=float(entry.amount),
                    legal_basis=_LEGAL_BASIS,
                    recommended_action=_ACTION,
                    evidence_points=[
                        f"Tipo de tarifa: {fee_key}",
                        f"Valor: R$ {entry.amount:.2f}",
                        f"Banco: {entry.bank_name}",
                        entry.description or "",
                        "Tema 972/STJ — abusividade sem liberdade de escolha da seguradora.",
                    ],
                ))
            return findings
        except Exception as exc:
            logger.debug("[D1] _check_fee_analyzer: %s", exc)
            return []

    # ── D1c: Histórico bank_fee_history ──────────────────────────────

    def _check_fee_history(self, user_id: str) -> list[DefenseFinding]:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                rows = db.execute(
                    text(
                        "SELECT bank_name, fee_type, SUM(amount) as total, COUNT(*) as months"
                        " FROM bank_fee_history"
                        " WHERE user_id = :uid"
                        f"  AND fee_type IN ({', '.join(repr(k) for k in _TIED_FEE_TYPES)})"
                        " GROUP BY bank_name, fee_type"
                        " ORDER BY total DESC"
                    ),
                    {"uid": user_id},
                ).fetchall()

            findings = []
            for bank, ftype, total, months in rows:
                label = _TIED_FEE_TYPES.get(ftype, ftype)
                findings.append(DefenseFinding(
                    detector="D1",
                    severity="high",
                    bank_name=bank,
                    title=f"{label} — histórico de {months} mês(es)",
                    description=(
                        f"{bank} cobrou '{ftype.replace('_', ' ').lower()}' "
                        f"por {months} mês(es), total R$ {float(total):.2f}. "
                        f"{_DISCLAIMER_D1}"
                    ),
                    amount_disputed=round(float(total), 2),
                    legal_basis=_LEGAL_BASIS,
                    recommended_action=_ACTION,
                    evidence_points=[
                        f"Banco: {bank}",
                        f"Tipo: {ftype}",
                        f"Meses cobrados: {months}",
                        f"Total acumulado: R$ {float(total):.2f}",
                        "Tema 972/STJ — abusividade quando não há liberdade de escolha da seguradora.",
                        "PRÉ-INDÍCIO — confirme se você escolheu livremente este produto.",
                    ],
                ))
            return findings
        except Exception as exc:
            logger.debug("[D1] _check_fee_history: %s", exc)
            return []
