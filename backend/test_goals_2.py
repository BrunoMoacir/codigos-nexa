from datetime import datetime, timezone
import uuid

# Criar banco sqlite puro para teste
import sqlite3
conn = sqlite3.connect('test_db.sqlite')
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE financial_goals (
        goal_id TEXT PRIMARY KEY,
        user_id TEXT,
        name TEXT,
        goal_type TEXT,
        target_amount REAL,
        current_amount REAL,
        target_date TEXT,
        monthly_contribution_needed REAL,
        monthly_contribution_actual REAL,
        status TEXT,
        created_at TEXT,
        updated_at TEXT,
        version INTEGER
    )
''')
conn.commit()

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.goals.tracker import GoalTracker
from app.goals.models import FinancialGoal

engine = create_engine('sqlite:///test_db.sqlite')
Session = sessionmaker(bind=engine)
db = Session()

tracker = GoalTracker(db)
goal = tracker.create_goal(
    user_id=str(uuid.uuid4()),
    name="Test",
    goal_type="outros",
    target_amount=100.0,
    current_amount=0.0,
    target_date="2027-01-01"
)
print("GOAL CREATED:", goal.to_dict())
