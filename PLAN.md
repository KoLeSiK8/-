# PLAN.md — Анализатор рисков оттока (инструкция для ИИ-агента)

Ты реализуешь систему целиком. Работай по фазам строго по порядку. Фаза закрыта, только когда выполнен её блок **DoD** (команды из него проходят). Не переходи дальше при красных тестах.

## 0. Правила работы

1. Контракт первым: `openapi.yml` пишется в фазе 0 и обновляется при любом изменении API. В конце он должен совпадать с тем, что отдаёт FastAPI.
2. Результаты нигде не хардкодятся. Всё, что видит пользователь (score, уровни, деньги, метрики, график), считается из данных в БД и текущих настроек.
3. Деньги хранятся и считаются в целых евроцентах (`int`). В EUR (÷100, 2 знака) переводятся только на выходе API и в UI.
4. Единый источник правды: таблицы `app.customer_scores` и `app.service_scores`. `/api/v1/analytics/summary`, `/metrics` и UI читают одну и ту же функцию `build_summary()`.
5. Код на английском, интерфейс и документация на русском.
6. Секретов в репозитории нет, только `.env.example`.
7. Один uvicorn-воркер (in-process шина событий SSE).
8. После каждой фазы делай коммит с понятным сообщением.

## 1. Зафиксированные решения

| Область | Решение |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (sync, psycopg 3), Pydantic v2 |
| БД | PostgreSQL 16 |
| Миграции | Простой раннер: SQL-файлы `backend/migrations/NNN_*.sql`, таблица `app.schema_migrations`. Файл `001_schema.up.sql` из комплекта данных копируется без изменений |
| Frontend | React 18 + Vite + TypeScript, TanStack Query, Recharts, React Router |
| Раздача | nginx: статика SPA, проксирует `/api` и `/metrics` на `api:8000` |
| Auth | Cookie-сессия (HttpOnly, SameSite=Lax), сессии в БД, пароли argon2. Администратор из `ADMIN_LOGIN` / `ADMIN_PASSWORD` создаётся при старте |
| Live | SSE `GET /api/v1/events`, событие `recomputed` |
| Метрики | `prometheus_client`, кастомный collector, считает в момент запроса |
| Тесты | pytest + httpx TestClient + testcontainers или docker-postgres; Playwright для e2e (опционально) |

Публичными остаются только `POST /api/v1/auth/login`, `GET /api/v1/docs`, `GET /api/v1/openapi.json`, `GET /healthz`. Всё остальное требует сессии. Исключение: `/metrics` принимает ещё и `Authorization: Bearer ${METRICS_TOKEN}`. Алиас `/metics` (опечатка из ТЗ) отдаёт то же самое.

## 2. Структура репозитория

```
backend/
  app/
    main.py                # создание app, роутеры, lifespan (миграции, seed, admin)
    config.py              # pydantic-settings из env
    db.py                  # engine, session
    auth/                  # security.py (argon2, сессии), deps.py (require_user), router.py
    ingestion/             # schemas.py (Pydantic под data.json), loader.py, diff.py, quality.py
    scoring/
      context.py           # ScoringContext, as_of, helpers
      registry.py          # @register_feature, FEATURES
      features/            # по одному файлу на признак
      engine.py            # расчёт service/customer score, уровни, причины
      money.py             # P(churn), денежные показатели
      settings.py          # схема настроек, load/save, версия
      recompute.py         # полный пересчёт + запись в БД + публикация события
    analytics/             # summary.py (build_summary), timeline.py
    api/                   # customers.py, analytics.py, model.py, source.py, events.py, metrics.py
    events.py              # in-process шина для SSE
  migrations/              # 001_schema.sql (из комплекта), 010_app_schema.sql
  tests/
frontend/                  # React-приложение
tools/generate_demo.py     # генератор расширенных данных
data/official.json         # исходный data.json из комплекта (не менять)
data/demo.json             # результат generate_demo.py (коммитим)
deploy/prometheus.yml      # опционально
docker-compose.yml  .env.example  openapi.yml  README.md
docs/ model.md  architecture.md  add-feature.md
```

