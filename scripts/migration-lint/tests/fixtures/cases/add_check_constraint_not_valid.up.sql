-- expect-custom: none
-- expect-squawk: none
ALTER TABLE webhooks ADD CONSTRAINT webhooks_org_set CHECK (organization_id IS NOT NULL) NOT VALID;
