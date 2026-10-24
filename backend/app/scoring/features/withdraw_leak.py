from ..context import ScoringContext
from ..registry import Feature, FeatureResult, register_feature


@register_feature
class WithdrawLeak(Feature):
    key = "withdraw_leak"
    title = "Доля средств на вывод"
    scope = "account"
    default_weight = 5

    def compute(self, ctx: ScoringContext) -> FeatureResult:
        if ctx.account.balance <= 0:
            return FeatureResult(False)
        value = max(0.0, min(1.0, ctx.account.withdraw_balance / ctx.account.balance))
        return FeatureResult(
            True,
            value,
            f"На вывод доступно {ctx.account.withdraw_balance} из {ctx.account.balance} единиц баланса.",
        )