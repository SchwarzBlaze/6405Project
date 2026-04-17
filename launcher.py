"""Unified launcher for desktop study mode and lecture-video mode."""

from __future__ import annotations

import os
import queue
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
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
)

from analysis.desktop_analyzer import format_payload_text
from analysis.desktop_inference import DesktopInferenceThread
from analysis.video_worker import VideoAnalysisWorker
from app_i18n import LANGUAGE_OPTIONS, model_output_language, normalize_ui_language, tr
from desktop.capture import CaptureSettings, CaptureThread
from desktop.subtitle import SubtitleBar
from desktop.windows import WindowDescriptor, is_window_alive, list_windows

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


class Launcher(QWidget):
    """Single-window launcher that combines desktop and video modes."""

    def __init__(self):
        super().__init__()
        self._ui_language = "zh"
        self.setObjectName("launcher")
        self.setWindowTitle("Study Lens")
        self.setMinimumSize(980, 800)
        self.setStyleSheet(WINDOW_STYLE)

        self._frame_queue = queue.Queue(maxsize=1)
        self._subtitle = SubtitleBar(ui_language=self._ui_language)
        self._subtitle.hide()

        self._capture_thread: CaptureThread | None = None
        self._desktop_thread: DesktopInferenceThread | None = None
        self._video_thread: VideoAnalysisWorker | None = None
        self._current_preview_path: str | None = None
        self._window_options: dict[int, WindowDescriptor] = {}
        self._active_target: WindowDescriptor | None = None
        self._latest_started_capture_index: int | None = None
        self._last_result_payload: dict | None = None
        self._last_preview_payload: dict | None = None
        self._current_status_note = ""

        self._build_ui()
        self._apply_ui_language()
        self._refresh_window_options()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 22, 24, 22)

        self._title_label = QLabel("Study Lens")
        self._title_label.setFont(QFont("Microsoft YaHei", 22, QFont.Weight.Bold))
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title_label)

        self._subtitle_label = QLabel("")
        self._subtitle_label.setFont(QFont("Microsoft YaHei", 11))
        self._subtitle_label.setStyleSheet("color: #a6adc8;")
        self._subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._subtitle_label)

        layout.addWidget(self._row_with_language_selector())
        layout.addWidget(
            self._row_with_input(
                field_name="server_url",
                default_text=DEFAULT_SERVER_URL,
            )
        )

        self._server_hint = QLabel("")
        self._server_hint.setWordWrap(True)
        self._server_hint.setStyleSheet("color: #a6adc8;")
        layout.addWidget(self._server_hint)

        layout.addWidget(
            self._row_with_browse(
                field_name="output",
                default_text=os.path.abspath("./output"),
            )
        )
        layout.addWidget(self._capture_settings_row())
        layout.addWidget(self._window_selector_row())

        button_row = QHBoxLayout()
        button_row.setSpacing(10)

        self._btn_desktop = QPushButton("")
        self._btn_desktop.setObjectName("primary")
        self._btn_desktop.clicked.connect(self._start_desktop_mode)
        button_row.addWidget(self._btn_desktop)

        self._btn_video = QPushButton("")
        self._btn_video.clicked.connect(self._start_video_mode)
        button_row.addWidget(self._btn_video)

        self._btn_stop = QPushButton("")
        self._btn_stop.setObjectName("danger")
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._stop_all)
        button_row.addWidget(self._btn_stop)

        layout.addLayout(button_row)

        self._status = QLabel("")
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

        self._preview_title = QLabel("")
        self._preview_title.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        preview_layout.addWidget(self._preview_title)

        self._preview_meta = QLabel("")
        self._preview_meta.setWordWrap(True)
        self._preview_meta.setStyleSheet("color: #a6adc8;")
        preview_layout.addWidget(self._preview_meta)

        self._preview_image = QLabel("")
        self._preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_image.setMinimumSize(360, 220)
        self._preview_image.setStyleSheet(
            "background-color: #11111b; border: 1px solid #45475a; border-radius: 8px; color: #6c7086;"
        )
        preview_layout.addWidget(self._preview_image, 1)

        content_row.addWidget(preview_panel, 1)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self._log_title = QLabel("")
        self._log_title.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        right_layout.addWidget(self._log_title)

        self._details = QTextEdit()
        self._details.setReadOnly(True)
        self._details.setFont(QFont("Microsoft YaHei", 10))
        right_layout.addWidget(self._details, 1)

        content_row.addWidget(right_panel, 1)
        layout.addLayout(content_row, 1)

    def _row_with_language_selector(self) -> QWidget:
        container = QWidget()
        row = QVBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self._language_label = QLabel("")
        row.addWidget(self._language_label)

        self._language_combo = QComboBox()
        for code, title in LANGUAGE_OPTIONS:
            self._language_combo.addItem(title, code)
        self._language_combo.currentIndexChanged.connect(lambda _index: self._on_language_changed())
        row.addWidget(self._language_combo)
        return container

    def _row_with_browse(self, field_name: str, default_text: str) -> QWidget:
        container = QWidget()
        row = QVBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        label = QLabel("")
        row.addWidget(label)

        inner = QHBoxLayout()
        inner.setContentsMargins(0, 0, 0, 0)

        line_edit = QLineEdit(default_text)
        browse_btn = QPushButton("")
        browse_btn.clicked.connect(lambda: self._browse_dir(line_edit))

        if field_name == "output":
            self._output_label = label
            self._output_dir_edit = line_edit
            self._output_browse_btn = browse_btn
        else:
            raise ValueError(f"Unexpected field_name: {field_name}")

        inner.addWidget(line_edit, 1)
        inner.addWidget(browse_btn)
        row.addLayout(inner)
        return container

    def _row_with_input(self, field_name: str, default_text: str) -> QWidget:
        container = QWidget()
        row = QVBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        label = QLabel("")
        row.addWidget(label)

        line_edit = QLineEdit(default_text)
        row.addWidget(line_edit)

        if field_name == "server_url":
            self._server_label = label
            self._server_url_edit = line_edit
        else:
            raise ValueError(f"Unexpected field_name: {field_name}")

        return container

    def _capture_settings_row(self) -> QWidget:
        container = QWidget()
        row = QVBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self._capture_settings_label = QLabel("")
        row.addWidget(self._capture_settings_label)

        inner = QHBoxLayout()
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(10)

        self._interval_spin = QDoubleSpinBox()
        self._interval_spin.setRange(0.05, 5.00)
        self._interval_spin.setSingleStep(0.05)
        self._interval_spin.setSuffix(" s")
        self._interval_spin.setValue(0.20)
        self._interval_box, self._interval_box_label = self._labeled_widget(self._interval_spin)
        inner.addWidget(self._interval_box, 1)

        self._threshold_spin = QDoubleSpinBox()
        self._threshold_spin.setRange(0.2, 50.0)
        self._threshold_spin.setSingleStep(0.2)
        self._threshold_spin.setValue(1.0)
        self._threshold_box, self._threshold_box_label = self._labeled_widget(self._threshold_spin)
        inner.addWidget(self._threshold_box, 1)

        row.addLayout(inner)

        self._capture_hint = QLabel("")
        self._capture_hint.setWordWrap(True)
        self._capture_hint.setStyleSheet("color: #a6adc8;")
        row.addWidget(self._capture_hint)

        return container

    def _labeled_widget(self, widget: QWidget) -> tuple[QWidget, QLabel]:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label = QLabel("")
        layout.addWidget(label)
        layout.addWidget(widget)
        return container, label

    def _window_selector_row(self) -> QWidget:
        container = QWidget()
        row = QVBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self._window_label = QLabel("")
        row.addWidget(self._window_label)

        inner = QHBoxLayout()
        inner.setContentsMargins(0, 0, 0, 0)

        self._window_combo = QComboBox()
        self._refresh_btn = QPushButton("")
        self._refresh_btn.clicked.connect(self._refresh_window_options)

        inner.addWidget(self._window_combo, 1)
        inner.addWidget(self._refresh_btn)
        row.addLayout(inner)
        return container

    def _text(self, key: str, **kwargs) -> str:
        return tr(self._ui_language, key, **kwargs)

    def _apply_ui_language(self) -> None:
        self._subtitle_label.setText(self._text("app_subtitle"))
        self._language_label.setText(self._text("display_language"))
        self._server_label.setText(self._text("ai_service_url"))
        self._server_url_edit.setPlaceholderText(self._text("ai_service_placeholder"))
        self._server_hint.setText(self._text("server_hint"))
        self._output_label.setText(self._text("output_dir"))
        self._output_browse_btn.setText(self._text("browse"))
        self._capture_settings_label.setText(self._text("capture_settings"))
        self._interval_box_label.setText(self._text("detect_interval"))
        self._threshold_box_label.setText(self._text("trigger_threshold"))
        self._capture_hint.setText(self._text("threshold_hint"))
        self._window_label.setText(self._text("target_window"))
        self._refresh_btn.setText(self._text("refresh_window_list"))
        self._btn_desktop.setText(self._text("start_desktop"))
        self._btn_video.setText(self._text("analyze_video"))
        self._btn_stop.setText(self._text("stop_task"))
        self._preview_title.setText(self._text("current_analysis_frame"))
        self._log_title.setText(self._text("latest_analysis_and_logs"))

        if not self._capture_thread and not self._desktop_thread and not self._video_thread:
            self._status.setText(self._text("ready"))

        self._clear_debug_preview()
        self._refresh_window_options()
        self._subtitle.set_language(self._ui_language)

        if self._desktop_thread:
            self._desktop_thread.set_language(self._ui_language)

        if self._last_preview_payload:
            self._render_preview_meta(self._last_preview_payload)
            self._render_preview_pixmap()
        if self._last_result_payload:
            self._render_subtitle_from_payload(self._last_result_payload, self._current_status_note)
            self._details.setPlainText(
                format_payload_text(
                    self._last_result_payload,
                    language=model_output_language(self._ui_language),
                )
            )

    @Slot()
    def _on_language_changed(self):
        self._ui_language = normalize_ui_language(self._language_combo.currentData())
        self._apply_ui_language()

    def _browse_dir(self, line_edit: QLineEdit):
        path = QFileDialog.getExistingDirectory(
            self,
            self._text("output_dir"),
            line_edit.text() or os.getcwd(),
        )
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
        self._window_combo.addItem(self._text("select_target_window"), None)
        for item in windows:
            self._window_combo.addItem(item.formatted_title(self._ui_language), item.hwnd)

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

    def _set_idle(self, status: str | None = None):
        self._status.setText(status or self._text("ready"))
        self._btn_desktop.setEnabled(True)
        self._btn_video.setEnabled(True)
        self._btn_stop.setEnabled(False)

    def _render_subtitle_from_payload(self, payload: dict, status_note: str = "") -> None:
        self._subtitle.update_subtitle(
            payload.get("line1", ""),
            payload.get("line2", ""),
            status_note,
            payload.get("formula_text", ""),
            payload.get("summary_raw", payload.get("summary", "")),
            payload.get("key_points", []),
            payload.get("next_action", ""),
        )

    def _render_preview_meta(self, payload: dict) -> None:
        capture_index = payload.get("capture_index")
        change_distance = payload.get("change_distance")
        target_title = payload.get("target_title")
        capture_interval = payload.get("capture_interval")
        change_threshold = payload.get("change_threshold")
        width = payload.get("width")
        height = payload.get("height")
        source_width = payload.get("source_width")
        source_height = payload.get("source_height")
        captured_at = payload.get("captured_at")
        analysis_started_at = payload.get("analysis_started_at")

        delay_text = self._text("unknown")
        if captured_at and analysis_started_at:
            delay_text = f"{analysis_started_at - captured_at:.2f}s"

        if width and height and source_width and source_height and (
            width != source_width or height != source_height
        ):
            resolution_text = self._text(
                "analysis_resolution_with_source",
                width=width,
                height=height,
                source_width=source_width,
                source_height=source_height,
            )
        elif width and height:
            resolution_text = self._text("analysis_resolution", width=width, height=height)
        else:
            resolution_text = self._text("analysis_resolution", width="?", height="?")

        meta_lines = [
            self._text("meta_current_window", title=target_title or self._text("unknown")),
            self._text("meta_capture_index", index=capture_index if capture_index is not None else self._text("unknown")),
            (
                self._text("meta_capture_interval", value=capture_interval)
                if capture_interval
                else self._text("meta_capture_interval_unknown")
            ),
            (
                self._text("meta_trigger_threshold", value=change_threshold)
                if change_threshold is not None
                else self._text("meta_trigger_threshold_unknown")
            ),
            resolution_text,
            (
                self._text("meta_screen_change", value=change_distance)
                if change_distance is not None
                else self._text("meta_first_capture")
            ),
            self._text("meta_captured_at", value=self._format_debug_time(captured_at)),
            self._text("meta_analysis_started_at", value=self._format_debug_time(analysis_started_at)),
            self._text("meta_processing_delay", value=delay_text),
        ]
        self._preview_meta.setText("\n".join(meta_lines))

    @Slot()
    def _start_desktop_mode(self):
        self._stop_all()
        target = self._selected_target_window()
        if not target:
            QMessageBox.information(self, "Study Lens", self._text("choose_target_window_message"))
            return

        settings = self._capture_settings()
        self._details.clear()
        self._append_log(self._text("desktop_mode_started"))
        self._append_log(f"{self._text('current_window')}: {target.formatted_title(self._ui_language)}")
        self._append_log(f"{self._text('service_url_log')}: {self._server_url()}")
        self._append_log(
            self._text(
                "capture_settings_log",
                interval=settings.interval_seconds,
                threshold=settings.change_threshold,
            )
        )

        self._active_target = target
        self._latest_started_capture_index = None
        self._last_result_payload = None
        self._last_preview_payload = None
        self._current_status_note = ""
        self._set_busy(self._text("busy_start_desktop", title=target.formatted_title(self._ui_language)))

        self._desktop_thread = DesktopInferenceThread(
            self._frame_queue,
            server_url=self._server_url(),
            language=model_output_language(self._ui_language),
            ui_language=self._ui_language,
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

        intro_payload = {
            "line1": self._text("desktop_subtitle_started"),
            "line2": self._text("desktop_subtitle_target", title=target.formatted_title(self._ui_language)),
            "formula_text": "",
            "summary": self._text("desktop_subtitle_summary"),
            "key_points": [],
            "next_action": "",
        }
        self._render_subtitle_from_payload(intro_payload)
        self._subtitle.show()

    @Slot()
    def _start_video_mode(self):
        self._stop_all()
        video_path, _ = QFileDialog.getOpenFileName(
            self,
            self._text("select_video_dialog"),
            "",
            self._text("video_file_filter"),
        )
        if not video_path:
            return

        self._details.clear()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_name = Path(video_path).stem
        output_dir = os.path.join(self._output_dir(), f"{video_name}_{stamp}")
        os.makedirs(output_dir, exist_ok=True)

        self._append_log(self._text("video_started", path=video_path))
        self._append_log(self._text("video_output_dir", path=output_dir))
        self._append_log(f"{self._text('service_url_log')}: {self._server_url()}")
        self._set_busy(self._text("busy_video"))

        self._video_thread = VideoAnalysisWorker(
            video_path=video_path,
            output_dir=output_dir,
            server_url=self._server_url(),
            language=model_output_language(self._ui_language),
            ui_language=self._ui_language,
        )
        self._video_thread.log_line.connect(self._append_log)
        self._video_thread.failed.connect(self._on_worker_error)
        self._video_thread.completed.connect(self._on_video_completed)
        self._video_thread.start()

    @Slot(object)
    def _on_desktop_result(self, payload: dict):
        capture_index = payload.get("capture_index")
        if (
            capture_index is not None
            and self._latest_started_capture_index is not None
            and capture_index < self._latest_started_capture_index
        ):
            self._append_log(self._text("stale_result_dropped", index=capture_index))
            return

        self._last_result_payload = dict(payload)
        self._current_status_note = ""
        self._render_subtitle_from_payload(payload)
        self._details.setPlainText(
            format_payload_text(payload, language=model_output_language(self._ui_language))
        )

    @Slot(object)
    def _on_desktop_analysis_started(self, payload: dict):
        self._last_preview_payload = dict(payload)
        image_path = payload.get("image_path")
        if image_path and os.path.exists(image_path):
            self._current_preview_path = image_path
            self._render_preview_pixmap()
        else:
            self._current_preview_path = None
            self._preview_image.clear()
            self._preview_image.setText(self._text("preview_missing"))

        capture_index = payload.get("capture_index")
        if capture_index is not None:
            self._latest_started_capture_index = capture_index

        self._render_preview_meta(payload)

        self._current_status_note = self._text("new_page_captured")
        if self._last_result_payload:
            self._render_subtitle_from_payload(self._last_result_payload, self._current_status_note)
        else:
            self._render_subtitle_from_payload(
                {
                    "line1": self._text("analyzing_current_frame"),
                    "line2": "",
                    "formula_text": "",
                    "summary": "",
                    "key_points": [],
                    "next_action": "",
                },
                self._current_status_note,
            )

        change_distance = payload.get("change_distance")
        change_text = self._text("unknown") if change_distance is None else f"{change_distance:.2f}"
        delay_text = self._text("unknown")
        if payload.get("captured_at") and payload.get("analysis_started_at"):
            delay_text = f"{payload['analysis_started_at'] - payload['captured_at']:.2f}s"
        self._append_log(
            self._text(
                "processing_frame_log",
                index=capture_index if capture_index is not None else "?",
                title=payload.get("target_title") or self._text("unknown"),
                change=change_text,
                delay=delay_text,
            )
        )

    @Slot(object)
    def _on_video_completed(self, payload: dict):
        self._append_log("")
        self._append_log(self._text("video_completed", title=payload["title"]))
        self._append_log(self._text("segment_count", count=payload["segments"]))
        self._append_log(self._text("report_path", path=payload["report_path"]))
        self._append_log(self._text("output_video_path", path=payload["output_video"]))
        self._set_idle(self._text("video_completed_status"))

    @Slot(str)
    def _on_worker_error(self, message: str):
        self._append_log("")
        self._append_log(self._text("error_prefix", message=message))
        self._set_idle(self._text("task_failed"))
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
        self._latest_started_capture_index = None
        self._last_result_payload = None
        self._last_preview_payload = None
        self._current_status_note = ""
        self._subtitle.hide()
        self._clear_debug_preview()
        self._set_idle(self._text("stopped_status"))

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
        self._preview_image.setText(self._text("no_capture"))
        self._preview_meta.setText(self._text("not_started"))

    def _format_debug_time(self, value) -> str:
        if not value:
            return self._text("unknown")
        return datetime.fromtimestamp(value).strftime("%H:%M:%S.%f")[:-3]

    def _render_preview_pixmap(self):
        if not self._current_preview_path or not os.path.exists(self._current_preview_path):
            return
        pixmap = QPixmap(self._current_preview_path)
        if pixmap.isNull():
            self._preview_image.clear()
            self._preview_image.setText(self._text("preview_load_failed"))
            return
        self._preview_image.setPixmap(
            pixmap.scaled(
                self._preview_image.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
