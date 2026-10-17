-- expect-custom: none
-- expect-custom-warning: lint-opt-out-unused
-- lint: allow-backfill nothing here backfills
ALTER TABLE webhooks ADD COLUMN IF NOT EXISTS note TEXT;
