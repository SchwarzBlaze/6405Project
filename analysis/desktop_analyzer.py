"""Academic desktop-image analysis helpers."""

from __future__ import annotations

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
    formula_text = _render_math_text(result.formula_text)
    formula_spotlight = _render_math_text(result.formula_spotlight)
    summary = _render_math_text(result.summary)
    key_points = [_render_math_text(point) for point in result.key_points]
    next_action = _render_math_text(result.next_action)

    lines = [
        f"页面类型: {result.page_type}",
        f"标题: {result.title or '未识别'}",
        "",
    ]
    if formula_text:
        lines.extend(
            [
                "识别到的公式/矩阵:",
                formula_text,
                "",
            ]
        )
    if formula_spotlight:
        lines.extend(
            [
                "公式/图像讲解:",
                formula_spotlight,
                "",
            ]
        )
    lines.extend(
        [
            "摘要:",
            summary or "暂无摘要",
            "",
            "关键点:",
        ]
    )
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
    payload["formula_text"] = _render_math_text(result.formula_text)
    payload["formula_spotlight"] = _render_math_text(result.formula_spotlight)
    payload["summary"] = _overlay_summary_text(result)
    payload["key_points"] = [_render_math_text(point) for point in result.key_points]
    payload["next_action"] = _render_math_text(result.next_action)
    payload["display_text"] = format_analysis_text(result)
    return payload


def _analysis_from_raw_text(raw: str) -> DesktopAnalysis:
    data = _parse_json_response(raw)
    return DesktopAnalysis(
        page_type=str(data.get("page_type", "other")),
        title=str(data.get("title", "")),
        line1=str(data.get("line1", "检测到学习页面")),
        line2=str(data.get("line2", "")),
        formula_text=str(data.get("formula_text", "")),
        summary=str(data.get("summary", "")),
        formula_spotlight=str(data.get("formula_spotlight", "")),
        key_points=_normalize_points(data.get("key_points")),
        next_action=str(data.get("next_action", "")),
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
- formula_text: if a formula, matrix, vector relation, or graph label is clearly visible, copy one important expression in short plain text, for example "2x - y = 0", "A x = b", or "[[2,-1],[-1,2]] [x,y]^T = [0,3]^T"; otherwise return an empty string
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
- If the current screenshot is clearly from a different subject than the recent context, ignore the recent context instead of forcing continuity.
- If text is blurry, infer conservatively and say less rather than hallucinating.
- Avoid generic phrases like "掌握代入法和消元法" unless those methods are clearly supported by the screenshot.
- Keep output useful for study and review.
- Respond in {language}.
- Output JSON only, with no markdown fences or extra commentary."""


def _normalize_points(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in re.split(r"[;\n]+", value) if part.strip()]
    return []


def _overlay_summary_text(result: DesktopAnalysis) -> str:
    parts: list[str] = []
    if result.formula_text:
        parts.append(f"公式：{_render_math_text(result.formula_text)}")
    if result.formula_spotlight:
        parts.append(f"公式讲解：{_render_math_text(result.formula_spotlight)}")
    if result.summary:
        parts.append(_render_math_text(result.summary))
    return "\n".join(part for part in parts if part).strip()


def _parse_json_response(raw: str) -> dict:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    parsed = _try_parse_json(text)
    if parsed is not None:
        return parsed

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        parsed = _try_parse_json(match.group(0))
        if parsed is not None:
            return parsed

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
    candidates = [
        text,
        _repair_json_string_escapes(text),
    ]
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


def _repair_json_string_escapes(text: str) -> str:
    """Repair common model-produced JSON mistakes inside quoted strings."""

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


_LATEX_REPLACEMENTS = {
    r"\cup": "∪",
    r"\cap": "∩",
    r"\subset": "⊂",
    r"\subseteq": "⊆",
    r"\supset": "⊃",
    r"\supseteq": "⊇",
    r"\in": "∈",
    r"\notin": "∉",
    r"\forall": "∀",
    r"\exists": "∃",
    r"\land": "∧",
    r"\lor": "∨",
    r"\to": "→",
    r"\rightarrow": "→",
    r"\leftarrow": "←",
    r"\Rightarrow": "⇒",
    r"\Leftarrow": "⇐",
    r"\leftrightarrow": "↔",
    r"\leq": "≤",
    r"\geq": "≥",
    r"\neq": "≠",
    r"\approx": "≈",
    r"\times": "×",
    r"\cdot": "·",
    r"\pm": "±",
    r"\infty": "∞",
    r"\alpha": "α",
    r"\beta": "β",
    r"\gamma": "γ",
    r"\delta": "δ",
    r"\epsilon": "ϵ",
    r"\theta": "θ",
    r"\lambda": "λ",
    r"\mu": "μ",
    r"\pi": "π",
    r"\sigma": "σ",
    r"\phi": "φ",
    r"\omega": "ω",
    r"\Gamma": "Γ",
    r"\Delta": "Δ",
    r"\Theta": "Θ",
    r"\Lambda": "Λ",
    r"\Pi": "Π",
    r"\Sigma": "Σ",
    r"\Phi": "Φ",
    r"\Omega": "Ω",
}


def _render_math_text(text: str) -> str:
    if not text:
        return ""

    rendered = str(text)
    rendered = re.sub(r"\\{2,}(?=[A-Za-z])", r"\\", rendered)

    for latex, symbol in _LATEX_REPLACEMENTS.items():
        rendered = rendered.replace(latex, symbol)

    rendered = re.sub(r"\\+text\{([^{}]+)\}", r"\1", rendered)
    rendered = re.sub(r"\\+mathrm\{([^{}]+)\}", r"\1", rendered)
    rendered = re.sub(r"\\+operatorname\{([^{}]+)\}", r"\1", rendered)
    rendered = rendered.replace("{", "").replace("}", "")
    return rendered.strip()
