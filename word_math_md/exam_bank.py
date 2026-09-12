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


def split_by_question_number(text: str) -> list[tuple[int, str]]:
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
    if not filtered:
        best: list[tuple[int, int, int]] = []
        seen: set[int] = set()
        for hit in hits:
            if hit[0] in seen:
                continue
            seen.add(hit[0])
            chain = take_chain(hit[0])
            if len(chain) > len(best):
                best = chain
        filtered = best
    if not filtered:
        return []

    out: list[tuple[int, str]] = []
    for i, (index, start, body_start) in enumerate(filtered):
        end = filtered[i + 1][1] if i + 1 < len(filtered) else len(text)
        body = text[body_start:end].strip()
        if i == 0 and start > 0:
            preamble = text[:start].strip()
            if len(preamble) >= 40 and not re.match(r"^(学科网|机密|注意事项)", preamble):
                body = f"{preamble}\n\n{body}".strip()
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
    m = SCORE_RE.search(text)
    if not m:
        return None
    return float(m.group(1))


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


def import_parsed_paper(paper: ParsedPaper, asset_dir: Path | None = None) -> dict[str, Any]:
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
) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8-sig")
    paper = parse_markdown_paper(
        raw,
        filename=path.name,
        paper_code=paper_code,
        title=title,
    )
    asset_dir = path.parent
    return import_parsed_paper(paper, asset_dir=asset_dir)


def list_papers(limit: int = 50) -> list[dict[str, Any]]:
    client = _client()
    res = (
        client.table("papers")
        .select("id,paper_code,title,source_filename,created_at,updated_at")
        .order("updated_at", desc=True)
        .limit(limit)
        .execute()
    )
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


def get_paper_questions(paper_id: str) -> dict[str, Any]:
    client = _client()
    paper = (
        client.table("papers")
        .select("id,paper_code,title,source_filename,source_md,created_at,updated_at")
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
