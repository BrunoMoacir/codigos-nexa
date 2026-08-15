"""
🧪 ETL COM DADOS SUJOS DE PRODUÇÃO — PLUGGY → transactions_clean
═══════════════════════════════════════════════════════════════════════════════

OBJETIVO
    Reproduzir, o mais fielmente possível, o que a Pluggy REALMENTE entrega em
    produção: payload cru (camelCase + objetos aninhados), misturado com todo o
    lixo que o Open Finance brasileiro produz — valores em string, datas em três
    formatos, descrição com HTML, sinal invertido, campos nulos, reenvio de
    webhook, elementos quebrados no array `results`.

    Os testes existentes (test_ultimate_etl_and_schemas, test_etl_ingestor)
    usam dados JÁ no formato interno e essencialmente limpos. Este aqui ataca a
    camada anterior: o que chega do fio.

CAMINHO EXERCITADO (idêntico ao de produção — app/api/v1/routes/pluggy.py)
    Pluggy /transactions (payload cru)
        → normalização da rota (merchant aninhado, descriptionRaw, não-dicts)
        → TransactionBatchResult.from_raw_batch  (Camada 1: firewall Pydantic)
        → TransactionIngestor.process            (Camada 2: Polars + BankStrategy)
        → run_etl_pipeline                       (Camada 3: steps 2..8)
        → save_transactions_clean                (Camada 4: upsert Postgres)

    Nenhum teste aqui precisa de banco, rede ou credencial Pluggy: o cliente é
    substituído por um fake que devolve payload sujo, e a Session é um stub.

ORGANIZAÇÃO
    TestCamada1ValidacaoTolerante  — lote sujo entra, válidas seguem, resto vai p/ DLQ
    TestCamada2ParsingDeCamposSujos— valor/data/sinal/texto/status normalizados
    TestCamada3IngestorMultiBanco  — 4 bancos no mesmo lote + data_status + dedup
    TestCamada4PipelineCompleto    — 8 steps sobrevivem ao lote sujo
    TestCamada5RotaDeProducao      — a rota real de sync, ponta a ponta

HISTÓRICO
    A primeira versão deste arquivo encontrou 7 falhas de produção (registro
    não-dict derrubando o lote, teto de valor furado na via numérica, descrição
    longa descartando a transação, fallback de descrição morto, dedup não
    plugada, Step 7 sempre no except, IncomeProfiler cego para as colunas do
    ETL). Todas foram corrigidas — os testes abaixo são a trava contra a
    regressão de cada uma.

Como executar:
    cd backend && python -m pytest tests/test_etl_pluggy_sujo_producao.py -v -s
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import count
from pathlib import Path
from typing import Any, Literal

import polars as pl
import pytest

# Fix PYTHONPATH (mesmo padrão dos demais testes da suíte)
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.schemas.enums import TransactionStatus  # noqa: E402
from app.core.schemas.transaction import (  # noqa: E402
    TZ_BR,
    TransactionBatchResult,
    TransactionWebhook,
)
from app.forecast.etl.dedup.default import DefaultDedupPolicy  # noqa: E402
from app.forecast.etl.ingestor import TransactionIngestor  # noqa: E402
from app.forecast.etl.runner import run_etl_pipeline  # noqa: E402

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONSTANTES DO CENÁRIO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Tudo é relativo a AGORA: nenhuma data fixa que expire e deixe a suíte vermelha
# no ano que vem (transação > 1 ano no futuro é rejeitada pelo schema).
AGORA = datetime.now(timezone.utc)

ACC_CORRENTE = "0f6b1e2a-conta-corrente"
ACC_CARTAO = "3c8d4f9b-cartao-credito"
ITEM_ID = "6b2c9d1e-item-pluggy"
USER_ID = "user_prod_sujo"

VALIDA: Literal["VALIDA"] = "VALIDA"
REJEITADA: Literal["REJEITADA"] = "REJEITADA"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CATÁLOGO DE SUJEIRA — cada caso é algo que a Pluggy já entregou de verdade
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass(frozen=True)
class RegistroSujo:
    """Um caso de sujeira, com o motivo pelo qual ele existe em produção."""

    caso: str
    motivo: str
    payload: dict[str, Any]
    esperado: str  # VALIDA | REJEITADA
    banco: str = "nubank"
    campo_erro: str | None = None  # campo que deve aparecer no DLQ
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def tx_id(self) -> str:
        return self.payload.get("id") or self.payload.get("transaction_id") or ""


_SEQUENCIA = count()


def _tx_pluggy(caso: str, *, dias_atras: int = 3, **overrides: Any) -> dict[str, Any]:
    """
    Transação no formato REAL da Pluggy (camelCase, objetos aninhados,
    campos que o Nexa nem usa). É esse dict que chega no webhook/sync.

    'nexaCaso' é marcador do teste — campo desconhecido, que o schema deve
    ignorar e o DLQ deve preservar em raw_data (é assim que rastreamos cada
    caso, já que registro rejeitado pode nem ter id).

    Cada chamada ganha um instante próprio (segundos da sequência): com a
    deduplicação por dedup_hash ligada no ingestor, dois casos com mesma
    conta/data/valor/descrição seriam colapsados — o que é certo em produção
    e péssimo dentro de um catálogo de casos distintos.
    """
    data = AGORA - timedelta(days=dias_atras, seconds=next(_SEQUENCIA) * 37)
    base: dict[str, Any] = {
        "nexaCaso": caso,
        "id": f"tx_{caso}",
        "accountId": ACC_CORRENTE,
        "date": data.isoformat().replace("+00:00", "Z"),
        "description": "PAG*IFOOD DELIVERY",
        "descriptionRaw": "IFD*IFOOD DELIVERY BR",
        "currencyCode": "BRL",
        "amount": -63.90,
        "amountInAccountCurrency": None,
        "balance": 4210.55,
        "category": "Food and drinks",
        "categoryId": "05000000",
        "providerCode": None,
        "status": "POSTED",
        "type": "DEBIT",
        "operationType": None,
        "paymentData": None,
        "creditCardMetadata": None,
        "createdAt": data.isoformat(),
        "updatedAt": data.isoformat(),
    }
    base.update(overrides)
    return base


def _br_naive(dias_atras: int, fmt: str) -> tuple[str, datetime]:
    """
    Gera uma data 'naive' escrita no fuso de São Paulo (é assim que Itaú e
    bancos legados mandam) e devolve também o instante UTC equivalente —
    o schema assume America/Sao_Paulo para datas sem fuso.
    """
    momento_brt = (AGORA - timedelta(days=dias_atras)).astimezone(TZ_BR).replace(microsecond=0)
    return momento_brt.strftime(fmt), momento_brt.astimezone(timezone.utc)


# Datas usadas em asserts precisos (string suja ↔ instante UTC esperado)
DATA_SQL_STR, DATA_SQL_UTC = _br_naive(9, "%Y-%m-%d %H:%M:%S")
DATA_BR_STR, DATA_BR_UTC = _br_naive(11, "%d/%m/%Y %H:%M:%S")
DATA_SO_DIA_STR = (AGORA - timedelta(days=13)).astimezone(TZ_BR).strftime("%Y-%m-%d")
DATA_SO_DIA_UTC = datetime.strptime(DATA_SO_DIA_STR, "%Y-%m-%d").replace(tzinfo=TZ_BR).astimezone(timezone.utc)


CATALOGO: list[RegistroSujo] = [
    # ══════════════════════════════════════════════════════════════════════
    # A) SUJEIRA QUE O ETL TEM QUE LIMPAR E APROVEITAR
    # ══════════════════════════════════════════════════════════════════════
    RegistroSujo(
        caso="valor_string_br",
        motivo="Conector legado serializa valor como texto BR ('R$ 1.234,56')",
        payload=_tx_pluggy("valor_string_br", amount="R$ 1.234,56", type=None),
        esperado=VALIDA,
        tags=("valor",),
    ),
    RegistroSujo(
        caso="valor_string_us",
        motivo="Conector com locale US no meio do lote BR ('1,234.56')",
        payload=_tx_pluggy("valor_string_us", amount="1,234.56", type=None),
        esperado=VALIDA,
        tags=("valor",),
    ),
    RegistroSujo(
        caso="valor_contabil",
        motivo="Extrato contábil marca débito com parênteses: (89,90)",
        payload=_tx_pluggy("valor_contabil", amount="(89,90)", type=None),
        esperado=VALIDA,
        tags=("valor",),
    ),
    RegistroSujo(
        caso="valor_com_espaco",
        motivo="Separador de milhar como espaço ('1 500,00')",
        payload=_tx_pluggy("valor_com_espaco", amount="1 500,00", type=None),
        esperado=VALIDA,
        tags=("valor",),
    ),
    RegistroSujo(
        caso="valor_zero",
        motivo="Tarifa isenta / estorno integral chega com amount = 0",
        payload=_tx_pluggy("valor_zero", amount=0, type=None),
        esperado=VALIDA,
        tags=("valor",),
    ),
    RegistroSujo(
        caso="data_sql_naive",
        motivo="Banco manda 'YYYY-MM-DD HH:MM:SS' sem fuso (hora de Brasília)",
        payload=_tx_pluggy("data_sql_naive", date=DATA_SQL_STR),
        esperado=VALIDA,
        tags=("data",),
    ),
    RegistroSujo(
        caso="data_br",
        motivo="Formato brasileiro 'dd/mm/aaaa hh:mm:ss'",
        payload=_tx_pluggy("data_br", date=DATA_BR_STR),
        esperado=VALIDA,
        tags=("data",),
    ),
    RegistroSujo(
        caso="data_so_dia",
        motivo="Cartão manda só a data da fatura, sem hora",
        payload=_tx_pluggy("data_so_dia", date=DATA_SO_DIA_STR),
        esperado=VALIDA,
        tags=("data",),
    ),
    RegistroSujo(
        caso="data_antiga",
        motivo="Backfill de histórico: transação de 12 anos atrás (aceita com warning)",
        payload=_tx_pluggy("data_antiga", dias_atras=4380),
        esperado=VALIDA,
        tags=("data",),
    ),
    RegistroSujo(
        caso="sinal_invertido_debito",
        motivo="Clássico Itaú/legado: valor positivo com flag DEBIT",
        payload=_tx_pluggy("sinal_invertido_debito", amount=250.00, type="DEBIT"),
        esperado=VALIDA,
        tags=("sinal",),
    ),
    RegistroSujo(
        caso="sinal_invertido_credito",
        motivo="Estorno chega negativo com flag CREDIT",
        payload=_tx_pluggy("sinal_invertido_credito", amount=-180.00, type="CREDIT"),
        esperado=VALIDA,
        tags=("sinal",),
    ),
    RegistroSujo(
        caso="descricao_xss",
        motivo="Nome de estabelecimento com HTML/script (injeção via campo livre do lojista)",
        payload=_tx_pluggy(
            "descricao_xss",
            description="<script>alert('xss')</script>MERCADO PAO DE ACUCAR",
        ),
        esperado=VALIDA,
        tags=("texto",),
    ),
    RegistroSujo(
        caso="descricao_controle",
        motivo="Bytes de controle e espaços duplicados vindos de mainframe",
        payload=_tx_pluggy(
            "descricao_controle",
            description="PAG\x00\x07 UBER   \t\n TRIP  ",
        ),
        esperado=VALIDA,
        tags=("texto",),
    ),
    RegistroSujo(
        caso="descricao_unicode",
        motivo="Acentos, emoji e travessão no nome do lojista",
        payload=_tx_pluggy("descricao_unicode", description="MERCADO SÃO JOÃO 🛒 — PAGAMENTO"),
        esperado=VALIDA,
        tags=("texto",),
    ),
    RegistroSujo(
        caso="descricao_vazia_com_observacao",
        motivo="Descrição vazia; o que importa está em observations (fallback do schema)",
        payload=_tx_pluggy(
            "descricao_vazia_com_observacao",
            description="   ",
            descriptionRaw=None,  # terceiro elo da cadeia: só sobra observations
            observations="TARIFA PACOTE DE SERVICOS",
        ),
        esperado=VALIDA,
        tags=("texto",),
    ),
    RegistroSujo(
        caso="descricao_nula",
        motivo=(
            "description = null com descriptionRaw preenchido — o fallback "
            "description → description_raw → observations tem que salvar a linha"
        ),
        payload=_tx_pluggy("descricao_nula", description=None),
        esperado=VALIDA,
        tags=("texto",),
    ),
    RegistroSujo(
        caso="descricao_gigante",
        motivo=(
            "Descrição de 501 chars (PIX com mensagem longa concatenada): "
            "trunca em 500, não descarta a transação"
        ),
        payload=_tx_pluggy("descricao_gigante", description="A" * 501),
        esperado=VALIDA,
        tags=("texto", "seguranca"),
    ),
    RegistroSujo(
        caso="status_processed",
        motivo="Belvo/Pluggy usam PROCESSED em vez de POSTED",
        payload=_tx_pluggy("status_processed", status="PROCESSED"),
        esperado=VALIDA,
        tags=("status",),
    ),
    RegistroSujo(
        caso="status_minusculo",
        motivo="Conector manda 'processing' em minúsculo",
        payload=_tx_pluggy("status_minusculo", status="processing"),
        esperado=VALIDA,
        tags=("status",),
    ),
    RegistroSujo(
        caso="status_nulo",
        motivo="Campo status ausente/nulo (muito comum em cartão)",
        payload=_tx_pluggy("status_nulo", status=None),
        esperado=VALIDA,
        tags=("status",),
    ),
    RegistroSujo(
        caso="status_desconhecido",
        motivo="Status proprietário do banco ('ESTORNADO_PARCIAL')",
        payload=_tx_pluggy("status_desconhecido", status="ESTORNADO_PARCIAL"),
        esperado=VALIDA,
        tags=("status",),
    ),
    RegistroSujo(
        caso="saldo_string_br",
        motivo="Saldo em texto BR ('1.849,50')",
        payload=_tx_pluggy("saldo_string_br", balance="1.849,50"),
        esperado=VALIDA,
        tags=("valor",),
    ),
    RegistroSujo(
        caso="saldo_vazio",
        motivo="Cartão de crédito não expõe saldo → string vazia",
        payload=_tx_pluggy("saldo_vazio", balance=""),
        esperado=VALIDA,
        tags=("valor",),
    ),
    RegistroSujo(
        caso="campos_extras_pluggy",
        motivo="Payload completo da Pluggy (paymentData, creditCardMetadata, MCC...)",
        payload=_tx_pluggy(
            "campos_extras_pluggy",
            accountId=ACC_CARTAO,
            operationType="PIX",
            providerCode="0001",
            paymentData={
                "payer": {
                    "name": "FULANO DE TAL",
                    "documentNumber": {"type": "CPF", "value": "882.937.890-30"},
                    "accountNumber": "12345-6",
                },
                "paymentMethod": "PIX",
                "referenceNumber": "E1234567820260812",
            },
            creditCardMetadata={
                "installmentNumber": 2,
                "totalInstallments": 10,
                "totalAmount": 1899.90,
                "payeeMCC": 5812,
                "cardNumber": "4020",
            },
        ),
        esperado=VALIDA,
        tags=("payload",),
    ),
    RegistroSujo(
        caso="merchant_texto_sujo",
        motivo="Merchant como texto com espaços/caixa alta",
        payload=_tx_pluggy("merchant_texto_sujo", merchant="   IFOOD.COM   "),
        esperado=VALIDA,
        tags=("texto",),
    ),
    RegistroSujo(
        caso="parcela_coerente",
        motivo="Parcelamento legítimo 3/12",
        payload=_tx_pluggy("parcela_coerente", installment_number=3, installment_total=12),
        esperado=VALIDA,
        tags=("parcela",),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # B) SUJEIRA IRRECUPERÁVEL — tem que cair no DLQ, sem derrubar o lote
    # ══════════════════════════════════════════════════════════════════════
    RegistroSujo(
        caso="valor_nulo",
        motivo="amount = null (falha do conector no meio da sincronização)",
        payload=_tx_pluggy("valor_nulo", amount=None),
        esperado=REJEITADA,
        campo_erro="amount",
        tags=("valor",),
    ),
    RegistroSujo(
        caso="valor_string_null",
        motivo="Serialização quebrada manda a string literal 'null'",
        payload=_tx_pluggy("valor_string_null", amount="null"),
        esperado=REJEITADA,
        campo_erro="amount",
        tags=("valor",),
    ),
    RegistroSujo(
        caso="valor_objeto",
        motivo="amount vem como objeto {value, currency} em alguns conectores",
        payload=_tx_pluggy("valor_objeto", amount={"value": 10.0, "currency": "BRL"}),
        esperado=REJEITADA,
        campo_erro="amount",
        tags=("valor",),
    ),
    RegistroSujo(
        caso="valor_texto_absurdo",
        motivo="Valor acima do teto de segurança (1 bi) — provável erro de escala",
        payload=_tx_pluggy("valor_texto_absurdo", amount="1.234.567.890.123,45"),
        esperado=REJEITADA,
        campo_erro="amount",
        tags=("valor", "seguranca"),
    ),
    RegistroSujo(
        caso="data_nula",
        motivo="date = null (transação ainda não liquidada em conector instável)",
        payload=_tx_pluggy("data_nula", date=None),
        esperado=REJEITADA,
        campo_erro="transaction_date",
        tags=("data",),
    ),
    RegistroSujo(
        caso="data_epoch_ms",
        motivo="Timestamp epoch em milissegundos (formato não suportado)",
        payload=_tx_pluggy("data_epoch_ms", date=1754049600000),
        esperado=REJEITADA,
        campo_erro="transaction_date",
        tags=("data",),
    ),
    RegistroSujo(
        caso="data_futuro_absurdo",
        motivo="Data 2 anos no futuro (bug de fuso/ano do conector)",
        payload=_tx_pluggy("data_futuro_absurdo", dias_atras=-730),
        esperado=REJEITADA,
        campo_erro="root",
        tags=("data",),
    ),
    RegistroSujo(
        caso="sem_id",
        motivo="Registro sem 'id' — não dá para deduplicar nem auditar",
        payload={k: v for k, v in _tx_pluggy("sem_id").items() if k != "id"},
        esperado=REJEITADA,
        campo_erro="transaction_id",
        tags=("chave",),
    ),
    RegistroSujo(
        caso="id_vazio",
        motivo="id = '' (string vazia passa no tipo, mas não é chave)",
        payload=_tx_pluggy("id_vazio", id=""),
        esperado=REJEITADA,
        campo_erro="root",
        tags=("chave",),
    ),
    RegistroSujo(
        caso="sem_conta",
        motivo="accountId ausente — impossível ligar a transação à conta",
        payload={k: v for k, v in _tx_pluggy("sem_conta").items() if k != "accountId"},
        esperado=REJEITADA,
        campo_erro="account_id",
        tags=("chave",),
    ),
    RegistroSujo(
        caso="parcela_maior_que_total",
        motivo="Parcela 13 de 12 (bug conhecido de conector de cartão)",
        payload=_tx_pluggy("parcela_maior_que_total", installment_number=13, installment_total=12),
        esperado=REJEITADA,
        campo_erro="root",
        tags=("parcela",),
    ),
    RegistroSujo(
        caso="parcela_sem_total",
        motivo="installment_number sem installment_total",
        payload=_tx_pluggy("parcela_sem_total", installment_number=3, installment_total=None),
        esperado=REJEITADA,
        campo_erro="root",
        tags=("parcela",),
    ),
    RegistroSujo(
        caso="merchant_objeto",
        motivo=(
            "Merchant aninhado {name, businessName, cnpj} — formato REAL da Pluggy "
            "em transação de cartão. Só sobrevive porque a rota achata antes "
            "(ver TestCamada5RotaDeProducao)."
        ),
        payload=_tx_pluggy(
            "merchant_objeto",
            accountId=ACC_CARTAO,
            merchant={
                "name": "Ifood",
                "businessName": "IFOOD.COM AGENCIA DE RESTAURANTES LTDA",
                "cnpj": "14380200000121",
                "cnae": "6209100",
                "category": "Delivery",
            },
        ),
        esperado=REJEITADA,
        campo_erro="merchant",
        tags=("payload", "rota"),
    ),
    RegistroSujo(
        caso="valor_numerico_absurdo",
        motivo="Valor numérico acima do teto de 1 bi (erro de escala do conector)",
        payload=_tx_pluggy("valor_numerico_absurdo", amount=1e12, type=None),
        esperado=REJEITADA,
        campo_erro="amount",
        tags=("valor", "seguranca"),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # C) OUTROS BANCOS DO MESMO USUÁRIO (mapeamentos não-padrão)
    # ══════════════════════════════════════════════════════════════════════
    RegistroSujo(
        caso="itau_portugues",
        motivo="Itaú manda os campos em português: conta/data/valor/descricao/tipo/saldo",
        payload={
            "nexaCaso": "itau_portugues",
            "id": "tx_itau_portugues",
            "conta": "acc_itau_9999",
            "data": DATA_BR_STR,
            "valor": "1.234,56",
            "descricao": "COMPRA CARTAO SUPERMERCADO",
            "tipo": "DEBITO",
            "saldo": "5.000,00",
        },
        esperado=VALIDA,
        banco="itau",
        tags=("mapeamento",),
    ),
    RegistroSujo(
        caso="inter_value",
        motivo="Inter usa 'value' em vez de 'amount'",
        payload={
            "nexaCaso": "inter_value",
            "id": "tx_inter_value",
            "accountId": "acc_inter_7777",
            "date": DATA_SQL_STR,
            "description": "PIX ENVIADO MERCADO",
            "value": -33.90,
        },
        esperado=VALIDA,
        banco="inter",
        tags=("mapeamento",),
    ),
    RegistroSujo(
        caso="banco_nao_mapeado",
        motivo="Conector fora do radar (cooperativa regional) → DefaultStrategy",
        payload=_tx_pluggy("banco_nao_mapeado", accountId="acc_coop_5555"),
        esperado=VALIDA,
        banco="coopregional",
        tags=("mapeamento",),
    ),
]


def _catalogo(banco: str) -> list[RegistroSujo]:
    return [r for r in CATALOGO if r.banco == banco]


def _por_caso(caso: str) -> RegistroSujo:
    return next(r for r in CATALOGO if r.caso == caso)


BANCOS = ("nubank", "itau", "inter", "coopregional")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FIXTURES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.fixture(scope="module")
def batches() -> dict[str, TransactionBatchResult]:
    """Um lote sujo por banco, validado exatamente como a rota de sync faz."""
    return {
        banco: TransactionBatchResult.from_raw_batch(
            raw_data=[r.payload for r in _catalogo(banco)],
            institution_id=banco,
            item_id=ITEM_ID,
            fetched_at=AGORA,
        )
        for banco in BANCOS
    }


@pytest.fixture(scope="module")
def batch_nubank(batches) -> TransactionBatchResult:
    return batches["nubank"]


@pytest.fixture(scope="module")
def validas(batches) -> dict[str, TransactionWebhook]:
    """Transações aprovadas, indexadas por transaction_id (facilita o assert)."""
    return {
        tx.transaction_id: tx
        for batch in batches.values()
        for tx in batch.valid_transactions
    }


@pytest.fixture(scope="module")
def ingestao(batches):
    """Saída do TransactionIngestor com os 4 bancos no mesmo DataFrame."""
    todas = [tx for batch in batches.values() for tx in batch.valid_transactions]
    return TransactionIngestor().process(todas)


@pytest.fixture(scope="module")
def df_ingerido(ingestao) -> pl.DataFrame:
    return ingestao[0]


@pytest.fixture(scope="module")
def metricas_ingestor(ingestao):
    return ingestao[1]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CAMADA 1 — VALIDAÇÃO TOLERANTE (firewall Pydantic + DLQ)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestCamada1ValidacaoTolerante:
    """
    Filosofia declarada no schema: "99 transações válidas > 0 transações".
    Um registro podre não pode levar o lote inteiro junto.
    """

    def test_lote_sujo_mantem_as_validas_e_isola_as_rejeitadas(self, batches):
        esperadas_ok = {r.tx_id for r in CATALOGO if r.esperado == VALIDA}
        esperadas_rej = {r.caso for r in CATALOGO if r.esperado == REJEITADA}

        aprovadas = {
            tx.transaction_id for b in batches.values() for tx in b.valid_transactions
        }
        rejeitadas = {
            r.transaction_id for b in batches.values() for r in b.rejected_transactions
        }

        faltando = esperadas_ok - aprovadas
        assert not faltando, f"transações recuperáveis foram descartadas: {sorted(faltando)}"

        for caso in esperadas_rej:
            registro = _por_caso(caso)
            # 'sem_id' não tem id para rastrear — checado pelo total abaixo
            if registro.tx_id:
                assert registro.tx_id in rejeitadas, (
                    f"caso '{caso}' deveria ter ido para o DLQ ({registro.motivo})"
                )

        total_recebido = sum(b.total_received for b in batches.values())
        total_valido = sum(b.total_valid for b in batches.values())
        total_rejeitado = sum(b.total_rejected for b in batches.values())

        assert total_recebido == len(CATALOGO)
        assert total_valido == len(esperadas_ok)
        assert total_rejeitado == len(esperadas_rej)
        assert total_valido + total_rejeitado == total_recebido, "nenhum registro pode sumir"

        print(
            f"\n   📥 lote sujo: {total_recebido} recebidas → "
            f"{total_valido} válidas / {total_rejeitado} no DLQ"
        )
        for tag in sorted({t for r in CATALOGO for t in r.tags}):
            do_tipo = [r for r in CATALOGO if tag in r.tags]
            ok = sum(1 for r in do_tipo if r.esperado == VALIDA)
            print(f"      • {tag:<11} {len(do_tipo):>2} casos → {ok} recuperados, {len(do_tipo) - ok} DLQ")

    @pytest.mark.parametrize(
        "registro",
        [r for r in CATALOGO if r.esperado == REJEITADA],
        ids=lambda r: r.caso,
    )
    def test_dlq_registra_causa_por_campo_para_auditoria(self, batches, registro):
        """DLQ precisa dizer O QUE quebrou e guardar o payload cru p/ reprocesso."""
        batch = batches[registro.banco]
        alvo = next(
            (
                r
                for r in batch.rejected_transactions
                if r.raw_data.get("nexaCaso") == registro.caso
            ),
            None,
        )
        assert alvo is not None, f"caso '{registro.caso}' não chegou ao DLQ"

        assert alvo.error_type == "ValidationError"
        assert alvo.institution_id == registro.banco
        assert alvo.raw_data, "payload cru tem que ser preservado para reprocessamento"
        assert registro.campo_erro in alvo.field_errors, (
            f"esperava erro em '{registro.campo_erro}', veio {list(alvo.field_errors)}"
        )

    def test_registro_que_nao_e_objeto_json_vai_para_o_dlq(self):
        """
        Um None/string/lista no array 'results' (conector truncando resposta)
        não pode derrubar o lote: vai para o DLQ como qualquer outro registro.
        """
        batch = TransactionBatchResult.from_raw_batch(
            raw_data=[_tx_pluggy("boa_entre_lixo"), None, "quebrado", []],
            institution_id="nubank",
            item_id=ITEM_ID,
            fetched_at=AGORA,
        )

        assert batch.total_valid == 1, "a transação boa tem que sobreviver ao lixo"
        assert batch.total_rejected == 3
        assert batch.error_summary.get("TypeError") == 3

        auditavel = [r for r in batch.rejected_transactions if r.error_type == "TypeError"]
        assert all("_invalid_payload" in r.raw_data for r in auditavel), (
            "o registro inválido tem que ficar auditável no DLQ"
        )
        assert any("NoneType" in r.error_message for r in auditavel)

    def test_lote_totalmente_corrompido_gera_alerta_critico(self):
        """Conector quebrado devolve lixo: o batch tem que gritar, não passar batido."""
        batch = TransactionBatchResult.from_raw_batch(
            raw_data=[
                {"id": "x1", "amount": None},
                {"foo": "bar"},
                {"id": "x3", "accountId": "a", "date": None, "amount": 1},
            ],
            institution_id="nubank",
            item_id=ITEM_ID,
            fetched_at=AGORA,
        )

        assert batch.total_valid == 0
        assert batch.rejection_rate == 1.0
        assert batch.alert_level == "CRITICAL"
        assert batch.should_alert is True
        assert "100.0%" in (batch.alert_message or "")
        assert batch.error_summary.get("ValidationError") == 3

    def test_taxa_de_rejeicao_acima_do_limite_gera_warning(self):
        """20%+ de rejeição = degradação do conector → WARNING para o time."""
        boas = [_tx_pluggy(f"ok_{i}", dias_atras=i + 1) for i in range(3)]
        ruim = _tx_pluggy("ruim", date=None)

        batch = TransactionBatchResult.from_raw_batch(
            raw_data=[*boas, ruim],
            institution_id="nubank",
            item_id=ITEM_ID,
            fetched_at=AGORA,
        )

        assert batch.rejection_rate == pytest.approx(0.25)
        assert batch.alert_level == "WARNING"
        assert batch.should_alert is True
        assert batch.field_error_summary.get("transaction_date") == 1

    def test_lote_vazio_nao_quebra_e_nao_alerta(self):
        """Sync de conta sem movimento no período: caso normal, não é erro."""
        batch = TransactionBatchResult.from_raw_batch(
            raw_data=[], institution_id="nubank", item_id=ITEM_ID, fetched_at=AGORA
        )
        assert batch.total_received == 0
        assert batch.rejection_rate == 0.0
        assert batch.alert_level == "INFO"
        assert batch.should_alert is False

    def test_fetched_at_no_futuro_e_rejeitado(self):
        """Relógio adiantado do worker não pode contaminar a base."""
        batch = TransactionBatchResult.from_raw_batch(
            raw_data=[_tx_pluggy("clock_skew")],
            institution_id="nubank",
            item_id=ITEM_ID,
            fetched_at=AGORA + timedelta(hours=2),
        )
        assert batch.total_valid == 0
        assert "root" in batch.rejected_transactions[0].field_errors


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CAMADA 2 — PARSING DOS CAMPOS SUJOS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestCamada2ParsingDeCamposSujos:
    """O valor que chega feio tem que virar Decimal/datetime corretos."""

    @pytest.mark.parametrize(
        "caso,esperado",
        [
            ("valor_string_br", Decimal("1234.56")),
            ("valor_string_us", Decimal("1234.56")),
            ("valor_contabil", Decimal("-89.90")),
            ("valor_com_espaco", Decimal("1500.00")),
            ("valor_zero", Decimal("0")),
        ],
    )
    def test_valores_monetarios_do_mercado_br(self, validas, caso, esperado):
        tx = validas[f"tx_{caso}"]
        assert tx.amount == esperado, f"{caso}: {tx.amount} != {esperado}"

    @pytest.mark.parametrize(
        "caso,esperado",
        [
            ("data_sql_naive", DATA_SQL_UTC),
            ("data_br", DATA_BR_UTC),
            ("data_so_dia", DATA_SO_DIA_UTC),
        ],
    )
    def test_datas_sem_fuso_viram_utc_assumindo_horario_de_brasilia(
        self, validas, caso, esperado
    ):
        tx = validas[f"tx_{caso}"]
        assert tx.transaction_date.tzinfo is not None, "data tem que ser timezone-aware"
        assert tx.transaction_date.utcoffset() == timedelta(0), "tem que estar em UTC"
        assert tx.transaction_date == esperado

    def test_sinal_do_valor_e_corrigido_pelo_campo_type(self, validas):
        debito = validas["tx_sinal_invertido_debito"]
        credito = validas["tx_sinal_invertido_credito"]

        assert debito.amount == Decimal("-250.00"), "DEBIT tem que ficar negativo"
        assert credito.amount == Decimal("180.00"), "CREDIT tem que ficar positivo"

    def test_descricao_e_sanitizada_contra_html_e_bytes_de_controle(self, validas):
        xss = validas["tx_descricao_xss"]
        controle = validas["tx_descricao_controle"]
        unicode_ok = validas["tx_descricao_unicode"]

        assert "<script>" not in xss.description
        assert "alert" not in xss.description
        assert xss.description == "MERCADO PAO DE ACUCAR"

        assert "\x00" not in controle.description
        assert "\x07" not in controle.description
        assert controle.description == "PAG UBER TRIP", "espaços duplicados normalizados"

        # sanitização não pode destruir nome legítimo de lojista
        assert unicode_ok.description == "MERCADO SÃO JOÃO 🛒 — PAGAMENTO"

    def test_descricao_vazia_cai_para_observations(self, validas):
        tx = validas["tx_descricao_vazia_com_observacao"]
        assert tx.description == "TARIFA PACOTE DE SERVICOS"

    def test_descricao_nula_cai_para_description_raw(self, validas):
        """
        Fallback documentado do schema: description → description_raw →
        observations. A Pluggy manda 'descriptionRaw' em camelCase, mapeado
        no _normalize_webhook_fields.
        """
        tx = validas["tx_descricao_nula"]
        assert tx.description == "IFD*IFOOD DELIVERY BR"

    def test_descricao_longa_e_truncada_e_nao_descarta_a_transacao(self, validas):
        """Perder a transação por causa do texto é pior do que cortar o texto."""
        tx = validas["tx_descricao_gigante"]
        assert len(tx.description) == 500
        assert tx.amount == Decimal("-63.9"), "o valor sobreviveu intacto"

    def test_teto_de_seguranca_vale_para_valor_numerico_e_nao_so_string(self, validas, batches):
        """
        O limite de R$ 1 bi tem que valer para float/int também — era só a via
        string que passava pelo check, e valor com erro de escala entrava na base.
        """
        rejeitadas = {
            r.raw_data.get("nexaCaso") for r in batches["nubank"].rejected_transactions
        }
        assert "valor_numerico_absurdo" in rejeitadas
        assert "valor_texto_absurdo" in rejeitadas
        assert "tx_valor_numerico_absurdo" not in validas

    def test_valor_nao_finito_e_rejeitado(self):
        """NaN/Infinity num campo monetário envenenam todo cálculo a jusante."""
        batch = TransactionBatchResult.from_raw_batch(
            raw_data=[
                _tx_pluggy("valor_nan", amount=float("nan"), type=None),
                _tx_pluggy("valor_inf", amount=float("inf"), type=None),
            ],
            institution_id="nubank",
            item_id=ITEM_ID,
            fetched_at=AGORA,
        )
        assert batch.total_valid == 0
        assert all("amount" in r.field_errors for r in batch.rejected_transactions)

    @pytest.mark.parametrize(
        "caso,esperado",
        [
            ("status_processed", TransactionStatus.PROCESSED),
            ("status_minusculo", TransactionStatus.PENDING),
            ("status_nulo", TransactionStatus.POSTED),
            ("status_desconhecido", TransactionStatus.POSTED),
        ],
    )
    def test_status_exotico_nao_derruba_a_transacao(self, validas, caso, esperado):
        assert validas[f"tx_{caso}"].status == esperado

    def test_saldo_em_texto_e_saldo_ausente(self, validas):
        assert validas["tx_saldo_string_br"].balance == Decimal("1849.50")
        assert validas["tx_saldo_vazio"].balance is None, "cartão sem saldo → None (Polars estima)"

    def test_campos_desconhecidos_da_pluggy_sao_ignorados_sem_erro(self, validas):
        """paymentData/MCC não podem quebrar a validação."""
        tx = validas["tx_campos_extras_pluggy"]
        assert tx.account_id == ACC_CARTAO
        assert tx.amount == Decimal("-63.9")
        assert not hasattr(tx, "paymentData")

    def test_parcelas_vem_do_credit_card_metadata(self, validas):
        """A Pluggy já diz 'parcela 2 de 10' — não precisa adivinhar por regex."""
        tx = validas["tx_campos_extras_pluggy"]
        assert tx.installment_number == 2
        assert tx.installment_total == 10

    def test_parcela_incoerente_do_conector_e_ignorada_sem_perder_a_transacao(self):
        """
        Conector com o bug de "13 de 12" não pode custar a transação:
        parcela é melhorador, não campo fundamental.
        """
        batch = TransactionBatchResult.from_raw_batch(
            raw_data=[
                _tx_pluggy(
                    "parcela_metadata_quebrada",
                    creditCardMetadata={"installmentNumber": 13, "totalInstallments": 12},
                )
            ],
            institution_id="nubank",
            item_id=ITEM_ID,
            fetched_at=AGORA,
        )
        assert batch.total_valid == 1
        assert batch.valid_transactions[0].installment_number is None

    def test_moeda_estrangeira_nao_e_gravada_como_real(self):
        """currencyCode=USD virava BRL: o valor em dólar entrava no fluxo como R$."""
        batch = TransactionBatchResult.from_raw_batch(
            raw_data=[_tx_pluggy("compra_em_dolar", currencyCode="USD", description="AMAZON US")],
            institution_id="nubank",
            item_id=ITEM_ID,
            fetched_at=AGORA,
        )
        assert batch.total_valid == 1
        assert batch.valid_transactions[0].currency.value == "USD"

    def test_mapeamento_de_campos_do_itau_e_do_inter(self, validas):
        itau = validas["tx_itau_portugues"]
        assert itau.account_id == "acc_itau_9999", "conta → account_id"
        assert itau.amount == Decimal("-1234.56"), "valor 'DEBITO' vira negativo"
        assert itau.description == "COMPRA CARTAO SUPERMERCADO"
        assert itau.transaction_date == DATA_BR_UTC

        inter = validas["tx_inter_value"]
        assert inter.amount == Decimal("-33.9"), "value → amount"

    def test_reenvio_de_webhook_produz_o_mesmo_dedup_hash(self):
        """
        A Pluggy reentrega o mesmo lote (retry) e, ao reprocessar um item,
        chega a gerar IDs novos para a MESMA transação. O hash composto
        (conta+data+valor+descrição) é o que permite detectar isso.
        """
        original = _tx_pluggy("reenvio", dias_atras=2)
        mesmo_id = dict(original)
        id_novo = {**original, "id": "tx_reenvio_id_novo"}
        outro_valor = {**original, "id": "tx_outro", "amount": -99.90}

        batch = TransactionBatchResult.from_raw_batch(
            raw_data=[original, mesmo_id, id_novo, outro_valor],
            institution_id="nubank",
            item_id=ITEM_ID,
            fetched_at=AGORA,
        )
        hashes = [tx.dedup_hash for tx in batch.valid_transactions]

        assert hashes[0] == hashes[1] == hashes[2], "mesmo conteúdo → mesmo hash"
        assert hashes[3] != hashes[0], "valor diferente → hash diferente"
        assert all(len(h) == 64 for h in hashes), "sha256 hex"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CAMADA 3 — INGESTOR (Polars + BankStrategy) COM 4 BANCOS NO MESMO LOTE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestCamada3IngestorMultiBanco:

    def test_ingestor_processa_todos_os_bancos_sem_perder_linha(
        self, df_ingerido, metricas_ingestor, batches
    ):
        total_validas = sum(b.total_valid for b in batches.values())

        assert df_ingerido.height == total_validas, "ingestor não pode perder transação"
        assert metricas_ingestor.total_records == total_validas
        assert metricas_ingestor.duplicates_removed == 0, "não há reentrega neste lote"
        assert (
            metricas_ingestor.trusted_count
            + metricas_ingestor.degraded_count
            + metricas_ingestor.untrusted_count
            == total_validas
        ), "toda linha precisa de um data_status"
        assert metricas_ingestor.processing_time_ms >= 0

    def test_data_status_reflete_o_tier_do_banco(self, df_ingerido):
        """
        A strategy dá o TETO por banco: Nubank (TIER_1) TRUSTED; Itaú (TIER_3)
        e conector desconhecido (DefaultStrategy) DEGRADED.
        """
        status: dict[str, set[str]] = {}
        for linha in df_ingerido.select("institution_id", "data_status").unique().to_dicts():
            status.setdefault(linha["institution_id"], set()).add(linha["data_status"])

        assert "TRUSTED" in status["nubank"], "TIER_1 pode chegar a TRUSTED"
        assert status["itau"] == {"DEGRADED"}
        assert status["inter"] == {"DEGRADED"}, (
            "única transação da conta, sem saldo e sem âncora → rebaixada"
        )
        assert status["coopregional"] == {"DEGRADED"}, (
            "banco fora do radar cai no fallback conservador"
        )

    def test_bancos_reconhecidos_ganham_strategy_por_tier(self):
        """
        Bradesco/Santander/C6 eram identificados e mesmo assim caíam na
        DefaultStrategy (a porta abria para uma sala vazia). Agora recebem
        TieredStrategy com o teto do tier real do banco.
        """
        from app.core.schemas.enums import BankTier
        from app.forecast.etl.bank_strategy import get_bank_strategy
        from app.forecast.etl.bank_strategy.strategies.default import DefaultStrategy
        from app.forecast.etl.bank_strategy.strategies.tiered import TieredStrategy

        casos = {
            "c6": BankTier.TIER_1,
            "btg": BankTier.TIER_1,
            "bradesco": BankTier.TIER_3,
            "santander": BankTier.TIER_3,
            "picpay": BankTier.TIER_4,
        }
        for banco, tier in casos.items():
            strategy = get_bank_strategy(banco)
            assert isinstance(strategy, TieredStrategy), f"{banco} ainda cai no fallback"
            assert strategy.tier == tier

        assert isinstance(get_bank_strategy("coopregional"), DefaultStrategy)

    def test_teto_por_tier_no_lote_real(self):
        """C6 (TIER_1) com dados completos chega a TRUSTED; Bradesco (TIER_3), não."""
        rows_por_banco = {
            banco: [
                _tx_pluggy(f"{banco}_tier_{i}", dias_atras=i + 1, accountId=f"acc_{banco}")
                for i in range(3)
            ]
            for banco in ("c6", "bradesco")
        }

        status = {}
        for banco, rows in rows_por_banco.items():
            batch = TransactionBatchResult.from_raw_batch(
                raw_data=rows, institution_id=banco, item_id=ITEM_ID, fetched_at=AGORA
            )
            df, _ = TransactionIngestor().process(batch.valid_transactions)
            status[banco] = set(df["data_status"].to_list())

        assert status["c6"] == {"TRUSTED"}
        assert status["bradesco"] == {"DEGRADED"}, "TIER_3 nunca passa de DEGRADED"

    def test_lacuna_de_uma_linha_nao_contamina_o_lote(self, df_ingerido):
        """
        Antes o veredito era por LOTE: um saldo nulo em 50 transações marcava
        as 50 como DEGRADED. Agora a lacuna é da linha — e quando a conta tem
        âncora de saldo, o cumsum preenche e a linha nem é rebaixada.
        """
        nubank = df_ingerido.filter(pl.col("institution_id") == "nubank")

        sem_saldo = nubank.filter(pl.col("transaction_id") == "tx_saldo_vazio")
        assert sem_saldo["balance"].null_count() == 0, (
            "a conta tem saldos reais nas vizinhas — o cumsum tinha que preencher"
        )
        assert sem_saldo["balance_estimated"].to_list() == [True], (
            "saldo derivado tem que ficar marcado como estimativa"
        )
        assert sem_saldo["data_status"].to_list() == ["TRUSTED"], (
            "lacuna preenchida por estimativa não rebaixa a linha"
        )

        vizinhas = nubank.filter(~pl.col("balance_estimated"))
        assert set(vizinhas["data_status"].to_list()) == {"TRUSTED"}, (
            "as linhas completas do mesmo lote continuam confiáveis"
        )

    def test_conta_sem_nenhuma_ancora_de_saldo_nao_inventa_dinheiro(self):
        """
        Cartão que nunca manda saldo: sem âncora, estimar seria inventar.
        O saldo fica nulo e a linha é rebaixada — comportamento honesto.
        """
        rows = [
            _tx_pluggy(
                f"cartao_sem_saldo_{i}",
                dias_atras=i + 1,
                accountId="acc_cartao_orfa",
                balance=None,
            )
            for i in range(4)
        ]
        batch = TransactionBatchResult.from_raw_batch(
            raw_data=rows, institution_id="nubank", item_id=ITEM_ID, fetched_at=AGORA
        )
        df, _ = TransactionIngestor().process(batch.valid_transactions)

        assert df["balance"].null_count() == df.height, "não pode chutar saldo do nada"
        assert not df["balance_estimated"].any()
        assert set(df["data_status"].to_list()) == {"DEGRADED"}

    def test_cumsum_reconstroi_o_saldo_na_ordem_cronologica(self):
        """
        Âncora no meio da série: as linhas ANTES dela também são
        reconstruídas (saldo_anterior = âncora − movimentos entre elas).
        """
        rows = [
            _tx_pluggy("extrato_1", dias_atras=3, accountId="acc_cumsum",
                       amount=-100.0, balance=None),
            _tx_pluggy("extrato_2", dias_atras=2, accountId="acc_cumsum",
                       amount=-50.0, balance=850.0),   # única âncora real
            _tx_pluggy("extrato_3", dias_atras=1, accountId="acc_cumsum",
                       amount=200.0, balance=None, type="CREDIT"),
        ]
        batch = TransactionBatchResult.from_raw_batch(
            raw_data=rows, institution_id="nubank", item_id=ITEM_ID, fetched_at=AGORA
        )
        df, _ = TransactionIngestor().process(batch.valid_transactions)

        por_id = {r["transaction_id"]: r for r in df.to_dicts()}
        assert por_id["tx_extrato_1"]["balance"] == pytest.approx(900.0), (
            "antes da âncora: 850 + 50 (desfaz o débito seguinte)"
        )
        assert por_id["tx_extrato_2"]["balance"] == pytest.approx(850.0)
        assert por_id["tx_extrato_2"]["balance_estimated"] is False
        assert por_id["tx_extrato_3"]["balance"] == pytest.approx(1050.0), (
            "depois da âncora: 850 + 200 (crédito)"
        )

    def test_normalizacao_e_colunas_derivadas(self, df_ingerido):
        # tipos convertidos para o Polars
        assert df_ingerido.schema["amount"] == pl.Float64
        assert df_ingerido.schema["balance"] == pl.Float64

        # enriquecimento do passo 5 do ingestor
        for coluna in ("month", "day_of_week", "transaction_type", "data_status"):
            assert coluna in df_ingerido.columns, f"coluna '{coluna}' ausente"

        # texto normalizado (lowercase + trim) — description nunca fica nula
        descricoes = df_ingerido["description"].to_list()
        assert all(d is not None for d in descricoes)
        assert all(d == d.strip().lower() for d in descricoes)

        # DEBIT/CREDIT derivado do sinal, não do campo cru do banco
        derivado = df_ingerido.select("amount", "transaction_type").to_dicts()
        assert all(
            (linha["transaction_type"] == "DEBIT") == (linha["amount"] < 0)
            for linha in derivado
        )

    def test_ingestor_remove_reentregas_do_webhook(self):
        """
        Reentrega da Pluggy chega de duas formas: o mesmo lote de novo (id
        igual, que o upsert já resolveria) e o reprocessamento do item, que
        gera ID NOVO para a mesma transação — esse o upsert não pega. A
        deduplicação por dedup_hash no ingestor cobre os dois.
        """
        originais = [
            _tx_pluggy(f"unica_{i}", dias_atras=i + 1, amount=-(10.0 + i))
            for i in range(5)
        ]
        reenvios = [dict(originais[0]), {**originais[1], "id": "tx_reenvio_id_novo"}]

        batch = TransactionBatchResult.from_raw_batch(
            raw_data=[*originais, *reenvios],
            institution_id="nubank",
            item_id=ITEM_ID,
            fetched_at=AGORA,
        )
        df, metrics = TransactionIngestor().process(batch.valid_transactions)

        assert metrics.total_records == 7
        assert metrics.duplicates_removed == 2
        assert metrics.records_after_dedup == 5
        assert df.height == 5
        assert df["dedup_hash"].n_unique() == df.height

        # a primeira ocorrência é que fica (a de ID novo é a descartada)
        assert "tx_reenvio_id_novo" not in df["transaction_id"].to_list()
        assert df["transaction_id"].to_list()[:2] == ["tx_unica_0", "tx_unica_1"], (
            "a ordem cronológica do lote tem que ser preservada"
        )

    def test_politica_de_dedup_e_injetavel(self):
        """
        O ingestor aceita outra DedupPolicy (contrato DedupPolicy) — útil para
        bancos que reemitem transação legítima idêntica no mesmo dia.
        """

        class SemDedup(DefaultDedupPolicy):
            def apply(self, df):
                return df, 0

        originais = [_tx_pluggy("injetavel", dias_atras=1)]
        batch = TransactionBatchResult.from_raw_batch(
            raw_data=originais * 3,
            institution_id="nubank",
            item_id=ITEM_ID,
            fetched_at=AGORA,
        )

        df, metrics = TransactionIngestor(dedup_policy=SemDedup()).process(
            batch.valid_transactions
        )
        assert df.height == 3
        assert metrics.duplicates_removed == 0

    def test_chave_canonica_une_o_mesmo_gasto_escrito_por_bancos_diferentes(self):
        """
        O MESMO Netflix, como cada banco escreve. Sem chave canônica isso são
        5 estabelecimentos diferentes — e o Bradesco, que carimba a
        competência no texto, nunca forma série mensal.
        """
        escritas = {
            "nubank": "Netflix.com",
            "itau": "COMPRA CARTAO 1234 NETFLIX.COM SAO PAULO BR",
            "bradesco": "DEB AUT NETFLIX*ASSINAT 08/26",
            "inter": "PAGAMENTO NETFLIX ENTRETENIMENTO LTDA",
            "c6": "COMPRA NO DEBITO - NETFLIX - SAO PAULO",
        }

        chaves = set()
        for banco, descricao in escritas.items():
            batch = TransactionBatchResult.from_raw_batch(
                raw_data=[_tx_pluggy(f"netflix_{banco}", description=descricao, amount=-49.90)],
                institution_id=banco,
                item_id=ITEM_ID,
                fetched_at=AGORA,
            )
            df, _ = TransactionIngestor().process(batch.valid_transactions)
            chaves.add(df["merchant_key"][0])

        assert chaves == {"netflix"}, f"cada banco gerou uma chave diferente: {chaves}"

    @pytest.mark.parametrize(
        "descricao,chave",
        [
            ("PAG*IFOOD DELIVERY", "ifood"),      # prefixo de adquirente
            ("IFD*IFOOD 08/2026", "ifood"),
            ("COMPRA NO DEBITO - UBER *1234", "uber"),  # sufixo de cartão
            ("EC *PADARIA CENTRAL SP", "padaria central"),
            ("NETFLIX.COM", "netflix"),
        ],
    )
    def test_chave_sobrevive_ao_asterisco_dos_extratos(self, descricao, chave):
        """
        O asterisco separa coisas diferentes conforme o banco: adquirente à
        esquerda ("PAG*IFOOD") ou dígitos do cartão à direita ("UBER *1234").
        Cortar tudo depois dele deixava merchant "pag" e chave VAZIA — sem
        chave não há agrupamento de recorrência nem sinal de categoria.
        """
        batch = TransactionBatchResult.from_raw_batch(
            raw_data=[_tx_pluggy("asterisco", description=descricao)],
            institution_id="nubank",
            item_id=ITEM_ID,
            fetched_at=AGORA,
        )
        df, _ = TransactionIngestor().process(batch.valid_transactions)

        assert df["merchant_key"][0] == chave
        assert df["merchant_key"][0] != "", "chave vazia mata recorrência e categoria"

    def test_chave_canonica_preserva_a_descricao_original(self, df_ingerido):
        """A chave é coluna nova — extrato e auditoria continuam com o texto cru."""
        assert "merchant_key" in df_ingerido.columns

        itau = df_ingerido.filter(pl.col("institution_id") == "itau")
        assert itau["description"][0] == "compra cartao supermercado", (
            "a descrição original não pode ser sobrescrita pela chave"
        )
        assert itau["merchant_key"][0] == "supermercado"

    def test_moeda_estrangeira_e_convertida_para_brl(self):
        """
        Compra em dólar entrava na soma como se fossem reais — subestimando
        o gasto em ~5x. Converte na ingestão, congelando a taxa do dia, e
        preserva o valor original para o extrato mostrar "US$ 120 (R$ 648)".
        """
        from app.forecast.etl.currency import CurrencyConverter

        rows = [
            _tx_pluggy("compra_brl", dias_atras=5, amount=-100.0,
                       description="MERCADO", balance=1000.0),
            _tx_pluggy("compra_usd", dias_atras=2, amount=-120.0, currencyCode="USD",
                       description="AMAZON US", balance=None),
        ]
        batch = TransactionBatchResult.from_raw_batch(
            raw_data=rows, institution_id="nubank", item_id=ITEM_ID, fetched_at=AGORA
        )
        # Conversor com taxa fixa: teste não pode depender de cotação viva
        converter = CurrencyConverter(live=False)
        df, _ = TransactionIngestor().process(batch.valid_transactions)

        por_id = {r["transaction_id"]: r for r in df.to_dicts()}
        usd = por_id["tx_compra_usd"]
        brl = por_id["tx_compra_brl"]

        assert usd["original_currency"] == "USD"
        assert usd["original_amount"] == pytest.approx(-120.0), "original preservado"
        assert usd["fx_rate"] > 1.0
        assert usd["amount"] == pytest.approx(-120.0 * usd["fx_rate"]), "convertido"
        assert usd["amount"] < -500, "dólar não pode virar real 1:1"

        assert brl["fx_rate"] == 1.0
        assert brl["amount"] == pytest.approx(-100.0), "real não é convertido"

        # o cumsum roda depois da conversão: saldo estimado sai em BRL
        assert usd["balance"] == pytest.approx(1000.0 + usd["amount"])
        assert converter.rate_to_brl("BRL") == 1.0

    def test_moeda_sem_cotacao_nao_inventa_taxa(self):
        """Moeda fora da tabela mantém o valor original em vez de chutar."""
        from app.forecast.etl.currency import CurrencyConverter

        converter = CurrencyConverter(live=False)
        assert converter.rate_to_brl("JPY") == 1.0, "sem cotação → não converte"
        assert converter.rate_to_brl("USD") > 1.0

    def test_quality_score_mede_o_lote_de_verdade(self):
        """Era fixo em 1.0 — dizia '100% de qualidade' para qualquer lixo."""
        completo = [
            _tx_pluggy(f"completo_{i}", dias_atras=i + 1, accountId="acc_bom", balance=500.0 - i)
            for i in range(4)
        ]
        batch = TransactionBatchResult.from_raw_batch(
            raw_data=completo, institution_id="nubank", item_id=ITEM_ID, fetched_at=AGORA
        )
        _, met_bom = TransactionIngestor().process(batch.valid_transactions)

        ruim = [
            _tx_pluggy(f"ruim_{i}", dias_atras=i + 1, accountId="acc_ruim",
                       description="", descriptionRaw=None, observations=f"x{i}",
                       balance=500.0 if i == 0 else None)
            for i in range(4)
        ]
        batch_ruim = TransactionBatchResult.from_raw_batch(
            raw_data=ruim, institution_id="nubank", item_id=ITEM_ID, fetched_at=AGORA
        )
        _, met_ruim = TransactionIngestor().process(batch_ruim.valid_transactions)

        assert met_bom.quality_score == pytest.approx(1.0), "lote completo = 1.0"
        assert met_ruim.quality_score < met_bom.quality_score, (
            "lote com lacunas tem que pontuar menos"
        )

    def test_quality_score_nao_pune_conta_que_nunca_manda_saldo(self):
        """
        Cartão de crédito não tem saldo em transação — uma fatura perfeita
        não pode ficar eternamente em 0.70 por isso.
        """
        rows = [
            _tx_pluggy(f"fatura_{i}", dias_atras=i + 1, accountId="acc_cartao", balance=None)
            for i in range(5)
        ]
        batch = TransactionBatchResult.from_raw_batch(
            raw_data=rows, institution_id="nubank", item_id=ITEM_ID, fetched_at=AGORA
        )
        _, met = TransactionIngestor().process(batch.valid_transactions)

        assert met.quality_score == pytest.approx(1.0)

    def test_lote_vazio_e_erro_explicito(self):
        """Chamar o ingestor sem transação é bug do chamador — tem que estourar."""
        with pytest.raises(ValueError, match="vazia"):
            TransactionIngestor().process([])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CAMADA 4 — PIPELINE COMPLETO (steps 2 a 7) SOBRE O LOTE SUJO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestCamada4PipelineCompleto:

    @pytest.fixture(scope="class")
    def df_pipeline(self, df_ingerido) -> pl.DataFrame:
        # save_db fora: persistência tem teste próprio (Camada 5, com Session stub)
        return run_etl_pipeline(
            transactions_df=df_ingerido,
            user_id=USER_ID,
            account_id=ACC_CORRENTE,
            skip_steps=["save_db"],
            db=None,
        )

    def test_pipeline_completo_nao_perde_nem_corrompe_transacao(
        self, df_pipeline, df_ingerido
    ):
        assert df_pipeline.height == df_ingerido.height, "nenhum step pode dropar linha"
        assert df_pipeline["transaction_id"].null_count() == 0
        assert df_pipeline["amount"].null_count() == 0
        assert df_pipeline["transaction_date"].null_count() == 0
        assert df_pipeline["transaction_id"].n_unique() == df_pipeline.height

    def test_todos_os_steps_enriqueceram_o_dataframe(self, df_pipeline):
        esperadas = {
            "predicted_category": "Step 2 (classificador de categoria)",
            "category_source": "Step 2 (origem da categoria)",
            "is_recurring": "Step 3 (recorrências)",
            "is_installment": "Step 3 (parcelamentos)",
            "pf_pj_label": "Step 4 (contexto PF/PJ)",
        }
        faltando = {c: passo for c, passo in esperadas.items() if c not in df_pipeline.columns}
        assert not faltando, f"steps que não produziram coluna: {faltando}"

        assert df_pipeline["predicted_category"].null_count() == 0
        assert set(df_pipeline["pf_pj_label"].unique()) <= {"PF", "PJ", "UNCERTAIN"}

    def test_validador_de_qualidade_avalia_o_lote_sujo(self, df_pipeline):
        from app.forecast.etl.data_quality import DataQualityValidator

        relatorio = DataQualityValidator().validate(df_pipeline)

        assert 0.0 <= relatorio.overall_confidence <= 1.0
        assert 0.0 <= relatorio.temporal_coverage <= 1.0
        assert relatorio.gap_count >= 0
        assert relatorio.quality_level is not None
        # o lote tem uma transação de 12 anos atrás → cobertura temporal furada
        assert relatorio.gap_count > 0, "buracos de histórico têm que ser reportados"

        print(
            f"\n   🔎 qualidade do lote sujo: confiança={relatorio.overall_confidence:.2f} "
            f"nível={relatorio.quality_level} gaps={relatorio.gap_count} "
            f"anomalias={relatorio.anomaly_count}"
        )

    def test_steps_finais_rodam_sem_erro_com_lote_sujo(self, df_ingerido, caplog):
        """
        Step 7 (perfil + IncomeProfiler) rodava sempre no except em produção:
        o log usava profile.score (atributo inexistente) e o IncomeProfiler
        procurava a coluna 'date' num DataFrame que usa 'transaction_date'.
        """
        caplog.set_level(logging.WARNING)

        run_etl_pipeline(
            transactions_df=df_ingerido,
            user_id=USER_ID,
            skip_steps=["save_db"],
            db=None,
        )

        erros = [
            r.getMessage()
            for r in caplog.records
            if r.levelno >= logging.ERROR and "Erro no Step" in r.getMessage()
        ]
        assert not erros, f"steps do pipeline falharam: {erros}"

        sem_colunas = [
            r.getMessage()
            for r in caplog.records
            if "IncomeProfiler" in r.getMessage() and "ausentes" in r.getMessage()
        ]
        assert not sem_colunas, "IncomeProfiler não enxergou as colunas do ETL"

    def test_assinatura_e_detectada_mesmo_com_competencia_na_descricao(self):
        """
        Bradesco escreve "DEB AUT NETFLIX*ASSINAT 08/26" — a descrição muda
        todo mês. Agrupando por descrição, ele perdia 100% das assinaturas.
        """
        rows = []
        for mes in range(6):
            dia = AGORA - timedelta(days=30 * mes + 4)
            rows.append(
                _tx_pluggy(
                    f"bradesco_netflix_{mes}",
                    dias_atras=30 * mes + 4,
                    amount=-49.90,
                    description=f"DEB AUT NETFLIX*ASSINAT {dia.strftime('%m/%y')}",
                )
            )

        batch = TransactionBatchResult.from_raw_batch(
            raw_data=rows, institution_id="bradesco", item_id=ITEM_ID, fetched_at=AGORA
        )
        df, _ = TransactionIngestor().process(batch.valid_transactions)
        processado = run_etl_pipeline(
            transactions_df=df, user_id=USER_ID, skip_steps=["save_db"], db=None
        )

        assert processado["merchant_key"].n_unique() == 1, "os 6 meses são o mesmo serviço"
        assert processado["is_recurring"].all(), "as 6 cobranças são uma assinatura"

    def test_parcelamento_fixo_nao_vira_assinatura(self):
        """
        Contrapartida da chave canônica: sem o contador "4/10", um
        parcelamento de valor fixo fica idêntico a uma assinatura. Parcela
        tem que vencer — senão o Shadow Invoice projeta cobrança eterna de
        algo que acaba na décima.
        """
        rows = [
            _tx_pluggy(
                f"parcela_notebook_{n}",
                dias_atras=30 * n + 3,
                amount=-389.90,
                description=f"PARCELA {n + 1}/10 - MAGAZINE LUIZA NOTEBOOK DELL",
            )
            for n in range(6)
        ]

        batch = TransactionBatchResult.from_raw_batch(
            raw_data=rows, institution_id="nubank", item_id=ITEM_ID, fetched_at=AGORA
        )
        df, _ = TransactionIngestor().process(batch.valid_transactions)
        processado = run_etl_pipeline(
            transactions_df=df, user_id=USER_ID, skip_steps=["save_db"], db=None
        )

        assert processado["merchant_key"].n_unique() == 1, "as parcelas são o mesmo bem"
        assert processado["is_installment"].any(), "tem que ser reconhecido como parcelamento"
        assert not processado["is_recurring"].any(), "parcelamento não é assinatura"

    def test_despesa_fixa_nao_vira_parcelamento(self):
        """
        Aluguel/condomínio: série mensal de valor fixo SEM marcador de
        parcela. O chute por padrão do InstallmentDetector marcava como
        parcelamento — e o Shadow Invoice projetava um "plano" com fim para
        uma despesa que não acaba nunca.
        """
        despesas = {
            "aluguel": ("TED ENVIADA - ALUGUEL APARTAMENTO SAO PAULO", -2200.0),
            "condominio": ("PAGAMENTO BOLETO - CONDOMINIO ED PRIMAVERA", -680.0),
        }
        for nome, (descricao, valor) in despesas.items():
            rows = [
                _tx_pluggy(f"{nome}_{m}", dias_atras=30 * m + 5,
                           amount=valor, description=descricao)
                for m in range(6)
            ]
            batch = TransactionBatchResult.from_raw_batch(
                raw_data=rows, institution_id="nubank", item_id=ITEM_ID, fetched_at=AGORA
            )
            df, _ = TransactionIngestor().process(batch.valid_transactions)
            out = run_etl_pipeline(
                transactions_df=df, user_id=USER_ID, skip_steps=["save_db"], db=None
            )
            assert not out["is_installment"].any(), f"{nome} não é parcelamento"

        # E o marcador explícito continua valendo — inclusive acima de 12x
        rows = [
            _tx_pluggy(f"moto_{m}", dias_atras=30 * m + 5, amount=-450.0,
                       description=f"FINANCIAMENTO MOTO {m + 13}/24")
            for m in range(4)
        ]
        batch = TransactionBatchResult.from_raw_batch(
            raw_data=rows, institution_id="nubank", item_id=ITEM_ID, fetched_at=AGORA
        )
        df, _ = TransactionIngestor().process(batch.valid_transactions)
        out = run_etl_pipeline(
            transactions_df=df, user_id=USER_ID, skip_steps=["save_db"], db=None
        )
        assert out["is_installment"].any(), "15/24 tem numerador > 12 — é parcela, não mês"

    def test_classificacao_pf_pj_vem_com_confianca(self, df_pipeline):
        """
        context_confidence alimentará o badge da UI e o filtro do agente —
        ficava sempre nulo porque nenhuma via o produzia.
        """
        assert "pf_pj_confidence" in df_pipeline.columns
        assert df_pipeline["pf_pj_confidence"].null_count() == 0

        conf = df_pipeline.select(
            pl.col("pf_pj_confidence").min().alias("min"),
            pl.col("pf_pj_confidence").max().alias("max"),
        ).to_dicts()[0]
        assert 0.0 < conf["min"] <= conf["max"] <= 1.0

        # UNCERTAIN tem que valer menos que uma classificação decidida
        por_label = {
            r["pf_pj_label"]: r["conf"]
            for r in df_pipeline.group_by("pf_pj_label")
            .agg(pl.col("pf_pj_confidence").mean().alias("conf"))
            .to_dicts()
        }
        if "UNCERTAIN" in por_label and {"PF", "PJ"} & set(por_label):
            decididas = [v for k, v in por_label.items() if k != "UNCERTAIN"]
            assert por_label["UNCERTAIN"] < min(decididas)

    def test_assinatura_nao_vira_parcelamento_pelo_chute_do_detector(self):
        """
        Espelho do teste acima: sem marcador de parcela, o InstallmentDetector
        chuta parcelamento em qualquer série mensal de valor fixo — inclusive
        Netflix. As duas flags têm que ser excludentes no caso ambíguo, senão
        o Shadow Invoice projeta plano finito para assinatura contínua.
        """
        rows = [
            _tx_pluggy(
                f"netflix_competencia_{n}",
                dias_atras=30 * n + 3,
                amount=-49.90,
                description=f"DEB AUT NETFLIX*ASSINAT {(AGORA - timedelta(days=30 * n + 3)).strftime('%m/%y')}",
            )
            for n in range(6)
        ]

        batch = TransactionBatchResult.from_raw_batch(
            raw_data=rows, institution_id="bradesco", item_id=ITEM_ID, fetched_at=AGORA
        )
        df, _ = TransactionIngestor().process(batch.valid_transactions)
        processado = run_etl_pipeline(
            transactions_df=df, user_id=USER_ID, skip_steps=["save_db"], db=None
        )

        assert processado["is_recurring"].all(), "é assinatura"
        assert not processado["is_installment"].any(), (
            "competência '08/26' não é 'parcela 8 de 26'"
        )
        assert processado["installment_info"].null_count() == processado.height

    def test_ruido_do_adquirente_nao_desvia_a_categoria(self):
        """
        "compra cartao 1234 netflix.com sao paulo br" era classificado como
        Saúde: a regra casava com o ruído antes de chegar ao nome real.
        """
        limpo = _tx_pluggy("netflix_limpo", description="Netflix.com", amount=-49.90)
        sujo = _tx_pluggy(
            "netflix_sujo",
            description="COMPRA CARTAO 1234 NETFLIX.COM SAO PAULO BR",
            amount=-49.90,
        )

        batch = TransactionBatchResult.from_raw_batch(
            raw_data=[limpo, sujo], institution_id="itau", item_id=ITEM_ID, fetched_at=AGORA
        )
        df, _ = TransactionIngestor().process(batch.valid_transactions)
        processado = run_etl_pipeline(
            transactions_df=df, user_id=USER_ID, skip_steps=["save_db"], db=None
        )

        categorias = processado["predicted_category"].unique().to_list()
        assert len(categorias) == 1, f"o mesmo gasto recebeu categorias diferentes: {categorias}"
        assert categorias[0] == "Lazer"

    def test_categoria_do_classificador_chega_ao_banco(self, df_pipeline):
        """
        `category` sempre existe (campo cru da Pluggy, em inglês), então o
        rename nunca disparava e o Step 2 era descartado no save.
        """
        from app.core.db import queries

        salvos: dict = {}

        class SessionQueSoRegistra:
            def execute(self, stmt, *a, **k):
                salvos["colunas"] = list(stmt.compile().params.keys())
                salvos["stmt"] = stmt

            def commit(self):
                pass

            def rollback(self):
                pass

        linhas = queries.save_transactions_clean(
            SessionQueSoRegistra(), df_pipeline, user_id=USER_ID, account_id=ACC_CORRENTE
        )

        assert linhas == df_pipeline.height
        gravado = {p for p in salvos["colunas"] if p.startswith("category")}
        assert gravado, "nenhuma categoria chegou ao INSERT"

        valores = {salvos["stmt"].compile().params[p] for p in gravado}
        assert "Entertainment" not in valores, "gravou a categoria crua do banco"
        assert valores & {"Lazer", "Alimentação", "Transporte", "Transferências", "Outros"}, (
            f"esperava categorias do classificador, veio {valores}"
        )

    def test_correcao_manual_do_usuario_e_aplicada(self):
        """
        `map_dict` foi removido no Polars 1.0: a linha levantava
        AttributeError, o except engolia e a correção do usuário ("isso é
        pessoal, não empresarial") NUNCA era aplicada. O feedback loop do F4
        estava morto em silêncio — e continuaria morto, porque o except
        devolve o DataFrame original sem reclamar.
        """
        from app.forecast.etl.runner import apply_user_overrides

        class _Override:
            transaction_id = "tx_corrigida"
            original_context = "PJ"
            corrected_context = "PF"
            reason = "gasto pessoal no cartão da empresa"
            created_at = None

        class _Query:
            def filter(self, *a, **k):
                return self

            def order_by(self, *a, **k):
                return self

            def all(self):
                return [_Override()]

        class _Db:
            def query(self, *a, **k):
                return _Query()

        df = pl.DataFrame({
            "transaction_id": ["tx_corrigida", "tx_intocada"],
            "pf_pj_label": ["PJ", "PJ"],
            "pf_pj_confidence": [0.6, 0.6],
        })

        out = apply_user_overrides(_Db(), df, USER_ID)
        por_id = {r["transaction_id"]: r for r in out.to_dicts()}

        assert por_id["tx_corrigida"]["pf_pj_label"] == "PF", "override não foi aplicado"
        assert por_id["tx_corrigida"]["context_override_by_user"] is True
        assert por_id["tx_corrigida"]["pf_pj_confidence"] == 1.0, "correção humana é certeza"

        assert por_id["tx_intocada"]["pf_pj_label"] == "PJ", "sem override, nada muda"
        assert por_id["tx_intocada"]["context_override_by_user"] is False

    def test_shadow_invoices_sao_persistidas(self, monkeypatch, tmp_path):
        """
        O Step 5 detectava obrigações futuras e jogava fora (TODO no runner):
        cada consulta reprocessava o histórico para redescobrir o mesmo, e
        nada podia comparar o previsto com o que de fato caiu.
        """
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.core.db.shadow_invoices import get_shadow_invoices, save_shadow_invoices
        from app.core.models.shadow_invoice import ShadowInvoice

        engine = create_engine(f"sqlite:///{tmp_path}/shadow.db")
        ShadowInvoice.__table__.create(engine)
        Session = sessionmaker(bind=engine)
        monkeypatch.setattr("app.core.database.SessionLocal", Session, raising=False)

        shadow_df = pl.DataFrame({
            "type": ["SUBSCRIPTION", "INSTALLMENT"],
            "amount": [-49.90, -389.90],
            "next_due_date": [AGORA + timedelta(days=12), AGORA + timedelta(days=20)],
            "metadata": [
                {"description": "netflix.com", "occurrences": 6},
                {"description": "parcela 4/10 - notebook dell", "occurrences": 4},
            ],
            "confidence": [0.9, 0.85],
        })

        assert save_shadow_invoices(USER_ID, shadow_df, account_id=ACC_CORRENTE) == 2

        salvas = get_shadow_invoices(USER_ID)
        assert {s["type"] for s in salvas} == {"SUBSCRIPTION", "INSTALLMENT"}

        netflix = next(s for s in salvas if s["type"] == "SUBSCRIPTION")
        assert netflix["merchant_key"] == "netflix", "indexada pela chave canônica"
        assert netflix["amount"] == pytest.approx(-49.90)
        assert netflix["occurrences"] == 6

        # Re-sync do mesmo período não pode empilhar duplicata
        save_shadow_invoices(USER_ID, shadow_df, account_id=ACC_CORRENTE)
        assert len(get_shadow_invoices(USER_ID)) == 2, "upsert por (user, chave, tipo)"

    def test_pipeline_e_resiliente_a_step_quebrado(self, df_ingerido, monkeypatch):
        """
        Contrato do runner: se um step explode (modelo indisponível, bug novo),
        o pipeline segue com o que já tem — não derruba o sync do usuário.
        """
        import app.forecast.etl.runner as runner_mod

        class ClassificadorQuebrado:
            def predict(self, df):
                raise RuntimeError("modelo CatBoost indisponível")

        monkeypatch.setattr(runner_mod, "TransactionClassifier", ClassificadorQuebrado)

        df = run_etl_pipeline(
            transactions_df=df_ingerido,
            user_id=USER_ID,
            skip_steps=["save_db"],
            db=None,
        )

        assert df.height == df_ingerido.height
        assert "predicted_category" not in df.columns, "step 2 caiu, mas o resto seguiu"
        assert "pf_pj_label" in df.columns, "step 4 tem que rodar mesmo com step 2 quebrado"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CAMADA 5 — A ROTA REAL DE SYNC (produção, ponta a ponta)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class _FakeQuery:
    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def all(self):
        return []

    def first(self):
        return None


class _FakeSession:
    """Session mínima: o teste não valida SQL, valida o fluxo do ETL."""

    def __init__(self):
        self.statements: list[Any] = []
        self.commits = 0
        self.rollbacks = 0

    def query(self, *a, **k):
        return _FakeQuery()

    def execute(self, stmt, *a, **k):
        self.statements.append(stmt)
        return None

    def add(self, _obj):
        pass

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _FakePluggyClient:
    """
    Devolve o payload EXATAMENTE como a Pluggy devolve — inclusive as duas
    coisas que só a rota resolve (merchant aninhado e description nula) e o
    lixo que nem é dict.
    """

    def get_item(self, item_id: str) -> dict:
        # É AQUI que a Pluggy diz qual é o banco — o objeto Account não traz
        # connector, por isso o sync resolve a instituição pelo item.
        return {
            "id": item_id,
            "status": "UPDATED",
            "connector": {"id": 212, "name": "Nubank", "institutionUrl": "https://nubank.com.br"},
        }

    def get_accounts(self, item_id: str) -> dict:
        return {
            "results": [
                {
                    "id": ACC_CORRENTE,
                    "type": "BANK",
                    "subtype": "CHECKING_ACCOUNT",
                    "name": "Conta Corrente",
                    "balance": 4210.55,
                    "currencyCode": "BRL",
                    "itemId": item_id,
                    # sem 'connector' → institution_id vira "unknown" (DefaultStrategy)
                },
                {
                    "id": ACC_CARTAO,
                    "type": "CREDIT",
                    "subtype": "CREDIT_CARD",
                    "name": "Cartão",
                    "balance": -1899.90,
                    "currencyCode": "BRL",
                    "itemId": item_id,
                    "connector": {"id": 201, "name": "Nubank"},
                },
                {"semId": True},  # conta corrompida no meio da lista
            ]
        }

    def get_transactions(self, account_id: str) -> dict:
        if account_id == ACC_CARTAO:
            return {
                "results": [
                    _tx_pluggy(
                        "rota_merchant_objeto",
                        accountId=account_id,
                        merchant={
                            "name": "Ifood",
                            "businessName": "IFOOD.COM AGENCIA DE RESTAURANTES LTDA",
                            "cnpj": "14380200000121",
                        },
                    ),
                    _tx_pluggy(
                        "rota_descricao_nula",
                        accountId=account_id,
                        description=None,
                        descriptionRaw="COMPRA CARTAO 4020 MERCADO",
                    ),
                    _tx_pluggy("rota_sem_data", accountId=account_id, date=None),
                    None,  # elemento nulo no array results
                    "registro-quebrado",  # elemento string no array results
                ]
            }
        return {
            "results": [
                _tx_pluggy("rota_pix", accountId=account_id, amount=3500.0, type="CREDIT",
                           description="PIX RECEBIDO SALARIO"),
                _tx_pluggy("rota_boleto", accountId=account_id, dias_atras=5,
                           amount="R$ 1.230,45", type="DEBIT",
                           description="PAGAMENTO BOLETO ENERGIA"),
            ]
        }


@pytest.fixture
def sync_com_pluggy_fake(monkeypatch):
    """
    Instala o cliente fake no runner de sync e neutraliza o snapshot de saldo
    (que abre Session própria e iria bater no Postgres).

    O corpo do sync mora em app/pluggy_sync/runner.py; a rota
    app/api/v1/routes/pluggy.py só delega para ele.
    """
    import app.core.db.balances as balances_mod
    import app.pluggy_sync.runner as runner_sync

    monkeypatch.setattr(runner_sync, "PluggyClient", lambda *a, **k: _FakePluggyClient())
    monkeypatch.setattr(balances_mod, "save_account_balances", lambda *a, **k: 2)
    return runner_sync


class TestCamada5RotaDeProducao:

    def test_sync_ponta_a_ponta_com_payload_sujo(self, sync_com_pluggy_fake):
        db = _FakeSession()
        progresso: list[dict] = []

        relatorio = sync_com_pluggy_fake.sync_item_transactions(
            db=db,
            user_id=USER_ID,
            item_id=ITEM_ID,
            on_progress=lambda **kwargs: progresso.append(kwargs),
        )

        assert relatorio["errors"] == [], "o sync não pode registrar erro com esse payload"
        assert relatorio["accounts"] == 2, "conta sem 'id' é ignorada, não quebra o sync"
        assert relatorio["received"] == 7, "5 do cartão (incl. lixo) + 2 da conta corrente"
        assert relatorio["valid"] == 4, "só 'rota_sem_data' é irrecuperável"
        assert relatorio["saved"] == 4
        assert relatorio["balances_saved"] == 2
        assert db.commits >= 1, "as transações limpas foram persistidas"

        # o progresso do long-polling/SSE continua sendo emitido com dado sujo
        assert [p["account_index"] for p in progresso] == [1, 2]

        print(
            f"\n   🔁 sync de produção: {relatorio['received']} recebidas → "
            f"{relatorio['valid']} válidas → {relatorio['saved']} salvas"
        )

    def test_sync_achata_merchant_aninhado_antes_do_schema(self, sync_com_pluggy_fake):
        """
        Sem esse achatamento, TODA transação de cartão da Pluggy (que sempre traz
        merchant como objeto) seria rejeitada pelo schema. Ver caso
        'merchant_objeto' do catálogo, que é rejeitado quando pula essa etapa.
        """
        cru = _FakePluggyClient().get_transactions(ACC_CARTAO)["results"]
        assert isinstance(cru[0]["merchant"], dict), "payload cru mesmo"

        db = _FakeSession()
        relatorio = sync_com_pluggy_fake.sync_item_transactions(
            db=db, user_id=USER_ID, item_id=ITEM_ID
        )

        # a transação de cartão com merchant aninhado sobreviveu ao caminho real
        assert relatorio["valid"] >= 2
        assert db.statements, "nenhum statement chegou ao banco"

        # e o schema, sozinho, continua rejeitando o formato cru:
        batch = TransactionBatchResult.from_raw_batch(
            raw_data=[cru[0]], institution_id="nubank", item_id=ITEM_ID, fetched_at=AGORA
        )
        assert batch.total_valid == 0
        assert "merchant" in batch.rejected_transactions[0].field_errors

    def test_sync_usa_description_raw_quando_description_vem_nula(self):
        """O sync copia descriptionRaw → description; sem isso, a linha morreria."""
        cru = _FakePluggyClient().get_transactions(ACC_CARTAO)["results"][1]
        assert cru["description"] is None

        # exatamente o que app/pluggy_sync/runner.py faz antes do schema
        normalizado = dict(cru)
        if not normalizado.get("description") and normalizado.get("descriptionRaw"):
            normalizado["description"] = normalizado["descriptionRaw"]

        batch = TransactionBatchResult.from_raw_batch(
            raw_data=[normalizado], institution_id="nubank", item_id=ITEM_ID, fetched_at=AGORA
        )
        assert batch.total_valid == 1
        assert batch.valid_transactions[0].description == "COMPRA CARTAO 4020 MERCADO"

    def test_banco_e_resolvido_pelo_item_e_nao_por_id_numerico(self, sync_com_pluggy_fake):
        """
        O /accounts real da Pluggy não traz 'connector' — quem traz é
        /items/{id}. Com o mapa antigo de IDs numéricos, toda conta bancária
        caía em "unknown" e a BankStrategy do banco nunca rodava.
        """
        contas = _FakePluggyClient().get_accounts(ITEM_ID)["results"]
        assert "connector" not in contas[0], "conta bancária real não traz connector"

        resolvido = sync_com_pluggy_fake._resolve_institution(_FakePluggyClient(), ITEM_ID)
        assert resolvido == "nubank", "o nome do conector no item tem que mandar"

        db = _FakeSession()
        relatorio = sync_com_pluggy_fake.sync_item_transactions(
            db=db, user_id=USER_ID, item_id=ITEM_ID
        )
        assert relatorio["errors"] == []

    def test_falha_ao_resolver_o_banco_nao_derruba_o_sync(self, sync_com_pluggy_fake, monkeypatch):
        """Perder o tratamento por banco é ruim; perder o sync inteiro é pior."""

        def get_item_quebrado(self, item_id):
            raise RuntimeError("Pluggy 503")

        monkeypatch.setattr(_FakePluggyClient, "get_item", get_item_quebrado)

        db = _FakeSession()
        relatorio = sync_com_pluggy_fake.sync_item_transactions(
            db=db, user_id=USER_ID, item_id=ITEM_ID
        )
        assert relatorio["errors"] == []
        assert relatorio["saved"] == 4, "seguiu com DefaultStrategy"

    def test_rejeicoes_sao_persistidas_na_dlq(self, monkeypatch, tmp_path):
        """
        Rejeitada morria no fim do request: conector degradando em produção
        era invisível. Agora fica com payload cru + erro por campo, e o lote
        podre gera alerta.
        """
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        import app.core.db.rejections as dlq
        from app.core.database import Base
        from app.core.models.rejected_transaction import RejectedTransactionRecord

        engine = create_engine(f"sqlite:///{tmp_path}/dlq.db")
        RejectedTransactionRecord.__table__.create(engine)
        Session = sessionmaker(bind=engine)
        monkeypatch.setattr("app.core.database.SessionLocal", Session, raising=False)

        # 1 boa + 3 podres → 75% de rejeição, muito acima do limiar
        batch = TransactionBatchResult.from_raw_batch(
            raw_data=[
                _tx_pluggy("dlq_boa"),
                _tx_pluggy("dlq_sem_data", date=None),
                _tx_pluggy("dlq_sem_valor", amount=None),
                _tx_pluggy("dlq_parcela", installment_number=13, installment_total=12),
            ],
            institution_id="bradesco",
            item_id=ITEM_ID,
            fetched_at=AGORA,
        )

        gravadas = dlq.save_rejected_transactions(
            user_id=USER_ID, item_id=ITEM_ID, institution_id="bradesco", batch_result=batch
        )
        assert gravadas == 3

        with Session() as db:
            linhas = db.query(RejectedTransactionRecord).all()
            assert len(linhas) == 3
            assert {l.institution_id for l in linhas} == {"bradesco"}
            assert all(l.user_id == USER_ID for l in linhas)
            assert all(l.batch_id == batch.batch_id for l in linhas), (
                "amarra a rejeição ao lote que a produziu"
            )
            assert all(l.raw_data for l in linhas), "payload cru p/ reprocessar"

            campos = set()
            for linha in linhas:
                campos.update(json.loads(linha.field_errors or "{}"))
            assert {"transaction_date", "amount"} <= campos

        # o alerta que só existia em memória agora é emitido
        alerta = dlq.alert_on_batch(batch, "bradesco", USER_ID)
        assert alerta and "75.0%" in alerta

        stats = dlq.rejection_stats(institution_id="bradesco", hours=24)
        assert stats.total == 3
        assert stats.por_campo, "estatística por campo é o que denuncia conector quebrado"

    @pytest.mark.asyncio
    async def test_endpoint_de_qualidade_traduz_a_dlq(self, monkeypatch):
        """
        DLQ gravada que ninguém lê continua sendo invisibilidade. O endpoint
        responde à pergunta do usuário ("cadê meus lançamentos?") e à nossa
        ("o conector quebrou?") — esta última é o campo dominante.
        """
        import app.forecast.router_data_quality as rota
        from app.core.db.rejections import RejectionStats

        stats = RejectionStats(
            institution_id="bradesco",
            total=5,
            por_erro={"ValidationError": 5},
            por_campo={"transaction_date": 4, "amount": 1},
            janela_horas=168,
        )
        monkeypatch.setattr(rota, "rejection_stats", lambda **kwargs: stats)

        resposta = await rota.get_data_quality(user_id=USER_ID, hours=168, institution_id=None)

        assert resposta["total_rejeitadas"] == 5
        assert resposta["por_campo"]["transaction_date"] == 4
        assert "transaction_date" in resposta["diagnostico"]
        assert "ATENCAO" in resposta["diagnostico"], (
            "campo dominante é assinatura de conector quebrado — tem que gritar"
        )

    @pytest.mark.asyncio
    async def test_endpoint_de_qualidade_silencioso_quando_esta_tudo_bem(self, monkeypatch):
        import app.forecast.router_data_quality as rota
        from app.core.db.rejections import RejectionStats

        monkeypatch.setattr(
            rota,
            "rejection_stats",
            lambda **kwargs: RejectionStats(institution_id=None, total=0),
        )
        resposta = await rota.get_data_quality(user_id=USER_ID, hours=24, institution_id=None)

        assert resposta["total_rejeitadas"] == 0
        assert resposta["diagnostico"].startswith("OK")

    def test_lote_saudavel_nao_gera_alerta(self, monkeypatch):
        import app.core.db.rejections as dlq

        batch = TransactionBatchResult.from_raw_batch(
            raw_data=[_tx_pluggy(f"ok_alerta_{i}", dias_atras=i + 1) for i in range(10)],
            institution_id="nubank",
            item_id=ITEM_ID,
            fetched_at=AGORA,
        )
        assert dlq.alert_on_batch(batch, "nubank", USER_ID) is None

    def test_sync_reporta_rejeicoes_e_alertas(self, sync_com_pluggy_fake, monkeypatch):
        """O relatório do sync passa a carregar o que foi descartado."""
        import app.pluggy_sync.runner as runner_sync

        gravadas: list = []
        monkeypatch.setattr(
            runner_sync,
            "save_rejected_transactions",
            lambda **kwargs: gravadas.append(kwargs) or kwargs["batch_result"].total_rejected,
        )

        db = _FakeSession()
        relatorio = sync_com_pluggy_fake.sync_item_transactions(
            db=db, user_id=USER_ID, item_id=ITEM_ID
        )

        assert relatorio["rejected"] == 1, "só 'rota_sem_data' é irrecuperável"
        assert relatorio["dlq_saved"] == 1, "e ela foi para a DLQ"
        assert gravadas and gravadas[0]["institution_id"] == "nubank"

    @pytest.mark.parametrize(
        "nome,esperado",
        [
            ("Nubank", "nubank"),
            ("Itaú Unibanco", "itau"),
            ("Banco Inter ", "inter"),
            ("Bradesco", "bradesco"),
            ("Mercado Pago", "mercadopago"),
            ("Pluggy Bank", "pluggy_sandbox"),
            ("Cooperativa de Crédito Qualquer", "unknown"),
        ],
    )
    def test_resolucao_de_instituicao_por_nome(self, nome, esperado):
        from app.forecast.etl.bank_strategy.institutions import resolve_institution_id

        assert resolve_institution_id(nome) == esperado

    def test_conta_que_falha_nao_contamina_as_outras(self, sync_com_pluggy_fake, monkeypatch):
        """Erro em uma conta é isolado no relatório; as demais seguem salvando."""

        original = _FakePluggyClient.get_transactions

        def get_transactions_com_falha(self, account_id):
            if account_id == ACC_CARTAO:
                raise RuntimeError("Pluggy 500 na conta de cartão")
            return original(self, account_id)

        monkeypatch.setattr(_FakePluggyClient, "get_transactions", get_transactions_com_falha)

        db = _FakeSession()
        relatorio = sync_com_pluggy_fake.sync_item_transactions(
            db=db, user_id=USER_ID, item_id=ITEM_ID
        )

        assert len(relatorio["errors"]) == 1
        assert ACC_CARTAO in relatorio["errors"][0]
        assert relatorio["saved"] == 2, "a conta corrente continuou sendo processada"

