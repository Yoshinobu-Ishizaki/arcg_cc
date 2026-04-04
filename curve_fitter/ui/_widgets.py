"""
共有ウィジェットヘルパー

- _ColorButton    : 色選択ボタン
- _EndpointWidget : 端点拘束入力ウィジェット
- render_mathtext_pixmap : matplotlib mathtext → QPixmap 変換
"""
from __future__ import annotations
import io
import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QLineEdit, QColorDialog,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QDoubleValidator, QColor, QPixmap, QPainter, QPolygon
from PyQt6.QtCore import QPoint

# デフォルト色
_DEFAULT_COLORS = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
    "#42d4f4", "#f032e6", "#bfef45", "#469990", "#9a6324",
]


def render_mathtext_pixmap(
    latex: str, fontsize: int = 13, dpi: int = 100, color: str = "black"
) -> QPixmap:
    """matplotlib mathtext で数式を QPixmap に変換する（起動時に一度だけ呼ぶ）"""
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    fig = Figure(figsize=(1, 0.35), dpi=dpi)
    fig.patch.set_alpha(0.0)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.patch.set_alpha(0.0)
    txt = ax.text(
        0.0, 0.5, latex, fontsize=fontsize, color=color,
        va="center", ha="left", transform=ax.transAxes,
    )
    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    bb = txt.get_window_extent(renderer=canvas.get_renderer())
    fig.set_size_inches(
        (bb.width / dpi) + 0.1,
        max(bb.height / dpi, 0.3) + 0.1,
    )
    canvas.draw()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, transparent=True)
    buf.seek(0)
    px = QPixmap()
    px.loadFromData(buf.read())
    return px


class BarberPoleBar(QWidget):
    """タイマー駆動のバーバーポール進捗バー（プラットフォーム非依存）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._offset = 0
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)

    def _tick(self):
        self._offset = (self._offset + 2) % 20
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        w, h = self.width(), self.height()

        painter.fillRect(0, 0, w, h, QColor("#d0d0d0"))

        stripe = 20
        col_a = QColor("#1a6ec7")
        col_b = QColor("#5fa8f5")

        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(-2, (w + h) // stripe + 3):
            x0 = i * stripe + self._offset
            pts = QPolygon([
                QPoint(x0,               0),
                QPoint(x0 + stripe,      0),
                QPoint(x0 + stripe + h,  h),
                QPoint(x0 + h,           h),
            ])
            painter.setBrush(col_a if i % 2 == 0 else col_b)
            painter.drawPolygon(pts)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QColor("#888888"))
        painter.drawRect(0, 0, w - 1, h - 1)
        painter.end()


class _ColorButton(QPushButton):
    """クリックで QColorDialog を開き、選択色を背景色に反映するボタン"""

    def __init__(self, color: str = "#e6194b", parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 22)
        self.setToolTip("クリックして色を選択")
        self._color = color
        self._apply_color(color)
        self.clicked.connect(self._on_click)

    def _apply_color(self, hex_color: str):
        self._color = hex_color
        self.setStyleSheet(
            f"background-color: {hex_color}; border: 1px solid #888; border-radius: 3px;"
        )

    def _on_click(self):
        c = QColorDialog.getColor(QColor(self._color), self, "セグメント色を選択")
        if c.isValid():
            self._apply_color(c.name())

    def color(self) -> str:
        return self._color

    def set_color(self, hex_color: str):
        self._apply_color(hex_color)


class _EndpointWidget(QWidget):
    """始点または終点の拘束を入力するサブウィジェット"""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(3)
        lay.addWidget(QLabel(f"<b>{label}</b>"))
        self._pin_cb = QCheckBox("この点を必ず通る（pin）")
        lay.addWidget(self._pin_cb)
        self._tan_cb = QCheckBox("接線ベクトルを指定")
        lay.addWidget(self._tan_cb)
        tan_row = QHBoxLayout()
        tan_row.setSpacing(2)
        dv = QDoubleValidator(-1e9, 1e9, 6)
        tan_row.addWidget(QLabel("tx:"))
        self._tx_edit = QLineEdit("1.0")
        self._tx_edit.setValidator(dv)
        self._tx_edit.setFixedWidth(52)
        tan_row.addWidget(self._tx_edit)
        tan_row.addWidget(QLabel("ty:"))
        self._ty_edit = QLineEdit("0.0")
        self._ty_edit.setValidator(dv)
        self._ty_edit.setFixedWidth(52)
        tan_row.addWidget(self._ty_edit)
        lay.addLayout(tan_row)
        self._tan_cb.toggled.connect(self._tx_edit.setEnabled)
        self._tan_cb.toggled.connect(self._ty_edit.setEnabled)
        self._tx_edit.setEnabled(False)
        self._ty_edit.setEnabled(False)

    def pin(self) -> bool:
        return self._pin_cb.isChecked()

    def tangent(self) -> "np.ndarray | None":
        if not self._tan_cb.isChecked():
            return None
        try:
            tx, ty = float(self._tx_edit.text()), float(self._ty_edit.text())
        except ValueError:
            return None
        v = np.array([tx, ty])
        n = np.linalg.norm(v)
        return v / n if n > 1e-12 else None

    def set_pin(self, val: bool):
        self._pin_cb.setChecked(val)

    def set_tangent(self, tx: float, ty: float):
        self._tan_cb.setChecked(True)
        self._tx_edit.setText(str(tx))
        self._ty_edit.setText(str(ty))
        self._tx_edit.setEnabled(True)
        self._ty_edit.setEnabled(True)
