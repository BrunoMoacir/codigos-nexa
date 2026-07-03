"""
app/defense/services/wrongful_charge_detector.py — D2: Cobranças Indevidas

Detecta:
  - Tarifas duplicadas no mesmo mês
  - Cobranças sobre serviços essenciais obrigatoriamente gratuitos
  - Cobranças de bancos sem transações recentes (conta possivelmente encerrada)
  - Tarifas novas sem histórico anterior

Base legal:
  CDC art. 42, parágrafo único — vedada cobrança de dívida já paga ou indevida.
  EAREsp 676.608/STJ — devolução em dobro independe de má-fé para cobranças
    indevidas A PARTIR de 30/03/2021 (modula anteriores para restituição simples).
  Res. CMN 3.919/2010, art. 7º — serviços essenciais obrigatoriamente gratuitos.
  Res. CMN 3.919/2010, art. 3º — alterações de tarifas exigem aviso prévio de 30 dias.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date, timedelta

from app.defense.models import DefenseFinding

logger = logging.getLogger(__name__)

# Data de corte do EAREsp 676.608/STJ para restituição em dobro
_DATA_CORTE_DOBRO = date(2021, 3, 30)

_LEGAL_BASIS_D2 = (
    "CDC art. 42, parágrafo único — vedada cobrança de valor já pago ou indevido. "
    "EAREsp 676.608/STJ — devolução em dobro independe de má-fé para cobranças "
    "indevidas a partir de 30/03/2021; antes disso, restituição simples. "
    "Súmula 297/STJ — CDC aplica-se às instituições financeiras."
)

_LEGAL_BASIS_ESSENCIAIS = (
    "Res. CMN 3.919/2010, art. 7º — serviços essenciais são obrigatoriamente gratuitos "
    "para contas de depósito à vista e poupança de pessoas físicas. "
    "CDC art. 42, parágrafo único — cobrança indevida; valor contestável conforme data."
)

_ACTION_DUPLICATA = (
    "1. Reúna o extrato com os lançamentos duplicados (mesmo tipo, mesmo mês).\n"
    "2. Abra reclamação formal no banco — exija número de protocolo.\n"
    "3. Se não resolvido em 5 dias úteis: Banco Central (bcb.gov.br/meubc) ou PROCON.\n"
    "4. Para valores acima de R$ 20: Juizado Especial Cível (gratuito, sem advogado até 20 SM)."
)

_ACTION_ESSENCIAL = (
    "1. Identifique o tipo de serviço cobrado (saque, extrato, consulta de saldo).\n"
    "2. Verifique se está dentro da franquia gratuita mensal da sua conta.\n"
    "3. Se dentro da franquia: exija estorno imediato — é direito garantido por lei.\n"
    "4. Guarde o extrato como prova e registre no SAC/ouvidoria."
)

_ACTION_INATIVA = (
    "1. Verifique se a conta foi de fato encerrada — solicite certidão de encerramento.\n"
    "2. Exija estorno de todas as cobranças após a data de encerramento.\n"
    "3. Se o banco persistir, acione o BACEN e PROCON com o histórico de cobranças."
)

_ACTION_NOVA_TARIFA = (
    "1. Solicite ao banco o contrato ou aditivo que prevê essa tarifa.\n"
    "2. Exija comprovante de notificação enviada com 30 dias de antecedência.\n"
    "3. Se não houver notificação prévia, solicite estorno e registre no BACEN."
)

# ── Serviços essenciais gratuitos (Res. CMN 3.919/2010, art. 7º) ──────
# Mapeamento: padrão de descrição → (nome, franquia mensal, tipo)
_ESSENTIAL_SERVICES = {
    # Saques — até 4/mês na rede própria
    "saque": {
        "name": "saque em caixa eletrônico (rede própria)",
        "monthly_limit": 4,
        "patterns": [
            r"\bsaque\b", r"\bsaq\b", r"\bwithdraw\b", r"\btar[\s_]saq",
        ],
    },
    # Extratos — até 4/mês
    "extrato": {
        "name": "fornecimento de extrato",
        "monthly_limit": 4,
        "patterns": [
            r"\bextrato\b", r"\btar[\s_]ext", r"\bext[\s_]conta\b",
        ],
    },
    # Transferências mesma IF — até 2/mês
    "transferencia_interna": {
        "name": "transferência entre contas da mesma IF",
        "monthly_limit": 2,
        "patterns": [
            r"\btar[\s_]transf\b", r"\btef[\s_]prop", r"\btransf[\s_]int",
        ],
    },
    # Cartão de débito — emissão da 1ª via
    "cartao_debito": {
        "name": "emissão de cartão de débito (1ª via)",
        "monthly_limit": None,  # evento único
        "patterns": [
            r"\btar[\s_]cartao[\s_]deb", r"\bemissao[\s_]cartao\b",
            r"\bcartao[\s_]deb", r"\banuidade[\s_]deb",
        ],
    },
    # Consulta de saldo — ilimitado
    "consulta_saldo": {
        "name": "consulta de saldo (caixa eletrônico da rede própria)",
        "monthly_limit": None,  # ilimitado = nunca deve cobrar
        "patterns": [
            r"\btar[\s_]consul", r"\bconsulta[\s_]saldo\b", r"\bsaldo[\s_]atm\b",
        ],
    },
    # PIX recebimento PF — cobrança indevida para pessoa física
    "pix_recebimento_pf": {
        "name": "tarifa de recebimento Pix (pessoa física)",
        "monthly_limit": None,  # PF não deve pagar para receber Pix em uso pessoal
        "patterns": [
            r"\btar[\s_]pix[\s_]rec", r"\bpix[\s_]recebimento\b",
            r"\brecebimento[\s_]pix\b", r"\btar[\s_]rec[\s_]pix",
        ],
    },
}


def _normalize(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def _multiplicador_dobro(charge_date: date) -> float:
    """
    Aplica regra do dobro conforme EAREsp 676.608/STJ.
    Cobranças >= 30/03/2021 → 2,0x  |  antes → 1,0x
    """
    return 2.0 if charge_date >= _DATA_CORTE_DOBRO else 1.0


def _dobro_label(charge_date: date) -> str:
    if charge_date >= _DATA_CORTE_DOBRO:
        return "em dobro (EAREsp 676.608/STJ — cobrança pós-30/03/2021)"
    return "simples (cobrança anterior a 30/03/2021 — restituição sem dobro)"


class WrongfulChargeDetector:
    """D2 — Detecta cobranças indevidas com regra do dobro e serviços essenciais."""

    _STALE_DAYS = 60

    def detect(self, user_id: str) -> list[DefenseFinding]:
        findings: list[DefenseFinding] = []
        findings.extend(self._check_duplicates(user_id))
        findings.extend(self._check_essential_services(user_id))
        findings.extend(self._check_stale_banks(user_id))
        findings.extend(self._check_new_fees(user_id))
        logger.info("[D2] user=%s → %d achados", user_id, len(findings))
        return findings

    # ── D2a: Duplicatas ───────────────────────────────────────────────

    def _check_duplicates(self, user_id: str) -> list[DefenseFinding]:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            current_month = date.today().strftime("%Y-%m")
            # Usa primeiro dia do mês corrente como data de referência para dobro
            ref_date = date.today().replace(day=1)
            mult = _multiplicador_dobro(ref_date)
            dobro_label = _dobro_label(ref_date)

            with SessionLocal() as db:
                rows = db.execute(
                    text(
                        "SELECT bank_name, fee_type, COUNT(*) as cnt, SUM(amount) as total"
                        " FROM bank_fee_history"
                        " WHERE user_id = :uid AND month = :month"
                        " GROUP BY bank_name, fee_type"
                        " HAVING COUNT(*) > 1"
                        " ORDER BY total DESC"
                    ),
                    {"uid": user_id, "month": current_month},
                ).fetchall()

            findings = []
            for bank, ftype, cnt, total in rows:
                total_f = float(total)
                excedente = round(total_f * (cnt - 1) / cnt, 2)
                contestavel = round(excedente * mult, 2)

                findings.append(DefenseFinding(
                    detector="D2",
                    severity="high",
                    bank_name=bank,
                    title=f"Tarifa duplicada — {ftype.replace('_', ' ')} ({cnt}x)",
                    description=(
                        f"{bank} cobrou '{ftype.replace('_', ' ').lower()}' "
                        f"{cnt}x no mesmo mês (total R$ {total_f:.2f}). "
                        f"Apenas 1 cobrança deveria ocorrer. "
                        f"Valor contestável: R$ {excedente:.2f} — "
                        f"estimativa {dobro_label} = R$ {contestavel:.2f}."
                    ),
                    amount_disputed=contestavel,
                    legal_basis=_LEGAL_BASIS_D2,
                    recommended_action=_ACTION_DUPLICATA,
                    evidence_points=[
                        f"Mês: {current_month}",
                        f"Banco: {bank}",
                        f"Tipo de tarifa: {ftype}",
                        f"Ocorrências no mês: {cnt}x",
                        f"Total cobrado: R$ {total_f:.2f}",
                        f"Excedente indevido (base): R$ {excedente:.2f}",
                        f"Estimativa contestável ({dobro_label}): R$ {contestavel:.2f}",
                    ],
                ))
            return findings
        except Exception as exc:
            logger.debug("[D2] _check_duplicates: %s", exc)
            return []

    # ── D2b: Serviços essenciais gratuitos (CMN 3.919/2010 art. 7º) ───

    def _check_essential_services(self, user_id: str) -> list[DefenseFinding]:
        try:
            from app.core.db.queries import get_transactions_for_user
            import polars as pl
            from collections import defaultdict

            df = get_transactions_for_user(user_id)
            if df.is_empty():
                return []

            desc_col = "description" if "description" in df.columns else None
            bank_col  = "bank_name"  if "bank_name"  in df.columns else None
            date_col  = next((c for c in ("transaction_date", "date") if c in df.columns), None)
            amt_col   = "amount"     if "amount"      in df.columns else None

            if not desc_col or not amt_col:
                return []

            # Compila padrões
            compiled: dict[str, list] = {
                svc_key: [re.compile(p, re.IGNORECASE) for p in svc["patterns"]]
                for svc_key, svc in _ESSENTIAL_SERVICES.items()
            }

            # Acumula cobranças suspeitas por serviço + banco
            hits: dict[tuple[str, str], list[dict]] = defaultdict(list)

            for row in df.filter(pl.col(amt_col) < 0).iter_rows(named=True):
                desc_raw = row.get(desc_col, "") or ""
                desc_norm = _normalize(desc_raw)
                bank = row.get(bank_col, "Banco") if bank_col else "Banco"
                amount = abs(row.get(amt_col, 0.0))
                row_date = row.get(date_col) if date_col else None

                for svc_key, patterns in compiled.items():
                    if any(p.search(desc_norm) for p in patterns):
                        hits[(svc_key, bank)].append({
                            "desc": desc_raw[:80],
                            "amount": amount,
                            "date": row_date,
                        })
                        break

            if not hits:
                return []

            findings = []
            for (svc_key, bank), ocorrencias in hits.items():
                svc = _ESSENTIAL_SERVICES[svc_key]
                total = sum(o["amount"] for o in ocorrencias)
                count = len(ocorrencias)

                # Para serviços com franquia: só contesta se exceder o limite
                limit = svc.get("monthly_limit")
                if limit is not None and count <= limit:
                    continue  # dentro da franquia gratuita

                # Calcula contestável com regra do dobro
                ref_date = (
                    ocorrencias[0]["date"]
                    if ocorrencias[0]["date"] and isinstance(ocorrencias[0]["date"], date)
                    else date.today()
                )
                mult = _multiplicador_dobro(ref_date)
                contestavel = round(total * mult, 2)
                dobro_label = _dobro_label(ref_date)

                limit_text = (
                    f"(franquia gratuita: {limit}/mês)"
                    if limit else
                    "(deve ser gratuito — sem franquia)"
                )

                findings.append(DefenseFinding(
                    detector="D2",
                    severity="high",
                    bank_name=bank,
                    title=f"Cobrança indevida — {svc['name']} {limit_text}",
                    description=(
                        f"{bank} cobrou R$ {total:.2f} por {svc['name']} "
                        f"({count} ocorrência(s)), que é obrigatoriamente gratuito "
                        f"por lei (Res. CMN 3.919/2010, art. 7º). "
                        f"Estimativa contestável {dobro_label}: R$ {contestavel:.2f}."
                    ),
                    amount_disputed=contestavel,
                    legal_basis=_LEGAL_BASIS_ESSENCIAIS,
                    recommended_action=_ACTION_ESSENCIAL,
                    evidence_points=[
                        f"Banco: {bank}",
                        f"Serviço: {svc['name']}",
                        f"Ocorrências: {count}",
                        f"Total cobrado: R$ {total:.2f}",
                        f"Estimativa contestável ({dobro_label}): R$ {contestavel:.2f}",
                        f"Base: Res. CMN 3.919/2010, art. 7º — gratuidade obrigatória",
                        *[f"• {o['desc']}: R$ {o['amount']:.2f}" for o in ocorrencias[:5]],
                    ],
                ))
            return findings
        except Exception as exc:
            logger.debug("[D2] _check_essential_services: %s", exc)
            return []

    # ── D2c: Bancos sem transações recentes ainda cobrando ────────────

    def _check_stale_banks(self, user_id: str) -> list[DefenseFinding]:
        try:
            from app.core.db.queries import get_transactions_for_user
            from app.core.database import SessionLocal
            from sqlalchemy import text
            import polars as pl

            df = get_transactions_for_user(user_id)
            cutoff = date.today() - timedelta(days=self._STALE_DAYS)

            if df.is_empty() or "bank_name" not in df.columns:
                return []

            date_col = next((c for c in ("transaction_date", "date") if c in df.columns), None)
            if not date_col:
                return []

            active_banks: set[str] = set(
                df.filter(pl.col(date_col) >= cutoff)
                  .select("bank_name")
                  .unique()["bank_name"]
                  .to_list()
            )

            current_month = date.today().strftime("%Y-%m")
            ref_date = date.today().replace(day=1)
            mult = _multiplicador_dobro(ref_date)
            dobro_label = _dobro_label(ref_date)

            with SessionLocal() as db:
                rows = db.execute(
                    text(
                        "SELECT bank_name, SUM(amount) as total"
                        " FROM bank_fee_history"
                        " WHERE user_id = :uid AND month = :month"
                        " GROUP BY bank_name"
                    ),
                    {"uid": user_id, "month": current_month},
                ).fetchall()

            stale = [(b, float(t)) for b, t in rows if b not in active_banks]

            findings = []
            for bank, total in stale:
                contestavel = round(total * mult, 2)
                findings.append(DefenseFinding(
                    detector="D2",
                    severity="high",
                    bank_name=bank,
                    title=f"Cobrança em conta possivelmente encerrada — {bank}",
                    description=(
                        f"{bank} cobrou R$ {total:.2f} este mês sem nenhuma "
                        f"transação nos últimos {self._STALE_DAYS} dias. "
                        f"Pode indicar conta não encerrada formalmente ou cobrança indevida. "
                        f"Estimativa contestável {dobro_label}: R$ {contestavel:.2f}."
                    ),
                    amount_disputed=contestavel,
                    legal_basis=_LEGAL_BASIS_D2,
                    recommended_action=_ACTION_INATIVA,
                    evidence_points=[
                        f"Banco: {bank}",
                        f"Total cobrado no mês: R$ {total:.2f}",
                        f"Última transação: mais de {self._STALE_DAYS} dias atrás",
                        f"Estimativa contestável ({dobro_label}): R$ {contestavel:.2f}",
                        "Ausência de transações sugere conta encerrada ou cancelada",
                    ],
                ))
            return findings
        except Exception as exc:
            logger.debug("[D2] _check_stale_banks: %s", exc)
            return []

    # ── D2d: Tarifas novas sem histórico ──────────────────────────────

    def _check_new_fees(self, user_id: str) -> list[DefenseFinding]:
        try:
            from app.core.db.queries import get_transactions_for_user
            from app.costs.bank_fee_analyzer import BankFeeAnalyzer

            df = get_transactions_for_user(user_id)
            if df.is_empty():
                return []

            report = BankFeeAnalyzer().analyze(df, user_id=user_id)
            new_fees = BankFeeAnalyzer.detect_new_fees(user_id, report.entries)

            # Exclui tipos cobertos pelo D1 (seguro embutido)
            d1_types = {"SEGURO_EMBUTIDO", "SEGURO_PRESTAMISTA", "TARIFA_CADASTRO"}
            new_fees = [f for f in new_fees if f.fee_type.value not in d1_types]

            ref_date = date.today().replace(day=1)
            mult = _multiplicador_dobro(ref_date)
            dobro_label = _dobro_label(ref_date)

            findings = []
            for fee in new_fees:
                contestavel = round(float(fee.amount) * mult, 2)
                findings.append(DefenseFinding(
                    detector="D2",
                    severity="medium",
                    bank_name=fee.bank_name,
                    title=f"Tarifa nova sem histórico — {fee.fee_type.value.replace('_', ' ')}",
                    description=(
                        f"{fee.bank_name} cobrou "
                        f"'{fee.fee_type.value.replace('_', ' ').lower()}' "
                        f"(R$ {fee.amount:.2f}) pela primeira vez — sem registros anteriores. "
                        f"Tarifas novas exigem notificação prévia de 30 dias (Res. CMN 3.919/2010, art. 3º). "
                        f"Estimativa contestável {dobro_label}: R$ {contestavel:.2f}."
                    ),
                    amount_disputed=contestavel,
                    legal_basis=(
                        "Res. CMN 3.919/2010, art. 3º — alterações de tarifas bancárias "
                        "exigem comunicação prévia ao cliente com no mínimo 30 dias de antecedência. "
                        "CDC art. 42, parágrafo único — cobrança indevida deve ser restituída."
                    ),
                    recommended_action=_ACTION_NOVA_TARIFA,
                    evidence_points=[
                        f"Banco: {fee.bank_name}",
                        f"Tipo: {fee.fee_type.value}",
                        f"Valor: R$ {fee.amount:.2f}",
                        f"Estimativa contestável ({dobro_label}): R$ {contestavel:.2f}",
                        "Sem ocorrências anteriores no histórico bank_fee_history",
                    ],
                ))
            return findings
        except Exception as exc:
            logger.debug("[D2] _check_new_fees: %s", exc)
            return []
