"""Build an original practice variant from a real exam item.

The real item is only a base. A variant changes the numbers, the setting, or
the way the question is asked, then writes a solution for the new data. Item
shapes whose new answer can be recalculated stay local. The remaining items
go to DeepSeek, DashScope, or OpenAI when that key is configured.
"""

from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Callable

from word_math_md.question_rewrite import rewrite_question

Completer = Callable[[str, str], str]

VARIANT_SYSTEM = """你是高中数学变式题作者。用户给出的是一道真题底本，不是让你出一道无关新题，也不是让你誊抄原题。

请生成一道同核心考点的原创变式模拟题，并写出详细解答。

必须遵守：
1. 先确认核心考点，再在底本上变式。求解思路与底本同类。
2. 数据、背景、问法三项里至少改一项。数据指数字、系数、区间、参数；背景指情境和对象名称；问法指设问角度或所求目标。
3. 解答必须按新数据重新计算。禁止把底本的详解或选项换几个字后交上来。
4. 不要出现学校、年份、试卷名称。不要复述底本题干里连续 12 个以上的相同汉字，也不要照搬底本的整段公式。
5. 公式放在 $...$ 里。只输出一个 JSON 对象，不要代码围栏。
6. 先把新数据算通，再写题面。详解只保留从新数据到最终结果的正确推导。详解最后一行必须是「答案：」加上 answer 字段的原文。选择题的 answer 只能是一个大写字母，该选项的 content_md 必须等于详解算出的结果，并且这串内容要出现在详解中。禁止写试错过程，禁止写数据矛盾、结果不在选项中，或要求再改题。

JSON 字段：
point, essence, axis, changes, stem_md, options, answer, analysis_md, solution_md。
axis 使用“数据”“背景”“问法”，多项用顿号连接。
changes 是字符串数组，逐条写改了什么。
options 是 [{"label":"A","content_md":"..."}]，非选择题用 []。
"""

REPAIR_SYSTEM = """你是高中数学校对员。用户给出的变式题已经写好题干。不要另出一题，不要改题干里的数据、函数和设问。

请只根据这个题干重新计算，并改写答案、选项和详解，使三者一致。

必须遵守：
1. stem_md 原样返回，一个符号都不要改。
2. 详解只写这道题的正确推导。最后一行必须是「答案：」加上 answer 字段的原文。
3. 选择题：answer 只能是一个大写字母。该选项的 content_md 必须与详解算出的结果相同，并且这串内容要出现在详解中。如果现有选项都不是正确结果，把其中一个选项改成正确结果，再把 answer 改成该选项字母。其余选项保留为干扰项。
4. 非选择题：options 用 []。answer 写成详解最后算出的结果；answer 里的每一段公式都要原样出现在详解正文中。
5. 禁止出现这些说法：不在选项、与选项不符、选项不符、需重新、需调整、题设数据、若坚持选项、互相矛盾。
6. 公式放在 $...$ 里。只输出一个 JSON 对象，不要代码围栏。

JSON 字段：stem_md, options, answer, analysis_md, solution_md。
"""

_MARKS = ("命题", "不等式", "求值", "已知", "设函数", "计算")
_SCHOOL_MARKS = ("深圳外国语", "注意事项", "答题卡", "学科网")


def variant_question(row: dict[str, Any], *, complete: Completer | None = None) -> dict[str, Any]:
    """Return a variant of one stored question.

    Local recalculation wins. A text model is called only when this item has
    no local solver, and only when a key or an injected completer is available.
    """
    base = prepare_base(row)
    local = _local_variant(row, base)
    if local.get("supported"):
        return local
    caller = complete
    if caller is None and _model_configured():
        caller = _model_complete
    if caller is None:
        return local
    extra = ""
    drafted: dict[str, Any] | None = None
    for _attempt in range(2):
        try:
            drafted = _from_model(base, caller, extra=extra)
        except Exception as exc:
            local["message"] = f"变式模型调用失败：{exc}"
            return local
        if drafted.get("supported") and not _inconsistent(drafted):
            return drafted
        if drafted.get("supported") and _inconsistent(drafted):
            try:
                repaired = _repair_draft(base, drafted, caller)
            except Exception as exc:
                local["message"] = f"变式模型调用失败：{exc}"
                return local
            if repaired.get("supported") and not _inconsistent(repaired):
                return repaired
            if repaired.get("rejected"):
                drafted = repaired
        extra = (
            "上一次结果不能用：要么与底本过于接近，要么题干、选项和详解互相矛盾。"
            "请更换数据后重新计算。详解的最终结果必须与正确选项一致，"
            "不要在详解中承认算错或要求改题。"
        )
    if drafted and drafted.get("rejected"):
        return drafted
    if drafted and drafted.get("message"):
        local["message"] = str(drafted["message"])
    elif drafted and _inconsistent(drafted):
        local["message"] = "变式模型给出的题干、选项和详解不一致，已拒绝。"
    return local


