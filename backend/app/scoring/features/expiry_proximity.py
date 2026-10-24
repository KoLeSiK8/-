from ..context import ScoringContext
from ..registry import Feature, FeatureResult, register_feature


@register_feature
class ExpiryProximity(Feature):
    key = "expiry_proximity"
    title = "Близость окончания услуги"
    scope = "service"
    default_weight = 20

    def compute(self, ctx: ScoringContext) -> FeatureResult:
        if ctx.service.status not in {"active", "suspended"}:
            return FeatureResult(False)
        value = 1.0 if ctx.days_left < 0 else max(
            0.0, min(1.0, 1 - ctx.days_left / ctx.horizon_days)
        )
        return FeatureResult(
            True,
            value,
            f"Услуга {ctx.service.name} истекает через {ctx.days_left:.1f} суток.",
        )