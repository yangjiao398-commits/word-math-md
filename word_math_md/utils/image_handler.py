"""Image extraction and WMF/EMF conversion."""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from word_math_md.config import ConvertConfig
from word_math_md.core.parser import ImageRef

RASTER_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
VECTOR_EXTS = {".wmf", ".emf"}
# 2× 96dpi so glyphs stay sharp; CSS displays at 50%.
RASTER_SCALE = 2.0


def sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def pt_to_px(pt: float, scale: float = RASTER_SCALE) -> int:
    return max(1, int(round(float(pt) * 96.0 / 72.0 * scale)))


def _len_to_pt(value: float, unit: str | None) -> float:
    u = (unit or "pt").lower()
    if u == "px":
        return value * 72.0 / 96.0
    if u == "in":
        return value * 72.0
    if u == "cm":
        return value * 72.0 / 2.54
    if u == "mm":
        return value * 72.0 / 25.4
    if u == "emu":
        return value / 12700.0
    return value


def parse_shape_pt(style: str) -> tuple[float, float] | None:
    if not style:
        return None
    hm = re.search(r"height:\s*([0-9.]+)\s*(pt|px|in|cm|mm)?", style, re.I)
    wm = re.search(r"width:\s*([0-9.]+)\s*(pt|px|in|cm|mm)?", style, re.I)
    if not hm or not wm:
        return None
    h = _len_to_pt(float(hm.group(1)), hm.group(2))
    w = _len_to_pt(float(wm.group(1)), wm.group(2))
    if w <= 0 or h <= 0:
        return None
    return w, h


def collect_hash_pixel_sizes(docx_path: Path) -> dict[str, tuple[int, int]]:
    """Map sha1(media bytes) → PNG pixel size from Word layout (pt/EMU)."""
    import zipfile
    from xml.etree import ElementTree as ET

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    V = "urn:schemas-microsoft-com:vml"
    R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    A = "http://schemas.openxmlformats.org/drawingml/2006/main"
    WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
    out: dict[str, tuple[int, int]] = {}
    try:
        with zipfile.ZipFile(docx_path) as zf:
            rels: dict[str, str] = {}
            rel_path = "word/_rels/document.xml.rels"
            if rel_path in zf.namelist():
                rel_root = ET.fromstring(zf.read(rel_path))
                for rel in rel_root:
                    rid, target = rel.get("Id"), rel.get("Target")
                    if rid and target:
                        t = target.replace("\\", "/")
                        rels[rid] = t if t.startswith("word/") else "word/" + t.lstrip("/")
            xml = zf.read("word/document.xml")
            root = ET.fromstring(xml)
            r_id = f"{{{R}}}id"
            r_embed = f"{{{R}}}embed"

            def media_hash(part: str) -> str | None:
                try:
                    return sha1_bytes(zf.read(part))
                except KeyError:
                    return None

            for shape in root.iter(f"{{{V}}}shape"):
                pts = parse_shape_pt(shape.get("style") or "")
                if not pts:
                    continue
                w_pt, h_pt = pts
                for im in shape.iter(f"{{{V}}}imagedata"):
                    rid = im.get(r_id) or im.get("r:id")
                    if not rid or rid not in rels:
                        continue
                    key = media_hash(rels[rid])
                    if key:
                        out[key] = (pt_to_px(w_pt), pt_to_px(h_pt))

            emu_per_pt = 12700.0
            for ext in list(root.iter(f"{{{WP}}}extent")):
                try:
                    cx = int(ext.get("cx") or 0)
                    cy = int(ext.get("cy") or 0)
                except ValueError:
                    continue
                if cx <= 0 or cy <= 0:
                    continue
                parent = None
                # find enclosing inline/anchor by walking... ElementTree has no parent.
                # handled below via inline/anchor iteration

            for wrap in list(root.iter(f"{{{WP}}}inline")) + list(root.iter(f"{{{WP}}}anchor")):
                ext_el = wrap.find(f"{{{WP}}}extent")
                if ext_el is None:
                    continue
                try:
                    cx = int(ext_el.get("cx") or 0)
                    cy = int(ext_el.get("cy") or 0)
                except ValueError:
                    continue
                blip = None
                for b in wrap.iter(f"{{{A}}}blip"):
                    blip = b
                    break
                if blip is None:
                    continue
                rid = blip.get(r_embed) or blip.get("r:embed")
                if not rid or rid not in rels:
                    continue
                key = media_hash(rels[rid])
                if key:
                    out[key] = (pt_to_px(cx / emu_per_pt), pt_to_px(cy / emu_per_pt))
    except Exception:
        return out
    return out


