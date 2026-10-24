from ..context import ScoringContext
from ..registry import Feature, FeatureResult, register_feature


@register_feature
class ProlongWaitState(Feature):
    key = "prolong_wait_state"
    title = "Ожидание продления"
    scope = "service"
    default_weight = 25

    def compute(self, ctx: ScoringContext) -> FeatureResult:
        if ctx.service.status != "prolong_wait":
            return FeatureResult(False)
        if ctx.available < ctx.service.price:
            value = 1.0
        else:
            elapsed = max(0.0, min(1.0, -ctx.days_left / 5))
            value = 0.6 + 0.4 * elapsed
        return FeatureResult(
            True,
            value,
            f"Услуга {ctx.service.name} ожидает продления; доступно средств: "
            f"{ctx.available}, цена: {ctx.service.price}.",
        )