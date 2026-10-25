from dataclasses import dataclass
from datetime import datetime

from ..ingestion.schemas import AccountInput, ServiceInput, TransactionInput

PERIOD_DAYS = {
    "hour": 1 / 24,
    "week": 7,
    "month": 30,
    "quarter_year": 91,
    "half_year": 182,
    "year": 365,
}
LIVE_STATUSES = {"active", "suspended", "prolong_wait"}


def format_number(value: float, digits: int = 1) -> str:

    text = f"{value:,.{digits}f}"
    return text.replace(",", "\u00a0").replace(".", ",")


def format_eur(cents: int) -> str:
    return f"{format_number(cents / 100, 2)}\u00a0€"


@dataclass(frozen=True)
class ScoringContext:
    account: AccountInput
    service: ServiceInput
    services: list[ServiceInput]
    transactions: list[TransactionInput]
    as_of: datetime
    horizon_days: float
    suspended_value: float

    @property
    def available(self) -> int:
        bonus = self.account.bonus_balance if self.account.bonus_state == "unlocked" else 0
        return self.account.balance + bonus

    @property
    def days_left(self) -> float:
        return (self.service.expires_at - self.as_of).total_seconds() / 86400

    @property
    def daily_burn(self) -> float:
        return sum(
            service.price / PERIOD_DAYS[service.payment_term]
            for service in self.services
            if service.status in LIVE_STATUSES
        )

    @property
    def account_transactions(self) -> list[TransactionInput]:
        service_ids = {service.id for service in self.services}
        return [tx for tx in self.transactions if tx.service_id in service_ids]