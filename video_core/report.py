"""Markdown report generation for lecture analysis results."""

from __future__ import annotations

import logging
import os
from datetime import datetime

from .analyzer import VideoType
from .slide_detector import Segment

logger = logging.getLogger(__name__)


def format_timestamp(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _segment_label(video_type: VideoType) -> str:
    if video_type in (VideoType.SLIDES, VideoType.SCREEN_RECORDING):
        return "Slide"
    return "Segment"


def generate_report(
    video_path: str,
    video_info: dict,
    video_type: VideoType,
    segments: list[Segment],
    analyses: list[str],
    summary: str | None,
    output_dir: str,
    transcript_text: str | None = None,
) -> str:
    """Write a Markdown report to *output_dir*/report.md and return its path."""
    label = _segment_label(video_type)
    lines: list[str] = []

    # --- header ---------------------------------------------------------
    lines.append("# Lecture Analysis Report\n")
    lines.append(f"**Video**: {os.path.basename(video_path)}  ")
    lines.append(f"**Duration**: {format_timestamp(video_info.get('duration', 0))}  ")
    lines.append(f"**Resolution**: {video_info.get('width', '?')}x{video_info.get('height', '?')}  ")
    lines.append(f"**Type**: {video_type.value}  ")
    lines.append(f"**{label}s detected**: {len(segments)}  ")
    lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}  ")
    lines.append("")

    # --- per-segment analysis -------------------------------------------
    for seg, analysis in zip(segments, analyses):
        lines.append("---\n")
        lines.append(
            f"## {label} {seg.index + 1} "
            f"({format_timestamp(seg.start_time)} \u2013 {format_timestamp(seg.end_time)})\n"
        )
        if seg.frame_path:
            rel = os.path.relpath(seg.frame_path, output_dir)
            lines.append(f"![{label} {seg.index + 1}]({rel})\n")
        lines.append(analysis)
        lines.append("")

    # --- overall summary ------------------------------------------------
    if summary:
        lines.append("---\n")
        lines.append("## Overall Summary\n")
        lines.append(summary)
        lines.append("")

    # --- transcript (link only) -----------------------------------------
    if transcript_text:
        transcript_path = os.path.join(output_dir, "transcript.txt")
        with open(transcript_path, "w", encoding="utf-8") as fh:
            fh.write(transcript_text)
        lines.append("---\n")
        lines.append("## Audio Transcript\n")
        lines.append(f"Full transcript saved to [{os.path.basename(transcript_path)}]"
                      f"({os.path.relpath(transcript_path, output_dir)})\n")

    report_path = os.path.join(output_dir, "report.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    logger.info("Report written to %s", report_path)
    return report_path
