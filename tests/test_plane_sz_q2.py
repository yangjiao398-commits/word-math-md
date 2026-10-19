import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENE_PATH = ROOT / "word_math_md" / "static" / "scenes" / "sz-q2-piecewise.json"
PAGE_PATH = ROOT / "word_math_md" / "static" / "plane-sz-q2.html"
CATALOG_PATH = ROOT / "word_math_md" / "static" / "question-plane.js"
ENGINE_PATH = ROOT / "word_math_md" / "static" / "plane-scene.js"
QUESTION_ID = "c9a09c8c-1e42-4907-9f4a-80770c2048a5"


def _scene() -> dict:
    return json.loads(SCENE_PATH.read_text(encoding="utf-8"))


def _curve(name: str) -> dict:
    return next(curve for curve in _scene()["curves"] if curve["id"] == name)


def test_inner_value_uses_the_right_piece() -> None:
    right = _curve("right")
    assert right["preset"] == "reciprocal"
    assert right["reciprocal"] == {"h": 1, "k": 1}
    assert right["domain"]["from"] == 1
    assert 1 / (3 - 1) == 0.5
    inner = next(step for step in _scene()["steps"] if step["id"] == "inner")
    assert inner["curve"] == "right"
    assert inner["markers"][0]["x"] == 3
    assert r"\dfrac{1}{2}" in " ".join(inner["formula"])


def test_outer_value_uses_the_left_piece() -> None:
    left = _curve("left")
    assert left["preset"] == "quadratic"
    assert left["quadratic"] == {"a": 1, "b": 0, "c": -1}
    assert left["domain"]["to"] == 1
    assert (1 / 2) ** 2 - 1 == -0.75
    assert 3 ** 2 - 1 == 8
    outer = next(step for step in _scene()["steps"] if step["id"] == "outer")
    assert outer["curve"] == "left"
    assert outer["markers"][0]["x"] == 0.5
    joined = " ".join(outer["formula"])
    assert r"-\dfrac{3}{4}" in joined
    answer = next(step for step in _scene()["steps"] if step["id"] == "answer")
    assert "故选 B" in " ".join(answer["formula"])


def test_question_page_points_at_this_scene() -> None:
    page = PAGE_PATH.read_text(encoding="utf-8")
    catalog = CATALOG_PATH.read_text(encoding="utf-8")
    engine = ENGINE_PATH.read_text(encoding="utf-8")
    assert "/static/scenes/sz-q2-piecewise.json" in page
    assert "plane-scene.js?v=8" in page
    assert QUESTION_ID in catalog
    assert "/static/plane-sz-q2.html?embed=1" in catalog
    assert 'preset === "reciprocal"' in engine
    assert "curve.domain" in engine
