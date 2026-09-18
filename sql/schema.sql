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
  semester TEXT NOT NULL DEFAULT '',
  exam_type TEXT NOT NULL DEFAULT '',
  province TEXT NOT NULL DEFAULT '',
  gaokao_paper TEXT NOT NULL DEFAULT '',
  extra JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE papers ADD COLUMN IF NOT EXISTS semester TEXT NOT NULL DEFAULT '';
ALTER TABLE papers ADD COLUMN IF NOT EXISTS exam_type TEXT NOT NULL DEFAULT '';
ALTER TABLE papers ADD COLUMN IF NOT EXISTS province TEXT NOT NULL DEFAULT '';
ALTER TABLE papers ADD COLUMN IF NOT EXISTS gaokao_paper TEXT NOT NULL DEFAULT '';
ALTER TABLE papers DROP CONSTRAINT IF EXISTS papers_semester_check;
ALTER TABLE papers ADD CONSTRAINT papers_semester_check
  CHECK (semester = '' OR semester IN (
    '高一上学期','高一下学期','高二上学期','高二下学期','高三上学期','高三下学期'
  ));
ALTER TABLE papers DROP CONSTRAINT IF EXISTS papers_exam_type_check;
ALTER TABLE papers ADD CONSTRAINT papers_exam_type_check
  CHECK (exam_type = '' OR exam_type IN ('月考','期中','期末'));
ALTER TABLE papers DROP CONSTRAINT IF EXISTS papers_province_check;
ALTER TABLE papers ADD CONSTRAINT papers_province_check
  CHECK (province = '' OR province IN (
    '北京','天津','河北','山西','内蒙古','辽宁','吉林','黑龙江',
    '上海','江苏','浙江','安徽','福建','江西','山东','河南',
    '湖北','湖南','广东','广西','海南','重庆','四川','贵州',
    '云南','西藏','陕西','甘肃','青海','宁夏','新疆'
  ));
ALTER TABLE papers DROP CONSTRAINT IF EXISTS papers_gaokao_paper_check;
ALTER TABLE papers ADD CONSTRAINT papers_gaokao_paper_check
  CHECK (gaokao_paper = '' OR gaokao_paper IN ('全国A卷','全国B卷'));
CREATE INDEX IF NOT EXISTS papers_province ON papers (province);
CREATE INDEX IF NOT EXISTS papers_gaokao_paper ON papers (gaokao_paper);

CREATE TABLE IF NOT EXISTS knowledge_points (
  code TEXT PRIMARY KEY,
  description TEXT NOT NULL,
  semester TEXT NOT NULL DEFAULT '',
  major_category TEXT NOT NULL DEFAULT '',
  minor_category TEXT NOT NULL DEFAULT '',
  sort_order INT NOT NULL DEFAULT 0,
  extra JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE knowledge_points ADD COLUMN IF NOT EXISTS semester TEXT NOT NULL DEFAULT '';
ALTER TABLE knowledge_points ADD COLUMN IF NOT EXISTS major_category TEXT NOT NULL DEFAULT '';
ALTER TABLE knowledge_points ADD COLUMN IF NOT EXISTS minor_category TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS knowledge_points_semester ON knowledge_points (semester);
CREATE INDEX IF NOT EXISTS knowledge_points_major ON knowledge_points (major_category);

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
  knowledge_codes TEXT[] NOT NULL DEFAULT '{}',
  extra JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (paper_id, question_no)
);

-- Existing databases created before knowledge_codes was added.
ALTER TABLE questions ADD COLUMN IF NOT EXISTS knowledge_codes TEXT[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS questions_paper_order ON questions (paper_id, sort_order);
CREATE INDEX IF NOT EXISTS questions_type ON questions (type_code);
CREATE INDEX IF NOT EXISTS questions_knowledge_codes ON questions USING GIN (knowledge_codes);

CREATE TABLE IF NOT EXISTS question_knowledge_points (
  question_id UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  knowledge_code TEXT NOT NULL REFERENCES knowledge_points(code),
  sort_order INT NOT NULL DEFAULT 0,
  PRIMARY KEY (question_id, knowledge_code)
);

CREATE INDEX IF NOT EXISTS qkp_knowledge ON question_knowledge_points (knowledge_code);

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

CREATE TABLE IF NOT EXISTS app_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone TEXT NOT NULL UNIQUE,
  nickname TEXT NOT NULL DEFAULT '',
  extra JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_memberships (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  plan TEXT NOT NULL DEFAULT 'trial',
  status TEXT NOT NULL DEFAULT 'active',
  expires_at TIMESTAMPTZ,
  extra JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS app_memberships_user ON app_memberships (user_id, expires_at DESC);

CREATE TABLE IF NOT EXISTS app_devices (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  platform TEXT NOT NULL,
  vendor TEXT NOT NULL DEFAULT '',
  push_token TEXT NOT NULL,
  extra JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS app_devices_user ON app_devices (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS app_devices_token ON app_devices (user_id, push_token);

CREATE TABLE IF NOT EXISTS app_orders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  plan TEXT NOT NULL,
  amount_fen INT NOT NULL DEFAULT 0,
  channel TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'created',
  extra JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  paid_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS app_orders_user ON app_orders (user_id, created_at DESC);

ALTER TABLE papers ENABLE ROW LEVEL SECURITY;
ALTER TABLE questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE question_options ENABLE ROW LEVEL SECURITY;
ALTER TABLE assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE question_types ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_points ENABLE ROW LEVEL SECURITY;
ALTER TABLE question_knowledge_points ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_geogebra_animations ENABLE ROW LEVEL SECURITY;
ALTER TABLE answer_sheets ENABLE ROW LEVEL SECURITY;
ALTER TABLE answer_sheet_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_orders ENABLE ROW LEVEL SECURITY;

-- Backend uses the service role (bypasses RLS). Anon has no table access.
