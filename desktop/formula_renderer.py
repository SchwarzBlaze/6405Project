"""Utilities for rendering formulas into pixmaps."""

from __future__ import annotations

import io
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PIL import Image, ImageDraw, ImageFont

try:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    _HAS_MATPLOTLIB = True
except Exception:
    plt = None
    _HAS_MATPLOTLIB = False


def render_formula_pixmap(formula_text: str, max_width: int = 520) -> QPixmap | None:
    text = (formula_text or "").strip()
    if not text:
        return None

    normalized = _normalize_formula_for_mathtext(text)

    if _HAS_MATPLOTLIB:
        pixmap = _render_mathtext_pixmap(normalized, max_width=max_width)
        if pixmap is not None:
            return pixmap

    return _render_plain_text_pixmap(text, max_width=max_width)


def _normalize_formula_for_mathtext(text: str) -> str:
    normalized = str(text).strip()
    normalized = normalized.replace("\n", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.replace("（", "(").replace("）", ")")
    normalized = normalized.replace("，", ",")
    if normalized.startswith("$") and normalized.endswith("$"):
        return normalized
    return f"${normalized}$"


def _render_mathtext_pixmap(formula_text: str, max_width: int) -> QPixmap | None:
    for font_size in range(20, 9, -2):
        pixmap = _render_mathtext_once(formula_text, font_size)
        if pixmap is not None and pixmap.width() <= max_width:
            return pixmap

    return _render_mathtext_once(formula_text, 10)


def _render_mathtext_once(formula_text: str, font_size: int) -> QPixmap | None:
    try:
        fig = plt.figure(figsize=(0.01, 0.01), dpi=200)
        fig.patch.set_alpha(0)
        text_artist = fig.text(
            0.0,
            0.0,
            formula_text,
            fontsize=font_size,
            color="white",
        )
        fig.canvas.draw()
        bbox = text_artist.get_window_extent(renderer=fig.canvas.get_renderer()).expanded(
            1.08, 1.25
        )
        fig.set_size_inches(bbox.width / fig.dpi, bbox.height / fig.dpi)
        text_artist.set_position((0.03, 0.5))
        text_artist.set_verticalalignment("center")
        fig.canvas.draw()

        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=fig.dpi, transparent=True, bbox_inches="tight", pad_inches=0.04)
        buffer.seek(0)
        data = buffer.getvalue()
    except Exception:
        return None
    finally:
        try:
            plt.close(fig)
        except Exception:
            pass

    pixmap = QPixmap()
    if pixmap.loadFromData(data, "PNG"):
        return pixmap
    return None


def _render_plain_text_pixmap(text: str, max_width: int) -> QPixmap | None:
    lines = _wrap_plain_text(text, max_width=max_width)
    if not lines:
        return None

    font = _load_plain_font(20)
    line_spacing = 10
    widths = []
    for line in lines:
        bbox = font.getbbox(line or " ")
        widths.append(max(1, bbox[2] - bbox[0]))
    line_height = font.getbbox("Ag")[3] - font.getbbox("Ag")[1]

    width = min(max_width, max(widths) + 24)
    height = (line_height * len(lines)) + line_spacing * max(0, len(lines) - 1) + 20
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    y = 10
    for line in lines:
        draw.text((12, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_height + line_spacing

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    pixmap = QPixmap()
    if pixmap.loadFromData(buffer.getvalue(), "PNG"):
        return pixmap
    return None


def _wrap_plain_text(text: str, max_width: int) -> list[str]:
    font = _load_plain_font(20)
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1), (0, 0, 0, 0)))
    max_text_width = max(80, max_width - 24)

    wrapped: list[str] = []
    for paragraph in text.splitlines() or [text]:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        current = ""
        for char in paragraph:
            candidate = current + char
            if measure.textlength(candidate, font=font) <= max_text_width or not current:
                current = candidate
            else:
                wrapped.append(current)
                current = char
        if current:
            wrapped.append(current)
    return wrapped


def _load_plain_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/cambria.ttc",
        "C:/Windows/Fonts/cambria.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    return ImageFont.load_default()
