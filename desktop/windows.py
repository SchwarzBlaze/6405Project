"""Window enumeration helpers for Study Lens."""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from ctypes import wintypes

from app_i18n import normalize_ui_language

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

CAPTURE_BACKEND_WGC = "windows_graphics_capture"


@dataclass(frozen=True)
class WindowDescriptor:
    hwnd: int
    title: str
    process_name: str = ""
    is_minimized: bool = False

    @property
    def base_title(self) -> str:
        if self.process_name and self.process_name.lower() not in self.title.lower():
            return f"{self.title} - {self.process_name}"
        return self.title

    def formatted_title(self, ui_language: str = "zh") -> str:
        text = self.base_title
        if self.is_minimized:
            suffix = " [已最小化]" if normalize_ui_language(ui_language) == "zh" else " [Minimized]"
            return f"{text}{suffix}"
        return text


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def list_windows(excluded_hwnds: set[int] | None = None) -> list[WindowDescriptor]:
    excluded = excluded_hwnds or set()
    windows: list[WindowDescriptor] = []

    def callback(hwnd, _lparam):
        hwnd_int = int(hwnd)
        if hwnd_int in excluded:
            return True
        if not _is_capturable_window(hwnd_int):
            return True

        title = _get_window_text(hwnd_int).strip()
        if not title:
            return True

        process_name = _get_process_name(hwnd_int)
        windows.append(
            WindowDescriptor(
                hwnd=hwnd_int,
                title=title,
                process_name=process_name,
                is_minimized=bool(user32.IsIconic(hwnd_int)),
            )
        )
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    windows.sort(key=lambda item: item.base_title.lower())
    return windows


def is_window_alive(hwnd: int) -> bool:
    return bool(hwnd) and bool(user32.IsWindow(hwnd))


def _is_capturable_window(hwnd: int) -> bool:
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    if not user32.IsWindowVisible(hwnd):
        return False

    exstyle = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if exstyle & WS_EX_TOOLWINDOW:
        return False

    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False
    if rect.right - rect.left < 64 or rect.bottom - rect.top < 64:
        return False

    return True


def _get_window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value


def _get_process_name(hwnd: int) -> str:
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    if not process_id.value:
        return ""

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id.value)
    if not handle:
        return ""

    try:
        buffer_len = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(buffer_len.value)
        query_name = getattr(kernel32, "QueryFullProcessImageNameW", None)
        if not query_name:
            return ""
        if not query_name(handle, 0, buffer, ctypes.byref(buffer_len)):
            return ""
        return os.path.basename(buffer.value)
    finally:
        kernel32.CloseHandle(handle)
