#!/bin/bash
# Script para testar o build do Docker antes do deploy no Railway

echo "🚀 Testando build do Docker para Railway..."

# Build da imagem
echo "📦 Fazendo build da imagem..."
docker build -t nexa-api-test .

if [ $? -ne 0 ]; then
    echo "❌ Erro ao fazer build da imagem!"
    exit 1
fi

echo "✅ Build concluído com sucesso!"

# Testar se a imagem roda
echo "🧪 Testando se o container inicia..."
docker run -d --name nexa-test -p 8001:8000 \
    -e DATABASE_URL="postgresql+psycopg2://test:test@localhost:5432/test" \
    -e SECRET_KEY="test-secret-key" \
    -e APP_ENV="development" \
    nexa-api-test

if [ $? -ne 0 ]; then
    echo "❌ Erro ao iniciar o container!"
    exit 1
fi

# Aguardar alguns segundos
echo "⏳ Aguardando container inicializar..."
sleep 5

# Testar health check
echo "🏥 Testando health check..."
response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/health)

if [ "$response" = "200" ]; then
    echo "✅ Health check passou! API está funcionando."
else
    echo "❌ Health check falhou! Status: $response"
    echo "📋 Logs do container:"
    docker logs nexa-test
    docker stop nexa-test
    docker rm nexa-test
    exit 1
fi

# Limpar
echo "🧹 Limpando containers de teste..."
docker stop nexa-test
docker rm nexa-test

echo "✨ Todos os testes passaram! Você pode fazer deploy no Railway."
echo ""
echo "Próximos passos:"
echo "1. Fazer commit e push das mudanças"
echo "2. Conectar o repositório no Railway"
echo "3. Adicionar PostgreSQL no Railway"
echo "4. Configurar variáveis de ambiente"
echo "5. Deploy automático!"
