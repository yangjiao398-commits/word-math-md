from word_math_md.gaokao_knowledge_data import GAOKAO_KNOWLEDGE_POINTS
from word_math_md.knowledge_catalog import parse_catalog_text


def test_parse_catalog_one_per_line():
    items = parse_catalog_text("1.1 集合的含义\n1.2 集合间的基本关系\n")
    assert [(i.code, i.description) for i in items] == [
        ("1.1", "集合的含义"),
        ("1.2", "集合间的基本关系"),
    ]


def test_parse_catalog_skips_blank_and_comment():
    items = parse_catalog_text("# 必修一\n\n2.1 函数的概念\n")
    assert [i.code for i in items] == ["2.1"]


def test_gaokao_catalog_unique_codes():
    codes = [row[0] for row in GAOKAO_KNOWLEDGE_POINTS]
    assert len(codes) == 89
    assert len(set(codes)) == 89
    assert codes[0] == "1.1"
    assert codes[-1] == "26"
