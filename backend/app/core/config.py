from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = "Heart Failure CDSS"
    version: str = "0.1.0"
    environment: str = "development"
    cors_origins: list[str] = ["http://localhost:5173"]
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_prefix="HF_CDSS_", env_file=".env")


settings = Settings()
