-- expect-custom: update-backfill
DO $$
BEGIN
    UPDATE webhooks SET created_at = now();
END
$$;
