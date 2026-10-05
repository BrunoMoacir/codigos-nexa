import json
import pytest
from unittest.mock import MagicMock, patch

from app.negotiator.models import (
    NegotiationChannel,
    NegotiationOpportunity,
    NegotiationScript,
    NegotiationTrigger,
)
from app.negotiator.script_generator import NegotiationScriptGenerator

def _mock_opportunity() -> NegotiationOpportunity:
    return NegotiationOpportunity(
        trigger=NegotiationTrigger.JUROS_ROTATIVO_ALTO,
        bank_name="Itaú",
        product="Crédito Rotativo",
        user_rate_monthly=0.12,
        market_rate_monthly=0.035,
        potential_saving_monthly=250.0,
        health_score=72,
        months_as_good_payer=0,
        description="Juros rotativos detectados acima do mercado.",
    )

def test_script_generator_success():
    generator = NegotiationScriptGenerator()
    opp = _mock_opportunity()
    
    mock_json_response = {
        "opening_line": "Olá gerente, tudo bem?",
        "key_arguments": [
            "Sou um bom cliente.",
            "A taxa está alta.",
            "Gostaria de reduzir."
        ],
        "target_ask": "Redução para 3.5%",
        "fallback_ask": "Isenção de uma parcela",
        "closing_line": "Obrigado.",
        "recommended_channel": "APP_CHAT",
        "best_time": "segunda de manhã",
        "estimated_success_pct": 80,
        "warnings": []
    }
    
    with patch.object(generator, "_call_claude", return_value=json.dumps(mock_json_response)):
        script = generator.generate(opp)
        
    assert script.opening_line == "Olá gerente, tudo bem?"
    assert len(script.key_arguments) == 3
    assert script.recommended_channel == NegotiationChannel.APP_CHAT
    assert script.estimated_success_pct == 80

def test_script_generator_fallback_on_json_error():
    generator = NegotiationScriptGenerator()
    opp = _mock_opportunity()
    
    with patch.object(generator, "_call_claude", return_value="Isso não é um JSON válido"):
        script = generator.generate(opp)
        
    assert script.generated_by == "fallback"
    assert script.opportunity == opp
    assert len(script.key_arguments) > 0
    assert len(script.warnings) > 0
    assert "localmente" in script.warnings[0]

def test_script_generator_fallback_on_api_exception():
    generator = NegotiationScriptGenerator()
    opp = _mock_opportunity()
    
    with patch.object(generator, "_call_claude", side_effect=Exception("API Error")):
        script = generator.generate(opp)
        
    assert script.generated_by == "fallback"
    assert script.opportunity == opp
    assert len(script.warnings) > 0

def test_parse_script_handles_invalid_channel():
    generator = NegotiationScriptGenerator()
    opp = _mock_opportunity()
    
    mock_json_response = {
        "opening_line": "Olá",
        "key_arguments": [],
        "target_ask": "",
        "fallback_ask": "",
        "closing_line": "",
        "recommended_channel": "CANAL_INVENTADO",
        "best_time": "",
        "estimated_success_pct": 50,
        "warnings": []
    }
    
    with patch.object(generator, "_call_claude", return_value=json.dumps(mock_json_response)):
        script = generator.generate(opp)
        
    # Deve fazer fallback para APP_CHAT se channel for inválido
    assert script.recommended_channel == NegotiationChannel.APP_CHAT

def test_parse_script_clamps_success_pct():
    generator = NegotiationScriptGenerator()
    opp = _mock_opportunity()
    
    mock_json_response = {
        "opening_line": "Olá",
        "key_arguments": [],
        "target_ask": "",
        "fallback_ask": "",
        "closing_line": "",
        "recommended_channel": "APP_CHAT",
        "best_time": "",
        "estimated_success_pct": 150, # Acima de 100
        "warnings": []
    }
    
    with patch.object(generator, "_call_claude", return_value=json.dumps(mock_json_response)):
        script = generator.generate(opp)
        
    assert script.estimated_success_pct == 100


# ── JSON do LLM embrulhado em markdown ou com frase antes ─────────────────────

def test_extrair_json_aceita_cerca_markdown_e_texto_antes():
    """`json.loads` direto falhava e todo roteiro caía no template local."""
    from app.negotiator.script_generator import _extrair_json

    assert _extrair_json('```json\n{"opening_line": "Oi"}\n```') == {"opening_line": "Oi"}
    assert _extrair_json('Claro! Segue:\n{"a": 1, "b": [2]}') == {"a": 1, "b": [2]}


def test_extrair_json_sem_objeto_levanta_decode_error():
    import json

    import pytest

    from app.negotiator.script_generator import _extrair_json

    with pytest.raises(json.JSONDecodeError):
        _extrair_json("não consigo ajudar com isso")