def extract_and_convert_images(docx_path: Path, config: ConvertConfig) -> dict[str, ImageRef]:
    """Extract media from docx; convert WMF/EMF to PNG when possible."""
    config.image_dir.mkdir(parents=True, exist_ok=True)
    images: dict[str, ImageRef] = {}
    index = 1

    with zipfile.ZipFile(docx_path, "r") as zf:
        media = [n for n in zf.namelist() if n.replace("\\", "/").startswith("word/media/")]
        media.sort()
        vectors: list[tuple[str, bytes, str]] = []  # name, data, image_id
        for name in media:
            raw = zf.read(name)
            original = Path(name).name
            if not original or original in {".", ".."}:
                continue
            ext = Path(original).suffix.lower()
            image_id = f"{index:03d}"
            if ext in VECTOR_EXTS:
                vectors.append((original, raw, image_id))
            elif ext in RASTER_EXTS or ext == ".svg":
                out_ext = ".jpg" if ext in {".jpg", ".jpeg"} else (ext if ext else ".png")
                out_path = config.image_dir / f"image{image_id}{out_ext}"
                out_path.write_bytes(raw)
                images[image_id] = ImageRef(
                    image_id=image_id, path=out_path, original_name=original
                )
            else:
                out_path = config.image_dir / f"image{image_id}{ext or '.bin'}"
                out_path.write_bytes(raw)
                images[image_id] = ImageRef(
                    image_id=image_id, path=out_path, original_name=original
                )
            index += 1

        if vectors:
            sizes = collect_hash_pixel_sizes(docx_path)
            png_map = batch_convert_vectors_to_png([d for _, d, _ in vectors], sizes)
            for original, raw, image_id in vectors:
                key = sha1_bytes(raw)
                out_path = config.image_dir / f"image{image_id}.png"
                png = png_map.get(key)
                if png:
                    out_path.write_bytes(png)
                else:
                    # fallback keep original
                    out_path = config.image_dir / f"image{image_id}{Path(original).suffix.lower()}"
                    out_path.write_bytes(raw)
                images[image_id] = ImageRef(
                    image_id=image_id, path=out_path, original_name=original
                )
    return images


def batch_convert_vectors_to_png(
    blobs: list[bytes],
    pixel_sizes: dict[str, tuple[int, int]] | None = None,
) -> dict[str, bytes]:
    """Convert many WMF/EMF buffers → PNG bytes keyed by sha1.

    pixel_sizes: optional sha1 → (width_px, height_px) from Word layout.
    """
    result: dict[str, bytes] = {}
    if not blobs:
        return result

    unique: dict[str, bytes] = {}
    for b in blobs:
        unique[sha1_bytes(b)] = b
    pixel_sizes = pixel_sizes or {}

    with tempfile.TemporaryDirectory(prefix="word-math-wmf-") as tmp:
        tmp_path = Path(tmp)
        for h, data in unique.items():
            ext = ".emf" if data[:4] == b"\x01\x00\x00\x00" else ".wmf"
            (tmp_path / f"{h}{ext}").write_bytes(data)
            if h in pixel_sizes:
                w, ht = pixel_sizes[h]
                (tmp_path / f"{h}.size").write_text(f"{int(w)},{int(ht)}", encoding="ascii")

        if _windows_batch_metafile_to_png(tmp_path):
            for png in tmp_path.glob("*.png"):
                result[png.stem] = png.read_bytes()
            if result:
                return result

        if shutil.which("magick"):
            for h, data in unique.items():
                ext = ".emf" if data[:4] == b"\x01\x00\x00\x00" else ".wmf"
                src = tmp_path / f"{h}{ext}"
                out = tmp_path / f"{h}.png"
                try:
                    subprocess.run(
                        [
                            "magick",
                            "convert",
                            "-density",
                            "192",
                            "-background",
                            "white",
                            "-flatten",
                            str(src),
                            str(out),
                        ],
                        check=True,
                        capture_output=True,
                        timeout=60,
                    )
                    if out.exists():
                        result[h] = out.read_bytes()
                except Exception:
                    pass
    return result


