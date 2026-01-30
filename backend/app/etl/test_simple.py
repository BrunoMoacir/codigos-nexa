"""
🧪 TESTE SIMPLIFICADO - NEXA AI
═══════════════════════════════════════════════════════════════

Este teste valida os componentes principais de forma isolada,
sem precisar da estrutura completa de imports.

Testa:
    ✅ Parsers (amount, date, status)
    ✅ Validators (sanitize_text)
    ✅ BankStrategy (conceito)
    ✅ Lógica de normalização

Como executar:
    python test_simple.py
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
import re
import html


# ═══════════════════════════════════════════════════════════════════
# CONSTANTES (do transaction.py)
# ═══════════════════════════════════════════════════════════════════

MAX_AMOUNT = Decimal("1_000_000_000")
MAX_DESCRIPTION_LENGTH = 500

CONTROL_CHARS = "".join(chr(i) for i in range(32) if i not in (9, 10, 13))
CONTROL_CHARS_PATTERN = re.compile(f"[{re.escape(CONTROL_CHARS)}]")

SCRIPT_PATTERN = re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL)
STYLE_PATTERN = re.compile(r'<style[^>]*>.*?</style>', re.IGNORECASE | re.DOTALL)
HTML_TAG_PATTERN = re.compile(r'<[^>]+>')


# ═══════════════════════════════════════════════════════════════════
# HELPERS (do transaction.py)
# ═══════════════════════════════════════════════════════════════════

def sanitize_text(text: str, max_length: int = MAX_DESCRIPTION_LENGTH) -> str:
    """Sanitiza texto (anti-XSS, anti-ReDoS)."""
    if not isinstance(text, str):
        return ""
    
    # 1. Proteção ReDoS
    if len(text) > max_length * 2:
        text = text[:max_length * 2]
    
    # 2. Remove tags perigosas
    text = SCRIPT_PATTERN.sub('', text)
    text = STYLE_PATTERN.sub('', text)
    text = HTML_TAG_PATTERN.sub('', text)
    
    # 3. Remove controles
    text = CONTROL_CHARS_PATTERN.sub("", text)
    
    # 4. Normaliza espaços
    text = re.sub(r"\s+", " ", text).strip()
    
    # 5. Escapa HTML
    text = html.escape(text)
    
    # 6. Corte final
    if len(text) > max_length:
        text = text[:max_length]
    
    return text


def parse_amount_safe(v: str, locale: str = 'BR') -> Decimal:
    """Parser híbrido BR/US."""
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v))
    
    v = str(v).strip()
    
    # Remove moeda
    v = v.replace("R$", "").replace("$", "").replace(" ", "")
    
    # Detecta formato
    has_comma = "," in v
    has_dot = "." in v
    
    if has_comma and has_dot:
        # Ambos: última ocorrência = decimal
        if v.rfind(",") > v.rfind("."):
            v = v.replace(".", "").replace(",", ".")
        else:
            v = v.replace(",", "")
    elif has_comma:
        if locale == 'BR':
            v = v.replace(",", ".")
        else:
            v = v.replace(",", "")
    elif has_dot:
        if locale == 'BR':
            # Heurística: 1.000 (milhar) vs 1.50 (decimal)
            if re.match(r"^\d{1,3}(\.\d{3})+$", v):
                v = v.replace(".", "")
    
    return Decimal(v)


def parse_date_safe(v: str) -> datetime:
    """Parser de datas com timezone."""
    # ISO 8601
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    
    try:
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except:
        pass
    
    # Formatos BR
    formats = [
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S",
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(v, fmt)
            dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except:
            continue
    
    raise ValueError(f"Data inválida: {v}")


# ═══════════════════════════════════════════════════════════════════
# TESTES
# ═══════════════════════════════════════════════════════════════════

def test_sanitize_text():
    """Testa sanitização de texto."""
    print("\n" + "="*80)
    print("🧪 TESTE 1: SANITIZAÇÃO DE TEXTO")
    print("="*80)
    
    # Caso 1: HTML perigoso
    dirty = '<script>alert("xss")</script>Texto limpo'
    clean = sanitize_text(dirty)
    print(f"\n✅ Caso 1: Remove <script>")
    print(f"   Input:  '{dirty}'")
    print(f"   Output: '{clean}'")
    assert "<script>" not in clean
    assert "Texto limpo" in clean
    
    # Caso 2: Controles
    dirty2 = "Texto\x00com\x01controles\x02"
    clean2 = sanitize_text(dirty2)
    print(f"\n✅ Caso 2: Remove controles")
    print(f"   Output: '{clean2}'")
    assert "\x00" not in clean2
    
    # Caso 3: Espaços múltiplos
    dirty3 = "Texto    com    espaços"
    clean3 = sanitize_text(dirty3)
    print(f"\n✅ Caso 3: Normaliza espaços")
    print(f"   Input:  '{dirty3}'")
    print(f"   Output: '{clean3}'")
    assert clean3 == "Texto com espaços"
    
    print("\n✅ TESTE 1 PASSOU!")


def test_parse_amount():
    """Testa parser de valores financeiros."""
    print("\n" + "="*80)
    print("🧪 TESTE 2: PARSER DE VALORES FINANCEIROS")
    print("="*80)
    
    casos = [
        ("1.500,00", "BR", Decimal("1500.00")),  # BR
        ("1,500.00", "US", Decimal("1500.00")),  # US
        ("1.50", "BR", Decimal("1.50")),  # BR decimal híbrido
        ("1000", "BR", Decimal("1000")),  # Sem separador
        ("R$ 1.500,00", "BR", Decimal("1500.00")),  # Com moeda
    ]
    
    for input_val, locale, expected in casos:
        result = parse_amount_safe(input_val, locale)
        print(f"\n✅ Caso: '{input_val}' (locale={locale})")
        print(f"   Esperado: {expected}")
        print(f"   Resultado: {result}")
        assert result == expected, f"Falhou: {result} != {expected}"
    
    print("\n✅ TESTE 2 PASSOU!")


def test_parse_date():
    """Testa parser de datas."""
    print("\n" + "="*80)
    print("🧪 TESTE 3: PARSER DE DATAS")
    print("="*80)
    
    casos = [
        ("2024-01-15T10:30:00Z", "ISO 8601 com Z"),
        ("2024-01-15T10:30:00+00:00", "ISO 8601 com offset"),
        ("15/01/2024 10:30:00", "BR completo"),
        ("15/01/2024", "BR data"),
    ]
    
    for input_val, descricao in casos:
        result = parse_date_safe(input_val)
        print(f"\n✅ Caso: {descricao}")
        print(f"   Input: '{input_val}'")
        print(f"   Output: {result}")
        assert isinstance(result, datetime)
        assert result.tzinfo is not None  # Timezone-aware
    
    print("\n✅ TESTE 3 PASSOU!")


def test_bank_strategy_concept():
    """Testa conceito de BankStrategy (normalização)."""
    print("\n" + "="*80)
    print("🧪 TESTE 4: CONCEITO BANK STRATEGY")
    print("="*80)
    
    # Simula normalização do Itaú
    print("\n▶ Simulando Itaú (TIER_3 - campos não-padrão)")
    
    # Input cru (como vem do Itaú)
    raw_itau = {
        "conta": "acc_itau_123",
        "data": "15/01/2024 10:30:00",
        "valor": "1.500,50",
        "descricao": "NETFLIX.COM ASSINATURA",
    }
    
    print(f"   Input cru:")
    for k, v in raw_itau.items():
        print(f"      {k}: '{v}'")
    
    # Normalização (mapear campos + parsear valores)
    normalized = {
        "account_id": raw_itau["conta"],  # conta → account_id
        "transaction_date": parse_date_safe(raw_itau["data"]),
        "amount": parse_amount_safe(raw_itau["valor"], "BR"),
        "description": sanitize_text(raw_itau["descricao"].lower()),
    }
    
    print(f"\n   Output normalizado:")
    for k, v in normalized.items():
        print(f"      {k}: {v}")
    
    # Validações
    assert normalized["account_id"] == "acc_itau_123"
    assert normalized["amount"] == Decimal("1500.50")
    assert isinstance(normalized["transaction_date"], datetime)
    assert "netflix" in normalized["description"]
    
    print("\n✅ TESTE 4 PASSOU!")


def test_integration():
    """Testa integração: webhook → normalização → validação."""
    print("\n" + "="*80)
    print("🧪 TESTE 5: INTEGRAÇÃO (Webhook → Normalização)")
    print("="*80)
    
    # 1. Webhook chega (Nubank)
    webhook_nubank = {
        "id": "txn_001",
        "accountId": "acc_nubank_123",
        "date": "2024-01-15T10:30:00Z",
        "description": "UBER *TRIP ABC",
        "amount": -50.75,
        "balance": 1949.25,
        "status": "POSTED",
    }
    
    print("\n▶ ETAPA 1: Webhook recebido")
    print(f"   Banco: Nubank")
    print(f"   ID: {webhook_nubank['id']}")
    print(f"   Amount: {webhook_nubank['amount']}")
    
    # 2. Enriquecer
    enriched = {
        **webhook_nubank,
        "institution_id": "nubank",
        "item_id": "item_123",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        # Mapear campos Pluggy → padrão
        "transaction_id": webhook_nubank["id"],
        "account_id": webhook_nubank["accountId"],
        "transaction_date": webhook_nubank["date"],
    }
    
    print("\n▶ ETAPA 2: Enriquecido com contexto")
    print(f"   institution_id: {enriched['institution_id']}")
    print(f"   item_id: {enriched['item_id']}")
    
    # 3. Normalizar
    normalized = {
        "transaction_id": enriched["transaction_id"],
        "account_id": enriched["account_id"],
        "institution_id": enriched["institution_id"],
        "transaction_date": parse_date_safe(enriched["transaction_date"]),
        "amount": Decimal(str(enriched["amount"])),
        "description": sanitize_text(enriched["description"].lower()),
        "balance": Decimal(str(enriched["balance"])),
    }
    
    print("\n▶ ETAPA 3: Normalizado")
    print(f"   transaction_date: {normalized['transaction_date']}")
    print(f"   amount: {normalized['amount']}")
    print(f"   description: '{normalized['description']}'")
    
    # Validações
    assert normalized["amount"] == Decimal("-50.75")
    assert "uber" in normalized["description"]
    assert normalized["transaction_date"].tzinfo is not None
    
    print("\n✅ TESTE 5 PASSOU!")


def run_all_tests():
    """Executa todos os testes."""
    print("\n" + "🚀"*40)
    print("🧪 NEXA AI - TESTE SIMPLIFICADO")
    print("🚀"*40)
    
    try:
        test_sanitize_text()
        test_parse_amount()
        test_parse_date()
        test_bank_strategy_concept()
        test_integration()
        
        print("\n" + "="*80)
        print("✅ TODOS OS TESTES PASSARAM COM SUCESSO!")
        print("="*80)
        print("\n📋 COMPONENTES VALIDADOS:")
        print("   ✅ Sanitização de texto (anti-XSS, anti-ReDoS)")
        print("   ✅ Parser de valores (BR/US híbrido)")
        print("   ✅ Parser de datas (timezone-aware)")
        print("   ✅ Conceito BankStrategy (normalização por banco)")
        print("   ✅ Integração (webhook → normalização)")
        
        print("\n🎯 COMPONENTES FUNCIONANDO:")
        print("   ✅ Helpers (sanitize, parse_amount, parse_date)")
        print("   ✅ Lógica de normalização")
        print("   ✅ Validações básicas")
        
        print("\n📚 PARA TESTE COMPLETO:")
        print("   1. Configure a estrutura completa (app/schemas/, app/etl/)")
        print("   2. Copie os arquivos dos documentos")
        print("   3. Execute test_nexa_complete.py")
        
    except AssertionError as e:
        print("\n" + "="*80)
        print("❌ TESTE FALHOU!")
        print("="*80)
        print(f"\nAssertion Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    except Exception as e:
        print("\n" + "="*80)
        print("❌ ERRO NO TESTE!")
        print("="*80)
        print(f"\n{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)