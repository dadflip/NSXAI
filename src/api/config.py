"""
NSXAI API Configuration
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """API configuration settings."""
    
    # Application
    APP_NAME: str = "NSXAI API"
    APP_VERSION: str = "0.1.0-dev"
    DEBUG: bool = False
    
    # API
    API_V1_PREFIX: str = "/api/v1"
    API_V2_PREFIX: str = "/api/v2"
    
    # CORS
    CORS_ORIGINS: list[str] = ["*"]
    CORS_METHODS: list[str] = ["*"]
    CORS_HEADERS: list[str] = ["*"]
    
    # Security
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    
    # Ontologies
    ONTOLOGY_DIR: str = "../../source/ontologies"
    
    # Models
    MODELS_DIR: str = "../../models"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Returns cached configuration settings."""
    return Settings()
