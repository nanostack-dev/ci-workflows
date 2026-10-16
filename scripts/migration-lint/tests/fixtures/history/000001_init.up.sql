CREATE TABLE IF NOT EXISTS webhooks (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS events (
    id UUID NOT NULL,
    webhook_id UUID NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (id, received_at)
);
SELECT create_hypertable('events', 'received_at', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS "Metrics" (time_bucket TIMESTAMPTZ NOT NULL, n BIGINT);
SELECT create_hypertable('public."Metrics"', by_range('time_bucket'));

CREATE TABLE IF NOT EXISTS samples (at TIMESTAMPTZ NOT NULL, v BIGINT) WITH (tsdb.hypertable, tsdb.partition_column = 'at');
