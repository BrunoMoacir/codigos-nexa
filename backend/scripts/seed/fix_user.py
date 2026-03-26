import sys
sys.path.append('.')
from app.core.database import SessionLocal
from app.models.user import User
from app.core.security import get_password_hash

db = SessionLocal()
user = db.query(User).filter_by(user_id="golden_user_777").first()
if user:
    user.email = "demo@nexa.com"
    user.hashed_password = get_password_hash("demo123")
    db.commit()
    print("User updated to demo@nexa.com / demo123")
