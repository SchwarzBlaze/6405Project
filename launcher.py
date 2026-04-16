"""Unified launcher for desktop study mode and lecture-video mode."""

from __future__ import annotations

import os
import queue
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from analysis.desktop_inference import DesktopInferenceThread
from analysis.video_worker import VideoAnalysisWorker
from desktop.capture import CaptureSettings, CaptureThread
from desktop.subtitle import SubtitleBar
from desktop.windows import CAPTURE_BACKEND_WGC, WindowDescriptor, is_window_alive, list_windows

DEFAULT_SERVER_URL = "http://127.0.0.1:8080"

WINDOW_STYLE = """
    QWidget#launcher {
        background-color: #1e1e2e;
    }
    QLabel {
        color: #cdd6f4;
    }
    QLineEdit, QTextEdit, QComboBox, QDoubleSpinBox {
        background-color: #11111b;
        color: #cdd6f4;
        border: 1px solid #45475a;
        border-radius: 8px;
        padding: 8px;
    }
    QPushButton {
        background-color: #313244;
        color: #cdd6f4;
        border: 1px solid #45475a;
        border-radius: 8px;
        padding: 10px 18px;
        font-size: 14px;
    }
    QPushButton:hover {
        background-color: #45475a;
    }
    QPushButton:disabled {
        background-color: #1e1e2e;
        color: #585b70;
        border-color: #313244;
    }
    QPushButton#primary {
        background-color: #89b4fa;
        color: #1e1e2e;
        border: none;
        font-weight: bold;
    }
    QPushButton#primary:hover {
        background-color: #74c7ec;
    }
    QPushButton#danger {
        background-color: #f38ba8;
        color: #1e1e2e;
        border: none;
    }
"""

CAPTURE_BACKEND_LABEL = "Windows Graphics Capture"


