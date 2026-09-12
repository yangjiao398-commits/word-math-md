-- Incremental migration for existing exam-bank databases.
-- Safe to re-run. New installs can just apply sql/schema.sql.

CREATE TABLE IF NOT EXISTS knowledge_points (
  code TEXT PRIMARY KEY,
  description TEXT NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  extra JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE questions ADD COLUMN IF NOT EXISTS knowledge_codes TEXT[] NOT NULL DEFAULT '{}';
CREATE INDEX IF NOT EXISTS questions_knowledge_codes ON questions USING GIN (knowledge_codes);

CREATE TABLE IF NOT EXISTS question_knowledge_points (
  question_id UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  knowledge_code TEXT NOT NULL REFERENCES knowledge_points(code),
  sort_order INT NOT NULL DEFAULT 0,
  PRIMARY KEY (question_id, knowledge_code)
);

CREATE INDEX IF NOT EXISTS qkp_knowledge ON question_knowledge_points (knowledge_code);

ALTER TABLE knowledge_points ENABLE ROW LEVEL SECURITY;
ALTER TABLE question_knowledge_points ENABLE ROW LEVEL SECURITY;
