"""Floating subtitle window with move and resize support."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QFont, QMouseEvent, QPixmap, QScreen
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app_i18n import tr
from desktop.formula_renderer import render_formula_pixmap

EDGE = 7
HANDLE_WIDTH = 28


class SubtitleBar(QWidget):
    _CURSORS = {
        "L": Qt.CursorShape.SizeHorCursor,
        "R": Qt.CursorShape.SizeHorCursor,
        "T": Qt.CursorShape.SizeVerCursor,
        "B": Qt.CursorShape.SizeVerCursor,
        "TL": Qt.CursorShape.SizeFDiagCursor,
        "BR": Qt.CursorShape.SizeFDiagCursor,
        "TR": Qt.CursorShape.SizeBDiagCursor,
        "BL": Qt.CursorShape.SizeBDiagCursor,
    }

    geometry_changed = Signal()

    def __init__(self, ui_language: str = "zh"):
        super().__init__()
        self._ui_language = ui_language

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)

        self.setMinimumSize(320, 90)
        self.setMaximumSize(1600, 420)

        self._action = None
        self._drag_offset = None
        self._resize_edge = None
        self._resize_start_pos = None
        self._resize_start_geo = None
        self._formula_raw_text = ""

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._handle = QLabel("⋮⋮")
        self._handle.setFixedWidth(HANDLE_WIDTH)
        self._handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._handle.setContentsMargins(8, 0, 0, 0)
        self._handle.setStyleSheet(
            "color: rgba(255,255,255,120); background-color: rgba(30,30,30,200);"
            "border-top-left-radius: 12px; border-bottom-left-radius: 12px;"
            "font-size: 16px; padding-left: 6px;"
        )
        self._handle.setMouseTracking(True)
        outer.addWidget(self._handle)

        self._container = QWidget()
        self._container.setMouseTracking(True)
        self._container.setStyleSheet(
            "background-color: rgba(30, 30, 30, 200);"
            "border-top-right-radius: 12px; border-bottom-right-radius: 12px;"
        )

        content_layout = QVBoxLayout(self._container)
        content_layout.setContentsMargins(20, 10, 24, 10)
        content_layout.setSpacing(4)

        self._line1 = QLabel(tr(self._ui_language, "subtitle_waiting"))
        self._line1.setFont(QFont("Microsoft YaHei", 14))
        self._line1.setStyleSheet("color: white; background: transparent;")
        self._line1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._line1.setWordWrap(True)
        self._line1.setMouseTracking(True)
        content_layout.addWidget(self._line1)

        self._line2 = QLabel("")
        self._line2.setFont(QFont("Microsoft YaHei", 11))
        self._line2.setStyleSheet("color: rgba(255,255,255,180); background: transparent;")
        self._line2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._line2.setWordWrap(True)
        self._line2.setMouseTracking(True)
        self._line2.hide()
        content_layout.addWidget(self._line2)

        self._notice = QLabel("")
        self._notice.setFont(QFont("Microsoft YaHei", 10))
        self._notice.setStyleSheet("color: rgba(255,255,255,150); background: transparent;")
        self._notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._notice.setWordWrap(True)
        self._notice.setMouseTracking(True)
        self._notice.hide()
        content_layout.addWidget(self._notice)

        self._formula = QLabel("")
        self._formula.setFont(QFont("Cambria Math", 12))
        self._formula.setStyleSheet("color: rgba(255,255,255,230); background: transparent;")
        self._formula.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._formula.setWordWrap(True)
        self._formula.setScaledContents(False)
        self._formula.setMouseTracking(True)
        self._formula.hide()
        content_layout.addWidget(self._formula)

        self._summary = QLabel("")
        self._summary.setFont(QFont("Microsoft YaHei", 10))
        self._summary.setStyleSheet("color: rgba(255,255,255,205); background: transparent;")
        self._summary.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._summary.setWordWrap(True)
        self._summary.setMouseTracking(True)
        self._summary.hide()
        content_layout.addWidget(self._summary)

        self._detail = QLabel("")
        self._detail.setFont(QFont("Microsoft YaHei", 9))
        self._detail.setStyleSheet("color: rgba(255,255,255,160); background: transparent;")
        self._detail.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._detail.setWordWrap(True)
        self._detail.setMouseTracking(True)
        self._detail.hide()
        content_layout.addWidget(self._detail)

        outer.addWidget(self._container)

        self._user_moved = False
        self._reposition()

    def set_language(self, ui_language: str) -> None:
        self._ui_language = ui_language
        if not self._line1.text().strip():
            self._line1.setText(tr(self._ui_language, "subtitle_waiting"))

    def update_subtitle(
        self,
        line1: str,
        line2: str = "",
        status_note: str = "",
        formula_text: str = "",
        summary: str = "",
        key_points: list[str] | None = None,
        next_action: str = "",
    ):
        self._line1.setText(line1 if line1 else tr(self._ui_language, "subtitle_waiting"))
        if line2:
            self._line2.setText(line2)
            self._line2.show()
        else:
            self._line2.hide()

        if status_note:
            self._notice.setText(status_note)
            self._notice.show()
        else:
            self._notice.hide()

        if formula_text:
            self._formula_raw_text = formula_text
            self._apply_formula_render()
            self._formula.show()
        else:
            self._formula_raw_text = ""
            self._formula.clear()
            self._formula.hide()

        if summary:
            self._summary.setText(summary)
            self._summary.show()
        else:
            self._summary.hide()

        detail_lines: list[str] = []
        bullet_prefix = tr(self._ui_language, "detail_bullet_prefix")
        if key_points:
            detail_lines.extend(f"{bullet_prefix}{point}" for point in key_points if point)
        if next_action:
            detail_lines.append(f"{tr(self._ui_language, 'next_step_prefix')} {next_action}")

        if detail_lines:
            self._detail.setText("\n".join(detail_lines))
            self._detail.show()
        else:
            self._detail.hide()

        target_height = 100
        if line2:
            target_height += 18
        if status_note:
            target_height += 18
        if formula_text:
            target_height += 26
        if summary:
            target_height += 56
        if detail_lines:
            target_height += min(110, 22 * len(detail_lines))
        target_height = max(self.minimumHeight(), min(target_height, self.maximumHeight()))
        self.resize(self.width(), target_height)
        self.geometry_changed.emit()

    def _reposition(self):
        screen: QScreen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        width, height = 620, 150
        x = geo.x() + (geo.width() - width) // 2
        y = geo.y() + geo.height() - height - 48
        self.resize(width, height)
        self.move(x, y)
        self.geometry_changed.emit()

    def _apply_formula_render(self):
        if not self._formula_raw_text:
            self._formula.clear()
            return
        pixmap = render_formula_pixmap(
            self._formula_raw_text,
            max_width=max(220, self.width() - 80),
        )
        if pixmap is not None and not pixmap.isNull():
            self._formula.setPixmap(pixmap)
            self._formula.setText("")
        else:
            self._formula.setPixmap(QPixmap())
            self._formula.setText(self._formula_raw_text)

    def _edge_at(self, pos: QPoint) -> str | None:
        x, y, width, height = pos.x(), pos.y(), self.width(), self.height()
        on_left = x < EDGE
        on_right = x > width - EDGE
        on_top = y < EDGE
        on_bottom = y > height - EDGE

        if on_top and on_left:
            return "TL"
        if on_top and on_right:
            return "TR"
        if on_bottom and on_left:
            return "BL"
        if on_bottom and on_right:
            return "BR"
        if on_left:
            return "L"
        if on_right:
            return "R"
        if on_top:
            return "T"
        if on_bottom:
            return "B"
        return None

    def _on_handle(self, pos: QPoint) -> bool:
        return EDGE <= pos.x() < HANDLE_WIDTH and EDGE <= pos.y() < self.height() - EDGE

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position().toPoint()
        edge = self._edge_at(pos)
        if edge:
            self._action = "resize"
            self._resize_edge = edge
            self._resize_start_pos = event.globalPosition().toPoint()
            self._resize_start_geo = self.geometry()
        elif self._on_handle(pos):
            self._action = "move"
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() & Qt.MouseButton.LeftButton:
            if self._action == "resize":
                self._do_resize(event.globalPosition().toPoint())
            elif self._action == "move" and self._drag_offset:
                self.move(event.globalPosition().toPoint() - self._drag_offset)
                self._user_moved = True
                self.geometry_changed.emit()
            event.accept()
            return

        pos = event.position().toPoint()
        edge = self._edge_at(pos)
        if edge:
            self.setCursor(self._CURSORS[edge])
        elif self._on_handle(pos):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.unsetCursor()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._action:
            self._user_moved = True
        self._action = None
        self._drag_offset = None
        self._resize_edge = None
        self._resize_start_pos = None
        self._resize_start_geo = None
        event.accept()

    def _do_resize(self, global_pos: QPoint):
        dx = global_pos.x() - self._resize_start_pos.x()
        dy = global_pos.y() - self._resize_start_pos.y()
        geometry = QRect(self._resize_start_geo)
        edge = self._resize_edge

        if "R" in edge:
            geometry.setRight(geometry.right() + dx)
        if "L" in edge:
            geometry.setLeft(geometry.left() + dx)
        if "B" in edge:
            geometry.setBottom(geometry.bottom() + dy)
        if "T" in edge:
            geometry.setTop(geometry.top() + dy)

        width = max(self.minimumWidth(), min(geometry.width(), self.maximumWidth()))
        height = max(self.minimumHeight(), min(geometry.height(), self.maximumHeight()))
        if "L" in edge:
            geometry.setLeft(geometry.right() - width + 1)
        if "T" in edge:
            geometry.setTop(geometry.bottom() - height + 1)
        geometry.setWidth(width)
        geometry.setHeight(height)

        self.setGeometry(geometry)
        self.geometry_changed.emit()

    def moveEvent(self, event):
        super().moveEvent(event)
        self.geometry_changed.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_formula_render()
        self.geometry_changed.emit()

    def showEvent(self, event):
        super().showEvent(event)
        self.geometry_changed.emit()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.geometry_changed.emit()
