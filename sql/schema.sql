-- Exam bank for word-math-md Markdown papers.
-- Apply on Supabase (SQL editor or scripts/setup_supabase.py).

CREATE TABLE IF NOT EXISTS question_types (
  code TEXT PRIMARY KEY,
  name_zh TEXT NOT NULL,
  has_options BOOLEAN NOT NULL DEFAULT false,
  sort_order INT NOT NULL
);

INSERT INTO question_types (code, name_zh, has_options, sort_order) VALUES
  ('single_choice', '单选题', true, 1),
  ('multi_choice',  '多选题', true, 2),
  ('fill_blank',    '填空题', false, 3),
  ('solution',      '解答题', false, 4)
ON CONFLICT (code) DO UPDATE SET
  name_zh = EXCLUDED.name_zh,
  has_options = EXCLUDED.has_options,
  sort_order = EXCLUDED.sort_order;

CREATE TABLE IF NOT EXISTS papers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_code TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  source_filename TEXT,
  source_md TEXT,
  extra JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS questions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_id UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  question_no INT NOT NULL,
  sort_order INT NOT NULL,
  type_code TEXT NOT NULL REFERENCES question_types(code),
  stem_md TEXT NOT NULL DEFAULT '',
  stem_text TEXT NOT NULL DEFAULT '',
  score NUMERIC(6,2),
  answer_md TEXT NOT NULL DEFAULT '',
  analysis_md TEXT NOT NULL DEFAULT '',
  solution_md TEXT NOT NULL DEFAULT '',
  extra JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (paper_id, question_no)
);

CREATE INDEX IF NOT EXISTS questions_paper_order ON questions (paper_id, sort_order);
CREATE INDEX IF NOT EXISTS questions_type ON questions (type_code);

CREATE TABLE IF NOT EXISTS question_options (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  question_id UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  label TEXT NOT NULL,
  content_md TEXT NOT NULL DEFAULT '',
  sort_order INT NOT NULL,
  extra JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (question_id, label)
);

CREATE TABLE IF NOT EXISTS assets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_id UUID REFERENCES papers(id) ON DELETE CASCADE,
  question_id UUID REFERENCES questions(id) ON DELETE SET NULL,
  option_id UUID REFERENCES question_options(id) ON DELETE SET NULL,
  storage_key TEXT NOT NULL UNIQUE,
  mime_type TEXT,
  sha1 TEXT,
  alt TEXT
);

CREATE INDEX IF NOT EXISTS assets_sha1 ON assets (sha1);

ALTER TABLE papers ENABLE ROW LEVEL SECURITY;
ALTER TABLE questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE question_options ENABLE ROW LEVEL SECURITY;
ALTER TABLE assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE question_types ENABLE ROW LEVEL SECURITY;

-- Backend uses the service role (bypasses RLS). Anon has no table access.
