-- expect-custom: none
-- expect-squawk: adding-foreign-key-constraint, constraint-missing-not-valid
ALTER TABLE webhooks ADD CONSTRAINT fk_webhooks_org FOREIGN KEY (organization_id) REFERENCES organizations (id);
