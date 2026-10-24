import secrets

from fastapi import APIRouter, Header, HTTPException, Request, status
from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.core import GaugeMetricFamily
from starlette.responses import Response

from ..analytics.summary import build_summary
from ..auth.deps import require_user
from ..config import settings


class SummaryCollector:
    def __init__(self, request: Request) -> None:
        self._request = request

    def collect(self):
        summary = build_summary(self._request.app.state.engine)
        customers = GaugeMetricFamily(
            "churn_customers", "Число клиентов по уровню риска", labels=["level"]
        )
        for level, count in summary["counts"].items():
            customers.add_metric([level], count)
        yield customers

        metric_values = (
            ("churn_revenue_at_risk_eur", "Выручка под риском в EUR", "revenueAtRiskCents"),
            ("churn_expected_loss_eur", "Ожидаемые потери в EUR", "expectedLossCents"),
            ("churn_recoverable_eur", "Устранимая часть в EUR", "recoverableCents"),
            (
                "churn_lost_revenue_monthly_eur",
                "Потерянная месячная выручка в EUR",
                "lostRevenueMonthlyCents",
            ),
        )
        for name, description, key in metric_values:
            metric = GaugeMetricFamily(name, description)
            metric.add_metric([], summary[key] / 100)
            yield metric

        average = GaugeMetricFamily("churn_score_avg", "Средний score клиентов с оценкой")
        average.add_metric([], summary["averageScore"] or 0)
        yield average

        version = GaugeMetricFamily("churn_model_version", "Версия модели")
        version.add_metric([], summary["modelVersion"])
        yield version

        calculated_at = summary["calculatedAt"]
        timestamp = calculated_at.timestamp() if calculated_at else 0
        last_recalc = GaugeMetricFamily(
            "churn_last_recalc_timestamp_seconds", "Время последнего пересчёта Unix timestamp"
        )
        last_recalc.add_metric([], timestamp)
        yield last_recalc


router = APIRouter()


def _authorize_metrics(request: Request, authorization: str | None) -> None:
    if authorization and authorization.startswith("Bearer "):
        supplied = authorization.removeprefix("Bearer ")
        if settings.metrics_token and secrets.compare_digest(supplied, settings.metrics_token):
            return
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    require_user(request)


def _metrics_response(request: Request, authorization: str | None) -> Response:
    _authorize_metrics(request, authorization)
    registry = CollectorRegistry()
    registry.register(SummaryCollector(request))
    return Response(
        generate_latest(registry),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("/metrics", operation_id="getMetrics", summary="Метрики Prometheus (сессия или Bearer METRICS_TOKEN)")
def get_metrics(
    request: Request,
    authorization: str | None = Header(default=None),
) -> Response:
    return _metrics_response(request, authorization)


@router.get("/metics", operation_id="getMetricsTypoAlias", summary="Алиас /metrics (написание из ТЗ)")
def get_metrics_alias(
    request: Request,
    authorization: str | None = Header(default=None),
) -> Response:
    return _metrics_response(request, authorization)