def convert_vector_to_png(
    data: bytes,
    ext: str,
    out_path: Path,
    pixel_size: tuple[int, int] | None = None,
) -> bool:
    """Convert a single WMF/EMF buffer to PNG."""
    sizes = {sha1_bytes(data): pixel_size} if pixel_size else None
    mapped = batch_convert_vectors_to_png([data], sizes)
    key = sha1_bytes(data)
    if key in mapped:
        out_path.write_bytes(mapped[key])
        return True

    tmp = out_path.with_suffix(ext)
    try:
        tmp.write_bytes(data)
        if shutil.which("magick"):
            try:
                subprocess.run(
                    [
                        "magick",
                        "convert",
                        "-density",
                        "200",
                        "-background",
                        "white",
                        "-flatten",
                        str(tmp),
                        str(out_path),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
                if out_path.exists() and out_path.stat().st_size > 0:
                    return True
            except Exception:
                pass
        return False
    finally:
        if tmp.exists() and tmp != out_path:
            try:
                tmp.unlink()
            except OSError:
                pass


def _windows_batch_metafile_to_png(dir_path: Path) -> bool:
    try:
        import platform

        if platform.system() != "Windows":
            return False
        d = str(dir_path).replace("'", "''")
        ps = f"""
$ErrorActionPreference = 'Continue'
Add-Type -AssemblyName System.Drawing
$dir = '{d}'
function Convert-One([string]$src) {{
  $out = [System.IO.Path]::ChangeExtension($src, '.png')
  $img = $null; $bmp = $null; $g = $null
  try {{
    $img = [System.Drawing.Image]::FromFile($src)
    $w = [Math]::Max(1, [int]$img.Width)
    $h = [Math]::Max(1, [int]$img.Height)
    $nw = $w
    $nh = $h
    $sizeFile = [System.IO.Path]::ChangeExtension($src, '.size')
    if (Test-Path -LiteralPath $sizeFile) {{
      $pair = ((Get-Content -Raw -LiteralPath $sizeFile).Trim() -split ',')
      if ($pair.Length -ge 2) {{
        $nw = [Math]::Max(1, [int]$pair[0])
        $nh = [Math]::Max(1, [int]$pair[1])
      }}
    }} else {{
      # Keep native GDI size; only shrink pathological metafiles.
      if ($nh -gt 240 -or $nw -gt 1200) {{
        $s = [Math]::Min(240.0 / $nh, 1200.0 / $nw)
        $nw = [Math]::Max(1, [int][Math]::Round($w * $s))
        $nh = [Math]::Max(1, [int][Math]::Round($h * $s))
      }}
    }}
    $bmp = New-Object System.Drawing.Bitmap $nw, $nh
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.Clear([System.Drawing.Color]::White)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.DrawImage($img, 0, 0, $nw, $nh)
    $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
  }} catch {{
  }} finally {{
    if ($g) {{ $g.Dispose() }}
    if ($bmp) {{ $bmp.Dispose() }}
    if ($img) {{ $img.Dispose() }}
  }}
}}
Get-ChildItem -LiteralPath $dir -File | Where-Object {{ $_.Extension -match '\\.(wmf|emf)$' }} | ForEach-Object {{
  Convert-One $_.FullName
}}
"""
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True,
            timeout=600,
        )
        return r.returncode == 0 and any(dir_path.glob("*.png"))
    except Exception:
        return False


def rewrite_markdown_images(markdown: str, images: dict[str, ImageRef], image_dir_name: str) -> str:
    """Normalize image links to image_dir_name/imageNNN.ext.

    Leave formulaNNN.png (MathType exports) untouched.
    """
    by_name = {img.original_name.lower(): img for img in images.values()}
    by_stem = {Path(img.original_name).stem.lower(): img for img in images.values()}

    def repl(match: re.Match) -> str:
        alt = match.group(1) or ""
        url = match.group(2).strip()
        path_part = url.split()[0].strip("\"'")
        norm = path_part.replace("\\", "/")
        base = Path(norm).name
        # MathType formula images already correct
        if re.match(r"(formula|glyph)\d+\.(png|wmf|emf)$", base, re.I):
            if not norm.startswith(image_dir_name + "/") and "/" not in norm:
                return f"![{alt}]({image_dir_name}/{base})"
            return match.group(0)

        img = by_name.get(base.lower()) or by_stem.get(Path(base).stem.lower())
        if img is None:
            m = re.search(r"image(\d+)", base, re.I)
            if m:
                key = f"{int(m.group(1)):03d}"
                img = images.get(key) or images.get(m.group(1).zfill(3))
        if img is None:
            return match.group(0)
        rel = f"{image_dir_name}/{img.path.name}".replace("\\", "/")
        return f"![{alt}]({rel})"

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", repl, markdown)