def prepare_base(row: dict[str, Any]) -> dict[str, Any]:
    stem = _body(str(row.get("stem_md") or ""))
    analysis = html.unescape(str(row.get("analysis_md") or ""))
    solution = html.unescape(str(row.get("solution_md") or ""))
    options = []
    for opt in row.get("options") or []:
        if not isinstance(opt, dict):
            continue
        options.append(
            {
                "label": str(opt.get("label") or "").strip(),
                "content_md": html.unescape(str(opt.get("content_md") or "")),
            }
        )
    point = _point_name(row) or infer_point(stem, analysis, solution)
    return {
        "id": str(row.get("id") or ""),
        "type": str(row.get("type_code") or ""),
        "stem": stem,
        "options": options,
        "answer": html.unescape(str(row.get("answer_md") or "")).strip(),
        "analysis": analysis.strip(),
        "solution": solution.strip(),
        "point": point,
    }


def infer_point(stem: str, analysis: str = "", solution: str = "") -> str:
    blob = _compact(stem + "\n" + analysis + "\n" + solution)
    rules = (
        (("导数", "单调"), "利用导数求单调区间"),
        (("椭圆", "定值"), "圆锥曲线中的定值问题"),
        (("双曲线", "定值"), "圆锥曲线中的定值问题"),
        (("抛物线", "定值"), "圆锥曲线中的定值问题"),
        (("\\forall", "否定"), "全称量词命题的否定"),
        (("\\exists", "否定"), "存在量词命题的否定"),
        (("解集", "ax^{2}"), "由不等式解集用根与系数的关系确定系数"),
        (("x^{2}-1", "f(f"), "分段函数求值"),
        (("\\pi^{x}-1", "最小"), "利用函数奇偶性与基本不等式求最值"),
        (("扇形", "弧长"), "由弦长和圆心角求扇形弧长"),
        (("求值", "lg"), "指数幂与对数的求值"),
        (("求值", "\\log"), "指数幂与对数的求值"),
        (("\\sin",), "三角函数求值"),
        (("\\cos",), "三角函数求值"),
        (("集合",), "集合关系"),
        (("弹跳",), "指数模型的应用"),
        (("准偶",), "新定义下的函数性质"),
        (("零点",), "函数零点的大小关系"),
        (("最大值",), "函数最值"),
        (("最小值",), "函数最值"),
        (("定义域",), "定义域与集合的包含关系"),
        (("不动点",), "函数不动点"),
        (("反比",), "反比例关系下的最值"),
        (("单调",), "函数的单调性"),
        (("奇",), "函数的奇偶性"),
    )
    for keys, name in rules:
        if all(key in blob for key in keys):
            return name
    return "与底本同一求解思路"


def _from_model(base: dict[str, Any], complete: Completer, extra: str = "") -> dict[str, Any]:
    user = _base_prompt(base)
    if extra:
        user = user + "\n\n" + extra
    raw = complete(VARIANT_SYSTEM, user)
    payload = _parse_json(raw)
    if payload is None:
        return {"ok": True, "supported": False, "rejected": False, "message": "变式模型没有返回可解析的题目。"}
    stem = str(payload.get("stem_md") or "").strip()
    solution = str(payload.get("solution_md") or "").strip()
    answer = str(payload.get("answer") or "").strip()
    if not stem or not solution or not answer:
        return {"ok": True, "supported": False, "rejected": False, "message": "变式结果缺少题干、答案或详解。"}
    if _copied(base, stem, solution):
        return {
            "ok": True,
            "supported": False,
            "rejected": True,
            "point": base.get("point") or "",
            "message": "生成结果与真题底本过于接近，已拒绝。变式需要改动数据、背景或问法，并重写解答。",
        }
    axis = str(payload.get("axis") or "").strip()
    if not any(name in axis for name in ("数据", "背景", "问法")):
        axis = "数据"
    options = []
    for opt in payload.get("options") or []:
        if isinstance(opt, dict) and opt.get("label"):
            options.append({"label": str(opt["label"]).strip(), "content_md": str(opt.get("content_md") or "")})
    changes = [str(item) for item in (payload.get("changes") or []) if str(item).strip()]
    return {
        "ok": True,
        "supported": True,
        "source": "model",
        "point": str(payload.get("point") or base.get("point") or ""),
        "essence": str(payload.get("essence") or "变式保留底本的核心考点，并按改动后的题目重新解答。"),
        "axis": axis,
        "changes": changes,
        "stem_md": stem,
        "options": options,
        "answer": answer,
        "analysis_md": str(payload.get("analysis_md") or ""),
        "solution_md": solution,
    }


