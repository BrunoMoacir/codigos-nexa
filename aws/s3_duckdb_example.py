"""
Exemplo de conexão do DuckDB com o AWS S3 (Fase 2 do plano).
Na AWS, não podemos manter o arquivo .db local (pois ele se perde quando o container Fargate reinicia).
A solução oficial e performática para DuckDB na nuvem é carregar e salvar a base no S3 usando a extensão httpfs.
"""

import duckdb
import os
import logging

logger = logging.getLogger(__name__)

def get_duckdb_s3_connection() -> duckdb.DuckDBPyConnection:
    """
    Retorna uma conexão DuckDB mapeada diretamente para um bucket S3.
    Requisitos:
      - Variáveis AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION configuradas.
      - Variável S3_DUCKDB_PATH (ex: s3://meu-bucket/finance.duckdb)
    """
    s3_path = os.getenv("S3_DUCKDB_PATH")
    
    if not s3_path:
        raise ValueError("S3_DUCKDB_PATH não configurado.")

    # Conecta a uma base em memória temporariamente para instalar as extensões S3
    # NOTA: O DuckDB suporta query direta no S3 (parquet) ou abrir um arquivo .db via httpfs.
    conn = duckdb.connect()
    
    logger.info("Configurando DuckDB para integração S3...")
    conn.execute("INSTALL httpfs;")
    conn.execute("LOAD httpfs;")
    
    # Injeta credenciais da AWS direto na engine do DuckDB
    aws_id = os.getenv("AWS_ACCESS_KEY_ID", "")
    aws_secret = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    aws_region = os.getenv("AWS_REGION", "us-east-1")
    
    conn.execute(f"SET s3_region='{aws_region}';")
    conn.execute(f"SET s3_access_key_id='{aws_id}';")
    conn.execute(f"SET s3_secret_access_key='{aws_secret}';")
    
    # IMPORTANTE:
    # Ler/Gravar um .db inteiro do S3 direto é lento. A prática recomendada de 
    # Data Lakehouse é exportar as tabelas analíticas para S3 no formato Parquet,
    # e ler de lá.
    # Exemplo:
    # conn.execute("CREATE TABLE transactions AS SELECT * FROM read_parquet('s3://meu-bucket/transactions/*.parquet')")
    
    logger.info("DuckDB pronto para rodar queries analíticas no Data Lake S3.")
    return conn

if __name__ == "__main__":
    # Como rodar para testar localmente:
    # export S3_DUCKDB_PATH="s3://nexa-analytics-bucket/test.parquet"
    # python s3_duckdb_example.py
    pass
