# Анализатор рисков оттока

Веб-панель, которая оценивает риск ухода каждого клиента, объясняет причины и переводит риск в деньги. Данные — снимок аккаунтов, услуг и транзакций в формате `data.json`. Оценки пересчитываются сразу после загрузки снимка или изменения настроек модели, и панель обновляется без перезагрузки страницы.

![Дашборд на демо-наборе](docs/img/demo-1-dashboard.png)

**С чего начать:** [сценарий демо на 5 минут](docs/demo.md) · [анализ модели и метрик](docs/analysis.md) · [чек-лист приёмки с доказательствами](docs/acceptance.md)

## Требования

- Docker Engine и Docker Compose v2.
- Для локальной разработки без Docker: Python 3.12, Node.js 22, PostgreSQL 16.

## Запуск

```bash
cp .env.example .env        # в PowerShell: Copy-Item .env.example .env
docker compose up -d --build
```

| Что | Адрес |
|---|---|
| Панель | <http://localhost:8081> |
| Swagger UI | <http://localhost:8081/api/v1/docs> |
| Проверка API | <http://localhost:8081/healthz> |
| Метрики Prometheus | <http://localhost:8081/metrics> (алиас `/metics`) |

Вход: логин и пароль из `.env` (`ADMIN_LOGIN` / `ADMIN_PASSWORD`). Без `.env` используются `admin` / `change-me-before-deploy`. Пароль администратора синхронизируется с `.env` при каждом старте API.

Перед публикацией замените `ADMIN_PASSWORD`, `SESSION_SECRET` и `METRICS_TOKEN`. Если панель открывается по HTTPS, поставьте `COOKIE_SECURE=true`.

Чистый запуск с пустой базой: `docker compose down -v && docker compose up -d --build` (или `make reset`).

## Переменные окружения

| Переменная | Назначение |
|---|---|
| `DATABASE_URL` | Подключение к PostgreSQL |
| `ADMIN_LOGIN`, `ADMIN_PASSWORD` | Учётная запись администратора, создаётся при старте |
| `SESSION_SECRET` | Ключ HMAC-подписи cookie сессии |
| `METRICS_TOKEN` | Bearer-токен для `/metrics` без сессии (для Prometheus) |
| `SEED_DATASET` | `official`, `demo` или `none`: что загрузить при первом старте, если база пуста |
| `COOKIE_SECURE` | `true` — cookie сессии только по HTTPS |

## Загрузка данных

- В панели: вкладка «Данные» → выбрать JSON-файл или нажать один из встроенных наборов.
- Через API (нужна сессия): `PUT /api/v1/source/snapshot` с телом в формате `data.json`, или `POST /api/v1/source/presets/{name}`.

Встроенные наборы (`data/`):

| Набор | Что внутри |
|---|---|
| `official` | 10 клиентов из ТЗ; эталон для проверки формул |
| `demo` | 200 клиентов пяти сегментов с разбросом балансов, цен и сроков |
| `demo-step2` | те же клиенты через сутки: часть пополнила баланс, часть ушла. Нужен для шага 5 [сценария демо](docs/demo.md) и линии «Факт» на графике |

Снимок проверяется целиком: при любой ошибке API отвечает 422 со списком проблем, и в базе ничего не меняется. Загрузка, история смен статусов и пересчёт выполняются одной транзакцией.

Пример с `curl`:

```bash
curl -c cookies.txt -H 'Content-Type: application/json' \
  -d '{"login":"admin","password":"change-me-before-deploy"}' \
  http://localhost:8081/api/v1/auth/login
curl -b cookies.txt -X PUT -H 'Content-Type: application/json' \
  --data @data/official.json http://localhost:8081/api/v1/source/snapshot
curl -H "Authorization: Bearer $METRICS_TOKEN" http://localhost:8081/metrics
```

Демо-наборы пересобираются командой `make demo-data` (`tools/generate_demo.py --accounts 200 --seed 42`).

## Тесты

Тесты API работают с настоящим PostgreSQL и **очищают данные в указанной базе**, поэтому им нужна отдельная тестовая база. Без `DATABASE_URL` тесты API пропускаются (будут отмечены как skipped).

Внутри Docker:

```bash
make test-docker
```

Локально (Python 3.12, PostgreSQL на `localhost`):

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt
createdb churn_test
make test   # DATABASE_URL=postgresql+psycopg://churn:churn@localhost:5432/churn_test
```

Фронтенд: `cd frontend && npm ci && npm run build` (проверка типов и сборка).

## Разработка без Docker

```bash
# API на :8000
cd backend
DATABASE_URL=postgresql+psycopg://churn:churn@localhost:5432/churn uvicorn app.main:app --reload
# фронтенд на :5173, /api проксируется на :8000
cd frontend && npm ci && npm run dev
```

## OpenAPI

`openapi.yml` в корне выгружается из приложения командой `make openapi`. Тест `backend/tests/test_openapi.py` падает, если файл разошёлся с живой схемой `/api/v1/openapi.json`.

## Анализ модели

`python tools/analyze_model.py` пересчитывает все цифры и графики [docs/analysis.md](docs/analysis.md) на встроенных наборах. Нужны `backend/requirements.txt` и `tools/requirements-analysis.txt`. Результат пишется в `docs/analysis-data.json` и `docs/img/analysis-*.png`.

## Документация

- [docs/demo.md](docs/demo.md) — сценарий демо со скриншотами.
- [docs/analysis.md](docs/analysis.md) — как модель ведёт себя на данных: признаки, устойчивость, проверка на втором снимке, денежные метрики, ограничения.
- [docs/acceptance.md](docs/acceptance.md) — чек-лист приёмки и чем подтверждается каждый пункт.
- [docs/model.md](docs/model.md) — признаки, формулы, денежная оценка, обоснование коэффициентов.
- [docs/architecture.md](docs/architecture.md) — компоненты, поток данных, источник правды.
- [docs/add-feature.md](docs/add-feature.md) — как добавить новый признак риска.