"""Small translation helpers for Study Lens."""

from __future__ import annotations

LANGUAGE_OPTIONS: list[tuple[str, str]] = [
    ("zh", "中文"),
    ("en", "English"),
]


def normalize_ui_language(language: str | None) -> str:
    text = (language or "").strip().lower()
    if text in {"en", "english"}:
        return "en"
    return "zh"


def model_output_language(language: str | None) -> str:
    return "English" if normalize_ui_language(language) == "en" else "Chinese"


_TEXTS: dict[str, dict[str, str]] = {
    "app_subtitle": {
        "zh": "桌面学习助手与讲座视频分析器",
        "en": "Desktop study assistant and lecture video analyzer",
    },
    "display_language": {
        "zh": "界面语言",
        "en": "Display language",
    },
    "ai_service_url": {
        "zh": "AI 服务地址",
        "en": "AI service URL",
    },
    "ai_service_placeholder": {
        "zh": "默认一般为 http://127.0.0.1:8080",
        "en": "Usually http://127.0.0.1:8080",
    },
    "server_hint": {
        "zh": "使用前请先启动本地 AI 服务。默认地址一般不用改，具体启动方式见 README。",
        "en": "Start the local AI service first. The default address usually does not need to be changed. See the README for startup steps.",
    },
    "output_dir": {
        "zh": "输出目录",
        "en": "Output directory",
    },
    "capture_settings": {
        "zh": "画面更新设置",
        "en": "Capture settings",
    },
    "detect_interval": {
        "zh": "检测间隔",
        "en": "Capture interval",
    },
    "trigger_threshold": {
        "zh": "触发阈值",
        "en": "Trigger threshold",
    },
    "threshold_hint": {
        "zh": "如果窗口滚动后没有及时触发分析，可以先把“触发阈值”调低，再把“检测间隔”调短。",
        "en": "If scrolling does not trigger analysis quickly enough, lower the trigger threshold first and then shorten the capture interval.",
    },
    "target_window": {
        "zh": "目标窗口",
        "en": "Target window",
    },
    "refresh_window_list": {
        "zh": "刷新窗口列表",
        "en": "Refresh window list",
    },
    "select_target_window": {
        "zh": "请选择目标窗口",
        "en": "Select a target window",
    },
    "browse": {
        "zh": "浏览",
        "en": "Browse",
    },
    "start_desktop": {
        "zh": "启动桌面学习模式",
        "en": "Start desktop study mode",
    },
    "analyze_video": {
        "zh": "选择讲座视频分析",
        "en": "Analyze a lecture video",
    },
    "stop_task": {
        "zh": "停止当前任务",
        "en": "Stop current task",
    },
    "ready": {
        "zh": "就绪",
        "en": "Ready",
    },
    "current_analysis_frame": {
        "zh": "当前分析画面",
        "en": "Current analysis frame",
    },
    "latest_analysis_and_logs": {
        "zh": "最新分析 / 运行日志",
        "en": "Latest analysis / logs",
    },
    "not_started": {
        "zh": "尚未开始分析",
        "en": "Analysis has not started yet",
    },
    "no_capture": {
        "zh": "暂无截图",
        "en": "No screenshot yet",
    },
    "choose_target_window_message": {
        "zh": "请先选择一个要分析的目标窗口。",
        "en": "Please choose a target window first.",
    },
    "desktop_mode_started": {
        "zh": "桌面学习模式已启动。",
        "en": "Desktop study mode started.",
    },
    "current_window": {
        "zh": "当前窗口",
        "en": "Current window",
    },
    "service_url_log": {
        "zh": "AI 服务地址",
        "en": "AI service URL",
    },
    "capture_settings_log": {
        "zh": "检测间隔: {interval:.2f}s，触发阈值: {threshold:.2f}",
        "en": "Capture interval: {interval:.2f}s, trigger threshold: {threshold:.2f}",
    },
    "busy_start_desktop": {
        "zh": "正在启动桌面学习模式（{title}）...",
        "en": "Starting desktop study mode ({title})...",
    },
    "desktop_subtitle_started": {
        "zh": "桌面学习模式已启动",
        "en": "Desktop study mode started",
    },
    "desktop_subtitle_target": {
        "zh": "目标窗口：{title}",
        "en": "Target window: {title}",
    },
    "desktop_subtitle_summary": {
        "zh": "程序会读取这个窗口的画面，并自动生成学习辅助分析。",
        "en": "Study Lens will capture this window and generate learning assistance automatically.",
    },
    "select_video_dialog": {
        "zh": "选择讲座视频",
        "en": "Choose a lecture video",
    },
    "video_file_filter": {
        "zh": "视频文件 (*.mp4 *.avi *.mkv *.mov *.flv *.wmv);;所有文件 (*)",
        "en": "Video files (*.mp4 *.avi *.mkv *.mov *.flv *.wmv);;All files (*)",
    },
    "video_started": {
        "zh": "开始分析视频: {path}",
        "en": "Started analyzing video: {path}",
    },
    "video_output_dir": {
        "zh": "输出目录: {path}",
        "en": "Output directory: {path}",
    },
    "busy_video": {
        "zh": "讲座视频分析中...",
        "en": "Analyzing lecture video...",
    },
    "stale_result_dropped": {
        "zh": "已丢弃过期结果：第 {index} 张截图的分析晚于新截图返回。",
        "en": "Dropped an outdated result: capture {index} finished after a newer capture.",
    },
    "preview_missing": {
        "zh": "未找到当前截图文件",
        "en": "Current screenshot file was not found",
    },
    "preview_load_failed": {
        "zh": "截图预览加载失败",
        "en": "Failed to load screenshot preview",
    },
    "unknown": {
        "zh": "未知",
        "en": "Unknown",
    },
    "analysis_resolution": {
        "zh": "分析分辨率: {width} x {height}",
        "en": "Analysis resolution: {width} x {height}",
    },
    "analysis_resolution_with_source": {
        "zh": "分析分辨率: {width} x {height}（原始画面: {source_width} x {source_height}）",
        "en": "Analysis resolution: {width} x {height} (source: {source_width} x {source_height})",
    },
    "meta_current_window": {
        "zh": "当前窗口: {title}",
        "en": "Current window: {title}",
    },
    "meta_capture_index": {
        "zh": "截图编号: {index}",
        "en": "Capture index: {index}",
    },
    "meta_capture_interval": {
        "zh": "检测间隔: {value:.2f}s",
        "en": "Capture interval: {value:.2f}s",
    },
    "meta_capture_interval_unknown": {
        "zh": "检测间隔: 未知",
        "en": "Capture interval: Unknown",
    },
    "meta_trigger_threshold": {
        "zh": "触发阈值: {value:.2f}",
        "en": "Trigger threshold: {value:.2f}",
    },
    "meta_trigger_threshold_unknown": {
        "zh": "触发阈值: 未知",
        "en": "Trigger threshold: Unknown",
    },
    "meta_screen_change": {
        "zh": "画面变化程度: {value:.2f}",
        "en": "Screen change score: {value:.2f}",
    },
    "meta_first_capture": {
        "zh": "画面变化程度: 首次捕获",
        "en": "Screen change score: first capture",
    },
    "meta_captured_at": {
        "zh": "截图时间: {value}",
        "en": "Captured at: {value}",
    },
    "meta_analysis_started_at": {
        "zh": "开始分析: {value}",
        "en": "Analysis started: {value}",
    },
    "meta_processing_delay": {
        "zh": "处理延迟: {value}",
        "en": "Processing delay: {value}",
    },
    "new_page_captured": {
        "zh": "已捕获新页面，正在分析新内容...",
        "en": "A new page was captured. Analyzing the new content...",
    },
    "analyzing_current_frame": {
        "zh": "正在分析当前画面",
        "en": "Analyzing the current frame",
    },
    "processing_frame_log": {
        "zh": "正在分析第 {index} 张画面，窗口：{title}，画面变化程度：{change}，处理延迟：{delay}",
        "en": "Analyzing frame {index}, window: {title}, change score: {change}, processing delay: {delay}",
    },
    "video_completed": {
        "zh": "视频分析完成: {title}",
        "en": "Video analysis completed: {title}",
    },
    "segment_count": {
        "zh": "片段数: {count}",
        "en": "Segments: {count}",
    },
    "report_path": {
        "zh": "报告: {path}",
        "en": "Report: {path}",
    },
    "output_video_path": {
        "zh": "视频: {path}",
        "en": "Video: {path}",
    },
    "video_completed_status": {
        "zh": "视频分析完成",
        "en": "Video analysis completed",
    },
    "task_failed": {
        "zh": "任务失败",
        "en": "Task failed",
    },
    "error_prefix": {
        "zh": "[错误] {message}",
        "en": "[Error] {message}",
    },
    "stopped_status": {
        "zh": "已停止",
        "en": "Stopped",
    },
    "subtitle_waiting": {
        "zh": "Study Lens 已启动，等待新画面...",
        "en": "Study Lens is ready and waiting for a new frame...",
    },
    "next_step_prefix": {
        "zh": "下一步：",
        "en": "Next:",
    },
    "detail_bullet_prefix": {
        "zh": "• ",
        "en": "• ",
    },
    "service_connecting": {
        "zh": "正在连接 AI 服务...",
        "en": "Connecting to the AI service...",
    },
    "desktop_waiting_for_change": {
        "zh": "桌面学习模式运行中，等待窗口内容变化...",
        "en": "Desktop study mode is running and waiting for content changes...",
    },
    "desktop_analysis_failed_prefix": {
        "zh": "桌面分析失败: {message}",
        "en": "Desktop analysis failed: {message}",
    },
    "video_analysis_stopped": {
        "zh": "视频分析已停止。",
        "en": "Video analysis stopped.",
    },
    "reading_video_info": {
        "zh": "读取视频信息...",
        "en": "Reading video information...",
    },
    "connecting_ai": {
        "zh": "连接 AI 服务...",
        "en": "Connecting to the AI service...",
    },
    "extracting_frames": {
        "zh": "抽帧中（{fps:.1f} fps）...",
        "en": "Extracting frames ({fps:.1f} fps)...",
    },
    "no_frames_extracted": {
        "zh": "未能从视频中提取到画面。",
        "en": "No frames could be extracted from the video.",
    },
    "recognizing_video_type": {
        "zh": "识别视频类型...",
        "en": "Recognizing the video type...",
    },
    "video_type": {
        "zh": "视频类型: {value}",
        "en": "Video type: {value}",
    },
    "splitting_video_segments": {
        "zh": "切分讲座片段...",
        "en": "Splitting the lecture into segments...",
    },
    "transcribing_audio": {
        "zh": "提取并转录音频...",
        "en": "Extracting and transcribing audio...",
    },
    "analyzing_segment": {
        "zh": "分析片段 {index}/{total} ({start:.1f}s - {end:.1f}s)",
        "en": "Analyzing segment {index}/{total} ({start:.1f}s - {end:.1f}s)",
    },
    "generating_summary": {
        "zh": "生成整体总结...",
        "en": "Generating the overall summary...",
    },
    "writing_report": {
        "zh": "写出 Markdown 报告...",
        "en": "Writing the Markdown report...",
    },
    "composing_video": {
        "zh": "合成注释视频...",
        "en": "Composing the annotated video...",
    },
    "report_title": {
        "zh": "# 讲座分析报告\n",
        "en": "# Lecture Analysis Report\n",
    },
    "report_video": {
        "zh": "**视频**: {name}  ",
        "en": "**Video**: {name}  ",
    },
    "report_duration": {
        "zh": "**时长**: {value}  ",
        "en": "**Duration**: {value}  ",
    },
    "report_resolution": {
        "zh": "**分辨率**: {value}  ",
        "en": "**Resolution**: {value}  ",
    },
    "report_type": {
        "zh": "**类型**: {value}  ",
        "en": "**Type**: {value}  ",
    },
    "report_segments": {
        "zh": "**检测到的{label}数**: {count}  ",
        "en": "**Detected {label}s**: {count}  ",
    },
    "report_generated": {
        "zh": "**生成时间**: {value}  ",
        "en": "**Generated**: {value}  ",
    },
    "report_slide_label": {
        "zh": "页",
        "en": "Slide",
    },
    "report_segment_label": {
        "zh": "片段",
        "en": "Segment",
    },
    "report_section": {
        "zh": "## {label} {index} ({start} – {end})\n",
        "en": "## {label} {index} ({start} – {end})\n",
    },
    "report_summary_heading": {
        "zh": "## 整体总结\n",
        "en": "## Overall Summary\n",
    },
    "report_transcript_heading": {
        "zh": "## 音频转录\n",
        "en": "## Audio Transcript\n",
    },
    "report_transcript_saved": {
        "zh": "完整转录已保存到 [{name}]({rel})\n",
        "en": "Full transcript saved to [{name}]({rel})\n",
    },
    "truncation_notice": {
        "zh": "内容较多，已省略后续。",
        "en": "More content exists below and has been omitted.",
    },
}


def tr(language: str | None, key: str, **kwargs) -> str:
    code = normalize_ui_language(language)
    mapping = _TEXTS.get(key)
    if not mapping:
        return key
    text = mapping.get(code) or mapping.get("zh") or mapping.get("en") or key
    if kwargs:
        return text.format(**kwargs)
    return text
