"""Ask DeepSeek for a plane-engine solution scene and make it playable."""

from __future__ import annotations

import re
from typing import Any

from word_math_md.plane_scenes import plain_solution, save_scene, validate_scene
from word_math_md.question_variant import _model_complete, _model_configured, _parse_json

_NEXT_SECTION = re.compile(r"(?m)^\s*[一二三四五六七八九十]+、")
_PRESETS = {"square", "quadratic", "exponential", "reciprocal", "fraction-exp", "linear-reciprocal"}
_TONES = {"up", "down", "neutral"}

SYSTEM = """你是高中数学解题动画的编剧，画面由 plane 引擎播放。
plane 引擎会：把曲线从左到右画出来；在对称轴处标出顶点；若一步里有两个点，就连成割线并比较它们的函数值；涂出区间；画出竖直或水平辅助线。
你只负责把详解拆成逐步画面，不要另起一种解法。只输出一个 JSON 对象，不要 Markdown。

每一步的画面必须跟上一步不同，并且只推进详解里的一个动作。建议 5 步：
1. 审题：画出函数，标出题设里的区间或点。
2. 到 4. 按详解逐条演算，每步新增一条辅助线、一个顶点，或一对用来比较的点。
5. 结论：给出答案，并说明其他选项错在哪。

系数必须是具体数字。详解用某个值举例时，曲线就用那个值，caption 里写明取值。
不要写入下一题的大题标题。

JSON 形状：
{
  "title": "第8题 · 二次函数的零点与单调",
  "meta": "按详解逐步作图",
  "curves": [
    {
      "id": "left",
      "preset": "quadratic",
      "quadratic": {"a": 1, "b": -4, "c": 2},
      "color": "#2457d6",
      "label": "a=-4 时 y=x^2-4x+2",
      "labelCorner": "left"
    }
  ],
  "steps": [
    {
      "id": "axis",
      "title": "标出对称轴",
      "caption": "60到160字，只讲这一步新算出的结论。",
      "formula": ["x=-\\\\frac{a}{2}", "a=-4"],
      "curves": ["left"],
      "intervals": [{"from": -1, "to": 2, "tone": "down", "label": "(-1,2) 递减"}],
      "markers": [],
      "guides": [{"x": 2, "label": "对称轴 x=2"}]
    },
    {
      "id": "signs",
      "title": "比较两端函数值",
      "caption": "这一步只比较区间两端。",
      "formula": ["f(-1)=7", "f(2)=-2"],
      "curves": ["left"],
      "intervals": [{"from": -1, "to": 2, "tone": "down", "label": "(-1,2)"}],
      "markers": [
        {"x": -1, "name": "f(-1)", "tone": "up"},
        {"x": 2, "name": "f(2)", "tone": "down"}
      ],
      "guides": [{"x": 2, "label": "对称轴 x=2"}]
    }
  ]
}

preset 只能是 square、quadratic、exponential、reciprocal、fraction-exp、linear-reciprocal。
quadratic 是 ax^2+bx+c，a、b、c 放在 quadratic 里。
exponential 的底数放在 base，且 base>0、base 不等于 1，add 是加上的常数。
reciprocal 是 k/(x-h)，放在 reciprocal 的 h、k 里，k 不能为 0。
linear-reciprocal 是 ax+k/x，放在 linearReciprocal 的 a、k 里。
fraction-exp 只需要 base。square 就是 y=x^2。
集合、命题或只讨论范围时，用 quadratic 的 a=0,b=0,c=0 当数轴，范围画成 intervals。
intervals 的 from、to 是 x。比较大小时 markers 必须正好两个。讨论对称轴时，guides 的 x 要等于顶点横坐标。
"""


def generate_animation(question: dict[str, Any]) -> dict[str, Any]:
    """Return a playable lesson, or a supported=False message when the model cannot."""
    if not _model_configured():
        return {
            "ok": True,
            "supported": False,
            "message": "未配置 DEEPSEEK_API_KEY，无法生成解题动画。",
        }
    prompt = _user_prompt(question)
    errors: list[str] = []
    scene: dict[str, Any] | None = None
    for _attempt in range(2):
        extra = ""
        if errors:
            extra = "\n上一次结果不能用：" + errors[-1] + "\n请重新输出完整 JSON。"
        try:
            raw = _model_complete(SYSTEM, prompt + extra)
        except Exception as exc:
            return {"ok": True, "supported": False, "message": f"DeepSeek 调用失败：{exc}"}
        parsed = _parse_scene(raw)
        if parsed is None:
            errors.append("没有返回可解析的场景 JSON")
            continue
        try:
            scene = normalize_scene(parsed)
            break
        except ValueError as exc:
            errors.append(str(exc))
            scene = None
    if scene is None:
        detail = errors[-1] if errors else "没有返回场景"
        return {"ok": True, "supported": False, "message": f"DeepSeek 给出的动画场景不可用：{detail}"}
    title = str(scene.get("title") or "DeepSeek 解题动画").strip()[:80]
    lesson = save_scene(str(question.get("id") or ""), scene, title=title)
    href = str(lesson["href"])
    if "auto=1" not in href:
        href += "&auto=1"
    return {
        "ok": True,
        "supported": True,
        "title": lesson["title"],
        "href": href,
        "scene": scene,
        "message": "",
    }