class Launcher(QWidget):
    """Single-window launcher that combines desktop and video modes."""

    def __init__(self):
        super().__init__()
        self.setObjectName("launcher")
        self.setWindowTitle("Study Lens Integrated")
        self.setMinimumSize(980, 800)
        self.setStyleSheet(WINDOW_STYLE)

        self._frame_queue = queue.Queue(maxsize=1)
        self._subtitle = SubtitleBar()
        self._subtitle.hide()

        self._capture_thread: CaptureThread | None = None
        self._desktop_thread: DesktopInferenceThread | None = None
        self._video_thread: VideoAnalysisWorker | None = None
        self._current_preview_path: str | None = None
        self._window_options: dict[int, WindowDescriptor] = {}
        self._active_target: WindowDescriptor | None = None

        self._build_ui()
        self._refresh_window_options()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 22, 24, 22)

        title = QLabel("Study Lens Integrated")
        title.setFont(QFont("Microsoft YaHei", 22, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("桌面学习助手 + 讲座视频分析器（统一 llama.cpp 后端）")
        subtitle.setFont(QFont("Microsoft YaHei", 11))
        subtitle.setStyleSheet("color: #a6adc8;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addWidget(
            self._row_with_input(
                "llama.cpp 服务地址",
                DEFAULT_SERVER_URL,
                field_name="server_url",
                placeholder="例如 http://127.0.0.1:8080 或 http://127.0.0.1:8080/v1/chat/completions",
            )
        )

        server_hint = QLabel(
            "推荐启动命令：`llama-server -hf ggml-org/gemma-4-E2B-it-GGUF --reasoning off`"
        )
        server_hint.setWordWrap(True)
        server_hint.setStyleSheet("color: #a6adc8;")
        layout.addWidget(server_hint)

        layout.addWidget(
            self._row_with_browse(
                "输出目录",
                os.path.abspath("./output"),
                field_name="output",
            )
        )
        layout.addWidget(self._capture_settings_row())
        layout.addWidget(self._window_selector_row())

        button_row = QHBoxLayout()
        button_row.setSpacing(10)

        self._btn_desktop = QPushButton("启动桌面学习模式")
        self._btn_desktop.setObjectName("primary")
        self._btn_desktop.clicked.connect(self._start_desktop_mode)
        button_row.addWidget(self._btn_desktop)

        self._btn_video = QPushButton("选择讲座视频分析")
        self._btn_video.clicked.connect(self._start_video_mode)
        button_row.addWidget(self._btn_video)

        self._btn_stop = QPushButton("停止当前任务")
        self._btn_stop.setObjectName("danger")
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._stop_all)
        button_row.addWidget(self._btn_stop)

        layout.addLayout(button_row)

        self._status = QLabel("就绪")
        self._status.setFont(QFont("Microsoft YaHei", 10))
        self._status.setStyleSheet("color: #a6adc8;")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status)

        content_row = QHBoxLayout()
        content_row.setSpacing(14)

        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(8)

        preview_title = QLabel("调试预览：当前送进模型分析的截图")
        preview_title.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        preview_layout.addWidget(preview_title)

        self._preview_meta = QLabel("尚未开始分析")
        self._preview_meta.setWordWrap(True)
        self._preview_meta.setStyleSheet("color: #a6adc8;")
        preview_layout.addWidget(self._preview_meta)

        self._preview_image = QLabel("暂无截图")
        self._preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_image.setMinimumSize(360, 220)
        self._preview_image.setStyleSheet(
            "background-color: #11111b; border: 1px solid #45475a; border-radius: 8px; color: #6c7086;"
        )
        preview_layout.addWidget(self._preview_image, 1)

        self._preview_hint = QLabel(
            "当前固定使用 Windows Graphics Capture 按目标窗口抓取，不再自动回退到区域截屏。"
        )
        self._preview_hint.setWordWrap(True)
        self._preview_hint.setStyleSheet("color: #a6adc8;")
        preview_layout.addWidget(self._preview_hint)

        content_row.addWidget(preview_panel, 1)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        log_title = QLabel("最新分析 / 运行日志")
        log_title.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        right_layout.addWidget(log_title)

        self._details = QTextEdit()
        self._details.setReadOnly(True)
        self._details.setFont(QFont("Consolas", 11))
        right_layout.addWidget(self._details, 1)

        content_row.addWidget(right_panel, 1)
        layout.addLayout(content_row, 1)

    def _row_with_browse(self, label_text: str, default_text: str, field_name: str) -> QWidget:
        container = QWidget()
        row = QVBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        label = QLabel(label_text)
        row.addWidget(label)

        inner = QHBoxLayout()
        inner.setContentsMargins(0, 0, 0, 0)

        line_edit = QLineEdit(default_text)
        browse_btn = QPushButton("浏览")
        browse_btn.clicked.connect(lambda: self._browse_dir(line_edit))

        if field_name == "output":
            self._output_dir_edit = line_edit
        else:
            raise ValueError(f"Unexpected field_name: {field_name}")

        inner.addWidget(line_edit, 1)
        inner.addWidget(browse_btn)
        row.addLayout(inner)
        return container

    def _row_with_input(
        self,
        label_text: str,
        default_text: str,
        field_name: str,
        placeholder: str = "",
    ) -> QWidget:
        container = QWidget()
        row = QVBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        label = QLabel(label_text)
        row.addWidget(label)

        line_edit = QLineEdit(default_text)
        if placeholder:
            line_edit.setPlaceholderText(placeholder)
        row.addWidget(line_edit)

        if field_name == "server_url":
            self._server_url_edit = line_edit
        else:
            raise ValueError(f"Unexpected field_name: {field_name}")

        return container

    def _capture_settings_row(self) -> QWidget:
        container = QWidget()
        row = QVBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        label = QLabel("采集参数")
        row.addWidget(label)

        inner = QHBoxLayout()
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(10)

        backend_label = QLabel(CAPTURE_BACKEND_LABEL)
        backend_label.setStyleSheet(
            "background-color: #11111b; border: 1px solid #45475a; border-radius: 8px; padding: 8px;"
        )
        inner.addWidget(self._labeled_widget("采集后端", backend_label), 2)

        self._interval_spin = QDoubleSpinBox()
        self._interval_spin.setRange(0.05, 5.00)
        self._interval_spin.setSingleStep(0.05)
        self._interval_spin.setSuffix(" s")
        self._interval_spin.setValue(0.20)
        inner.addWidget(self._labeled_widget("采集间隔", self._interval_spin), 1)

        self._threshold_spin = QDoubleSpinBox()
        self._threshold_spin.setRange(0.2, 50.0)
        self._threshold_spin.setSingleStep(0.2)
        self._threshold_spin.setValue(3.0)
        inner.addWidget(self._labeled_widget("触发阈值", self._threshold_spin), 1)

        row.addLayout(inner)

        hint = QLabel(
            "阈值越小越敏感；在 VS Code 里滚轮轻微滚动不触发时，优先把阈值调低到 0.8~2.0，"
            "并把采集间隔调低到 0.10~0.20s。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #a6adc8;")
        row.addWidget(hint)

        return container

    def _labeled_widget(self, text: str, widget: QWidget) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label = QLabel(text)
        layout.addWidget(label)
        layout.addWidget(widget)
        return container

    def _window_selector_row(self) -> QWidget:
        container = QWidget()
        row = QVBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        label = QLabel("目标窗口")
        row.addWidget(label)

        inner = QHBoxLayout()
        inner.setContentsMargins(0, 0, 0, 0)

        self._window_combo = QComboBox()
        refresh_btn = QPushButton("刷新窗口列表")
        refresh_btn.clicked.connect(self._refresh_window_options)

        inner.addWidget(self._window_combo, 1)
        inner.addWidget(refresh_btn)
        row.addLayout(inner)
        return container

    def _browse_dir(self, line_edit: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, "选择目录", line_edit.text() or os.getcwd())
        if path:
            line_edit.setText(path)

    def _append_log(self, message: str):
        self._details.append(message)

    def _refresh_window_options(self):
        previous = self._window_combo.currentData() if hasattr(self, "_window_combo") else None
        windows = list_windows(excluded_hwnds=self._excluded_hwnds())
        self._window_options = {item.hwnd: item for item in windows}

        self._window_combo.blockSignals(True)
        self._window_combo.clear()
        self._window_combo.addItem("请选择目标窗口", None)
        for item in windows:
            self._window_combo.addItem(f"{item.title}  [HWND {item.hwnd}]", item.hwnd)

        if previous in self._window_options:
            index = self._window_combo.findData(previous)
            if index >= 0:
                self._window_combo.setCurrentIndex(index)
        self._window_combo.blockSignals(False)

    def _excluded_hwnds(self) -> set[int]:
        excluded: set[int] = set()
        for widget in (self, self._subtitle):
            try:
                hwnd = int(widget.winId())
            except Exception:
                hwnd = 0
            if hwnd:
                excluded.add(hwnd)
        return excluded

    def _selected_target_window(self) -> WindowDescriptor | None:
        hwnd = self._window_combo.currentData()
        if hwnd is None:
            return None
        return self._window_options.get(int(hwnd))

    def _active_target_provider(self) -> WindowDescriptor | None:
        if self._active_target and is_window_alive(self._active_target.hwnd):
            return self._active_target
        return None

    def _server_url(self) -> str:
        text = self._server_url_edit.text().strip()
        if not text:
            text = DEFAULT_SERVER_URL
            self._server_url_edit.setText(text)
        return text

    def _output_dir(self) -> str:
        text = self._output_dir_edit.text().strip()
        if not text:
            text = os.path.abspath("./output")
            self._output_dir_edit.setText(text)
        os.makedirs(text, exist_ok=True)
        return text

    def _capture_settings(self) -> CaptureSettings:
        return CaptureSettings(
            interval_seconds=float(self._interval_spin.value()),
            change_threshold=float(self._threshold_spin.value()),
        )

    def _set_busy(self, status: str):
        self._status.setText(status)
        self._btn_desktop.setEnabled(False)
        self._btn_video.setEnabled(False)
        self._btn_stop.setEnabled(True)

    def _set_idle(self, status: str = "就绪"):
        self._status.setText(status)
        self._btn_desktop.setEnabled(True)
        self._btn_video.setEnabled(True)
        self._btn_stop.setEnabled(False)

    @Slot()
    def _start_desktop_mode(self):
        self._stop_all()
        target = self._selected_target_window()
        if not target:
            QMessageBox.information(self, "Study Lens", "请先选择一个要分析的目标窗口。")
            return

        settings = self._capture_settings()
        self._details.clear()
        self._append_log("桌面学习模式已启动。")
        self._append_log(f"目标窗口: {target.title} [HWND {target.hwnd}]")
        self._append_log(f"桌面后端: llama.cpp server @ {self._server_url()}")
        self._append_log(
            f"采集参数: backend={CAPTURE_BACKEND_LABEL}, interval={settings.interval_seconds:.2f}s, "
            f"threshold={settings.change_threshold:.2f}"
        )
        self._active_target = target
        self._set_busy(f"正在启动桌面学习模式（目标：{target.title}）...")

        self._desktop_thread = DesktopInferenceThread(
            self._frame_queue,
            server_url=self._server_url(),
            language="Chinese",
        )
        self._desktop_thread.status_changed.connect(self._status.setText)
        self._desktop_thread.analysis_started.connect(self._on_desktop_analysis_started)
        self._desktop_thread.analysis_ready.connect(self._on_desktop_result)
        self._desktop_thread.error.connect(self._on_worker_error)

        self._capture_thread = CaptureThread(
            self._frame_queue,
            target_window_provider=self._active_target_provider,
            settings_provider=self._capture_settings,
        )

        self._desktop_thread.start()
        self._capture_thread.start()
        self._subtitle.update_subtitle(
            "桌面学习模式已启动",
            f"目标窗口：{target.title}",
            "当前会把选中窗口的截图发送到本地 llama.cpp 服务做学术分析。",
        )
        self._subtitle.show()

    @Slot()
    def _start_video_mode(self):
        self._stop_all()
        video_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择讲座视频",
            "",
            "视频文件 (*.mp4 *.avi *.mkv *.mov *.flv *.wmv);;所有文件(*)",
        )
        if not video_path:
            return

        self._details.clear()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_name = Path(video_path).stem
        output_dir = os.path.join(self._output_dir(), f"{video_name}_{stamp}")
        os.makedirs(output_dir, exist_ok=True)

        self._append_log(f"开始分析视频: {video_path}")
        self._append_log(f"输出目录: {output_dir}")
        self._append_log(f"视频后端: llama.cpp server @ {self._server_url()}")
        self._set_busy("讲座视频分析中...")

        self._video_thread = VideoAnalysisWorker(
            video_path=video_path,
            output_dir=output_dir,
            server_url=self._server_url(),
            language="Chinese",
        )
        self._video_thread.log_line.connect(self._append_log)
        self._video_thread.failed.connect(self._on_worker_error)
        self._video_thread.completed.connect(self._on_video_completed)
        self._video_thread.start()

    @Slot(object)
    def _on_desktop_result(self, payload: dict):
        self._subtitle.update_subtitle(
            payload.get("line1", ""),
            payload.get("line2", ""),
            payload.get("summary", ""),
            payload.get("key_points", []),
            payload.get("next_action", ""),
        )
        self._details.setPlainText(payload.get("display_text", ""))

    @Slot(object)
    def _on_desktop_analysis_started(self, payload: dict):
        image_path = payload.get("image_path")
        if image_path and os.path.exists(image_path):
            self._current_preview_path = image_path
            self._render_preview_pixmap()
        else:
            self._current_preview_path = None
            self._preview_image.clear()
            self._preview_image.setText("未找到当前截图文件")

        capture_index = payload.get("capture_index")
        change_distance = payload.get("change_distance")
        target_title = payload.get("target_title")
        target_hwnd = payload.get("target_hwnd")
        capture_interval = payload.get("capture_interval")
        change_threshold = payload.get("change_threshold")
        width = payload.get("width")
        height = payload.get("height")
        source_width = payload.get("source_width")
        source_height = payload.get("source_height")
        captured_at = payload.get("captured_at")
        analysis_started_at = payload.get("analysis_started_at")
        delay_text = "未知"
        if captured_at and analysis_started_at:
            delay_text = f"{analysis_started_at - captured_at:.2f}s"

        if width and height and source_width and source_height and (width != source_width or height != source_height):
            resolution_text = f"送模分辨率: {width} x {height}（原始: {source_width} x {source_height}）"
        elif width and height:
            resolution_text = f"送模分辨率: {width} x {height}"
        else:
            resolution_text = "送模分辨率: 未知"

        meta_lines = [
            f"目标窗口: {target_title or '未知'}",
            f"目标 HWND: {target_hwnd if target_hwnd is not None else '未知'}",
            f"截图编号: {capture_index if capture_index is not None else '未知'}",
            f"采集后端: {CAPTURE_BACKEND_LABEL}",
            f"采集间隔: {capture_interval:.2f}s" if capture_interval else "采集间隔: 未知",
            f"触发阈值: {change_threshold:.2f}" if change_threshold is not None else "触发阈值: 未知",
            resolution_text,
            f"变化得分: {change_distance:.2f}" if change_distance is not None else "变化得分: first",
            f"捕获时间: {self._format_debug_time(captured_at)}",
            f"开始分析: {self._format_debug_time(analysis_started_at)}",
            f"从截取到开始分析的延迟: {delay_text}",
        ]
        self._preview_meta.setText("\n".join(meta_lines))

        change_text = "first" if change_distance is None else f"{change_distance:.2f}"
        self._append_log(
            f"[调试] 开始分析截图 #{capture_index if capture_index is not None else '?'}，"
            f"目标窗口={target_title or '未知'}，变化得分={change_text}，延迟={delay_text}"
        )

    @Slot(object)
    def _on_video_completed(self, payload: dict):
        self._append_log("")
        self._append_log(f"视频分析完成: {payload['title']}")
        self._append_log(f"片段数: {payload['segments']}")
        self._append_log(f"报告: {payload['report_path']}")
        self._append_log(f"视频: {payload['output_video']}")
        self._set_idle("视频分析完成")

    @Slot(str)
    def _on_worker_error(self, message: str):
        self._append_log("")
        self._append_log(f"[错误] {message}")
        self._set_idle("任务失败")
        QMessageBox.warning(self, "Study Lens", message)

    @Slot()
    def _stop_all(self):
        if self._capture_thread:
            self._capture_thread.stop()
            if not self._capture_thread.wait(2000):
                self._capture_thread.terminate()
                self._capture_thread.wait(1000)
            self._capture_thread = None

        if self._desktop_thread:
            self._desktop_thread.stop()
            if not self._desktop_thread.wait(2000):
                self._desktop_thread.terminate()
                self._desktop_thread.wait(1000)
            self._desktop_thread = None

        if self._video_thread:
            self._video_thread.stop()
            if not self._video_thread.wait(2000):
                self._video_thread.terminate()
                self._video_thread.wait(1000)
            self._video_thread = None

        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                break

        self._active_target = None
        self._subtitle.hide()
        self._clear_debug_preview()
        self._set_idle("已停止")

    def closeEvent(self, event):
        self._stop_all()
        self._subtitle.close()
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render_preview_pixmap()

    def _clear_debug_preview(self):
        self._current_preview_path = None
        self._preview_image.clear()
        self._preview_image.setText("暂无截图")
        self._preview_meta.setText("尚未开始分析")

    def _format_debug_time(self, value) -> str:
        if not value:
            return "未知"
        return datetime.fromtimestamp(value).strftime("%H:%M:%S.%f")[:-3]

    def _render_preview_pixmap(self):
        if not self._current_preview_path or not os.path.exists(self._current_preview_path):
            return
        pixmap = QPixmap(self._current_preview_path)
        if pixmap.isNull():
            self._preview_image.clear()
            self._preview_image.setText("截图预览加载失败")
            return
        self._preview_image.setPixmap(
            pixmap.scaled(
                self._preview_image.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
