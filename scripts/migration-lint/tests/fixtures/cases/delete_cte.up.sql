-- expect-custom: unbounded-delete
WITH gone AS (DELETE FROM webhooks RETURNING id) SELECT count(*) FROM gone;
