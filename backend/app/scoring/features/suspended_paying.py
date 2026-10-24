from ..context import ScoringContext
from ..registry import Feature, FeatureResult, register_feature


@register_feature
class SuspendedPaying(Feature):
    key = "suspended_paying"
    title = "Приостановленная услуга"
    description = (
        "Услуга приостановлена, но остаётся у клиента. Значение задаётся настройкой "
        "suspended_value (по умолчанию 0,4)."
    )
    scope = "service"
    default_weight = 5

    def compute(self, ctx: ScoringContext) -> FeatureResult:
        if ctx.service.status != "suspended":
            return FeatureResult(False)
        value = max(0.0, min(1.0, ctx.suspended_value))
        return FeatureResult(
            True,
            value,
            f"Услуга {ctx.service.name} приостановлена, но продолжает занимать средства.",
        )
