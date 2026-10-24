from ..context import ScoringContext
from ..registry import Feature, FeatureResult, register_feature


@register_feature
class UnperformedTxShare(Feature):
    key = "unperformed_tx_share"
    title = "Невыполненные операции"
    description = (
        "Доля транзакций аккаунта в статусе not_performed. Данные синтетические, "
        "поэтому вес по умолчанию низкий."
    )
    scope = "account"
    default_weight = 5

    def compute(self, ctx: ScoringContext) -> FeatureResult:
        transactions = ctx.account_transactions
        if not transactions:
            return FeatureResult(False)
        count = sum(tx.status == "not_performed" for tx in transactions)
        value = count / len(transactions)
        return FeatureResult(
            True,
            value,
            f"Не выполнено {count} из {len(transactions)} операций.",
        )
