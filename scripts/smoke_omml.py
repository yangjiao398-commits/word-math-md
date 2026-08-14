"""Create a minimal OMML docx and convert it."""

from __future__ import annotations

import zipfile
from pathlib import Path

from word_math_md.config import ConvertConfig
from word_math_md.pipeline import convert_docx_to_markdown

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
FIXTURES.mkdir(parents=True, exist_ok=True)

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""

DOC = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
  <w:body>
    <w:p><w:r><w:t>公式：</w:t></w:r>
      <m:oMath>
        <m:f>
          <m:num><m:r><m:t>a</m:t></m:r></m:num>
          <m:den><m:r><m:t>b</m:t></m:r></m:den>
        </m:f>
      </m:oMath>
    </w:p>
    <w:p><w:r><w:t>结束</w:t></w:r></w:p>
    <w:sectPr/>
  </w:body>
</w:document>
"""


def main() -> None:
    docx = FIXTURES / "sample_omml.docx"
    with zipfile.ZipFile(docx, "w") as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/document.xml", DOC)

    out_md = FIXTURES / "sample_omml.md"
    cfg = ConvertConfig(
        input_path=docx,
        output_path=out_md,
        image_dir=FIXTURES / "assets",
        clean_level="basic",
        backend="foss",
        debug=True,
        debug_dir=FIXTURES / ".debug",
    )
    ir = convert_docx_to_markdown(cfg)
    print(out_md.read_text(encoding="utf-8"))
    print("formulas:", {k: v.latex for k, v in ir.formulas.items()})


if __name__ == "__main__":
    main()
