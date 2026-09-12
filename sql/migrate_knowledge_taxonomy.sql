-- Add semester / major / minor to the knowledge-point dictionary.
-- Junction table question_knowledge_points stays as question ↔ code.

ALTER TABLE knowledge_points ADD COLUMN IF NOT EXISTS semester TEXT NOT NULL DEFAULT '';
ALTER TABLE knowledge_points ADD COLUMN IF NOT EXISTS major_category TEXT NOT NULL DEFAULT '';
ALTER TABLE knowledge_points ADD COLUMN IF NOT EXISTS minor_category TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS knowledge_points_semester ON knowledge_points (semester);
CREATE INDEX IF NOT EXISTS knowledge_points_major ON knowledge_points (major_category);