## 3. Контракт данных (вход)

Тело `PUT /api/v1/source/snapshot` повторяет `data.json`:

```json
{ "capturedAt": "2026-10-19T15:00:00.000Z",
  "accounts": [...], "services": [...], "transactions": [...] }
```

`capturedAt` необязателен. Валидация строго по схеме БД:

- accounts: `id`, `email`, `balance`, `withdrawBalance`, `totalReplenished`, `bonusBalance` (int ≥ 0), `bonusState` ∈ {`locked`,`unlocked`}.
- services: `id`, `name` (`^[A-Za-z0-9-]+$`), `ownerId`, `paymentTerm` ∈ {`hour`,`week`,`month`,`quarter_year`,`half_year`,`year`}, `autoProlong` bool, `createdAt`, `expiresAt` (≥ createdAt), `status` ∈ {`active`,`blocked`,`deleted`,`suspended`,`prolong_wait`}, `price` int ≥ 0.
- transactions: `id`, `amount` int 0..1000, `status` ∈ {`not_performed`,`performed`}, `performedAt` (null ⇔ not_performed), `createdAt`, `type` ∈ {`prolong`,`order`}, `serviceId`.

Ссылочная целостность (`ownerId`, `serviceId`) проверяется до записи. Ошибка валидации это 422 со списком проблем, в БД ничего не меняется.

Операция PUT делает в одной транзакции: диф статусов услуг со старым состоянием → запись в `app.service_status_events` → замена данных (DELETE transactions, services, accounts → INSERT с явными id) → пересчёт → коммит → событие SSE.

## 4. Спецификация модели

### 4.1. Контекст

- `as_of` по настройке `as_of_mode`:
  - `snapshot` (по умолчанию): `capturedAt` из последнего PUT, иначе `max(createdAt, performedAt)` по данным;
  - `now`: текущее время;
  - `fixed`: значение `as_of_fixed`.
- Длина периода в сутках: hour = 1/24, week = 7, month = 30, quarter_year = 91, half_year = 182, year = 365.
- Живые услуги: статусы `active`, `suspended`, `prolong_wait`. «Ушедшие»: `deleted`, `blocked`.
- `available` аккаунта = `balance` + (`bonusBalance`, если `bonusState = unlocked`).
- `daily_burn` аккаунта = Σ `price / period_days` по живым услугам.
- `horizon_days` по умолчанию 7 (настройка).

### 4.2. Признаки

Каждый признак это класс: `key`, `title`, `scope` (`service` или `account`), `default_weight`, `compute(ctx) -> FeatureResult(applicable: bool, value: float 0..1, explanation: str)`. Регистрация декоратором `@register_feature`. Вес, название и описание автоматически попадают в `GET /model/settings` и в форму UI.

| key | scope | Применим | Значение v ∈ [0,1] | Вес |
|---|---|---|---|---|
| `expiry_proximity` | service | active, suspended | `clamp(1 − days_left/horizon, 0, 1)`, при `days_left < 0` v = 1 | 20 |
| `autoprolong_off_near_expiry` | service | active, suspended | 1, если `autoProlong = false` и `days_left ≤ horizon`, иначе 0 | 25 |
| `funds_deficit` | account | `daily_burn > 0` | `1 − min(1, runway/horizon)`, где `runway = available / daily_burn` | 25 |
| `prolong_wait_state` | service | prolong_wait | нет средств на цену услуги (`available < price`): 1.0; есть: `0.6 + 0.4 · elapsed`, где `elapsed = clamp((as_of − expiresAt)/5 суток, 0, 1)` | 25 |
| `suspended_paying` | service | suspended | 0.4 (константа, параметр) | 5 |
| `withdraw_leak` | account | `balance > 0` | `withdrawBalance / balance` | 5 |
| `bonus_dependency` | account | `bonusState = unlocked` и `bonusBalance > 0` | `bonusBalance / (balance + bonusBalance)` | 5 |
| `unperformed_tx_share` | account | есть транзакции | доля `not_performed` среди транзакций аккаунта (данные синтетические, вес низкий) | 5 |
| `billing_anomaly` | service | prolong_wait и `autoProlong` и `available ≥ price` | 1 | 10 |

