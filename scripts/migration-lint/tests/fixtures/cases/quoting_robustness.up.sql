-- expect-custom: none
-- A semicolon in a string, E-string, quoted identifier or comment must not split a statement:
-- CREATE INDEX CONCURRENTLY idx ON webhooks (x); UPDATE webhooks SET x = 1;
/* block comment; /* nested; */ UPDATE webhooks SET x = 1; */
INSERT INTO webhooks (id, organization_id) VALUES (gen_random_uuid(), gen_random_uuid()) ON CONFLICT DO NOTHING;
COMMENT ON TABLE webhooks IS 'a; b ''quoted; UPDATE webhooks SET x = 1;''';
COMMENT ON COLUMN webhooks.id IS E'escaped \'; UPDATE webhooks SET x = 1; \'';
COMMENT ON COLUMN webhooks.organization_id IS $tag$dollar; UPDATE webhooks SET x = 1; $tag$;
ALTER TABLE webhooks ADD COLUMN IF NOT EXISTS "semi;colon" TEXT;
