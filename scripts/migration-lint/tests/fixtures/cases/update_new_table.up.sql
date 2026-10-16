-- expect-custom: none
CREATE TABLE IF NOT EXISTS gadgets (id UUID PRIMARY KEY, name TEXT, label TEXT);
UPDATE gadgets SET label = name;
