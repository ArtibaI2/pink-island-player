import os
import sys
import ctypes
import subprocess
import time
import urllib.request
import json
import base64
import winreg

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QHBoxLayout, QVBoxLayout, QSystemTrayIcon,
    QMenu
)
from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QRect, QPropertyAnimation,
    QEasingCurve, pyqtSignal, QSize, QPointF
)
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QPen, QPixmap, QImage,
    QIcon, QFont, QCursor, QLinearGradient, QPolygonF
)
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

# Registry constants for Windows Autostart
REG_AUTORUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "PinkIslandPlayer"
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "player_settings.json")
SOCKET_NAME = "PinkIslandPlayer_SingleInstance_V2"


def load_settings():
    default_settings = {
        "bg_alpha": 0,         # 0 = 100% transparent zero background fill!
        "dock_mode": "right",
        "is_pinned": False
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_settings.update(data)
        except Exception:
            pass
    return default_settings


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def set_windows_autostart(enable=True):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_AUTORUN, 0, winreg.KEY_SET_VALUE)
        if enable:
            vbs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "start_player.vbs"))
            cmd = f'wscript.exe "{vbs_path}"'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print("Autostart setting error:", e)
        return False


def is_windows_autostart_enabled():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_AUTORUN, 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return bool(val)
    except Exception:
        return False


def get_screen_resolution():
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)
    except Exception:
        return 1920, 1080


def create_media_icon(icon_type, color=QColor(255, 255, 255, 230), size=24):
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QBrush(color))
    p.setPen(Qt.PenStyle.NoPen)

    s = float(size)
    if icon_type == "prev":
        p.drawRoundedRect(int(s * 0.16), int(s * 0.22), int(s * 0.12), int(s * 0.56), 1, 1)
        poly = QPolygonF([
            QPointF(s * 0.82, s * 0.22),
            QPointF(s * 0.36, s * 0.50),
            QPointF(s * 0.82, s * 0.78)
        ])
        p.drawPolygon(poly)
    elif icon_type == "next":
        p.drawRoundedRect(int(s * 0.72), int(s * 0.22), int(s * 0.12), int(s * 0.56), 1, 1)
        poly = QPolygonF([
            QPointF(s * 0.18, s * 0.22),
            QPointF(s * 0.64, s * 0.50),
            QPointF(s * 0.18, s * 0.78)
        ])
        p.drawPolygon(poly)
    elif icon_type == "play":
        poly = QPolygonF([
            QPointF(s * 0.30, s * 0.22),
            QPointF(s * 0.78, s * 0.50),
            QPointF(s * 0.30, s * 0.78)
        ])
        p.drawPolygon(poly)
    elif icon_type == "pause":
        p.drawRoundedRect(int(s * 0.26), int(s * 0.22), int(s * 0.16), int(s * 0.56), 1, 1)
        p.drawRoundedRect(int(s * 0.58), int(s * 0.22), int(s * 0.16), int(s * 0.56), 1, 1)

    p.end()
    return QIcon(pix)


# Custom Clickable Progress Bar for Seeking
class ClickableProgressBar(QWidget):
    seekRequested = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(12)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.progress = 0.0  # 0.0 to 1.0

    def setProgress(self, val):
        self.progress = max(0.0, min(1.0, float(val)))
        self.update()

    def mousePressEvent(self, event):
        if self.width() > 0:
            ratio = max(0.0, min(1.0, event.position().x() / self.width()))
            self.seekRequested.emit(ratio)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        track_h = 5
        y = (h - track_h) // 2

        # Background track
        painter.setBrush(QColor(255, 255, 255, 35))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, y, w, track_h, 2.5, 2.5)

        # Pink gradient fill
        fill_w = int(w * self.progress)
        if fill_w > 0:
            grad = QLinearGradient(0, 0, fill_w, 0)
            grad.setColorAt(0.0, QColor(255, 45, 117))
            grad.setColorAt(1.0, QColor(255, 110, 160))
            painter.setBrush(grad)
            painter.drawRoundedRect(0, y, fill_w, track_h, 2.5, 2.5)

            # Thumb head
            painter.setBrush(QColor(255, 255, 255))
            painter.drawEllipse(max(0, fill_w - 5), y - 2, 9, 9)


