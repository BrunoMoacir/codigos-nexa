"""
app/etl/pf_pj_classifier.py - Classificador PF/PJ para o pipeline ETL

Integra modelo ML (Random Forest) com regras de fallback para classificar
transações como Pessoais (PF) ou Empresariais (PJ).

Uso no pipeline:
- Carrega modelo treinado + encoders/scalers
- Extrai features das transações
- Prediz com ML, usa fallback se confiança baixa
- Adiciona coluna 'pf_pj_label' ao DataFrame
"""

import polars as pl
import logging
import re
from datetime import datetime
from typing import Dict, Any

from app.divider.subcategory_classifier import get_pj_subcategory_classifier

logger = logging.getLogger(__name__)

# ── Regras que dependem da DIREÇÃO do dinheiro ──────────────────────────────
#
# As regras antigas olhavam só a palavra: "salario" e "aluguel" eram PJ, e
# qualquer valor acima de R$ 2.000 também. O salário CLT da Ana ("credito
# salario folha mensal acme ltda") virava receita de empresa — o relatório
# fiscal cobrava DAS de R$ 10 mil de quem não é MEI e o IncomeProfiler (que
# lê só PF) zerava a renda dela. Ao mesmo tempo, os recebimentos da
# maquininha do Bruno, que É MEI, ficavam UNCERTAIN e o fiscal dele dizia
# "sem receita".

# Crédito que é renda de pessoa física (CLT, benefício, restituição)
RENDA_PF_RE = (
    r"\b(salario|folha|13o?\s*salario|decimo\s*terceiro|ferias|plr|"
    r"adiantamento\s*salarial|restituicao|inss|aposentadoria|pensao|fgts)\b"
)
# Crédito que é receita de negócio: liquidação de maquininha/adquirente,
# cliente PJ, nota fiscal, prestação de serviço
RECEITA_PJ_RE = (
    r"(maquininha|\*\s*vendas?\b|\bstone\b|getnet|pagseguro|pagbank|cielo|"
    r"\brede\s*(card)?\b|sumup|mercado\s*pago\s*vendas?|cliente\s*pj|"
    r"nota\s*fiscal|\bnfs?-?e\b|prestacao\s*(de\s*)?servico)"
)
# Débito que é despesa de negócio (folha paga, aluguel comercial, imposto do MEI)
DESPESA_PJ_RE = (
    r"(pagamento\s*(de\s*)?(salario|folha)|folha\s*de\s*pagamento|"
    r"aluguel\s*(sala|escritorio|comercial|loja|galpao|ponto)|"
    r"\bdas\s*(mei|simples)\b|simples\s*nacional)"
)


