from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    PROJECT_NAME: str = "forjd backend"
    API_V1_STR: str = "/api/v1"
    
    # Database & Cache
    POSTGRES_DSN: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/forjd"
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Prefect
    PREFECT_API_URL: str = "http://127.0.0.1:4200/api"  # default local

settings = Settings()