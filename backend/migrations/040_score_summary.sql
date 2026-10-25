BEGIN;
CREATE TABLE IF NOT EXISTS app.score_summary (
    id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    model_version integer NOT NULL,
    as_of timestamptz NOT NULL,
    calculated_at timestamptz NOT NULL,
    revenue_at_risk_cents bigint NOT NULL DEFAULT 0,
    expected_loss_cents bigint NOT NULL DEFAULT 0,
    recoverable_cents bigint NOT NULL DEFAULT 0,
    lost_revenue_monthly_cents bigint NOT NULL DEFAULT 0,
    hourly_share double precision NOT NULL DEFAULT 0
);

COMMIT;