class PFPJClassifier:
    """
    Classificador PF/PJ baseado em regras vetorizadas (Polars expressions).

    Classifica transações como Pessoais (PF), Empresariais (PJ) ou UNCERTAIN
    usando um conjunto de regras determinísticas aplicadas em batch via Polars.
    """

    def __init__(self):
        # Optional ML model (may be None in test/dev environments)
        self.model = None
        self.fallback_classifier = PFPJFallbackClassifier()

    def _classify_single(self, transaction: dict) -> str:
        """Classifica uma única transação (usado em testes de performance)."""
        # If an ML model is available, use it (not implemented here).
        # Fallback to rule-based classifier for deterministic behavior.
        return self.fallback_classifier.classify(transaction)

    def classify_batch(self, transactions_df: pl.DataFrame) -> pl.DataFrame:
        """
        Classifica batch de transações PF/PJ e adiciona subcategoria para PJ.

        Usa expressões Polars nativas (vetorizado) para a classificação principal,
        evitando loop Python por linha. O ML é aplicado antes se o modelo estiver
        disponível e a confiança for alta.

        Args:
            transactions_df: DataFrame com transações (depois do ETL Ingestor)

        Returns:
            DataFrame com colunas 'pf_pj_label' e 'pj_subcategory' adicionadas.
            'pj_subcategory' é None para transações PF/UNCERTAIN.
        """
        logger.info("Classificando %s transacoes PF/PJ...", len(transactions_df))

        fb = self.fallback_classifier

        # ── Classificação vetorizada via Polars expressions ────────────────
        # Normaliza colunas de texto para lowercase uma única vez
        desc_col = pl.col("description").fill_null("").str.to_lowercase()
        merch_col = (
            pl.col("merchant").fill_null("").str.to_lowercase()
            if "merchant" in transactions_df.columns
            else pl.lit("")
        )

        # Padrões regex: une keywords com "|" para uma única passagem por linha
        pj_kw  = "|".join(re.escape(k) for k in fb.pj_keywords)
        pf_kw  = "|".join(re.escape(k) for k in fb.pf_keywords)
        pj_mch = "|".join(re.escape(m) for m in fb.pj_merchants)
        pf_mch = "|".join(re.escape(m) for m in fb.pf_merchants)
        credito = pl.col("amount") > 0
        categoria = pl.col("category").fill_null("")

        # Mesma ordem de PFPJFallbackClassifier.classify (testada lá).
        label_expr = (
            pl.when(credito & desc_col.str.contains(RECEITA_PJ_RE))
            .then(pl.lit("PJ"))
            .when(credito & desc_col.str.contains(RENDA_PF_RE))
            .then(pl.lit("PF"))
            .when(~credito & desc_col.str.contains(DESPESA_PJ_RE))
            .then(pl.lit("PJ"))
            .when(categoria.is_in(fb.pj_categories) | (~credito & (categoria == "SALARY")))
            .then(pl.lit("PJ"))
            .when(desc_col.str.contains(pj_kw))
            .then(pl.lit("PJ"))
            .when(desc_col.str.contains(pf_kw))
            .then(pl.lit("PF"))
            .when(merch_col.str.contains(pj_mch))
            .then(pl.lit("PJ"))
            .when(merch_col.str.contains(pf_mch))
            .then(pl.lit("PF"))
            .otherwise(pl.lit("UNCERTAIN"))
        )

        # Confiança da REGRA que decidiu, na mesma ordem do label_expr.
        # Escala do contrato TransactionOut.context_confidence:
        #   0.70-0.89 = regra determinística forte, 0.50-0.69 = heurística
        #   ambígua, < 0.50 = UNCERTAIN. Este campo alimenta o badge da UI e
        #   o filtro de confiança do agente — ficava sempre nulo porque
        #   nenhuma via o produzia.
        confidence_expr = (
            pl.when(credito & desc_col.str.contains(RECEITA_PJ_RE))
            .then(pl.lit(0.85))   # liquidação de adquirente / nota fiscal
            .when(credito & desc_col.str.contains(RENDA_PF_RE))
            .then(pl.lit(0.85))   # salário / benefício
            .when(~credito & desc_col.str.contains(DESPESA_PJ_RE))
            .then(pl.lit(0.80))
            .when(categoria.is_in(fb.pj_categories) | (~credito & (categoria == "SALARY")))
            .then(pl.lit(0.85))   # categoria estruturada do banco
            .when(desc_col.str.contains(pj_kw))
            .then(pl.lit(0.80))   # keyword inequívoca na descrição
            .when(desc_col.str.contains(pf_kw))
            .then(pl.lit(0.80))
            .when(merch_col.str.contains(pj_mch))
            .then(pl.lit(0.70))   # merchant conhecido, lista curta
            .when(merch_col.str.contains(pf_mch))
            .then(pl.lit(0.70))
            .otherwise(pl.lit(0.40))  # UNCERTAIN
            .cast(pl.Float64)
        )

        classifications = (
            transactions_df
            .with_columns(label_expr.alias("pf_pj_label"))
            ["pf_pj_label"]
            .to_list()
        )

        # Subcategoria PJ: map_elements apenas nas linhas rotuladas como PJ
        pj_classifier = get_pj_subcategory_classifier()
        rows_for_subcat = list(transactions_df.iter_rows(named=True))
        subcategories = [
            pj_classifier.classify(row) if label == "PJ" else None
            for row, label in zip(rows_for_subcat, classifications)
        ]

        result_df = transactions_df.with_columns([
            pl.Series("pf_pj_label", classifications),
            pl.Series("pj_subcategory", subcategories),
            confidence_expr.alias("pf_pj_confidence"),
        ])

        pf_count = classifications.count("PF")
        pj_count = classifications.count("PJ")
        uncertain_count = classifications.count("UNCERTAIN")

        logger.info("Classificacao completa: PF=%s, PJ=%s, UNCERTAIN=%s", pf_count, pj_count, uncertain_count)

        return result_df

