"""
app/purchase/post_purchase.py — Análise retroativa de compras (R1.a)

O F7 responde "como devo pagar?" ANTES da compra. Este módulo fecha o
ciclo DEPOIS dela: varre as compras grandes recentes já sincronizadas via
Open Finance, infere como o usuário pagou e roda o PurchaseAdvisor
retroativamente para medir quanto ficou na mesa.

O resultado vira o card PURCHASE_FOLLOWUP do feed — tom de aprendizado
("na próxima, consulte o Modo Compra"), nunca de bronca.

Regras de honestidade:
  - Só analisa compras à vista (débito único). Compras parceladas não têm
    o valor total nem o nº de parcelas confiáveis na transação isolada —
    comparar seria chute, então ficam de fora.
  - Só gera follow-up quando a diferença de custo líquido é >= R$10 e o
    método inferido tem correspondência exata nas opções do F7.

Performance: pré-filtro 100% SQL (uma query), no máximo 3 candidatos
passam pelo PurchaseAdvisor por rodada e cada transação é analisada UMA
única vez na vida — o marcador `nexa:pp_seen:{user}:{tx}` (Redis, TTL 45d,
fallback em memória) faz o custo em regime permanente cair para apenas
transações novas, independente da frequência do scheduler.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Compra mínima para valer análise retroativa (o relevance_filter ainda
# aplica piso de economia relativo à renda)
_MIN_PURCHASE_BRL = 300.0

# Janela de compras analisadas
_LOOKBACK_DAYS = 14

# Máximo de candidatos que rodam o PurchaseAdvisor por chamada
_MAX_CANDIDATES = 3

# Economia mínima para emitir follow-up
_MIN_SAVINGS_BRL = 10.0

# Marcador "já analisada" — TTL maior que a janela de lookback garante que
# uma transação nunca é reanalisada enquanto ainda é elegível
_SEEN_KEY_PREFIX = "nexa:pp_seen:"
_SEEN_TTL_SECONDS = 45 * 24 * 3600

# Descrições que NÃO são compra (transferências, faturas, obrigações e
# contas recorrentes sem escolha real de meio de pagamento). Ampliado após
# calibração com corpora reais (scripts/calibrate_retention_heuristics.py):
# plano de saúde, contas de consumo e mensalidades passavam como "compra".
_NON_PURCHASE_PATTERNS = re.compile(
    r"transf|\bted\b|\bdoc\b|pgto|pagamento\s+(de\s+)?fatura|fatura|aplicacao|"
    r"aplicação|resgate|invest|emprestimo|empréstimo|financiamento|"
    r"consorcio|consórcio|salario|salário|folha|aluguel|condominio|"
    r"condomínio|iptu|ipva|darf|\bdas\b|inss|fgts|tarifa|anuidade|juros|"
    r"iof|seguro|boleto\s+bancario|"
    r"plano\s+(de\s+)?sa[uú]de|unimed|hapvida|amil\b|"
    r"conta\s+(de\s+)?(energia|luz|agua|água|internet|g[aá]s|telefone|celular)|"
    r"energia\s+el[eé]trica|mensalidade",
    re.IGNORECASE,
)

# Marcador de parcelamento na descrição (ex: "PARC 03/10", "3/12")
_INSTALLMENT_PATTERN = re.compile(r"\bparc|\b\d{1,2}/\d{1,2}\b", re.IGNORECASE)

_PIX_PATTERN = re.compile(r"\bpix\b", re.IGNORECASE)
_CARD_PATTERN = re.compile(r"cartao|cartão|credito|crédito", re.IGNORECASE)


@dataclass
class _Candidate:
    transaction_id: str
    tx_date: date
    amount: float          # positivo (valor da compra)
    description: str
    category: str
    paid_method: str       # "PIX_AVISTA" | "CARTAO_AVISTA"
    paid_label: str


class PostPurchaseAnalyzer:
    """Detecta compras grandes recentes pagas de forma subótima."""

    def __init__(self) -> None:
        # Fallback do marcador "já analisada" quando Redis está fora —
        # vale pela vida do processo, o que já elimina o retrabalho entre
        # as rodadas de 6h do scheduler no mesmo worker
        self._seen_local: set[str] = set()

    def detect(
        self,
        user_id: str,
        today: date | None = None,
        use_seen_marker: bool = True,
    ) -> list:
        """
        Retorna PurchaseFollowupInput para cada compra grande recente em
        que outro meio de pagamento teria custo líquido menor.

        Com use_seen_marker=True (padrão — caminho do scheduler/feed),
        cada transação passa pelo PurchaseAdvisor no máximo uma vez:
        quem consumir o resultado primeiro (engine proativo ou feed
        reativo) entrega o card; a persistência in_app do delivery
        garante que o usuário o veja de todo jeito.

        Com use_seen_marker=False (revisão sob demanda — endpoint
        recent-review e tool do chat), sempre reanalisa: o usuário pediu
        explicitamente e paga o custo de uma rodada.
        """
        from app.notifications.notifier import PurchaseFollowupInput

        today = today or date.today()
        candidates = self._fetch_candidates(user_id, today)
        if use_seen_marker:
            candidates = [
                c for c in candidates
                if not self._is_seen(user_id, c.transaction_id)
            ]
        if not candidates:
            return []

        followups: list[PurchaseFollowupInput] = []
        for cand in candidates[:_MAX_CANDIDATES]:
            try:
                followup = self._analyze_candidate(user_id, cand)
            except Exception as exc:
                # análise falhou — NÃO marca como vista, tenta no próximo ciclo
                logger.debug(
                    "[PostPurchase] candidato %s falhou: %s", cand.transaction_id, exc
                )
                continue
            if use_seen_marker:
                self._mark_seen(user_id, cand.transaction_id)
            if followup is not None:
                followups.append(followup)

        return followups

    # ── Marcador de transação já analisada ───────────────────────────

    def _is_seen(self, user_id: str, tx_id: str) -> bool:
        key = f"{_SEEN_KEY_PREFIX}{user_id}:{tx_id}"
        try:
            from app.core.cache import get_redis

            redis = get_redis()
            if redis is not None:
                return bool(redis.exists(key))
        except Exception:
            pass
        return key in self._seen_local

    def _mark_seen(self, user_id: str, tx_id: str) -> None:
        key = f"{_SEEN_KEY_PREFIX}{user_id}:{tx_id}"
        try:
            from app.core.cache import get_redis

            redis = get_redis()
            if redis is not None:
                redis.set(key, "1", ex=_SEEN_TTL_SECONDS)
                return
        except Exception:
            pass
        self._seen_local.add(key)

    # ── Pré-filtro SQL ───────────────────────────────────────────────

    def _fetch_candidates(self, user_id: str, today: date) -> list[_Candidate]:
        cutoff = today - timedelta(days=_LOOKBACK_DAYS)
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                rows = db.execute(
                    text(
                        "SELECT transaction_id, date, amount, description, category"
                        " FROM transactions_clean"
                        " WHERE user_id = :uid AND amount <= :max_amount"
                        " AND date >= :cutoff"
                        " AND (is_installment IS NULL OR is_installment = :no)"
                        " ORDER BY amount ASC"          # maiores débitos primeiro
                        " LIMIT 20"
                    ),
                    {
                        "uid": user_id,
                        "max_amount": -_MIN_PURCHASE_BRL,
                        "cutoff": cutoff,
                        "no": False,
                    },
                ).fetchall()
        except Exception as exc:
            logger.warning("[PostPurchase] _fetch_candidates user=%s: %s", user_id, exc)
            return []

        candidates: list[_Candidate] = []
        for tx_id, tx_date, amount, description, category in rows:
            description = description or ""
            if _NON_PURCHASE_PATTERNS.search(description):
                continue
            if _INSTALLMENT_PATTERN.search(description):
                continue   # parcelado sem total confiável — fora (honestidade)

            paid_method, paid_label = self._infer_paid_method(description)
            if isinstance(tx_date, str):
                tx_date = date.fromisoformat(tx_date[:10])
            elif hasattr(tx_date, "date") and not isinstance(tx_date, date):
                tx_date = tx_date.date()

            candidates.append(_Candidate(
                transaction_id=str(tx_id),
                tx_date=tx_date,
                amount=abs(float(amount)),
                description=description,
                category=category or "Outros",
                paid_method=paid_method,
                paid_label=paid_label,
            ))

        return candidates

    @staticmethod
    def _infer_paid_method(description: str) -> tuple[str, str]:
        """Infere o meio de pagamento pela descrição da transação."""
        if _PIX_PATTERN.search(description):
            return "PIX_AVISTA", "PIX à vista"
        if _CARD_PATTERN.search(description):
            return "CARTAO_AVISTA", "cartão de crédito à vista"
        # débito em conta sem marcador: custo idêntico ao PIX à vista
        return "DEBITO_AVISTA", "débito/PIX à vista"

    # ── Análise retroativa via F7 ────────────────────────────────────

    def _analyze_candidate(self, user_id: str, cand: _Candidate):
        from app.notifications.notifier import PurchaseFollowupInput
        from app.purchase.models import PurchaseRequest
        from app.purchase.purchase_advisor import PurchaseAdvisor

        result = PurchaseAdvisor().analyze(PurchaseRequest(
            user_id=user_id,
            amount=cand.amount,
            category=cand.category,
            installments=1,
        ))
        if not result.options:
            return None

        paid_method = (
            "PIX_AVISTA" if cand.paid_method == "DEBITO_AVISTA"
            else cand.paid_method
        )
        paid_option = next(
            (o for o in result.options if o.method.value == paid_method), None
        )
        if paid_option is None:
            return None

        def _cost(option) -> float:
            return option.net_cost_real if option.net_cost_real is not None else option.net_cost

        best = min(result.options, key=_cost)
        savings = round(_cost(paid_option) - _cost(best), 2)
        if best.method == paid_option.method or savings < _MIN_SAVINGS_BRL:
            return None

        merchant = self._merchant_from_description(cand.description)
        return PurchaseFollowupInput(
            transaction_id=cand.transaction_id,
            merchant=merchant,
            amount=cand.amount,
            category=cand.category,
            purchase_date=cand.tx_date.isoformat(),
            paid_method_label=cand.paid_label,
            best_method_label=best.label,
            potential_savings_brl=savings,
        )

    @staticmethod
    def _merchant_from_description(description: str) -> str:
        """Extrai um nome legível do estabelecimento da descrição."""
        cleaned = re.sub(
            r"\b(compra|pagamento|debito|débito|cartao|cartão|pix|em|no|na)\b",
            " ",
            description,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"[\d*#-]+", " ", cleaned)
        cleaned = " ".join(cleaned.split()).strip()
        return cleaned[:40] if cleaned else "estabelecimento"


_analyzer: PostPurchaseAnalyzer | None = None


def get_post_purchase_analyzer() -> PostPurchaseAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = PostPurchaseAnalyzer()
    return _analyzer


__all__ = ["PostPurchaseAnalyzer", "get_post_purchase_analyzer"]
