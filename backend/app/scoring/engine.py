from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from ..ingestion.quality import snapshot_as_of
from ..ingestion.schemas import ServiceInput, SnapshotInput
from .context import LIVE_STATUSES, ScoringContext
from .registry import FEATURES, Feature, load_features
from .settings import ScoringSettings

load_features()


@dataclass(frozen=True)
class ServiceScore:
    service_id: int
    customer_id: int
    score: float | None
    contributions: list[dict[str, Any]]


@dataclass(frozen=True)
class CustomerScore:
    customer_id: int
    score: float | None
    level: str
    loyalty: float | None
    reasons: list[dict[str, Any]]


@dataclass(frozen=True)
class ScoringResult:
    as_of: datetime
    customers: list[CustomerScore]
    services: list[ServiceScore]


def resolve_as_of(snapshot: SnapshotInput, settings: ScoringSettings) -> datetime:
    if settings.as_of_mode == "now":
        return datetime.now(timezone.utc)
    if settings.as_of_mode == "fixed":
        if settings.as_of_fixed is None:
            raise ValueError("as_of_fixed is required when as_of_mode is fixed")
        return settings.as_of_fixed
    return snapshot_as_of(snapshot)


def compute_scoring(
    snapshot: SnapshotInput, settings: ScoringSettings | None = None
) -> ScoringResult:
    active_settings = settings or ScoringSettings()
    as_of = resolve_as_of(snapshot, active_settings)
    accounts = {account.id: account for account in snapshot.accounts}
    services_by_owner: dict[int, list[ServiceInput]] = {}
    owner_by_service: dict[int, int] = {}
    for service in snapshot.services:
        services_by_owner.setdefault(service.owner_id, []).append(service)
        owner_by_service[service.id] = service.owner_id


    transactions_by_owner: dict[int, list] = {}
    for transaction in snapshot.transactions:
        owner_id = owner_by_service.get(transaction.service_id)
        if owner_id is not None:
            transactions_by_owner.setdefault(owner_id, []).append(transaction)

    service_scores: list[ServiceScore] = []
    customer_scores: list[CustomerScore] = []
    for account in snapshot.accounts:
        customer_services = services_by_owner.get(account.id, [])
        live_services = [
            service for service in customer_services if service.status in LIVE_STATUSES
        ]
        if not customer_services:
            customer_scores.append(_special_customer(account.id, "no_data"))
            continue
        if not live_services:
            state = "churned" if any(
                service.status in {"deleted", "blocked"} for service in customer_services
            ) else "no_data"
            customer_scores.append(_special_customer(account.id, state))
            continue

        scored_services = []
        for service in live_services:
            ctx = ScoringContext(
                account=accounts[service.owner_id],
                service=service,
                services=customer_services,
                transactions=transactions_by_owner.get(account.id, []),
                as_of=as_of,
                horizon_days=active_settings.horizon_days,
                suspended_value=active_settings.suspended_value,
            )
            score = score_service(ctx, active_settings)
            service_scores.append(score)
            if score.score is not None:
                scored_services.append(score)

        if not scored_services:
            customer_scores.append(_special_customer(account.id, "no_data"))
            continue

        service_values = [score.score for score in scored_services if score.score is not None]
        max_score = max(service_values)
        customer_score = (
            active_settings.alpha_max_mean * max_score
            + (1 - active_settings.alpha_max_mean) * mean(service_values)
        )
        level = _risk_level(customer_score, active_settings)
        riskiest = max(scored_services, key=lambda score: score.score or 0)
        reasons = sorted(
            (
                item
                for item in riskiest.contributions
                if item["weightedContribution"] > 0
            ),
            key=lambda item: item["weightedContribution"],
            reverse=True,
        )[:3]
        customer_scores.append(
            CustomerScore(
                customer_id=account.id,
                score=customer_score,
                level=level,
                loyalty=100 - customer_score,
                reasons=reasons,
            )
        )

    return ScoringResult(as_of, customer_scores, service_scores)


def score_service(ctx: ScoringContext, settings: ScoringSettings) -> ServiceScore:
    contributions: list[dict[str, Any]] = []
    weighted_total = 0.0
    weight_total = 0.0
    for key, feature_class in FEATURES.items():
        feature: Feature = feature_class()
        result = feature.compute(ctx)
        if not result.applicable:
            continue
        value = max(0.0, min(1.0, result.value))
        weight = settings.weights.get(key, feature.default_weight)
        if weight <= 0:
            continue
        weighted_contribution = weight * value
        weighted_total += weighted_contribution
        weight_total += weight
        contributions.append(
            {
                "key": key,
                "title": feature.title,
                "scope": feature.scope,
                "value": value,
                "weight": weight,
                "weightedContribution": weighted_contribution,
                "scoreContribution": 100 * weighted_contribution,
                "explanation": result.explanation,
            }
        )
    score = 100 * weighted_total / weight_total if weight_total else None
    if weight_total:
        for contribution in contributions:
            contribution["scoreContribution"] /= weight_total
    return ServiceScore(ctx.service.id, ctx.account.id, score, contributions)


def _risk_level(score: float, settings: ScoringSettings) -> str:
    if score < settings.thresholds.low:
        return "low"
    if score < settings.thresholds.high:
        return "medium"
    return "high"


def _special_customer(customer_id: int, level: str) -> CustomerScore:
    return CustomerScore(customer_id, None, level, None, [])