# 24-Band Pink Audio Spectrum Visualizer
class SpectrumWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(26)
        self.spectrum = [0.05] * 24

    def setSpectrum(self, bars):
        if bars and len(bars) > 0:
            self.spectrum = bars[:24]
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        bars_count = len(self.spectrum)
        if bars_count == 0:
            return

        spacing = 3.0
        bar_w = max(2.0, (w - (bars_count - 1) * spacing) / bars_count)

        for i, val in enumerate(self.spectrum):
            x = i * (bar_w + spacing)
            bar_h = max(3.0, val * (h - 2))
            y = h - bar_h

            grad = QLinearGradient(x, y, x, h)
            grad.setColorAt(0.0, QColor(255, 105, 165))
            grad.setColorAt(1.0, QColor(255, 45, 117))

            painter.setBrush(grad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(int(x), int(y), int(bar_w), int(bar_h), 1.5, 1.5)


# Mini Equalizer in Collapsed Pill
class MiniEqWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(22, 16)
        self.is_playing = False
        self.step = 0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(90)

    def setPlaying(self, playing):
        self.is_playing = bool(playing)
        self.update()

    def animate(self):
        if self.is_playing:
            self.step = (self.step + 1) % 100
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        h = self.height()
        bar_w = 3.0
        gap = 2.5

        import math
        for i in range(4):
            x = i * (bar_w + gap)
            if self.is_playing:
                factor = (math.sin(self.step * 0.35 + i * 1.3) + 1.0) / 2.0
                bar_h = max(3.0, 3.0 + factor * (h - 4.0))
            else:
                bar_h = 3.0
            y = h - bar_h

            grad = QLinearGradient(x, y, x, h)
            grad.setColorAt(0.0, QColor(255, 115, 165))
            grad.setColorAt(1.0, QColor(255, 45, 117))

            painter.setBrush(grad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(int(x), int(y), int(bar_w), int(bar_h), 1.5, 1.5)


# Main Dynamic Island Player Window
class PinkIslandPlayer(QWidget):
    TRANSPARENCY_PRESETS = [
        ("100% Прозрачный (без фона)", 0),
        ("Кристально-прозрачный (15%)", 38),
        ("Прозрачное стекло (35% — Рекомендуется)", 85),
        ("Полупрозрачный (60%)", 150),
        ("Тёмное стекло (80%)", 205),
    ]

    def __init__(self, rust_proc=None):
        super().__init__()
        self.rust_proc = rust_proc
        self.settings = load_settings()
        self.dock_mode = self.settings.get("dock_mode", "right")
        self.bg_alpha = int(self.settings.get("bg_alpha", 0))  # Default 0 = 100% transparent
        self.is_expanded = False
        self.is_pinned = bool(self.settings.get("is_pinned", False))
        self.current_state = None
        self.tray_manager = None

        # Sizes
        self.pill_w = 230
        self.pill_h = 46
        self.expanded_w = 380
        self.expanded_h = 220

        # Enable true per-pixel alpha transparency and hide from Taskbar
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setMinimumSize(0, 0)

        # Dragging state
        self.is_dragging = False
        self.drag_start = QPoint()

        # Collapse timer
        self.collapse_timer = QTimer(self)
        self.collapse_timer.setSingleShot(True)
        self.collapse_timer.timeout.connect(self.collapse_island)

        # UI Setup
        self.init_ui()

        # Position to initial dock (right edge)
        self.snap_to_dock()

        # Start Rust API Poller
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll_rust_state)
        self.poll_timer.start(100)

    def set_background_transparency(self, alpha):
        self.bg_alpha = int(alpha)
        self.settings["bg_alpha"] = self.bg_alpha
        save_settings(self.settings)
        self.update()
        if self.tray_manager:
            self.tray_manager.update_transparency_ui()

    def cycle_transparency(self):
        alphas = [p[1] for p in self.TRANSPARENCY_PRESETS]
        try:
            idx = alphas.index(self.bg_alpha)
            next_alpha = alphas[(idx + 1) % len(alphas)]
        except ValueError:
            next_alpha = 0
        self.set_background_transparency(next_alpha)

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.setup_pill_view()
        self.setup_expanded_view()

        self.main_layout.addWidget(self.pill_container)
        self.main_layout.addWidget(self.exp_container)

        if self.is_pinned:
            self.is_expanded = True
            self.pill_container.hide()
            self.exp_container.show()
            self.setFixedSize(self.expanded_w, self.expanded_h)
        else:
            self.is_expanded = False
            self.exp_container.hide()
            self.pill_container.show()
            self.setFixedSize(self.pill_w, self.pill_h)

    # 1. Collapsed Pill View Setup
    def setup_pill_view(self):
        self.pill_container = QWidget(self)
        self.pill_container.setFixedSize(self.pill_w, self.pill_h)
        layout = QHBoxLayout(self.pill_container)
        layout.setContentsMargins(10, 6, 12, 6)
        layout.setSpacing(10)

        # Mini Cover Art (circle)
        self.pill_cover = QLabel(self.pill_container)
        self.pill_cover.setFixedSize(30, 30)
        self.pill_cover.setStyleSheet("border-radius: 15px; background: rgba(255, 45, 117, 0.4);")
        self.pill_cover.setScaledContents(True)
        layout.addWidget(self.pill_cover)

        # Track meta (Title & Artist)
        meta_layout = QVBoxLayout()
        meta_layout.setSpacing(1)
        meta_layout.setContentsMargins(0, 0, 0, 0)

        self.pill_title = QLabel("Подключение...", self.pill_container)
        self.pill_title.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 700; background: transparent;")
        meta_layout.addWidget(self.pill_title)

        self.pill_artist = QLabel("Ожидание аудио", self.pill_container)
        self.pill_artist.setStyleSheet("color: #ff65a3; font-size: 10px; font-weight: 500; background: transparent;")
        meta_layout.addWidget(self.pill_artist)

        layout.addLayout(meta_layout, 1)

        # Mini Equalizer
        self.mini_eq = MiniEqWidget(self.pill_container)
        layout.addWidget(self.mini_eq)

    # 2. Expanded Player View Setup
    def setup_expanded_view(self):
        self.exp_container = QWidget(self)
        self.exp_container.setFixedSize(self.expanded_w, self.expanded_h)
        layout = QVBoxLayout(self.exp_container)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        # Top Header Bar
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)

        self.status_dot = QLabel(self.exp_container)
        self.status_dot.setFixedSize(8, 8)
        self.status_dot.setStyleSheet("border-radius: 4px; background: #ff2d75;")
        header.addWidget(self.status_dot)

        self.app_badge = QLabel("WINDOWS AUDIO", self.exp_container)
        self.app_badge.setStyleSheet("color: rgba(255, 230, 240, 0.7); font-size: 10px; font-weight: 700; letter-spacing: 0.5px; background: transparent;")
        header.addWidget(self.app_badge)

        header.addStretch(1)

        btn_style = """
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: rgba(255, 255, 255, 0.6);
                border: none;
                border-radius: 6px;
                font-size: 10px;
                padding: 3px 6px;
            }
            QPushButton:hover {
                background: rgba(255, 45, 117, 0.3);
                color: #ffffff;
            }
        """

        # Dock mode buttons: Left, Top, Right, Float
        self.btn_dock_left = QPushButton("◄", self.exp_container)
        self.btn_dock_left.setStyleSheet(btn_style)
        self.btn_dock_left.setToolTip("Прикрепить слева")
        self.btn_dock_left.clicked.connect(lambda: self.set_dock_mode("left"))
        header.addWidget(self.btn_dock_left)

        self.btn_dock_top = QPushButton("▲", self.exp_container)
        self.btn_dock_top.setStyleSheet(btn_style)
        self.btn_dock_top.setToolTip("Остров сверху (Dynamic Island)")
        self.btn_dock_top.clicked.connect(lambda: self.set_dock_mode("top"))
        header.addWidget(self.btn_dock_top)

        self.btn_dock_right = QPushButton("►", self.exp_container)
        self.btn_dock_right.setStyleSheet(btn_style)
        self.btn_dock_right.setToolTip("Прикрепить справа")
        self.btn_dock_right.clicked.connect(lambda: self.set_dock_mode("right"))
        header.addWidget(self.btn_dock_right)

        self.btn_dock_float = QPushButton("✦", self.exp_container)
        self.btn_dock_float.setStyleSheet(btn_style)
        self.btn_dock_float.setToolTip("Свободный режим")
        self.btn_dock_float.clicked.connect(lambda: self.set_dock_mode("float"))
        header.addWidget(self.btn_dock_float)

        # Quick Transparency Toggle Button
        self.btn_trans = QPushButton("💎", self.exp_container)
        self.btn_trans.setStyleSheet(btn_style)
        self.btn_trans.setToolTip("Прозрачность фона (нажмите для смены режима)")
        self.btn_trans.clicked.connect(self.cycle_transparency)
        header.addWidget(self.btn_trans)

        # Pin button
        self.btn_pin = QPushButton("📌", self.exp_container)
        if self.is_pinned:
            self.btn_pin.setStyleSheet("background: #ff2d75; color: #fff; border-radius: 6px; padding: 3px 6px; border: none; font-size: 10px;")
        else:
            self.btn_pin.setStyleSheet(btn_style)
        self.btn_pin.setToolTip("Закрепить открытым")
        self.btn_pin.clicked.connect(self.toggle_pin)
        header.addWidget(self.btn_pin)

        # Close / Minimize button
        self.btn_close = QPushButton("✕", self.exp_container)
        self.btn_close.setStyleSheet(btn_style)
        self.btn_close.setToolTip("Свернуть плеер")
        self.btn_close.clicked.connect(self.collapse_island)
        header.addWidget(self.btn_close)

        layout.addLayout(header)

        # Track Info Row (Cover Art + Title + Artist)
        track_row = QHBoxLayout()
        track_row.setSpacing(12)

        self.main_cover = QLabel(self.exp_container)
        self.main_cover.setFixedSize(54, 54)
        self.main_cover.setStyleSheet("border-radius: 14px; background: rgba(255, 45, 117, 0.3); border: 1px solid rgba(255, 45, 117, 0.4);")
        self.main_cover.setScaledContents(True)
        track_row.addWidget(self.main_cover)

        details_layout = QVBoxLayout()
        details_layout.setSpacing(2)
        details_layout.setContentsMargins(0, 0, 0, 0)

        self.main_title = QLabel("Загрузка трека...", self.exp_container)
        self.main_title.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: 800; background: transparent;")
        details_layout.addWidget(self.main_title)

        self.main_artist = QLabel("Ожидание аудиопотока", self.exp_container)
        self.main_artist.setStyleSheet("color: #ff65a3; font-size: 12px; font-weight: 600; background: transparent;")
        details_layout.addWidget(self.main_artist)

        self.main_album = QLabel("", self.exp_container)
        self.main_album.setStyleSheet("color: rgba(255, 200, 220, 0.5); font-size: 11px; background: transparent;")
        details_layout.addWidget(self.main_album)

        track_row.addLayout(details_layout, 1)
        layout.addLayout(track_row)

        # 24-Band Spectrum Visualizer
        self.spectrum_widget = SpectrumWidget(self.exp_container)
        layout.addWidget(self.spectrum_widget)

        # Timeline Seek Bar
        self.progress_bar = ClickableProgressBar(self.exp_container)
        self.progress_bar.seekRequested.connect(self.on_seek_requested)
        layout.addWidget(self.progress_bar)

        time_row = QHBoxLayout()
        self.time_current = QLabel("0:00", self.exp_container)
        self.time_current.setStyleSheet("color: rgba(255, 230, 240, 0.7); font-size: 10px; font-weight: 600; background: transparent;")
        time_row.addWidget(self.time_current)

        time_row.addStretch(1)

        self.time_total = QLabel("-0:00", self.exp_container)
        self.time_total.setStyleSheet("color: rgba(255, 230, 240, 0.7); font-size: 10px; font-weight: 600; background: transparent;")
        time_row.addWidget(self.time_total)

        layout.addLayout(time_row)

        # Playback Controls Row
        ctrl_row = QHBoxLayout()
        ctrl_row.setContentsMargins(0, 2, 0, 0)
        ctrl_row.setSpacing(14)

        ctrl_row.addStretch(1)

        ctrl_btn_style = """
            QPushButton {
                background: rgba(255, 255, 255, 0.06);
                border: none;
                border-radius: 18px;
            }
            QPushButton:hover {
                background: rgba(255, 45, 117, 0.3);
            }
        """
        self.btn_prev = QPushButton(self.exp_container)
        self.btn_prev.setIcon(create_media_icon("prev", size=22))
        self.btn_prev.setIconSize(QSize(20, 20))
        self.btn_prev.setStyleSheet(ctrl_btn_style)
        self.btn_prev.setFixedSize(36, 36)
        self.btn_prev.clicked.connect(lambda: self.send_command("prev"))
        ctrl_row.addWidget(self.btn_prev)

        self.btn_play = QPushButton(self.exp_container)
        self.btn_play.setIcon(create_media_icon("play", color=QColor(255, 255, 255), size=24))
        self.btn_play.setIconSize(QSize(22, 22))
        self.btn_play.setFixedSize(42, 42)
        self.btn_play.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff2d75, stop:1 #ff758c);
                border-radius: 21px;
                border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff4b8d, stop:1 #ff8da0);
            }
        """)
        self.btn_play.clicked.connect(lambda: self.send_command("toggle"))
        ctrl_row.addWidget(self.btn_play)

        self.btn_next = QPushButton(self.exp_container)
        self.btn_next.setIcon(create_media_icon("next", size=22))
        self.btn_next.setIconSize(QSize(20, 20))
        self.btn_next.setStyleSheet(ctrl_btn_style)
        self.btn_next.setFixedSize(36, 36)
        self.btn_next.clicked.connect(lambda: self.send_command("next"))
        ctrl_row.addWidget(self.btn_next)

        ctrl_row.addStretch(1)

        layout.addLayout(ctrl_row)

    # Background Painting: Per-pixel alpha transparency + Glowing Pink Border
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        radius = 23.0 if not self.is_expanded else 26.0

        # Dynamic glass background fill based on selected transparency
        if self.bg_alpha > 0:
            glass_grad = QLinearGradient(0, 0, 0, rect.height())
            glass_grad.setColorAt(0.0, QColor(255, 255, 255, min(255, int(self.bg_alpha * 0.35))))
            glass_grad.setColorAt(0.12, QColor(22, 12, 28, self.bg_alpha))
            glass_grad.setColorAt(1.0, QColor(10, 5, 16, self.bg_alpha))
            painter.setBrush(QBrush(glass_grad))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)

        border_alpha = 180 if self.bg_alpha == 0 else 140
        border_pen = QPen(QColor(255, 45, 117, border_alpha), 1.5)
        painter.setPen(border_pen)
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius, radius)

    # Snap / Docking Logic
    def snap_to_dock(self):
        screen_w, screen_h = get_screen_resolution()
        cur_w = self.expanded_w if self.is_expanded else self.pill_w
        cur_h = self.expanded_h if self.is_expanded else self.pill_h

        if self.dock_mode == "right":
            x = screen_w - cur_w - 15
            y = int((screen_h - cur_h) * 0.45)
        elif self.dock_mode == "left":
            x = 15
            y = int((screen_h - cur_h) * 0.45)
        elif self.dock_mode == "top":
            x = int((screen_w - cur_w) / 2)
            y = 12
        else:
            x = self.x()
            y = self.y()

        self.setGeometry(x, y, cur_w, cur_h)
        self.setFixedSize(cur_w, cur_h)

    def set_dock_mode(self, mode):
        self.dock_mode = mode
        self.settings["dock_mode"] = mode
        save_settings(self.settings)
        self.snap_to_dock()

    # Expand / Collapse with Smooth Geometry Animation
    def expand_island(self):
        self.collapse_timer.stop()
        if not self.is_expanded:
            self.is_expanded = True
            self.pill_container.hide()
            self.exp_container.show()
            self.animate_geometry(self.expanded_w, self.expanded_h, on_finish=lambda: self.setFixedSize(self.expanded_w, self.expanded_h))

    def collapse_island(self):
        if self.is_pinned:
            return
        if self.is_expanded:
            self.is_expanded = False
            self.animate_geometry(self.pill_w, self.pill_h, on_finish=self._on_collapse_finished)

    def _on_collapse_finished(self):
        if not self.is_expanded:
            self.exp_container.hide()
            self.pill_container.show()
            self.setFixedSize(self.pill_w, self.pill_h)

    def animate_geometry(self, target_w, target_h, on_finish=None):
        screen_w, _ = get_screen_resolution()
        cur_geom = self.geometry()

        if self.dock_mode == "right":
            target_x = screen_w - target_w - 15
            target_y = cur_geom.y()
        elif self.dock_mode == "top":
            target_x = int((screen_w - target_w) / 2)
            target_y = 12
        elif self.dock_mode == "left":
            target_x = 15
            target_y = cur_geom.y()
        else:
            target_x = cur_geom.x()
            target_y = cur_geom.y()

        target_geom = QRect(target_x, target_y, target_w, target_h)

        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)

        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(260)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.setStartValue(cur_geom)
        self.anim.setEndValue(target_geom)
        if on_finish:
            self.anim.finished.connect(on_finish)
        self.anim.start()

    def toggle_pin(self):
        self.is_pinned = not self.is_pinned
        self.settings["is_pinned"] = self.is_pinned
        save_settings(self.settings)
        if self.is_pinned:
            self.btn_pin.setStyleSheet("background: #ff2d75; color: #fff; border-radius: 6px; padding: 3px 6px; border: none; font-size: 10px;")
            self.expand_island()
        else:
            self.btn_pin.setStyleSheet("background: rgba(255, 255, 255, 0.08); color: rgba(255, 255, 255, 0.6); border-radius: 6px; padding: 3px 6px; border: none; font-size: 10px;")

    # Hover detection
    def enterEvent(self, event):
        self.expand_island()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.is_pinned:
            self.collapse_timer.start(350)
        super().leaveEvent(event)

    # Drag & Drop handling
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.drag_start = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            self.dock_mode = "float"
            self.move(event.globalPosition().toPoint() - self.drag_start)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.is_dragging = False
        super().mouseReleaseEvent(event)

    # API Communication with Rust Core
    def send_command(self, cmd):
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:48123/api/command?cmd={cmd}",
                data=b"",
                method="POST"
            )
            urllib.request.urlopen(req, timeout=0.5)
        except Exception:
            pass

    def on_seek_requested(self, ratio):
        if self.current_state and self.current_state.get("duration_sec"):
            sec = ratio * self.current_state["duration_sec"]
            self.send_command(f"seek:{sec:.1f}")

    # Polling Rust API State
    def poll_rust_state(self):
        try:
            req = urllib.request.urlopen("http://127.0.0.1:48123/api/state", timeout=0.25)
            data = json.loads(req.read().decode())
            self.current_state = data
            self.update_ui_state(data)
        except Exception:
            pass

    def update_ui_state(self, data):
        title = data.get("title") or "Нет воспроизведения"
        artist = data.get("artist") or "Ожидание аудио..."
        album = data.get("album") or ""
        app_id = data.get("app_id") or ""
        is_playing = bool(data.get("is_playing"))
        pos = data.get("position_sec") or 0.0
        dur = max(1.0, data.get("duration_sec") or 180.0)

        # Pill meta
        self.pill_title.setText(title[:26] + ("..." if len(title) > 26 else ""))
        self.pill_artist.setText(artist[:22] + ("..." if len(artist) > 22 else ""))
        self.mini_eq.setPlaying(is_playing)

        # Expanded meta
        self.main_title.setText(title[:34] + ("..." if len(title) > 34 else ""))
        self.main_artist.setText(artist[:30] + ("..." if len(artist) > 30 else ""))
        self.main_album.setText(album[:35] if album else "")

        # Format App name
        clean_app = app_id.split('\\')[-1].replace('.exe', '').upper()
        if "SPOTIFY" in clean_app: clean_app = "SPOTIFY"
        elif "CHROME" in clean_app: clean_app = "CHROME / YOUTUBE"
        elif "YANDEX" in clean_app: clean_app = "ЯНДЕКС МУЗЫКА"
        elif "VK" in clean_app: clean_app = "VK МУЗЫКА"
        elif "TELEGRAM" in clean_app: clean_app = "TELEGRAM"
        self.app_badge.setText(clean_app if clean_app else "WINDOWS AUDIO")

        # Status dot & Play button
        if is_playing:
            self.status_dot.setStyleSheet("border-radius: 4px; background: #30d158;")
            self.btn_play.setIcon(create_media_icon("pause", color=QColor(255, 255, 255), size=24))
        else:
            self.status_dot.setStyleSheet("border-radius: 4px; background: #ff2d75;")
            self.btn_play.setIcon(create_media_icon("play", color=QColor(255, 255, 255), size=24))

        # Timeline
        ratio = max(0.0, min(1.0, pos / dur))
        self.progress_bar.setProgress(ratio)

        def fmt_time(sec):
            m = int(sec // 60)
            s = int(sec % 60)
            return f"{m}:{s:02d}"

        self.time_current.setText(fmt_time(pos))
        rem = max(0.0, dur - pos)
        self.time_total.setText(f"-{fmt_time(rem)}")

        # Spectrum
        if "spectrum" in data:
            self.spectrum_widget.setSpectrum(data["spectrum"])

        # Artwork
        thumb_b64 = data.get("thumbnail_b64")
        if thumb_b64 and "," in thumb_b64:
            try:
                raw_data = base64.b64decode(thumb_b64.split(",", 1)[1])
                img = QImage.fromData(raw_data)
                if not img.isNull():
                    pix = QPixmap.fromImage(img)
                    self.pill_cover.setPixmap(pix)
                    self.main_cover.setPixmap(pix)
            except Exception:
                pass


# System Tray Icon Creation & Management
class SystemTrayManager:
    def __init__(self, player_window):
        self.win = player_window
        self.win.tray_manager = self

        self.tray = QSystemTrayIcon()
        self.tray.setIcon(self.generate_pink_icon())
        self.tray.setToolTip("Pink Island Player")

        # Context Menu
        self.menu = QMenu()
        self.menu.setStyleSheet("""
            QMenu {
                background: #18121c;
                color: #ffffff;
                border: 1px solid rgba(255, 45, 117, 0.4);
                border-radius: 8px;
                padding: 6px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: rgba(255, 45, 117, 0.35);
            }
            QMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 0.1);
                margin: 4px 6px;
            }
        """)

        # Actions
        act_toggle = self.menu.addAction("🎵 Показать / Скрыть плеер")
        act_toggle.triggered.connect(self.toggle_player)

        self.act_pin = self.menu.addAction("📌 Закрепить открытым")
        self.act_pin.setCheckable(True)
        self.act_pin.setChecked(self.win.is_pinned)
        self.act_pin.triggered.connect(self.win.toggle_pin)

        self.menu.addSeparator()

        # Transparency Submenu
        trans_menu = self.menu.addMenu("💎 Прозрачность фона")
        trans_menu.setStyleSheet(self.menu.styleSheet())
        self.trans_actions = {}
        for label, a_val in self.win.TRANSPARENCY_PRESETS:
            act = trans_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(self.win.bg_alpha == a_val)
            act.triggered.connect(lambda checked, a=a_val: self.win.set_background_transparency(a))
            self.trans_actions[a_val] = act

        # Dock Submenu
        dock_menu = self.menu.addMenu("🧭 Положение на экране")
        dock_menu.setStyleSheet(self.menu.styleSheet())

        act_right = dock_menu.addAction("Справа у края (По умолчанию)")
        act_right.triggered.connect(lambda: self.win.set_dock_mode("right"))

        act_top = dock_menu.addAction("Сверху (Dynamic Island)")
        act_top.triggered.connect(lambda: self.win.set_dock_mode("top"))

        act_left = dock_menu.addAction("Слева у края")
        act_left.triggered.connect(lambda: self.win.set_dock_mode("left"))

        act_float = dock_menu.addAction("Свободный режим")
        act_float.triggered.connect(lambda: self.win.set_dock_mode("float"))

        self.menu.addSeparator()

        # Autostart Action
        self.act_autostart = self.menu.addAction("⚡ Автозагрузка при старте Windows")
        self.act_autostart.setCheckable(True)
        self.act_autostart.setChecked(is_windows_autostart_enabled())
        self.act_autostart.triggered.connect(self.toggle_autostart)

        self.menu.addSeparator()

        act_exit = self.menu.addAction("❌ Выход")
        act_exit.triggered.connect(self.exit_app)

        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

    def update_transparency_ui(self):
        for a_val, act in self.trans_actions.items():
            act.setChecked(self.win.bg_alpha == a_val)

    def generate_pink_icon(self):
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Glowing pink background circle
        painter.setBrush(QColor(255, 45, 117))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 28, 28)

        # White musical note
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawLine(12, 10, 12, 22)
        painter.drawLine(20, 7, 20, 19)
        painter.drawLine(12, 10, 20, 7)

        painter.setBrush(QColor(255, 255, 255))
        painter.drawEllipse(8, 19, 5, 4)
        painter.drawEllipse(16, 16, 5, 4)
        painter.end()

        return QIcon(pixmap)

    def toggle_player(self):
        if self.win.isVisible():
            self.win.hide()
        else:
            self.win.show()
            self.win.raise_()

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_player()

    def toggle_autostart(self):
        cur = is_windows_autostart_enabled()
        set_windows_autostart(not cur)
        self.act_autostart.setChecked(not cur)

    def exit_app(self):
        self.tray.hide()
        if self.win.rust_proc:
            try:
                self.win.rust_proc.terminate()
            except Exception:
                pass
        QApplication.quit()


def start_rust_core():
    rust_binary = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "pink_core", "target", "release", "pink_core.exe")
    )
    if not os.path.exists(rust_binary):
        return None

    # Check if already running on port 48123
    try:
        urllib.request.urlopen("http://127.0.0.1:48123/api/state", timeout=0.2)
        return None
    except Exception:
        pass

    try:
        creation_flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        proc = subprocess.Popen(
            [rust_binary],
            creationflags=creation_flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(0.4)
        return proc
    except Exception as e:
        print("Failed to start Rust daemon:", e)
        return None


def main():
    # 1. Enable Windows Autostart on startup
    if not is_windows_autostart_enabled():
        set_windows_autostart(True)

    # 2. Check Single Instance Guard via Windows Named Mutex
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "PinkIslandPlayer_NamedMutex_App")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        sys.exit(0)

    # 3. Launch Rust Daemon
    rust_proc = start_rust_core()

    # 4. Start Qt App
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Keep running in system tray

    player = PinkIslandPlayer(rust_proc)
    player.show()

    tray = SystemTrayManager(player)

    exit_code = app.exec()
    if mutex:
        ctypes.windll.kernel32.CloseHandle(mutex)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
