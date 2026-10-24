# Как добавить признак риска

Признак — это один Python-файл в `backend/app/scoring/features/`. Все модули этой папки подключаются автоматически, поэтому больше ничего регистрировать не нужно: вес, название и описание сами появятся в `GET /api/v1/model/settings`, в форме на вкладке «Модель», в расчёте score и в карточке клиента.

## 1. Создайте файл

Пример: признак «почасовая услуга без запаса» — почасовая услуга, на которую денег хватит меньше чем на сутки.

`backend/app/scoring/features/hourly_low_balance.py`:

```python
from ..context import ScoringContext, format_eur
from ..registry import Feature, FeatureResult, register_feature


@register_feature
class HourlyLowBalance(Feature):
    key = "hourly_low_balance"
    title = "Почасовая услуга без запаса"
    description = (
        "Почасовая услуга, на которую доступных средств хватит меньше чем на сутки. "
        "Значение 1 − min(1, доступно / (цена × 24))."
    )
    scope = "service"
    default_weight = 15

    def compute(self, ctx: ScoringContext) -> FeatureResult:
        if ctx.service.payment_term != "hour" or ctx.service.status not in {"active", "suspended"}:
            return FeatureResult(False)
        day_cost = ctx.service.price * 24
        if day_cost <= 0:
            return FeatureResult(False)
        value = 1 - min(1.0, ctx.available / day_cost)
        return FeatureResult(
            True,
            value,
            f"Почасовая услуга {ctx.service.name} стоит {format_eur(day_cost)} в сутки, "
            f"доступно {format_eur(ctx.available)}.",
        )
```

Что обязательно:

| Поле | Смысл |
|---|---|
| `key` | Уникальный ключ латиницей; по нему хранится вес в настройках |
| `title` | Короткое название для интерфейса |
| `description` | Как считается значение, простыми словами — показывается под слайдером веса |
| `scope` | `service` — свойство услуги, `account` — свойство всего аккаунта (применяется к каждой живой услуге) |
| `default_weight` | Вес по умолчанию, 0…100 |
| `compute(ctx)` | Возвращает `FeatureResult(applicable, value, explanation)` |

Правила для `compute`:

- `FeatureResult(False)` — признак к этой услуге не относится и не участвует в среднем (не путайте с `value = 0`: применимый признак со значением 0 снижает score).
- `value` — число от 0 до 1; выход за границы обрезается.
- `explanation` — законченная фраза для пользователя. Деньги в данных хранятся в центах: выводите их через `format_eur(cents)`, дробные числа — через `format_number(x)`.
- В `ctx` доступны `account`, `service`, все `services` аккаунта, `transactions`, `as_of`, `horizon_days`, а также готовые `available`, `days_left`, `daily_burn`, `account_transactions`.

## 2. Добавьте тест

`backend/tests/scoring/test_engine.py` уже содержит помощник `feature_value`:

```python
def test_hourly_low_balance(snapshot: SnapshotInput) -> None:
    # service-0001: почасовая, 0,95 €/час = 22,80 €/сутки, у клиента 838,10 € — запас есть
    assert feature_value(snapshot, 1, "hourly_low_balance") == 0
```

Новый признак с ненулевым весом меняет знаменатель `Σwᵢ`, поэтому эталонные значения в `test_official_snapshot_golden_scores_and_special_states` и `test_money_formulas_match_official_golden_values` нужно пересчитать (или выставить новому признаку вес 0 в этих тестах).

## 3. Перезапустите API

```bash
docker compose up -d --build api
make test-docker
```

Пересборка нужна, потому что код признаков копируется в образ. Сохранённые настройки не ломаются: вес нового признака берётся из `default_weight`, пока его не поменяют в интерфейсе. Если признак позже удалить, его вес просто пропадёт из настроек.

## Что вы увидите

- **Модель**: новая карточка «Почасовая услуга без запаса» с меткой «УСЛУГА», описанием и слайдером на 15.
- **Клиенты** (демо-набор): у клиента 147 почасовая услуга `demo-service-00358` (3,78 €/час при 4,81 € на счёте) получает значение 0,95 и вклад около 15 баллов. В карточке клиента появится полоса «Почасовая услуга без запаса» и фраза «Почасовая услуга demo-service-00358 стоит 90,72 € в сутки, доступно 4,81 €.»
- **Дашборд и `/metrics`** пересчитаются автоматически после старта API.

Чтобы быстро проверить вклад без интерфейса:

```bash
curl -b cookies.txt http://localhost:8081/api/v1/customers/147 | jq '.services[].featureContributions[] | select(.key=="hourly_low_balance")'
```
