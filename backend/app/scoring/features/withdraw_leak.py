from ..context import ScoringContext, format_eur
from ..registry import Feature, FeatureResult, register_feature


@register_feature
class WithdrawLeak(Feature):
    key = "withdraw_leak"
    title = "Доля средств на вывод"
    description = (
        "withdrawBalance / balance: какую часть баланса клиент может вывести. "
        "Большая доля говорит о том, что деньги могут уйти с платформы."
    )
    scope = "account"
    default_weight = 5

    def compute(self, ctx: ScoringContext) -> FeatureResult:
        if ctx.account.balance <= 0:
            return FeatureResult(False)
        value = max(0.0, min(1.0, ctx.account.withdraw_balance / ctx.account.balance))
        return FeatureResult(
            True,
            value,
            f"На вывод доступно {format_eur(ctx.account.withdraw_balance)} из "
            f"{format_eur(ctx.account.balance)} баланса.",
        )
