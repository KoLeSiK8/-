from ..context import ScoringContext
from ..registry import Feature, FeatureResult, register_feature


@register_feature
class FundsDeficit(Feature):
    key = "funds_deficit"
    title = "Дефицит средств"
    scope = "account"
    default_weight = 25

    def compute(self, ctx: ScoringContext) -> FeatureResult:
        if ctx.daily_burn <= 0:
            return FeatureResult(False)
        runway = ctx.available / ctx.daily_burn
        value = 1 - min(1.0, runway / ctx.horizon_days)
        return FeatureResult(
            True,
            value,
            f"Средств хватит примерно на {runway:.1f} суток при текущих расходах.",
        )