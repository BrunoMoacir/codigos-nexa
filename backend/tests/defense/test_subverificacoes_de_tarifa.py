"""
D1 e D2 sobre o relatório de tarifas — as subverificações que devolviam [].

Achado na REVALIDAÇÃO do agente, não na auditoria: as tools
`detect_abusive_fees` / `detect_wrongful_charges` foram corrigidas por usarem
`BankCostReport.entries`, atributo que não existe (é `fees_detected`). A mesma
linha estava na camada AUDITADA, que é a que o `get_defense_analysis`, o dossiê
D5 e a API `/defense` usam:

    app/defense/services/tied_sale_detector.py:270      for entry in report.entries
    app/defense/services/wrongful_charge_detector.py:449  detect_new_fees(..., report.entries)

Nos dois casos o `AttributeError` caía num `except` que devolve `[]`. Resultado
medido: `TiedSaleDetector._check_fee_analyzer` e
`WrongfulChargeDetector._check_new_fees` **nunca produziram um achado** — para
nenhum usuário, desde sempre.

Corrigir isso trouxe o segundo problema à tona. `detect_new_fees` devolvia toda
`FeeEntry` cujo par (banco, tipo) não estivesse em `bank_fee_history` — uma
tarifa mensal de R$ 34,90 cobrada em seis meses virava SEIS "tarifas novas sem
histórico anterior", e o D2 escreve "cobrou pela primeira vez" e manda exigir
comprovante do banco. Duas afirmações falsas: o número e o "primeira vez".

Agora: uma entrada por par, e só para pares que não se repetem ao longo da
janela analisada — porque a ausência em `bank_fee_history` é fato sobre os
NOSSOS registros, não sobre o comportamento do banco.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app.costs.bank_fee_analyzer import BankFeeAnalyzer
from app.costs.models import BankCostReport
from app.defense.services.tied_sale_detector import TiedSaleDetector
from app.defense.services.wrongful_charge_detector import WrongfulChargeDetector


def _semear(linhas: list[tuple[dt.date, float, str]]) -> str:
    from sqlalchemy import text

    from app.core.database import SessionLocal

    uid = f"teste-defesa-{uuid.uuid4().hex[:8]}"
    with SessionLocal() as db:
        for data, valor, descricao in linhas:
            db.execute(
                text(
                    "INSERT INTO transactions_clean (transaction_id, user_id, account_id,"
                    " description, amount, date, transaction_type, category,"
                    " is_recurring, is_installment)"
                    " VALUES (:t, :u, 'acc-teste', :d, :v, :dt, 'DEBIT', 'Tarifas', false, false)"
                ),
                {"t": str(uuid.uuid4()), "u": uid, "d": descricao, "v": valor, "dt": data},
            )
        db.commit()
    return uid


def _limpar(uid: str) -> None:
    from sqlalchemy import text

    from app.core.database import SessionLocal

    with SessionLocal() as db:
        db.execute(text("DELETE FROM transactions_clean WHERE user_id = :u"), {"u": uid})
        db.execute(text("DELETE FROM bank_fee_history WHERE user_id = :u"), {"u": uid})
        db.commit()


_MENSAL = [(dt.date(2026, m, 18), -34.90, "TARIFA PACOTE SERVICOS") for m in range(1, 7)]


@pytest.fixture
def usuario_com_tarifa_recorrente():
    uid = _semear(_MENSAL)
    yield uid
    _limpar(uid)


@pytest.fixture
def usuario_com_tarifa_nova():
    """Recorrente + duas tarifas pontuais só no último mês."""
    uid = _semear(_MENSAL + [
        (dt.date(2026, 6, 20), -89.90, "SEGURO PRESTAMISTA CONTRATADO"),
        (dt.date(2026, 6, 22), -12.50, "TARIFA TED ENVIADA"),
    ])
    yield uid
    _limpar(uid)


# ── 1. O atributo que não existe ───────────────────────────────────────────

class TestAtributoDoRelatorio:

    def test_o_relatorio_expoe_fees_detected_e_nao_entries(self):
        assert "fees_detected" in BankCostReport.model_fields
        assert "entries" not in BankCostReport.model_fields

    def test_nenhum_detector_acessa_report_entries(self):
        """
        Varredura de origem: `.entries` sobre o relatório de tarifas é a forma
        exata do defeito, e ele estava em dois arquivos ao mesmo tempo.
        """
        import pathlib
        import re

        raiz = pathlib.Path(__file__).resolve().parents[2] / "app"
        padrao = re.compile(r"report\.entries\b")
        culpados = [
            f"{p.relative_to(raiz.parent)}:{i}"
            for p in raiz.rglob("*.py")
            for i, linha in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if padrao.search(linha) and not linha.lstrip().startswith("#")
        ]
        assert not culpados, culpados


# ── 2. As subverificações voltaram a produzir achado ───────────────────────

class TestSubverificacoesProduzemAchado:

    def test_d1_detecta_seguro_prestamista(self, usuario_com_tarifa_nova):
        titulos = [f.title for f in TiedSaleDetector().detect(usuario_com_tarifa_nova)]
        assert any("prestamista" in t.lower() for t in titulos), titulos

    def test_d2_detecta_tarifa_pontual_nova(self, usuario_com_tarifa_nova):
        titulos = [f.title for f in WrongfulChargeDetector().detect(usuario_com_tarifa_nova)]
        assert any("TED" in t for t in titulos), titulos

    def test_d2_defere_ao_d1_nos_tipos_de_venda_casada(self, usuario_com_tarifa_nova):
        """Seguro prestamista é achado de D1; D2 não pode duplicá-lo."""
        titulos = [f.title for f in WrongfulChargeDetector().detect(usuario_com_tarifa_nova)]
        assert not any("prestamista" in t.lower() for t in titulos), titulos


# ── 3. Tarifa recorrente não é "primeira vez" ──────────────────────────────

class TestRecorrenteNaoEhNova:

    def test_seis_cobrancas_iguais_nao_viram_seis_achados(self, usuario_com_tarifa_recorrente):
        achados = WrongfulChargeDetector().detect(usuario_com_tarifa_recorrente)
        novas = [f for f in achados if "sem histórico" in f.title.lower()]
        assert novas == [], f"tarifa mensal reportada como nova: {[f.title for f in novas]}"

    def test_detect_new_fees_devolve_um_por_par(self, usuario_com_tarifa_nova):
        from app.core.db.queries import get_transactions_for_user

        relatorio = BankFeeAnalyzer().analyze(
            get_transactions_for_user(usuario_com_tarifa_nova), usuario_com_tarifa_nova
        )
        novas = BankFeeAnalyzer.detect_new_fees(usuario_com_tarifa_nova, relatorio.fees_detected)

        pares = [(f.bank_name, f.fee_type.value) for f in novas]
        assert len(pares) == len(set(pares)), f"par duplicado: {pares}"
        assert "PACOTE_SERVICOS" not in {p[1] for p in pares}, "recorrente entrou como nova"
        assert {"SEGURO_PRESTAMISTA", "TED_DOC"} <= {p[1] for p in pares}, pares

    def test_o_relatorio_realmente_tem_a_recorrente_repetida(self, usuario_com_tarifa_recorrente):
        """
        Guarda do próprio teste: se o analisador parar de detectar as seis
        cobranças, o teste acima passaria por vacuidade.
        """
        from app.core.db.queries import get_transactions_for_user

        relatorio = BankFeeAnalyzer().analyze(
            get_transactions_for_user(usuario_com_tarifa_recorrente),
            usuario_com_tarifa_recorrente,
        )
        pacotes = [f for f in relatorio.fees_detected if f.fee_type.value == "PACOTE_SERVICOS"]
        assert len(pacotes) >= 5, f"só {len(pacotes)} cobranças detectadas"
        meses = {f.transaction_date.strftime("%Y-%m") for f in pacotes}
        assert len(meses) >= 5, meses
