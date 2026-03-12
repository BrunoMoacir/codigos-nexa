import sys
import os

sys.path.append('.')
from app.db.users import create_user, get_user_by_email
from app.core.security import get_password_hash

def seed_auth_user():
    email = "golden_user_777"
    password = "password123"
    
    existing = get_user_by_email(email)
    if existing:
        print(f"Usuario {email} ja existe.")
        return
    
    hashed = get_password_hash(password)
    user = create_user(email=email, hashed_password=hashed, full_name="Golden User")
    if user:
        print(f"Usuario {email} criado com sucesso. Senha: {password}")
    else:
        print("Erro ao criar usuario.")

if __name__ == "__main__":
    seed_auth_user()
