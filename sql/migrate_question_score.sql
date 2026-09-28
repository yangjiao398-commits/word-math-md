-- Ensure questions.score exists. Safe to re-run.

ALTER TABLE questions ADD COLUMN IF NOT EXISTS score NUMERIC(6,2);
