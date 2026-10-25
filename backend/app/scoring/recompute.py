from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy.engine import Engine

from ..db_copy import copy_rows

from ..ingestion.schemas import SnapshotInput
from ..ingestion.quality import find_quality_warnings
from .engine import compute_scoring
from .money import compute_money
from .lock import RECOMPUTE_LOCK
from .registry import FEATURES
from .settings import ScoringSettings


def load_settings(engine: Engine) -> tuple[ScoringSettings, int]:
    default_settings = ScoringSettings()
    connection = engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT settings, version FROM app.model_settings WHERE id = 1")
            row = cursor.fetchone()
            if row is not None:
                return _validate_stored(row[0]), row[1]
            cursor.execute(
                """
                INSERT INTO app.model_settings (id, settings, version)
                VALUES (1, %s, 1)
                ON CONFLICT (id) DO NOTHING
                RETURNING settings, version
                """,
                (Jsonb(default_settings.model_dump(mode="json")),),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute("SELECT settings, version FROM app.model_settings WHERE id = 1")
                row = cursor.fetchone()
            connection.commit()
            return _validate_stored(row[0]), row[1]
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _validate_stored(stored: dict[str, Any]) -> ScoringSettings:

    data = dict(stored)
    weights = {
        key: feature.default_weight for key, feature in FEATURES.items()
    } | {key: value for key, value in (data.get("weights") or {}).items() if key in FEATURES}
    data["weights"] = weights
    return ScoringSettings.model_validate(data)


def save_settings(
    engine: Engine, settings: ScoringSettings, connection: Any | None = None
) -> int:

    owns_connection = connection is None
    active_connection = connection or engine.raw_connection()
    try:
        with active_connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app.model_settings (id, settings, version)
                VALUES (1, %s, 1)
                ON CONFLICT (id) DO UPDATE SET
                    settings = EXCLUDED.settings,
                    version = app.model_settings.version + 1,
                    updated_at = now()
                RETURNING version
                """,
                (Jsonb(settings.model_dump(mode="json")),),
            )
            version = cursor.fetchone()[0]
        if owns_connection:
            active_connection.commit()
        return version
    except Exception:
        if owns_connection:
            active_connection.rollback()
        raise
    finally:
        if owns_connection:
            active_connection.close()


def recompute(
    engine: Engine,
    snapshot: SnapshotInput | None = None,
    connection: Any | None = None,
    settings: ScoringSettings | None = None,
    version: int | None = None,
) -> dict[str, Any]:

    with RECOMPUTE_LOCK:
        return _recompute(engine, snapshot, connection, settings, version)


def _recompute(
    engine: Engine,
    snapshot: SnapshotInput | None,
    connection: Any | None,
    settings: ScoringSettings | None,
    version: int | None,
) -> dict[str, Any]:
    snapshot = snapshot or _load_snapshot(engine)
    if settings is None or version is None:
        settings, version = load_settings(engine)
    scored = compute_scoring(snapshot, settings)
    customer_money, summary = compute_money(
        snapshot.accounts, snapshot.services, scored, settings
    )
    value_by_service = {
        service.service_id: service
        for customer in customer_money
        for service in customer.services
    }
    expected_loss_by_customer = {
        customer.customer_id: sum(item.expected_loss_cents for item in customer.services)
        for customer in customer_money
    }
    warnings_by_customer: dict[int, list[dict[str, Any]]] = {}
    for warning in find_quality_warnings(snapshot):
        warnings_by_customer.setdefault(warning["customerId"], []).append(warning)

    calculated_at = datetime.now(timezone.utc)
    owns_connection = connection is None
    active_connection = connection or engine.raw_connection()
    try:
        with active_connection.cursor() as cursor:
            cursor.execute("DELETE FROM app.service_scores")
            cursor.execute("DELETE FROM app.customer_scores")
            copy_rows(
                cursor,
                "app.customer_scores (customer_id, score, level, loyalty, expected_loss_cents, reasons, data_warnings, model_version, calculated_at)",
                [
                    (
                        customer.customer_id,
                        customer.score,
                        customer.level,
                        customer.loyalty,
                        expected_loss_by_customer.get(customer.customer_id, 0),
                        Jsonb(customer.reasons),
                        Jsonb(warnings_by_customer.get(customer.customer_id, [])),
                        version,
                        calculated_at,
                    )
                    for customer in scored.customers
                ],
            )
            copy_rows(
                cursor,
                "app.service_scores (service_id, customer_id, score, feature_contributions, value_cents, expected_loss_cents, model_version, calculated_at)",
                [
                    (
                        service.service_id,
                        service.customer_id,
                        service.score,
                        Jsonb(service.contributions),
                        value_by_service.get(service.service_id).value_cents
                        if service.service_id in value_by_service
                        else 0,
                        value_by_service.get(service.service_id).expected_loss_cents
                        if service.service_id in value_by_service
                        else 0,
                        version,
                        calculated_at,
                    )
                    for service in scored.services
                ],
            )
            cursor.execute(
                """
                INSERT INTO app.score_summary
                    (id, model_version, as_of, calculated_at, revenue_at_risk_cents,
                     expected_loss_cents, recoverable_cents, lost_revenue_monthly_cents,
                     hourly_share)
                VALUES (1, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    model_version = EXCLUDED.model_version,
                    as_of = EXCLUDED.as_of,
                    calculated_at = EXCLUDED.calculated_at,
                    revenue_at_risk_cents = EXCLUDED.revenue_at_risk_cents,
                    expected_loss_cents = EXCLUDED.expected_loss_cents,
                    recoverable_cents = EXCLUDED.recoverable_cents,
                    lost_revenue_monthly_cents = EXCLUDED.lost_revenue_monthly_cents,
                    hourly_share = EXCLUDED.hourly_share
                """,
                (
                    version,
                    scored.as_of,
                    calculated_at,
                    summary.revenue_at_risk_cents,
                    summary.expected_loss_cents,
                    summary.recoverable_cents,
                    summary.lost_revenue_monthly_cents,
                    summary.hourly_share,
                ),
            )
        if owns_connection:
            active_connection.commit()
    except Exception:
        if owns_connection:
            active_connection.rollback()
        raise
    finally:
        if owns_connection:
            active_connection.close()

    return {
        "modelVersion": version,
        "asOf": scored.as_of,
        "calculatedAt": calculated_at,
        "customerCount": len(scored.customers),
        "serviceCount": len(scored.services),
        "summary": summary,
    }


def _load_snapshot(engine: Engine) -> SnapshotInput:
    with engine.connect() as connection:
        accounts = connection.exec_driver_sql(
            """
            SELECT id, email, balance, "withdrawBalance", "totalReplenished",
                   "bonusBalance", "bonusState"
            FROM public.accounts ORDER BY id
            """
        ).mappings().all()
        services = connection.exec_driver_sql(
            """
            SELECT id, name, "ownerId", "paymentTerm", "autoProlong", "createdAt",
                   "expiresAt", status, price
            FROM public.services ORDER BY id
            """
        ).mappings().all()
        transactions = connection.exec_driver_sql(
            """
            SELECT id, amount, status, "performedAt", "createdAt", type, "serviceId"
            FROM public.transactions ORDER BY id
            """
        ).mappings().all()
        meta = connection.exec_driver_sql(
            "SELECT captured_at FROM app.source_meta WHERE id = 1"
        ).first()

    payload = {
        "capturedAt": meta[0] if meta else None,
        "accounts": [dict(row) for row in accounts],
        "services": [dict(row) for row in services],
        "transactions": [dict(row) for row in transactions],
    }
    return SnapshotInput.model_validate(payload)