### 4.3. Формулы

```
service_score = 100 · Σ(wᵢ·vᵢ) / Σ(wᵢ)            по применимым признакам (service + account scope)
customer_score = α · max(service_score) + (1−α) · mean(service_score)    α = 0.7 (настройка)
level: score < t_low → low;  t_low ≤ score < t_high → medium;  ≥ t_high → high     t_low=35, t_high=65
loyalty = 100 − score
```

Особые состояния клиента (вместо уровня риска):

- `no_data`: нет услуг, либо у живых услуг нет ни одного применимого признака. `score = null`, в UI «Недостаточно данных для оценки».
- `churned`: нет живых услуг, но есть `deleted`/`blocked`. `score = null`, в UI «Клиент ушёл / неактивен», попадает в список win-back.

Причины: три признака с наибольшим `wᵢ·vᵢ` по самой рисковой услуге. Каждый выдаёт готовую русскоязычную фразу (например: «Автопродление выключено, услуга service-0026 истекает через 6,9 суток»). Хранятся в `reasons` (JSON) вместе с вкладом в баллах.

### 4.4. Качество данных (предупреждения, не влияют на score)

- `prolong_wait` старше 5 суток от `expiresAt` на момент `as_of` (по правилу должен был стать `deleted`);
- `active`/`suspended` с `expiresAt < as_of`;
- `prolong_wait` при `autoProlong` и достаточных средствах.

Предупреждения хранятся в `customer_scores.data_warnings` и показываются в карточке клиента.

### 4.5. Денежная оценка

```
P(churn | score) = 1 / (1 + exp(−k · (score − s0)))       k = 0.08, s0 = 60  (настройки)
value(service)   = price · horizon_money_days / period_days     horizon_money_days = 30 (настройка)
coverage         = min(1, available / Σ value(живых услуг аккаунта))
expected_loss(service) = value · P(service_score) · (1 − balance_shield · coverage)     balance_shield = 0.5
```

Показатели панели (все в центах в БД):

1. `revenue_at_risk` = Σ value по живым услугам клиентов уровня medium и high.
2. `expected_loss` = Σ expected_loss(service) по всем клиентам с оценкой.
3. `recoverable` = Σ по аккаунтам `max(0, Σ value услуг, истекающих в пределах horizon_days − available)`. Это деньги, которые клиент должен пополнить для продления.
4. `lost_revenue_monthly` = Σ `price · 30 / period_days` по услугам клиентов `churned`.
5. `hourly_share` = доля `revenue_at_risk` от услуг с `paymentTerm = hour` (показывается рядом с цифрой, чтобы почасовые услуги не искажали картину незаметно).

Для каждого числа в UI есть иконка-подсказка с формулой простыми словами.

### 4.6. Настройки (`app.model_settings`, одна строка, JSON + `version`)

```
weights: {feature_key: float ≥ 0}      horizon_days, horizon_money_days
thresholds: {low, high}                alpha_max_mean
churn_curve: {k, midpoint}             balance_shield
suspended_value                        as_of_mode, as_of_fixed
```

`PATCH /model/settings` принимает частичный объект, мержит с текущим, валидирует диапазоны (веса 0..100, пороги 0..100 при `low < high`, α 0..1 и т.д.), сохраняет в БД, увеличивает `version`, запускает пересчёт, публикует событие. Значения переживают рестарт контейнера.

### 4.7. График оттока (`GET /api/v1/analytics/churn-timeline`)

Ежедневные точки (`date`, `value`) в трёх сериях с явными типами:

