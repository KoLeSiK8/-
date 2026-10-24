from ..context import ScoringContext, format_number
from ..registry import Feature, FeatureResult, register_feature


@register_feature
class AutoprolongOffNearExpiry(Feature):
    key = "autoprolong_off_near_expiry"
    title = "Автопродление выключено"
    description = (
        "1, если у активной или приостановленной услуги выключено автопродление "
        "и до окончания осталось не больше горизонта оценки; иначе 0."
    )
    scope = "service"
    default_weight = 25

    def compute(self, ctx: ScoringContext) -> FeatureResult:
        if ctx.service.status not in {"active", "suspended"}:
            return FeatureResult(False)
        value = float(not ctx.service.auto_prolong and ctx.days_left <= ctx.horizon_days)
        if not value:
            explanation = (
                f"Для услуги {ctx.service.name} автопродление включено или срок не близок."
            )
        elif ctx.days_left < 0:
            explanation = (
                f"Автопродление выключено, услуга {ctx.service.name} истекла "
                f"{format_number(-ctx.days_left)} суток назад."
            )
        else:
            explanation = (
                f"Автопродление выключено, услуга {ctx.service.name} истекает через "
                f"{format_number(ctx.days_left)} суток."
            )
        return FeatureResult(True, value, explanation)
