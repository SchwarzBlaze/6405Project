"""Lecture video analysis: classification, per-segment interpretation, and
rolling context management."""

from __future__ import annotations

import logging
import os
import re
from enum import Enum

import numpy as np

from .model import generate
from .slide_detector import Segment

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Video type classification
# ---------------------------------------------------------------------------

class VideoType(str, Enum):
    SLIDES = "SLIDES"
    TEACHER_SLIDES = "TEACHER_SLIDES"
    WHITEBOARD = "WHITEBOARD"
    TEACHER_ONLY = "TEACHER_ONLY"
    SCREEN_RECORDING = "SCREEN_RECORDING"

    @classmethod
    def from_string(cls, text: str) -> "VideoType":
        cleaned = text.strip().upper().replace(" ", "_")
        for member in cls:
            if member.value in cleaned:
                return member
        return cls.SLIDES


_CLASSIFY_PROMPT = """\
Look at these sample frames from a lecture / educational video.
Classify the video into exactly ONE of these categories:

- SLIDES – presentation slides or screen-shared slides occupy most of the frame
- TEACHER_SLIDES – a teacher / presenter is visible AND slides or projected content are also shown
- WHITEBOARD – a teacher writes on a whiteboard, blackboard, or similar surface
- TEACHER_ONLY – only a teacher / presenter speaking to camera, no visual aids
- SCREEN_RECORDING – screen recording of software, code, or digital content that is NOT slides

Respond with ONLY the category name, nothing else."""


def classify_video_type(
    model,
    processor,
    frame_paths: list[str],
    max_samples: int = 5,
) -> VideoType:
    """Send a handful of sample frames to Gemma 4 and return the detected
    :class:`VideoType`."""
    indices = np.linspace(0, len(frame_paths) - 1, min(max_samples, len(frame_paths)), dtype=int)
    content: list[dict] = []
    for idx in indices:
        content.append({"type": "image", "url": frame_paths[int(idx)]})
    content.append({"type": "text", "text": _CLASSIFY_PROMPT})

    messages = [{"role": "user", "content": content}]
    response = generate(model, processor, messages, max_tokens=30)
    vtype = VideoType.from_string(response)
    logger.info("Video classified as %s (raw response: %r)", vtype.value, response)
    return vtype


# ---------------------------------------------------------------------------
# Default thresholds per video type
# ---------------------------------------------------------------------------

_TYPE_DEFAULTS: dict[VideoType, dict] = {
    VideoType.SLIDES:           {"threshold": 0.15, "representative": "first", "min_duration": 2.0},
    VideoType.TEACHER_SLIDES:   {"threshold": 0.12, "representative": "middle", "min_duration": 3.0},
    VideoType.WHITEBOARD:       {"threshold": 0.03, "representative": "last",  "min_duration": 5.0},
    VideoType.TEACHER_ONLY:     {"threshold": 0.08, "representative": "middle", "min_duration": 10.0},
    VideoType.SCREEN_RECORDING: {"threshold": 0.10, "representative": "first", "min_duration": 2.0},
}


def get_defaults_for_type(vtype: VideoType) -> dict:
    return dict(_TYPE_DEFAULTS.get(vtype, _TYPE_DEFAULTS[VideoType.SLIDES]))


# ---------------------------------------------------------------------------
# Rolling context
# ---------------------------------------------------------------------------

class LectureContext:
    """Keeps a bounded window of segment summaries so that each new analysis
    prompt receives enough background without overflowing the context."""

    def __init__(self, max_entries: int = 10):
        self._entries: list[tuple[int, str]] = []
        self.max_entries = max_entries

    def add(self, segment_index: int, summary: str) -> None:
        self._entries.append((segment_index, summary))

    def get_context_text(self) -> str:
        if not self._entries:
            return "This is the very beginning of the lecture — no prior content."
        recent = self._entries[-self.max_entries:]
        lines = [f"  • Segment {idx + 1}: {s}" for idx, s in recent]
        header = "What has been covered so far:\n"
        if len(self._entries) > self.max_entries:
            header = (f"What has been covered so far "
                      f"(last {self.max_entries} of {len(self._entries)} segments):\n")
        return header + "\n".join(lines)

    @staticmethod
    def extract_summary(full_analysis: str, max_length: int = 200) -> str:
        """Extract a concise summary from the analysis for rolling context.

        Prefers the **Topic** line when available, falls back to the first
        substantive line."""
        for line in full_analysis.split("\n"):
            stripped = line.strip()
            if "**Topic**" in stripped or "**topic**" in stripped.lower():
                text = re.sub(r"\*\*.*?\*\*:?\s*", "", stripped).strip()
                if len(text) > 10:
                    return text[:max_length]
        for line in full_analysis.split("\n"):
            stripped = line.strip().lstrip("#*•- ")
            if len(stripped) > 15:
                return stripped[:max_length] + ("..." if len(stripped) > max_length else "")
        clean = full_analysis.replace("\n", " ").strip()
        return clean[:max_length] + ("..." if len(clean) > max_length else "")


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

