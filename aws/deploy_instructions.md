# Guia de Deploy na AWS (Nexa)

Este documento centraliza tudo que você precisa fazer **assim que criar a sua conta na AWS**, para subir toda a infraestrutura do Nexa preparada nos scripts desta pasta.

## Passo 1: Criar as Chaves de Acesso (IAM)
1. Acesse o console da AWS e vá em **IAM (Identity and Access Management)**.
2. Crie um novo usuário chamado `github-actions-nexa`.
3. Anexe as seguintes políticas (Policies) a este usuário:
   - `AmazonEC2ContainerRegistryPowerUser` (Para o GitHub enviar as imagens Docker pro ECR)
   - `AmazonECS_FullAccess` (Para atualizar os serviços ECS)
   - `AmazonS3FullAccess` (Para o DuckDB gravar a analítica e o Frontend subir estático)
   - `AmazonSQSFullAccess` (Para enviar jobs de win-back e relatórios)
4. Gere uma **Access Key** e **Secret Key**. Guarde com segurança.

## Passo 2: Subir a Infraestrutura Base (Terraform)
Você não precisa clicar em mil telas na AWS. A pasta `terraform/` já tem a receita pronta.
No seu terminal local (onde você tem o Terraform instalado):

```bash
cd aws/terraform
terraform init
terraform apply
```
*Isto criará automaticamente: O Registro do Docker (ECR), o Cluster ECS (Fargate), o RDS do Postgres, o Bucket do S3 (DuckDB/Frontend) e a Fila SQS (Jobs).*
Anote os URLs que aparecerão no final do script (`ecr_repository_url`, `rds_endpoint`, etc).

## Passo 3: Configurar os Secrets do GitHub
Vá no seu repositório GitHub em `Settings -> Secrets and variables -> Actions` e adicione:
- `AWS_ACCESS_KEY_ID`: (A chave gerada no passo 1)
- `AWS_SECRET_ACCESS_KEY`: (A chave secreta)
- `S3_BUCKET_NAME`: (O nome do bucket gerado pelo Terraform)
- `CLOUDFRONT_ID`: (O ID da CDN, se criar uma futuramente pro Front)

## Passo 4: Fazer o Deploy
Basta fazer um push na branch `main` ou rodar a Action manualmente. 
O arquivo `.github/workflows/aws-build.yml` vai cuidar de fazer o build do `Dockerfile.api` e do Frontend e jogar tudo pros lugares certos na AWS.
