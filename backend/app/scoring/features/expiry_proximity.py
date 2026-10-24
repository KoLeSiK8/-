from ..context import ScoringContext, format_number
from ..registry import Feature, FeatureResult, register_feature


@register_feature
class ExpiryProximity(Feature):
    key = "expiry_proximity"
    title = "Близость окончания услуги"
    description = (
        "Чем ближе окончание услуги, тем выше значение: 1 − дней_до_окончания / горизонт, "
        "в пределах 0…1; для уже истёкшей услуги 1."
    )
    scope = "service"
    default_weight = 20

    def compute(self, ctx: ScoringContext) -> FeatureResult:
        if ctx.service.status not in {"active", "suspended"}:
            return FeatureResult(False)
        value = 1.0 if ctx.days_left < 0 else max(
            0.0, min(1.0, 1 - ctx.days_left / ctx.horizon_days)
        )
        explanation = (
            f"Услуга {ctx.service.name} истекла {format_number(-ctx.days_left)} суток назад."
            if ctx.days_left < 0
            else f"Услуга {ctx.service.name} истекает через "
            f"{format_number(ctx.days_left)} суток."
        )
        return FeatureResult(True, value, explanation)
