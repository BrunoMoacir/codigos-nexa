from sqlalchemy import Column, String, DateTime, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class PluggyItem(Base):
    __tablename__ = "pluggy_items"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    item_id = Column(String, nullable=False, index=True)
    connector_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "item_id", name="uq_pluggy_items_user_item"),
    )
