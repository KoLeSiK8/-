from datetime import datetime, timedelta, timezone
from typing import Any

from .schemas import SnapshotInput


def snapshot_as_of(snapshot: SnapshotInput) -> datetime:
    if snapshot.captured_at is not None:
        return snapshot.captured_at

    timestamps = [service.created_at for service in snapshot.services]
    for transaction in snapshot.transactions:
        timestamps.append(transaction.created_at)
        if transaction.performed_at is not None:
            timestamps.append(transaction.performed_at)
    return max(timestamps, default=datetime.now(timezone.utc))


def find_quality_warnings(snapshot: SnapshotInput) -> list[dict[str, Any]]:
    as_of = snapshot_as_of(snapshot)
    accounts = {account.id: account for account in snapshot.accounts}
    warnings: list[dict[str, Any]] = []

    for service in snapshot.services:
        if (
            service.status == "prolong_wait"
            and as_of - service.expires_at > timedelta(days=5)
        ):
            warnings.append(_warning(
                service.id,
                service.owner_id,
                "prolong_wait_overdue",
                "Услуга prolong_wait находится в этом статусе более 5 суток.",
            ))

        if service.status in {"active", "suspended"} and service.expires_at < as_of:
            warnings.append(_warning(
                service.id,
                service.owner_id,
                "expired_live_service",
                "Активная или приостановленная услуга уже истекла.",
            ))

        if service.status == "prolong_wait" and service.auto_prolong:
            account = accounts[service.owner_id]
            available = account.balance + (
                account.bonus_balance if account.bonus_state == "unlocked" else 0
            )
            if available >= service.price:
                warnings.append(_warning(
                    service.id,
                    service.owner_id,
                    "prolong_wait_funded_autoprolong",
                    "Автопродление ожидает оплаты, хотя на счёте достаточно средств.",
                ))

    return warnings


def _warning(service_id: int, customer_id: int, code: str, message: str) -> dict[str, Any]:
    return {
        "serviceId": service_id,
        "customerId": customer_id,
        "code": code,
        "message": message,
    }