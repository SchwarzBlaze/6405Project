"""Desktop inference thread for screenshot-based academic analysis."""

from __future__ import annotations

import os
import queue
import tempfile
import time
from math import sqrt

from PIL import Image
from PySide6.QtCore import QThread, Signal

from analysis.desktop_analyzer import (
    DesktopContext,
    analysis_to_payload,
    analyze_desktop_image_via_llamacpp,
)
from analysis.llamacpp_client import LlamaCppServerClient
from app_i18n import model_output_language, normalize_ui_language, tr

MAX_ANALYSIS_LONG_EDGE = 1280
MAX_ANALYSIS_AREA = 900_000


class DesktopInferenceThread(QThread):
    """Read screenshots from a queue and analyze them with llama.cpp."""

    analysis_ready = Signal(object)
    analysis_started = Signal(object)
    status_changed = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        frame_queue: queue.Queue,
        server_url: str,
        language: str = "Chinese",
        max_tokens: int = 512,
        ui_language: str = "zh",
    ):
        super().__init__()
        self._queue = frame_queue
        self._server_url = server_url
        self._language = language
        self._ui_language = normalize_ui_language(ui_language)
        self._max_tokens = max_tokens
        self._running = True
        self._paused = False
        self._context = DesktopContext(max_entries=0)

    def set_language(self, ui_language: str) -> None:
        self._ui_language = normalize_ui_language(ui_language)
        self._language = model_output_language(self._ui_language)

    def run(self):
        try:
            self.status_changed.emit(tr(self._ui_language, "service_connecting"))
            client = LlamaCppServerClient(self._server_url, ui_language=self._ui_language)
            self.status_changed.emit(tr(self._ui_language, "desktop_waiting_for_change"))
        except Exception as exc:
            self.error.emit(str(exc))
            return

        with tempfile.TemporaryDirectory(prefix="study_lens_") as temp_dir:
            index = 0
            while self._running:
                if self._paused:
                    self.msleep(100)
                    continue

                try:
                    payload = self._queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                try:
                    image, meta = self._unpack_payload(payload)
                    image_path = os.path.join(temp_dir, f"capture_{index:05d}.png")
                    index += 1
                    prepared = self._prepare_image_for_analysis(image)
                    prepared.save(image_path)
                    analysis_started_at = time.time()
                    self.analysis_started.emit(
                        {
                            "image_path": image_path,
                            "captured_at": meta.get("captured_at"),
                            "analysis_started_at": analysis_started_at,
                            "capture_index": meta.get("capture_index"),
                            "change_distance": meta.get("change_distance"),
                            "target_hwnd": meta.get("target_hwnd"),
                            "target_title": meta.get("target_title"),
                            "capture_method": meta.get("capture_method"),
                            "capture_source": meta.get("capture_source"),
                            "capture_interval": meta.get("capture_interval"),
                            "change_threshold": meta.get("change_threshold"),
                            "width": prepared.width,
                            "height": prepared.height,
                            "source_width": image.width,
                            "source_height": image.height,
                        }
                    )
                    result = analyze_desktop_image_via_llamacpp(
                        client=client,
                        image_path=image_path,
                        context=self._context,
                        language=self._language,
                        max_tokens=self._max_tokens,
                    )
                    self._context.add(result.summary)
                    ready_payload = analysis_to_payload(result, language=self._language)
                    ready_payload.update(
                        {
                            "capture_index": meta.get("capture_index"),
                            "target_title": meta.get("target_title"),
                            "captured_at": meta.get("captured_at"),
                            "analysis_started_at": analysis_started_at,
                        }
                    )
                    self.analysis_ready.emit(ready_payload)
                except Exception as exc:
                    self.error.emit(
                        tr(
                            self._ui_language,
                            "desktop_analysis_failed_prefix",
                            message=str(exc),
                        )
                    )

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        self._running = False

    def _unpack_payload(self, payload):
        if isinstance(payload, dict):
            image = payload.get("image")
            meta = {
                "captured_at": payload.get("captured_at"),
                "change_distance": payload.get("change_distance"),
                "capture_index": payload.get("capture_index"),
                "target_hwnd": payload.get("target_hwnd"),
                "target_title": payload.get("target_title"),
                "capture_method": payload.get("capture_method"),
                "capture_source": payload.get("capture_source"),
                "capture_interval": payload.get("capture_interval"),
                "change_threshold": payload.get("change_threshold"),
            }
            return image, meta
        return payload, {"captured_at": None, "change_distance": None, "capture_index": None}

    def _prepare_image_for_analysis(self, image):
        width, height = image.size
        scale = min(
            1.0,
            MAX_ANALYSIS_LONG_EDGE / max(width, height),
            sqrt(MAX_ANALYSIS_AREA / float(width * height)),
        )
        if scale >= 0.999:
            return image

        new_width = max(48, int(width * scale))
        new_height = max(48, int(height * scale))
        new_width = max(48, (new_width // 48) * 48)
        new_height = max(48, (new_height // 48) * 48)

        if new_width == width and new_height == height:
            return image

        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
