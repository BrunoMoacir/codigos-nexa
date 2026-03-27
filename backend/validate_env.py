#!/usr/bin/env python3
"""
Script para validar variáveis de ambiente necessárias no Railway
Execute antes de fazer deploy para verificar se tudo está configurado corretamente
"""

import os
import sys

def check_env_var(var_name: str, required: bool = True, description: str = "") -> bool:
    """Verifica se uma variável de ambiente está configurada"""
    value = os.getenv(var_name)
    status = "✅" if value else "❌"
    req_label = "(OBRIGATÓRIA)" if required else "(Opcional)"

    print(f"{status} {var_name} {req_label}")
    if description:
        print(f"   └─ {description}")

    if value:
        # Mostra apenas os primeiros/últimos caracteres de valores sensíveis
        if any(key in var_name.lower() for key in ['key', 'secret', 'password', 'token']):
            masked = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
            print(f"   └─ Valor: {masked}")
        elif 'url' in var_name.lower():
            # Para URLs, mostra apenas o protocolo e host
            try:
                from urllib.parse import urlparse
                parsed = urlparse(value)
                print(f"   └─ Valor: {parsed.scheme}://{parsed.netloc}/...")
            except:
                print(f"   └─ Valor: {value[:30]}...")
        else:
            print(f"   └─ Valor: {value}")

    if required and not value:
        return False
    return True

def main():
    print("=" * 60)
    print("🔍 VALIDAÇÃO DE VARIÁVEIS DE AMBIENTE - RAILWAY")
    print("=" * 60)
    print()

    all_good = True

    print("📦 VARIÁVEIS OBRIGATÓRIAS:")
    print("-" * 60)
    all_good &= check_env_var("DATABASE_URL", True, "URL do PostgreSQL")
    all_good &= check_env_var("SECRET_KEY", True, "Chave secreta para JWT")
    all_good &= check_env_var("APP_ENV", True, "Ambiente (production/development)")

    print()
    print("🤖 VARIÁVEIS DE LLM (recomendadas):")
    print("-" * 60)
    check_env_var("OPENAI_API_KEY", False, "Chave da API OpenAI")
    check_env_var("ANTHROPIC_API_KEY", False, "Chave da API Anthropic")
    check_env_var("LLM_PROVIDER", False, "Provider LLM (openai/anthropic)")
    check_env_var("LLM_MODEL", False, "Modelo LLM")

    print()
    print("🔌 VARIÁVEIS DE INTEGRAÇÃO (opcionais):")
    print("-" * 60)
    check_env_var("PLUGGY_CLIENT_ID", False, "Client ID Pluggy")
    check_env_var("PLUGGY_CLIENT_SECRET", False, "Client Secret Pluggy")
    check_env_var("PLUGGY_BASE_URL", False, "URL base Pluggy")

    print()
    print("🗄️ CACHE E OUTROS (opcionais):")
    print("-" * 60)
    check_env_var("REDIS_URL", False, "URL do Redis")
    check_env_var("LOG_LEVEL", False, "Nível de log")
    check_env_var("FRONTEND_BASE_URL", False, "URL do frontend")
    check_env_var("PORT", False, "Porta da API (Railway define automaticamente)")

    print()
    print("=" * 60)

    if all_good:
        print("✅ TODAS AS VARIÁVEIS OBRIGATÓRIAS ESTÃO CONFIGURADAS!")
        print()
        print("🚀 Você pode fazer deploy no Railway com segurança.")
        print()
        print("📝 Próximos passos:")
        print("   1. Commit e push para o GitHub")
        print("   2. O Railway fará deploy automaticamente")
        print("   3. Aguarde 2-3 minutos")
        print("   4. Verifique: curl https://sua-url.railway.app/health")
        return 0
    else:
        print("❌ FALTAM VARIÁVEIS OBRIGATÓRIAS!")
        print()
        print("🔧 Configure no Railway:")
        print("   1. Acesse o painel do serviço da API")
        print("   2. Vá em 'Variables'")
        print("   3. Adicione as variáveis marcadas com ❌")
        print()
        print("💡 Exemplo:")
        print("   DATABASE_URL=${{Postgres.DATABASE_URL}}")
        print("   SECRET_KEY=<gere com: openssl rand -hex 32>")
        print("   APP_ENV=production")
        return 1

if __name__ == "__main__":
    sys.exit(main())
