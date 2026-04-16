"""底部悬浮分析窗（可拖动 + 可调节大小）。"""

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QCursor, QFont, QMouseEvent, QScreen
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget

# 边缘热区宽度（像素），鼠标进入此范围显示 resize 光标
EDGE = 7
# 左侧手柄宽度
HANDLE_WIDTH = 28


class SubtitleBar(QWidget):
    """悬浮字幕条

    - 左侧 ⠿ 手柄拖动移动位置
    - 四边/四角拖动调节大小，鼠标自动变为对应箭头
    - 无边框、半透明深色背景、圆角、始终置顶
    """

    _CURSORS = {
        "L":  Qt.CursorShape.SizeHorCursor,
        "R":  Qt.CursorShape.SizeHorCursor,
        "T":  Qt.CursorShape.SizeVerCursor,
        "B":  Qt.CursorShape.SizeVerCursor,
        "TL": Qt.CursorShape.SizeFDiagCursor,
        "BR": Qt.CursorShape.SizeFDiagCursor,
        "TR": Qt.CursorShape.SizeBDiagCursor,
        "BL": Qt.CursorShape.SizeBDiagCursor,
    }

    geometry_changed = Signal()

    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)

        self.setMinimumSize(320, 90)
        self.setMaximumSize(1600, 400)

        # 交互状态
        self._action = None      # "move" | "resize"
        self._drag_offset = None
        self._resize_edge = None
        self._resize_start_pos = None
        self._resize_start_geo = None

        # 外层水平布局：手柄 + 内容
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 左侧拖动手柄
        self._handle = QLabel("⠿")
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

        # 内容容器
        self._container = QWidget()
        self._container.setMouseTracking(True)
        self._container.setStyleSheet(
            "background-color: rgba(30, 30, 30, 200);"
            "border-top-right-radius: 12px; border-bottom-right-radius: 12px;"
        )

        content_layout = QVBoxLayout(self._container)
        content_layout.setContentsMargins(20, 10, 24, 10)
        content_layout.setSpacing(4)

        # 主标题
        self._line1 = QLabel("ScreenLens 已启动，等待屏幕变化...")
        self._line1.setFont(QFont("Microsoft YaHei", 14))
        self._line1.setStyleSheet("color: white; background: transparent;")
        self._line1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._line1.setWordWrap(True)
        self._line1.setMouseTracking(True)
        content_layout.addWidget(self._line1)

        # 副标题
        self._line2 = QLabel("")
        self._line2.setFont(QFont("Microsoft YaHei", 11))
        self._line2.setStyleSheet("color: rgba(255,255,255,180); background: transparent;")
        self._line2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._line2.setWordWrap(True)
        self._line2.setMouseTracking(True)
        self._line2.hide()
        content_layout.addWidget(self._line2)

        # 摘要
        self._summary = QLabel("")
        self._summary.setFont(QFont("Microsoft YaHei", 10))
        self._summary.setStyleSheet("color: rgba(255,255,255,205); background: transparent;")
        self._summary.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._summary.setWordWrap(True)
        self._summary.setMouseTracking(True)
        self._summary.hide()
        content_layout.addWidget(self._summary)

        # 关键点和下一步
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

    # --- 公开接口 ---

    def update_subtitle(
        self,
        line1: str,
        line2: str = "",
        summary: str = "",
        key_points: list[str] | None = None,
        next_action: str = "",
    ):
        self._line1.setText(line1 if line1 else "")
        if line2:
            self._line2.setText(line2)
            self._line2.show()
        else:
            self._line2.hide()

        if summary:
            self._summary.setText(summary)
            self._summary.show()
        else:
            self._summary.hide()

        detail_lines: list[str] = []
        if key_points:
            detail_lines.extend(f"• {point}" for point in key_points if point)
        if next_action:
            detail_lines.append(f"下一步：{next_action}")

        if detail_lines:
            self._detail.setText("\n".join(detail_lines))
            self._detail.show()
        else:
            self._detail.hide()

        target_height = 100
        if line2:
            target_height += 18
        if summary:
            target_height += 56
        if detail_lines:
            target_height += min(110, 22 * len(detail_lines))
        target_height = max(self.minimumHeight(), min(target_height, self.maximumHeight()))
        self.resize(self.width(), target_height)
        self.geometry_changed.emit()

    # --- 初始定位 ---

    def _reposition(self):
        screen: QScreen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        w, h = 620, 150
        x = geo.x() + (geo.width() - w) // 2
        y = geo.y() + geo.height() - h - 48
        self.resize(w, h)
        self.move(x, y)
        self.geometry_changed.emit()

    # --- 区域检测 ---

    def _edge_at(self, pos: QPoint) -> str | None:
        """返回鼠标所在的边/角标识"""
        x, y, w, h = pos.x(), pos.y(), self.width(), self.height()
        on_l = x < EDGE
        on_r = x > w - EDGE
        on_t = y < EDGE
        on_b = y > h - EDGE

        if on_t and on_l: return "TL"
        if on_t and on_r: return "TR"
        if on_b and on_l: return "BL"
        if on_b and on_r: return "BR"
        if on_l: return "L"
        if on_r: return "R"
        if on_t: return "T"
        if on_b: return "B"
        return None

    def _on_handle(self, pos: QPoint) -> bool:
        """判断鼠标是否在左侧手柄区域（排除边缘热区）"""
        return EDGE <= pos.x() < HANDLE_WIDTH and EDGE <= pos.y() < self.height() - EDGE

    # --- 鼠标事件 ---

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
        # 正在拖动
        if event.buttons() & Qt.MouseButton.LeftButton:
            if self._action == "resize":
                self._do_resize(event.globalPosition().toPoint())
            elif self._action == "move" and self._drag_offset:
                self.move(event.globalPosition().toPoint() - self._drag_offset)
                self._user_moved = True
                self.geometry_changed.emit()
            event.accept()
            return

        # 悬停：更新光标
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

    # --- resize 计算 ---

    def _do_resize(self, gpos: QPoint):
        dx = gpos.x() - self._resize_start_pos.x()
        dy = gpos.y() - self._resize_start_pos.y()
        g = QRect(self._resize_start_geo)
        e = self._resize_edge

        if "R" in e: g.setRight(g.right() + dx)
        if "L" in e: g.setLeft(g.left() + dx)
        if "B" in e: g.setBottom(g.bottom() + dy)
        if "T" in e: g.setTop(g.top() + dy)

        w = max(self.minimumWidth(), min(g.width(), self.maximumWidth()))
        h = max(self.minimumHeight(), min(g.height(), self.maximumHeight()))
        if "L" in e: g.setLeft(g.right() - w + 1)
        if "T" in e: g.setTop(g.bottom() - h + 1)
        g.setWidth(w)
        g.setHeight(h)

        self.setGeometry(g)
        self.geometry_changed.emit()

    def moveEvent(self, event):
        super().moveEvent(event)
        self.geometry_changed.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.geometry_changed.emit()

    def showEvent(self, event):
        super().showEvent(event)
        self.geometry_changed.emit()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.geometry_changed.emit()
