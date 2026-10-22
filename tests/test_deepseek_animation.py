import json

from word_math_md import deepseek_animation


QID = "fc66d711-9313-44ea-8398-478803c215f7"


def _scene(**overrides):
    scene = {
        "title": "第8题 · 零点与单调",
        "meta": "按详解的两种情形",
        "view": {"xMin": -4, "xMax": 4, "yMin": -4, "yMax": 8},
        "curves": [
            {
                "id": "f",
                "preset": "quadratic",
                "quadratic": {"a": "1", "b": "−4", "c": "2"},
                "label": "a=-4",
            }
        ],
        "steps": [
            {
                "id": "read",
                "title": "审题",
                "caption": "函数在开区间上单调，并且区间里恰好有一个零点。",
                "formula": "$f(x)=x^{2}+ax+2$",
                "intervals": [{"from": -1, "to": 2, "tone": "down", "label": "(-1,2)"}],
            },
            {
                "id": "case",
                "title": "递减段",
                "caption": "取 a=-4，对称轴在 x=2，区间落在递减段，f(-1)=7，f(2)=-2。",
                "formula": ["a\\le -4"],
                "markers": [
                    {"x": -1, "name": "f(-1)=7", "tone": "up"},
                    {"x": 2, "name": "f(2)=-2", "tone": "down"},
                ],
                "guides": [{"x": 2, "label": "对称轴"}, {"x": 1, "y": 3, "label": "丢掉横线"}],
            },
        ],
    }
    scene.update(overrides)
    return scene


def test_string_coefficients_become_a_playable_scene() -> None:
    scene = deepseek_animation.normalize_scene(_scene())
    curve = scene["curves"][0]
    assert curve["quadratic"] == {"a": 1.0, "b": -4.0, "c": 2.0}
    assert scene["steps"][0]["formula"] == ["f(x)=x^{2}+ax+2"]
    assert scene["steps"][1]["guides"] == [
        {"label": "对称轴", "x": 2.0},
        {"label": "丢掉横线", "x": 1.0},
    ]
    assert scene["view"]["xMin"] < -1
    assert scene["view"]["xMax"] > 2
    assert scene["steps"][0]["draw"] is True
    assert scene["steps"][1]["vertex"]["x"] == 2
    assert [item["name"] for item in scene["steps"][1]["markers"]] == ["左端", "右端"]
    assert scene["engine"] == "plane"


def test_prompt_stops_before_the_next_section_header() -> None:
    prompt = deepseek_animation._user_prompt(
        {
            "question_no": 8,
            "stem_md": "已知 $f(x)=x^2+ax+2$。",
            "options": [{"label": "C", "content_md": "$(-\\infty,-4]\\cup(3,+\\infty)$"}],
            "answer_md": "C",
            "solution_md": "故选 C。\n\n二、多选题\n21. 下一题不应该进入动画。",
        }
    )
    assert "故选 C" in prompt
    assert "二、多选题" not in prompt
    assert "下一题" not in prompt
    assert "C." in prompt


def test_model_scene_is_saved_for_the_player(monkeypatch) -> None:
    saved = {}

    def fake_complete(_system, _user):
        return json.dumps({"scene": _scene()})

    def fake_save(question_id, scene, *, title):
        saved["id"] = question_id
        saved["scene"] = scene
        saved["title"] = title
        return {"title": title, "href": f"/static/plane-player.html?scene=/static/scenes/authored/{question_id}.json&embed=1"}

    monkeypatch.setattr(deepseek_animation, "_model_complete", fake_complete)
    monkeypatch.setattr(deepseek_animation, "_model_configured", lambda: True)
    monkeypatch.setattr(deepseek_animation, "save_scene", fake_save)
    result = deepseek_animation.generate_animation({"id": QID, "question_no": 8, "stem_md": "题干"})
    assert result["supported"] is True
    assert f"{QID}.json" in result["href"]
    assert "auto=1" in result["href"]
    assert saved["id"] == QID
    assert saved["scene"]["steps"][1]["markers"][0]["x"] == -1


def test_a_bad_scene_is_sent_back_for_one_repair(monkeypatch) -> None:
    calls = {"n": 0}

    def fake_complete(_system, user):
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps({"title": "坏的", "curves": [{"preset": "parabola"}], "steps": []})
        assert "上一次结果不能用" in user
        return json.dumps(_scene())

    monkeypatch.setattr(deepseek_animation, "_model_complete", fake_complete)
    monkeypatch.setattr(deepseek_animation, "_model_configured", lambda: True)
    monkeypatch.setattr(
        deepseek_animation,
        "save_scene",
        lambda question_id, scene, title: {"title": title, "href": "/play"},
    )
    result = deepseek_animation.generate_animation({"id": QID, "question_no": 8})
    assert calls["n"] == 2
    assert result["supported"] is True


def test_missing_key_does_not_call_the_model(monkeypatch) -> None:
    monkeypatch.setattr(deepseek_animation, "_model_configured", lambda: False)

    def fail(_system, _user):
        raise AssertionError("should not call")

    monkeypatch.setattr(deepseek_animation, "_model_complete", fail)
    result = deepseek_animation.generate_animation({"id": QID})
    assert result["supported"] is False
    assert "DEEPSEEK_API_KEY" in result["message"]
