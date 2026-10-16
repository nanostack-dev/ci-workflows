-- expect-custom: none
UPDATE webhooks SET created_at = now(); -- lint: allow-backfill small table, reviewed in the PR
