from app.core.shadow_invoices import detect_shadow_invoices


class ShadowInvoiceDetector:

    def run(self, transactions):
        return detect_shadow_invoices(transactions)