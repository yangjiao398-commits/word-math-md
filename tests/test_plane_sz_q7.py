import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENE_PATH = ROOT / "word_math_md" / "static" / "scenes" / "sz-q7-minimum.json"
PAGE_PATH = ROOT / "word_math_md" / "static" / "plane-sz-q7.html"
CATALOG_PATH = ROOT / "word_math_md" / "static" / "question-plane.js"
ENGINE_PATH = ROOT / "word_math_md" / "static" / "plane-scene.js"
QUESTION_ID = "4129cbd6-c865-4b57-8d48-3c1b6a0ab0c8"


def _scene() -> dict:
    import json

    return json.loads(SCENE_PATH.read_text(encoding="utf-8"))


def _b(a: float) -> float:
    return (1 - a) / 2


def test_domain_and_oddness_follow_the_solution() -> None:
    scene = _scene()
    denom = next(item for item in scene["curves"] if item["id"] == "denom")
    assert denom["preset"] == "exponential"
    assert denom["base"] == math.pi
    assert denom["add"] == 1
    for x in (-1, 0, 1, 2):
        assert math.pi**x + 1 > 0
        assert math.pi**x + 1 < math.pi ** (x + 0.5) + 1
    odd = next(step for step in scene["steps"] if step["id"] == "odd")
    joined = " ".join(odd["formula"])
    assert r"\pi^{-x}-1" in joined
    assert r"\pi^{x}(\pi^{-x}-1)" in joined
    assert "=-f(x)" in joined
    rewrite = next(step for step in scene["steps"] if step["id"] == "rewrite")
    assert r"1-\dfrac{2}{\pi^{x}+1}" in " ".join(rewrite["formula"])


def test_minimum_follows_the_expansion() -> None:
    line = next(item for item in _scene()["curves"] if item["id"] == "line")
    assert line["quadratic"] == {"a": 0, "b": -0.5, "c": 0.5}
    assert _b(0.5) == 0.25
    assert 0.5 + 2 * 0.25 == 1
    assert 2 / 0.5 + 1 / 0.25 == 8
    expand = " ".join(next(step for step in _scene()["steps"] if step["id"] == "expand")["formula"])
    assert r"(a+2b)\left(\dfrac{2}{a}+\dfrac{1}{b}\right)" in expand
    assert r"4+\dfrac{a}{b}+\dfrac{4b}{a}" in expand
    inequality = " ".join(next(step for step in _scene()["steps"] if step["id"] == "inequality")["formula"])
    assert r"\ge 4+2\sqrt" in inequality
    assert "=8" in inequality
    minimum = next(step for step in _scene()["steps"] if step["id"] == "minimum")
    assert minimum["markers"][0]["x"] == 0.5
    joined = " ".join(minimum["formula"])
    assert r"a=\dfrac{1}{2}" in joined
    assert r"b=\dfrac{1}{4}" in joined
    assert "故选 D" in joined
    ids = [step["id"] for step in _scene()["steps"]]
    assert ids == ["domain", "odd", "rewrite", "increase", "relation", "expand", "inequality", "minimum"]


def test_question_page_points_at_this_scene() -> None:
    page = PAGE_PATH.read_text(encoding="utf-8")
    catalog = CATALOG_PATH.read_text(encoding="utf-8")
    engine = ENGINE_PATH.read_text(encoding="utf-8")
    assert "/static/scenes/sz-q7-minimum.json" in page
    assert "plane-scene.js?v=10" in page
    assert QUESTION_ID in catalog
    assert "/static/plane-sz-q7.html?embed=1&v=2" in catalog
    assert 'preset === "fraction-exp"' in engine
    assert "step.view" in engine
