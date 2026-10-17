-- expect-custom: none
-- expect-squawk: renaming-column
ALTER TABLE webhooks RENAME COLUMN organization_id TO org_id;
