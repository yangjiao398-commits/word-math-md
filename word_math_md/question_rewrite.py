"""Rewrite a question's stem and answer while keeping the same exam point.

The rewriter does not call a language model. It currently adapts multiple-choice
items whose point is the negation of a quantified statement: the quantifier
flips, the set stays, and the predicate is negated. The numbers, the set, and
the correct letter change.
"""

from __future__ import annotations

import hashlib
import html
import re
from typing import Any

_PROP_RE = re.compile(
    r"命题\s*\$([A-Za-z])\$\s*[：:]\s*[“\"]\s*"
    r"\$(.+?)\$\s*[，,]\s*\$(.+?)\$\s*[”\"]",
    re.S,
)
_QUANT_RE = re.compile(
    r"^\\(forall|exists)\s*([A-Za-z])\s*\\(in|notin|subset|subseteq)\s*(.+)$",
    re.S,
)
_ANSWER_RE = re.compile(r"[A-Da-d]")

# Same trap shapes as the source item: one correct negation, and three options
# that change the quantifier or the set relation but still negate the predicate.
_PERMS = (
    ("correct", "keep_quant_flip_domain", "keep_quant_subset", "flip_quant_flip_domain"),
    ("keep_quant_flip_domain", "correct", "flip_quant_flip_domain", "keep_quant_subset"),
    ("flip_quant_flip_domain", "keep_quant_subset", "correct", "keep_quant_flip_domain"),
    ("keep_quant_subset", "flip_quant_flip_domain", "keep_quant_flip_domain", "correct"),
)
_LETTERS = "qrs"
_BANK = (
    {
        "var": "t",
        "interval": r"\left[-1,1\right]",
        "pred": r"2^{{v}+1}\ge 1",
        "neg": r"2^{{v}+1}<1",
    },
    {
        "var": "x",
        "interval": r"\left[1,3\right]",
        "pred": r"2^{{v}}\ge 2",
        "neg": r"2^{{v}}<2",
    },
    {
        "var": "u",
        "interval": r"\left[-3,-1\right]",
        "pred": r"{v}^{2}\ge 1",
        "neg": r"{v}^{2}<1",
    },
    {
        "var": "t",
        "interval": r"\left[2,5\right]",
        "pred": r"{v}-1\ge 1",
        "neg": r"{v}-1<1",
    },
)
_SUP = str.maketrans("0123456789+-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻")


def rewrite_question(row: dict[str, Any]) -> dict[str, Any]:
    """Return a rewritten stem, options, and answer for one stored question."""
    point = _point_name(row)
    body = _question_body(str(row.get("stem_md") or ""))
    parsed = _parse_proposition(body)
    if parsed is None or "否定" not in body:
        return {
            "ok": True,
            "supported": False,
            "point": point,
            "message": _unsupported_message(point),
        }

    seed = hashlib.sha256(
        (str(row.get("id") or "") + "\n" + _compact(body)).encode("utf-8")
    ).digest()
    variant = _pick_variant(seed, parsed)
    if variant is None:
        return {
            "ok": True,
            "supported": False,
            "point": point,
            "message": _unsupported_message(point),
        }

    letter = _pick_letter(seed, parsed["letter"])
    original_answer = _answer_letter(str(row.get("answer_md") or ""))
    perm_index = seed[1] % len(_PERMS)
    if "ABCD"[perm_index] == original_answer:
        perm_index = (perm_index + 1) % len(_PERMS)
    roles = _PERMS[perm_index]
    answer = "ABCD"[roles.index("correct")]

    options = []
    faults: list[str] = []
    for label, role in zip("ABCD", roles):
        content = _option_md(role, parsed["quant"], variant)
        options.append({"label": label, "content_md": content})
        fault = _role_fault(role, parsed["quant"])
        if fault:
            faults.append(f"{label} {fault}")

    stem = (
        f"命题${letter}$：“${_quant_md(parsed['quant'], variant['var'], variant['interval'])}$，"
        f"${variant['pred']}$”，则${letter}$的否定是（ ）"
    )
    negation = _option_md("correct", parsed["quant"], variant)
    solution = (
        f"命题${letter}$：“${_quant_md(parsed['quant'], variant['var'], variant['interval'])}$，"
        f"${variant['pred']}$”，则${letter}$的否定是“{negation}”。\n\n"
        + "；".join(faults)
        + f"。\n\n故选：{answer}."
    )
    quant_name = "全称" if parsed["quant"] == "forall" else "存在"
    flip_name = "存在" if parsed["quant"] == "forall" else "全称"
    analysis = (
        f"根据{quant_name}命题的否定：量词改为{flip_name}量词，范围不变，结论取否定."
    )
    return {
        "ok": True,
        "supported": True,
        "point": point or ("全称量词与存在量词" if parsed["quant"] == "forall" else "存在量词命题的否定"),
        "essence": _essence(parsed["quant"]),
        "changes": _changes(parsed, variant, letter, original_answer, answer),
        "stem_md": stem,
        "options": options,
        "answer": answer,
        "analysis_md": analysis,
        "solution_md": solution,
    }


def _unsupported_message(point: str) -> str:
    tagged = f"本题标注的考点是「{point}」。" if point else ""
    return (
        tagged
        + "这道题还不能按考点自动改编。目前会改编考查命题否定的选择题："
        "全称命题改成存在命题（或反过来），范围不动，只否定结论；"
        "题干里的集合、结论和正确选项字母会换成另一组。"
    )


def _essence(quant: str) -> str:
    if quant == "forall":
        rule = "把全称量词 ∀ 改成存在量词 ∃"
    else:
        rule = "把存在量词 ∃ 改成全称量词 ∀"
    return (
        f"考点精髓是这个命题怎么否定：{rule}，元素仍属于原来的集合，只把结论改成它的否定。"
        "改编后仍考这一条，只更换命题、范围和结论，并把正确选项换到另一个字母。"
    )


