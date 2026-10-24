BEGIN;

ALTER TABLE app.source_meta
    ADD COLUMN IF NOT EXISTS data_warnings jsonb NOT NULL DEFAULT '[]'::jsonb;

COMMIT;