import sys
import os
from dataclasses import dataclass, field
from pathlib import Path

from PyQt5.QtCore import Qt, QPoint, QTimer, QSize, QRect
from PyQt5.QtGui import (
    QColor, QPainter, QPen, QCursor, QIcon, QPixmap,
    QLinearGradient, QPainterPath
)
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QSlider,
    QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGraphicsDropShadowEffect
)

os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

# ── Asset dizinini bul ────────────────────────────────────────────────
def _asset_dir() -> Path:
    """PyInstaller bundle içinde / normal script çalışmasında asset dizinini döndür."""
    if getattr(sys, 'frozen', False):
        # PyInstaller ile paketlenmiş: executable'ın yanı
        return Path(sys.executable).parent.resolve()
    else:
        # Normal python çalıştırması: bu dosyanın yanı
        return Path(__file__).parent.resolve()

_ASSETS = _asset_dir()


@dataclass
class Stroke:
    color:  QColor
    width:  int
    points: list = field(default_factory=list)


class ColorBtn(QPushButton):
    def __init__(self, color: str, name: str):
        super().__init__()
        self.setFixedSize(24, 24)
        self.setToolTip(name)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {color};
                border: 2px solid rgba(0,0,0,0.25);
                border-radius: 12px;
            }}
            QPushButton:hover  {{ border: 2px solid #fff; }}
            QPushButton:pressed{{ border: 2px solid #adf; }}
        """)


class ToolBtn(QPushButton):
    def __init__(self, icon_path: str, tip: str, fallback: str = ""):
        super().__init__()
        self.setFixedSize(40, 40)
        self.setToolTip(tip)
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)
        self.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.0);
                border: none;
                border-radius: 8px;
                font-size: 16px;
                color: #333;
            }
            QPushButton:hover   { background: rgba(100,160,255,0.18); }
            QPushButton:pressed { background: rgba(100,160,255,0.35); }
            QPushButton:checked {
                background: rgba(100,160,255,0.28);
                border: 2px solid rgba(80,140,255,0.7);
            }
        """)
        p = Path(icon_path)
        if p.exists():
            self.setIcon(QIcon(str(p)))
            self.setIconSize(QSize(26, 26))
        else:
            self.setText(fallback or tip[:2])


class Toolbar(QWidget):
    FRICTION = 0.88
    BOUNCE   = 0.65
    MIN_VEL  = 0.8
    FRAME_MS = 16

    def __init__(self, parent: "DrawingWindow"):
        super().__init__(parent)
        self._win = parent
        self._bubble: QWidget | None = None

        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._panel = QFrame(self)
        self._panel.setObjectName("panel")
        self._panel.setStyleSheet("""
            QFrame#panel {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f8f9fc, stop:1 #e8eaf0
                );
                border-radius: 14px;
                border: 1px solid #c0c4d0;
            }
        """)

        vbox = QVBoxLayout(self._panel)
        vbox.setContentsMargins(6, 10, 6, 10)
        vbox.setSpacing(3)

        def mk(icon, tip, fb):
            b = ToolBtn(str(_ASSETS / icon), tip, fb)
            vbox.addWidget(b, alignment=Qt.AlignHCenter)
            return b

        self.btn_pen    = mk("pen.png",    "Kalem",   "✏️")
        self.btn_finger = mk("finger.png", "Parmak",  "👆")
        self.btn_eraser = mk("eraser.png", "Silgi",   "⌫")
        self.btn_clear  = mk("clear.png",  "Temizle", "🗑")

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("border:none; background:#bbb; max-height:1px;")
        vbox.addSpacing(3)
        vbox.addWidget(sep)
        vbox.addSpacing(3)

        self.btn_quit = mk("quit.png", "Çıkış", "✕")
        self.btn_quit.setCheckable(False)

        lbl = QLabel("by Kerim\nv0.1")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color:#aaa; font-size:7px; background:transparent;")
        vbox.addWidget(lbl)

        self._panel.adjustSize()
        self.resize(self._panel.size())

        self.btn_pen.clicked.connect(self._on_pen)
        self.btn_finger.clicked.connect(self._on_finger)
        self.btn_eraser.clicked.connect(self._on_eraser)
        self.btn_clear.clicked.connect(self._on_clear)
        self.btn_quit.clicked.connect(QApplication.quit)

        self._drag_off = QPoint()
        self._vel      = [0.0, 0.0]
        self._hx: list[float] = []
        self._hy: list[float] = []
        self._ptimer = QTimer(self)
        self._ptimer.timeout.connect(self._physics_tick)

        self.move(20, 200)
        self.raise_()

    def resizeEvent(self, _):
        self._panel.resize(self.size())

    def _uncheck(self):
        for b in (self.btn_pen, self.btn_finger, self.btn_eraser):
            b.setChecked(False)

    def _close_bubble(self):
        if self._bubble:
            try:
                self._bubble.close()
            except Exception:
                pass
            self._bubble = None

    def _on_pen(self):
        self._uncheck(); self.btn_pen.setChecked(True)
        self._close_bubble()
        self._win.set_mode("pen")
        self._bubble = self._make_pen_bubble()

    def _on_finger(self):
        self._uncheck(); self.btn_finger.setChecked(True)
        self._close_bubble()
        self._win.set_mode("finger")

    def _on_eraser(self):
        self._uncheck(); self.btn_eraser.setChecked(True)
        self._close_bubble()
        self._win.set_mode("eraser")
        self._bubble = self._make_eraser_bubble()

    def _on_clear(self):
        self._win.clear()
        self._close_bubble()

    def _bubble_base(self) -> QWidget:
        b = QWidget(self._win)
        b.setAutoFillBackground(True)
        b.setStyleSheet("""
            QWidget {
                background: #f7f8fc;
                border: 1px solid #bbb;
                border-radius: 8px;
            }
            QLabel  { border:none; background:transparent; font-size:9px; color:#444; }
            QSlider::groove:horizontal {
                height: 5px; background: #ddd; border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width:13px; height:13px; background:#557;
                border-radius:6px; margin:-4px 0;
            }
        """)
        return b

    def _place_bubble(self, b: QWidget):
        tx = self.x() + self.width() + 6
        ty = self.y()
        sw = self._win.width()
        if tx + b.width() > sw:
            tx = self.x() - b.width() - 6
        b.move(max(0, tx), max(0, ty))
        b.show()
        b.raise_()

    def _make_pen_bubble(self) -> QWidget:
        b = self._bubble_base()
        lay = QVBoxLayout(b)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        row = QHBoxLayout(); row.setSpacing(4)
        for name, hx in [
            ("Cyan",    "#00ffff"), ("Kırmızı", "#ff4444"),
            ("Mavi",    "#4488ff"), ("Yeşil",   "#44dd88"),
            ("Sarı",    "#ffee00"), ("Turuncu", "#ff9900"),
            ("Beyaz",   "#ffffff"), ("Siyah",   "#222222"),
        ]:
            cb = ColorBtn(hx, name)
            c  = QColor(hx)
            cb.clicked.connect(lambda _, col=c, bref=b: self._pick_color(col, bref))
            row.addWidget(cb)
        lay.addLayout(row)

        lay.addWidget(QLabel("Kalınlık"))
        sl = QSlider(Qt.Horizontal)
        sl.setRange(2, 30)
        sl.setValue(self._win.pen_width)
        sl.valueChanged.connect(lambda v: setattr(self._win, "pen_width", v))
        lay.addWidget(sl)

        b.adjustSize()
        self._place_bubble(b)
        return b

    def _make_eraser_bubble(self) -> QWidget:
        b = self._bubble_base()
        lay = QVBoxLayout(b)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        lay.addWidget(QLabel("Silgi boyutu"))
        sl = QSlider(Qt.Horizontal)
        sl.setRange(8, 80)
        sl.setValue(self._win.eraser_radius)
        sl.valueChanged.connect(
            lambda v: setattr(self._win, "eraser_radius", v))
        lay.addWidget(sl)
        b.adjustSize()
        self._place_bubble(b)
        return b

    def _pick_color(self, color: QColor, bubble: QWidget):
        self._win.pen_color = color
        bubble.close()
        self._bubble = None
        self._win.set_mode("pen")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_off = event.pos()
            self._hx.clear(); self._hy.clear()
            self._ptimer.stop()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            delta = event.pos() - self._drag_off
            new_pos = self.pos() + delta
            pw = self._win.width()
            ph = self._win.height()
            nx = max(0, min(new_pos.x(), pw - self.width()))
            ny = max(0, min(new_pos.y(), ph - self.height()))
            self.move(nx, ny)
            self._hx.append(float(delta.x()))
            self._hy.append(float(delta.y()))
            if len(self._hx) > 6:
                self._hx.pop(0); self._hy.pop(0)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._hx:
            self._vel[0] = sum(self._hx[-3:]) / len(self._hx[-3:]) * 3
            self._vel[1] = sum(self._hy[-3:]) / len(self._hy[-3:]) * 3
        if abs(self._vel[0]) > self.MIN_VEL or abs(self._vel[1]) > self.MIN_VEL:
            self._ptimer.start(self.FRAME_MS)
        event.accept()

    def _physics_tick(self):
        self._vel[0] *= self.FRICTION
        self._vel[1] *= self.FRICTION
        if abs(self._vel[0]) < self.MIN_VEL and abs(self._vel[1]) < self.MIN_VEL:
            self._ptimer.stop(); return
        pw = self._win.width()
        ph = self._win.height()
        nx = self.x() + int(self._vel[0])
        ny = self.y() + int(self._vel[1])
        if nx <= 0 or nx >= pw - self.width():
            nx = max(0, min(nx, pw - self.width()))
            self._vel[0] *= -self.BOUNCE
        if ny <= 0 or ny >= ph - self.height():
            ny = max(0, min(ny, ph - self.height()))
            self._vel[1] *= -self.BOUNCE
        self.move(nx, ny)


class DrawingWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.pen_color     = QColor("#00ffff")
        self.pen_width     = 8
        self.eraser_radius = 16
        self._mode         = "finger"
        self._strokes: list[Stroke]  = []
        self._current: Stroke | None = None

        self._canvas: QPixmap | None = None

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground,    True)
        self.setAutoFillBackground(False)

        geo = QApplication.primaryScreen().geometry()
        self.setGeometry(geo)

        self._toolbar = Toolbar(self)

        self._detach_toolbar()

    def _ensure_canvas(self):
        if self._canvas is None or self._canvas.size() != self.size():
            self._canvas = QPixmap(self.size())
            self._canvas.fill(Qt.transparent)
            p = QPainter(self._canvas)
            p.setRenderHint(QPainter.Antialiasing)
            for s in self._strokes:
                _draw_stroke(p, s)
            p.end()

    def _canvas_draw_stroke(self, stroke: Stroke):
        self._ensure_canvas()
        p = QPainter(self._canvas)
        p.setRenderHint(QPainter.Antialiasing)
        _draw_stroke(p, stroke)
        p.end()

    def _canvas_erase(self, pos: QPoint):
        self._ensure_canvas()
        r = self.eraser_radius
        p = QPainter(self._canvas)
        p.setCompositionMode(QPainter.CompositionMode_Clear)
        p.setPen(Qt.NoPen)
        p.setBrush(Qt.transparent)
        p.drawEllipse(pos, r, r)
        p.end()

    def set_mode(self, mode: str):
        self._mode = mode
        if mode == "finger":
            self._detach_toolbar()
            self.hide()
        else:
            self._attach_toolbar()
            self.show()
            self.raise_()
            self._toolbar.raise_()
            if mode == "pen":
                self.setCursor(Qt.CrossCursor)
            else:
                self.setCursor(self._make_eraser_cursor())

    def _detach_toolbar(self):
        tb = self._toolbar
        if tb.parent() is not self:
            return
        if self.isVisible():
            global_pos = self.mapToGlobal(tb.pos())
        else:
            global_pos = QPoint(
                self.geometry().x() + tb.pos().x(),
                self.geometry().y() + tb.pos().y(),
            )
        tb.setParent(None)
        tb.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        tb.move(global_pos)
        tb.show()
        tb.raise_()

    def _attach_toolbar(self):
        tb = self._toolbar
        if tb.parent() is self:
            return
        global_pos = tb.pos()
        tb.setParent(self)
        tb.setWindowFlags(Qt.Widget)
        local_pos = self.mapFromGlobal(global_pos)
        tb.move(local_pos)
        tb.show()
        tb.raise_()

    def clear(self):
        self._strokes.clear()
        self._current = None
        if self._canvas is not None:
            self._canvas.fill(Qt.transparent)
        self.update()

    def _is_toolbar_area(self, pos: QPoint) -> bool:
        tb = self._toolbar
        if tb.geometry().contains(pos):
            return True
        b = tb._bubble
        if b and b.isVisible() and b.geometry().contains(pos):
            return True
        return False

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self._is_toolbar_area(event.pos()):
            event.ignore()
            return
        if self._mode == "pen":
            self._current = Stroke(
                color=QColor(self.pen_color),
                width=self.pen_width,
                points=[QPoint(event.pos())],
            )
        elif self._mode == "eraser":
            self._ensure_canvas()
            self._canvas_erase(event.pos())
            self.update()
        event.accept()

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        if self._mode == "pen" and self._current is not None:
            self._current.points.append(QPoint(event.pos()))
            self.update()
        elif self._mode == "eraser":
            self._canvas_erase(event.pos())
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self._mode == "pen" and self._current is not None:
            self._current.points.append(QPoint(event.pos()))
            self._strokes.append(self._current)
            self._canvas_draw_stroke(self._current)
            self._current = None
            self.update()
        event.accept()

    def paintEvent(self, _):
        self._ensure_canvas()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.drawPixmap(0, 0, self._canvas)
        if self._current:
            _draw_stroke(p, self._current)
        p.end()

    def _make_eraser_cursor(self) -> QCursor:
        r  = self.eraser_radius
        sz = max(r * 2 + 4, 16)
        px = QPixmap(sz, sz)
        px.fill(Qt.transparent)
        p = QPainter(px)
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawEllipse(2, 2, sz - 4, sz - 4)
        p.setPen(QPen(QColor("#555"), 1))
        p.drawEllipse(1, 1, sz - 2, sz - 2)
        p.end()
        return QCursor(px, sz // 2, sz // 2)


def _draw_stroke(painter: QPainter, stroke: Stroke):
    pts = stroke.points
    if not pts:
        return
    pen = QPen(stroke.color, stroke.width,
               Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    if len(pts) == 1:
        painter.drawPoint(pts[0])
    else:
        for i in range(1, len(pts)):
            painter.drawLine(pts[i - 1], pts[i])


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    win = DrawingWindow()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()