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
    summary: str
    key_points: list[str]
    next_action: str


class DesktopContext:
    """Keep a short rolling memory of recent desktop analyses."""

    def __init__(self, max_entries: int = 5):
        self.max_entries = max_entries
        self._entries: list[str] = []

    def add(self, summary: str) -> None:
        text = summary.strip()
        if text:
            self._entries.append(text)
            self._entries = self._entries[-self.max_entries :]

    def to_prompt_text(self) -> str:
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
    lines = [
        f"页面类型: {result.page_type}",
        f"标题: {result.title or '未识别'}",
        "",
        "摘要:",
        result.summary or "暂无摘要",
        "",
        "关键点:",
    ]
    if result.key_points:
        lines.extend(f"- {point}" for point in result.key_points)
    else:
        lines.append("- 暂无关键点")
    lines.extend(
        [
            "",
            "建议下一步:",
            result.next_action or "继续浏览当前页面，或追问某个术语/图表/公式的含义。",
        ]
    )
    return "\n".join(lines)


def analysis_to_payload(result: DesktopAnalysis) -> dict:
    payload = asdict(result)
    payload["display_text"] = format_analysis_text(result)
    return payload


def _analysis_from_raw_text(raw: str) -> DesktopAnalysis:
    data = _parse_json_response(raw)
    return DesktopAnalysis(
        page_type=str(data.get("page_type", "other")),
        title=str(data.get("title", "")),
        line1=str(data.get("line1", "检测到学习页面")),
        line2=str(data.get("line2", "")),
        summary=str(data.get("summary", "")),
        key_points=_normalize_points(data.get("key_points")),
        next_action=str(data.get("next_action", "")),
    )


def _build_prompt(context_text: str, language: str) -> str:
    return f"""You are an academic study assistant.

The image is a screenshot from a student's desktop. It may show a paper, slide,
PDF, textbook, course website, chart, code notebook, whiteboard image, or study
material. Do NOT just describe the screen. Help the student understand the
content at a high level.

{context_text}

Return a JSON object with exactly these fields:
- page_type: one of ["paper", "slides", "document", "webpage", "code", "whiteboard", "chart", "other"]
- title: short title for the current content
- line1: very short Chinese subtitle for the current page, <= 24 characters
- line2: a second short Chinese subtitle with the most useful insight, <= 32 characters, may be empty
- summary: 2-4 Chinese sentences that explain the main academic content
- key_points: an array of 2-4 short Chinese bullet points
- next_action: one short Chinese suggestion for what the student can ask next

Rules:
- Focus on teaching, not scene description.
- If text is blurry, infer conservatively and say less rather than hallucinating.
- Keep output useful for study and review.
- Respond in {language}.
- Output JSON only, with no markdown fences or extra commentary."""


def _normalize_points(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in re.split(r"[;\n]+", value) if part.strip()]
    return []


def _parse_json_response(raw: str) -> dict:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        return json.loads(match.group(0))

    return {
        "page_type": "other",
        "title": "",
        "line1": "分析结果格式异常",
        "line2": "",
        "summary": text[:400],
        "key_points": [],
        "next_action": "",
    }
