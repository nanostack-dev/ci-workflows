-- expect-custom: none
-- expect-squawk: none
-- A PostgreSQL 18 VIRTUAL generated column is metadata-only; squawk reads every generated column as STORED.
ALTER TABLE webhooks
    ADD COLUMN IF NOT EXISTS label_sort VARCHAR(255)
        GENERATED ALWAYS AS (left(label, 255)::varchar(255)) VIRTUAL,
    ADD COLUMN IF NOT EXISTS other_sort VARCHAR(255)
        GENERATED ALWAYS AS (left(other, 255)::varchar(255)) VIRTUAL;
