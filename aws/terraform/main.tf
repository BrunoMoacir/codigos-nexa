terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  default = "us-east-1"
}

variable "project_name" {
  default = "nexa"
}

# 1. Registro de Containers (ECR) para a API e Worker
resource "aws_ecr_repository" "backend_repo" {
  name                 = "${var.project_name}-backend"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}

# 2. Cluster ECS (Onde os containeres Fargate vão rodar)
resource "aws_ecs_cluster" "main_cluster" {
  name = "${var.project_name}-cluster"
}

# 3. Bucket S3 (Para DuckDB Analytics e/ou Frontend estático)
resource "aws_s3_bucket" "nexa_storage" {
  bucket        = "${var.project_name}-storage-bucket-${random_id.bucket_suffix.hex}"
  force_destroy = true
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}
  
# 4. SQS Queue (Para processamento de jobs assíncronos - Fase 3)
resource "aws_sqs_queue" "jobs_queue" {
  name                       = "${var.project_name}-jobs-queue"
  visibility_timeout_seconds = 300
}

# 5. RDS PostgreSQL (Banco de Dados Primário)
# ATENÇÃO: Para produção, defina uma senha forte via AWS Secrets Manager e remova o `skip_final_snapshot`.
resource "aws_db_instance" "postgres_db" {
  identifier           = "${var.project_name}-db"
  allocated_storage    = 20
  engine               = "postgres"
  engine_version       = "16"
  instance_class       = "db.t3.micro"
  username             = "nexaadmin"
  password             = "mudar12345" # Mudar em produção!
  skip_final_snapshot  = true
  publicly_accessible  = false
}

output "ecr_repository_url" {
  value = aws_ecr_repository.backend_repo.repository_url
}

output "s3_bucket_name" {
  value = aws_s3_bucket.nexa_storage.id
}

output "sqs_queue_url" {
  value = aws_sqs_queue.jobs_queue.url
}

output "rds_endpoint" {
  value = aws_db_instance.postgres_db.endpoint
}
