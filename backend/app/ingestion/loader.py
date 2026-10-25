from datetime import datetime, timezone
from math import floor

from psycopg.types.json import Jsonb
from sqlalchemy.engine import Engine

from ..db_copy import copy_rows

from .quality import find_quality_warnings
from .schemas import SnapshotInput
from ..scoring.lock import RECOMPUTE_LOCK
from ..scoring.recompute import recompute


def load_snapshot(engine: Engine, snapshot: SnapshotInput) -> dict[str, int]:

    with RECOMPUTE_LOCK:
        return _load_snapshot(engine, snapshot)


def _service_identity(owner_id: int, name: str, created_at: datetime) -> tuple:

    return owner_id, name, floor(created_at.timestamp() * 1000 + 0.5)


def _load_snapshot(engine: Engine, snapshot: SnapshotInput) -> dict[str, int]:
    data_warnings = find_quality_warnings(snapshot)
    connection = engine.raw_connection()
    try:
        connection.autocommit = False
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT id, "ownerId", name, "createdAt", status FROM public.services'
            )
            previous = {
                service_id: (_service_identity(owner_id, name, created_at), status)
                for service_id, owner_id, name, created_at, status in cursor.fetchall()
            }

            changed_at = snapshot.captured_at or datetime.now(timezone.utc)
            status_events = []
            for service in snapshot.services:
                if service.id not in previous:
                    continue
                identity, old_status = previous[service.id]
                same_service = identity == _service_identity(
                    service.owner_id, service.name, service.created_at
                )
                if same_service and old_status != service.status:
                    status_events.append(
                        (service.id, old_status, service.status, changed_at)
                    )
            if status_events:
                copy_rows(
                    cursor,
                    "app.service_status_events (service_id, old_status, new_status, changed_at)",
                    status_events,
                )

            cursor.execute('DELETE FROM public.transactions')
            cursor.execute('DELETE FROM public.services')
            cursor.execute('DELETE FROM public.accounts')

            if snapshot.accounts:
                copy_rows(
                    cursor,
                    'public.accounts (id, email, balance, "withdrawBalance", "totalReplenished", "bonusBalance", "bonusState")',
                    [
                        (
                            account.id,
                            account.email,
                            account.balance,
                            account.withdraw_balance,
                            account.total_replenished,
                            account.bonus_balance,
                            account.bonus_state,
                        )
                        for account in snapshot.accounts
                    ],
                )

            if snapshot.services:
                copy_rows(
                    cursor,
                    'public.services (id, name, "ownerId", "paymentTerm", "autoProlong", "createdAt", "expiresAt", status, price)',
                    [
                        (
                            service.id,
                            service.name,
                            service.owner_id,
                            service.payment_term,
                            service.auto_prolong,
                            service.created_at,
                            service.expires_at,
                            service.status,
                            service.price,
                        )
                        for service in snapshot.services
                    ],
                )

            if snapshot.transactions:
                copy_rows(
                    cursor,
                    'public.transactions (id, amount, status, "performedAt", "createdAt", type, "serviceId")',
                    [
                        (
                            transaction.id,
                            transaction.amount,
                            transaction.status,
                            transaction.performed_at,
                            transaction.created_at,
                            transaction.type,
                            transaction.service_id,
                        )
                        for transaction in snapshot.transactions
                    ],
                )

            for table in ("accounts", "services", "transactions"):
                cursor.execute(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence('public.{table}', 'id'),
                        COALESCE((SELECT MAX(id) FROM public.{table}), 1),
                        EXISTS (SELECT 1 FROM public.{table})
                    )
                    """
                )

            cursor.execute(
                """
                INSERT INTO app.source_meta
                    (id, captured_at, loaded_at, account_count, service_count,
                     transaction_count, data_warnings)
                VALUES (1, %s, now(), %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    captured_at = EXCLUDED.captured_at,
                    loaded_at = EXCLUDED.loaded_at,
                    account_count = EXCLUDED.account_count,
                    service_count = EXCLUDED.service_count,
                    transaction_count = EXCLUDED.transaction_count,
                    data_warnings = EXCLUDED.data_warnings
                """,
                (
                    snapshot.captured_at,
                    len(snapshot.accounts),
                    len(snapshot.services),
                    len(snapshot.transactions),
                    Jsonb(data_warnings),
                ),
            )
        recomputed = recompute(engine, snapshot=snapshot, connection=connection)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return {
        "accounts": len(snapshot.accounts),
        "services": len(snapshot.services),
        "transactions": len(snapshot.transactions),
        "changedStatuses": len(status_events),
        "modelVersion": recomputed["modelVersion"],
    }