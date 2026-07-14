import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    API_VERSION: str = "/api/v1"
    PORT: int = int(os.environ.get("PORT", 8000))
    HOST: str = os.environ.get("HOST", "0.0.0.0")
    ENVIRONMENT: str = "development"
    
    class Config:
        env_file = ".env"

settings = Settings()
