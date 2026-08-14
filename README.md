# word-math-md（MathDoc Converter）

将含 **OMML / MathType(Equation.DSMT)** 数学公式与 **WMF/EMF** 矢量图的复杂 Word（`.docx`）转为干净的 **Markdown + LaTeX**。

默认 Web 端口：**3010**

## 功能

- 清理：批注、修订、页眉页脚、分页、隐藏文本、空段落等
- 公式：OfficeMath(OMML) → `$...$` / `$$...$$`；MathType OLE 可降级为图片/占位
- 图片：PNG/JPG 导出；WMF/EMF 尽量转 PNG（ImageMagick / Pillow / Windows GDI）
- 输出：规范 Markdown + `assets/` 图片目录

## 架构

```
Cleaner → Parser(IR) → Converter → PostProcessor
              ↑              ↑
        math_handler   image_handler
```

## 安装

```bash
cd word-math-md
python -m venv .venv

# Windows
.venv\Scripts\activate
pip install -e .

# 可选：Aspose.Words（商业许可，更强 Word 清理/导出）
# pip install aspose-words
# 将许可证放到 Aspose.Words.lic 或设置 ASPOSE_WORDS_LICENSE
```

无 Aspose 时自动使用 **FOSS** 路径（OpenXML 清理 + mammoth）。

## 命令行

```bash
# 单文件
word-math-md paper.docx -o paper.md --image-dir assets

# 或
python cli.py paper.docx -o paper.md -i assets --debug

# 批量
word-math-md ./papers -o ./md_out --recursive --clean-level aggressive
```

主要参数：

| 参数 | 说明 |
|------|------|
| `-o` | 输出 Markdown 路径 |
| `--image-dir` / `-i` | 图片目录 |
| `--math-format` | `latex`（默认） |
| `--clean-level` | `none` / `basic` / `aggressive` |
| `--math-fallback` | `image` / `code` / `placeholder` |
| `--backend` | `auto` / `aspose` / `foss` |
| `--debug` | 写出 `clean.docx`、`raw.md` 等中间文件 |

## Web 服务（端口 3010）

```bash
python server.py
# 或
uvicorn word_math_md.server:app --host 0.0.0.0 --port 3010
```

打开 http://127.0.0.1:3010 ：

- 页面上传转换
- `POST /api/convert` 返回预览与 ZIP 下载链接
- `GET /health` 健康检查

## Python 库调用

```python
from pathlib import Path
from word_math_md import convert_docx_to_markdown
from word_math_md.config import ConvertConfig

cfg = ConvertConfig(
    input_path=Path("paper.docx"),
    output_path=Path("paper.md"),
    image_dir=Path("assets"),
)
ir = convert_docx_to_markdown(cfg)
print(len(ir.formulas), len(ir.images))
```

## 目录结构

```
word-math-md/
├── cli.py
├── server.py                 # 端口 3010
├── word_math_md/
│   ├── cli.py
│   ├── server.py
│   ├── pipeline.py
│   ├── config.py
│   ├── core/
│   │   ├── cleaner.py
│   │   ├── parser.py
│   │   ├── converter.py
│   │   └── postprocess.py
│   └── utils/
│       ├── image_handler.py
│       └── math_handler.py
└── tests/
```

## 公式说明

| 来源 | 处理 |
|------|------|
| OMML (`oMath`) | 内置转换器 → LaTeX |
| MathType OLE (`Equation.DSMT4` 等) | 占位；无 SDK 时按 `--math-fallback` 降级 |
| 公式图 (WMF/EMF) | 转 PNG 后以 `![](assets/...)` 引用 |

后续可接入 MathType SDK / Mathpix 等提升 OLE 公式还原率。

## License

MIT
