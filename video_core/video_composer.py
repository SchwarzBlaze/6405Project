"""Compose an output video with the original lecture on the left and a
synchronised analysis text panel on the right.

The panel renders rich text with **bold** emphasis, bullet points, and clean
typography. On Windows we prefer Microsoft YaHei/SimHei so Chinese analysis
text stays readable in the rendered panel.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import NamedTuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .slide_detector import Segment

logger = logging.getLogger(__name__)

# ── Fresh Teal palette ────────────────────────────────────────────────────

BG_COLOR = (10, 10, 16)
ACCENT = (78, 205, 196)          # Teal  #4ECDC4
TITLE_COLOR = (78, 205, 196)
TITLE_BG = (18, 48, 46)          # Dark teal for title pill
BOLD_COLOR = (224, 224, 238)
BODY_COLOR = (144, 144, 166)
SEPARATOR_COLOR = (30, 30, 44)
BULLET_DOT = (78, 205, 196)
TRUNCATION_NOTICE_COLOR = (166, 173, 200)
MIN_PANEL_FONT_SIZE = 11
TRUNCATION_NOTICE = "内容较多，已省略后续。"

# ── Font loading ──────────────────────────────────────────────────────────

_FONT_PAIRS = [
    (
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
    ),
    (
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simhei.ttf",
    ),
    (
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/simsun.ttc",
    ),
    (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ),
    (
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ),
    (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ),
    (
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
    ),
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
]


def _load_fonts(size: int):
    """Return (title_font, bold_font, regular_font)."""
    for reg, bold in _FONT_PAIRS:
        if os.path.isfile(reg) and os.path.isfile(bold):
            try:
                regular_font = ImageFont.truetype(reg, size)
                bold_font = ImageFont.truetype(bold, size)
                title_font = ImageFont.truetype(bold, size + 5)
                logger.info("Using annotation fonts: regular=%s bold=%s", reg, bold)
                return title_font, bold_font, regular_font
            except OSError:
                continue
        elif os.path.isfile(reg):
            try:
                regular_font = ImageFont.truetype(reg, size)
                bold_font = ImageFont.truetype(reg, size)
                title_font = ImageFont.truetype(reg, size + 5)
                logger.info("Using single annotation font for all weights: %s", reg)
                return title_font, bold_font, regular_font
            except OSError:
                continue
    d = ImageFont.load_default()
    logger.warning(
        "No annotation font with CJK support was found. Falling back to Pillow default font."
    )
    return d, d, d


# ── Rich-text helpers ─────────────────────────────────────────────────────

class _Span(NamedTuple):
    text: str
    bold: bool


@dataclass
class _RenderedLine:
    spans: list[_Span]
    x: int
    y: int
    bottom: int
    bullet: bool = False
    color_override: tuple[int, int, int] | None = None


@dataclass
class _PanelLayout:
    lines: list[_RenderedLine]
    regular_font: object
    bold_font: object
    font_size: int
    mx: int
    bottom_margin: int
    line_gap: int
    bullet_r: int
    overflow: bool


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_BULLET_RE = re.compile(r"^[•\-\*]\s+")
_NUM_RE = re.compile(r"^\d+\.\s")
_LABEL_RE = re.compile(r"^\*\*[^*]+\*\*\s*:")


def _parse_spans(line: str) -> list[_Span]:
    """Split *line* at ``**bold**`` markers into typed spans."""
    spans: list[_Span] = []
    pos = 0
    for m in _BOLD_RE.finditer(line):
        if m.start() > pos:
            spans.append(_Span(line[pos:m.start()], False))
        spans.append(_Span(m.group(1), True))
        pos = m.end()
    if pos < len(line):
        spans.append(_Span(line[pos:], False))
    return spans or [_Span("", False)]


# ── Pixel-aware text wrapping ────────────────────────────────────────────

def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    return draw.textbbox((0, 0), text, font=font)[2]


def _append_span(spans: list[_Span], text: str, bold: bool) -> None:
    if not text:
        return
    if spans and spans[-1].bold == bold:
        spans[-1] = _Span(spans[-1].text + text, bold)
    else:
        spans.append(_Span(text, bold))


def _trim_spaces(spans: list[_Span], *, leading: bool = False, trailing: bool = False) -> list[_Span]:
    result = [_Span(span.text, span.bold) for span in spans if span.text]
    if not result:
        return []

    if leading:
        while result and not result[0].text.strip():
            result.pop(0)
        if result:
            result[0] = _Span(result[0].text.lstrip(), result[0].bold)
            if not result[0].text:
                result.pop(0)

    if trailing:
        while result and not result[-1].text.strip():
            result.pop()
        if result:
            result[-1] = _Span(result[-1].text.rstrip(), result[-1].bold)
            if not result[-1].text:
                result.pop()

    return result


def _wrap_rich_spans(
    draw: ImageDraw.ImageDraw,
    spans: list[_Span],
    regular_font,
    bold_font,
    max_w: int,
) -> list[list[_Span]]:
    """Wrap spans to fit *max_w* pixels.

    This is intentionally character-based so CJK text, long URLs, and mixed
    Chinese/English content all break safely inside the panel.
    """
    if not spans or not any(span.text.strip() for span in spans):
        return [[_Span("", False)]]

    lines: list[list[_Span]] = []
    current: list[_Span] = []
    current_width = 0

    for span in spans:
        font = bold_font if span.bold else regular_font
        for ch in span.text:
            if ch == "\n":
                current = _trim_spaces(current, trailing=True)
                lines.append(current or [_Span("", False)])
                current = []
                current_width = 0
                continue

            if ch.isspace() and not current:
                continue

            ch_width = _text_width(draw, ch, font)
            if current and current_width + ch_width > max_w:
                current = _trim_spaces(current, trailing=True)
                lines.append(current or [_Span("", False)])
                current = []
                current_width = 0
                if ch.isspace():
                    continue

            _append_span(current, ch, span.bold)
            current_width += ch_width

    current = _trim_spaces(current, leading=True, trailing=True)
    if current or not lines:
        lines.append(current or [_Span("", False)])

    return lines


def _line_bottom(
    draw: ImageDraw.ImageDraw,
    y: int,
    spans: list[_Span],
    regular_font,
    bold_font,
) -> int:
    bottom = y
    for span in spans:
        if not span.text:
            continue
        font = bold_font if span.bold else regular_font
        bottom = max(bottom, draw.textbbox((0, y), span.text, font=font)[3])
    return bottom


# ── Drawing helpers ──────────────────────────────────────────────────────

def _draw_gradient_line(draw: ImageDraw.ImageDraw, x: int, y: int,
                        length: int, thickness: int, color: tuple[int, ...]):
    """Draw a horizontal line that fades from *color* to near-transparent."""
    for i in range(length):
        fade = 1.0 - (i / length) * 0.88
        c = tuple(max(0, min(255, int(v * fade))) for v in color)
        draw.line([(x + i, y), (x + i, y + thickness - 1)], fill=c)


def _draw_pill(draw: ImageDraw.ImageDraw, bbox: tuple, color: tuple, radius: int = 8):
    """Draw a rounded-rectangle pill background."""
    x0, y0, x1, y1 = bbox
    try:
        draw.rounded_rectangle([(x0, y0), (x1, y1)], radius=radius, fill=color)
    except AttributeError:
        draw.rectangle([(x0, y0), (x1, y1)], fill=color)


# ── Panel rendering ──────────────────────────────────────────────────────

def _ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _build_panel_layout(
    draw: ImageDraw.ImageDraw,
    body: str,
    size: tuple[int, int],
    font_size: int,
) -> _PanelLayout:
    w, h = size
    _ft_title, ft_bold, ft_reg = _load_fonts(font_size)

    mx = 28
    bottom_margin = 16
    line_gap = int(font_size * 0.42)
    section_gap = int(font_size * 0.7)
    bullet_indent = 24
    bullet_r = 3

    lines: list[_RenderedLine] = []
    y = 20
    overflow = False

    for raw_line in body.split("\n"):
        if y >= h - bottom_margin:
            overflow = True
            break

        stripped = raw_line.strip()
        if not stripped:
            y += section_gap
            continue

        bm = _BULLET_RE.match(stripped)
        nm = _NUM_RE.match(stripped)
        lm = _LABEL_RE.match(stripped)
        is_bullet = bool(bm)
        is_num = bool(nm)
        is_label = bool(lm) and not is_bullet
        indented = is_bullet or is_num or is_label

        content = stripped[bm.end():] if bm else stripped
        text_x = mx + (bullet_indent if indented else 0)
        avail_w = w - text_x - mx
        wrapped = _wrap_rich_spans(draw, _parse_spans(content), ft_reg, ft_bold, avail_w)

        for li, line_spans in enumerate(wrapped):
            line_bottom = _line_bottom(draw, y, line_spans, ft_reg, ft_bold)
            if line_bottom > h - bottom_margin:
                overflow = True
                break
            lines.append(
                _RenderedLine(
                    spans=line_spans,
                    x=text_x,
                    y=y,
                    bottom=line_bottom,
                    bullet=(is_bullet or is_label) and li == 0,
                )
            )
            y = line_bottom + line_gap

        if overflow:
            break

    return _PanelLayout(
        lines=lines,
        regular_font=ft_reg,
        bold_font=ft_bold,
        font_size=font_size,
        mx=mx,
        bottom_margin=bottom_margin,
        line_gap=line_gap,
        bullet_r=bullet_r,
        overflow=overflow,
    )


def _truncate_layout(
    draw: ImageDraw.ImageDraw,
    layout: _PanelLayout,
    size: tuple[int, int],
) -> _PanelLayout:
    w, h = size
    notice_spans = [_Span(TRUNCATION_NOTICE, False)]
    notice_wrapped = _wrap_rich_spans(
        draw,
        notice_spans,
        layout.regular_font,
        layout.bold_font,
        w - layout.mx * 2,
    )

    notice_heights: list[int] = []
    for line_spans in notice_wrapped:
        notice_heights.append(
            _line_bottom(draw, 0, line_spans, layout.regular_font, layout.bold_font)
        )

    notice_block_height = 0
    for idx, line_height in enumerate(notice_heights):
        notice_block_height += line_height
        if idx != len(notice_heights) - 1:
            notice_block_height += layout.line_gap

    available_bottom = h - layout.bottom_margin
    max_content_bottom = max(20, available_bottom - notice_block_height - layout.line_gap)

    kept_lines = list(layout.lines)
    while kept_lines and kept_lines[-1].bottom > max_content_bottom:
        kept_lines.pop()

    if kept_lines:
        notice_y = kept_lines[-1].bottom + layout.line_gap
    else:
        notice_y = 20

    max_notice_start = max(20, available_bottom - notice_block_height)
    notice_y = min(notice_y, max_notice_start)

    notice_lines: list[_RenderedLine] = []
    current_y = notice_y
    for idx, line_spans in enumerate(notice_wrapped):
        line_bottom = _line_bottom(draw, current_y, line_spans, layout.regular_font, layout.bold_font)
        notice_lines.append(
            _RenderedLine(
                spans=line_spans,
                x=layout.mx,
                y=current_y,
                bottom=line_bottom,
                color_override=TRUNCATION_NOTICE_COLOR,
            )
        )
        current_y = line_bottom + (layout.line_gap if idx != len(notice_wrapped) - 1 else 0)

    return _PanelLayout(
        lines=kept_lines + notice_lines,
        regular_font=layout.regular_font,
        bold_font=layout.bold_font,
        font_size=layout.font_size,
        mx=layout.mx,
        bottom_margin=layout.bottom_margin,
        line_gap=layout.line_gap,
        bullet_r=layout.bullet_r,
        overflow=False,
    )


def _render_text_panel(
    body: str,
    size: tuple[int, int],
    font_size: int = 15,
) -> np.ndarray:
    w, h = size
    img = Image.new("RGB", (w, h), color=BG_COLOR)
    draw = ImageDraw.Draw(img)
    layout: _PanelLayout | None = None

    for candidate_size in range(font_size, MIN_PANEL_FONT_SIZE - 1, -1):
        candidate_layout = _build_panel_layout(draw, body, size, candidate_size)
        if not candidate_layout.overflow:
            layout = candidate_layout
            break
        layout = candidate_layout

    if layout is None:
        layout = _build_panel_layout(draw, body, size, MIN_PANEL_FONT_SIZE)

    if layout.overflow:
        layout = _truncate_layout(draw, layout, size)

    for line in layout.lines:
        if line.bullet:
            dot_y = line.y + layout.font_size // 2 - layout.bullet_r
            draw.ellipse(
                [
                    (layout.mx + 7, dot_y),
                    (layout.mx + 7 + 2 * layout.bullet_r, dot_y + 2 * layout.bullet_r),
                ],
                fill=BULLET_DOT,
            )

        cx = line.x
        for span in line.spans:
            font = layout.bold_font if span.bold else layout.regular_font
            color = line.color_override or (BOLD_COLOR if span.bold else BODY_COLOR)
            draw.text((cx, line.y), span.text, fill=color, font=font)
            cx = draw.textbbox((cx, line.y), span.text, font=font)[2]

    return np.asarray(img, dtype=np.uint8)


# ── Video composition ────────────────────────────────────────────────────

def compose_annotated_video(
    video_path: str,
    segments: list[Segment],
    analyses: list[str],
    output_path: str,
    panel_width: int | None = None,
    font_size: int | None = None,
) -> None:
    """Create *output_path* = original video (left) + analysis panel (right)."""
    from moviepy import VideoFileClip, ImageClip, CompositeVideoClip

    video = VideoFileClip(video_path)
    vw, vh = video.size
    pw = panel_width or max(420, vw)
    canvas_w, canvas_h = vw + pw, vh

    if font_size is None:
        font_size = max(13, min(17, vh // 24))

    logger.info(
        "Composing annotated video (%dx%d, %d segments, font=%dpx) ...",
        canvas_w, canvas_h, len(segments), font_size,
    )

    bg = ImageClip(np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8))
    bg = bg.with_duration(video.duration)

    video_clip = video.with_position((0, 0))
    clips = [bg, video_clip]

    for i, (seg, text) in enumerate(zip(segments, analyses)):
        panel_img = _render_text_panel(text, (pw, canvas_h), font_size)

        start = seg.start_time
        end = video.duration if i == len(segments) - 1 else segments[i + 1].start_time

        clip = (
            ImageClip(panel_img)
            .with_start(start)
            .with_duration(end - start)
            .with_position((vw, 0))
        )
        clips.append(clip)

    final = CompositeVideoClip(clips, size=(canvas_w, canvas_h))
    final.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=video.fps,
        logger="bar",
    )

    video.close()
    final.close()
    logger.info("Annotated video saved to %s", output_path)
