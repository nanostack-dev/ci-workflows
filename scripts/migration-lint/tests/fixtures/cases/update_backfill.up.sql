-- expect-custom: update-backfill
UPDATE webhooks SET created_at = now() WHERE created_at IS NULL;
