"""Author plane-engine solution scenes without hand-writing a file per question."""

from __future__ import annotations

import math
import json
import re
from pathlib import Path
from typing import Any

STATIC_DIR = Path(__file__).resolve().parent / "static"
AUTHORED_DIR = STATIC_DIR / "scenes" / "authored"
CATALOG_PATH = STATIC_DIR / "scenes" / "plane-catalog.json"

_UUID = re.compile(r"^[0-9a-fA-F-]{36}$")
_FORMULA = re.compile(r"\$\$([\s\S]+?)\$\$|\$([^$]+)\$")
_TAG = re.compile(r"<[^>]+>")
_PRESETS = {
    "square",
    "quadratic",
    "exponential",
    "reciprocal",
    "fraction-exp",
    "linear-reciprocal",
}

BUILTIN_LESSONS: dict[str, dict[str, str]] = {
    "ac94d186-2233-4a03-ae46-88e390073595": {
        "title": "第1题 · 全称命题的否定",
        "href": "/static/plane-sz-q1.html?embed=1",
    },
    "c9a09c8c-1e42-4907-9f4a-80770c2048a5": {
        "title": "第2题 · 分段函数求值",
        "href": "/static/plane-sz-q2.html?embed=1",
    },
    "d793894c-ce81-4d98-9f85-a98f435c1ea4": {
        "title": "第3题 · 二次不等式与根的分布",
        "href": "/static/plane-sz-q3.html?embed=1",
    },
    "4129cbd6-c865-4b57-8d48-3c1b6a0ab0c8": {
        "title": "第7题 · 奇函数与基本不等式",
        "href": "/static/plane-sz-q7.html?embed=1&v=2",
    },
    "fbd83a00-ed11-4ede-979d-d40caefa79df": {
        "title": "第16题 · 幂函数与奇函数单调性",
        "href": "/static/plane-sz-q16.html?embed=1",
    },
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def player_href(question_id: str) -> str:
    return (
        "/static/plane-player.html?scene="
        + f"/static/scenes/authored/{question_id}.json"
        + "&embed=1"
    )


def load_lessons() -> dict[str, dict[str, str]]:
    lessons = dict(BUILTIN_LESSONS)
    if CATALOG_PATH.is_file():
        raw = _read_json(CATALOG_PATH).get("lessons") or {}
        if isinstance(raw, dict):
            for key, item in raw.items():
                if _UUID.match(str(key)) and isinstance(item, dict) and item.get("href"):
                    lessons[str(key)] = {
                        "title": str(item.get("title") or "解题过程"),
                        "href": str(item["href"]),
                    }
    return lessons


def load_scene(question_id: str) -> dict[str, Any] | None:
    path = AUTHORED_DIR / f"{_require_id(question_id)}.json"
    if not path.is_file():
        return None
    return _read_json(path)


def save_scene(question_id: str, scene: dict[str, Any], *, title: str) -> dict[str, str]:
    qid = _require_id(question_id)
    cleaned = validate_scene(scene)
    _write_json(AUTHORED_DIR / f"{qid}.json", cleaned)
    catalog: dict[str, Any] = {"lessons": {}}
    if CATALOG_PATH.is_file():
        loaded = _read_json(CATALOG_PATH)
        if isinstance(loaded.get("lessons"), dict):
            catalog = loaded
    lesson = {"title": (title or cleaned.get("title") or "解题过程").strip()[:80], "href": player_href(qid)}
    catalog.setdefault("lessons", {})[qid] = lesson
    _write_json(CATALOG_PATH, catalog)
    return lesson


def _require_id(question_id: str) -> str:
    qid = (question_id or "").strip()
    if not _UUID.match(qid):
        raise ValueError("无效的题目 id")
    return qid


def validate_scene(scene: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(scene, dict):
        raise ValueError("动画场景必须是对象")
    steps = scene.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("至少需要一步")
    if len(steps) > 20:
        raise ValueError("步骤不能超过 20 步")
    curves = scene.get("curves") or []
    if not isinstance(curves, list):
        raise ValueError("曲线格式不正确")
    for curve in curves:
        preset = str((curve or {}).get("preset") or "")
        if preset not in _PRESETS:
            raise ValueError(f"不支持的曲线类型：{preset}")
    cleaned_steps: list[dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ValueError("步骤格式不正确")
        title = str(step.get("title") or "").strip()
        caption = str(step.get("caption") or "").strip()
        if not title or not caption:
            raise ValueError(f"第 {index} 步需要标题和说明")
        formulas = step.get("formula") or []
        if not isinstance(formulas, list):
            raise ValueError(f"第 {index} 步的公式格式不正确")
        cleaned_steps.append(step)
    scene = dict(scene)
    scene["version"] = 1
    scene["engine"] = "plane"
    scene["steps"] = cleaned_steps
    if not scene.get("view"):
        scene["view"] = {"xMin": -4, "xMax": 4, "yMin": -4, "yMax": 4}
    if not curves:
        scene["curves"] = [_default_curve()]
    return scene


def _default_curve() -> dict[str, Any]:
    return {
        "id": "f",
        "preset": "quadratic",
        "quadratic": {"a": 1, "b": 0, "c": 0},
        "color": "#2457d6",
        "label": "y = x²",
        "labelCorner": "left",
    }


def plain_solution(text: str) -> str:
    raw = _TAG.sub("", text or "")
    raw = (
        raw.replace("&nbsp;", " ")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
    )
    return raw.replace("\r\n", "\n").replace("\r", "\n").strip()


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _normalize(text: str) -> str:
    """Collapse exam LaTeX so function, point, and interval patterns can match."""
    raw = plain_solution(text or "")
    for token in (r"\,", r"\;", r"\!", r"\:", r"\quad", r"\qquad"):
        raw = raw.replace(token, "")
    raw = _compact(raw)
    for name in ("dfrac", "tfrac", "cfrac"):
        raw = raw.replace("\\" + name, r"\frac")
    raw = raw.replace(r"\leqslant", r"\le").replace(r"\leq", r"\le")
    raw = raw.replace(r"\geqslant", r"\ge").replace(r"\geq", r"\ge")
    return raw


def _braced(text: str, index: int) -> tuple[str | None, int]:
    if index >= len(text) or text[index] != "{":
        return None, index
    depth = 0
    for cursor in range(index, len(text)):
        if text[cursor] == "{":
            depth += 1
        elif text[cursor] == "}":
            depth -= 1
            if depth == 0:
                return text[index + 1 : cursor], cursor + 1
    return None, index


def _unwrap_ends(token: str) -> str:
    token = _compact(token)
    while len(token) >= 2 and token[0] == "{" and token[-1] == "}":
        inner, end = _braced(token, 0)
        if inner is None or end != len(token):
            break
        token = inner
    return token


def _clean(value: float) -> float:
    if abs(value - round(value)) < 1e-8:
        return float(round(value))
    return round(value, 6)


def _num(token: str) -> float | None:
    token = _unwrap_ends(token)
    if not token:
        return None
    if token in {r"\pi", "π"}:
        return math.pi
    if token[0] in "+-" and token[1:] in {r"\pi", "π"}:
        return math.pi if token[0] == "+" else -math.pi
    if token.startswith(r"\sqrt"):
        inner, end = _braced(token, len(r"\sqrt")) if token[len(r"\sqrt") :].startswith("{") else (None, 0)
        if inner is not None and end == len(token):
            value = _num(inner)
            if value is None or value < 0:
                return None
            return math.sqrt(value)
    if token.startswith(r"\frac"):
        rest = token[len(r"\frac") :]
        numerator, cursor = _braced(rest, 0) if rest.startswith("{") else (None, 0)
        if numerator is not None and cursor < len(rest) and rest[cursor] == "{":
            denominator, end = _braced(rest, cursor)
            if denominator is not None and end == len(rest):
                top = _num(numerator)
                bottom = _num(denominator)
                if top is None or bottom in (None, 0):
                    return None
                return top / bottom
    if token.startswith("+"):
        token = token[1:]
    try:
        return float(token)
    except ValueError:
        return None

def _split_top_commas(body: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(body):
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            parts.append(body[start:index])
            start = index + 1
    parts.append(body[start:])
    return [part for part in parts if part != ""]


def _endpoint(token: str) -> tuple[float | None, int]:
    token = _unwrap_ends(token)
    if re.fullmatch(r"[+-]?\\infty", token):
        return None, -1 if token.startswith("-") else 1
    value = _num(token)
    if value is None:
        return None, 0
    return value, 0


def _scan_delimiters(compact: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    cursor = 0
    while True:
        start = compact.find(r"\left", cursor)
        if start < 0:
            break
        open_at = start + len(r"\left")
        if open_at >= len(compact) or compact[open_at] not in "(,[":
            cursor = open_at + 1
            continue
        open_ch = compact[open_at]
        if open_ch == ",":
            cursor = open_at + 1
            continue
        close_ch = ")" if open_ch == "(" else "]"
        depth = 0
        scan = open_at + 1
        close_at = -1
        while scan < len(compact):
            if compact.startswith(r"\right", scan) and depth == 0:
                mark = scan + len(r"\right")
                if mark < len(compact) and compact[mark] == close_ch:
                    close_at = scan
                    break
            if compact[scan] == "{":
                depth += 1
            elif compact[scan] == "}":
                depth = max(0, depth - 1)
            scan += 1
        if close_at < 0:
            cursor = open_at + 1
            continue
        end = close_at + len(r"\right") + 1
        body = _unwrap_ends(compact[open_at + 1 : close_at])
        found.append({"start": start, "end": end, "open": open_ch, "body": body})
        cursor = end
    return found


def _role(compact: str, start: int, end: int, body: str, infinite: bool) -> str:
    if infinite:
        return "interval"
    before = compact[max(0, start - 16) : start]
    after = compact[end : end + 8]
    if any(word in before for word in ("点", "经过", "坐标")):
        return "point"
    if any(word in before for word in ("区间", "解集", r"\in")) or "上" in after:
        return "interval"
    if any(token in body for token in (r"\sqrt", r"\frac", r"\pi")):
        return "point"
    return "interval"


def _geometry(compact: str) -> tuple[list[tuple[float, float]], list[dict[str, Any]]]:
    points: list[tuple[float, float]] = []
    intervals: list[dict[str, Any]] = []
    spans = _scan_delimiters(compact)

    def add_pair(start: int, end: int, open_ch: str, left: str, right: str) -> None:
        x_value, x_inf = _endpoint(left)
        y_value, y_inf = _endpoint(right)
        infinite = x_inf != 0 or y_inf != 0
        if not infinite and (x_value is None or y_value is None):
            return
        if infinite and x_inf == 0 and x_value is None:
            return
        if infinite and y_inf == 0 and y_value is None:
            return
        role = _role(compact, start, end, left + right, infinite)
        if role == "point" and x_value is not None and y_value is not None:
            if abs(x_value) <= 30 and abs(y_value) <= 30:
                points.append((x_value, y_value))
            return
        if role != "interval":
            return
        if x_inf == 0 and y_inf == 0 and y_value is not None and x_value is not None and y_value <= x_value:
            return
        intervals.append(
            {
                "start": x_value,
                "end": y_value,
                "start_inf": x_inf,
                "end_inf": y_inf,
                "closed": open_ch == "[",
            }
        )

    for item in spans:
        parts = _split_top_commas(item["body"])
        if len(parts) != 2:
            continue
        add_pair(item["start"], item["end"], item["open"], parts[0], parts[1])
    covered = [(item["start"], item["end"]) for item in spans]
    for match in re.finditer(r"(?<![\\0-9.])[\(\[]([0-9.]+),([0-9.]+)[\)\]]", compact):
        if any(start <= match.start() < end for start, end in covered):
            continue
        add_pair(match.start(), match.end(), match.group(0)[0], match.group(1), match.group(2))
    return points, intervals


def _is_domain_hole(intervals: list[dict[str, Any]]) -> bool:
    if len(intervals) < 2:
        return False
    finite: list[float] = []
    for item in intervals:
        if item["start_inf"] and item["end_inf"]:
            return False
        if item["start_inf"] and item["end"] is not None:
            finite.append(float(item["end"]))
        elif item["end_inf"] and item["start"] is not None:
            finite.append(float(item["start"]))
        else:
            return False
    return len(finite) >= 2 and max(finite) - min(finite) < 1e-6


def _boundary_roots(intervals: list[dict[str, Any]]) -> list[float]:
    ends: list[float] = []
    for item in intervals:
        if item["start_inf"] and not item["end_inf"] and item["end"] is not None:
            ends.append(float(item["end"]))
        elif item["end_inf"] and not item["start_inf"] and item["start"] is not None:
            ends.append(float(item["start"]))
    unique: list[float] = []
    for value in ends:
        if not any(abs(value - kept) < 1e-6 for kept in unique):
            unique.append(value)
    return unique if len(unique) >= 2 else []


def _explicit_roots(compact: str) -> list[float]:
    found: list[float] = []
    for match in re.finditer(r"根(?!据)", compact):
        window = compact[max(0, match.start() - 80) : match.end() + 40]
        for raw in re.findall(r"(?<![A-Za-z])x=([+-]?\d+(?:\.\d+)?)", window):
            value = float(raw)
            if not any(abs(value - kept) < 1e-6 for kept in found):
                found.append(value)
    return found


def _assignments(compact: str) -> dict[str, float]:
    found: dict[str, float] = {}
    for match in re.finditer(r"(?:^|[^A-Za-z0-9\\-])([A-Za-z])=(-?\d+(?:\.\d+)?)", compact):
        found[match.group(1)] = float(match.group(2))
    return found


def _coeff_before(prefix: str) -> tuple[Any, int]:
    if not prefix:
        return ("num", 1.0), 0
    if prefix[-1].isalpha():
        return ("var", prefix[-1], 1.0), 1
    number = re.search(r"([+-]?\d+(?:\.\d+)?)$", prefix)
    if number and number.group(1) not in {"", "+", "-"}:
        return ("num", float(number.group(1))), len(number.group(1))
    if prefix[-1] == "-":
        return ("num", -1.0), 1
    if prefix[-1] == "+":
        return ("num", 1.0), 1
    return ("num", 1.0), 0


def _terms_after(rest: str) -> tuple[Any, Any, int]:
    linear = ("num", 0.0)
    constant = ("num", 0.0)
    consumed = 0
    match = re.match(r"([+-])(\d+(?:\.\d+)?)?([A-Za-z])?x(?![A-Za-z])", rest)
    if match and (match.group(2) or match.group(3) or rest[match.end() - 1 : match.end()] == "x"):
        sign = -1.0 if match.group(1) == "-" else 1.0
        if match.group(3):
            linear = ("var", match.group(3), sign)
        else:
            magnitude = float(match.group(2)) if match.group(2) else 1.0
            linear = ("num", sign * magnitude)
        consumed = match.end()
    variable = re.match(r"([+-])([A-Za-z])(?![A-Za-z\(])", rest[consumed:])
    number = re.match(r"([+-])(\d+(?:\.\d+)?)", rest[consumed:])
    if number and not (variable and variable.start() == 0 and (not number.group(2))):
        sign = -1.0 if number.group(1) == "-" else 1.0
        magnitude = float(number.group(2)) if number.group(2) else 1.0
        constant = ("num", sign * magnitude)
        consumed += number.end()
    elif variable:
        sign = -1.0 if variable.group(1) == "-" else 1.0
        constant = ("var", variable.group(2), sign)
        consumed += variable.end()
    return linear, constant, consumed


def _resolve(coeff: Any, assignments: dict[str, float]) -> float | None:
    if coeff[0] == "num":
        return float(coeff[1])
    if coeff[1] not in assignments:
        return None
    return float(assignments[coeff[1]]) * float(coeff[2])


def _side_domain(compact: str, end: int) -> dict[str, float] | None:
    window = compact[end : end + 28]
    match = re.match(r",x(\\le|\\ge|\\lt|\\gt|<|>)([0-9.]+)", window)
    if not match:
        return None
    value = float(match.group(2))
    if match.group(1) in {r"\le", r"\lt", "<"}:
        return {"to": value}
    return {"from": value}


def _poly_label(a_value: float, b_value: float, c_value: float) -> str:
    parts: list[tuple[str, str]] = []

    def piece(coef: float, body: str) -> None:
        if abs(coef) < 1e-9:
            return
        magnitude = abs(coef)
        number = "" if body and abs(magnitude - 1) < 1e-9 else f"{magnitude:g}"
        parts.append(("−" if coef < 0 else "+", number + body))

    piece(a_value, "x²")
    piece(b_value, "x")
    piece(c_value, "")
    if not parts:
        return "y = 0"
    text = ""
    for index, (sign, body) in enumerate(parts):
        if index == 0:
            text += ("" if sign == "+" else "−") + body
        else:
            text += f" {sign} {body}"
    return "y = " + text


def _curve_fn(spec: dict[str, Any]):
    preset = spec["preset"]
    if preset == "quadratic":
        quad = spec["quadratic"]
        return lambda x, a=float(quad["a"]), b=float(quad["b"]), c=float(quad["c"]): a * x * x + b * x + c
    if preset == "square":
        return lambda x: x * x
    if preset == "exponential":
        base = float(spec["base"])
        add = float(spec.get("add") or 0)
        return lambda x, base=base, add=add: base**x + add
    if preset == "reciprocal":
        rec = spec["reciprocal"]
        return lambda x, h=float(rec["h"]), k=float(rec["k"]): k / (x - h)
    if preset == "fraction-exp":
        base = float(spec["base"])
        return lambda x, base=base: (base**x - 1) / (base**x + 1)
    if preset == "linear-reciprocal":
        rec = spec["linearReciprocal"]
        return lambda x, a=float(rec["a"]), k=float(rec["k"]): a * x + k / x
    return lambda x: x * x


def _vertical_holes(spec: dict[str, Any]) -> list[float]:
    preset = spec.get("preset")
    if preset == "reciprocal":
        return [float(spec["reciprocal"]["h"])]
    if preset == "linear-reciprocal":
        return [0.0]
    return []


def _sample_ys(spec: dict[str, Any], x_min: float, x_max: float) -> list[float]:
    """Sample a curve inside its domain, staying off vertical asymptotes."""
    function = _curve_fn(spec)
    domain = spec.get("domain") or {}
    holes = _vertical_holes(spec)
    found: list[float] = []
    steps = 72
    for index in range(1, steps):
        x_value = x_min + (x_max - x_min) * index / steps
        if "from" in domain and x_value < float(domain["from"]):
            continue
        if "to" in domain and x_value > float(domain["to"]):
            continue
        if any(abs(x_value - hole) < 0.42 for hole in holes):
            continue
        try:
            y_value = float(function(x_value))
        except (OverflowError, ZeroDivisionError, ValueError):
            continue
        if math.isfinite(y_value) and abs(y_value) <= 20:
            found.append(y_value)
    return found


def _frame_view(curves: list[dict[str, Any]], x_min: float, x_max: float) -> dict[str, float]:
    sample_ys: list[float] = []
    for spec in curves:
        sample_ys.extend(_sample_ys(spec, x_min, x_max))
    if not sample_ys:
        return {"xMin": round(x_min, 2), "xMax": round(x_max, 2), "yMin": -4, "yMax": 4}
    low = min(sample_ys)
    high = max(sample_ys)
    if high - low < 1.2:
        mid = (low + high) / 2
        low, high = mid - 0.8, mid + 0.8
    pad = max(0.7, (high - low) * 0.22)
    y_min = low - pad
    y_max = high + pad
    if y_min > 0:
        y_min = -0.6
    if y_max < 0:
        y_max = 0.6
    return {
        "xMin": round(x_min, 2),
        "xMax": round(x_max, 2),
        "yMin": round(y_min, 2),
        "yMax": round(y_max, 2),
    }


def _view_for(spec: dict[str, Any], x_min: float, x_max: float) -> dict[str, float]:
    return _frame_view([spec], x_min, x_max)


def _piecewise_break(curves: list[dict[str, Any]]) -> float | None:
    """Return the shared boundary when one piece ends where the next begins."""
    left = [
        float(item["domain"]["to"])
        for item in curves
        if isinstance(item.get("domain"), dict) and "to" in item["domain"] and "from" not in item["domain"]
    ]
    right = [
        float(item["domain"]["from"])
        for item in curves
        if isinstance(item.get("domain"), dict) and "from" in item["domain"] and "to" not in item["domain"]
    ]
    best: tuple[float, float] | None = None
    for end in left:
        for start in right:
            gap = start - end
            if -0.05 <= gap <= 0.45 and (best is None or gap < best[1] - best[0]):
                best = (end, start)
    return best[0] if best else None


def _with_gap(spec: dict[str, Any], hole: float, gap: float) -> list[dict[str, Any]]:
    left = dict(spec)
    right = dict(spec)
    left["id"] = f"{spec['id']}-left"
    right["id"] = f"{spec['id']}-right"
    left["domain"] = {"to": round(hole - gap, 2)}
    right["domain"] = {"from": round(hole + gap, 2)}
    left["labelCorner"] = "left"
    right["labelCorner"] = "right"
    return [left, right]


def _remember(curves: list[dict[str, Any]], spec: dict[str, Any]) -> None:
    signature = spec.pop("_sig")
    primary = spec.pop("_primary", False)
    hole = spec.pop("_hole", None)
    gap = float(spec.pop("_gap", 0.18) or 0.18)
    domain = spec.pop("_domain", None)
    pieces = _with_gap(spec, float(hole), gap) if hole is not None and domain is None else [spec]
    if domain and hole is None:
        pieces[0]["domain"] = domain
    for piece in pieces:
        piece["_sig"] = signature
        piece["_primary"] = primary
    curves.extend(pieces)


def _discover_curves(compact: str) -> list[dict[str, Any]]:
    curves: list[dict[str, Any]] = []
    seen: set[str] = set()
    colors = ["#2457d6", "#0f7a4a", "#c2413a", "#7a4e0f"]
    counter = 0

    def fresh_id(preferred: str) -> str:
        nonlocal counter
        used = {item["id"].split("-")[0] for item in curves}
        if preferred not in used:
            return preferred
        counter += 1
        return "fghpqr"[counter] if counter < len("fghpqr") else f"c{counter}"

    def add(key: str, spec: dict[str, Any]) -> None:
        if key in seen:
            return
        seen.add(key)
        spec.setdefault("color", colors[len(curves) % len(colors)])
        spec.setdefault("labelCorner", "right")
        _remember(curves, spec)

    for match in re.finditer(r"\\frac\{(.+?)\^\{x\}-1\}\{\1\^\{x\}\+1\}", compact):
        base = _num(match.group(1))
        if base is None or base <= 0 or base == 1:
            continue
        add(
            f"fraction:{_clean(base)}",
            {
                "id": fresh_id("f"),
                "preset": "fraction-exp",
                "base": _clean(base),
                "label": "y = (aˣ − 1)/(aˣ + 1)",
                "_sig": [match.group(0)],
                "_primary": True,
            },
        )
    linear_pattern = re.compile(
        r"\\frac\{([^{}]+)\}\{x\}\+([0-9.]*)x|([0-9.]*)x\+\\frac\{([^{}]+)\}\{x\}"
    )
    for match in linear_pattern.finditer(compact):
        k_value = _num(match.group(1) or match.group(4) or "")
        a_raw = match.group(2) if match.group(1) else match.group(3)
        a_value = 1.0 if not a_raw else _num(a_raw)
        if k_value in (None, 0) or a_value is None:
            continue
        k_value = _clean(float(k_value))
        a_value = _clean(float(a_value))
        a_text = "" if abs(a_value - 1) < 1e-9 else f"{a_value:g}"
        add(
            f"linear:{a_value:g}:{k_value:g}",
            {
                "id": fresh_id("g"),
                "preset": "linear-reciprocal",
                "linearReciprocal": {"a": a_value, "k": k_value},
                "label": f"y = {a_text}x + {k_value:g}/x",
                "_sig": [rf"\frac{{{k_value:g}}}{{x}}+{a_text}x", rf"{a_text}x+\frac{{{k_value:g}}}{{x}}"],
                "_hole": 0,
                "_gap": max(0.18, min(1.2, abs(k_value) * 0.06)),
                "_primary": True,
            },
        )
    for match in re.finditer(r"\\frac\{([^{}]+)\}\{x(?:-([^{}]+))?\}", compact):
        k_value = _num(match.group(1))
        h_value = _num(match.group(2) or "0")
        if k_value in (None, 0) or h_value is None:
            continue
        k_value = _clean(float(k_value))
        h_value = _clean(float(h_value))
        if h_value == 0 and abs(k_value - 1) > 1e-9 and any(
            item.startswith("linear:") and item.endswith(f":{k_value:g}") for item in seen
        ):
            continue
        domain = _side_domain(compact, match.end())
        if domain and "from" in domain and abs(domain["from"] - h_value) < 1e-6:
            domain = {"from": round(h_value + 0.12, 2)}
        if domain and "to" in domain and abs(domain["to"] - h_value) < 1e-6:
            domain = {"to": round(h_value - 0.12, 2)}
        label = f"y = {k_value:g}/x" if h_value == 0 else f"y = {k_value:g}/(x - {h_value:g})"
        signatures = [rf"\frac{{{k_value:g}}}{{x}}" if h_value == 0 else rf"\frac{{{k_value:g}}}{{x-{h_value:g}}}"]
        if h_value == 0 and k_value == 1:
            signatures.append(r"x^{-1}")
        add(
            f"reciprocal:{k_value:g}:{h_value:g}",
            {
                "id": fresh_id("f"),
                "preset": "reciprocal",
                "reciprocal": {"h": h_value, "k": k_value},
                "label": label,
                "_sig": signatures,
                "_hole": None if domain else h_value,
                "_domain": domain,
                "_primary": True,
            },
        )
    if r"x^{-1}" in compact and "reciprocal:1:0" not in seen:
        add(
            "reciprocal:1:0",
            {
                "id": fresh_id("f"),
                "preset": "reciprocal",
                "reciprocal": {"h": 0, "k": 1},
                "label": "y = 1/x",
                "_sig": [r"x^{-1}", r"\frac{1}{x}"],
                "_hole": 0,
                "_primary": True,
            },
        )
    fraction_spans = [match.span() for match in re.finditer(r"\\frac\{(.+?)\^\{x\}-1\}\{\1\^\{x\}\+1\}", compact)]
    for match in re.finditer(r"(\\pi|[0-9.]+)\^\{x\}(?:\+([0-9.]+))?", compact):
        if any(start <= match.start() < end for start, end in fraction_spans):
            continue
        base = _num(match.group(1))
        add_value = _num(match.group(2) or "0")
        if base is None or base <= 0 or base == 1 or add_value is None:
            continue
        base = _clean(base)
        add_value = _clean(add_value)
        add(
            f"exp:{base:g}:{add_value:g}",
            {
                "id": fresh_id("e"),
                "preset": "exponential",
                "base": base,
                "add": add_value,
                "label": "y = aˣ" if add_value == 0 else f"y = aˣ + {add_value:g}",
                "labelCorner": "left",
                "_sig": [match.group(0)],
                "_primary": False,
            },
        )
    assignments = _assignments(compact)
    _, intervals = _geometry(compact)
    roots = _explicit_roots(compact) or _boundary_roots(intervals)
    token = r"x^{2}"
    cursor = 0
    while True:
        at = compact.find(token, cursor)
        if at < 0:
            break
        linear, constant, consumed = _terms_after(compact[at + len(token) :])
        coeff, coeff_len = _coeff_before(compact[max(0, at - 12) : at])
        end = at + len(token) + consumed
        a_value = _resolve(coeff, assignments)
        b_value = _resolve(linear, assignments)
        c_value = _resolve(constant, assignments)
        if (a_value is None or b_value is None or c_value is None) and len(roots) >= 2 and c_value is not None:
            r1, r2 = roots[0], roots[1]
            if a_value is None and b_value is None and r1 * r2 != 0:
                a_value = c_value / (r1 * r2)
                b_value = -a_value * (r1 + r2)
            elif a_value is None and b_value is not None and r1 + r2 != 0:
                a_value = -b_value / (r1 + r2)
            elif b_value is None and a_value is not None:
                b_value = -a_value * (r1 + r2)
        cursor = max(end, at + len(token))
        if None in (a_value, b_value, c_value) or a_value == 0:
            continue
        a_value, b_value, c_value = _clean(a_value), _clean(b_value), _clean(c_value)
        domain = _side_domain(compact, end)
        signature = compact[at - coeff_len : end]
        add(
            f"quad:{a_value:g}:{b_value:g}:{c_value:g}:{domain}",
            {
                "id": fresh_id("f" if domain is None else "q"),
                "preset": "quadratic",
                "quadratic": {"a": a_value, "b": b_value, "c": c_value},
                "label": _poly_label(a_value, b_value, c_value),
                "labelCorner": "left",
                "_sig": [signature],
                "_domain": domain,
                "_primary": True,
            },
        )
    if not curves:
        fallback = _default_curve()
        fallback["_sig"] = []
        fallback["_primary"] = True
        curves.append(fallback)
    if not any(item.get("_primary") for item in curves):
        curves[-1]["_primary"] = True
    return curves


def _passes(spec: dict[str, Any], x_value: float, y_value: float) -> bool:
    try:
        got = float(_curve_fn(spec)(x_value))
    except (OverflowError, ZeroDivisionError, ValueError):
        return False
    if not math.isfinite(got):
        return False
    return abs(got - y_value) <= 0.08 + 0.02 * abs(y_value)


def _curve_ids(piece: str, curves: list[dict[str, Any]], points: list[tuple[float, float]]) -> list[str]:
    compact = _normalize(piece)
    hits = [item for item in curves if any(sig and sig in compact for sig in item.get("_sig") or [])]

    def dominated(curve: dict[str, Any]) -> bool:
        own = [sig for sig in curve.get("_sig") or [] if sig and sig in compact]
        if not own:
            return False
        longest = max(len(sig) for sig in own)
        for other in hits:
            if other is curve:
                continue
            larger = [sig for sig in other.get("_sig") or [] if sig and sig in compact and len(sig) > longest]
            if any(sig in big for sig in own for big in larger):
                return True
        return False

    hits = [item for item in hits if not dominated(item)] or hits
    if hits:
        return [item["id"] for item in hits]
    if points:
        passed = [item for item in curves if any(_passes(item, x_value, y_value) for x_value, y_value in points)]
        if passed:
            return [item["id"] for item in passed]
    primary = [item["id"] for item in curves if item.get("_primary")]
    return primary or [curves[0]["id"]]


def _strip_curve(spec: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in spec.items() if not key.startswith("_")}


def _plain_formula(latex: str) -> str:
    """Turn one formula into a short readable fragment so the sentence stays intact."""
    text = _compact(latex)
    text = text.replace(r"\left.", "").replace(r"\right.", "")
    text = text.replace(r"\left", "").replace(r"\right", "")
    text = text.replace(r"\dfrac", r"\frac").replace(r"\tfrac", r"\frac").replace(r"\cfrac", r"\frac")
    for src, dst in (
        (r"\leqslant", "≤"),
        (r"\leq", "≤"),
        (r"\geqslant", "≥"),
        (r"\geq", "≥"),
        (r"\infty", "∞"),
        (r"\times", "×"),
        (r"\cdot", "·"),
        (r"\le", "≤"),
        (r"\ge", "≥"),
        (r"\ne", "≠"),
        (r"\pi", "π"),
        (r"\lt", "<"),
        (r"\gt", ">"),
    ):
        text = text.replace(src, dst)
    while True:
        match = re.search(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", text)
        if not match:
            break
        def piece(body: str) -> str:
            return f"({body})" if re.search(r"[+\-；]", body) else body

        text = text[: match.start()] + f"{piece(match.group(1))}/{piece(match.group(2))}" + text[match.end() :]
    for src, dst in (
        (r"\varphi", "φ"),
        (r"\alpha", "α"),
        (r"\beta", "β"),
        (r"\gamma", "γ"),
        (r"\delta", "δ"),
        (r"\theta", "θ"),
        (r"\lambda", "λ"),
        (r"\omega", "ω"),
        (r"\Delta", "Δ"),
        (r"\sin", "sin"),
        (r"\cos", "cos"),
        (r"\tan", "tan"),
        (r"\cot", "cot"),
        (r"\log", "log"),
        (r"\ln", "ln"),
        (r"\lg", "lg"),
    ):
        text = text.replace(src, dst)
    text = text.replace(r"^{2}", "²").replace(r"^{3}", "³")
    text = re.sub(r"\^\{([^{}]+)\}", r"^\1", text)
    text = text.replace(r"\sqrt", "√")
    text = text.replace("\\\\", "；")
    text = re.sub(r"\\begin\{[a-zA-Z*]+\}(?:\{[^{}]*\})?", "", text)
    text = re.sub(r"\\end\{[a-zA-Z*]+\}", "", text)
    text = re.sub(r"\\[a-zA-Z]+", "", text)
    text = text.replace("{", "").replace("}", "").replace("\\", "")
    text = re.sub(r",*；", "；", text)
    text = re.sub(r"；+", "；", text)
    return text.strip("； ")


def _quad_y(spec: dict[str, Any], x_value: float) -> float:
    quad = spec["quadratic"]
    return float(quad["a"]) * x_value * x_value + float(quad["b"]) * x_value + float(quad["c"])


def _const_over_a(constant: float) -> str:
    if constant < 0:
        return f"-\\dfrac{{{abs(constant):g}}}{{a}}"
    if constant > 0:
        return f"\\dfrac{{{constant:g}}}{{a}}"
    return "0"


def _num_prose(value: float) -> str:
    text = f"{abs(value):g}"
    return f"−{text}" if value < 0 else text


def _const_prose(constant: float) -> str:
    if constant < 0:
        return f"−{abs(constant):g}/a"
    if constant > 0:
        return f"{constant:g}/a"
    return "0"


def _axis_markers(roots: list[float], name: str | None = None) -> list[dict[str, Any]]:
    return [
        {"x": value, "name": name or f"{value:g}", "tone": "neutral"}
        for value in roots
    ]


def _root_guides(roots: list[float]) -> list[dict[str, Any]]:
    return [{"x": value, "label": f"x = {value:g}"} for value in roots]


def _choice_letter(text: str) -> str:
    found = re.search(r"故选\s*[:：]?\s*([A-Da-d])", text)
    return found.group(1).upper() if found else ""


_QUAD_EXPR = re.compile(
    r"(?<![A-Za-z0-9])([+-]?(?:\d+(?:\.\d+)?|[A-Za-z])?)x\^\{2\}"
    r"([+-](?:\d+(?:\.\d+)?|[A-Za-z])?x)?"
    r"([+-]\d+(?:\.\d+)?)?"
)


def _source_quadratic(compact: str) -> str | None:
    found = _QUAD_EXPR.search(compact)
    if not found:
        return None
    return found.group(0)


def _quadratic_prose(expr: str) -> str:
    body = expr.replace("^{2}", "²")
    if body.startswith("-"):
        body = "−" + body[1:]
    body = body.replace("+", " + ").replace("-", " − ")
    return re.sub(r"\s+", " ", body).strip()


def _relation_after(compact: str, expr: str) -> str:
    at = compact.find(expr)
    tail = compact[at + len(expr) : at + len(expr) + 8] if at >= 0 else ""
    if tail.startswith(r"\le") or tail.startswith("≤"):
        return r"\le"
    if tail.startswith(r"\ge") or tail.startswith("≥"):
        return r"\ge"
    if tail.startswith(">"):
        return ">"
    return "<"


def _relation_prose(relation: str) -> str:
    return {"\\le": "≤", "\\ge": "≥"}.get(relation, relation)


def _relation_word(relation: str) -> str:
    return {">": "大于", r"\ge": "大于等于", r"\le": "小于等于"}.get(relation, "小于")


def _factor_piece(root: float, *, latex: bool) -> str:
    if abs(root) < 1e-9:
        return "x"
    if latex:
        return f"(x-{root:g})" if root > 0 else f"(x+{abs(root):g})"
    if root > 0:
        return f"(x − {root:g})"
    return f"(x + {abs(root):g})"


def _poly_latex(a_value: float, b_value: float, c_value: float) -> str:
    parts: list[str] = []

    def piece(coef: float, body: str) -> None:
        if abs(coef) < 1e-9:
            return
        magnitude = abs(coef)
        number = "" if body and abs(magnitude - 1) < 1e-9 else f"{magnitude:g}"
        sign = "-" if coef < 0 else "+"
        parts.append(sign + number + body)

    piece(a_value, "x^{2}")
    piece(b_value, "x")
    piece(c_value, "")
    if not parts:
        return "y=0"
    text = "".join(parts)
    if text.startswith("+"):
        text = text[1:]
    return "y=" + text


def _quadratic_inequality_steps(raw: str, curves: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Stage a quadratic-inequality solution in the same order as a written 详解."""
    quads = [item for item in curves if item.get("preset") == "quadratic" and not item.get("domain")]
    if len(quads) != 1:
        return None
    spec = quads[0]
    a_value = float(spec["quadratic"]["a"])
    b_value = float(spec["quadratic"]["b"])
    c_value = float(spec["quadratic"]["c"])
    compact = _normalize(raw)
    if "解集" not in compact and "不等式" not in compact:
        return None
    _, intervals = _geometry(compact)
    roots = _boundary_roots(intervals) or _explicit_roots(compact)
    if len(roots) < 2:
        return None
    r1, r2 = sorted(roots[:2])
    if abs(_quad_y(spec, r1)) > 1e-4 or abs(_quad_y(spec, r2)) > 1e-4:
        return None
    curve_id = spec["id"]
    outside = a_value < 0
    vertex_x = -b_value / (2 * a_value)
    vertex_y = _quad_y(spec, vertex_x)
    x_min = round(r1 - 1.8, 2)
    x_max = round(r2 + 1.8, 2)
    edge = min(_quad_y(spec, x_min), _quad_y(spec, x_max), 0.0)
    wide = {
        "xMin": x_min,
        "xMax": x_max,
        "yMin": round(min(-1.6, max(edge + 2.6, -4.2)), 2),
        "yMax": round(max(vertex_y, 0.8) + 1.4, 2),
    }
    between = {
        "xMin": round(r1 - 0.8, 2),
        "xMax": round(r2 + 0.8, 2),
        "yMin": round(min(-1.2, vertex_y - 1), 2),
        "yMax": round(max(vertex_y, 0.8) + 1.2, 2),
    }
    expr = _source_quadratic(compact) or "ax^{2}+bx+c"
    prose = _quadratic_prose(expr)
    relation = _relation_after(compact, expr)
    rel_prose = _relation_prose(relation)
    solution_prose = (
        f"(−∞, {r1:g}) ∪ ({r2:g}, +∞)" if outside else f"({r1:g}, {r2:g})"
    )
    solution_latex = (
        f"\\left(-\\infty,{r1:g}\\right)\\cup\\left({r2:g},+\\infty\\right)"
        if outside
        else f"\\left({r1:g},{r2:g}\\right)"
    )
    solution = (
        [
            {"from": wide["xMin"], "to": r1, "tone": "down", "label": f"(−∞, {r1:g})"},
            {"from": r2, "to": wide["xMax"], "tone": "down", "label": f"({r2:g}, +∞)"},
        ]
        if outside
        else [{"from": r1, "to": r2, "tone": "down", "label": f"({r1:g}, {r2:g})"}]
    )
    opening_label = "开口向下，a < 0" if outside else "开口向上，a > 0"
    opening_caption = (
        "详解的第一个结论：解集在两根外侧，而不是两根之间。二次函数开口向下时，函数值在两根外侧为负，所以 a < 0。"
        f"图中 ({r1:g}, {r2:g}) 在 x 轴上方，这一段不在解集里。"
        if outside
        else "详解的第一个结论：解集在两根之间。二次函数开口向上时，函数值在两根之间为负，所以 a > 0。"
        f"图中 ({r1:g}, {r2:g}) 在 x 轴下方，这一段就是解集。"
    )
    interior = {
        "from": r1,
        "to": r2,
        "tone": "up" if outside else "down",
        "label": f"({r1:g}, {r2:g}) 上 y {'>' if outside else '<'} 0",
    }
    product = r1 * r2
    total = r1 + r2
    label = _poly_label(a_value, b_value, c_value)
    spec["label"] = label
    choice = _choice_letter(raw)
    answer_tail = f"，故选 {choice}" if choice else ""
    lead = "−" if abs(a_value + 1) < 1e-9 else ("" if abs(a_value - 1) < 1e-9 else _num_prose(a_value))
    latex_lead = "-" if abs(a_value + 1) < 1e-9 else ("" if abs(a_value - 1) < 1e-9 else f"{a_value:g}")
    factor = lead + _factor_piece(r1, latex=False) + _factor_piece(r2, latex=False)
    product_piece = _factor_piece(r1, latex=False) + _factor_piece(r2, latex=False)
    latex_factor = latex_lead + _factor_piece(r1, latex=True) + _factor_piece(r2, latex=True)
    latex_product = _factor_piece(r1, latex=True) + _factor_piece(r2, latex=True)
    below = relation in {"<", r"\le"}
    product_rel = ">" if (a_value < 0) == below else "<"
    region = f"x < {r1:g} 或 x > {r2:g}" if outside else f"{r1:g} < x < {r2:g}"
    sign_note = ""
    if outside and a_value < 0:
        sign_note = "这和前面得到的 a < 0 一致。"
    elif not outside and a_value > 0:
        sign_note = "这和前面得到的 a > 0 一致。"
    if abs(a_value + 1) < 1e-9:
        substitute = f"把 a = −1 代入，{total:g} = −b/(−1) = b，所以 b = {_num_prose(b_value)}。"
    else:
        substitute = f"把 a = {_num_prose(a_value)} 代入，得到 b = {_num_prose(b_value)}。"
    shared = {"curve": curve_id, "curves": [curve_id]}
    shade = "两段" if outside else "一段"
    return [
        {
            "id": "given",
            "title": "看清解集",
            "caption": (
                f"题干：不等式 {prose} {rel_prose} 0 的解集是 {solution_prose}。"
                f"图中涂色的{shade}就是这个解集，分界点是 x = {r1:g} 和 x = {r2:g}。"
            ),
            "formula": [expr + relation + "0", solution_latex],
            "view": wide,
            "intervals": solution,
            "markers": _axis_markers([r1, r2]),
            "guides": _root_guides([r1, r2]),
            **shared,
        },
        {
            "id": "opening",
            "title": opening_label,
            "caption": opening_caption,
            "formula": ["a<0" if outside else "a>0", "\\text{解集在两根外侧}" if outside else "\\text{解集在两根之间}"],
            "view": between,
            "intervals": [interior],
            "markers": _axis_markers([r1, r2]),
            "guides": [],
            **shared,
        },
        {
            "id": "roots",
            "title": f"两根是 {r1:g} 和 {r2:g}",
            "caption": (
                f"详解接着写：x = {r1:g} 和 x = {r2:g} 是方程 {prose} = 0 的根。"
                "图像与 x 轴的交点就是这两个根，交点处函数值为 0。"
            ),
            "formula": [expr + "=0", f"x={r1:g}", f"x={r2:g}"],
            "view": wide,
            "intervals": [],
            "markers": _axis_markers([r1, r2], "根"),
            "guides": _root_guides([r1, r2]),
            **shared,
        },
        {
            "id": "vieta",
            "title": "根与系数",
            "caption": (
                "由根与系数的关系，两根之和等于 −b/a，两根之积等于常数项除以 a。"
                f"常数项是 {_num_prose(c_value)}，所以 {r1:g} + {r2:g} = −b/a，{r1:g} × {r2:g} = {_const_prose(c_value)}。"
            ),
            "formula": [f"{r1:g}+{r2:g}=-\\dfrac{{b}}{{a}}", f"{r1:g}\\times {r2:g}={_const_over_a(c_value)}"],
            "view": wide,
            "intervals": [],
            "markers": _axis_markers([r1, r2]),
            "guides": [],
            **shared,
        },
        {
            "id": "coefficient-a",
            "title": f"求出 a = {_num_prose(a_value)}",
            "caption": (
                f"先用积：{r1:g} × {r2:g} = {_const_prose(c_value)}，即 {product:g} = {_const_prose(c_value)}，"
                f"所以 a = {_num_prose(a_value)}。{sign_note}"
            ),
            "formula": [f"{product:g}={_const_over_a(c_value)}", f"a={a_value:g}"],
            "view": wide,
            "intervals": [],
            "markers": _axis_markers([r1, r2]),
            "guides": [],
            **shared,
        },
        {
            "id": "coefficient-b",
            "title": f"求出 b = {_num_prose(b_value)}",
            "caption": (
                f"再用和：{r1:g} + {r2:g} = −b/a。{substitute}"
                f"解析式是 {label}，顶点在 ({vertex_x:g}, {vertex_y:g})。"
            ),
            "formula": [f"{total:g}=-\\dfrac{{b}}{{a}}", f"b={b_value:g}", _poly_latex(a_value, b_value, c_value)],
            "view": wide,
            "intervals": [],
            "markers": [{"x": vertex_x, "name": "顶点", "tone": "up"}],
            "guides": [
                {"x": vertex_x, "label": f"x = {vertex_x:g}"},
                {"y": vertex_y, "label": f"y = {vertex_y:g}"},
            ],
            **shared,
        },
        {
            "id": "difference",
            "title": "计算 b − a",
            "caption": (
                f"系数都求出来了：a = {_num_prose(a_value)}，b = {_num_prose(b_value)}。"
                f"所以 b − a = {_num_prose(b_value)} − ({_num_prose(a_value)}) = {_num_prose(b_value - a_value)}。"
            ),
            "formula": [f"b-a={b_value:g}-({a_value:g})={b_value - a_value:g}"],
            "view": wide,
            "intervals": [],
            "markers": _axis_markers([r1, r2]),
            "guides": [],
            **shared,
        },
        {
            "id": "answer",
            "title": "核对并作答",
            "caption": (
                f"代回检验：{label.removeprefix('y = ')} = {factor}。"
                f"它{_relation_word(relation)} 0 时 {product_piece} {product_rel} 0，即 {region}，与题干的解集一致。"
                f"因此 b − a = {_num_prose(b_value - a_value)}{answer_tail}。"
            ),
            "formula": [
                latex_factor + relation + "0",
                latex_product + product_rel + "0",
                f"b-a={b_value - a_value:g}" + (f",\\ \\text{{故选 {choice}}}" if choice else ""),
            ],
            "view": wide,
            "intervals": solution,
            "markers": _axis_markers([r1, r2]),
            "guides": [],
            **shared,
        },
    ]


def _finite_intervals(intervals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in intervals
        if not item["start_inf"] and not item["end_inf"] and item["start"] is not None and item["end"] is not None
    ]


def _function_story_steps(raw: str, curves: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Stage a function solution: point, expression, then parity or monotonicity."""
    if any(item.get("preset") == "quadratic" and item.get("domain") for item in curves):
        return None
    interesting = [item for item in curves if item.get("preset") in {"reciprocal", "linear-reciprocal", "fraction-exp"}]
    if not interesting:
        return None
    compact = _normalize(raw)
    points, intervals = _geometry(compact)
    finite = _finite_intervals(intervals)
    decreasing = bool(re.search(r"递减|减函数", raw))
    increasing = bool(re.search(r"递增|增函数", raw))
    if not points and not (finite and (decreasing or increasing)):
        return None
    steps: list[dict[str, Any]] = []

    def ids_of(preset: str) -> list[str]:
        return [item["id"] for item in curves if item.get("preset") == preset]

    def add(step: dict[str, Any]) -> None:
        steps.append(step)

    if points:
        carriers = [item for item in interesting if any(_passes(item, x_value, y_value) for x_value, y_value in points)]
        focus = carriers[0] if carriers else interesting[0]
        shown = [item["id"] for item in curves if item.get("preset") == focus.get("preset")] or [focus["id"]]
        x_value, y_value = points[0]
        add(
            {
                "id": "point",
                "title": "标出已知点",
                "caption": f"题干给出函数图像经过点 ({x_value:.3g}, {y_value:.3g})。先把这个点标在对应的曲线上。",
                "formula": [f"\\left({x_value:.3g},{y_value:.3g}\\right)"],
                "curve": shown[0],
                "curves": shown,
                "view": _view_for(focus, x_value - 1.4, x_value + 1.4),
                "intervals": [],
                "markers": [{"x": x_value, "name": f"({x_value:.3g}, {y_value:.3g})", "tone": "neutral"}],
                "guides": [{"x": x_value, "label": f"x = {x_value:.3g}"}, {"y": y_value, "label": f"y = {y_value:.3g}"}],
            }
        )
    for preset, title in (("reciprocal", "写出解析式"), ("fraction-exp", "写出解析式"), ("linear-reciprocal", "得到新函数")):
        matched = [item for item in curves if item.get("preset") == preset]
        if not matched:
            continue
        focus = matched[0]
        shown = [item["id"] for item in matched]
        add(
            {
                "id": "expression-" + preset,
                "title": title,
                "caption": f"详解得到 {focus.get('label') or title}。这一步只看这条曲线。",
                "formula": [],
                "curve": shown[0],
                "curves": shown,
                "view": _view_for(focus, -3.2, 3.2),
                "intervals": [],
                "markers": [],
                "guides": [],
            }
        )
    if "奇函数" in compact:
        focus = interesting[0]
        shown = ids_of(str(focus.get("preset"))) or [focus["id"]]
        add(
            {
                "id": "odd",
                "title": "判断奇偶性",
                "caption": "详解说明函数是奇函数：图像关于原点对称。图上取一对相反的自变量，对应的函数值也相反。",
                "formula": ["f(-x)=-f(x)"],
                "curve": shown[0],
                "curves": shown,
                "view": _view_for(focus, -3.2, 3.2),
                "intervals": [],
                "markers": [
                    {"x": -2, "name": "−2", "tone": "neutral"},
                    {"x": 2, "name": "2", "tone": "neutral"},
                ],
                "guides": [],
            }
        )
    if finite and (decreasing or increasing):
        start = float(finite[0]["start"])
        end = float(finite[0]["end"])
        focus = next((item for item in interesting if item.get("preset") == "linear-reciprocal"), interesting[0])
        shown = ids_of(str(focus.get("preset"))) or [focus["id"]]
        tone = "down" if decreasing else "up"
        word = "递减" if decreasing else "递增"
        width = end - start
        gap = min(width * 0.28, 0.8)
        motion = {
            "type": "pair",
            "x1From": round(start + width * 0.2, 2),
            "x1To": round(end - gap - width * 0.12, 2),
            "gap": round(gap, 2),
            "tone": tone,
        }
        step = {
            "id": "mono",
            "title": f"在 ({start:g}, {end:g}) 上{word}",
            "caption": f"详解的结论：{focus.get('label') or '函数'} 在 ({start:g}, {end:g}) 上{word}。图中从左向右取 x₁、x₂，比较它们的函数值。",
            "formula": [f"x\\in\\left({start:g},{end:g}\\right)"],
            "curve": shown[0],
            "curves": shown,
            "view": _view_for(focus, start - 0.45, end + 0.45),
            "intervals": [{"from": start, "to": end, "tone": tone, "label": f"({start:g}, {end:g})"}],
            "markers": [],
            "guides": [],
        }
        if motion["x1To"] > motion["x1From"]:
            step["motion"] = motion
        add(step)
    return steps or None


def _fmt_end(value: float | None, infinite: int) -> str:
    if infinite < 0:
        return "-∞"
    if infinite > 0:
        return "+∞"
    return f"{float(value):g}"


def draft_scene(
    text: str,
    *,
    title: str = "解题过程",
    stem: str = "",
    analysis: str = "",
) -> dict[str, Any]:
    """Build plane steps from the functions, points, and intervals in the question text."""
    chunks = [plain_solution(part) for part in (stem, analysis, text) if plain_solution(part)]
    raw = "\n\n".join(chunks)
    curves = _discover_curves(_normalize(raw))
    lesson = _quadratic_inequality_steps(raw, curves) or _function_story_steps(raw, curves)
    global_down = bool(re.search(r"递减|减函数", raw))
    global_up = bool(re.search(r"递增|增函数", raw))
    pieces = [part.strip() for part in re.split(r"\n\s*\n+", raw) if part.strip()]
    if len(pieces) <= 1 and raw:
        pieces = [part.strip() for part in re.split(r"(?=【[^】]{1,24}】)", raw) if part.strip()]
    steps: list[dict[str, Any]] = list(lesson or [])
    for piece in pieces if not lesson else []:
        formulas: list[str] = []

        def _grab(match: re.Match[str]) -> str:
            latex = _compact(match.group(1) or match.group(2) or "")
            formulas.append(latex)
            return _plain_formula(latex)

        caption = _FORMULA.sub(_grab, piece)
        caption = re.sub(r"【[^】]{1,24}】", " ", caption)
        caption = re.sub(r"\s+", " ", caption).strip(" ：:，,。")
        heading = ""
        found = re.search(r"【([^】]{1,24})】", piece)
        if found:
            heading = found.group(1).strip()
        if len(caption) < 4 and not formulas:
            continue
        compact = _normalize(piece)
        points, intervals = _geometry(compact)
        ids = _curve_ids(piece, curves, points)
        chosen = [item for item in curves if item["id"] in ids]
        focus = chosen[0] if chosen else curves[0]
        decreasing = bool(re.search(r"递减|减函数", piece))
        increasing = bool(re.search(r"递增|增函数", piece))
        below = bool(re.search(r"<\s*0|＜\s*0", piece))
        above = bool(re.search(r">\s*0|＞\s*0", piece))
        domain_hole = _is_domain_hole(intervals)
        finite_intervals = [
            item
            for item in intervals
            if not item["start_inf"] and not item["end_inf"] and item["start"] is not None and item["end"] is not None
        ]
        if finite_intervals and "单调" in piece and not decreasing and not increasing:
            if global_down and not global_up:
                decreasing = True
            elif global_up and not global_down:
                increasing = True
        tone = "down" if decreasing or (below and not increasing) else "up"
        xs = [item[0] for item in points]
        xs.extend(float(item["start"]) for item in finite_intervals)
        xs.extend(float(item["end"]) for item in finite_intervals)
        for item in intervals:
            if item["start_inf"] and item["end"] is not None:
                xs.append(float(item["end"]))
            elif item["end_inf"] and item["start"] is not None:
                xs.append(float(item["start"]))
        if re.search(r"奇函数", piece) and not points:
            xs.extend([-2, 2])
        if not xs:
            x_min, x_max = -3.2, 3.2
        else:
            pad = 0.45 if finite_intervals and not points else 1.2
            x_min, x_max = min(xs) - pad, max(xs) + pad
        if (decreasing or increasing) and not finite_intervals and not domain_hole:
            x_min, x_max = min(x_min, -2.4), max(x_max, 2.4)
        shown = chosen or [focus]
        break_at = _piecewise_break(shown)
        if break_at is not None:
            x_min, x_max = break_at - 2.4, break_at + 2.6
            for value in xs:
                if abs(value - break_at) <= 5:
                    x_min = min(x_min, value - 0.6)
                    x_max = max(x_max, value + 0.6)
        view = _frame_view(shown, x_min, x_max)
        interval_specs: list[dict[str, Any]] = []
        if not domain_hole:
            source_intervals = finite_intervals or intervals
            if decreasing or increasing or below or above or finite_intervals:
                for item in source_intervals[:3]:
                    start = view["xMin"] if item["start_inf"] else item["start"]
                    end = view["xMax"] if item["end_inf"] else item["end"]
                    if start is None or end is None or end <= start:
                        continue
                    left = "[" if item["closed"] else "("
                    right = "]" if item["closed"] else ")"
                    interval_specs.append(
                        {
                            "from": start,
                            "to": end,
                            "tone": tone,
                            "label": f"{left}{_fmt_end(item['start'], item['start_inf'])}, {_fmt_end(item['end'], item['end_inf'])}{right}",
                        }
                    )
        markers: list[dict[str, Any]] = []
        guides: list[dict[str, Any]] = []
        for x_value, y_value in points[:3]:
            markers.append({"x": x_value, "name": f"({x_value:.3g}, {y_value:.3g})", "tone": "neutral"})
            guides.append({"x": x_value, "label": f"x = {x_value:.3g}"})
            guides.append({"y": y_value, "label": f"y = {y_value:.3g}"})
        if not markers:
            for value in _explicit_roots(compact) or (
                _boundary_roots(intervals) if (below or above or "解集" in compact) else []
            ):
                markers.append({"x": value, "name": f"x={value:g}", "tone": "neutral"})
                guides.append({"x": value, "label": f"x = {value:g}"})
        if re.search(r"奇函数", piece) and not markers:
            markers = [
                {"x": -2, "name": "−2", "tone": "neutral"},
                {"x": 2, "name": "2", "tone": "neutral"},
            ]
        if domain_hole and re.search(r"定义域", piece):
            guides.append({"x": 0, "label": "x ≠ 0"})
        motion = None
        if (decreasing or increasing) and finite_intervals:
            start = float(finite_intervals[0]["start"])
            end = float(finite_intervals[0]["end"])
            width = end - start
            if width >= 0.6:
                gap = min(width * 0.28, 0.8)
                motion = {
                    "type": "pair",
                    "x1From": round(start + width * 0.2, 2),
                    "x1To": round(end - gap - width * 0.12, 2),
                    "gap": round(gap, 2),
                    "tone": tone,
                }
        elif decreasing or increasing:
            motion = {"type": "pair", "x1From": -1.2, "x1To": 0.6, "gap": 0.8, "tone": tone}
        step: dict[str, Any] = {
            "id": f"step-{len(steps) + 1}",
            "title": (caption[:18] or heading or f"第 {len(steps) + 1} 步")[:24],
            "caption": (caption or "这一步见公式。")[:500],
            "formula": [item for item in formulas if item][:8],
            "curve": ids[0],
            "curves": ids,
            "view": view,
            "intervals": interval_specs,
            "markers": markers[:4],
            "guides": guides[:4],
        }
        if motion and motion["x1To"] > motion["x1From"]:
            step["motion"] = motion
        steps.append(step)
        if len(steps) >= 20:
            break
    if not steps:
        steps.append(
            {
                "id": "step-1",
                "title": "审题",
                "caption": "把题干、分析和详解放在左侧后生成草稿。图形会按其中的函数、点和区间来画。",
                "formula": [],
                "curves": [curves[0]["id"]],
                "intervals": [],
                "markers": [],
                "guides": [],
            }
        )
    return validate_scene(
        {
            "version": 1,
            "engine": "plane",
            "title": (title or "解题过程").strip()[:80] or "解题过程",
            "meta": "根据题干、分析、详解生成",
            "view": steps[0].get("view") or {"xMin": -4, "xMax": 4, "yMin": -4, "yMax": 4},
            "curves": [_strip_curve(item) for item in curves],
            "steps": steps,
        }
    )