- `observed`: переходы в `deleted`/`blocked` из `app.service_status_events` (накапливаются с PUT-снимков);
- `estimated`: услуги в `deleted`, дата оценивается как `expiresAt + 5 суток`;
- `forecast`: живые услуги с `expiresAt` в ближайшие 30 суток, суммируется `P(churn)` по дням `expiresAt`.

Плюс точка `as_of`, разделяющая прошлое и будущее. Ответ содержит `type` для каждой серии, и UI рисует: observed — сплошная линия, estimated — серая штриховая, forecast — пунктир другого цвета.

## 5. API (все под `/api/v1`, кроме `/metrics`)

| Метод и путь | Поведение |
|---|---|
| `POST /auth/login` `{login,password}` | ставит cookie, 200 / 401 |
| `GET /auth/me` | текущий пользователь / 401 |
| `POST /auth/logout` | удаляет сессию |
| `GET /customers` | параметры: `level` (low\|medium\|high\|churned\|no_data, множественный), `q` (id или часть email), `sort_by` (id\|email\|balance\|total_replenished\|score\|expected_loss), `order` (asc\|desc), `page`, `size`. Строка: id, email, balance, totalReplenished, score, level, loyalty, topReason, expectedLoss. `NULL` score всегда в конце |
| `GET /customers/{id}` | аккаунт, услуги со статусами и score, вклад каждого признака, причины, `dataWarnings`, денежная оценка. 404 при неизвестном id |
| `GET /analytics/summary` | счётчики по уровням, пять денежных показателей из п. 4.5, `modelVersion`, `asOf`, `calculatedAt` |
| `GET /analytics/churn-timeline` | см. п. 4.7 |
| `GET /model/settings` | текущие значения плюс описание: для каждого признака title, description, default_weight; допустимые диапазоны |
| `PATCH /model/settings` | см. п. 4.6 |
| `PUT /source/snapshot` | см. п. 3. Ответ: количество строк, число изменённых статусов, `modelVersion` |
| `GET /events` | SSE: `event: recomputed`, `data: {modelVersion, at}`; keep-alive каждые 15 с |
| `GET /metrics`, `GET /metics` | Prometheus text format |
| `GET /docs`, `GET /openapi.json` | Swagger UI с рабочим Try it out |

Все деньги в ответах в двух полях: `…Cents` (int) и `…Eur` (float, 2 знака) либо только Cents плюс единая подсказка валюты; выбери один подход и держи его везде.

### Метрики

```
churn_customers{level="low|medium|high|churned|no_data"}
churn_revenue_at_risk_eur
churn_expected_loss_eur
churn_recoverable_eur
churn_lost_revenue_monthly_eur
churn_score_avg
churn_model_version
churn_last_recalc_timestamp_seconds
```

## 6. Фазы

### Фаза 0. Каркас и контракт
1. Структура репозитория, `.env.example` (`DATABASE_URL`, `ADMIN_LOGIN`, `ADMIN_PASSWORD`, `SESSION_SECRET`, `METRICS_TOKEN`, `SEED_DATASET=demo|official|none`).
2. `docker-compose.yml`: `db` (healthcheck), `api` (depends_on healthy), `web`. Том для `pgdata`.
3. Скелет FastAPI с `/healthz` и Swagger.
4. Черновик `openapi.yml` по разделу 5.

**DoD:** `docker compose up -d --build` поднимает три контейнера; `curl localhost:8080/healthz` → 200.

### Фаза 1. БД и приём данных
1. Миграции: `001_schema.sql` (копия комплекта) и `010_app_schema.sql` (схема `app`: `users`, `sessions`, `model_settings`, `customer_scores`, `service_scores`, `service_status_events`, `source_meta` с `captured_at`).
2. Pydantic-схемы по разделу 3. Загрузчик `load_snapshot()`, дифф статусов, проверки качества данных.
3. Seed при старте по `SEED_DATASET`, только если таблицы пусты.
4. Эндпоинт `PUT /source/snapshot` (пока без пересчёта).

