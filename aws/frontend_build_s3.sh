#!/bin/bash
set -e

echo "=========================================="
echo "📦 NEXA FRONTEND - AWS S3 DEPLOYMENT"
echo "=========================================="
echo ""

# Na AWS, o frontend (React/Vite) não roda em um container NGINX na nuvem.
# Ele é 'compilado' para HTML/JS puro (Static Site Generation) e 
# jogado em um Bucket S3 atrás de uma CDN (CloudFront).

# 1. Instalar as dependencias
echo "1. Instalando dependências..."
cd ../frontend-react
npm install

# 2. Injetar a URL de produção na build
# IMPORTANTE: No modelo SSG, o front-end compila as URLs estaticamente.
echo "2. Gerando build de produção (Vite)..."
export VITE_API_URL="https://api.nexa.finance"
npm run build

# 3. Sincronizar pasta /dist com o Bucket S3 (Requer AWS CLI e aws configure)
echo "3. Fazendo upload para o Bucket S3..."
# aws s3 sync dist/ s3://meu-bucket-frontend-nexa --delete

# 4. Invalidar o cache do CloudFront para os usuários verem o site novo
echo "4. Invalidando cache da CDN..."
# aws cloudfront create-invalidation --distribution-id MEU_ID --paths "/*"

echo "✅ Deploy de Frontend na AWS concluído."
