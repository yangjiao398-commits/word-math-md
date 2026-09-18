-- Add province and gaokao national paper (A/B) to papers.
-- Safe to re-run.

ALTER TABLE papers ADD COLUMN IF NOT EXISTS province TEXT NOT NULL DEFAULT '';
ALTER TABLE papers ADD COLUMN IF NOT EXISTS gaokao_paper TEXT NOT NULL DEFAULT '';

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
