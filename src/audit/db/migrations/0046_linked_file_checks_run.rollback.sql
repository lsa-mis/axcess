-- Rollback for 0046: forget which checks ran. Old reports then read as if
-- every file ran the first five checks, as before.
ALTER TABLE linked_files DROP COLUMN checks_run;
