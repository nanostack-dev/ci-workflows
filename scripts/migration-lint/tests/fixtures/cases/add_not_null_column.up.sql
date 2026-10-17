-- expect-custom: none
-- expect-squawk: adding-required-field
ALTER TABLE webhooks ADD COLUMN IF NOT EXISTS region TEXT NOT NULL;
