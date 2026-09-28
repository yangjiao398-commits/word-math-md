from pathlib import Path

from word_math_md.batch_import import (
    import_docx_pipeline,
    is_parsed_edition_docx,
    title_from_parsed_docx,
)


def test_is_parsed_edition_docx_keeps_originals_only():
    assert is_parsed_edition_docx("深圳实验高一数学（解析版）.docx")
    assert is_parsed_edition_docx(r"papers\\精品解析-期末-解析版.docx")
    assert not is_parsed_edition_docx("深圳实验高一数学（解析版）.doc")
    assert not is_parsed_edition_docx("深圳实验高一数学.docx")
    assert not is_parsed_edition_docx("深圳实验高一数学（解析版）.ole-latex.docx")
    assert not is_parsed_edition_docx("深圳实验高一数学（解析版）.ole-latex.preprocessed.docx")
    assert not is_parsed_edition_docx("~$深圳实验高一数学（解析版）.docx")
    assert not is_parsed_edition_docx("")


def test_title_from_parsed_docx_strips_edition_mark():
    assert (
        title_from_parsed_docx("深圳实验学校高中部2023-2024学年度第一学期第二阶段考试（解析版）.docx")
        == "深圳实验学校高中部2023-2024学年度第一学期第二阶段考试"
    )
    assert title_from_parsed_docx("阶段考(解析版).docx") == "阶段考"


def test_import_docx_pipeline_runs_steps_in_order(tmp_path, monkeypatch):
    src = tmp_path / "阶段考（解析版）.docx"
    src.write_bytes(b"docx")
    work = tmp_path / "work"
    order: list[str] = []

    def fake_ole(src_path, dest):
        order.append("ole")
        Path(dest).write_bytes(b"ole")
        return [{"latex": "x"}]

    def fake_prep(src_path, dest):
        order.append("prep")
        Path(dest).write_bytes(b"prep")
        return {"tabs_replaced": 1, "footers_cleared": 0, "empty_paragraphs_removed": 0}

    def fake_convert(src_path, dest_md):
        order.append("convert")
        Path(dest_md).write_text("# md\n", encoding="utf-8")
        return {"mathConverted": 3, "imageCount": 1, "warnings": []}

    def fake_import(path, **kwargs):
        order.append("import")
        assert path.name.endswith(".md")
        assert kwargs["title"] == "阶段考"
        assert kwargs["province"] == "广东"
        return {
            "paper_id": "p1",
            "paper_code": "code",
            "title": kwargs["title"],
            "question_count": 8,
            "asset_count": 1,
            "replaced": False,
            "questions": [],
        }

    monkeypatch.setattr("word_math_md.batch_import.convert_ole_docx", fake_ole)
    monkeypatch.setattr("word_math_md.batch_import.preprocess_docx", fake_prep)
    monkeypatch.setattr("word_math_md.batch_import.convert_docx_like_gaokao", fake_convert)
    monkeypatch.setattr("word_math_md.batch_import.import_markdown_file", fake_import)

    data = import_docx_pipeline(src, work_dir=work, province="广东")
    assert order == ["ole", "prep", "convert", "import"]
    assert data["steps"] == ["ole-to-latex", "preprocess", "convert-md", "import-bank"]
    assert data["question_count"] == 8
    assert data["ole_formulas"] == 1
    assert data["math_converted"] == 3
    assert data["title"] == "阶段考"
