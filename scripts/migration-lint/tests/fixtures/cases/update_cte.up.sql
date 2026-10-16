-- expect-custom: update-backfill
WITH moved AS (
    UPDATE webhooks SET created_at = now() RETURNING id
)
SELECT count(*) FROM moved;