def _question_body(stem: str) -> str:
    text = html.unescape(stem or "").replace("&lt;", "<").replace("&gt;", ">")
    index = text.rfind("命题")
    if index >= 0:
        return text[index:]
    return text.strip()


def _parse_proposition(body: str) -> dict[str, str] | None:
    matched = _PROP_RE.search(body)
    if not matched:
        return None
    quant = _QUANT_RE.match(matched.group(2).strip())
    if not quant:
        return None
    return {
        "letter": matched.group(1),
        "quant": quant.group(1),
        "var": quant.group(2),
        "interval": quant.group(4).strip(),
        "pred": matched.group(3).strip(),
    }


def _pick_variant(seed: bytes, parsed: dict[str, str]) -> dict[str, str] | None:
    original = _compact(parsed["interval"] + parsed["pred"])
    count = len(_BANK)
    for step in range(count):
        item = _BANK[(seed[0] + step) % count]
        pred = item["pred"].replace("{v}", item["var"])
        neg = item["neg"].replace("{v}", item["var"])
        if _compact(item["interval"] + pred) == original:
            continue
        return {
            "var": item["var"],
            "interval": item["interval"],
            "pred": pred,
            "neg": neg,
        }
    return None


def _pick_letter(seed: bytes, original: str) -> str:
    count = len(_LETTERS)
    for step in range(count):
        letter = _LETTERS[(seed[2] + step) % count]
        if letter != original:
            return letter
    return "q"


def _answer_letter(answer: str) -> str:
    matched = _ANSWER_RE.search(answer or "")
    return matched.group(0).upper() if matched else ""


def _quant_md(quant: str, var: str, interval: str) -> str:
    symbol = r"\forall" if quant == "forall" else r"\exists"
    return f"{symbol} {var}\\in {interval}"


def _option_md(role: str, source_quant: str, variant: dict[str, str]) -> str:
    flipped = "exists" if source_quant == "forall" else "forall"
    if role == "correct":
        quant, rel = flipped, r"\in"
    elif role == "keep_quant_flip_domain":
        quant, rel = source_quant, r"\notin"
    elif role == "keep_quant_subset":
        quant, rel = source_quant, r"\subset"
    else:
        quant, rel = flipped, r"\notin"
    symbol = r"\forall" if quant == "forall" else r"\exists"
    return (
        f"${symbol} {variant['var']}{rel} {variant['interval']}$，"
        f"${variant['neg']}$"
    )


def _role_fault(role: str, source_quant: str) -> str:
    quant_name = "全称量词" if source_quant == "forall" else "存在量词"
    flipped_name = "存在量词" if source_quant == "forall" else "全称量词"
    if role == "keep_quant_flip_domain":
        return f"仍用{quant_name}，还把 $\\in$ 改成了 $\\notin$"
    if role == "keep_quant_subset":
        return f"仍用{quant_name}，并把 $\\in$ 写成了 $\\subset$"
    if role == "flip_quant_flip_domain":
        return f"量词改成了{flipped_name}，但把 $\\in$ 改成了 $\\notin$"
    return ""


def _changes(
    parsed: dict[str, str],
    variant: dict[str, str],
    letter: str,
    original_answer: str,
    answer: str,
) -> list[str]:
    rows = []
    if letter != parsed["letter"]:
        rows.append(f"命题字母由 {parsed['letter']} 改为 {letter}")
    if variant["var"] != parsed["var"]:
        rows.append(f"变量由 {parsed['var']} 改为 {variant['var']}")
    rows.append(f"范围由 {_plain(parsed['interval'])} 改为 {_plain(variant['interval'])}")
    rows.append(f"结论由 {_plain(parsed['pred'])} 改为 {_plain(variant['pred'])}")
    if original_answer:
        rows.append(f"正确选项由 {original_answer} 改为 {answer}")
    else:
        rows.append(f"正确选项是 {answer}")
    return rows


def _point_name(row: dict[str, Any]) -> str:
    names: list[str] = []
    for item in row.get("knowledge_points") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("minor_category") or item.get("description") or item.get("code") or "").strip()
        if name and name not in names:
            names.append(name)
    return "、".join(names)


def _plain(tex: str) -> str:
    text = _compact(tex)
    text = (
        text.replace(r"\geqslant", "≥")
        .replace(r"\leqslant", "≤")
        .replace(r"\geq", "≥")
        .replace(r"\leq", "≤")
        .replace(r"\ge", "≥")
        .replace(r"\le", "≤")
        .replace(r"\notin", "∉")
        .replace(r"\subseteq", "⊆")
        .replace(r"\subset", "⊂")
        .replace(r"\forall", "∀")
        .replace(r"\exists", "∃")
        .replace(r"\in", "∈")
        .replace(r"\cos", "cos ")
        .replace(r"\sin", "sin ")
    )
    text = re.sub(r"\^\{([0-9+-]+)\}", lambda match: match.group(1).translate(_SUP), text)
    text = re.sub(r"\^([0-9])", lambda match: match.group(1).translate(_SUP), text)
    text = re.sub(r"\^\{([^{}]+)\}", r"^(\1)", text)
    text = text.replace("{", "").replace("}", "").replace("\\", "")
    return text


def _compact(tex: str) -> str:
    text = html.unescape(tex or "")
    text = re.sub(r"\s+", "", text)
    text = text.replace(r"\left", "").replace(r"\right", "")
    text = text.replace(r"\geqslant", r"\ge").replace(r"\leqslant", r"\le")
    text = text.replace(r"\geq", r"\ge").replace(r"\leq", r"\le")
    text = text.replace(r"\dfrac", r"\frac")
    return text
