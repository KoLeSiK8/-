from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.engine import Engine

from .db import engine
from .migrations import run_migrations
from .api.source import router as source_router
from .api.customers import router as customers_router
from .api.analytics import router as analytics_router
from .api.model import router as model_router
from .api.events import router as events_router
from .api.metrics import router as metrics_router
from .auth.router import router as auth_router
from .config import dataset_path, settings
from .auth.security import hash_password
from .auth.throttle import LoginThrottle
from .ingestion.loader import load_snapshot
from .ingestion.schemas import SnapshotInput
from .scoring.recompute import recompute
from .events import EventBus
import json


def create_app(database_engine: Engine | None = None) -> FastAPI:
    app_engine = database_engine or engine

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        run_migrations(app_engine)
        _ensure_admin(app_engine)
        if settings.seed_dataset in {"official", "demo"}:
            with app_engine.connect() as connection:
                has_accounts = connection.exec_driver_sql(
                    "SELECT EXISTS (SELECT 1 FROM public.accounts)"
                ).scalar_one()
            seed_path = dataset_path(settings.seed_dataset)
            if not has_accounts and seed_path.is_file():
                payload = json.loads(seed_path.read_text(encoding="utf-8"))
                load_snapshot(app_engine, SnapshotInput.model_validate(payload))
        recompute(app_engine)
        yield

    application = FastAPI(
        title="Анализатор рисков оттока",
        description="API системы анализа риска оттока клиентов.",
        version="0.1.0",
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
        lifespan=lifespan,
    )
    application.state.engine = app_engine
    application.state.event_bus = EventBus()
    application.state.login_throttle = LoginThrottle()
    application.include_router(source_router, prefix="/api/v1/source", tags=["source"])
    application.include_router(customers_router, prefix="/api/v1/customers", tags=["customers"])
    application.include_router(analytics_router, prefix="/api/v1/analytics", tags=["analytics"])
    application.include_router(model_router, prefix="/api/v1/model", tags=["model"])
    application.include_router(events_router, prefix="/api/v1/events", tags=["events"])
    application.include_router(metrics_router, tags=["metrics"])
    application.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])

    @application.get("/healthz", tags=["health"], summary="Проверка доступности")
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()


def _ensure_admin(app_engine: Engine) -> None:
    connection = app_engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app.users (login, password_hash)
                VALUES (%s, %s)
                ON CONFLICT (login) DO UPDATE SET
                    password_hash = EXCLUDED.password_hash
                """,
                (settings.admin_login, hash_password(settings.admin_password)),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()