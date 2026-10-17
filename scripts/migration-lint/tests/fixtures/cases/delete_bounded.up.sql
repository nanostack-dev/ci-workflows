-- expect-custom: none
DELETE FROM webhooks WHERE created_at < now() - interval '90 days';
