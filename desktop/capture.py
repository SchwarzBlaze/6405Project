"""Target-window capture thread built on Windows Graphics Capture."""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass

import numpy as np
from PIL import Image
from PySide6.QtCore import QThread
from windows_capture import WindowsCapture

from desktop.windows import CAPTURE_BACKEND_WGC, WindowDescriptor


@dataclass(frozen=True)
class CaptureSettings:
    interval_seconds: float = 0.20
    change_threshold: float = 3.0


DEFAULT_CAPTURE_SETTINGS = CaptureSettings()
SIGNATURE_SIZE = (256, 144)


class CaptureThread(QThread):
    """Capture the selected target window and push changed frames into a queue."""

    def __init__(self, frame_queue: queue.Queue, target_window_provider, settings_provider=None):
        super().__init__()
        self._queue = frame_queue
        self._target_window_provider = target_window_provider
        self._settings_provider = settings_provider
        self._running = True
        self._paused = False
        self._last_signature = None
        self._capture_index = 0
        self._last_emit_at = 0.0

    def run(self):
        target = self._resolve_target_window()
        if not target:
            return

        capture = WindowsCapture(
            cursor_capture=False,
            draw_border=False,
            dirty_region=True,
            minimum_update_interval=16,
            window_hwnd=target.hwnd,
        )

        @capture.event
        def on_frame_arrived(frame, capture_control):
            if not self._running:
                capture_control.stop()
                return
            if self._paused:
                return

            settings = self._resolve_settings()
            now = time.time()
            if now - self._last_emit_at < settings.interval_seconds:
                return

            bgr = frame.convert_to_bgr().frame_buffer.copy()
            image = Image.fromarray(bgr[:, :, ::-1].copy())
            current_signature = _build_signature(image)
            distance = None

            if self._last_signature is not None:
                distance = _compute_change_score(current_signature, self._last_signature)
                if distance <= settings.change_threshold:
                    return

            self._last_signature = current_signature
            self._last_emit_at = now

            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass

            self._capture_index += 1
            self._queue.put(
                {
                    "image": image,
                    "captured_at": now,
                    "change_distance": distance,
                    "capture_index": self._capture_index,
                    "target_hwnd": target.hwnd,
                    "target_title": target.title,
                    "capture_method": CAPTURE_BACKEND_WGC,
                    "capture_source": CAPTURE_BACKEND_WGC,
                    "capture_interval": settings.interval_seconds,
                    "change_threshold": settings.change_threshold,
                }
            )

        @capture.event
        def on_closed():
            self._running = False

        control = capture.start_free_threaded()
        while self._running and not control.is_finished():
            self.msleep(100)

        if not control.is_finished():
            control.stop()
        control.wait()

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        self._running = False

    def _resolve_target_window(self) -> WindowDescriptor | None:
        try:
            target = self._target_window_provider()
        except Exception:
            return None
        if not target or not isinstance(target, WindowDescriptor):
            return None
        return target

    def _resolve_settings(self) -> CaptureSettings:
        if not self._settings_provider:
            return DEFAULT_CAPTURE_SETTINGS
        try:
            settings = self._settings_provider()
        except Exception:
            return DEFAULT_CAPTURE_SETTINGS
        if not isinstance(settings, CaptureSettings):
            return DEFAULT_CAPTURE_SETTINGS
        return settings


def _build_signature(image: Image.Image) -> np.ndarray:
    thumb = image.convert("L").resize(SIGNATURE_SIZE, Image.Resampling.BILINEAR)
    return np.asarray(thumb, dtype=np.int16)


def _compute_change_score(current: np.ndarray, previous: np.ndarray) -> float:
    return float(np.mean(np.abs(current - previous)))
