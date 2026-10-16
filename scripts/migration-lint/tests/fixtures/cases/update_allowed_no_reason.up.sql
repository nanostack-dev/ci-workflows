-- expect-custom: lint-opt-out, update-backfill
-- lint: allow-backfill
UPDATE webhooks SET created_at = now();
