from ..context import ScoringContext, format_eur
from ..registry import Feature, FeatureResult, register_feature


@register_feature
class BonusDependency(Feature):
    key = "bonus_dependency"
    title = "Зависимость от бонуса"
    description = (
        "Доля разблокированного бонуса в доступных средствах: bonusBalance / "
        "(balance + bonusBalance). Когда бонус закончится, клиенту придётся платить самому."
    )
    scope = "account"
    default_weight = 5

    def compute(self, ctx: ScoringContext) -> FeatureResult:
        if ctx.account.bonus_state != "unlocked" or ctx.account.bonus_balance <= 0:
            return FeatureResult(False)
        total = ctx.account.balance + ctx.account.bonus_balance
        value = ctx.account.bonus_balance / total if total else 0.0
        return FeatureResult(
            True,
            value,
            f"Бонус {format_eur(ctx.account.bonus_balance)} составляет {value:.0%} "
            "доступных средств.",
        )