def _local_variant(row: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    for builder in (
        _from_quantifier,
        _from_quadratic,
        _from_piecewise,
        _from_fraction_minimum,
        _from_exp_log,
        _from_sector,
        _from_terminal_side,
    ):
        made = builder(row, base)
        if made:
            return made
    point = base.get("point") or infer_point(base.get("stem") or "", base.get("analysis") or "", base.get("solution") or "")
    named = point if point and point != "与底本同一求解思路" else ""
    lead = f"核心考点是「{named}」。" if named else "这道题的核心考点需要对照底本判断。"
    return {
        "ok": True,
        "supported": False,
        "rejected": False,
        "point": named,
        "message": (
            lead
            + "当前不能在本地改完数据后重新算对。"
            "在 .env 配置 DEEPSEEK_API_KEY、DASHSCOPE_API_KEY 或 OPENAI_API_KEY 后，"
            "会以真题为底本修改数据、背景或问法，再生成变式题和详解。"
        ),
    }


def _from_quantifier(row: dict[str, Any], base: dict[str, Any]) -> dict[str, Any] | None:
    made = rewrite_question(row)
    if not made.get("supported"):
        return None
    return _pack(
        base,
        point=str(made.get("point") or base.get("point") or ""),
        essence=str(made.get("essence") or ""),
        axis="数据",
        changes=list(made.get("changes") or []),
        stem=str(made.get("stem_md") or ""),
        options=list(made.get("options") or []),
        answer=str(made.get("answer") or ""),
        analysis=str(made.get("analysis_md") or ""),
        solution=str(made.get("solution_md") or ""),
    )


def _from_quadratic(row: dict[str, Any], base: dict[str, Any]) -> dict[str, Any] | None:
    parsed = _parse_quadratic(base["stem"])
    if not parsed:
        return None
    bank = ((-8, 2, 4), (-6, 1, 6), (-12, 2, 3), (-4, 1, 4), (-18, 3, 6))
    seed = _seed(base)
    original = (parsed["c"], parsed["r1"], parsed["r2"])
    chosen = None
    for step in range(len(bank)):
        item = bank[(seed[0] + step) % len(bank)]
        solved = _solve_quadratic(item[0], item[1], item[2])
        if solved and item != original:
            chosen = (item, solved)
            break
    if not chosen:
        return None
    (c, r1, r2), (a, b, diff) = chosen
    const = f"{c}" if c < 0 else f"+{c}"
    stem = (
        f"设 $a$，$b$ 为实数。不等式 $ax^{{2}}+bx{const}<0$ 的解集是 "
        f"$(-\\infty,{r1})\\cup({r2},+\\infty)$，则 $b-a$ 的值是（ ）"
    )
    distractors = [str(-diff), str(a), str(b)]
    options, answer = _choices(str(diff), distractors, _answer_letter(base["answer"]), seed[1])
    solution = (
        f"解集在 ${r1}$ 与 ${r2}$ 的两侧，所以抛物线开口向下，$a<0$，"
        f"并且 ${r1}$、${r2}$ 是方程 $ax^{{2}}+bx{const}=0$ 的两根。\n\n"
        f"由根与系数的关系，$"
        f"{r1}+{r2}=-\\dfrac{{b}}{{a}}$，${r1}\\times {r2}={_const_over_a(c)}$。"
        f"由第二式得 $a={a}$，再代入第一式得 $b={b}$。\n\n"
        f"因此 $b-a={b}-({a})={diff}$。\n\n故选：{answer}。"
    )
    return _pack(
        base,
        point=base["point"] or "由不等式解集用根与系数的关系确定系数",
        essence="核心考点仍是由解集判断开口并利用根与系数的关系求出系数。变式更换了常数项和两根，再按新数据重算 b-a。",
        axis="数据、问法",
        changes=[
            f"常数项由 {parsed['c']} 改为 {c}",
            f"两根由 {parsed['r1']}、{parsed['r2']} 改为 {r1}、{r2}",
            "设问前增加“设 a、b 为实数”，所求仍是 b-a",
            f"正确选项由 {_answer_letter(base['answer']) or '原字母'} 改为 {answer}",
        ],
        stem=stem,
        options=[{"label": label, "content_md": f"${value}$"} for label, value in options],
        answer=answer,
        analysis="先由解集在两根外侧得到 a<0，再用两根之和、两根之积求出 a、b，最后计算 b-a。",
        solution=solution,
    )


def _from_piecewise(row: dict[str, Any], base: dict[str, Any]) -> dict[str, Any] | None:
    compact = _compact(base["stem"])
    calls = re.sub(r"\{([^{}]*)\}", r"\1", compact)
    calls = re.sub(r"\{([^{}]*)\}", r"\1", calls)
    if "x^{2}-1" not in compact or r"\frac{1}{x-1}" not in compact or "f(f(3))" not in calls:
        return None
    # f(x)=x^2-9 (x≤3), 1/(x-3) (x>3). f(5)=1/2, f(1/2)=1/4-9=-35/4.
    stem = (
        "已知函数 $f(x)=\\begin{cases} x^{2}-9, & x\\le 3,\\\\ "
        "\\dfrac{1}{x-3}, & x>3.\\end{cases}$ 则 $f(f(5))=$（ ）"
    )
    options, answer = _choices(
        r"-\dfrac{35}{4}",
        [r"\dfrac{1}{2}", r"\dfrac{35}{4}", r"-\dfrac{9}{4}"],
        _answer_letter(base["answer"]),
        _seed(base)[1],
    )
    solution = (
        "因为 $5>3$，先用右侧解析式：$f(5)=\\dfrac{1}{5-3}=\\dfrac{1}{2}$。\n\n"
        "$\\dfrac{1}{2}\\le 3$，再代入左侧解析式："
        "$f\\left(\\dfrac{1}{2}\\right)=\\left(\\dfrac{1}{2}\\right)^{2}-9=\\dfrac{1}{4}-9=-\\dfrac{35}{4}$。\n\n"
        f"所以 $f(f(5))=-\\dfrac{{35}}{{4}}$。故选：{answer}。"
    )
    return _pack(
        base,
        point=base["point"] or "分段函数求值",
        essence="核心考点仍是按分段条件由外向内代入。变式改了分界点、左侧常数和代入的自变量。",
        axis="数据",
        changes=[
            "分界点由 1 改为 3，左侧由 x²-1 改为 x²-9",
            "右侧由 1/(x-1) 改为 1/(x-3)，所求由 f(f(3)) 改为 f(f(5))",
        ],
        stem=stem,
        options=[{"label": label, "content_md": f"${value}$"} for label, value in options],
        answer=answer,
        analysis="先判断外层自变量落在哪一段，求出内层函数值后，再判断这个值落在哪一段。",
        solution=solution,
    )


def _from_fraction_minimum(row: dict[str, Any], base: dict[str, Any]) -> dict[str, Any] | None:
    compact = _compact(base["stem"])
    if r"\pi^{x}-1" not in compact or "2b-1" not in compact or r"\frac{2}{a}" not in compact:
        return None
    stem = (
        "已知函数 $f(x)=\\dfrac{3^{x}-1}{3^{x}+1}$。若正数 $a$、$b$ 满足 "
        "$f(a)+f(3b-1)=0$，则 $\\dfrac{3}{a}+\\dfrac{1}{b}$ 的最小值是（ ）"
    )
    options, answer = _choices("12", ["8", "10", "16"], _answer_letter(base["answer"]), _seed(base)[1])
    solution = (
        "对任意实数 $x$，$3^{x}+1>0$。又 $f(-x)=-f(x)$，所以 $f$ 是奇函数。\n\n"
        "由 $f(a)+f(3b-1)=0$ 得 $f(3b-1)=-f(a)=f(-a)$。$f$ 单调，因此 $3b-1=-a$，即 $a+3b=1$。\n\n"
        "因为 $a>0$、$b>0$，所以 $b<\\dfrac{1}{3}$。于是\n"
        "$(a+3b)\\left(\\dfrac{3}{a}+\\dfrac{1}{b}\\right)=6+\\dfrac{a}{b}+\\dfrac{9b}{a}"
        "\\ge 6+2\\sqrt{\\dfrac{a}{b}\\cdot\\dfrac{9b}{a}}=12$，\n"
        "当且仅当 $\\dfrac{a}{b}=\\dfrac{9b}{a}$，即 $a=3b$ 时等号成立。"
        "结合 $a+3b=1$ 得 $a=\\dfrac{1}{2}$，$b=\\dfrac{1}{6}$。\n\n"
        f"所以最小值为 $12$。故选：{answer}。"
    )
    return _pack(
        base,
        point=base["point"] or "利用函数奇偶性与基本不等式求最值",
        essence="核心考点仍是先用奇函数把函数方程改成线性关系，再用基本不等式求最值。变式更换了底数、线性关系和待求式的系数。",
        axis="数据",
        changes=[
            "函数底数由 π 改为 3",
            "条件由 f(a)+f(2b-1)=0 改为 f(a)+f(3b-1)=0",
            "所求由 2/a+1/b 改为 3/a+1/b，最小值由 8 改为 12",
        ],
        stem=stem,
        options=[{"label": label, "content_md": f"${value}$"} for label, value in options],
        answer=answer,
        analysis="先证明奇函数，把条件化成 a+3b=1，再把该式与所求式相乘，用基本不等式求最小值。",
        solution=solution,
    )


def _from_exp_log(row: dict[str, Any], base: dict[str, Any]) -> dict[str, Any] | None:
    compact = _compact(base["stem"])
    if "求值" not in compact or "8^{\\frac{1}{3}}" not in compact or "lg100" not in compact:
        return None
    stem = r"计算：$27^{\frac{1}{3}}+\lg 1000+3^{1+\log_{3}2}=$________."
    solution = (
        "$27^{\\frac{1}{3}}=3$，$\\lg 1000=3$。\n\n"
        "$3^{1+\\log_{3}2}=3\\times 3^{\\log_{3}2}=3\\times 2=6$。\n\n"
        "所以原式 $=3+3+6=12$。"
    )
    return _pack(
        base,
        point=base["point"] or "指数幂与对数的求值",
        essence="核心考点仍是把根式幂写成同底数幂，并把对数式化成整数或系数。数字和设问用词都已更换。",
        axis="数据、问法",
        changes=[
            "8^{1/3} 改为 27^{1/3}，lg100 改为 lg1000",
            "2^{1+log2 3} 改为 3^{1+log3 2}",
            "问法由“求值”改为“计算”，结果由 10 改为 12",
        ],
        stem=stem,
        options=[],
        answer="12",
        analysis="分别把立方根、常用对数和同底数指数式化简，再相加。",
        solution=solution,
    )


def _from_sector(row: dict[str, Any], base: dict[str, Any]) -> dict[str, Any] | None:
    compact = _compact(base["stem"])
    if "扇形" not in compact or "弧长" not in compact or "弦长" not in compact:
        return None
    if r"\frac{2}{3}\pi" not in compact and r"\frac{2\pi}{3}" not in compact:
        return None
    stem = (
        "一个扇形窗的圆心角为 $\\dfrac{\\pi}{2}$，所对的弦长为 $2\\sqrt{2}$，"
        "求这条弧的长度。（结果用弧度制表示）"
    )
    solution = (
        "设半径为 $r$，圆心角 $\\alpha=\\dfrac{\\pi}{2}$。弦长公式为 $2r\\sin\\dfrac{\\alpha}{2}$。\n\n"
        "$\\sin\\dfrac{\\pi}{4}=\\dfrac{\\sqrt{2}}{2}$，所以 $2r\\cdot\\dfrac{\\sqrt{2}}{2}=2\\sqrt{2}$，得 $r=2$。\n\n"
        "弧长为 $r\\alpha=2\\times\\dfrac{\\pi}{2}=\\pi$。"
    )
    return _pack(
        base,
        point=base["point"] or "由弦长和圆心角求扇形弧长",
        essence="核心考点仍是先由圆心角和弦长求半径，再用弧长公式。背景改成扇形窗，圆心角和弦长也换了。",
        axis="数据、背景",
        changes=[
            "背景由试卷中的扇形改为扇形窗",
            "圆心角由 2π/3 改为 π/2，弦长由 2√3 改为 2√2",
            "弧长由 4π/3 改为 π",
        ],
        stem=stem,
        options=[],
        answer=r"\pi",
        analysis="取半条弦，用正弦求出半径，再乘圆心角。",
        solution=solution,
    )


def _from_terminal_side(row: dict[str, Any], base: dict[str, Any]) -> dict[str, Any] | None:
    compact = _compact(base["stem"])
    if "终边经过点" not in compact or r"\frac{5\pi}{3}" not in compact or r"\pi+" not in compact:
        return None
    # P(sin(11π/6), cos(11π/6)) = (-1/2, √3/2), r=1, sin β = √3/2, sin(π+β) = -√3/2.
    answer_tex = r"-\dfrac{\sqrt{3}}{2}"
    options, answer = _choices(
        answer_tex,
        [r"-\dfrac{1}{2}", r"\dfrac{1}{2}", r"\dfrac{\sqrt{3}}{2}"],
        _answer_letter(base["answer"]),
        _seed(base)[1],
    )
    stem = (
        r"角 $\beta$ 的终边经过点 $P\left(\sin\dfrac{11\pi}{6},\cos\dfrac{11\pi}{6}\right)$，"
        r"则 $\sin(\pi+\beta)=$（ ）"
    )
    solution = (
        r"$\sin\dfrac{11\pi}{6}=\sin\left(2\pi-\dfrac{\pi}{6}\right)=-\sin\dfrac{\pi}{6}=-\dfrac{1}{2}$，"
        r"$\cos\dfrac{11\pi}{6}=\cos\left(2\pi-\dfrac{\pi}{6}\right)=\cos\dfrac{\pi}{6}=\dfrac{\sqrt{3}}{2}$。"
        "\n\n所以终边经过点 $P\\left(-\\dfrac{1}{2},\\dfrac{\\sqrt{3}}{2}\\right)$。"
        "半径 $r=\\sqrt{\\left(-\\dfrac{1}{2}\\right)^{2}+\\left(\\dfrac{\\sqrt{3}}{2}\\right)^{2}}=1$，"
        "由三角函数定义得 $\\sin\\beta=\\dfrac{y}{r}=\\dfrac{\\sqrt{3}}{2}$。\n\n"
        "再由诱导公式 $\\sin(\\pi+\\beta)=-\\sin\\beta=-\\dfrac{\\sqrt{3}}{2}$。\n\n"
        f"故选：{answer}。"
    )
    return _pack(
        base,
        point="三角函数定义与诱导公式",
        essence="核心考点仍是先求出终边所过点的坐标，再用正弦定义得到正弦，最后用 sin(π+β)=-sin β。变式把角度从 5π/3 换成了 11π/6。",
        axis="数据",
        changes=[
            "角度由 5π/3 改为 11π/6，角的字母由 α 改为 β",
            "点由 P(-√3/2, 1/2) 改为 P(-1/2, √3/2)",
            "sin(π+角) 的值由 -1/2 改为 -√3/2",
            f"正确选项由 {_answer_letter(base['answer']) or '原字母'} 改为 {answer}",
        ],
        stem=stem,
        options=[{"label": label, "content_md": f"${value}$"} for label, value in options],
        answer=answer,
        analysis="先把特殊角化成 2π 减去锐角，求出点的横、纵坐标，再除以半径，并用诱导公式变号。",
        solution=solution,
    )


def _pack(
    base: dict[str, Any],
    *,
    point: str,
    essence: str,
    axis: str,
    changes: list[str],
    stem: str,
    options: list[dict[str, str]],
    answer: str,
    analysis: str,
    solution: str,
) -> dict[str, Any]:
    if _copied(base, stem, solution):
        return {}
    return {
        "ok": True,
        "supported": True,
        "source": "local",
        "point": point,
        "essence": essence,
        "axis": axis,
        "changes": changes,
        "stem_md": stem,
        "options": options,
        "answer": answer,
        "analysis_md": analysis,
        "solution_md": solution,
    }


def _parse_quadratic(stem: str) -> dict[str, int] | None:
    compact = _compact(stem)
    matched = re.search(
        r"不等式\$(ax\^\{2\}\+bx([+-]\d+)?(?:\\le|\\ge|<|>)0)\$的解集是"
        r"\$?\(\{?(?:-\\infty),([0-9+-]+)\}?\)\\cup\(\{?([0-9+-]+),(?:\+)?\\infty\}?\)",
        compact,
    )
    if not matched or "<" not in matched.group(1):
        return None
    const = matched.group(2) or "+0"
    return {"c": int(const), "r1": int(matched.group(3)), "r2": int(matched.group(4))}


def _solve_quadratic(c: int, r1: int, r2: int) -> tuple[int, int, int] | None:
    product = r1 * r2
    if product == 0 or c % product != 0:
        return None
    a = c // product
    if a >= 0:
        return None
    b = -a * (r1 + r2)
    return a, b, b - a


def _const_over_a(c: int) -> str:
    if c < 0:
        return f"-\\dfrac{{{abs(c)}}}{{a}}"
    return f"\\dfrac{{{c}}}{{a}}"


def _choices(correct: str, distractors: list[str], original: str, seed: int) -> tuple[list[tuple[str, str]], str]:
    values: list[str] = []
    for value in [correct, *distractors]:
        if value not in values:
            values.append(value)
    values = values[:4]
    while len(values) < 4:
        values.append(f"{correct}+{len(values)}")
    start = seed % 4
    if "ABCD"[start] == original:
        start = (start + 1) % 4
    ordered = values[start:] + values[:start]
    # Rotate so the correct value sits at `start`, unless that letter is the original answer.
    # values[0] is correct. Place it at index start.
    placed = [""] * 4
    placed[start] = correct
    rest = [item for item in values if item != correct]
    cursor = 0
    for index in range(4):
        if placed[index]:
            continue
        placed[index] = rest[cursor]
        cursor += 1
    pairs = list(zip("ABCD", placed))
    return pairs, "ABCD"[start]


def _choice_letter(answer: str) -> str:
    text = re.sub(r"^(答案|故选)[:：]?", "", (answer or "").strip())
    text = re.sub(r"[【】\[\]（）()\s。．.]", "", text)
    if re.fullmatch(r"[A-Da-d]", text):
        return text.upper()
    return ""


def _math_key(text: str) -> str:
    value = _compact(text).replace("$", "").replace("{", "").replace("}", "")
    value = value.replace(r"\,", "").replace(r"\;", "").replace(r"\!", "").replace("~", "")
    value = value.replace(r"\displaystyle", "").replace(r"\quad", "").replace(r"\qquad", "")
    value = value.replace("−", "-").replace("–", "-")
    return value


def _inconsistent(drafted: dict[str, Any]) -> bool:
    blob = str(drafted.get("solution_md") or "") + str(drafted.get("analysis_md") or "")
    marks = ("不在选项", "与选项不符", "选项不符", "需重新", "需调整", "题设数据", "若坚持选项", "互相矛盾")
    if any(mark in blob for mark in marks):
        return True
    answer = str(drafted.get("answer") or "")
    solution = _math_key(str(drafted.get("solution_md") or ""))
    letter = _choice_letter(answer)
    if not letter:
        fragments = _answer_fragments(answer)
        return any(fragment not in solution for fragment in fragments)
    matched = next((opt for opt in drafted.get("options") or [] if str(opt.get("label") or "") == letter), None)
    if not matched:
        return True
    content = _math_key(str(matched.get("content_md") or ""))
    return bool(content) and content not in solution


def _answer_fragments(answer: str) -> list[str]:
    fragments = [_math_key(part) for part in re.findall(r"\$([^$]+)\$", answer or "")]
    fragments = [part for part in fragments if part]
    if fragments:
        return fragments
    key = _math_key(answer)
    return [key] if key else []


def _repair_draft(base: dict[str, Any], drafted: dict[str, Any], complete: Completer) -> dict[str, Any]:
    """Ask the model to re-solve the draft it already wrote, without a new stem."""
    raw = complete(REPAIR_SYSTEM, _repair_prompt(drafted))
    payload = _parse_json(raw)
    if payload is None:
        return {"ok": True, "supported": False, "rejected": False, "message": "变式校对没有返回可解析的题目。"}
    stem = str(drafted.get("stem_md") or "")
    solution = str(payload.get("solution_md") or "").strip()
    answer = str(payload.get("answer") or "").strip()
    if not solution or not answer:
        return {"ok": True, "supported": False, "rejected": False, "message": "变式校对缺少答案或详解。"}
    if _copied(base, stem, solution):
        return {
            "ok": True,
            "supported": False,
            "rejected": True,
            "point": drafted.get("point") or "",
            "message": "生成结果与真题底本过于接近，已拒绝。变式需要改动数据、背景或问法，并重写解答。",
        }
    options = []
    for opt in payload.get("options") or []:
        if isinstance(opt, dict) and opt.get("label"):
            options.append({"label": str(opt["label"]).strip(), "content_md": str(opt.get("content_md") or "")})
    if not options:
        options = list(drafted.get("options") or [])
    return {
        "ok": True,
        "supported": True,
        "source": "model",
        "point": str(drafted.get("point") or base.get("point") or ""),
        "essence": str(drafted.get("essence") or ""),
        "axis": str(drafted.get("axis") or "数据"),
        "changes": list(drafted.get("changes") or []),
        "stem_md": stem,
        "options": options,
        "answer": answer,
        "analysis_md": str(payload.get("analysis_md") or drafted.get("analysis_md") or ""),
        "solution_md": solution,
    }


def _repair_prompt(drafted: dict[str, Any]) -> str:
    option_text = "\n".join(
        f"{opt.get('label')}. {opt.get('content_md')}"
        for opt in drafted.get("options") or []
        if opt.get("label")
    )
    return "\n".join(
        [
            "下面这道变式的题干、选项和详解不一致。请按题干重算，不要改题干。",
            "【题干】",
            str(drafted.get("stem_md") or ""),
            "【当前选项】",
            option_text or "（无，非选择题）",
            "【当前答案】",
            str(drafted.get("answer") or ""),
            "【当前详解】",
            str(drafted.get("solution_md") or "")[:8000],
            "请输出校对后的 JSON。stem_md 必须与上面的题干完全相同。",
        ]
    )


def _copied(base: dict[str, Any], stem: str, solution: str) -> bool:
    combined = stem + "\n" + solution
    if any(mark in combined for mark in _SCHOOL_MARKS):
        return True
    original = _compact(base.get("stem") or "")
    revised = _compact(stem)
    if original and original == revised:
        return True
    if _shares_run(_surface(base.get("stem") or ""), _surface(stem), 12):
        return True
    if len(original) >= 28:
        for index in range(0, len(original) - 27):
            chunk = original[index : index + 28]
            if "\\" in chunk and chunk in revised:
                return True
    return False


def _surface(text: str) -> str:
    compact = _compact(text)
    # Keep a break where a formula was, so Chinese on either side is not glued into one run.
    compact = re.sub(r"\$[^$]*\$", "|", compact)
    compact = re.sub(r"\\\[[\s\S]*?\\\]", "|", compact)
    compact = re.sub(r"\\[A-Za-z]+", "", compact)
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff|]", "", compact)


