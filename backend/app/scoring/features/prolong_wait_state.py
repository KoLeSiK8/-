from ..context import ScoringContext, format_eur, format_number
from ..registry import Feature, FeatureResult, register_feature


@register_feature
class ProlongWaitState(Feature):
    key = "prolong_wait_state"
    title = "Ожидание продления"
    description = (
        "Услуга в статусе prolong_wait. Если денег на продление нет, значение 1; "
        "если есть, 0,6 и растёт до 1 за 5 суток ожидания."
    )
    scope = "service"
    default_weight = 25

    def compute(self, ctx: ScoringContext) -> FeatureResult:
        if ctx.service.status != "prolong_wait":
            return FeatureResult(False)
        waited = max(0.0, -ctx.days_left)
        if ctx.available < ctx.service.price:
            value = 1.0
            explanation = (
                f"Услуга {ctx.service.name} ждёт продления {format_number(waited)} суток, "
                f"денег не хватает: доступно {format_eur(ctx.available)}, "
                f"цена {format_eur(ctx.service.price)}."
            )
        else:
            elapsed = max(0.0, min(1.0, waited / 5))
            value = 0.6 + 0.4 * elapsed
            explanation = (
                f"Услуга {ctx.service.name} ждёт продления {format_number(waited)} суток, "
                f"хотя доступно {format_eur(ctx.available)} при цене "
                f"{format_eur(ctx.service.price)}."
            )
        return FeatureResult(True, value, explanation)
