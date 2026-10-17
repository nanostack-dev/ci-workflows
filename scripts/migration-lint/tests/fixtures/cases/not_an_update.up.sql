-- expect-custom: none
-- expect-squawk: none
-- None of these modifies rows: the word UPDATE or DELETE appears in other roles.
CREATE TABLE IF NOT EXISTS gadget_links (
    id UUID PRIMARY KEY,
    webhook_id UUID NOT NULL REFERENCES webhooks (id) ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $fn$
BEGIN
    UPDATE webhooks SET created_at = now() WHERE id = NEW.id;
    DELETE FROM webhooks;
    RETURN NEW;
END
$fn$ LANGUAGE plpgsql;

CREATE TRIGGER gadget_links_touch BEFORE INSERT OR UPDATE ON gadget_links
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

INSERT INTO gadget_links (id, webhook_id) SELECT gen_random_uuid(), id FROM webhooks
    ON CONFLICT (id) DO UPDATE SET webhook_id = EXCLUDED.webhook_id;

SELECT id FROM webhooks FOR UPDATE;

COMMENT ON TABLE gadget_links IS 'UPDATE webhooks SET x = 1; DELETE FROM webhooks;';