**DoD:** тесты: `data/official.json` загружается (10/30/100); невалидный статус → 422 и БД не изменилась; повторный PUT с изменённым статусом создаёт запись в `service_status_events`.

### Фаза 2. Ядро скоринга
1. `registry`, 9 признаков по п. 4.2 (один файл на признак), `engine`, `money`, `settings`, `recompute`.
2. Unit-тесты на каждый признак и на формулы (эталонные значения посчитай руками для аккаунтов 1, 5, 9 из `official.json`).
3. Состояния `no_data` и `churned`.

**DoD:** `pytest backend/tests/scoring` зелёный; на `official.json` аккаунты 1 и 6 получают score, 2/3/7/8 это `churned`, аккаунты 5 и 9 имеют высокий `funds_deficit`.

### Фаза 3. API, auth, настройки
1. Auth (login/me/logout), зависимость `require_user` на всех роутерах, администратор при старте.
2. `customers`, `customers/{id}`, `analytics/summary`, `model/settings` (GET/PATCH), PUT snapshot с пересчётом.
3. `build_summary()` и `churn-timeline`.

**DoD:** тесты API: без cookie все защищённые эндпоинты дают 401; сортировка по каждому из 4 обязательных полей в обе стороны проверена; PATCH веса меняет score и `modelVersion`; после пересоздания приложения настройки сохранены.

### Фаза 4. Live и метрики
1. Шина событий, `GET /events` (SSE), публикация после `recompute`.
2. `/metrics` с кастомным collector и Bearer-доступом.

**DoD:** тест: подписка на SSE получает `recomputed` после PATCH и после PUT; тест согласованности `/metrics` и `/analytics/summary` (счётчики и деньги совпадают после округления до 2 знаков).

### Фаза 5. Демо-данные
`tools/generate_demo.py --accounts 200 --seed 42 --out data/demo.json`:
- 2–5 услуг на аккаунт со **смешанными** статусами внутри клиента;
- `expiresAt` согласован с `as_of` и статусом (`prolong_wait` в основном не старше 5 суток, небольшая доля с аномалиями);
- сценарные кластеры: дорогая почасовая услуга при малом балансе; автопродление выключено при скором окончании; клиент с большим `totalReplenished` и всеми удалёнными услугами; `bonusState = locked` с большим бонусом; `prolong_wait` + `autoProlong` + достаточный баланс;
- формат полностью совпадает с контрактом из раздела 3; детерминированный `--seed`.

**DoD:** `data/demo.json` проходит валидацию PUT; на нём все пять состояний клиента (low/medium/high/churned/no_data) непустые.

### Фаза 6. Frontend
Страницы (русский UI, адаптив от 1280px):
1. **Вход**: логин/пароль, сообщение об ошибке.
2. **Дашборд**: карточки (клиенты по уровням, выручка под риском, ожидаемые потери, устранимая часть, потерянная выручка) с подсказками; график оттока (observed / estimated / forecast, легенда, вертикальная линия `as_of`); бейдж «обновлено в HH:MM:SS» и индикатор SSE-соединения.
3. **Клиенты**: таблица (ID, email, баланс, сумма пополнений, score, уровень цветом, главная причина, ожидаемые потери), клик по заголовку сортирует с переключением asc/desc и стрелкой, фильтр по уровню, поиск, пагинация. Для `no_data` показывать «Нет оценки», для `churned` показывать «Ушёл».
4. **Карточка клиента** (боковая панель): услуги и их статусы, горизонтальные столбцы вклада признаков, текстовые причины, предупреждения по качеству данных, денежная оценка.
5. **Модель**: форма строится по ответу `GET /model/settings` (слайдеры весов, пороги, горизонты, кривая, `as_of`), PATCH с debounce 400 мс, кнопка «Сбросить к умолчанию».
6. **Данные**: загрузка JSON-файла в `PUT /source/snapshot`, кнопки «Загрузить демо» и «Загрузить официальный набор».

