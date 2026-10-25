from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://churn:churn@db:5432/churn"
    admin_login: str = "admin"
    admin_password: str = "change-me-before-deploy"


    session_secret: str = "development-only-change-me"
    metrics_token: str = "development-only-change-me"
    seed_dataset: str = "official"

    cookie_secure: bool = False
    data_dir: str = "data"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()


def dataset_path(name: str) -> Path:

    candidates = [
        Path(settings.data_dir) / f"{name}.json",
        Path(__file__).resolve().parents[2] / "data" / f"{name}.json",
    ]
    return next((path for path in candidates if path.is_file()), candidates[0])
