# Анализатор рисков оттока

Проект находится на фазе 0: создан каркас API, инфраструктура Docker Compose и черновик OpenAPI.

## Запуск

Требуются Docker Engine и Docker Compose.

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

Приложение будет доступно по адресу <http://localhost:8081>. Проверка API: <http://localhost:8081/healthz>, Swagger UI: <http://localhost:8081/api/v1/docs>.

Перед публикацией замените значения секретов в `.env`.