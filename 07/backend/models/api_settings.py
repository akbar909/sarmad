from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from database import Base

class APISettings(Base):
    __tablename__ = "api_settings"

    id = Column(Integer, primary_key=True, index=True)
    llm_provider = Column(String(50), default="claude") # 'claude', 'openai', or 'groq'
    anthropic_key = Column(String(255), nullable=True)
    openai_key = Column(String(255), nullable=True)
    groq_key = Column(String(255), nullable=True)
    api_key = Column(String(255), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

