from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENE_PATH = ROOT / "word_math_md" / "static" / "scenes" / "sz-q3-inequality.json"
PAGE_PATH = ROOT / "word_math_md" / "static" / "plane-sz-q3.html"
CATALOG_PATH = ROOT / "word_math_md" / "static" / "question-plane.js"
QUESTION_ID = "d793894c-ce81-4d98-9f85-a98f435c1ea4"


def _scene() -> dict:
    import json

    return json.loads(SCENE_PATH.read_text(encoding="utf-8"))


def _y(x: float) -> float:
    return -x * x + 4 * x - 3


def test_parabola_passes_through_the_given_roots() -> None:
    curve = _scene()["curves"][0]
    assert curve["preset"] == "quadratic"
    assert curve["quadratic"] == {"a": -1, "b": 4, "c": -3}
    assert _y(1) == 0
    assert _y(3) == 0
    assert _y(2) == 1
    assert _y(0) < 0
    given = next(step for step in _scene()["steps"] if step["id"] == "given")
    assert [item["label"] for item in given["intervals"]] == ["(−∞, 1)", "(3, +∞)"]
    opening = " ".join(next(step for step in _scene()["steps"] if step["id"] == "opening")["formula"])
    assert "a<0" in opening


def test_vieta_gives_the_choice() -> None:
    vieta = " ".join(next(step for step in _scene()["steps"] if step["id"] == "vieta")["formula"])
    assert r"1+3=-\dfrac{b}{a}" in vieta
    assert r"1\times 3=-\dfrac{3}{a}" in vieta
    coefficient_a = " ".join(next(step for step in _scene()["steps"] if step["id"] == "coefficient-a")["formula"])
    assert "a=-1" in coefficient_a
    coefficient_b = next(step for step in _scene()["steps"] if step["id"] == "coefficient-b")
    assert coefficient_b["markers"][0]["x"] == 2
    assert "b=4" in " ".join(coefficient_b["formula"])
    assert 4 - (-1) == 5
    answer = " ".join(next(step for step in _scene()["steps"] if step["id"] == "answer")["formula"])
    assert "b-a=5" in answer
    assert "故选 D" in answer
    ids = [step["id"] for step in _scene()["steps"]]
    assert ids == [
        "given",
        "opening",
        "roots",
        "vieta",
        "coefficient-a",
        "coefficient-b",
        "difference",
        "answer",
    ]


def test_question_page_points_at_this_scene() -> None:
    page = PAGE_PATH.read_text(encoding="utf-8")
    catalog = CATALOG_PATH.read_text(encoding="utf-8")
    assert "/static/scenes/sz-q3-inequality.json" in page
    assert "plane-scene.js?v=11" in page
    assert QUESTION_ID in catalog
    assert "/static/plane-sz-q3.html?embed=1" in catalog
