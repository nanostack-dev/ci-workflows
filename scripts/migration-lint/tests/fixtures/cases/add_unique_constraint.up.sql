-- expect-custom: none
-- expect-squawk: constraint-missing-not-valid, disallowed-unique-constraint
ALTER TABLE webhooks ADD CONSTRAINT webhooks_org_unique UNIQUE (organization_id);
