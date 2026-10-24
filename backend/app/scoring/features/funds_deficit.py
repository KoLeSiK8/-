from ..context import ScoringContext, format_eur, format_number
from ..registry import Feature, FeatureResult, register_feature


@register_feature
class FundsDeficit(Feature):
    key = "funds_deficit"
    title = "Дефицит средств"
    description = (
        "На сколько дней хватит доступных средств при текущих расходах на живые услуги. "
        "Значение 1 − min(1, запас_дней / горизонт)."
    )
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
            f"Доступно {format_eur(ctx.available)}, расход {format_eur(round(ctx.daily_burn))} "
            f"в сутки: средств хватит примерно на {format_number(runway)} суток.",
        )
