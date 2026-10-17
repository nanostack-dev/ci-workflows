-- expect-custom: concurrently-alone
CREATE INDEX IF NOT EXISTS idx_events_webhook_received
    ON events (webhook_id, received_at DESC) WITH (timescaledb.transaction_per_chunk);
CREATE INDEX IF NOT EXISTS idx_webhooks_org ON gadgets (id);
