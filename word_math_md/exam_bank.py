"""Parse Markdown papers and import them into the Supabase exam bank."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH)


def _load_env() -> None:
    load_dotenv(ENV_PATH, override=False)
    if not (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")):
        load_dotenv(ENV_PATH, override=True)

BUCKET = "exam-assets"
PAPER_SEMESTERS = (
    "高一上学期",
    "高一下学期",
    "高二上学期",
    "高二下学期",
    "高三上学期",
    "高三下学期",
)
PAPER_EXAM_TYPES = ("月考", "期中", "期末")
PAPER_PROVINCES = (
    "北京",
    "天津",
    "河北",
    "山西",
    "内蒙古",
    "辽宁",
    "吉林",
    "黑龙江",
    "上海",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "广西",
    "海南",
    "重庆",
    "四川",
    "贵州",
    "云南",
    "西藏",
    "陕西",
    "甘肃",
    "青海",
    "宁夏",
    "新疆",
)
PAPER_GAOKAO_PAPERS = ("全国A卷", "全国B卷")
_PROVINCE_SET = set(PAPER_PROVINCES)
_PROVINCE_ALIASES = {
    "北京市": "北京",
    "天津市": "天津",
    "上海市": "上海",
    "重庆市": "重庆",
    "内蒙古自治区": "内蒙古",
    "广西壮族自治区": "广西",
    "西藏自治区": "西藏",
    "宁夏回族自治区": "宁夏",
    "新疆维吾尔自治区": "新疆",
    "新疆维吾尔族自治区": "新疆",
}
_GAOKAO_PAPER_ALIASES = {
    "A卷": "全国A卷",
    "全国卷A": "全国A卷",
    "全国甲卷": "全国A卷",
    "甲卷": "全国A卷",
    "B卷": "全国B卷",
    "全国卷B": "全国B卷",
    "全国乙卷": "全国B卷",
    "乙卷": "全国B卷",
}
_PAPER_LIST_SELECT = (
    "id,paper_code,title,source_filename,semester,exam_type,"
    "province,gaokao_paper,created_at,updated_at"
)
SECTION_MARKERS = ("【答案】", "【解析】", "【分析】", "【详解】", "【知识点】")
MARKER_TO_KEY = {
    "【答案】": "answer",
    "【解析】": "analysis",
    "【分析】": "analysis",
    "【详解】": "detail",
    "【知识点】": "knowledge",
}
QUESTION_RE = re.compile(
    r"(?:^|\n)\s*(?:#{1,6}\s*)?(?:第\s*(\d+)\s*题|(\d+)\s*(?:\\\.|[.．、]))(?:\s+|(?=\S))"
)
OPTION_RE = re.compile(
    r"(?m)^[ \t]*(?:[(（]\s*)?([A-G])(?:[)）]|[.．、])[ \t]+"
)
SCORE_RE = re.compile(r"[（(]\s*(\d+(?:\.\d+)?)\s*分\s*[）)]")
SUBQUESTION_SCORE_RE = re.compile(r"本小题满分\s*(\d+(?:\.\d+)?)\s*分")
SECTION_HEADER_RE = re.compile(
    r"(?:^|\n)\s*(?:\*{0,2})\s*[一二三四五六七八九十][、､.．]\s*"
    r"(?P<label>单项选择题|多项选择题|单项选择|多项选择|单选题|多选题|选择题|填空题|解答题)"
    r"(?P<rest>[^\n]{0,180})",
)
SECTION_COUNT_RE = re.compile(r"共\s*(\d+)\s*小题")
SECTION_EACH_RE = re.compile(r"每小?题\s*(\d+(?:\.\d+)?)\s*分")
SECTION_TOTAL_RE = re.compile(r"共\s*(\d+(?:\.\d+)?)\s*分")
QUESTION_RANGE_SCORE_RE = re.compile(
    r"第\s*(\d+)\s*[~\-～—至到]\s*(\d+)\s*题[^。\n]{0,40}每小?题\s*(\d+(?:\.\d+)?)\s*分"
)
QUESTION_ONE_SCORE_RE = re.compile(
    r"第\s*(\d+)\s*题[^。\n]{0,24}(?:本小题)?(?:满分)?\s*(\d+(?:\.\d+)?)\s*分"
)
DATA_IMG_RE = re.compile(
    r"!\[([^\]]*)\]\((data:image/([a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/=\s]+))\)"
)
MD_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
HTML_TAG_RE = re.compile(r"<[^>]+>")
KNOWLEDGE_SPLIT_RE = re.compile(r"[；;、，,\n]+")
KNOWLEDGE_PAIR_RE = re.compile(
    r"^(?P<code>[A-Za-z0-9]+(?:[.\-][A-Za-z0-9]+)*)(?:\s+|[:：]\s*)(?P<desc>.+)$"
)
KNOWLEDGE_CODE_RE = re.compile(r"^(?P<code>[A-Za-z0-9]+(?:[.\-][A-Za-z0-9]+)*)$")


@dataclass
class ParsedOption:
    label: str
    content_md: str
    sort_order: int


@dataclass
class ParsedKnowledge:
    code: str
    description: str


@dataclass
class ParsedQuestion:
    question_no: int
    sort_order: int
    type_code: str
    stem_md: str
    stem_text: str
    score: float | None
    answer_md: str
    analysis_md: str
    solution_md: str
    options: list[ParsedOption] = field(default_factory=list)
    knowledge_points: list[ParsedKnowledge] = field(default_factory=list)


@dataclass
class ParsedPaper:
    paper_code: str
    title: str
    source_filename: str
    source_md: str
    questions: list[ParsedQuestion]


def _slug_code(name: str) -> str:
    stem = Path(name).stem.strip() or "paper"
    slug = re.sub(r"[^\w\u4e00-\u9fff\-]+", "-", stem).strip("-")
    return (slug or "paper")[:80]


def _storage_prefix(paper_code: str) -> str:
    """ASCII-only folder for Storage. Supabase rejects keys with CJK characters."""
    digest = hashlib.sha1((paper_code or "paper").encode("utf-8")).hexdigest()[:12]
    ascii_part = re.sub(r"[^A-Za-z0-9]+", "-", paper_code or "").strip("-")[:24].strip("-")
    if ascii_part:
        return f"{ascii_part}-{digest}"
    return f"paper-{digest}"


def strip_text(md: str) -> str:
    text = MD_IMG_RE.sub("[图]", md)
    text = HTML_TAG_RE.sub("", text)
    text = re.sub(r"\$\$[\s\S]+?\$\$", "[公式]", text)
    text = re.sub(r"\$[^$]+\$", "[公式]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_sections(block: str) -> dict[str, str]:
    cuts: list[tuple[str, int, int]] = []
    for marker in SECTION_MARKERS:
        start = 0
        while True:
            idx = block.find(marker, start)
            if idx < 0:
                break
            cuts.append((MARKER_TO_KEY[marker], idx, len(marker)))
            start = idx + len(marker)
    cuts.sort(key=lambda x: x[1])
    if not cuts:
        return {"stem": block.strip(), "answer": "", "analysis": "", "detail": "", "knowledge": ""}
    stem = block[: cuts[0][1]].strip()
    buckets = {"answer": "", "analysis": "", "detail": "", "knowledge": ""}
    for i, (key, pos, mlen) in enumerate(cuts):
        end = cuts[i + 1][1] if i + 1 < len(cuts) else len(block)
        content = block[pos + mlen : end].strip()
        buckets[key] = f"{buckets[key]}\n{content}".strip() if buckets[key] else content
    return {"stem": stem, **buckets}


def _question_hits(text: str) -> list[tuple[int, int, int]]:
    hits: list[tuple[int, int, int]] = []
    for m in QUESTION_RE.finditer(text):
        index = int(m.group(1) or m.group(2))
        raw = m.group(0)
        start = m.start() + (1 if raw.startswith("\n") else 0)
        hits.append((index, start, m.end()))
    if not hits:
        return []

    def take_chain(expect: int) -> list[tuple[int, int, int]]:
        chain: list[tuple[int, int, int]] = []
        want = expect
        for hit in hits:
            if hit[0] == want:
                chain.append(hit)
                want += 1
        return chain

    filtered = take_chain(1)
    seen: set[int] = set()
    for hit in hits:
        if hit[0] in seen:
            continue
        seen.add(hit[0])
        chain = take_chain(hit[0])
        if len(chain) > len(filtered):
            filtered = chain
    return filtered


def split_by_question_number(text: str) -> list[tuple[int, str]]:
    filtered = _question_hits(text)
    if not filtered:
        return []

    out: list[tuple[int, str]] = []
    for i, (index, _start, body_start) in enumerate(filtered):
        end = filtered[i + 1][1] if i + 1 < len(filtered) else len(text)
        body = text[body_start:end].strip()
        if body:
            out.append((index, body))
    return out


def parse_knowledge_points(text: str) -> list[ParsedKnowledge]:
    raw = (text or "").strip()
    if not raw:
        return []
    seen: set[str] = set()
    out: list[ParsedKnowledge] = []
    for part in KNOWLEDGE_SPLIT_RE.split(raw):
        item = part.strip().strip("。.;；")
        if not item:
            continue
        pair = KNOWLEDGE_PAIR_RE.match(item)
        code = ""
        description = ""
        if pair:
            code = pair.group("code").strip()
            description = pair.group("desc").strip()
        else:
            only = KNOWLEDGE_CODE_RE.match(item)
            if only:
                code = only.group("code").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(ParsedKnowledge(code=code, description=description))
    return out


def extract_score(text: str) -> float | None:
    if not text:
        return None
    m = SCORE_RE.search(text) or SUBQUESTION_SCORE_RE.search(text)
    if not m:
        return None
    return float(m.group(1))


def _distribute_points(total: float, n: int) -> list[float]:
    if n <= 0:
        return []
    if abs(total - round(total)) < 1e-9:
        tot_i = int(round(total))
        base, rem = divmod(tot_i, n)
        return [float(base + (1 if i >= n - rem else 0)) for i in range(n)]
    each = round(total / n, 2)
    head = [each] * (n - 1)
    last = round(total - each * (n - 1), 2)
    return head + [last]


def apply_declared_scores(text: str, questions: list[ParsedQuestion]) -> None:
    """Fill missing scores from type headers and numbered score notes in the paper."""
    if not questions:
        return
    by_no = {q.question_no: q for q in questions}
    hits = _question_hits(text)
    positions = {index: start for index, start, _end in hits}

    def assign(number: int, points: float) -> None:
        q = by_no.get(number)
        if q is None or q.score is not None:
            return
        if points <= 0:
            return
        q.score = float(points)

    for m in QUESTION_RANGE_SCORE_RE.finditer(text):
        a, b = int(m.group(1)), int(m.group(2))
        pts = float(m.group(3))
        lo, hi = (a, b) if a <= b else (b, a)
        for number in range(lo, hi + 1):
            assign(number, pts)
    for m in QUESTION_ONE_SCORE_RE.finditer(text):
        assign(int(m.group(1)), float(m.group(2)))

    headers = list(SECTION_HEADER_RE.finditer(text))
    for i, m in enumerate(headers):
        start = m.start()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        rest = m.group("rest") or ""
        nos = sorted(n for n, pos in positions.items() if start < pos < end)
        if not nos:
            continue
        count_m = SECTION_COUNT_RE.search(rest)
        if count_m:
            nos = nos[: int(count_m.group(1))]
        each_m = SECTION_EACH_RE.search(rest)
        total_m = SECTION_TOTAL_RE.search(rest)
        if each_m:
            pts = float(each_m.group(1))
            for number in nos:
                assign(number, pts)
            continue
        if not total_m:
            continue
        total = float(total_m.group(1))
        missing = [n for n in nos if by_no[n].score is None]
        if not missing:
            continue
        used = sum(by_no[n].score or 0 for n in nos if by_no[n].score is not None)
        leftover = total - used
        if leftover <= 0:
            continue
        for number, pts in zip(missing, _distribute_points(leftover, len(missing))):
            assign(number, pts)


def extract_options(stem: str) -> tuple[str, list[ParsedOption]]:
    matches = list(OPTION_RE.finditer(stem))
    if len(matches) < 2:
        return stem.strip(), []
    labels = [m.group(1).upper() for m in matches]
    expected = [chr(ord("A") + i) for i in range(len(labels))]
    if labels != expected:
        return stem.strip(), []
    head = stem[: matches[0].start()].rstrip()
    options: list[ParsedOption] = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(stem)
        content = stem[match.end() : end].strip()
        options.append(
            ParsedOption(label=match.group(1).upper(), content_md=content, sort_order=i)
        )
    return head, options


def guess_type(stem: str, answer: str, options: list[ParsedOption]) -> str:
    letters = re.sub(r"[^A-Ga-g]", "", answer)
    if options:
        unique = {c.upper() for c in letters}
        if len(unique) >= 2:
            return "multi_choice"
        return "single_choice"
    if re.search(r"_{3,}|(?:\\_){3,}|\\qquad|\\blank|填空", stem):
        return "fill_blank"
    return "solution"


def parse_markdown_paper(
    raw: str,
    *,
    filename: str = "paper.md",
    paper_code: str | None = None,
    title: str | None = None,
) -> ParsedPaper:
    text = raw.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    chunks = split_by_question_number(text)
    if not chunks:
        raise ValueError(
            "未识别到大题题号。请确认题号在段首，格式如：1. / 1． / 1、 / 第1题。"
        )
    questions: list[ParsedQuestion] = []
    for sort_order, (number, body) in enumerate(chunks):
        sections = split_sections(body)
        stem_head, options = extract_options(sections["stem"])
        score = extract_score(sections["stem"]) or extract_score(body)
        type_code = guess_type(stem_head, sections["answer"], options)
        questions.append(
            ParsedQuestion(
                question_no=number,
                sort_order=sort_order,
                type_code=type_code,
                stem_md=stem_head,
                stem_text=strip_text(stem_head)[:500],
                score=score,
                answer_md=sections["answer"],
                analysis_md=sections["analysis"],
                solution_md=sections["detail"],
                options=options,
                knowledge_points=parse_knowledge_points(sections.get("knowledge", "")),
            )
        )
    questions.sort(key=lambda q: q.sort_order)
    apply_declared_scores(text, questions)
    return ParsedPaper(
        paper_code=(paper_code or _slug_code(filename)).strip() or _slug_code(filename),
        title=(title or Path(filename).stem).strip() or Path(filename).stem,
        source_filename=Path(filename).name,
        source_md=text,
        questions=questions,
    )


def exam_bank_configured() -> bool:
    _load_env()
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))


def normalize_paper_semester(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if text not in PAPER_SEMESTERS:
        raise ValueError("学期必须是高一上学期、高一下学期、高二上学期、高二下学期、高三上学期或高三下学期。")
    return text


def normalize_paper_exam_type(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if text not in PAPER_EXAM_TYPES:
        raise ValueError("考试类型必须是月考、期中或期末。")
    return text


def normalize_paper_province(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    text = _PROVINCE_ALIASES.get(text, text)
    if text not in _PROVINCE_SET:
        for suffix in ("特别行政区", "维吾尔自治区", "壮族自治区", "回族自治区", "自治区", "省", "市"):
            if text.endswith(suffix):
                candidate = text[: -len(suffix)]
                if candidate in _PROVINCE_SET:
                    text = candidate
                    break
    if text not in _PROVINCE_SET:
        raise ValueError("省份必须是中国大陆省级行政区。")
    return text


def normalize_gaokao_paper(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    text = _GAOKAO_PAPER_ALIASES.get(text, text)
    if text not in PAPER_GAOKAO_PAPERS:
        raise ValueError("高考试卷必须是全国A卷或全国B卷。")
    return text


def paper_filter_options() -> dict[str, list[str]]:
    return {
        "provinces": list(PAPER_PROVINCES),
        "gaokao_papers": list(PAPER_GAOKAO_PAPERS),
    }


def _client():
    _load_env()
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError(
            "未配置题库。请在 .env 中设置 SUPABASE_URL 与 SUPABASE_SERVICE_ROLE_KEY。"
        )
    from supabase import create_client

    return create_client(url, key)


def public_asset_url(storage_key: str) -> str:
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    return f"{base}/storage/v1/object/public/{BUCKET}/{quote(storage_key)}"


def _ensure_bucket(client) -> None:
    try:
        buckets = client.storage.list_buckets()
        names = {getattr(b, "name", None) or b.get("name") for b in buckets}
        if BUCKET in names:
            return
    except Exception:
        pass
    try:
        client.storage.create_bucket(BUCKET, options={"public": True})
    except Exception as exc:
        msg = str(exc).lower()
        if "already exists" not in msg and "duplicate" not in msg:
            raise


def _guess_ext(mime: str) -> str:
    mapping = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/gif": "gif",
        "image/webp": "webp",
        "image/svg+xml": "svg",
        "image/bmp": "bmp",
    }
    return mapping.get(mime.lower(), "bin")


def _upload_bytes(client, paper_code: str, data: bytes, mime: str) -> str:
    digest = hashlib.sha1(data).hexdigest()
    key = f"{_storage_prefix(paper_code)}/{digest[:16]}.{_guess_ext(mime)}"
    try:
        client.storage.from_(BUCKET).upload(
            key,
            data,
            {"content-type": mime, "upsert": "true"},
        )
    except Exception as exc:
        if "already exists" not in str(exc).lower():
            raise
    return key


def rewrite_images(
    md: str,
    client,
    paper_code: str,
    asset_dir: Path | None,
) -> tuple[str, list[dict[str, str]]]:
    import base64

    uploaded: list[dict[str, str]] = []

    def replace_data(match: re.Match[str]) -> str:
        alt, _raw, subtype, b64 = match.groups()
        mime = f"image/{subtype}"
        blob = base64.b64decode(re.sub(r"\s+", "", b64))
        key = _upload_bytes(client, paper_code, blob, mime)
        uploaded.append({"storage_key": key, "mime_type": mime, "sha1": hashlib.sha1(blob).hexdigest(), "alt": alt})
        return f"![{alt}]({public_asset_url(key)})"

    md = DATA_IMG_RE.sub(replace_data, md)

    def replace_file(match: re.Match[str]) -> str:
        alt, src = match.groups()
        src = src.strip().strip("<>").split()[0]
        if re.match(r"^(https?:|data:|blob:)", src, re.I):
            return match.group(0)
        if not asset_dir:
            return match.group(0)
        rel = src.replace("\\", "/").lstrip("./")
        path = (asset_dir / rel).resolve()
        if not path.is_file():
            path = asset_dir / Path(rel).name
        if not path.is_file():
            return match.group(0)
        data = path.read_bytes()
        suffix = path.suffix.lower().lstrip(".") or "png"
        mime = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "webp": "image/webp",
            "svg": "image/svg+xml",
            "bmp": "image/bmp",
        }.get(suffix, "application/octet-stream")
        key = _upload_bytes(client, paper_code, data, mime)
        uploaded.append(
            {
                "storage_key": key,
                "mime_type": mime,
                "sha1": hashlib.sha1(data).hexdigest(),
                "alt": alt,
            }
        )
        return f"![{alt}]({public_asset_url(key)})"

    md = MD_IMG_RE.sub(replace_file, md)
    return md, uploaded


def upsert_knowledge_points(client, items: list[ParsedKnowledge]) -> None:
    unique: dict[str, ParsedKnowledge] = {}
    for item in items:
        code = (item.code or "").strip()
        if not code:
            continue
        prev = unique.get(code)
        if prev is None or (item.description and not prev.description):
            unique[code] = ParsedKnowledge(code=code, description=(item.description or "").strip())
    if not unique:
        return
    codes = list(unique)
    existing = (
        client.table("knowledge_points")
        .select("code,description")
        .in_("code", codes)
        .execute()
    )
    have = {row["code"]: (row.get("description") or "") for row in (existing.data or [])}
    to_insert = []
    now = datetime.now(timezone.utc).isoformat()
    for code, item in unique.items():
        description = item.description or code
        if code not in have:
            to_insert.append({"code": code, "description": description})
        elif item.description and item.description != have[code]:
            client.table("knowledge_points").update(
                {"description": item.description, "updated_at": now}
            ).eq("code", code).execute()
    if to_insert:
        client.table("knowledge_points").insert(to_insert).execute()


def import_parsed_paper(
    paper: ParsedPaper,
    asset_dir: Path | None = None,
    *,
    province: str | None = None,
    gaokao_paper: str | None = None,
) -> dict[str, Any]:
    client = _client()
    _ensure_bucket(client)

    all_assets: list[dict[str, str]] = []

    def rewrite(text: str) -> str:
        out, assets = rewrite_images(text, client, paper.paper_code, asset_dir)
        all_assets.extend(assets)
        return out

    paper.source_md = rewrite(paper.source_md)
    for q in paper.questions:
        q.stem_md = rewrite(q.stem_md)
        q.answer_md = rewrite(q.answer_md)
        q.analysis_md = rewrite(q.analysis_md)
        q.solution_md = rewrite(q.solution_md)
        for opt in q.options:
            opt.content_md = rewrite(opt.content_md)

    existing = (
        client.table("papers")
        .select("id")
        .eq("paper_code", paper.paper_code)
        .limit(1)
        .execute()
    )
    payload = {
        "paper_code": paper.paper_code,
        "title": paper.title,
        "source_filename": paper.source_filename,
        "source_md": paper.source_md,
        "extra": {},
    }
    if province:
        payload["province"] = normalize_paper_province(province)
    if gaokao_paper:
        payload["gaokao_paper"] = normalize_gaokao_paper(gaokao_paper)
    if existing.data:
        paper_id = existing.data[0]["id"]
        client.table("questions").delete().eq("paper_id", paper_id).execute()
        client.table("assets").delete().eq("paper_id", paper_id).execute()
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        client.table("papers").update(payload).eq("id", paper_id).execute()
    else:
        inserted = client.table("papers").insert(payload).execute()
        paper_id = inserted.data[0]["id"]

    upsert_knowledge_points(
        client,
        [kp for q in paper.questions for kp in q.knowledge_points],
    )

    question_rows = []
    for q in paper.questions:
        knowledge_codes = [kp.code for kp in q.knowledge_points]
        q_ins = (
            client.table("questions")
            .insert(
                {
                    "paper_id": paper_id,
                    "question_no": q.question_no,
                    "sort_order": q.sort_order,
                    "type_code": q.type_code,
                    "stem_md": q.stem_md,
                    "stem_text": q.stem_text,
                    "score": q.score,
                    "answer_md": q.answer_md,
                    "analysis_md": q.analysis_md,
                    "solution_md": q.solution_md,
                    "knowledge_codes": knowledge_codes,
                    "extra": {},
                }
            )
            .execute()
        )
        qid = q_ins.data[0]["id"]
        question_rows.append(
            {
                "id": qid,
                "question_no": q.question_no,
                "type_code": q.type_code,
                "score": q.score,
                "option_count": len(q.options),
                "knowledge_codes": knowledge_codes,
            }
        )
        if knowledge_codes:
            client.table("question_knowledge_points").insert(
                [
                    {
                        "question_id": qid,
                        "knowledge_code": kp.code,
                        "sort_order": i,
                    }
                    for i, kp in enumerate(q.knowledge_points)
                ]
            ).execute()
        if q.options:
            client.table("question_options").insert(
                [
                    {
                        "question_id": qid,
                        "label": opt.label,
                        "content_md": opt.content_md,
                        "sort_order": opt.sort_order,
                        "extra": {},
                    }
                    for opt in q.options
                ]
            ).execute()

    seen_keys: set[str] = set()
    asset_rows = []
    for item in all_assets:
        key = item["storage_key"]
        if key in seen_keys:
            continue
        seen_keys.add(key)
        asset_rows.append(
            {
                "paper_id": paper_id,
                "storage_key": key,
                "mime_type": item.get("mime_type"),
                "sha1": item.get("sha1"),
                "alt": item.get("alt") or None,
            }
        )
    if asset_rows:
        client.table("assets").insert(asset_rows).execute()

    return {
        "paper_id": paper_id,
        "paper_code": paper.paper_code,
        "title": paper.title,
        "question_count": len(question_rows),
        "asset_count": len(asset_rows),
        "replaced": bool(existing.data),
        "questions": question_rows,
    }


def import_markdown_file(
    path: Path,
    *,
    paper_code: str | None = None,
    title: str | None = None,
    province: str | None = None,
    gaokao_paper: str | None = None,
) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8-sig")
    paper = parse_markdown_paper(
        raw,
        filename=path.name,
        paper_code=paper_code,
        title=title,
    )
    asset_dir = path.parent
    return import_parsed_paper(
        paper,
        asset_dir=asset_dir,
        province=province,
        gaokao_paper=gaokao_paper,
    )


def list_papers(
    limit: int = 50,
    *,
    province: str | None = None,
    gaokao_paper: str | None = None,
) -> list[dict[str, Any]]:
    client = _client()
    query = (
        client.table("papers")
        .select(_PAPER_LIST_SELECT)
        .order("updated_at", desc=True)
        .limit(limit)
    )
    province_n = normalize_paper_province(province)
    gaokao_n = normalize_gaokao_paper(gaokao_paper)
    if province_n:
        query = query.eq("province", province_n)
    if gaokao_n:
        query = query.eq("gaokao_paper", gaokao_n)
    res = query.execute()
    rows = list(res.data or [])
    for row in rows:
        count = (
            client.table("questions")
            .select("id", count="exact")
            .eq("paper_id", row["id"])
            .execute()
        )
        row["question_count"] = count.count if count.count is not None else len(count.data or [])
    return rows


def backfill_question_scores() -> dict[str, int]:
    """Parse stored paper markdown and write declared scores onto questions."""
    client = _client()
    papers = (
        client.table("papers")
        .select("id,paper_code,title,source_filename,source_md")
        .execute()
    )
    updated = 0
    parsed_papers = 0
    skipped = 0
    for paper in papers.data or []:
        md = paper.get("source_md") or ""
        if not md.strip():
            skipped += 1
            continue
        try:
            parsed = parse_markdown_paper(
                md,
                filename=paper.get("source_filename") or "paper.md",
                paper_code=paper.get("paper_code"),
                title=paper.get("title"),
            )
        except ValueError:
            skipped += 1
            continue
        parsed_papers += 1
        for q in parsed.questions:
            if q.score is None:
                continue
            client.table("questions").update({"score": q.score}).eq("paper_id", paper["id"]).eq(
                "question_no", q.question_no
            ).execute()
            updated += 1
    return {"papers": parsed_papers, "updated": updated, "skipped": skipped}


def update_paper_meta(
    paper_id: str,
    *,
    semester: str | None = None,
    exam_type: str | None = None,
    province: str | None = None,
    gaokao_paper: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if semester is not None:
        payload["semester"] = normalize_paper_semester(semester)
    if exam_type is not None:
        payload["exam_type"] = normalize_paper_exam_type(exam_type)
    if province is not None:
        payload["province"] = normalize_paper_province(province)
    if gaokao_paper is not None:
        payload["gaokao_paper"] = normalize_gaokao_paper(gaokao_paper)
    if len(payload) == 1:
        raise ValueError("请选择要保存的试卷属性。")
    client = _client()
    found = (
        client.table("papers")
        .select("id")
        .eq("id", paper_id)
        .limit(1)
        .execute()
    )
    if not found.data:
        raise ValueError("试卷不存在")
    client.table("papers").update(payload).eq("id", paper_id).execute()
    row = (
        client.table("papers")
        .select("id,paper_code,title,semester,exam_type,province,gaokao_paper,updated_at")
        .eq("id", paper_id)
        .single()
        .execute()
    )
    return row.data or {}


def _remove_storage_keys(client, keys: list[str]) -> None:
    if not keys:
        return
    try:
        storage = client.storage.from_(BUCKET)
        for chunk in _chunked(keys, 50):
            storage.remove(chunk)
    except Exception:
        pass


def delete_paper(paper_id: str) -> dict[str, Any]:
    """Delete a paper and its questions, options, assets, and answer sheets."""
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", paper_id or ""):
        raise ValueError("无效的试卷 id")
    client = _client()
    found = (
        client.table("papers")
        .select("id,paper_code,title")
        .eq("id", paper_id)
        .limit(1)
        .execute()
    )
    if not found.data:
        raise ValueError("试卷不存在")
    paper = found.data[0]
    qres = (
        client.table("questions")
        .select("id")
        .eq("paper_id", paper_id)
        .execute()
    )
    question_ids = [row["id"] for row in (qres.data or []) if row.get("id")]
    ares = (
        client.table("assets")
        .select("storage_key")
        .eq("paper_id", paper_id)
        .execute()
    )
    storage_keys = [
        row["storage_key"] for row in (ares.data or []) if row.get("storage_key")
    ]

    for chunk in _chunked(question_ids):
        client.table("answer_sheet_items").delete().in_("question_id", chunk).execute()
        client.table("question_knowledge_points").delete().in_("question_id", chunk).execute()
        client.table("question_options").delete().in_("question_id", chunk).execute()
    client.table("answer_sheets").delete().eq("paper_id", paper_id).execute()
    client.table("questions").delete().eq("paper_id", paper_id).execute()
    _remove_storage_keys(client, storage_keys)
    client.table("assets").delete().eq("paper_id", paper_id).execute()
    client.table("papers").delete().eq("id", paper_id).execute()

    return {
        "paper_id": paper_id,
        "paper_code": paper.get("paper_code"),
        "title": paper.get("title"),
        "question_count": len(question_ids),
        "asset_count": len(storage_keys),
    }


def get_paper_questions(paper_id: str) -> dict[str, Any]:
    client = _client()
    paper = (
        client.table("papers")
        .select(
            "id,paper_code,title,source_filename,source_md,semester,exam_type,"
            "province,gaokao_paper,created_at,updated_at"
        )
        .eq("id", paper_id)
        .single()
        .execute()
    )
    questions = (
        client.table("questions")
        .select(
            "id,question_no,sort_order,type_code,stem_md,stem_text,score,"
            "answer_md,analysis_md,solution_md,knowledge_codes"
        )
        .eq("paper_id", paper_id)
        .order("sort_order")
        .execute()
    )
    qrows = list(questions.data or [])
    ids = [q["id"] for q in qrows]
    options_by_q: dict[str, list] = {qid: [] for qid in ids}
    if ids:
        opts = (
            client.table("question_options")
            .select("question_id,label,content_md,sort_order")
            .in_("question_id", ids)
            .order("sort_order")
            .execute()
        )
        for opt in opts.data or []:
            options_by_q.setdefault(opt["question_id"], []).append(opt)
    links_by_q: dict[str, list] = {qid: [] for qid in ids}
    if ids:
        links = (
            client.table("question_knowledge_points")
            .select("question_id,knowledge_code,sort_order")
            .in_("question_id", ids)
            .order("sort_order")
            .execute()
        )
        codes = sorted(
            {row["knowledge_code"] for row in (links.data or []) if row.get("knowledge_code")}
        )
        meta_by_code: dict[str, dict[str, str]] = {}
        if codes:
            kps = (
                client.table("knowledge_points")
                .select("code,description,semester,major_category,minor_category")
                .in_("code", codes)
                .execute()
            )
            meta_by_code = {
                row["code"]: {
                    "description": row.get("description") or "",
                    "semester": row.get("semester") or "",
                    "major_category": row.get("major_category") or "",
                    "minor_category": row.get("minor_category") or "",
                }
                for row in (kps.data or [])
            }
        for row in links.data or []:
            meta = meta_by_code.get(row["knowledge_code"], {})
            links_by_q.setdefault(row["question_id"], []).append(
                {
                    "code": row["knowledge_code"],
                    "description": meta.get("description", ""),
                    "semester": meta.get("semester", ""),
                    "major_category": meta.get("major_category", ""),
                    "minor_category": meta.get("minor_category", ""),
                    "sort_order": row.get("sort_order", 0),
                }
            )
    for q in qrows:
        q["options"] = options_by_q.get(q["id"], [])
        q["knowledge_points"] = links_by_q.get(q["id"], [])
        q["knowledge_codes"] = q.get("knowledge_codes") or [
            item["code"] for item in q["knowledge_points"]
        ]
    return {"paper": paper.data, "questions": qrows}


def questions_to_markdown(questions: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for q in questions:
        stem = (q.get("stem_md") or "").strip()
        opt_lines = []
        for opt in q.get("options") or []:
            label = (opt.get("label") or "").strip()
            content = (opt.get("content_md") or "").strip()
            if label:
                opt_lines.append(f"{label}. {content}".rstrip())
        body = stem
        if opt_lines:
            opts = "\n".join(opt_lines)
            body = f"{stem}\n{opts}".strip() if stem else opts
        if (q.get("answer_md") or "").strip():
            body += f"\n\n【答案】{(q.get('answer_md') or '').strip()}"
        if (q.get("analysis_md") or "").strip():
            body += f"\n\n【分析】{(q.get('analysis_md') or '').strip()}"
        if (q.get("solution_md") or "").strip():
            body += f"\n\n【详解】{(q.get('solution_md') or '').strip()}"
        kps = q.get("knowledge_points") or []
        if kps:
            bits = []
            for item in kps:
                code = (item.get("code") or "").strip()
                desc = (item.get("description") or "").strip()
                if code and desc:
                    bits.append(f"{code} {desc}")
                elif code:
                    bits.append(code)
            if bits:
                body += f"\n\n【知识点】{'；'.join(bits)}"
        no = q.get("question_no") or q.get("sort_order") or len(parts) + 1
        parts.append(f"{no}. {body}".strip())
    return "\n\n".join(parts).strip() + ("\n" if parts else "")


def normalize_knowledge_codes(codes: list[str] | None, *, limit: int = 40) -> list[str]:
    """Deduplicate and validate knowledge-point codes for queries."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in codes or []:
        code = str(raw or "").strip()
        if not code or code in seen or not KNOWLEDGE_CODE_RE.match(code):
            continue
        seen.add(code)
        out.append(code)
        if len(out) >= limit:
            break
    return out


