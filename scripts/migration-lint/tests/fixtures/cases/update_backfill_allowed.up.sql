-- expect-custom: none
-- lint: allow-backfill webhooks has under 1,000 rows in every environment
UPDATE webhooks SET created_at = now() WHERE created_at IS NULL;
