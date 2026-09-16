from word_math_md.geogebra_pep import embed_url, infer_knowledge_codes, load_book, mapped_rows


def test_infer_set_operations():
    assert "1.3" in infer_knowledge_codes("集合与常用逻辑用语", "交集与并集的动态展示")
    assert "1.1" in infer_knowledge_codes("集合与常用逻辑用语", "集合的识别")
    assert "1.2" in infer_knowledge_codes("集合与常用逻辑用语", "根据包含关系求参数例2")
    assert "25" in infer_knowledge_codes("集合与常用逻辑用语", "集合的识别")


def test_infer_conic_and_misplaced_zero():
    assert infer_knowledge_codes("圆锥曲线的方程", "椭圆定义")[0] == "13.1"
    assert "20.2" in infer_knowledge_codes("圆锥曲线的方程", "椭圆定义")
    codes = infer_knowledge_codes("圆锥曲线的方程", "二分法求函数零点值")
    assert "4.5" in codes
    assert "13.1" not in codes
    assert "20.2" not in codes


def test_infer_space_vector():
    codes = infer_knowledge_codes("空间向量与立体几何", "1.4.6利用空间向量判断两直线垂直")
    assert "11.4" in codes
    assert "21.2" in codes


def test_mapped_rows_cover_book_pages():
    book = load_book(live=False)
    assert book["page_count"] >= 140
    rows = mapped_rows(live=False)
    page_ids = {row["page_id"] for row in rows}
    expected = {
        page["page_id"]
        for chapter in book["chapters"]
        for page in chapter["pages"]
        if page.get("page_id")
    }
    assert page_ids == expected
    assert all(row["knowledge_code"] and row["material_id"] for row in rows)


def test_embed_url_includes_canvas_size():
    url = embed_url("kxsba9qj", width=960, height=540)
    assert "/id/kxsba9qj/width/960/height/540/" in url
    assert "/sfsb/true/" in url