def _chunked(items: list[str], size: int = 80) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _attach_options_and_knowledge(client, qrows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = [q["id"] for q in qrows]
    options_by_q: dict[str, list] = {qid: [] for qid in ids}
    links_by_q: dict[str, list] = {qid: [] for qid in ids}
    if not ids:
        return qrows
    for chunk in _chunked(ids):
        opts = (
            client.table("question_options")
            .select("question_id,label,content_md,sort_order")
            .in_("question_id", chunk)
            .order("sort_order")
            .execute()
        )
        for opt in opts.data or []:
            options_by_q.setdefault(opt["question_id"], []).append(opt)
        links = (
            client.table("question_knowledge_points")
            .select("question_id,knowledge_code,sort_order")
            .in_("question_id", chunk)
            .order("sort_order")
            .execute()
        )
        for row in links.data or []:
            links_by_q.setdefault(row["question_id"], []).append(row)
    all_codes = sorted(
        {
            row["knowledge_code"]
            for rows in links_by_q.values()
            for row in rows
            if row.get("knowledge_code")
        }
    )
    meta_by_code: dict[str, dict[str, str]] = {}
    if all_codes:
        kps = (
            client.table("knowledge_points")
            .select("code,description,semester,major_category,minor_category")
            .in_("code", all_codes)
            .execute()
        )
        meta_by_code = {
            row["code"]: {
                "description": row.get("description") or "",
                "semester": row.get("semester") or "",
                "major_category": row.get("major_category") or "",
                "minor_category": row.get("minor_category") or "",
            }
            for row in (kps.data or [])
        }
    for q in qrows:
        qid = q["id"]
        q["options"] = options_by_q.get(qid, [])
        points = []
        for row in links_by_q.get(qid, []):
            meta = meta_by_code.get(row["knowledge_code"], {})
            points.append(
                {
                    "code": row["knowledge_code"],
                    "description": meta.get("description", ""),
                    "semester": meta.get("semester", ""),
                    "major_category": meta.get("major_category", ""),
                    "minor_category": meta.get("minor_category", ""),
                    "sort_order": row.get("sort_order", 0),
                }
            )
        q["knowledge_points"] = points
        q["knowledge_codes"] = q.get("knowledge_codes") or [item["code"] for item in points]
    return qrows


def list_questions_by_knowledge(
    codes: list[str],
    *,
    match: str = "any",
    type_code: str = "",
    limit: int = 300,
) -> dict[str, Any]:
    """Cross-paper questions tagged with the given knowledge-point codes."""
    wanted = normalize_knowledge_codes(codes)
    if not wanted:
        return {"codes": [], "match": "any", "questions": []}
    mode = "all" if str(match).strip().lower() == "all" else "any"
    client = _client()
    qids: list[str] = []
    hits_by_q: dict[str, set[str]] = {}
    for chunk in _chunked(wanted):
        links = (
            client.table("question_knowledge_points")
            .select("question_id,knowledge_code")
            .in_("knowledge_code", chunk)
            .execute()
        )
        for row in links.data or []:
            qid = row.get("question_id")
            code = row.get("knowledge_code")
            if not qid or not code:
                continue
            hits_by_q.setdefault(qid, set()).add(code)
    wanted_set = set(wanted)
    for qid, hit in hits_by_q.items():
        if mode == "all":
            if wanted_set <= hit:
                qids.append(qid)
        elif hit:
            qids.append(qid)
    if not qids:
        return {"codes": wanted, "match": mode, "questions": []}

    qrows: list[dict[str, Any]] = []
    for chunk in _chunked(qids):
        query = (
            client.table("questions")
            .select(
                "id,paper_id,question_no,sort_order,type_code,stem_md,stem_text,score,"
                "answer_md,analysis_md,solution_md,knowledge_codes"
            )
            .in_("id", chunk)
        )
        if type_code:
            query = query.eq("type_code", type_code)
        res = query.execute()
        qrows.extend(res.data or [])
    paper_ids = sorted({q["paper_id"] for q in qrows if q.get("paper_id")})
    papers: dict[str, dict[str, Any]] = {}
    for chunk in _chunked(paper_ids):
        pres = (
            client.table("papers")
            .select("id,paper_code,title,semester,exam_type,province,gaokao_paper")
            .in_("id", chunk)
            .execute()
        )
        for row in pres.data or []:
            papers[row["id"]] = row
    qrows = _attach_options_and_knowledge(client, qrows)
    out: list[dict[str, Any]] = []
    for q in qrows:
        paper = papers.get(q.get("paper_id") or "", {})
        out.append(
            {
                **q,
                "paper_title": paper.get("title") or "",
                "paper_code": paper.get("paper_code") or "",
                "paper_semester": paper.get("semester") or "",
                "paper_exam_type": paper.get("exam_type") or "",
                "paper_province": paper.get("province") or "",
                "paper_gaokao_paper": paper.get("gaokao_paper") or "",
                "matched_codes": sorted(hits_by_q.get(q["id"], set()) & wanted_set),
            }
        )
    out.sort(
        key=lambda q: (
            q.get("matched_codes") or [],
            q.get("paper_code") or "",
            int(q.get("question_no") or 0),
        )
    )
    return {"codes": wanted, "match": mode, "questions": out[: max(1, min(limit, 400))]}


def get_questions_by_ids(question_ids: list[str], *, limit: int = 300) -> list[dict[str, Any]]:
    """Load full question rows in the given id order (for practice preview/print)."""
    ids: list[str] = []
    seen: set[str] = set()
    uuid_re = re.compile(r"^[0-9a-fA-F-]{36}$")
    for raw in question_ids or []:
        qid = str(raw or "").strip()
        if not qid or qid in seen or not uuid_re.match(qid):
            continue
        seen.add(qid)
        ids.append(qid)
        if len(ids) >= limit:
            break
    if not ids:
        return []
    client = _client()
    by_id: dict[str, dict[str, Any]] = {}
    for chunk in _chunked(ids):
        res = (
            client.table("questions")
            .select(
                "id,paper_id,question_no,sort_order,type_code,stem_md,stem_text,score,"
                "answer_md,analysis_md,solution_md,knowledge_codes"
            )
            .in_("id", chunk)
            .execute()
        )
        for row in res.data or []:
            by_id[row["id"]] = row
    ordered = [by_id[qid] for qid in ids if qid in by_id]
    paper_ids = sorted({q["paper_id"] for q in ordered if q.get("paper_id")})
    papers: dict[str, dict[str, Any]] = {}
    for chunk in _chunked(paper_ids):
        pres = (
            client.table("papers")
            .select("id,paper_code,title,semester,exam_type,province,gaokao_paper")
            .in_("id", chunk)
            .execute()
        )
        for row in pres.data or []:
            papers[row["id"]] = row
    ordered = _attach_options_and_knowledge(client, ordered)
    for q in ordered:
        paper = papers.get(q.get("paper_id") or "", {})
        q["paper_title"] = paper.get("title") or ""
        q["paper_code"] = paper.get("paper_code") or ""
        q["paper_semester"] = paper.get("semester") or ""
        q["paper_exam_type"] = paper.get("exam_type") or ""
        q["paper_province"] = paper.get("province") or ""
        q["paper_gaokao_paper"] = paper.get("gaokao_paper") or ""
        q["source_question_no"] = q.get("question_no")
    return ordered


def list_knowledge_points(limit: int = 500) -> list[dict[str, Any]]:
    client = _client()
    res = (
        client.table("knowledge_points")
        .select("code,description,semester,major_category,minor_category,sort_order,updated_at")
        .order("sort_order")
        .order("code")
        .limit(limit)
        .execute()
    )
    return list(res.data or [])


def set_question_knowledge_points(
    question_id: str,
    items: list[ParsedKnowledge] | list[dict[str, Any]] | list[str],
) -> list[dict[str, str]]:
    codes: list[str] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, str):
            code = item.strip()
        elif isinstance(item, ParsedKnowledge):
            code = (item.code or "").strip()
        else:
            code = str(item.get("code") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        codes.append(code)

    client = _client()
    found = (
        client.table("questions")
        .select("id")
        .eq("id", question_id)
        .limit(1)
        .execute()
    )
    if not found.data:
        raise ValueError("题目不存在")

    meta_by_code: dict[str, dict[str, str]] = {}
    if codes:
        rows = (
            client.table("knowledge_points")
            .select("code,description,semester,major_category,minor_category")
            .in_("code", codes)
            .execute()
        )
        meta_by_code = {row["code"]: row for row in (rows.data or [])}
    linked = [code for code in codes if code in meta_by_code]

    client.table("question_knowledge_points").delete().eq("question_id", question_id).execute()
    if linked:
        client.table("question_knowledge_points").insert(
            [
                {
                    "question_id": question_id,
                    "knowledge_code": code,
                    "sort_order": i,
                }
                for i, code in enumerate(linked)
            ]
        ).execute()
    client.table("questions").update({"knowledge_codes": linked}).eq("id", question_id).execute()

    return [
        {
            "code": code,
            "description": meta_by_code[code].get("description") or "",
            "semester": meta_by_code[code].get("semester") or "",
            "major_category": meta_by_code[code].get("major_category") or "",
            "minor_category": meta_by_code[code].get("minor_category") or "",
        }
        for code in linked
    ]


def _normalize_knowledge_codes(codes: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in codes or []:
        code = str(raw or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def list_animations_for_codes(codes: list[str] | None) -> list[dict[str, Any]]:
    """Unique GeoGebra animations linked to any of the given knowledge codes."""
    from word_math_md.geogebra_pep import serialize_animation

    wanted = _normalize_knowledge_codes(codes)
    if not wanted:
        return []
    client = _client()
    res = (
        client.table("knowledge_geogebra_animations")
        .select(
            "knowledge_code,book_id,page_id,material_id,title,chapter_title,"
            "chapter_id,thumb_url,sort_order"
        )
        .in_("knowledge_code", wanted)
        .order("sort_order")
        .execute()
    )
    grouped: dict[str, dict[str, Any]] = {}
    code_map: dict[str, list[str]] = {}
    for row in res.data or []:
        page_id = row.get("page_id") or ""
        if not page_id:
            continue
        if page_id not in grouped:
            grouped[page_id] = row
            code_map[page_id] = []
        code = row.get("knowledge_code") or ""
        if code and code not in code_map[page_id]:
            code_map[page_id].append(code)
    return [
        serialize_animation(grouped[page_id], code_map[page_id])
        for page_id in grouped
    ]


def list_animations_for_question(question_id: str) -> list[dict[str, Any]]:
    qid = (question_id or "").strip()
    if not qid:
        raise ValueError("无效的题目 id")
    client = _client()
    found = (
        client.table("questions")
        .select("id,knowledge_codes")
        .eq("id", qid)
        .limit(1)
        .execute()
    )
    if not found.data:
        raise ValueError("题目不存在")
    codes = list(found.data[0].get("knowledge_codes") or [])
    if not codes:
        links = (
            client.table("question_knowledge_points")
            .select("knowledge_code")
            .eq("question_id", qid)
            .execute()
        )
        codes = [row.get("knowledge_code") or "" for row in (links.data or [])]
    return list_animations_for_codes(codes)


def sync_geogebra_pep_animations(*, live: bool = True) -> dict[str, Any]:
    from word_math_md.geogebra_pep import BOOK_ID, mapped_rows

    rows = mapped_rows(live=live)
    client = _client()
    existing = (
        client.table("knowledge_points")
        .select("code")
        .in_("code", sorted({row["knowledge_code"] for row in rows}))
        .execute()
    )
    have = {row["code"] for row in (existing.data or [])}
    kept = [row for row in rows if row["knowledge_code"] in have]
    skipped = len(rows) - len(kept)
    client.table("knowledge_geogebra_animations").delete().eq("book_id", BOOK_ID).execute()
    for start in range(0, len(kept), 40):
        client.table("knowledge_geogebra_animations").insert(kept[start : start + 40]).execute()
    pages = {row["page_id"] for row in kept}
    codes = {row["knowledge_code"] for row in kept}
    return {
        "book_id": BOOK_ID,
        "pages": len(pages),
        "links": len(kept),
        "knowledge_codes": len(codes),
        "skipped_unknown_codes": skipped,
        "live": live,
    }


def save_answer_sheet(
    paper_id: str,
    report: dict[str, Any],
    *,
    student_name: str = "",
    ocr_engine: str = "",
    ocr_text: str = "",
) -> dict[str, Any]:
    """Persist an auto-graded photographed answer sheet."""
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", paper_id or ""):
        raise ValueError("无效的试卷 id")
    client = _client()
    found = (
        client.table("papers")
        .select("id")
        .eq("id", paper_id)
        .limit(1)
        .execute()
    )
    if not found.data:
        raise ValueError("试卷不存在")
    name = re.sub(r"\s+", " ", (student_name or "").strip())[:80]
    sheet_row = {
        "paper_id": paper_id,
        "student_name": name,
        "ocr_engine": (ocr_engine or "")[:40],
        "ocr_text": (ocr_text or "")[:20000],
        "total_score": report.get("total_score") or 0,
        "max_score": report.get("max_score") or 0,
        "correct_count": int(report.get("correct_count") or 0),
        "question_count": int(report.get("question_count") or 0),
        "extra": {
            "needs_review_count": int(report.get("needs_review_count") or 0),
            "missing_count": int(report.get("missing_count") or 0),
            "recognized_count": int(report.get("recognized_count") or 0),
        },
    }
    inserted = client.table("answer_sheets").insert(sheet_row).execute()
    sheet = (inserted.data or [{}])[0]
    sheet_id = sheet.get("id")
    item_rows = []
    for item in report.get("items") or []:
        qid = item.get("question_id")
        if qid and not re.fullmatch(r"[0-9a-fA-F-]{36}", str(qid)):
            qid = None
        item_rows.append(
            {
                "sheet_id": sheet_id,
                "question_id": qid,
                "question_no": int(item.get("question_no") or 0),
                "type_code": str(item.get("type_code") or "")[:40],
                "student_answer": str(item.get("student_answer") or "")[:500],
                "expected_answer": str(item.get("expected_answer") or "")[:500],
                "is_correct": bool(item.get("is_correct")),
                "status": str(item.get("status") or "graded")[:20],
                "score": item.get("score") or 0,
                "max_score": item.get("max_score") or 0,
            }
        )
    if item_rows:
        for start in range(0, len(item_rows), 80):
            client.table("answer_sheet_items").insert(item_rows[start : start + 80]).execute()
    return {
        "id": sheet_id,
        "paper_id": paper_id,
        "student_name": name,
        "ocr_engine": ocr_engine,
        "created_at": sheet.get("created_at"),
        **report,
    }


def list_answer_sheets(paper_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", paper_id or ""):
        raise ValueError("无效的试卷 id")
    client = _client()
    res = (
        client.table("answer_sheets")
        .select(
            "id,paper_id,student_name,ocr_engine,total_score,max_score,"
            "correct_count,question_count,extra,created_at"
        )
        .eq("paper_id", paper_id)
        .order("created_at", desc=True)
        .limit(max(1, min(limit, 50)))
        .execute()
    )
    return list(res.data or [])


def get_answer_sheet(sheet_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", sheet_id or ""):
        raise ValueError("无效的答卷 id")
    client = _client()
    sheet = (
        client.table("answer_sheets")
        .select(
            "id,paper_id,student_name,ocr_engine,ocr_text,total_score,max_score,"
            "correct_count,question_count,extra,created_at"
        )
        .eq("id", sheet_id)
        .single()
        .execute()
    )
    if not sheet.data:
        raise ValueError("答卷不存在")
    items = (
        client.table("answer_sheet_items")
        .select(
            "id,question_id,question_no,type_code,student_answer,expected_answer,"
            "is_correct,status,score,max_score"
        )
        .eq("sheet_id", sheet_id)
        .order("question_no")
        .execute()
    )
    data = dict(sheet.data)
    data["items"] = list(items.data or [])
    return data
