import sys
sys.path.append('.')
from app.core.database import SessionLocal
from app.models.user import User

db = SessionLocal()
users = db.query(User).all()
for u in users:
    print(u.user_id, u.email, u.full_name)
