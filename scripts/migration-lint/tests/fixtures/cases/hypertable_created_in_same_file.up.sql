-- expect-custom: none
-- expect-squawk: none
CREATE TABLE IF NOT EXISTS readings (
    id UUID NOT NULL,
    at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (id, at)
);
SELECT create_hypertable('readings', 'at');
CREATE INDEX IF NOT EXISTS idx_readings_at ON readings (at DESC);