Живое обновление: единый хук `useLiveUpdates()` подписывается на SSE и инвалидирует запросы TanStack Query при `recomputed`. Reload страницы не нужен. При 401 редирект на вход.

**DoD:** ручной прогон сценария из раздела 8 проходит без перезагрузки страницы.

### Фаза 7. Документация и приёмка
1. Выгрузка `openapi.yml` из приложения скриптом `make openapi`; тест, что файл в репозитории совпадает с живым `/openapi.json`.
2. `README.md`: требования, `cp .env.example .env`, `docker compose up --build`, адреса, логин/пароль по умолчанию, как загрузить данные, как запустить тесты.
3. `docs/model.md`: признаки, формулы, допущения, обоснование коэффициентов (кратко, для жюри).
4. `docs/architecture.md`: схема, поток данных, источник правды.
5. `docs/add-feature.md`: пошагово «как добавить признак» с рабочим примером (файл целиком, ожидаемый результат в UI).
6. Чистый запуск: `docker compose down -v && docker compose up --build` на пустой машине, без ручных шагов.

**DoD:** чек-лист из раздела 7 полностью отмечен.

### Фаза 8 (бонус, только после фазы 7)
1. OIDC через Keycloak (Compose-профиль `oidc`, импорт realm), кнопка «Войти через SSO», fallback на логин/пароль.
2. Prometheus (профиль `monitoring`) со скрейпом `/metrics` по Bearer.
3. Доработка UX: пустые состояния, скелетоны, экспорт таблицы в CSV.

## 7. Чек-лист приёмки

Доказательства по каждому пункту: [docs/acceptance.md](docs/acceptance.md).

- [x] `docker compose up --build` с нуля работает по README, без ручных шагов
- [x] Без авторизации недоступны панель и все `/api/v1/*`, кроме login и docs
- [x] В таблице видны score, уровень, причина; `no_data` и `churned` показаны явно
- [x] Сортировка по ID, email, балансу, сумме пополнений работает в обе стороны
- [x] PATCH коэффициента пересчитывает рейтинг и деньги без reload; после `docker compose restart api` значения сохранены
- [x] PUT snapshot обновляет UI автоматически
- [x] Денежная оценка учитывает цену услуг, балансы и риск, есть пояснения к цифрам
- [x] `/metrics` и `/metics` отдают Prometheus-формат и совпадают с `/analytics/summary`
- [x] Swagger на `/api/v1/docs` работает; `openapi.yml` в репозитории и совпадает с живым
- [x] На графике факт, оценка и прогноз различимы
- [x] README, `model.md`, `architecture.md`, `add-feature.md` присутствуют
- [x] Все тесты зелёные

## 8. Сценарий демо (проверяется в конце фазы 6 и 7)

1. Войти → на дашборде видно клиентов с высоким риском и ожидаемые потери.
2. Таблица клиентов → сортировка по score по убыванию → открыть клиента с `prolong_wait` и малым балансом.
3. В карточке показать вклад признаков, текстовые причины и денежную оценку.
4. Вкладка «Модель»: поднять вес `funds_deficit` → рейтинг, score и суммы изменились на экране сами.
5. Вкладка «Данные»: загрузить снимок, где у этого клиента пополнен баланс или включено автопродление → риск упал, карточки дашборда и `/metrics` обновились.
6. Показать график: сплошная линия факта, штриховая оценка, пунктир прогноза.

## 9. Чего не делать

- Не менять `data/official.json` и `001_schema.sql`.
- Не считать деньги во float до последнего шага.
- Не писать результаты скоринга в код или в статичные фикстуры.
- Не прибавлять `withdrawBalance` к `available`: в данных он всегда не больше `balance` и является его частью.
- Не засчитывать `deleted`/`blocked` как «риск», это уже состояние `churned`.
- Не тратить время на фазу 8, пока не закрыты фазы 0–7.
