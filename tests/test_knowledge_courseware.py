import pytest

from word_math_md.knowledge_courseware import _safe_filename, serialize_courseware


def test_safe_filename_accepts_pptx():
    assert _safe_filename("第一章.pptx") == "第一章.pptx"


def test_safe_filename_rejects_pdf():
    with pytest.raises(ValueError, match="ppt"):
        _safe_filename("notes.pdf")


def test_serialize_courseware_builds_office_view():
    row = serialize_courseware(
        {
            "id": "00000000-0000-4000-8000-000000000001",
            "knowledge_code": "1.1",
            "title": "集合",
            "filename": "set.pptx",
            "storage_key": "knowledge-ppt/abc/file.pptx",
            "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "byte_size": 1024,
            "sort_order": 0,
        }
    )
    assert row["knowledge_code"] == "1.1"
    assert "storage/v1/object/public" in row["public_url"]
    assert row["office_view_url"].startswith("https://view.officeapps.live.com/op/embed.aspx?src=")