def _shares_run(left: str, right: str, size: int) -> bool:
    """True when any formula-free piece shares a run. The pipe is a formula break."""
    right_parts = [part for part in right.split("|") if len(part) >= size]
    if not right_parts:
        return False
    for part in left.split("|"):
        if len(part) < size:
            continue
        seen = {part[index : index + size] for index in range(len(part) - size + 1)}
        for piece in right_parts:
            if any(piece[index : index + size] in seen for index in range(len(piece) - size + 1)):
                return True
    return False


def _base_prompt(base: dict[str, Any]) -> str:
    option_text = "\n".join(
        f"{opt['label']}. {opt['content_md']}" for opt in base.get("options") or [] if opt.get("label")
    )
    parts = [
        f"核心考点提示：{base.get('point') or '请根据底本自行判断'}",
        "【题干】",
        str(base.get("stem") or "")[:8000],
    ]
    if option_text:
        parts.extend(["【选项】", option_text[:4000]])
    if base.get("answer"):
        parts.extend(["【答案】", str(base["answer"])[:1000]])
    if base.get("analysis"):
        parts.extend(["【分析】", str(base["analysis"])[:4000]])
    if base.get("solution"):
        parts.extend(["【详解】", str(base["solution"])[:8000]])
    parts.append("请只基于这道底本做变式，并输出 JSON。")
    return "\n".join(parts)


