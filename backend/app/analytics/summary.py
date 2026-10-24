from sqlalchemy.engine import Engine

from ..scoring.engine import compute_scoring
from ..scoring.money import compute_money
from ..scoring.recompute import _load_snapshot, load_settings


def build_summary(engine: Engine) -> dict:
    snapshot = _load_snapshot(engine)
    settings, version = load_settings(engine)
    scoring = compute_scoring(snapshot, settings)
    _, money = compute_money(snapshot.accounts, snapshot.services, scoring, settings)
    counts = {level: 0 for level in ("low", "medium", "high", "churned", "no_data")}
    scored_values = []
    for customer in scoring.customers:
        counts[customer.level] += 1
        if customer.score is not None:
            scored_values.append(customer.score)
    with engine.connect() as connection:
        calculated_at = connection.exec_driver_sql(
            "SELECT max(calculated_at) FROM app.customer_scores"
        ).scalar_one()
    return {
        "counts": counts,
        "revenueAtRiskCents": money.revenue_at_risk_cents,
        "expectedLossCents": money.expected_loss_cents,
        "recoverableCents": money.recoverable_cents,
        "lostRevenueMonthlyCents": money.lost_revenue_monthly_cents,
        "hourlyShare": money.hourly_share,
        "averageScore": sum(scored_values) / len(scored_values) if scored_values else None,
        "modelVersion": version,
        "asOf": scoring.as_of,
        "calculatedAt": calculated_at,
    }