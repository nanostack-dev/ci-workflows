-- expect-custom: update-backfill
DO $migrate$
DECLARE r RECORD;
BEGIN
    FOR r IN SELECT id FROM webhooks LOOP
        UPDATE webhooks SET created_at = now() WHERE id = r.id;
    END LOOP;
END
$migrate$;
