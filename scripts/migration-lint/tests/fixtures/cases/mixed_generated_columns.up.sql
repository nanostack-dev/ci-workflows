-- expect-custom: none
-- expect-squawk: adding-field-with-default
ALTER TABLE webhooks
    ADD COLUMN IF NOT EXISTS a_sort TEXT GENERATED ALWAYS AS (lower(a)) VIRTUAL,
    ADD COLUMN IF NOT EXISTS b_sort TEXT GENERATED ALWAYS AS (lower(b)) STORED;