def _ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _lang_instruction(language: str | None) -> str:
    if language:
        return f"\nRespond in {language}."
    return "\nRespond in the same language as the content shown."


def _build_slide_prompt(
    context_text: str,
    seg_index: int,
    total: int,
    start: float,
    end: float,
    audio_text: str | None = None,
    language: str | None = None,
) -> str:
    parts = [
        "You are an expert tutor helping a student understand a lecture video "
        "in real time. The student can already see the current slide — do NOT "
        "describe what is visible. Instead, TEACH the subject matter: explain "
        "the concepts, formulas, and ideas being presented.\n\n",
        context_text, "\n\n",
        f"Analyzing slide {seg_index + 1}/{total} "
        f"(time: {_ts(start)} – {_ts(end)}).\n",
    ]
    if audio_text:
        parts.append(f'\nThe lecturer said: "{audio_text}"\n')
    parts.append(
        "\nStructure your response as bullet points:\n\n"
        "• **Topic**: State the main concept in a clear phrase, "
        "then summarize in 1-2 sentences.\n\n"
        "• **Key Concepts**: Identify the important ideas, terms, or formulas. "
        "For formulas, explain what each variable means and the intuition.\n\n"
        "• **Deep Dive**: Teach the underlying concept — provide reasoning, "
        "analogies, or examples that go beyond what is on the slide.\n\n"
        "• **Connection**: How does this relate to earlier content "
        "and the broader course? What should the student remember?\n\n"
        "Keep each bullet to 1-2 concise sentences. "
        "Do NOT repeat or list what is written on the slide.\n\n"
        "IMPORTANT: Write plain text only. Do NOT use markdown formatting "
        "such as *italic*, _underline_, # headings, or `code`. "
        "Only use **bold** for the four section labels above."
    )
    parts.append(_lang_instruction(language))
    return "".join(parts)


def _build_whiteboard_prompt(
    context_text: str,
    seg_index: int,
    total: int,
    start: float,
    end: float,
    has_prev_frame: bool = False,
    audio_text: str | None = None,
    language: str | None = None,
) -> str:
    parts = [
        "You are an expert tutor helping a student understand a blackboard / "
        "whiteboard lecture in real time. The student can see the board — "
        "do NOT simply transcribe what is written. Instead, TEACH the subject "
        "matter: explain the mathematics, reasoning, and ideas.\n\n",
        context_text, "\n\n",
        f"Analyzing segment {seg_index + 1}/{total} "
        f"(time: {_ts(start)} – {_ts(end)}).\n",
    ]
    if has_prev_frame:
        parts.append(
            "\nThe FIRST image is the board earlier; the SECOND is the "
            "current state. Focus on what is new.\n"
        )
    if audio_text:
        parts.append(f'\nThe lecturer said: "{audio_text}"\n')
    parts.append(
        "\nStructure your response as bullet points:\n\n"
        "• **New Content**: What new concept, equation, or diagram has "
        "appeared on the board? Summarize briefly.\n\n"
        "• **Explanation**: Teach the new material step by step. For "
        "equations, explain the reasoning behind each step.\n\n"
        "• **Intuition**: Provide the deeper \"why.\" Use analogies, visual "
        "reasoning, or real-world examples to build understanding.\n\n"
        "• **Connection**: How does this fit into the overall topic and "
        "build on what came before?\n\n"
        "Keep each bullet to 1-2 concise sentences. "
        "Do NOT just transcribe what is on the board.\n\n"
        "IMPORTANT: Write plain text only. Do NOT use markdown formatting "
        "such as *italic*, _underline_, # headings, or `code`. "
        "Only use **bold** for the four section labels above."
    )
    parts.append(_lang_instruction(language))
    return "".join(parts)


