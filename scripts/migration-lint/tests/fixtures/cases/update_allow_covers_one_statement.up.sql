-- expect-custom: update-backfill
-- lint: allow-backfill small table
UPDATE webhooks SET created_at = now();

UPDATE webhooks SET organization_id = organization_id;
