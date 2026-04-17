"""Academic desktop-image analysis helpers."""

from __future__ import annotations

import ast
import json
import re
from dataclasses import asdict, dataclass

from analysis.llamacpp_client import LlamaCppServerClient
from video_core.model import generate


@dataclass
class DesktopAnalysis:
    page_type: str
    title: str
    line1: str
    line2: str
    formula_text: str
    summary: str
    formula_spotlight: str
    key_points: list[str]
    next_action: str


class DesktopContext:
    """Keep a short rolling memory of recent desktop analyses."""

    def __init__(self, max_entries: int = 5):
        self.max_entries = max_entries
        self._entries: list[str] = []

    def add(self, summary: str) -> None:
        if self.max_entries <= 0:
            return
        text = summary.strip()
        if text:
            self._entries.append(text)
            self._entries = self._entries[-self.max_entries :]

    def to_prompt_text(self) -> str:
        if self.max_entries <= 0 or not self._entries:
            return "No prior context."
        lines = [f"- {item}" for item in self._entries]
        return "Recent study context:\n" + "\n".join(lines)


def analyze_desktop_image(
    model,
    processor,
    image_path: str,
    context: DesktopContext,
    language: str = "Chinese",
    max_tokens: int = 384,
) -> DesktopAnalysis:
    prompt = _build_prompt(context.to_prompt_text(), language)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "url": image_path},
                {"type": "text", "text": prompt},
            ],
        }
    ]
    raw = generate(model, processor, messages, max_tokens=max_tokens)
    return _analysis_from_raw_text(raw, language=language)


def analyze_desktop_image_via_llamacpp(
    client: LlamaCppServerClient,
    image_path: str,
    context: DesktopContext,
    language: str = "Chinese",
    max_tokens: int = 384,
) -> DesktopAnalysis:
    prompt = _build_prompt(context.to_prompt_text(), language)
    message = client.build_multimodal_message(prompt, image_path)
    raw = client.generate([message], max_tokens=max_tokens)
    return _analysis_from_raw_text(raw, language=language)


def format_analysis_text(result: DesktopAnalysis, language: str = "Chinese") -> str:
    formula_text = _clean_display_text(result.formula_text)
    formula_spotlight = _clean_display_text(result.formula_spotlight)
    summary = _clean_display_text(result.summary)
    key_points = [_clean_display_text(point) for point in result.key_points]
    next_action = _clean_display_text(result.next_action)

    if _is_english(language):
        labels = {
            "page_type": "Page type",
            "title": "Title",
            "formula": "Recognized formula / matrix",
            "spotlight": "Formula / diagram explanation",
            "summary": "Summary",
            "key_points": "Key points",
            "next_action": "Next step",
            "untitled": "Not recognized",
            "no_summary": "No summary available",
            "no_points": "No key points available",
            "fallback_next": "Keep reading the current page, or ask about a term, chart, or formula.",
        }
    else:
        labels = {
            "page_type": "页面类型",
            "title": "标题",
            "formula": "识别到的公式/矩阵",
            "spotlight": "公式/图像讲解",
            "summary": "摘要",
            "key_points": "关键点",
            "next_action": "建议下一步",
            "untitled": "未识别",
            "no_summary": "暂无摘要",
            "no_points": "暂无关键点",
            "fallback_next": "继续浏览当前页面，或追问某个术语、图表、公式的含义。",
        }

    lines = [
        f"{labels['page_type']}: {result.page_type}",
        f"{labels['title']}: {result.title or labels['untitled']}",
        "",
    ]
    if formula_text:
        lines.extend([f"{labels['formula']}:", formula_text, ""])
    if formula_spotlight:
        lines.extend([f"{labels['spotlight']}:", formula_spotlight, ""])

    lines.extend([f"{labels['summary']}:", summary or labels["no_summary"], "", f"{labels['key_points']}:"])
    if key_points:
        lines.extend(f"- {point}" for point in key_points)
    else:
        lines.append(f"- {labels['no_points']}")

    lines.extend(
        [
            "",
            f"{labels['next_action']}:",
            next_action or labels["fallback_next"],
        ]
    )
    return "\n".join(lines)


def format_payload_text(payload: dict, language: str = "Chinese") -> str:
    result = DesktopAnalysis(
        page_type=str(payload.get("page_type", "other")),
        title=str(payload.get("title", "")),
        line1=str(payload.get("line1", "")),
        line2=str(payload.get("line2", "")),
        formula_text=str(payload.get("formula_text", "")),
        summary=str(payload.get("summary_raw", payload.get("summary", ""))),
        formula_spotlight=str(payload.get("formula_spotlight", "")),
        key_points=list(payload.get("key_points", [])),
        next_action=str(payload.get("next_action", "")),
    )
    return format_analysis_text(result, language=language)


