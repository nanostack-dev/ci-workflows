-- expect-custom: hypertable-index
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_webhook_received ON events (webhook_id, received_at DESC);
