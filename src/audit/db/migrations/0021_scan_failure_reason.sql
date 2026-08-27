-- 0021 — retain a bounded diagnostic when a scan cannot produce evidence.

ALTER TABLE scans ADD COLUMN failure_reason TEXT;
