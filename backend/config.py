from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    API_VERSION: str = "/api/v1"
    PORT: int = 8000
    HOST: str = "127.0.0.1"
    ENVIRONMENT: str = "development"
    
    class Config:
        env_file = ".env"

settings = Settings()
