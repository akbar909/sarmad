from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from datetime import datetime
from database import Base

class Detection(Base):
    __tablename__ = "detections"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    image_url = Column(String, default="")
    result = Column(String)
    confidence = Column(Float)
    llm_explanation = Column(Text)
    category = Column(String, default="Other")
    risk_level = Column(String, default="UNKNOWN")
    evidence = Column(Text, default="{}")
    recommendation = Column(Text, default="")
    red_flags = Column(Text, default="[]")
    positive_signs = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)

