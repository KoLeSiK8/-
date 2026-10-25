from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from math import exp

from ..ingestion.schemas import AccountInput, ServiceInput
from .context import LIVE_STATUSES, PERIOD_DAYS
from .engine import ScoringResult
from .settings import ScoringSettings


@dataclass(frozen=True)
class ServiceMoney:
    service_id: int
    value_cents: int
    expected_loss_cents: int


@dataclass(frozen=True)
class CustomerMoney:
    customer_id: int
    services: list[ServiceMoney]


@dataclass(frozen=True)
class MoneySummary:
    revenue_at_risk_cents: int
    expected_loss_cents: int
    recoverable_cents: int
    lost_revenue_monthly_cents: int
    hourly_share: float


def churn_probability(score: float, settings: ScoringSettings) -> float:
    exponent = -settings.churn_curve.k * (score - settings.churn_curve.midpoint)
    return 1 / (1 + exp(exponent))


def service_value_cents(service: ServiceInput, settings: ScoringSettings) -> int:
    amount = (
        Decimal(service.price)
        * Decimal(str(settings.horizon_money_days))
        / Decimal(str(PERIOD_DAYS[service.payment_term]))
    )
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def compute_money(
    accounts: list[AccountInput],
    services: list[ServiceInput],
    scoring: ScoringResult,
    settings: ScoringSettings,
) -> tuple[list[CustomerMoney], MoneySummary]:
    account_by_id = {account.id: account for account in accounts}
    score_by_customer = {item.customer_id: item for item in scoring.customers}
    score_by_service = {item.service_id: item for item in scoring.services}
    services_by_customer: dict[int, list[ServiceInput]] = {}
    for service in services:
        services_by_customer.setdefault(service.owner_id, []).append(service)

    revenue_at_risk = 0
    expected_loss = 0
    hourly_at_risk = 0
    recoverable = 0
    lost_monthly = 0
    customers: list[CustomerMoney] = []

    for customer_id, customer_services in services_by_customer.items():
        customer = score_by_customer[customer_id]
        account = account_by_id[customer_id]
        live_services = [s for s in customer_services if s.status in LIVE_STATUSES]
        live_value = sum(service_value_cents(s, settings) for s in live_services)
        available = account.balance + (
            account.bonus_balance if account.bonus_state == "unlocked" else 0
        )
        coverage = min(1.0, available / live_value) if live_value else 0.0




        expiring_value = sum(
            service_value_cents(service, settings)
            for service in live_services
            if _renewable(service, scoring.as_of, settings.horizon_days)
        )
        recoverable += max(0, expiring_value - available)

        customer_service_money = []
        for service in live_services:
            value = service_value_cents(service, settings)
            service_score = score_by_service.get(service.id)
            service_expected_loss = 0
            if service_score and service_score.score is not None:
                probability = churn_probability(service_score.score, settings)
                shield = Decimal(1) - Decimal(str(settings.balance_shield * coverage))
                service_expected_loss = _to_cents(
                    Decimal(value) * Decimal(str(probability)) * shield
                )
                expected_loss += service_expected_loss
            if customer.level in {"medium", "high"}:
                revenue_at_risk += value
                if service.payment_term == "hour":
                    hourly_at_risk += value
            customer_service_money.append(
                ServiceMoney(service.id, value, service_expected_loss)
            )

        if customer.level == "churned":
            for service in customer_services:
                if service.status in {"deleted", "blocked"}:
                    lost_monthly += _to_cents(
                        Decimal(service.price)
                        * Decimal(30)
                        / Decimal(str(PERIOD_DAYS[service.payment_term]))
                    )
        customers.append(CustomerMoney(customer_id, customer_service_money))

    summary = MoneySummary(
        revenue_at_risk_cents=revenue_at_risk,
        expected_loss_cents=expected_loss,
        recoverable_cents=recoverable,
        lost_revenue_monthly_cents=lost_monthly,
        hourly_share=hourly_at_risk / revenue_at_risk if revenue_at_risk else 0.0,
    )
    return customers, summary


PROLONG_WAIT_GRACE_DAYS = 5


def _renewable(service: ServiceInput, as_of, horizon_days: float) -> bool:
    days_left = (service.expires_at - as_of).total_seconds() / 86400
    if service.status == "prolong_wait":
        return -PROLONG_WAIT_GRACE_DAYS <= days_left <= horizon_days
    return 0 <= days_left <= horizon_days


def _to_cents(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))