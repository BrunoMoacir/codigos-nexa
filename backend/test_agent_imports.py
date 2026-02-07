from app.agent.shadow_invoice.detector import ShadowInvoiceDetector
from app.agent.user_profile.analyzer import UserProfileAnalyzer

sid = ShadowInvoiceDetector()
profile = UserProfileAnalyzer()

print("ShadowInvoiceDetector OK")
print("UserProfileAnalyzer OK")

print(profile.analyze(7200, 5300))