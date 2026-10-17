-- expect-custom: none
-- expect-squawk: none
-- events is a hypertable, which has no CREATE INDEX CONCURRENTLY.
CREATE INDEX IF NOT EXISTS idx_events_webhook_received
    ON events (webhook_id, received_at DESC, id DESC) WITH (timescaledb.transaction_per_chunk);
