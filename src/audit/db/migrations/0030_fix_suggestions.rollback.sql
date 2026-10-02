-- Roll back 0030. Suggestions are advice only; no finding, status or export
-- depends on them, so dropping the table loses nothing a report needs.
DROP INDEX IF EXISTS idx_fix_suggestions_status;
DROP INDEX IF EXISTS idx_fix_suggestions_occurrence;
DROP TABLE IF EXISTS fix_suggestions;
