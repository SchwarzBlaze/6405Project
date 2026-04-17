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
        if self.max_entries <= 0:
            return "No prior context."
        if not self._entries:
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
    return _analysis_from_raw_text(raw)


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
    return _analysis_from_raw_text(raw)


def format_analysis_text(result: DesktopAnalysis) -> str:
    formula_text = _clean_display_text(result.formula_text)
    formula_spotlight = _clean_display_text(result.formula_spotlight)
    summary = _clean_display_text(result.summary)
    key_points = [_clean_display_text(point) for point in result.key_points]
    next_action = _clean_display_text(result.next_action)

    lines = [
        f"页面类型: {result.page_type}",
        f"标题: {result.title or '未识别'}",
        "",
    ]
    if formula_text:
        lines.extend(["识别到的公式/矩阵:", formula_text, ""])
    if formula_spotlight:
        lines.extend(["公式/图像讲解:", formula_spotlight, ""])

    lines.extend(["摘要:", summary or "暂无摘要", "", "关键点:"])
    if key_points:
        lines.extend(f"- {point}" for point in key_points)
    else:
        lines.append("- 暂无关键点")

    lines.extend(
        [
            "",
            "建议下一步:",
            next_action or "继续浏览当前页面，或追问某个术语、图表、公式的含义。",
        ]
    )
    return "\n".join(lines)


def analysis_to_payload(result: DesktopAnalysis) -> dict:
    payload = asdict(result)
    payload["formula_text"] = _clean_formula_text(result.formula_text)
    payload["formula_spotlight"] = _clean_display_text(result.formula_spotlight)
    payload["summary"] = _overlay_summary_text(result)
    payload["key_points"] = [_clean_display_text(point) for point in result.key_points]
    payload["next_action"] = _clean_display_text(result.next_action)
    payload["display_text"] = format_analysis_text(result)
    return payload


