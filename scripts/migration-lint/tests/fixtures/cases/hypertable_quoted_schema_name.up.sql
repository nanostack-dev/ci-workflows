-- expect-custom: hypertable-index
CREATE INDEX IF NOT EXISTS idx_metrics_n ON public."Metrics" (n);
