from typing import Any

from sqlalchemy.engine import Engine

LEVELS = ("low", "medium", "high", "churned", "no_data")


def build_summary(engine: Engine) -> dict[str, Any]:

    with engine.connect() as connection:
        level_rows = connection.exec_driver_sql(
            """
            SELECT level, count(*)
            FROM app.customer_scores
            GROUP BY level
            """
        ).all()
        average_score = connection.exec_driver_sql(
            "SELECT avg(score) FROM app.customer_scores WHERE score IS NOT NULL"
        ).scalar_one()
        stored = connection.exec_driver_sql(
            """
            SELECT model_version, as_of, calculated_at, revenue_at_risk_cents,
                   expected_loss_cents, recoverable_cents, lost_revenue_monthly_cents,
                   hourly_share
            FROM app.score_summary
            WHERE id = 1
            """
        ).mappings().first()
        if stored is None:
            version = connection.exec_driver_sql(
                "SELECT version FROM app.model_settings WHERE id = 1"
            ).scalar()

    counts = {level: 0 for level in LEVELS}
    for level, count in level_rows:
        counts[level] = count

    if stored is None:
        return {
            "counts": counts,
            "revenueAtRiskCents": 0,
            "expectedLossCents": 0,
            "recoverableCents": 0,
            "lostRevenueMonthlyCents": 0,
            "hourlyShare": 0.0,
            "averageScore": None,
            "modelVersion": version or 1,
            "asOf": None,
            "calculatedAt": None,
        }

    return {
        "counts": counts,
        "revenueAtRiskCents": stored["revenue_at_risk_cents"],
        "expectedLossCents": stored["expected_loss_cents"],
        "recoverableCents": stored["recoverable_cents"],
        "lostRevenueMonthlyCents": stored["lost_revenue_monthly_cents"],
        "hourlyShare": stored["hourly_share"],
        "averageScore": float(average_score) if average_score is not None else None,
        "modelVersion": stored["model_version"],
        "asOf": stored["as_of"],
        "calculatedAt": stored["calculated_at"],
    }
