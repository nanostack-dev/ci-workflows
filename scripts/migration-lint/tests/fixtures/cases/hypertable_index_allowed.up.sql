-- expect-custom: none
-- lint: allow-hypertable-index events has no chunks in any environment yet
CREATE INDEX IF NOT EXISTS idx_events_webhook_received ON events (webhook_id, received_at DESC);
