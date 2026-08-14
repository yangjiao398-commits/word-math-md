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
