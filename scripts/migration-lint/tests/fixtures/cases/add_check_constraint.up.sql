-- expect-custom: none
-- expect-squawk: constraint-missing-not-valid
ALTER TABLE webhooks ADD CONSTRAINT webhooks_org_set CHECK (organization_id IS NOT NULL);