def analysis_to_payload(result: DesktopAnalysis, language: str = "Chinese") -> dict:
    payload = asdict(result)
    payload["formula_text"] = _clean_formula_text(result.formula_text)
    payload["formula_spotlight"] = _clean_display_text(result.formula_spotlight)
    payload["summary_raw"] = _clean_display_text(result.summary)
    payload["summary"] = _overlay_summary_text(result, language=language)
    payload["key_points"] = [_clean_display_text(point) for point in result.key_points]
    payload["next_action"] = _clean_display_text(result.next_action)
    payload["display_text"] = format_analysis_text(result, language=language)
    return payload


def _analysis_from_raw_text(raw: str, language: str = "Chinese") -> DesktopAnalysis:
    data = _parse_response_to_fields(raw)
    fallback_line1 = "Detected a study page" if _is_english(language) else "检测到学习页面"
    fallback_line1_error = "Result format error" if _is_english(language) else "分析结果格式异常"
    return DesktopAnalysis(
        page_type=str(data.get("page_type", "other")).strip() or "other",
        title=_clean_display_text(str(data.get("title", ""))),
        line1=_clean_display_text(str(data.get("line1", fallback_line1_error if data.get("_fallback_error") else fallback_line1)))[:24],
        line2=_clean_display_text(str(data.get("line2", "")))[:48],
        formula_text=_clean_formula_text(str(data.get("formula_text", ""))),
        summary=_clean_display_text(str(data.get("summary", ""))),
        formula_spotlight=_clean_display_text(str(data.get("formula_spotlight", ""))),
        key_points=_normalize_points(data.get("key_points")),
        next_action=_clean_display_text(str(data.get("next_action", ""))),
    )


def _build_prompt(context_text: str, language: str) -> str:
    return f"""You are an academic study assistant.

The image is a screenshot from a student's desktop. It may show a paper, slide,
PDF, textbook, course website, chart, code notebook, whiteboard image, or study
material. Do NOT just describe the screen. Help the student understand the
content at a high level.

If the screenshot contains equations, matrices, vectors, coordinate axes, graphs,
derivations, or other math content, you MUST prioritize explaining them. When
possible, explain at least one concrete formula, matrix relation, or graph-to-
equation connection that is actually visible in the image.

{context_text}

Return a JSON object with exactly these fields:
- page_type: one of ["paper", "slides", "document", "webpage", "code", "whiteboard", "chart", "other"]
- title: short title for the current content
- line1: very short {language} subtitle for the current page, <= 24 characters
- line2: a second short {language} subtitle with the most useful insight, <= 32 characters; if formulas or diagrams are visible, prefer making this about them
- formula_text: if a formula, matrix, vector relation, or graph label is clearly visible, copy one important expression in short plain text or LaTeX-like notation; otherwise return an empty string
- summary: 2-4 {language} sentences that explain the main academic content; if formulas or diagrams are visible, this must include a concrete explanation of them instead of generic study advice
- formula_spotlight: 1-2 {language} sentences explaining the most important visible formula, matrix, graph, or symbol relation; if nothing mathematical is visible, return an empty string
- key_points: an array of 2-4 short {language} bullet points; when formulas/graphs are visible, at least one bullet must explain a concrete formula, symbol meaning, or algebra-geometry relation
- next_action: one short {language} suggestion for what the student can ask next

Rules:
- Focus on teaching, not scene description.
- Prefer explaining visible formulas, variables, matrices, and graph relationships over giving broad generic summaries.
- If you can read symbols such as x, y, A, b, matrix entries, or a plotted intersection point, use them conservatively.
- If both algebra and a graph/diagram are visible, explain how they correspond to each other.
- When formulas are visible, prefer returning a concrete formula in formula_text instead of leaving it empty.
- Do not put raw LaTeX commands into summary, key_points, or next_action unless absolutely necessary. Put symbolic expressions mainly in formula_text.
- If the current screenshot is clearly from a different subject than the recent context, ignore the recent context instead of forcing continuity.
- If text is blurry, infer conservatively and say less rather than hallucinating.
- Keep output useful for study and review.
- Respond in {language}.
- Output JSON only, with no markdown fences or extra commentary."""


def _normalize_points(value) -> list[str]:
    if isinstance(value, list):
        cleaned = [_clean_display_text(str(item)) for item in value]
        return [item for item in cleaned if item]
    if isinstance(value, str) and value.strip():
        parts = re.split(r"[;\n]+", value)
        cleaned = [_clean_display_text(part) for part in parts]
        return [item for item in cleaned if item]
    return []


