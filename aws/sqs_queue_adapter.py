"""
Adaptador de Filas AWS SQS (Fase 3 do plano).
Na arquitetura do Railway, o APScheduler rodava em memória.
Na AWS, o padrão ouro é usar EventBridge (para crons) chamando lambdas, 
ou enviando mensagens para o SQS (Simple Queue Service), e o Worker consome de lá.
"""

import boto3
import json
import logging
import os
from typing import Dict, Any, Callable

logger = logging.getLogger(__name__)

class SQSQueueAdapter:
    def __init__(self, queue_url: str):
        self.queue_url = queue_url
        self.sqs = boto3.client(
            'sqs',
            region_name=os.getenv("AWS_REGION", "us-east-1"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
        )

    def enqueue_job(self, job_name: str, payload: Dict[str, Any]):
        """Envia um job para a fila do SQS"""
        try:
            message = {
                "job_name": job_name,
                "payload": payload
            }
            response = self.sqs.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(message),
                MessageGroupId=job_name, # Apenas se for fila FIFO
                MessageDeduplicationId=str(hash(json.dumps(message)))
            )
            logger.info(f"Job {job_name} enviado para SQS. ID: {response.get('MessageId')}")
            return response.get("MessageId")
        except Exception as e:
            logger.error(f"Erro ao enviar job para SQS: {e}")
            raise

    def consume(self, handler_map: Dict[str, Callable]):
        """
        Roda em loop infinito no container 'Worker' puxando as mensagens do SQS.
        O handler_map vincula o nome do job à função que deve ser executada.
        """
        logger.info(f"Iniciando consumo da fila SQS: {self.queue_url}")
        
        while True:
            try:
                response = self.sqs.receive_message(
                    QueueUrl=self.queue_url,
                    MaxNumberOfMessages=10,
                    WaitTimeSeconds=20 # Long polling
                )
                
                messages = response.get('Messages', [])
                for msg in messages:
                    receipt_handle = msg['ReceiptHandle']
                    body = json.loads(msg['Body'])
                    job_name = body.get('job_name')
                    payload = body.get('payload', {})
                    
                    if job_name in handler_map:
                        logger.info(f"Executando job recebido: {job_name}")
                        try:
                            # Executa a tarefa correspondente
                            handler_map[job_name](**payload)
                            
                            # Sucesso! Apaga a mensagem da fila.
                            self.sqs.delete_message(
                                QueueUrl=self.queue_url,
                                ReceiptHandle=receipt_handle
                            )
                        except Exception as e:
                            logger.error(f"Falha ao executar job {job_name}: {e}")
                            # Não apaga a mensagem. Ela voltará para a fila após o Visibility Timeout.
                    else:
                        logger.warning(f"Nenhum handler para o job: {job_name}")
                        
            except KeyboardInterrupt:
                logger.info("Worker desligando...")
                break
            except Exception as e:
                logger.error(f"Erro ao ler SQS: {e}")
                
if __name__ == "__main__":
    # Exemplo de inicializacao:
    # adapter = SQSQueueAdapter("https://sqs.us-east-1.amazonaws.com/123456789/NexaJobsQueue")
    # adapter.enqueue_job("r5c_win_back", {"user_id": "test"})
    pass