def _parse_json(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _model_configured() -> bool:
    return bool(
        os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("DASHSCOPE_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )


def _model_complete(system: str, user: str) -> str:
    if os.environ.get("DEEPSEEK_API_KEY"):
        url = os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/chat/completions"
        key = os.environ["DEEPSEEK_API_KEY"]
        model = os.environ.get("DEEPSEEK_MODEL") or "deepseek-reasoner"
    elif os.environ.get("DASHSCOPE_API_KEY"):
        url = os.environ.get("DASHSCOPE_BASE_URL") or (
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        )
        key = os.environ["DASHSCOPE_API_KEY"]
        model = os.environ.get("VARIANT_MODEL") or os.environ.get("DASHSCOPE_TEXT_MODEL") or "qwen-plus"
    else:
        url = os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1/chat/completions"
        key = os.environ.get("OPENAI_API_KEY") or ""
        model = os.environ.get("VARIANT_MODEL") or os.environ.get("OPENAI_VARIANT_MODEL") or "gpt-4o-mini"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    reasoning = "reasoner" in model
    if reasoning:
        payload["max_tokens"] = 8192
    else:
        payload["temperature"] = 0.3
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180 if reasoning else 90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    message = ((data.get("choices") or [{}])[0].get("message") or {})
    content = str(message.get("content") or "").strip()
    if not content:
        content = str(message.get("reasoning_content") or "")
    return content


def _body(stem: str) -> str:
    text = html.unescape(stem or "").replace("&lt;", "<").replace("&gt;", ">")
    best = -1
    for mark in _MARKS:
        index = text.rfind(mark)
        if index > best:
            best = index
    if best >= 0:
        return text[best:].strip()
    return text.strip()


def _point_name(row: dict[str, Any]) -> str:
    names: list[str] = []
    for item in row.get("knowledge_points") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("minor_category") or item.get("description") or "").strip()
        if name and name not in names:
            names.append(name)
    return "、".join(names)


def _answer_letter(answer: str) -> str:
    matched = re.search(r"[A-Da-d]", answer or "")
    return matched.group(0).upper() if matched else ""


def _seed(base: dict[str, Any]) -> bytes:
    import hashlib

    return hashlib.sha256((base.get("id") or base.get("stem") or "").encode("utf-8")).digest()


def _compact(text: str) -> str:
    value = html.unescape(text or "")
    value = value.replace("&lt;", "<").replace("&gt;", ">")
    value = re.sub(r"\s+", "", value)
    value = value.replace(r"\left", "").replace(r"\right", "")
    value = value.replace(r"\leqslant", r"\le").replace(r"\geqslant", r"\ge")
    value = value.replace(r"\leq", r"\le").replace(r"\geq", r"\ge")
    value = value.replace(r"\dfrac", r"\frac")
    return value
