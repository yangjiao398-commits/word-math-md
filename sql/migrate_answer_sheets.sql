-- Photographed answer sheets and auto-grading history.
-- Safe to re-run.

CREATE TABLE IF NOT EXISTS answer_sheets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_id UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  student_name TEXT NOT NULL DEFAULT '',
  ocr_engine TEXT NOT NULL DEFAULT '',
  ocr_text TEXT NOT NULL DEFAULT '',
  total_score NUMERIC(8,2) NOT NULL DEFAULT 0,
  max_score NUMERIC(8,2) NOT NULL DEFAULT 0,
  correct_count INT NOT NULL DEFAULT 0,
  question_count INT NOT NULL DEFAULT 0,
  extra JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS answer_sheets_paper ON answer_sheets (paper_id, created_at DESC);

CREATE TABLE IF NOT EXISTS answer_sheet_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sheet_id UUID NOT NULL REFERENCES answer_sheets(id) ON DELETE CASCADE,
  question_id UUID REFERENCES questions(id) ON DELETE SET NULL,
  question_no INT NOT NULL,
  type_code TEXT NOT NULL DEFAULT '',
  student_answer TEXT NOT NULL DEFAULT '',
  expected_answer TEXT NOT NULL DEFAULT '',
  is_correct BOOLEAN NOT NULL DEFAULT false,
  status TEXT NOT NULL DEFAULT 'graded',
  score NUMERIC(8,2) NOT NULL DEFAULT 0,
  max_score NUMERIC(8,2) NOT NULL DEFAULT 0,
  extra JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS answer_sheet_items_sheet ON answer_sheet_items (sheet_id, question_no);

ALTER TABLE answer_sheets ENABLE ROW LEVEL SECURITY;
ALTER TABLE answer_sheet_items ENABLE ROW LEVEL SECURITY;
