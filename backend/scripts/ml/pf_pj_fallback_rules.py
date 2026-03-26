"""
pf_pj_fallback_rules.py - Regras de Fallback para Classificação PF/PJ

Objetivo: Implementar sistema de regras determinísticas como fallback quando
o modelo de ML não tem confiança alta ou para validação.

Regras baseadas na análise estatística dos dados mock:
- Keywords empresariais → PJ
- Categorias exclusivas PJ → PJ
- Valores muito altos → PJ
- Padrões temporais + valores baixos → PF
"""

import re
import sys
import os

# Adicionar o diretório backend ao path para imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Keywords discriminatórias
PJ_KEYWORDS = [
    'empresa', 'ltda', 'fornecedor', 'aluguel', 'escritorio', 'imobiliaria',
    'viagem negocios', 'software', 'corporativo', 'marketing', 'cemig empresas',
    'consultoria', 'contador', 'salario', 'papelaria', 'licenca'
]

PF_KEYWORDS = [
    'uber', 'netflix', 'carrefour', 'academia', 'restaurante', 'drogaria',
    'shopping', 'cinepolis', 'padaria', 'spotify', 'lavanderia', 'starbucks',
    'pet shop', 'livraria', 'pix recebido', 'amigo'
]

# Categorias exclusivas PJ
PJ_EXCLUSIVE_CATEGORIES = [
    'SALARY', 'OFFICE_SUPPLIES', 'RENT', 'SOFTWARE', 'CONSULTING',
    'MARKETING', 'UTILITIES', 'TELEPHONE'
]

# Categorias exclusivas PF
PF_EXCLUSIVE_CATEGORIES = [
    'ENTERTAINMENT', 'FOOD', 'HEALTH', 'PETS', 'EDUCATION', 'SHOPPING'
]

class PFPJFallbackClassifier:
    """
    Classificador rule-based para fallback do modelo ML.
    Retorna 'PF', 'PJ' ou 'UNCERTAIN' se não conseguir decidir.
    """

    def __init__(self):
        self.pj_keywords_pattern = re.compile(r'\b(?:' + '|'.join(PJ_KEYWORDS) + r')\b', re.IGNORECASE)
        self.pf_keywords_pattern = re.compile(r'\b(?:' + '|'.join(PF_KEYWORDS) + r')\b', re.IGNORECASE)

    def classify(self, transaction_data):
        """
        Classifica transação usando regras determinísticas.

        Args:
            transaction_data (dict): Dados da transação com keys:
                - description (str)
                - category (str)
                - amount (float)
                - hour_of_day (int)
                - merchant (str, optional)

        Returns:
            str: 'PF', 'PJ', ou 'UNCERTAIN'
        """
        description = transaction_data.get('description', '').lower()
        category = transaction_data.get('category', '')
        amount = abs(transaction_data.get('amount', 0))
        hour_of_day = transaction_data.get('hour_of_day', 12)
        merchant = transaction_data.get('merchant', '').lower() if transaction_data.get('merchant') else ''

        # Regra 1: Categorias exclusivas PJ → PJ
        if category in PJ_EXCLUSIVE_CATEGORIES:
            return 'PJ'

        # Regra 2: Categorias exclusivas PF → PF
        if category in PF_EXCLUSIVE_CATEGORIES:
            return 'PF'

        # Regra 3: Keywords PJ na descrição → PJ
        if self.pj_keywords_pattern.search(description):
            return 'PJ'

        # Regra 4: Keywords PF na descrição → PF
        if self.pf_keywords_pattern.search(description):
            return 'PF'

        # Regra 5: Valores muito altos (> R$ 2000) → PJ
        if amount > 2000:
            return 'PJ'

        # Regra 6: Valores muito baixos (< R$ 20) + horário não-comercial → PF
        if amount < 20 and (hour_of_day < 8 or hour_of_day > 18):
            return 'PF'

        # Regra 7: Merchant conhecido PJ → PJ
        pj_merchants = ['microsoft', 'fornecedor', 'imobiliaria', 'cemig', 'contador']
        if any(pj_m in merchant for pj_m in pj_merchants):
            return 'PJ'

        # Regra 8: Merchant conhecido PF → PF
        pf_merchants = ['uber', 'netflix', 'starbucks', 'cinepolis', 'spotify']
        if any(pf_m in merchant for pf_m in pf_merchants):
            return 'PF'

        # Regra 9: Horário comercial + valor médio → PJ
        if 9 <= hour_of_day <= 17 and 100 <= amount <= 1000:
            return 'PJ'

        # Regra 10: Fim de semana + valor baixo → PF
        weekend_hours = [6, 7, 13, 14, 18, 19, 20, 21, 22]
        if hour_of_day in weekend_hours and amount < 200:
            return 'PF'

        # Se nenhuma regra aplicou com confiança, retorna UNCERTAIN
        return 'UNCERTAIN'

    def get_confidence_score(self, transaction_data):
        """
        Retorna score de confiança da classificação (0-1).
        1.0 = Regra muito forte, 0.5 = Regra média, 0.0 = UNCERTAIN
        """
        classification = self.classify(transaction_data)

        if classification == 'UNCERTAIN':
            return 0.0

        description = transaction_data.get('description', '').lower()
        category = transaction_data.get('category', '')
        amount = abs(transaction_data.get('amount', 0))

        # Alta confiança: Categorias exclusivas
        if category in PJ_EXCLUSIVE_CATEGORIES or category in PF_EXCLUSIVE_CATEGORIES:
            return 1.0

        # Alta confiança: Keywords múltiplos
        pj_matches = len(self.pj_keywords_pattern.findall(description))
        pf_matches = len(self.pf_keywords_pattern.findall(description))
        if pj_matches >= 2 or pf_matches >= 2:
            return 0.9

        # Média confiança: Keywords únicos
        if pj_matches == 1 or pf_matches == 1:
            return 0.7

        # Média confiança: Valores extremos
        if amount > 2000 or amount < 20:
            return 0.6

        # Baixa confiança: Outras regras
        return 0.5

