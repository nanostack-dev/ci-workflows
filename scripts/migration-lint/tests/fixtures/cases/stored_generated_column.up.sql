-- expect-custom: none
-- expect-squawk: adding-field-with-default
ALTER TABLE webhooks
    ADD COLUMN IF NOT EXISTS label_sort TEXT GENERATED ALWAYS AS (lower(label)) STORED;