def _build_teacher_prompt(
    context_text: str,
    seg_index: int,
    total: int,
    start: float,
    end: float,
    audio_text: str | None = None,
    language: str | None = None,
) -> str:
    parts = [
        "You are an expert tutor helping a student understand a lecture "
        "in real time. The student can see the lecturer — focus entirely "
        "on TEACHING the subject matter being discussed, not on describing "
        "the scene.\n\n",
        context_text, "\n\n",
        f"Analyzing segment {seg_index + 1}/{total} "
        f"(time: {_ts(start)} – {_ts(end)}).\n",
    ]
    if audio_text:
        parts.append(f'\nThe lecturer said: "{audio_text}"\n')
    parts.append(
        "\nStructure your response as bullet points:\n\n"
        "• **Topic**: What concept is being taught right now? "
        "State it in 1-2 clear sentences.\n\n"
        "• **Key Points**: What are the most important ideas being "
        "conveyed? Explain them.\n\n"
        "• **Deep Dive**: Teach the concept in detail — provide clear "
        "explanations, examples, and intuition.\n\n"
        "• **Connection**: How does this relate to the broader subject "
        "and earlier content?\n\n"
        "Keep each bullet to 1-2 concise sentences. "
        "Do NOT describe the teacher's appearance or actions.\n\n"
        "IMPORTANT: Write plain text only. Do NOT use markdown formatting "
        "such as *italic*, _underline_, # headings, or `code`. "
        "Only use **bold** for the four section labels above."
    )
    parts.append(_lang_instruction(language))
    return "".join(parts)


# ---------------------------------------------------------------------------
# Per-segment analysis
# ---------------------------------------------------------------------------

def analyze_segment(
    model,
    processor,
    segment: Segment,
    context: LectureContext,
    video_type: VideoType,
    total_segments: int,
    audio_text: str | None = None,
    prev_frame_path: str | None = None,
    max_tokens: int = 1024,
    language: str | None = None,
) -> str:
    """Analyse a single segment and return the generated interpretation."""
    assert segment.frame_path, "segment.frame_path must be set before calling analyze_segment"
    ctx = context.get_context_text()

    if video_type == VideoType.WHITEBOARD:
        prompt = _build_whiteboard_prompt(
            ctx, segment.index, total_segments,
            segment.start_time, segment.end_time,
            has_prev_frame=prev_frame_path is not None,
            audio_text=audio_text, language=language,
        )
    elif video_type in (VideoType.TEACHER_SLIDES, VideoType.TEACHER_ONLY):
        prompt = _build_teacher_prompt(
            ctx, segment.index, total_segments,
            segment.start_time, segment.end_time,
            audio_text=audio_text, language=language,
        )
    else:
        prompt = _build_slide_prompt(
            ctx, segment.index, total_segments,
            segment.start_time, segment.end_time,
            audio_text=audio_text, language=language,
        )

    content: list[dict] = []
    if prev_frame_path and video_type == VideoType.WHITEBOARD:
        content.append({"type": "image", "url": prev_frame_path})
    content.append({"type": "image", "url": segment.frame_path})
    content.append({"type": "text", "text": prompt})

    messages = [{"role": "user", "content": content}]

    analysis = generate(model, processor, messages, max_tokens=max_tokens)
    analysis = _strip_preamble(analysis)
    analysis = _clean_markdown(analysis)
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:
        pass
    return analysis


def _strip_preamble(text: str) -> str:
    """Remove filler sentences before the first bullet point."""
    lines = text.split("\n")
    first_bullet = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^[•\-\*]\s", stripped) or re.match(r"^\d+\.\s", stripped):
            first_bullet = i
            break
    if first_bullet > 0:
        return "\n".join(lines[first_bullet:])
    return text


def _clean_markdown(text: str) -> str:
    """Strip unwanted markdown syntax while preserving **bold** labels."""
    # Protect **bold** markers
    text = text.replace("**", "\x00B\x00")
    # Remove *italic* and _italic_
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", text)
    # Remove # headings
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove `inline code`
    text = re.sub(r"`(.+?)`", r"\1", text)
    # Restore **bold**
    text = text.replace("\x00B\x00", "**")
    return text


# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------

_SUMMARY_PROMPT = """\
You are an expert tutor. Below are your explanations for each segment of a
lecture. Write a concise **study guide** (5-10 sentences) that a student can
use to review the material.

Cover the main topics, key concepts, important formulas, and the logical
flow of ideas. Highlight what is most important to understand and remember.

Respond in the same language as the segment analyses.

---
{analyses}
---"""


def generate_summary(
    model,
    processor,
    analyses: list[str],
    max_tokens: int = 1024,
) -> str:
    combined = "\n\n".join(
        f"[Segment {i + 1}]\n{text}" for i, text in enumerate(analyses)
    )
    if len(combined) > 300_000:
        combined = combined[:300_000] + "\n... (truncated)"

    prompt = _SUMMARY_PROMPT.format(analyses=combined)
    messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
    return generate(model, processor, messages, max_tokens=max_tokens)
