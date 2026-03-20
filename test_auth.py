import sys
sys.path.append('.')
from app.core.database import SessionLocal
from app.db.users import get_user_by_email
from app.core.security import verify_password

db = SessionLocal()
user = get_user_by_email(db, "demo@nexa.com")
print(user)
if user:
    pwd_match = verify_password("demo123", user["hashed_password"])
    print("Match:", pwd_match)