def normalize_scene(raw: dict[str, Any]) -> dict[str, Any]:
    """Turn a model scene into one validate_scene will accept and the player can draw."""
    if not isinstance(raw, dict):
        raise ValueError("场景必须是对象")
    curves = _curves(raw.get("curves"))
    if not curves:
        raise ValueError("至少需要一条系数全是数字的曲线")
    ids = [item["id"] for item in curves]
    steps = []
    for index, item in enumerate(raw.get("steps") or [], start=1):
        step = _step(item, index, ids)
        if step:
            steps.append(step)
        if len(steps) >= 8:
            break
    if len(steps) < 2:
        raise ValueError("至少需要两步，并且每一步都要有标题和说明")
    for step in steps:
        _arm_playback(step, curves)
    view = _span_view(curves, steps[0])
    for step in steps:
        step["view"] = _span_view(curves, step)
    scene = {
        "version": 1,
        "engine": "plane",
        "title": str(raw.get("title") or "DeepSeek 解题动画").strip()[:80] or "DeepSeek 解题动画",
        "meta": str(raw.get("meta") or "").strip()[:120],
        "view": view,
        "curves": curves,
        "steps": steps,
    }
    return validate_scene(scene)


def _user_prompt(question: dict[str, Any]) -> str:
    number = question.get("question_no") or ""
    parts = [f"请为第 {number} 题生成解题动画。"]
    stem = _clip(_plain(question.get("stem_md") or question.get("stem_text") or ""), 4000)
    if stem:
        parts.extend(["【题干】", stem])
    options = []
    for opt in question.get("options") or []:
        if not isinstance(opt, dict):
            continue
        label = str(opt.get("label") or "").strip()
        content = _clip(_plain(opt.get("content_md") or opt.get("content") or ""), 500)
        if label and content:
            options.append(f"{label}. {content}")
    if options:
        parts.extend(["【选项】", "\n".join(options)])
    answer = _clip(_plain(question.get("answer_md") or question.get("answer") or ""), 800)
    analysis = _clip(_plain(question.get("analysis_md") or question.get("analysis") or ""), 2000)
    solution = _clip(_plain(question.get("solution_md") or question.get("solution") or ""), 6000)
    if answer:
        parts.extend(["【答案】", answer])
    if analysis:
        parts.extend(["【分析】", analysis])
    if solution:
        parts.extend(["【详解】", solution])
    parts.append("请按详解的顺序输出场景 JSON。")
    return "\n".join(parts)


def _plain(text: str) -> str:
    raw = plain_solution(text)
    raw = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", raw)
    raw = re.sub(r"data:image/[^\s)]+", "", raw)
    return raw.strip()


def _clip(text: str, limit: int) -> str:
    found = _NEXT_SECTION.search(text)
    if found and found.start() > 0:
        text = text[: found.start()]
    return re.sub(r"\n{3,}", "\n\n", text).strip()[:limit]


def _parse_scene(raw: str) -> dict[str, Any] | None:
    data = _parse_json(raw)
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("steps"), list):
        return data
    inner = data.get("scene")
    if isinstance(inner, dict) and isinstance(inner.get("steps"), list):
        return inner
    return None


def _curves(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    curves: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, start=1):
        curve = _curve(item, index, seen)
        if curve:
            curves.append(curve)
        if len(curves) >= 4:
            break
    return curves


