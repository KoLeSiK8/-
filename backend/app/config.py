from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://churn:churn@db:5432/churn"
    admin_login: str = "admin"
    admin_password: str = "change-me-before-deploy"
    session_secret: str = "development-only-change-me"
    metrics_token: str = "development-only-change-me"
    seed_dataset: str = "official"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()