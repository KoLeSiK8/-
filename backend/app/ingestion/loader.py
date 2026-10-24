from datetime import datetime, timezone

from psycopg.types.json import Jsonb
from sqlalchemy.engine import Engine

from .quality import find_quality_warnings
from .schemas import SnapshotInput
from ..scoring.recompute import recompute


def load_snapshot(engine: Engine, snapshot: SnapshotInput) -> dict[str, int]:
    data_warnings = find_quality_warnings(snapshot)
    connection = engine.raw_connection()
    try:
        connection.autocommit = False
        with connection.cursor() as cursor:
            cursor.execute('SELECT id, status FROM public.services')
            previous_statuses = {service_id: status for service_id, status in cursor.fetchall()}

            changed_at = snapshot.captured_at or datetime.now(timezone.utc)
            status_events = [
                (service.id, previous_statuses[service.id], service.status, changed_at)
                for service in snapshot.services
                if service.id in previous_statuses
                and previous_statuses[service.id] != service.status
            ]
            if status_events:
                cursor.executemany(
                    """
                    INSERT INTO app.service_status_events
                        (service_id, old_status, new_status, changed_at)
                    VALUES (%s, %s, %s, %s)
                    """,
                    status_events,
                )

            cursor.execute('DELETE FROM public.transactions')
            cursor.execute('DELETE FROM public.services')
            cursor.execute('DELETE FROM public.accounts')

            if snapshot.accounts:
                cursor.executemany(
                    """
                    INSERT INTO public.accounts
                        (id, email, balance, "withdrawBalance", "totalReplenished",
                         "bonusBalance", "bonusState")
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
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
                cursor.executemany(
                    """
                    INSERT INTO public.services
                        (id, name, "ownerId", "paymentTerm", "autoProlong", "createdAt",
                         "expiresAt", status, price)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
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
                cursor.executemany(
                    """
                    INSERT INTO public.transactions
                        (id, amount, status, "performedAt", "createdAt", type, "serviceId")
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
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