-- PPT courseware linked to knowledge_points (multiple files per code).

CREATE TABLE IF NOT EXISTS knowledge_point_courseware (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  knowledge_code TEXT NOT NULL REFERENCES knowledge_points(code) ON DELETE CASCADE,
  title TEXT NOT NULL DEFAULT '',
  filename TEXT NOT NULL DEFAULT '',
  storage_key TEXT NOT NULL UNIQUE,
  mime_type TEXT,
  byte_size BIGINT NOT NULL DEFAULT 0,
  sort_order INT NOT NULL DEFAULT 0,
  extra JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS kpc_knowledge ON knowledge_point_courseware (knowledge_code, sort_order);
CREATE INDEX IF NOT EXISTS kpc_created ON knowledge_point_courseware (created_at DESC);

ALTER TABLE knowledge_point_courseware ENABLE ROW LEVEL SECURITY;
