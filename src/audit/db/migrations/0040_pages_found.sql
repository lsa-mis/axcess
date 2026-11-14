-- 0040 — how many pages a scan found, kept after the scan ends.
--
-- A report says how much of the site it covered with numbers (pages found,
-- pages visited, the page limit chosen, how it ended) instead of calling a
-- stopped scan "partial" (audit.db.reports). Pages found was only ever
-- counted live from the jobs queue, and Stop empties the waiting jobs, so
-- the number was lost the moment it mattered. NULL when it was not recorded.
ALTER TABLE scans ADD COLUMN pages_found INTEGER;

-- Backfill from the queue where it is still whole: completed and failed
-- scans keep every job, and a scan interrupted by a crash (not by Stop)
-- still holds its waiting jobs. A scan stopped from the app lost them, so it
-- stays NULL rather than showing a count that is too low.
CREATE TEMP TABLE _found AS
    SELECT CAST(json_extract(payload_json, '$.scan_id') AS INTEGER) AS scan_id,
           COUNT(*) AS n,
           SUM(state IN ('pending', 'leased')) AS waiting
      FROM jobs
     WHERE kind = 'fetch'
     GROUP BY 1;

UPDATE scans
   SET pages_found = MAX(page_count, (SELECT n FROM _found WHERE _found.scan_id = scans.id))
 WHERE id IN (
       SELECT scan_id FROM _found
        WHERE scans.status IN ('completed', 'failed')
           OR (scans.status = 'interrupted' AND waiting > 0)
 );

DROP TABLE _found;
