-- expect-custom: none
-- expect-squawk: none
-- squawk-ignore ban-drop-column
ALTER TABLE webhooks DROP COLUMN IF EXISTS legacy;
