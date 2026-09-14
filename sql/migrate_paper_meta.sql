-- Add semester and exam type to papers.
-- Safe to re-run.

ALTER TABLE papers ADD COLUMN IF NOT EXISTS semester TEXT NOT NULL DEFAULT '';
ALTER TABLE papers ADD COLUMN IF NOT EXISTS exam_type TEXT NOT NULL DEFAULT '';

ALTER TABLE papers DROP CONSTRAINT IF EXISTS papers_semester_check;
ALTER TABLE papers ADD CONSTRAINT papers_semester_check
  CHECK (semester = '' OR semester IN (
    '高一上学期','高一下学期','高二上学期','高二下学期','高三上学期','高三下学期'
  ));

ALTER TABLE papers DROP CONSTRAINT IF EXISTS papers_exam_type_check;
ALTER TABLE papers ADD CONSTRAINT papers_exam_type_check
  CHECK (exam_type = '' OR exam_type IN ('月考','期中','期末'));
