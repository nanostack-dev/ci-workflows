-- expect-custom: none
-- expect-squawk: none
CREATE TABLE IF NOT EXISTS gadgets (id UUID PRIMARY KEY, name TEXT, owner_id UUID);
CREATE INDEX IF NOT EXISTS idx_gadgets_owner ON gadgets (owner_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_gadgets_name ON gadgets (name);
