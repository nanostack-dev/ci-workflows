-- expect-custom: none
-- expect-squawk: none
-- The shared rule set leaves style alone: lock_timeout/statement_timeout, IF NOT EXISTS
-- advice, varchar(n), int and timestamp are the repositories' business.
ALTER TABLE webhooks ADD COLUMN IF NOT EXISTS name VARCHAR(100);
ALTER TABLE webhooks ADD COLUMN IF NOT EXISTS retries INT;
ALTER TABLE webhooks ADD COLUMN IF NOT EXISTS note TEXT;
ALTER TABLE webhooks DROP CONSTRAINT IF EXISTS webhooks_org_set;
ALTER TABLE webhooks ALTER COLUMN note DROP NOT NULL;
