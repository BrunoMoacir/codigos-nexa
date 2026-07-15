"""
app/privacy — Direitos do titular de dados (LGPD arts. 18 e 19).

  GET    /privacy/export/{user_id}  — portabilidade: todos os dados do
                                      titular em JSON estruturado
  DELETE /privacy/erase/{user_id}   — eliminação: apaga os dados pessoais
                                      e financeiros do titular

Ambas exigem o token do próprio titular (require_owner) e geram evento
de auditoria dedicado (PRIVACY_EXPORT / PRIVACY_DELETION).
"""
