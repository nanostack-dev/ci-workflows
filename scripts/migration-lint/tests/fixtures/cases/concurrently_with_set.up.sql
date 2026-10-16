-- expect-custom: concurrently-alone
SET lock_timeout = '5s';
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_a ON webhooks (organization_id);
