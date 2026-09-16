-- Knowledge point ↔ GeoGebra 人教配套册 animation mapping.
-- Safe to re-run.

CREATE TABLE IF NOT EXISTS knowledge_geogebra_animations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  knowledge_code TEXT NOT NULL REFERENCES knowledge_points(code) ON DELETE CASCADE,
  book_id TEXT NOT NULL DEFAULT 'dyetmjzr',
  page_id TEXT NOT NULL,
  material_id TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  chapter_title TEXT NOT NULL DEFAULT '',
  chapter_id TEXT NOT NULL DEFAULT '',
  thumb_url TEXT NOT NULL DEFAULT '',
  sort_order INT NOT NULL DEFAULT 0,
  extra JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (knowledge_code, book_id, page_id)
);

CREATE INDEX IF NOT EXISTS kga_knowledge ON knowledge_geogebra_animations (knowledge_code);
CREATE INDEX IF NOT EXISTS kga_page ON knowledge_geogebra_animations (page_id);
CREATE INDEX IF NOT EXISTS kga_book ON knowledge_geogebra_animations (book_id);

ALTER TABLE knowledge_geogebra_animations ENABLE ROW LEVEL SECURITY;