def _overlay_summary_text(result: DesktopAnalysis, language: str = "Chinese") -> str:
    parts: list[str] = []
    if result.formula_text:
        parts.append(f"{'Formula' if _is_english(language) else '公式'}: {_clean_formula_text(result.formula_text)}")
    if result.formula_spotlight:
        parts.append(_clean_display_text(result.formula_spotlight))
    if result.summary:
        parts.append(_clean_display_text(result.summary))
    return "\n".join(part for part in parts if part).strip()


def _parse_response_to_fields(raw: str) -> dict:
    text = _strip_code_fences(raw.strip())

    parsed = _try_parse_json(text)
    if parsed is not None:
        return _coerce_field_dict(parsed)

    brace_match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if brace_match:
        parsed = _try_parse_json(brace_match.group(0))
        if parsed is not None:
            return _coerce_field_dict(parsed)

    if brace_match:
        parsed = _try_parse_python_dict(brace_match.group(0))
        if parsed is not None:
            return _coerce_field_dict(parsed)

    parsed = _extract_loose_fields(text)
    if parsed is not None:
        return _coerce_field_dict(parsed)

    return {
        "_fallback_error": True,
        "page_type": "other",
        "title": "",
        "line1": "",
        "line2": "",
        "formula_text": "",
        "formula_spotlight": "",
        "summary": text[:400],
        "key_points": [],
        "next_action": "",
    }


def _try_parse_json(text: str) -> dict | None:
    candidates = [text, _repair_json_string_escapes(text)]
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _try_parse_python_dict(text: str) -> dict | None:
    candidate = _repair_json_string_escapes(text)
    try:
        parsed = ast.literal_eval(candidate)
    except Exception:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _extract_loose_fields(text: str) -> dict | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    alias_to_key = {
        "page_type": "page_type",
        "page type": "page_type",
        "页面类型": "page_type",
        "title": "title",
        "标题": "title",
        "line1": "line1",
        "line 1": "line1",
        "line2": "line2",
        "line 2": "line2",
        "formula_text": "formula_text",
        "formula text": "formula_text",
        "公式": "formula_text",
        "summary": "summary",
        "摘要": "summary",
        "formula_spotlight": "formula_spotlight",
        "formula spotlight": "formula_spotlight",
        "公式讲解": "formula_spotlight",
        "key_points": "key_points",
        "key points": "key_points",
        "关键点": "key_points",
        "next_action": "next_action",
        "next action": "next_action",
        "下一步": "next_action",
    }

    result: dict[str, object] = {}
    current_key: str | None = None

    for line in lines:
        match = re.match(r"^([A-Za-z0-9_\u4e00-\u9fff ]+)\s*[:：]\s*(.*)$", line)
        if match:
            key_alias = match.group(1).strip().lower()
            current_key = alias_to_key.get(key_alias)
            value = match.group(2).strip()
            if current_key == "key_points":
                result[current_key] = _normalize_points(value)
            elif current_key:
                result[current_key] = value
            continue

        if current_key == "key_points":
            result.setdefault("key_points", [])
            if isinstance(result["key_points"], list):
                result["key_points"].append(line.lstrip("-• ").strip())
        elif current_key and line:
            previous = str(result.get(current_key, "")).strip()
            result[current_key] = f"{previous} {line}".strip() if previous else line

    return result if result else None


def _coerce_field_dict(data: dict) -> dict:
    return {
        "_fallback_error": bool(data.get("_fallback_error")),
        "page_type": str(data.get("page_type", "other")).strip() or "other",
        "title": str(data.get("title", "")).strip(),
        "line1": str(data.get("line1", "")).strip(),
        "line2": str(data.get("line2", "")).strip(),
        "formula_text": str(data.get("formula_text", "")).strip(),
        "summary": str(data.get("summary", "")).strip(),
        "formula_spotlight": str(data.get("formula_spotlight", "")).strip(),
        "key_points": _normalize_points(data.get("key_points")),
        "next_action": str(data.get("next_action", "")).strip(),
    }


def _repair_json_string_escapes(text: str) -> str:
    return re.sub(r"\\(?![\"\\/bfnrtu])", r"\\\\", text)


def _strip_code_fences(text: str) -> str:
    if text.startswith("```"):
        text = re.sub(r"^```[A-Za-z0-9_-]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _clean_formula_text(text: str) -> str:
    cleaned = str(text).strip()
    cleaned = cleaned.replace("```", "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _clean_display_text(text: str) -> str:
    cleaned = str(text).strip()
    cleaned = cleaned.replace("```", "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _is_english(language: str | None) -> bool:
    return str(language or "").strip().lower().startswith("english")
