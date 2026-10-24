from ..context import ScoringContext
from ..registry import Feature, FeatureResult, register_feature


@register_feature
class BillingAnomaly(Feature):
    key = "billing_anomaly"
    title = "Аномалия продления"
    description = (
        "Услуга ждёт продления, хотя автопродление включено и денег хватает: "
        "вероятен сбой биллинга, который раздражает клиента."
    )
    scope = "service"
    default_weight = 10

    def compute(self, ctx: ScoringContext) -> FeatureResult:
        applicable = (
            ctx.service.status == "prolong_wait"
            and ctx.service.auto_prolong
            and ctx.available >= ctx.service.price
        )
        explanation = (
            f"Услуга {ctx.service.name} ожидает продления при включённом автопродлении "
            "и достаточном балансе."
            if applicable
            else ""
        )
        return FeatureResult(applicable, float(applicable), explanation)
