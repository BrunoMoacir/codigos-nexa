#!/bin/bash
set -e

echo "=================================================="
echo "🧪 TESTE LOCAL - RAILWAY DEPLOYMENT"
echo "=================================================="
echo ""

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Verificar se está na pasta correta
if [ ! -f "Dockerfile.minimal" ]; then
    echo -e "${RED}❌ Erro: Execute este script na raiz do projeto!${NC}"
    echo "   Pasta atual: $(pwd)"
    exit 1
fi

echo "📁 Diretório: $(pwd)"
echo ""

# Função para testar URL
test_endpoint() {
    local url=$1
    local name=$2
    echo -n"Testing $name... "

    for i in {1..10}; do
        if curl -s -f "$url" > /dev/null 2>&1; then
            echo -e "${GREEN}✅ OK${NC}"
            curl -s "$url" | jq '.' 2>/dev/null || curl -s "$url"
            return 0
        fi
        sleep 1
    done

    echo -e "${RED}❌ FALHOU${NC}"
    return 1
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 TESTE 1: Build da Imagem Minimal"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if docker build -f Dockerfile.minimal -t nexa-minimal-test .; then
    echo -e "${GREEN}✅ Build minimal bem-sucedido${NC}"
else
    echo -e "${RED}❌ Build minimal falhou${NC}"
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 TESTE 2: Executar Container Minimal"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Parar container anterior se existir
docker stop nexa-minimal-test 2>/dev/null || true
docker rm nexa-minimal-test 2>/dev/null || true

echo "Iniciando container..."
docker run -d \
    --name nexa-minimal-test \
    -p 8001:8000 \
    -e PORT=8000 \
    -e APP_ENV=test \
    nexa-minimal-test

echo ""
echo "⏳ Aguardando API iniciar..."
sleep 3

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 TESTE 3: Verificar Endpoints"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ALL_OK=true

if ! test_endpoint "http://localhost:8001/health" "Health Check"; then
    ALL_OK=false
fi

echo ""

if ! test_endpoint "http://localhost:8001/" "Root Endpoint"; then
    ALL_OK=false
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 TESTE 4: Verificar Logs do Container"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

docker logs nexa-minimal-test

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🧹 Limpeza"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

docker stop nexa-minimal-test
docker rm nexa-minimal-test

echo ""
echo "=================================================="
echo "📊 RESULTADO FINAL"
echo "=================================================="
echo ""

if [ "$ALL_OK" = true ]; then
    echo -e "${GREEN}✅ TODOS OS TESTES PASSARAM!${NC}"
    echo ""
    echo "🎉 A versão MINIMAL funciona localmente!"
    echo ""
    echo "📋 Próximos passos:"
    echo "   1. Se você quer testar a versão COMPLETA, rode:"
    echo "      ./test-full-docker.sh"
    echo ""
    echo "   2. Para fazer deploy da versão MINIMAL no Railway:"
    echo "      - Edite railway.toml: dockerfilePath = \"Dockerfile.minimal\""
    echo "      - git add . && git commit -m \"Test minimal\" && git push"
    echo ""
    echo "   3. Se a versão minimal funcionar no Railway mas você precisa da completa:"
    echo "      - Volte para dockerfilePath = \"Dockerfile.railway\""
    echo "      - Vamos debugar a versão completa"
    exit 0
else
    echo -e "${RED}❌ ALGUNS TESTES FALHARAM${NC}"
    echo ""
    echo "🔍 Problema encontrado LOCALMENTE, não é culpa do Railway!"
    echo ""
    echo "📋 O que fazer:"
    echo "   1. Verifique os logs acima"
    echo "   2. Procure por 'Traceback' ou 'Error'"
    echo "   3. Me envie os logs para eu ajudar"
    exit 1
fi
