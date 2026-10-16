-- expect-custom: none
-- expect-squawk: require-concurrent-index-creation, require-concurrent-index-creation
CREATE INDEX IF NOT EXISTS idx_webhooks_org_created_id ON webhooks (organization_id, created_at, id);
CREATE INDEX IF NOT EXISTS idx_webhooks_created ON webhooks (created_at);