def test_fallback_rules():
    """Testa regras de fallback com dados mock"""
    classifier = PFPJFallbackClassifier()

    # Test cases baseados nos dados mock
    test_cases = [
        # PJ cases
        {'description': 'SALARIO - EMPRESA XYZ LTDA', 'category': 'SALARY', 'amount': 8500, 'hour_of_day': 6, 'expected': 'PJ'},
        {'description': 'PAPELARIA EMPRESARIAL LTDA', 'category': 'OFFICE_SUPPLIES', 'amount': -456.78, 'hour_of_day': 10, 'expected': 'PJ'},
        {'description': 'ALUGUEL ESCRITORIO', 'category': 'RENT', 'amount': -2500, 'hour_of_day': 8, 'expected': 'PJ'},
        {'description': 'FORNECEDOR ABC MATERIAL', 'category': 'SUPPLIES', 'amount': -1234.56, 'hour_of_day': 14, 'expected': 'PJ'},

        # PF cases
        {'description': 'UBER *TRIP - SAO PAULO', 'category': 'TRANSPORT', 'amount': -45.50, 'hour_of_day': 18, 'expected': 'PF'},
        {'description': 'NETFLIX.COM', 'category': 'ENTERTAINMENT', 'amount': -49.90, 'hour_of_day': 10, 'expected': 'PF'},
        {'description': 'CARREFOUR SAO PAULO', 'category': 'GROCERIES', 'amount': -285.40, 'hour_of_day': 14, 'expected': 'PF'},
        {'description': 'RESTAURANTE DO ZE', 'category': 'FOOD', 'amount': -67.80, 'hour_of_day': 12, 'expected': 'PF'},
    ]

    print("🧪 TESTANDO REGRAS DE FALLBACK")
    print("=" * 40)

    correct = 0
    total = len(test_cases)

    for i, case in enumerate(test_cases, 1):
        result = classifier.classify(case)
        confidence = classifier.get_confidence_score(case)
        expected = case['expected']

        status = "✅" if result == expected else "❌"
        print(f"{status} Test {i}: {result} (esperado: {expected}) | Confiança: {confidence:.1f}")
        print(f"   Descrição: {case['description'][:50]}...")

        if result == expected:
            correct += 1

    accuracy = correct / total
    print(f"\nAccuracy das regras: {accuracy:.1%}")
    return accuracy

if __name__ == "__main__":
    print("🎯 REGRAS DE FALLBACK PF/PJ")
    print("=" * 35)

    # Testa regras
    accuracy = test_fallback_rules()

    print("\n📋 Regras implementadas:")
    print("   ✅ Categorias exclusivas PJ → PJ (SALARY, OFFICE_SUPPLIES, etc.)")
    print("   ✅ Keywords PJ → PJ (empresa, ltda, fornecedor, etc.)")
    print("   ✅ Valores > R$ 2000 → PJ")
    print("   ✅ Valores < R$ 20 + horário não-comercial → PF")
    print("   ✅ Merchants conhecidos → PF/PJ")
    print("   ✅ Padrões temporais + valores → PF/PJ")

    if accuracy >= 0.9:
        print("\n✅ Regras de fallback validadas com sucesso!")
        print("🚀 Pronto para integração com modelo ML")
    else:
        print("\n⚠️  Regras precisam ajuste - accuracy baixa")

    if accuracy >= 0.9:
        print("\n✅ Regras de fallback validadas com sucesso!")
        print("🚀 Pronto para integração com modelo ML")
    else:
        print("\n⚠️  Regras precisam ajuste - accuracy baixa")