"""Compose an output video with the original lecture on the left and a
synchronised analysis text panel on the right.

The panel renders rich text with **bold** emphasis, bullet points, and clean
typography using Noto Sans CJK with a fresh teal design language.
"""

from __future__ import annotations

import logging
import os
import re
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

# ── Font loading ──────────────────────────────────────────────────────────

_FONT_PAIRS = [
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
     "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]


def _load_fonts(size: int):
    """Return (title_font, bold_font, regular_font)."""
    for reg, bold in _FONT_PAIRS:
        if os.path.isfile(reg) and os.path.isfile(bold):
            try:
                return (
                    ImageFont.truetype(bold, size + 5),
                    ImageFont.truetype(bold, size),
                    ImageFont.truetype(reg, size),
                )
            except OSError:
                continue
    d = ImageFont.load_default()
    return d, d, d


# ── Rich-text helpers ─────────────────────────────────────────────────────

class _Span(NamedTuple):
    text: str
    bold: bool


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


def _wrap_px(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    """Word-wrap *text* to fit *max_w* pixels, with character-level fallback
    for long words (handles CJK text without spaces)."""
    if not text or not text.strip():
        return [""]

    words = text.split(" ")
    lines: list[str] = []
    cur = words[0]

    for word in words[1:]:
        trial = cur + " " + word
        if _text_width(draw, trial, font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
            if _text_width(draw, word, font) > max_w:
                broken = _break_chars(draw, word, font, max_w)
                lines.extend(broken[:-1])
                cur = broken[-1]
    if cur:
        lines.append(cur)
    return lines or [""]


def _break_chars(draw: ImageDraw.ImageDraw, word: str, font, max_w: int) -> list[str]:
    """Break a single token at character boundaries to fit *max_w*."""
    lines: list[str] = []
    buf = ""
    for ch in word:
        trial = buf + ch
        if _text_width(draw, trial, font) > max_w and buf:
            lines.append(buf)
            buf = ch
        else:
            buf = trial
    if buf:
        lines.append(buf)
    return lines or [""]


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


def _render_text_panel(
    body: str,
    size: tuple[int, int],
    font_size: int = 15,
) -> np.ndarray:
    w, h = size
    img = Image.new("RGB", (w, h), color=BG_COLOR)
    draw = ImageDraw.Draw(img)
    _ft_title, ft_bold, ft_reg = _load_fonts(font_size)

    mx = 28
    bottom_margin = 16
    line_gap = int(font_size * 0.42)
    section_gap = int(font_size * 0.7)
    bullet_indent = 24
    bullet_r = 3

    y = 20

    # ── body content (no title — content speaks for itself) ──
    for raw_line in body.split("\n"):
        if y >= h - bottom_margin:
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

        wrapped = _wrap_px(draw, content, ft_bold, avail_w)

        for li, wl in enumerate(wrapped):
            if y >= h - bottom_margin:
                break

            if (is_bullet or is_label) and li == 0:
                dot_y = y + font_size // 2 - bullet_r
                draw.ellipse(
                    [(mx + 7, dot_y),
                     (mx + 7 + 2 * bullet_r, dot_y + 2 * bullet_r)],
                    fill=BULLET_DOT,
                )

            cx = text_x
            max_bottom = y
            for sp in _parse_spans(wl):
                ft = ft_bold if sp.bold else ft_reg
                color = BOLD_COLOR if sp.bold else BODY_COLOR
                draw.text((cx, y), sp.text, fill=color, font=ft)
                bb = draw.textbbox((cx, y), sp.text, font=ft)
                cx = bb[2]
                max_bottom = max(max_bottom, bb[3])

            y = max_bottom + line_gap

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
