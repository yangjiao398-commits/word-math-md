from PIL import Image

from word_math_md.sheet_grade import answers_match, grade_paper
from word_math_md.sheet_ocr_v2 import (
    _predict,
    compose_reading_order,
    drop_text_covered_by_formula,
    is_formula_label,
    recognize_page,
)


def test_text_reader_is_called_without_batch_size():
    class TextModel:
        def predict(self, input, *, use_doc_orientation_classify=None):
            self.input = input
            return [{"res": {"rec_texts": ["1. A"]}}]

    model = TextModel()
    image = Image.new("RGB", (40, 20), "white")
    output = _predict(model, image)
    assert output[0]["res"]["rec_texts"] == ["1. A"]
    assert str(model.input).endswith("block.png")


def test_formula_labels_stay_out_of_text_ocr():
    assert is_formula_label("formula")
    assert is_formula_label("display_formula")
    assert not is_formula_label("formula_number")
    assert not is_formula_label("text")


def test_reading_order_keeps_question_number_beside_formula():
    text = compose_reading_order(
        [
            {"text": "15.", "x0": 10, "y0": 120, "x1": 40, "y1": 140},
            {"text": r"$\frac{2}{3}\pi+2$", "x0": 90, "y0": 40, "x1": 180, "y1": 70},
            {"text": "14.", "x0": 10, "y0": 42, "x1": 48, "y1": 64},
        ]
    )
    assert text.split("\n")[0] == "14."
    assert text.split("\n")[1] == r"$\frac{2}{3}\pi+2$"
    assert text.split("\n")[2] == "15."


def test_text_inside_a_formula_block_is_not_read_twice():
    regions = drop_text_covered_by_formula(
        [
            {"label": "formula", "x0": 0, "y0": 0, "x1": 100, "y1": 40},
            {"label": "text", "x0": 10, "y0": 8, "x1": 80, "y1": 30},
            {"label": "text", "x0": 0, "y0": 50, "x1": 40, "y1": 70},
        ]
    )
    assert [region["label"] for region in regions] == ["formula", "text"]


def test_page_sends_formula_crops_to_pix2tex_and_text_to_paddleocr():
    image = Image.new("RGB", (200, 80), "white")
    seen: list[str] = []

    def detect(_image):
        return [
            {"label": "text", "x0": 4, "y0": 4, "x1": 40, "y1": 28},
            {"label": "formula", "x0": 48, "y0": 4, "x1": 160, "y1": 36},
        ]

    def read_text(_crop):
        seen.append("text")
        return "14. 面积为"

    def read_formula(_crop):
        seen.append("formula")
        return r"\frac{2}{3}\pi+2"

    text = recognize_page(image, detect=detect, read_text=read_text, read_formula=read_formula)
    assert seen == ["text", "formula"]
    assert r"\frac{2}{3}\pi+2" in text
    questions = [
        {
            "question_no": 14,
            "type_code": "fill_blank",
            "answer_md": r"$\frac { 2 } { 3 }\pi+2$",
            "score": 5,
        }
    ]
    from word_math_md.sheet_grade import parse_answers_in_order

    answers = parse_answers_in_order(text, questions)
    assert answers_match("fill_blank", questions[0]["answer_md"], answers[14])[0]
    report = grade_paper(questions, answers)
    assert report["items"][0]["is_correct"] is True
