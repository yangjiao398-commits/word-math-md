-- Saved whole-paper variants. One variant paper per source paper.
-- Apply with: python scripts/apply_sql.py sql/migrate_variant_papers.sql

CREATE TABLE IF NOT EXISTS variant_papers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_paper_id UUID NOT NULL UNIQUE REFERENCES papers(id) ON DELETE CASCADE,
  paper_code TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  source_filename TEXT,
  source_md TEXT NOT NULL DEFAULT '',
  semester TEXT NOT NULL DEFAULT '',
  exam_type TEXT NOT NULL DEFAULT '',
  province TEXT NOT NULL DEFAULT '',
  gaokao_paper TEXT NOT NULL DEFAULT '',
  question_count INT NOT NULL DEFAULT 0,
  ready_count INT NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'partial',
  extra JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (status IN ('partial', 'complete'))
);

CREATE INDEX IF NOT EXISTS variant_papers_updated ON variant_papers (updated_at DESC);

CREATE TABLE IF NOT EXISTS variant_questions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  variant_paper_id UUID NOT NULL REFERENCES variant_papers(id) ON DELETE CASCADE,
  source_question_id UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  question_no INT NOT NULL,
  sort_order INT NOT NULL,
  type_code TEXT NOT NULL REFERENCES question_types(code),
  stem_md TEXT NOT NULL DEFAULT '',
  stem_text TEXT NOT NULL DEFAULT '',
  score NUMERIC(6,2),
  answer_md TEXT NOT NULL DEFAULT '',
  analysis_md TEXT NOT NULL DEFAULT '',
  solution_md TEXT NOT NULL DEFAULT '',
  options JSONB NOT NULL DEFAULT '[]'::jsonb,
  point TEXT NOT NULL DEFAULT '',
  essence TEXT NOT NULL DEFAULT '',
  axis TEXT NOT NULL DEFAULT '',
  changes JSONB NOT NULL DEFAULT '[]'::jsonb,
  supported BOOLEAN NOT NULL DEFAULT false,
  message TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT '',
  knowledge_codes TEXT[] NOT NULL DEFAULT '{}',
  extra JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (variant_paper_id, source_question_id),
  UNIQUE (variant_paper_id, question_no)
);

CREATE INDEX IF NOT EXISTS variant_questions_paper_order
  ON variant_questions (variant_paper_id, sort_order);

ALTER TABLE variant_papers ENABLE ROW LEVEL SECURITY;
ALTER TABLE variant_questions ENABLE ROW LEVEL SECURITY;
