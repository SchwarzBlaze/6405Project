"""Markdown report generation for lecture analysis results."""

from __future__ import annotations

import logging
import os
from datetime import datetime

from app_i18n import model_output_language, tr
from .analyzer import VideoType
from .slide_detector import Segment

logger = logging.getLogger(__name__)


def format_timestamp(seconds: float) -> str:
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def _segment_label(video_type: VideoType, language: str) -> str:
    key = "report_slide_label" if video_type in (VideoType.SLIDES, VideoType.SCREEN_RECORDING) else "report_segment_label"
    return tr("en" if model_output_language(language) == "English" else "zh", key)


def generate_report(
    video_path: str,
    video_info: dict,
    video_type: VideoType,
    segments: list[Segment],
    analyses: list[str],
    summary: str | None,
    output_dir: str,
    transcript_text: str | None = None,
    language: str | None = "Chinese",
) -> str:
    """Write a Markdown report to *output_dir*/report.md and return its path."""
    ui_language = "en" if model_output_language(language) == "English" else "zh"
    label = _segment_label(video_type, language or "Chinese")
    lines: list[str] = []

    lines.append(tr(ui_language, "report_title"))
    lines.append(tr(ui_language, "report_video", name=os.path.basename(video_path)))
    lines.append(tr(ui_language, "report_duration", value=format_timestamp(video_info.get("duration", 0))))
    lines.append(
        tr(
            ui_language,
            "report_resolution",
            value=f"{video_info.get('width', '?')}x{video_info.get('height', '?')}",
        )
    )
    lines.append(tr(ui_language, "report_type", value=video_type.value))
    lines.append(tr(ui_language, "report_segments", label=label, count=len(segments)))
    lines.append(tr(ui_language, "report_generated", value=datetime.now().strftime("%Y-%m-%d %H:%M")))
    lines.append("")

    for seg, analysis in zip(segments, analyses):
        lines.append("---\n")
        lines.append(
            tr(
                ui_language,
                "report_section",
                label=label,
                index=seg.index + 1,
                start=format_timestamp(seg.start_time),
                end=format_timestamp(seg.end_time),
            )
        )
        if seg.frame_path:
            rel = os.path.relpath(seg.frame_path, output_dir)
            lines.append(f"![{label} {seg.index + 1}]({rel})\n")
        lines.append(analysis)
        lines.append("")

    if summary:
        lines.append("---\n")
        lines.append(tr(ui_language, "report_summary_heading"))
        lines.append(summary)
        lines.append("")

    if transcript_text:
        transcript_path = os.path.join(output_dir, "transcript.txt")
        with open(transcript_path, "w", encoding="utf-8") as handle:
            handle.write(transcript_text)
        lines.append("---\n")
        lines.append(tr(ui_language, "report_transcript_heading"))
        lines.append(
            tr(
                ui_language,
                "report_transcript_saved",
                name=os.path.basename(transcript_path),
                rel=os.path.relpath(transcript_path, output_dir),
            )
        )

    report_path = os.path.join(output_dir, "report.md")
    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))

    logger.info("Report written to %s", report_path)
    return report_path
