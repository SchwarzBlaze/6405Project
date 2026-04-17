"""Windows window-enumeration helpers for target-window capture."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from ctypes import wintypes
from pathlib import Path

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
    def display_title(self) -> str:
        base = self.title
        if self.process_name and self.process_name.lower() not in self.title.lower():
            base = f"{self.title} - {self.process_name}"
        if self.is_minimized:
            return f"{base} [已最小化]"
        return base


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
    windows.sort(key=lambda item: item.display_title.lower())
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
    if rect.right <= rect.left or rect.bottom <= rect.top:
        return False

    return True


def _get_window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _get_process_name(hwnd: int) -> str:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""

    try:
        buffer_len = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(buffer_len.value)
        ok = kernel32.QueryFullProcessImageNameW(
            handle,
            0,
            buffer,
            ctypes.byref(buffer_len),
        )
        if not ok:
            return ""
        return Path(buffer.value).name
    finally:
        kernel32.CloseHandle(handle)
