# Приёмка: чек-лист и доказательства

Каждый пункт чек-листа из раздела 7 `PLAN.md` с тем, что его подтверждает, и способом проверить вручную. Автоматические проверки — тесты в `backend/tests` (запуск: `make test-docker`, см. README).

| # | Требование | Чем подтверждается | Как проверить руками |
|---|---|---|---|
| 1 | `docker compose up --build` с нуля по README, без ручных шагов | Миграции, администратор и стартовый набор создаются при запуске API (`app/main.py`); `test_startup_seeds_official_snapshot` | `docker compose down -v && docker compose up -d --build`, затем открыть <http://localhost:8081> |
| 2 | Без авторизации недоступны панель и все `/api/v1/*`, кроме login и docs | `test_protected_endpoints_require_session`, `test_forged_or_malformed_session_cookie_is_401`, `test_public_and_protected_paths_are_documented` | В приватном окне открыть <http://localhost:8081/api/v1/customers> — 401 |
| 3 | В таблице видны score, уровень, причина; `no_data` и `churned` показаны явно | `test_customer_filter_search_and_detail`; в UI «Ушёл» и «Нет оценки» вместо score | Вкладка «Клиенты», фильтр «Ушёл» |
| 4 | Сортировка по ID, email, балансу, сумме пополнений в обе стороны | `test_customer_sorting` (4 поля × 2 направления) | Клик по заголовкам столбцов |
| 5 | PATCH коэффициента пересчитывает рейтинг и деньги без reload; значения переживают рестарт | `test_patch_model_settings_changes_scores_and_version` (включая пересоздание приложения), `test_sse_publishes_recomputed_after_patch_and_put`, `test_invalid_settings_return_422_and_keep_version` | Шаг 4 [сценария демо](demo.md), затем `docker compose restart api` |
| 6 | PUT snapshot обновляет UI автоматически | `test_sse_publishes_recomputed_after_patch_and_put`, `test_demo_step2_feeds_observed_churn` | Шаг 5 сценария демо, страница не перезагружается |
| 7 | Денежная оценка учитывает цену услуг, балансы и риск, есть пояснения | `test_money_formulas_match_official_golden_values`, `test_recoverable_includes_prolong_wait_in_grace_period`; подсказки «Формула» на дашборде; [model.md](model.md) | Навести на «Формула» у любой карточки |
| 8 | `/metrics` и `/metics` в формате Prometheus и совпадают с `/analytics/summary` | `test_metrics_aliases_require_auth_and_bearer_works`, `test_prometheus_values_match_build_summary`, `test_summary_counts_match_customer_table` | `curl -H "Authorization: Bearer $METRICS_TOKEN" localhost:8081/metrics` |
| 9 | Swagger на `/api/v1/docs`; `openapi.yml` в репозитории совпадает с живым | `test_openapi_file_matches_live_schema`; `make openapi` | <http://localhost:8081/api/v1/docs> |
| 10 | На графике различимы факт, оценка и прогноз | Сплошная линия с точками / серая штриховая / оранжевый пунктир, легенда, одна единица (услуги) — `test_timeline_uses_one_unit` | Шаг 6 сценария демо |
| 11 | README, `model.md`, `architecture.md`, `add-feature.md` | [README](../README.md), [model.md](model.md), [architecture.md](architecture.md), [add-feature.md](add-feature.md); плюс [analysis.md](analysis.md) и [demo.md](demo.md) | — |
| 12 | Все тесты зелёные | 68 тестов: скоринг и формулы, приём данных, API, авторизация, live-обновления, метрики, OpenAPI, регрессии | `make test-docker` |

## Что проверено сверх чек-листа

| Область | Тесты |
|---|---|
| Транзакционность загрузки: ошибка валидации или пересчёта не меняет базу | `test_invalid_snapshot_returns_422_without_mutating_database`, `test_snapshot_rolls_back_when_recompute_fails` |
| История статусов без ложных событий при смене набора | `test_switching_datasets_records_no_fake_status_changes`, `test_real_status_change_is_still_recorded` |
| Одновременные PATCH и PUT | `test_concurrent_writes_do_not_fail` |
| Защита входа от перебора | `test_repeated_wrong_passwords_are_throttled` |
| Единый источник правды для сводки | `test_summary_reads_stored_result_instead_of_recalculating` |
| Устойчивость сохранённых настроек к добавлению и удалению признаков | `test_stored_settings_survive_feature_changes` |
| Даты без часового пояса, спецсимволы в поиске | `test_snapshot_without_timezone_is_treated_as_utc`, `test_search_treats_wildcards_literally` |
| Каждый из 9 признаков и эталонные значения на `official.json` | `tests/scoring/test_engine.py` |
| Демо-набор: все пять состояний, разнообразие клиентов, второй снимок | `test_demo_data_has_all_states_and_required_scenarios`, `test_demo_step2_lowers_risk_and_records_churn` |