class PFPJFallbackClassifier:
    """
    Classificador rule-based (mesmo código de pf_pj_fallback_rules.py)
    """

    def __init__(self):
        # Sem 'salario' (crédito de salário é PF; débito é coberto por
        # DESPESA_PJ_RE), 'aluguel' e 'imobiliaria' (aluguel residencial é PF;
        # o comercial está em DESPESA_PJ_RE).
        self.pj_keywords = [
            'empresa', 'ltda', 'fornecedor', 'escritorio',
            'viagem negocios', 'software', 'corporativo', 'marketing', 'cemig empresas',
            'consultoria', 'contador', 'papelaria'
        ]
        self.pf_keywords = [
            'uber', 'netflix', 'carrefour', 'academia', 'restaurante', 'drogaria',
            'shopping', 'cinepolis', 'padaria', 'spotify', 'lavanderia', 'starbucks',
            'pet shop', 'livraria', 'pix recebido', 'amigo',
            # moradia da família — o aluguel comercial está em DESPESA_PJ_RE
            'aluguel apartamento', 'aluguel casa', 'aluguel kitnet', 'aluguel residencial',
            'condominio',
        ]
        # Só categorias de negócio. SALARY conta como PJ apenas no débito
        # (empresa pagando folha); RENT, UTILITIES e TELEPHONE são contas de
        # casa na maioria dos extratos e iam todas para a empresa.
        self.pj_categories = [
            'OFFICE_SUPPLIES', 'SOFTWARE', 'CONSULTING', 'MARKETING',
        ]
        self.pj_merchants = ['microsoft', 'fornecedor', 'cemig', 'contador']
        self.pf_merchants = ['uber', 'netflix', 'starbucks', 'cinepolis', 'spotify']

    def classify(self, transaction: Dict[str, Any]) -> str:
        """Classifica usando regras determinísticas"""
        description = transaction.get('description', '') or ''
        category = transaction.get('category', '') or ''
        amount = transaction.get('amount', 0) or 0
        transaction_date = transaction.get('transaction_date')
        hour_of_day = 12  # default
        if isinstance(transaction_date, datetime):
            hour_of_day = transaction_date.hour
        elif isinstance(transaction_date, str):
            try:
                parsed_date = datetime.fromisoformat(transaction_date.replace('Z', '+00:00'))
                hour_of_day = parsed_date.hour
            except:
                pass
        merchant = transaction.get('merchant', '') or ''

        # Converte para tipos apropriados
        description = description.lower()
        merchant = merchant.lower()
        credito = amount > 0
        amount = abs(amount)

        # Direção primeiro: o mesmo texto é renda PF num crédito e despesa PJ
        # num débito ("salario").
        if credito and re.search(RECEITA_PJ_RE, description):
            return 'PJ'
        if credito and re.search(RENDA_PF_RE, description):
            return 'PF'
        if not credito and re.search(DESPESA_PJ_RE, description):
            return 'PJ'

        if category in self.pj_categories or (not credito and category == 'SALARY'):
            return 'PJ'

        if any(kw in description for kw in self.pj_keywords):
            return 'PJ'

        # Sem a regra "valor > R$ 2.000 → PJ": smartphone, eletrodoméstico e
        # aluguel de casa viravam despesa da empresa. Valor alto sem outro
        # sinal fica UNCERTAIN.

        if any(kw in description for kw in self.pf_keywords):
            return 'PF'

        if amount < 20 and (hour_of_day < 8 or hour_of_day > 18):
            return 'PF'

        # Merchants conhecidos
        if any(m in merchant for m in self.pj_merchants):
            return 'PJ'
        if any(m in merchant for m in self.pf_merchants):
            return 'PF'

        return 'UNCERTAIN'