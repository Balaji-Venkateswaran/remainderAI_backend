from sqlalchemy import Column, Integer, String, Text

from app.db import Base


class GoogleOAuthTokenORM(Base):
    __tablename__ = "google_oauth_tokens"

    id = Column(Integer, primary_key=True)
    provider = Column(String, nullable=False, unique=True)
    token_json = Column(Text, nullable=False)