def _curve(raw: Any, index: int, seen: set[str]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    preset = str(raw.get("preset") or "")
    if preset not in _PRESETS:
        return None
    ident = re.sub(r"[^A-Za-z0-9_-]", "", str(raw.get("id") or f"c{index}"))[:24] or f"c{index}"
    while ident in seen:
        ident = (ident + "x")[:24]
    seen.add(ident)
    curve: dict[str, Any] = {
        "id": ident,
        "preset": preset,
        "color": str(raw.get("color") or "#2457d6")[:20],
        "label": str(raw.get("label") or "")[:80],
        "labelCorner": "right" if raw.get("labelCorner") == "right" else "left",
    }
    if preset == "quadratic":
        source = raw.get("quadratic") if isinstance(raw.get("quadratic"), dict) else raw
        coeffs = {name: _num(source.get(name)) for name in ("a", "b", "c")}
        if any(value is None for value in coeffs.values()):
            return None
        curve["quadratic"] = coeffs
    elif preset == "exponential":
        base = _num(raw.get("base"))
        add = _num(raw.get("add"))
        if base is None or base <= 0 or base == 1:
            return None
        curve["base"] = base
        curve["add"] = 0 if add is None else add
    elif preset == "reciprocal":
        source = raw.get("reciprocal") if isinstance(raw.get("reciprocal"), dict) else raw
        h, k = _num(source.get("h")), _num(source.get("k"))
        if h is None or k is None or k == 0:
            return None
        curve["reciprocal"] = {"h": h, "k": k}
    elif preset == "fraction-exp":
        base = _num(raw.get("base"))
        if base is None or base <= 0 or base == 1:
            return None
        curve["base"] = base
    elif preset == "linear-reciprocal":
        source = raw.get("linearReciprocal") if isinstance(raw.get("linearReciprocal"), dict) else raw
        a, k = _num(source.get("a")), _num(source.get("k"))
        if a is None or k is None or k == 0:
            return None
        curve["linearReciprocal"] = {"a": a, "k": k}
    domain = raw.get("domain") if isinstance(raw.get("domain"), dict) else {}
    cleaned_domain = {}
    start, end = _num(domain.get("from")), _num(domain.get("to"))
    if start is not None:
        cleaned_domain["from"] = start
    if end is not None:
        cleaned_domain["to"] = end
    if cleaned_domain:
        curve["domain"] = cleaned_domain
    return curve


def _step(raw: Any, index: int, curve_ids: list[str]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    title = re.sub(r"\s+", " ", str(raw.get("title") or "")).strip()[:40]
    caption = re.sub(r"\s+", " ", _clip(str(raw.get("caption") or ""), 500)).strip()
    if not title or len(caption) < 8:
        return None
    formulas = raw.get("formula") or []
    if isinstance(formulas, str):
        formulas = [formulas]
    if not isinstance(formulas, list):
        formulas = []
    formula = []
    for item in formulas:
        text = str(item or "").strip().strip("$")
        if text:
            formula.append(text[:400])
        if len(formula) >= 6:
            break
    wanted = raw.get("curves") or []
    if isinstance(wanted, str):
        wanted = [wanted]
    chosen = [str(item) for item in wanted if str(item) in curve_ids]
    step: dict[str, Any] = {
        "id": re.sub(r"[^A-Za-z0-9_-]", "", str(raw.get("id") or f"s{index}"))[:24] or f"s{index}",
        "title": title,
        "caption": caption,
        "formula": formula,
        "curves": chosen or curve_ids[:1],
        "intervals": _intervals(raw.get("intervals")),
        "markers": _markers(raw.get("markers")),
        "guides": _guides(raw.get("guides")),
    }
    focus = str(raw.get("curve") or "")
    if focus in curve_ids:
        step["curve"] = focus
    return step


def _intervals(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    items = []
    for raw_item in raw:
        if not isinstance(raw_item, dict):
            continue
        start, end = _num(raw_item.get("from")), _num(raw_item.get("to"))
        if start is None or end is None or start >= end:
            continue
        tone = raw_item.get("tone") if raw_item.get("tone") in ("up", "down") else "up"
        items.append(
            {
                "from": start,
                "to": end,
                "tone": tone,
                "label": str(raw_item.get("label") or "")[:40],
            }
        )
        if len(items) >= 4:
            break
    return items


def _markers(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    items = []
    for raw_item in raw:
        if not isinstance(raw_item, dict):
            continue
        x_value = _num(raw_item.get("x"))
        if x_value is None:
            continue
        tone = raw_item.get("tone") if raw_item.get("tone") in _TONES else "neutral"
        items.append({"x": x_value, "name": str(raw_item.get("name") or "")[:24], "tone": tone})
        if len(items) >= 6:
            break
    return items


def _guides(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    items = []
    for raw_item in raw:
        if not isinstance(raw_item, dict):
            continue
        x_value, y_value = _num(raw_item.get("x")), _num(raw_item.get("y"))
        if x_value is None and y_value is None:
            continue
        guide: dict[str, Any] = {"label": str(raw_item.get("label") or "")[:40]}
        if x_value is not None and y_value is None:
            guide["x"] = x_value
        elif y_value is not None and x_value is None:
            guide["y"] = y_value
        else:
            guide["x"] = x_value
        items.append(guide)
        if len(items) >= 6:
            break
    return items


def _arm_playback(step: dict[str, Any], curves: list[dict[str, Any]]) -> None:
    """Hand the step to the plane engine: draw the curve, and mark a vertex when this step uses it."""
    curve = next((item for item in curves if item["id"] == step["curves"][0]), curves[0])
    quad = curve.get("quadratic") or {}
    flat_axis = (
        curve["preset"] == "quadratic"
        and quad.get("a") == 0
        and quad.get("b") == 0
        and quad.get("c") == 0
    )
    step["draw"] = not flat_axis
    if len(step["markers"]) == 2:
        for index, marker in enumerate(step["markers"]):
            name = str(marker.get("name") or "")
            if not name or "=" in name or name.startswith("f(") or len(name) > 6:
                marker["name"] = "左端" if index == 0 else "右端"
    if not quad.get("a"):
        return
    vertex = -float(quad["b"]) / (2 * float(quad["a"]))
    text = step["title"] + step["caption"]
    near_guide = any(abs(float(guide.get("x", 10**6)) - vertex) < 0.2 for guide in step["guides"])
    if near_guide or "对称" in text or "顶点" in text:
        step["vertex"] = {"x": vertex, "label": "顶点"}


def _span_view(curves: list[dict[str, Any]], step: dict[str, Any]) -> dict[str, float]:
    """Frame one step tightly around its interval, points, and the vertex in that span."""
    xs: list[float] = []
    ys: list[float] = []
    curve_id = step["curves"][0]
    for interval in step["intervals"]:
        xs.extend([interval["from"], interval["to"]])
        _keep_y(ys, _curve_y(curves, curve_id, interval["from"]))
        _keep_y(ys, _curve_y(curves, curve_id, interval["to"]))
    for marker in step["markers"]:
        xs.append(marker["x"])
        _keep_y(ys, _curve_y(curves, curve_id, marker["x"]))
    for guide in step["guides"]:
        if "x" in guide:
            xs.append(guide["x"])
        if "y" in guide:
            ys.append(guide["y"])
    curve = next((item for item in curves if item["id"] == curve_id), curves[0])
    quad = curve.get("quadratic") or {}
    if xs and quad.get("a"):
        vertex = -quad["b"] / (2 * quad["a"])
        if min(xs) - 1 <= vertex <= max(xs) + 1:
            xs.append(vertex)
            _keep_y(ys, _curve_y(curves, curve["id"], vertex))
    if not xs:
        xs = [-4.0, 4.0]
    if not ys:
        ys = [-1.5, 1.5]
    x_pad = max(1.4, (max(xs) - min(xs)) * 0.22)
    y_pad = max(1.0, (max(ys) - min(ys)) * 0.2)
    return {
        "xMin": min(xs) - x_pad,
        "xMax": max(xs) + x_pad,
        "yMin": min(ys) - y_pad,
        "yMax": max(ys) + y_pad,
    }


def _keep_y(bucket: list[float], value: float | None) -> None:
    if value is not None and abs(value) < 80:
        bucket.append(value)


def _curve_y(curves: list[dict[str, Any]], curve_id: str, x_value: float) -> float | None:
    curve = next((item for item in curves if item["id"] == curve_id), curves[0])
    preset = curve["preset"]
    if preset == "square":
        return x_value * x_value
    if preset == "quadratic":
        quad = curve["quadratic"]
        return quad["a"] * x_value * x_value + quad["b"] * x_value + quad["c"]
    if preset == "linear-reciprocal":
        if x_value == 0:
            return None
        spec = curve["linearReciprocal"]
        return spec["a"] * x_value + spec["k"] / x_value
    if preset == "reciprocal":
        spec = curve["reciprocal"]
        if x_value == spec["h"]:
            return None
        return spec["k"] / (x_value - spec["h"])
    return None


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if number == number and abs(number) < 1e6 else None
    text = str(value).strip().replace("−", "-").replace(" ", "")
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
        return float(text)
    matched = re.fullmatch(r"([+-]?\d+)/(\d+)", text)
    if matched and int(matched.group(2)) != 0:
        return int(matched.group(1)) / int(matched.group(2))
    return None
