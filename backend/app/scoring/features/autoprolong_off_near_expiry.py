from ..context import ScoringContext
from ..registry import Feature, FeatureResult, register_feature


@register_feature
class AutoprolongOffNearExpiry(Feature):
    key = "autoprolong_off_near_expiry"
    title = "Автопродление выключено"
    scope = "service"
    default_weight = 25

    def compute(self, ctx: ScoringContext) -> FeatureResult:
        if ctx.service.status not in {"active", "suspended"}:
            return FeatureResult(False)
        value = float(not ctx.service.auto_prolong and ctx.days_left <= ctx.horizon_days)
        explanation = (
            f"Автопродление выключено, услуга {ctx.service.name} истекает через "
            f"{ctx.days_left:.1f} суток."
            if value
            else f"Для услуги {ctx.service.name} автопродление включено или срок не близок."
        )
        return FeatureResult(True, value, explanation)