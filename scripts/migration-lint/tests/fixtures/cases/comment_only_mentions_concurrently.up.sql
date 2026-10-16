-- expect-custom: none
-- CREATE INDEX CONCURRENTLY would be better here; the table is new.
CREATE TABLE IF NOT EXISTS gadgets (id UUID PRIMARY KEY, name TEXT);
COMMENT ON TABLE gadgets IS 'built; CREATE INDEX CONCURRENTLY x ON y (z);';
