from pathlib import Path

from sqlalchemy.engine import Engine


MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


def run_migrations(engine: Engine) -> None:
    connection = engine.raw_connection()
    try:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute("CREATE SCHEMA IF NOT EXISTS app")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS app.schema_migrations (
                    filename text PRIMARY KEY,
                    applied_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            cursor.execute("SELECT filename FROM app.schema_migrations")
            applied = {row[0] for row in cursor.fetchall()}

            for migration in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")):
                if migration.name in applied:
                    continue
                cursor.execute(migration.read_text(encoding="utf-8"))
                connection.autocommit = False
                try:
                    cursor.execute(
                        "INSERT INTO app.schema_migrations (filename) VALUES (%s)",
                        (migration.name,),
                    )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                finally:
                    connection.autocommit = True
    finally:
        connection.close()