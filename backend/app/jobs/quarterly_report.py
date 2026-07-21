"""
app/jobs/quarterly_report.py — R4.a Relatório Trimestral Automático

Gera um relatório financeiro trimestral e envia via NotificationEngine (delivery_service).
Deve rodar no dia 1 dos meses 1, 4, 7, 10.
"""

import logging
from datetime import date, timezone
from dataclasses import dataclass
from ._base import job_guard, get_active_user_ids

logger = logging.getLogger(__name__)

@dataclass
class QuarterlyReportResult:
    user_id: str
    quarter: int
    year: int
    total_spent: float
    total_fees_paid: float
    total_saved: float
    generated: bool

class QuarterlyReportService:
    def __init__(self):
        pass
        
    async def generate_for_user(self, user_id: str, current_date: date) -> QuarterlyReportResult:
        # Define o trimestre baseado na data de execucao (ex: se rodar 1 de Abril, o trimestre é o 1)
        month = current_date.month
        year = current_date.year
        
        if month in [1, 2, 3]:
            quarter = 4
            year -= 1
        elif month in [4, 5, 6]:
            quarter = 1
        elif month in [7, 8, 9]:
            quarter = 2
        else:
            quarter = 3

        # Simula a consolidacao (Mock) -> em prod, vai ler F1 e F5 via duckdb
        total_spent = hash(user_id) % 15000 + 3000.0
        total_fees = hash(user_id + "fees") % 300 + 50.0
        total_saved = hash(user_id + "saved") % 1000 + 100.0
        
        # Envia notificacao (Mock)
        logger.info(f"Relatorio trimestral (Q{quarter}/{year}) gerado para {user_id}. Gasto: {total_spent}, Taxas: {total_fees}, Economia: {total_saved}")
        
        return QuarterlyReportResult(
            user_id=user_id,
            quarter=quarter,
            year=year,
            total_spent=round(total_spent, 2),
            total_fees_paid=round(total_fees, 2),
            total_saved=round(total_saved, 2),
            generated=True
        )

@job_guard("r4a_quarterly_report")
async def run_quarterly_report_job():
    """Executa a geracao do relatorio para todos os usuarios ativos."""
    service = QuarterlyReportService()
    active_users = get_active_user_ids()
    today = date.today()
    
    # Roda so no mes de inicio do trimestre
    if today.month not in [1, 4, 7, 10] or today.day != 1:
        logger.info("Hoje não é dia 1 de início de trimestre. Job ignorado.")
        return
        
    for user_id in active_users:
        try:
            await service.generate_for_user(user_id, today)
        except Exception as e:
            logger.error(f"Erro ao gerar relatorio trimestral para {user_id}: {e}")
