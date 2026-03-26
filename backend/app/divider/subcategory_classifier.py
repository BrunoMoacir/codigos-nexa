"""
app/etl/pj_subcategory_classifier.py - Subcategorizacao granular para transacoes PJ

Dado que uma transacao ja foi classificada como PJ pelo PFPJClassifier,
este modulo determina qual subcategoria PJ ela pertence.

Subcategorias:
  receita_servicos     - Notas fiscais de servico, pagamentos de clientes
  receita_produtos     - Vendas de produtos fisicos/digitais
  despesa_software     - SaaS, licencas, ferramentas digitais
  despesa_marketing    - Anuncios, design, agencias
  despesa_transporte   - Combustivel, Uber empresarial, pedagios
  despesa_equipamento  - Hardware, maquinas, moveis de escritorio
  despesa_pessoal_pj   - Pro-labore, salario de funcionarios, RH
  despesa_imposto      - DAS, ISS, INSS, IRPJ, CSLL
  despesa_bancaria     - Tarifas bancarias, juros, IOF
  despesa_outros_pj    - PJ nao categorizado
"""

import re
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

PJ_SUBCATEGORIES = [
    "receita_servicos",
    "receita_produtos",
    "despesa_software",
    "despesa_marketing",
    "despesa_transporte",
    "despesa_equipamento",
    "despesa_pessoal_pj",
    "despesa_imposto",
    "despesa_bancaria",
    "despesa_outros_pj",
]

# Mapeamento de categoria ETL -> subcategoria PJ
_CATEGORY_MAP: Dict[str, str] = {
    "SALARY": "despesa_pessoal_pj",
    "TAX": "despesa_imposto",
    "BANK_FEE": "despesa_bancaria",
    "SOFTWARE": "despesa_software",
    "MARKETING": "despesa_marketing",
    "OFFICE_SUPPLIES": "despesa_equipamento",
    "CONSULTING": "receita_servicos",
    "RENT": "despesa_equipamento",  # aluguel de escritorio
}

# Keywords por subcategoria (aplicadas na descricao + merchant)
_KEYWORD_RULES: list[tuple[str, list[str]]] = [
    # Receitas
    ("receita_servicos", [
        "nf servico", "nota fiscal servico", "pagamento servico", "honorario",
        "consultoria recebida", "freelance", "cliente pag", "recebimento pj",
        "transferencia recebida empresa", "pix recebido empresa",
    ]),
    ("receita_produtos", [
        "venda produto", "mercadoria", "pedido shopify", "marketplace",
        "mercado livre", "shopee", "amazon seller", "loja virtual",
    ]),
    # Despesas operacionais
    ("despesa_software", [
        "aws", "google cloud", "azure", "github", "notion", "slack", "figma",
        "adobe", "microsoft 365", "office 365", "salesforce", "hubspot",
        "trello", "asana", "jira", "cloudflare", "digitalocean", "heroku",
        "twilio", "sendgrid", "openai", "anthropic", "datadog", "sentry",
        "zoom", "dropbox", "linear", "vercel", "netlify",
    ]),
    ("despesa_marketing", [
        "google ads", "meta ads", "facebook ads", "instagram ads", "tiktok ads",
        "linkedin ads", "agencia marketing", "agencia publicidade", "design",
        "freelancer design", "criacao conteudo", "copywriter", "seo",
        "rd station", "mailchimp", "hubspot marketing",
    ]),
    ("despesa_transporte", [
        "combustivel", "gasolina", "posto", "shell", "ipiranga", "br distribuidora",
        "uber empresarial", "99 empresas", "cabify business", "pedagio",
        "estacionamento", "parking", "voo negocios", "passagem aerea empresa",
        "hotel viagem trabalho", "hotel negocios",
    ]),
    ("despesa_equipamento", [
        "amazon", "kabum", "dell", "lenovo", "hp", "apple store empresas",
        "magazine luiza empresa", "fast shop", "notebook", "computador",
        "servidor", "impressora", "monitor", "teclado", "cadeira escritorio",
        "mesa escritorio", "mobilia", "aluguel sala", "coworking",
    ]),
    ("despesa_pessoal_pj", [
        "pro-labore", "prolabore", "folha pagamento", "folha salarial",
        "salario funcionario", "rescisao", "ferias", "13 salario",
        "vale transporte empresa", "vale refeicao empresa", "beneficio funcionario",
        "guia inss patronal", "inss empresa",
    ]),
    ("despesa_imposto", [
        r"\bdas\b", r"\boss\b", r"\biss\b", r"\bpis\b", r"\bipi\b",
        "das-", "simples nacional", "iss-", "irpj", "csll",
        "cofins", "pis-", "inss autonomo", "decore", "darf",
        "receita federal", "prefeitura municipal imposto", "icms",
    ]),
    ("despesa_bancaria", [
        "tarifa bancaria", "tarifa manutencao", "ted empresarial fee",
        "juros conta pj", "iof ", "spread bancario", "anuidade cartao empresa",
        "cpmf", "taxa administracao", "taxa boleto",
    ]),
]


class PJSubcategoryClassifier:
    """
    Classifica subcategoria de transacoes PJ.

    Uso:
        classifier = PJSubcategoryClassifier()
        subcategory = classifier.classify(transaction_dict)
        # -> "despesa_software", "receita_servicos", etc.
    """

    def classify(self, transaction: Dict[str, Any]) -> str:
        """
        Retorna a subcategoria PJ da transacao.

        Args:
            transaction: dict com campos 'description', 'merchant', 'category',
                         'amount' (negativo = debito, positivo = credito)

        Returns:
            str: uma das PJ_SUBCATEGORIES
        """
        description = (transaction.get("description") or "").lower()
        merchant = (transaction.get("merchant") or "").lower()
        category = (transaction.get("category") or "").upper()
        amount = transaction.get("amount", 0) or 0

        text = f"{description} {merchant}"

        # 1. Mapeamento direto por categoria ETL
        if category in _CATEGORY_MAP:
            return _CATEGORY_MAP[category]

        # 2. Receita por sinal positivo + keywords fortes (apenas keywords explícitas aqui)
        if amount > 0:
            for kw in ["cliente", "pagamento recebido", "nf ", "nota fiscal", "recebimento"]:
                if kw in text:
                    return "receita_servicos"

        # 3. Keywords por subcategoria (inclui receita_produtos antes de qualquer heurística)
        for subcategory, keywords in _KEYWORD_RULES:
            for kw in keywords:
                if kw.startswith(r"\b"):
                    if re.search(kw, text):
                        return subcategory
                elif kw in text:
                    return subcategory

        # 4. Heuristicas por valor — so chegam aqui transacoes sem nenhuma keyword
        amount_abs = abs(amount)
        if amount > 0 and amount_abs > 500:
            # Credito alto sem keyword identificada: provavelmente receita de servico
            return "receita_servicos"
        if amount < 0 and amount_abs > 5000:
            # Debito muito alto sem keyword: provavelmente pessoal/fornecedor
            return "despesa_pessoal_pj"

        return "despesa_outros_pj"

    def classify_batch(self, transactions: list[Dict[str, Any]]) -> list[str]:
        """Classifica lista de transacoes, retorna lista de subcategorias na mesma ordem."""
        return [self.classify(tx) for tx in transactions]


# Singleton para reuso sem re-instanciar
_classifier_instance: PJSubcategoryClassifier | None = None


def get_pj_subcategory_classifier() -> PJSubcategoryClassifier:
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = PJSubcategoryClassifier()
    return _classifier_instance