def _analysis_from_raw_text(raw: str) -> DesktopAnalysis:
    data = _parse_response_to_fields(raw)
    return DesktopAnalysis(
        page_type=str(data.get("page_type", "other")).strip() or "other",
        title=_clean_display_text(str(data.get("title", ""))),
        line1=_clean_display_text(str(data.get("line1", "检测到学习页面")))[:24],
        line2=_clean_display_text(str(data.get("line2", "")))[:32],
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
- line1: very short Chinese subtitle for the current page, <= 24 characters
- line2: a second short Chinese subtitle with the most useful insight, <= 32 characters; if formulas or diagrams are visible, prefer making this about them
- formula_text: if a formula, matrix, vector relation, or graph label is clearly visible, copy one important expression in short plain text or LaTeX-like notation; otherwise return an empty string
- summary: 2-4 Chinese sentences that explain the main academic content; if formulas or diagrams are visible, this must include a concrete explanation of them instead of generic study advice
- formula_spotlight: 1-2 Chinese sentences explaining the most important visible formula, matrix, graph, or symbol relation; if nothing mathematical is visible, return an empty string
- key_points: an array of 2-4 short Chinese bullet points; when formulas/graphs are visible, at least one bullet must explain a concrete formula, symbol meaning, or algebra-geometry relation
- next_action: one short Chinese suggestion for what the student can ask next

Rules:
- Focus on teaching, not scene description.
- Prefer explaining visible formulas, variables, matrices, and graph relationships over giving broad generic summaries.
- If you can read symbols such as x, y, A, b, matrix entries, or a plotted intersection point, use them in the explanation conservatively.
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


def _overlay_summary_text(result: DesktopAnalysis) -> str:
    parts: list[str] = []
    if result.formula_text:
        parts.append(f"公式：{_clean_formula_text(result.formula_text)}")
    if result.formula_spotlight:
        parts.append(f"公式讲解：{_clean_display_text(result.formula_spotlight)}")
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

    dict_match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if dict_match:
        parsed = _try_parse_python_dict(dict_match.group(0))
        if parsed is not None:
            return _coerce_field_dict(parsed)

    parsed = _extract_loose_fields(text)
    if parsed is not None:
        return _coerce_field_dict(parsed)

    return {
        "page_type": "other",
        "title": "",
        "line1": "分析结果格式异常",
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
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
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
        "第一行": "line1",
        "line2": "line2",
        "line 2": "line2",
        "第二行": "line2",
        "formula_text": "formula_text",
        "formula": "formula_text",
        "equation": "formula_text",
        "公式": "formula_text",
        "formula_spotlight": "formula_spotlight",
        "formula explanation": "formula_spotlight",
        "公式讲解": "formula_spotlight",
        "summary": "summary",
        "摘要": "summary",
        "key_points": "key_points",
        "key points": "key_points",
        "关键点": "key_points",
        "next_action": "next_action",
        "next action": "next_action",
        "next step": "next_action",
        "下一步": "next_action",
    }

    data: dict[str, object] = {
        "page_type": "other",
        "title": "",
        "line1": "检测到学习页面",
        "line2": "",
        "formula_text": "",
        "formula_spotlight": "",
        "summary": "",
        "key_points": [],
        "next_action": "",
    }

    current_key: str | None = None
    for line in lines:
        if re.match(r"^[-*•]\s+", line) and current_key == "key_points":
            point = re.sub(r"^[-*•]\s+", "", line).strip()
            if point:
                data["key_points"].append(point)
            continue

        match = re.match(r"^([^:：]{1,40})\s*[:：]\s*(.*)$", line)
        if match:
            raw_key = match.group(1).strip().lower()
            value = match.group(2).strip()
            current_key = alias_to_key.get(raw_key)
            if current_key == "key_points":
                if value:
                    pieces = [part.strip() for part in re.split(r"[;；]+", value) if part.strip()]
                    data["key_points"].extend(pieces)
            elif current_key:
                if current_key in {"summary", "formula_spotlight"} and data[current_key]:
                    data[current_key] = f"{data[current_key]}\n{value}".strip()
                else:
                    data[current_key] = value
            else:
                current_key = None
            continue

        if current_key == "key_points":
            point = re.sub(r"^[-*•]\s*", "", line).strip()
            if point:
                data["key_points"].append(point)
            continue

        if current_key in {"summary", "formula_spotlight", "next_action"}:
            existing = str(data[current_key]).strip()
            data[current_key] = f"{existing}\n{line}".strip() if existing else line
            continue

        if not data["summary"]:
            data["summary"] = line
        else:
            data["summary"] = f"{data['summary']}\n{line}".strip()

    has_any_content = any(
        bool(data.get(key))
        for key in ["title", "line1", "line2", "formula_text", "summary", "formula_spotlight", "key_points", "next_action"]
    )
    return data if has_any_content else None


def _coerce_field_dict(data: dict) -> dict:
    normalized = {
        "page_type": data.get("page_type", "other"),
        "title": data.get("title", ""),
        "line1": data.get("line1", "检测到学习页面"),
        "line2": data.get("line2", ""),
        "formula_text": data.get("formula_text", data.get("formula", "")),
        "formula_spotlight": data.get("formula_spotlight", data.get("formula_explanation", "")),
        "summary": data.get("summary", ""),
        "key_points": data.get("key_points", []),
        "next_action": data.get("next_action", ""),
    }
    return normalized


def _repair_json_string_escapes(text: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    i = 0
    valid_escapes = {'"', "\\", "/", "b", "f", "n", "r", "t", "u"}

    while i < len(text):
        ch = text[i]

        if not in_string:
            result.append(ch)
            if ch == '"':
                in_string = True
            i += 1
            continue

        if escaped:
            result.append(ch)
            escaped = False
            i += 1
            continue

        if ch == "\\":
            next_char = text[i + 1] if i + 1 < len(text) else ""
            if next_char in valid_escapes:
                result.append(ch)
                escaped = True
            else:
                result.append("\\\\")
            i += 1
            continue

        if ch == '"':
            in_string = False
            result.append(ch)
            i += 1
            continue

        if ch == "\n":
            result.append("\\n")
            i += 1
            continue

        result.append(ch)
        i += 1

    return "".join(result)


def _strip_code_fences(text: str) -> str:
    cleaned = re.sub(r"^```(?:json|python)?\s*", "", text)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _clean_formula_text(text: str) -> str:
    cleaned = _clean_display_text(text)
    cleaned = cleaned.strip("`")
    cleaned = cleaned.strip()
    return cleaned


def _clean_display_text(text: str) -> str:
    cleaned = str(text or "")
    cleaned = cleaned.replace("\\n", "\n")
    cleaned = cleaned.replace("\r", "")
    cleaned = re.sub(r"^```(?:json|python)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip().strip('"').strip("'")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
