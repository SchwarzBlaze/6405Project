"""Lecture-video analysis pipeline adapted from lecture-lens."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from video_core.analyzer import (
    LectureContext,
    VideoType,
    analyze_segment,
    classify_video_type,
    generate_summary,
    get_defaults_for_type,
)
from video_core.audio import extract_audio, get_transcript_for_range, transcribe
from video_core.model import load_model
from video_core.report import generate_report
from video_core.slide_detector import adaptive_detect, extract_frames, get_video_info, time_based_segments
from video_core.video_composer import compose_annotated_video

LogFn = Callable[[str], None] | None
StopFn = Callable[[], bool] | None


def run_video_analysis(
    video_path: str,
    output_dir: str,
    server_url: str,
    mode: str = "auto",
    fps: float = 1.0,
    threshold: float | None = None,
    min_duration: float | None = None,
    max_tokens: int = 1024,
    language: str | None = "Chinese",
    use_audio: bool = False,
    whisper_model: str = "base",
    log_callback: LogFn = None,
    should_stop: StopFn = None,
) -> dict:
    video_path = os.path.abspath(video_path)
    output_dir = os.path.abspath(output_dir)
    frames_dir = os.path.join(output_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    def log(message: str) -> None:
        if log_callback:
            log_callback(message)

    def stopped() -> bool:
        return should_stop() if should_stop else False

    def guard() -> None:
        if stopped():
            raise InterruptedError("Video analysis stopped by user.")

    if not os.path.isfile(video_path):
        raise FileNotFoundError(video_path)

    log("读取视频信息...")
    vinfo = get_video_info(video_path)
    guard()

    log("连接 llama.cpp 服务...")
    model, processor = load_model(server_url=server_url)
    guard()

    log(f"抽帧中（{fps:.1f} fps）...")
    frames, timestamps = extract_frames(video_path, fps=fps)
    if not frames:
        raise RuntimeError("No frames could be extracted from the video.")
    guard()

    frame_paths: list[str] = []
    for idx, frame in enumerate(frames):
        frame_path = os.path.join(frames_dir, f"frame_{idx:05d}.png")
        frame.save(frame_path)
        frame_paths.append(os.path.abspath(frame_path))
    guard()

    if mode == "auto":
        log("识别视频类型...")
        video_type = classify_video_type(model, processor, frame_paths)
    else:
        video_type = VideoType(mode.upper())
    log(f"视频类型: {video_type.value}")
    guard()

    defaults = get_defaults_for_type(video_type)
    threshold = threshold if threshold is not None else defaults["threshold"]
    min_duration = min_duration if min_duration is not None else defaults["min_duration"]
    representative = defaults["representative"]

    log("切分讲座片段...")
    if video_type == VideoType.TEACHER_ONLY:
        segments = time_based_segments(frames, timestamps, interval=30.0)
    else:
        segments = adaptive_detect(
            frames,
            timestamps,
            initial_threshold=threshold,
            min_duration=min_duration,
            representative=representative,
        )
    guard()

    for seg in segments:
        seg_path = os.path.join(frames_dir, f"slide_{seg.index:04d}.png")
        seg.representative_frame.save(seg_path)
        seg.frame_path = os.path.abspath(seg_path)

    transcription: list[dict] | None = None
    full_transcript: str | None = None

    if use_audio and vinfo["has_audio"]:
        log("提取并转录音频...")
        audio_path = os.path.join(output_dir, "audio.wav")
        extract_audio(video_path, audio_path)
        transcription = transcribe(audio_path, model_size=whisper_model)
        full_transcript = " ".join(segment["text"] for segment in transcription)
        guard()

    analyses: list[str] = []
    context = LectureContext(max_entries=10)

    for idx, seg in enumerate(segments):
        guard()
        log(f"分析片段 {idx + 1}/{len(segments)} ({seg.start_time:.1f}s - {seg.end_time:.1f}s)")
        audio_text = None
        if transcription:
            audio_text = get_transcript_for_range(
                transcription,
                seg.start_time,
                seg.end_time,
            ) or None

        prev_frame = segments[idx - 1].frame_path if idx > 0 else None
        analysis = analyze_segment(
            model,
            processor,
            seg,
            context,
            video_type,
            total_segments=len(segments),
            audio_text=audio_text,
            prev_frame_path=prev_frame,
            max_tokens=max_tokens,
            language=language,
        )
        analyses.append(analysis)
        context.add(seg.index, LectureContext.extract_summary(analysis))

    guard()
    log("生成整体总结...")
    summary = generate_summary(model, processor, analyses, max_tokens=max_tokens)

    log("写出 Markdown 报告...")
    report_path = generate_report(
        video_path,
        vinfo,
        video_type,
        segments,
        analyses,
        summary,
        output_dir,
        transcript_text=full_transcript,
    )
    guard()

    log("合成注释视频...")
    output_video = os.path.join(output_dir, "annotated_video.mp4")
    compose_annotated_video(video_path, segments, analyses, output_video)

    return {
        "video_path": video_path,
        "output_dir": output_dir,
        "report_path": report_path,
        "output_video": output_video,
        "segments": len(segments),
        "video_type": video_type.value,
        "title": Path(video_path).name,
    }
