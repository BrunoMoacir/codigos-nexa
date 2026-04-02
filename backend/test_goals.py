from datetime import datetime, timezone
import uuid
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import create_engine, Column, String, Float, Integer
from sqlalchemy.orm import declarative_base, sessionmaker

from app.goals.models import FinancialGoal
from app.goals.tracker import GoalTracker

# Just use sqlite
engine = create_engine("sqlite:///test.db")
FinancialGoal.metadata.create_all(engine)
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
print("Goal:", goal.to_dict())
