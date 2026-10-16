-- expect-custom: none
-- expect-squawk: none
-- One statement per file, so golang-migrate runs it outside a transaction.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_webhooks_org_created_id
    ON webhooks (organization_id, created_at DESC, id DESC);
