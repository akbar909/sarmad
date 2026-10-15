from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from database import Base

class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_url = Column(String(500), nullable=True)
    description = Column(Text, nullable=False)
    image_url = Column(String(255), nullable=True)
    status = Column(String(50), default="Pending") # 'Pending', 'Reviewed', 'Action Taken'
    created_at = Column(DateTime(timezone=True), server_default=func.now())
