# Архитектура

## Компоненты

```
Браузер ──► web (nginx :80, наружу :8081)
              ├─ /            статика React-приложения (SPA)
              ├─ /api/*       ─┐
              ├─ /metrics     ─┼─► api (FastAPI + uvicorn, 1 воркер, :8000) ──► db (PostgreSQL 16)
              └─ /healthz     ─┘
Prometheus ──► /metrics (Bearer METRICS_TOKEN)
```

| Сервис | Что внутри |
|---|---|
| `db` | PostgreSQL 16. Схема `public` — исходные таблицы из комплекта (`accounts`, `services`, `transactions`), схема `app` — всё, что считает приложение |
| `api` | FastAPI. При старте применяет миграции, создаёт или обновляет администратора, при пустой базе загружает `SEED_DATASET` и пересчитывает оценки |
| `web` | nginx: отдаёт собранный фронтенд и проксирует API. Для SSE отключена буферизация |

Фронтенд: React 18, TanStack Query, Recharts, React Router; весь UI — `frontend/src/AppFixed.tsx`, запросы и типы — `frontend/src/api.ts`.

## Таблицы приложения (`app`)

| Таблица | Содержимое |
|---|---|
| `users`, `sessions` | Администратор (пароль argon2) и сессии. Cookie содержит id сессии с HMAC-подписью `SESSION_SECRET` |
| `model_settings` | Одна строка: настройки модели (JSON) и `version` |
| `customer_scores` | Score, уровень, лояльность, причины, предупреждения и ожидаемые потери по каждому клиенту |
| `service_scores` | Score, вклад признаков, стоимость и ожидаемые потери по каждой живой услуге |
| `score_summary` | Одна строка: денежные итоги дашборда, `as_of`, версия модели и время пересчёта |
| `service_status_events` | История переходов статусов услуг между снимками (для линии «Факт») |
| `source_meta` | `capturedAt` последнего снимка, число строк, предупреждения качества |
| `schema_migrations` | Применённые SQL-миграции из `backend/migrations` |

## Источник правды

Оценки считает только функция `recompute()` (`backend/app/scoring/recompute.py`). Она за один проход:

1. читает снимок из `public.*` и настройки из `app.model_settings`;
2. считает признаки, score, уровни (`engine.py`) и деньги (`money.py`);
3. перезаписывает `customer_scores`, `service_scores` и `score_summary`.

Всё, что видит пользователь, читается из этих таблиц и больше нигде не пересчитывается:

- `GET /customers`, `GET /customers/{id}` — из `customer_scores` и `service_scores`;
- `GET /analytics/summary` и `/metrics` — из одной функции `build_summary()` (`analytics/summary.py`): счётчики по уровням из `customer_scores`, деньги из `score_summary`;
- `GET /analytics/churn-timeline` — score услуг из `service_scores`, `as_of` из `score_summary`.

Поэтому числа на дашборде, в таблице клиентов и в Prometheus всегда совпадают.

## Поток данных

**Загрузка снимка** (`PUT /source/snapshot` или `POST /source/presets/{name}`), одна транзакция:

1. Pydantic проверяет формат, перечисления, даты и ссылки `ownerId`/`serviceId`. При ошибке — 422, база не трогается.
2. Новые статусы сравниваются со старыми; переходы той же услуги записываются в `service_status_events`.
3. `transactions`, `services`, `accounts` удаляются и вставляются заново с исходными id.
4. `recompute()` в той же транзакции, затем коммит.
5. Публикуется событие `recomputed` в SSE.

**Изменение настроек** (`PATCH /model/settings`): частичный объект сливается с текущими настройками и валидируется (ошибка — 422). Затем в одной транзакции настройки сохраняются с `version + 1` и выполняется `recompute()`, после коммита публикуется `recomputed`.

Записи в таблицы оценок сериализуются блокировкой `RECOMPUTE_LOCK` (`scoring/lock.py`): синхронные эндпоинты FastAPI работают в пуле потоков, и одновременные PATCH и PUT не должны перемешивать DELETE и INSERT.

## Живое обновление

`GET /api/v1/events` — Server-Sent Events. Шина событий (`app/events.py`) живёт в памяти процесса, поэтому API запускается с одним воркером. Каждые 15 секунд отправляется keep-alive. Фронтенд (`useLiveUpdates`) при событии `recomputed` инвалидирует все запросы TanStack Query, и экраны перерисовываются без перезагрузки. Индикатор Live в шапке показывает состояние соединения.

## Авторизация

Публичны только `POST /api/v1/auth/login`, `GET /api/v1/docs`, `GET /api/v1/openapi.json` и `GET /healthz`. Остальное требует сессии (cookie `session`, HttpOnly, SameSite=Lax, 12 часов). `/metrics` дополнительно принимает `Authorization: Bearer ${METRICS_TOKEN}`. При ответе 401 фронтенд возвращает пользователя на экран входа.
