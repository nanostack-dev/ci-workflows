-- expect-custom: concurrently-alone
-- expect-squawk: ban-concurrent-index-creation-in-transaction
BEGIN;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_a ON webhooks (organization_id);
COMMIT;
