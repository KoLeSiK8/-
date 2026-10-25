from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictInt, model_validator


def ensure_utc(value: datetime | None) -> datetime | None:

    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


UtcDatetime = Annotated[datetime, AfterValidator(ensure_utc)]


PaymentTerm = Literal["hour", "week", "month", "quarter_year", "half_year", "year"]
ServiceStatus = Literal["active", "blocked", "deleted", "suspended", "prolong_wait"]
TransactionStatus = Literal["not_performed", "performed"]


class SnapshotModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AccountInput(SnapshotModel):
    id: StrictInt = Field(ge=1)
    email: str = Field(min_length=1)
    balance: StrictInt = Field(ge=0)
    withdraw_balance: StrictInt = Field(alias="withdrawBalance", ge=0)
    total_replenished: StrictInt = Field(alias="totalReplenished", ge=0)
    bonus_balance: StrictInt = Field(alias="bonusBalance", ge=0)
    bonus_state: Literal["locked", "unlocked"] = Field(alias="bonusState")


class ServiceInput(SnapshotModel):
    id: StrictInt = Field(ge=1)
    name: str = Field(pattern=r"^[A-Za-z0-9-]+$")
    owner_id: StrictInt = Field(alias="ownerId", ge=1)
    payment_term: PaymentTerm = Field(alias="paymentTerm")
    auto_prolong: bool = Field(alias="autoProlong")
    created_at: UtcDatetime = Field(alias="createdAt")
    expires_at: UtcDatetime = Field(alias="expiresAt")
    status: ServiceStatus
    price: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def expires_after_creation(self) -> "ServiceInput":
        if self.expires_at < self.created_at:
            raise ValueError("expiresAt must be greater than or equal to createdAt")
        return self


class TransactionInput(SnapshotModel):
    id: StrictInt = Field(ge=1)
    amount: StrictInt = Field(ge=0, le=1000)
    status: TransactionStatus
    performed_at: UtcDatetime | None = Field(alias="performedAt")
    created_at: UtcDatetime = Field(alias="createdAt")
    type: Literal["prolong", "order"]
    service_id: StrictInt = Field(alias="serviceId", ge=1)

    @model_validator(mode="after")
    def validate_performed_timestamp(self) -> "TransactionInput":
        if self.status == "not_performed" and self.performed_at is not None:
            raise ValueError("performedAt must be null for not_performed transactions")
        if self.status == "performed":
            if self.performed_at is None:
                raise ValueError("performedAt is required for performed transactions")
            if self.performed_at < self.created_at:
                raise ValueError("performedAt must be greater than or equal to createdAt")
        return self


class SnapshotInput(SnapshotModel):
    captured_at: UtcDatetime | None = Field(default=None, alias="capturedAt")
    accounts: list[AccountInput]
    services: list[ServiceInput]
    transactions: list[TransactionInput]

    @model_validator(mode="after")
    def validate_references_and_ids(self) -> "SnapshotInput":
        account_ids = [account.id for account in self.accounts]
        service_ids = [service.id for service in self.services]
        transaction_ids = [transaction.id for transaction in self.transactions]

        if len(account_ids) != len(set(account_ids)):
            raise ValueError("account IDs must be unique")
        if len(service_ids) != len(set(service_ids)):
            raise ValueError("service IDs must be unique")
        if len(transaction_ids) != len(set(transaction_ids)):
            raise ValueError("transaction IDs must be unique")

        known_accounts = set(account_ids)
        known_services = set(service_ids)
        missing_accounts = sorted(
            {service.owner_id for service in self.services} - known_accounts
        )
        missing_services = sorted(
            {transaction.service_id for transaction in self.transactions} - known_services
        )
        if missing_accounts or missing_services:
            problems = []
            if missing_accounts:
                problems.append(f"unknown ownerId values: {missing_accounts}")
            if missing_services:
                problems.append(f"unknown serviceId values: {missing_services}")
            raise ValueError("; ".join(problems))
        return self