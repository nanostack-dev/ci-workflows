-- expect-custom: concurrently-alone
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_a ON webhooks (organization_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_b ON webhooks (created_at);
