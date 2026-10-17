-- expect-custom: none
-- expect-squawk: changing-column-type
ALTER TABLE webhooks ALTER COLUMN organization_id TYPE TEXT;
