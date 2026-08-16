"""Basic unit tests for OMML → LaTeX and postprocess."""

from word_math_md.core.postprocess import postprocess_markdown
from word_math_md.config import ConvertConfig
from word_math_md.utils.math_handler import omml_element_to_latex, placeholder_for, apply_formula_placeholders
from word_math_md.core.parser import FormulaRef
from pathlib import Path
from xml.etree import ElementTree as ET

MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def test_omml_fraction():
    xml = f"""
    <m:oMath xmlns:m="{MATH_NS}">
      <m:f>
        <m:num><m:r><m:t>a</m:t></m:r></m:num>
        <m:den><m:r><m:t>b</m:t></m:r></m:den>
      </m:f>
    </m:oMath>
    """
    el = ET.fromstring(xml)
    assert "dfrac" in omml_element_to_latex(el)
    assert "a" in omml_element_to_latex(el)
    assert "b" in omml_element_to_latex(el)


def test_placeholder_replace():
    ref = FormulaRef(formula_id="001", latex="x^2", display=False, placeholder=placeholder_for("001"))
    md = f"见 {ref.placeholder} 式"
    cfg = ConvertConfig(input_path=Path("a.docx"), output_path=Path("a.md"))
    out = apply_formula_placeholders(md, {"001": ref}, cfg)
    assert "$x^2$" in out


def test_postprocess_blank_lines():
    cfg = ConvertConfig(input_path=Path("a.docx"), output_path=Path("a.md"))
    md = "# 标题\n\n\n\n段落  \n"
    out = postprocess_markdown(md, cfg)
    assert "\n\n\n" not in out
    assert out.endswith("\n")


def test_inspect_omml_fixture():
    from word_math_md.inspect import inspect_docx

    fixture = Path(__file__).parent / "fixtures" / "sample_omml.docx"
    if not fixture.exists():
        return
    data = inspect_docx(fixture)
    kinds = {t["kind"]: t["count"] for t in data["math"]["types"]}
    assert kinds.get("omml_inline", 0) + kinds.get("omml_display", 0) >= 1
    assert isinstance(data["structure"]["rows"], list)
    assert data["file_name"].endswith(".docx")


def test_ole_extract_from_synthetic_docx(tmp_path):
    import zipfile
    from word_math_md.ole_to_latex import docx_extract_mt_formulas, format_formula_list

    doc_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:o="urn:schemas-microsoft-com:office:office"
            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <w:body>
    <w:p>
      <w:r>
        <w:object>
          <o:OLEObject Type="Embed" ProgID="Equation.DSMT4" r:id="rId8"/>
        </w:object>
      </w:r>
    </w:p>
  </w:body>
</w:document>
"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId8" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject" Target="embeddings/oleObject1.bin"/>
</Relationships>
"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="bin" ContentType="application/vnd.openxmlformats-officedocument.oleObject"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""
    docx = tmp_path / "ole.docx"
    with zipfile.ZipFile(docx, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("word/document.xml", doc_xml)
        zf.writestr("word/_rels/document.xml.rels", rels)
        zf.writestr("word/embeddings/oleObject1.bin", b"not-an-ole")

    original = docx.read_bytes()
    res = docx_extract_mt_formulas(docx)
    assert len(res) == 1
    assert res[0]["latex"] == "【无法提取】"
    text = format_formula_list(res)
    assert "公式 1" in text
    assert "【无法提取】" in text
    assert docx.read_bytes() == original

    from word_math_md.ole_to_latex import convert_ole_docx

    out = tmp_path / "ole.ole-latex.docx"
    convert_ole_docx(docx, out)
    assert docx.read_bytes() == original
    assert out.exists()
    with zipfile.ZipFile(out) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    assert "OLEObject" not in xml
    assert "$【无法提取】$" in xml


def test_mtef_equation_native_to_latex():
    from word_math_md.ole_to_latex import _convert_ole_bytes

    one = Path(__file__).parent / "fixtures" / "oleObject101.bin"
    first = Path(__file__).parent / "fixtures" / "oleObject1.bin"
    if not one.exists():
        return
    r1 = _convert_ole_bytes(one.read_bytes(), one.name)
    assert r1["latex"] == "1"
    r2 = _convert_ole_bytes(first.read_bytes(), first.name)
    assert r"x ^ { 2 }" in r2["latex"] or "x^{2}" in r2["latex"].replace(" ", "")
    assert "【无法提取】" not in r2["latex"]
    assert r"\le" in r2["latex"] or "A=" in r2["latex"]
