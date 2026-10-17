-- expect-custom: none
-- expect-squawk: ban-drop-column
ALTER TABLE webhooks DROP COLUMN IF EXISTS legacy;
