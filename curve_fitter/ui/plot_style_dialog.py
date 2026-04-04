"""
プロットスタイルダイアログ（非モーダル）

メイン画面の「プロットスタイル」ボタンを押すと表示される。
フィット後のセグメント色・種別をここで設定する。
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal

from ._widgets import _ColorButton, _DEFAULT_COLORS


class PlotStyleDialog(QWidget):
    """プロットスタイル設定ウィンドウ（非モーダル）"""

    colors_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("プロットスタイル")
        self.setMinimumWidth(280)
        self._color_buttons: list[_ColorButton] = []
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # ---- セグメント色 ----
        cg = QGroupBox("セグメント色")
        cl = QVBoxLayout(cg)
        lbl = QLabel("（フィット後に自動生成。クリックで変更）")
        lbl.setWordWrap(True)
        cl.addWidget(lbl)
        scroll_c = QScrollArea()
        scroll_c.setWidgetResizable(True)
        scroll_c.setMinimumHeight(100)
        self._color_container = QWidget()
        self._color_layout    = QVBoxLayout(self._color_container)
        self._color_layout.setSpacing(2)
        scroll_c.setWidget(self._color_container)
        cl.addWidget(scroll_c)
        outer.addWidget(cg)

        outer.addStretch()

    # ------------------------------------------------------------------
    def rebuild_color_buttons(self, n: int):
        """セグメント数 n に合わせて色ボタン行を再生成する"""
        old_colors = [b.color() for b in self._color_buttons]
        for b in self._color_buttons:
            b.setParent(None)
        self._color_buttons.clear()

        for i in range(n):
            row = QHBoxLayout()
            lbl = QLabel(f"  Seg {i+1}:")
            lbl.setFixedWidth(50)
            init_color = (
                old_colors[i] if i < len(old_colors)
                else _DEFAULT_COLORS[i % len(_DEFAULT_COLORS)]
            )
            btn = _ColorButton(init_color)
            btn.clicked.connect(self._on_color_changed)
            row.addWidget(lbl)
            row.addWidget(btn)
            row.addStretch()
            self._color_layout.addLayout(row)
            self._color_buttons.append(btn)

    def _on_color_changed(self):
        self.colors_changed.emit(self.get_colors())

    def get_colors(self) -> list[str]:
        return [b.color() for b in self._color_buttons]

    def apply_colors(self, colors: list[str]):
        """パラメータ読み込み時などに色を一括適用する"""
        self.rebuild_color_buttons(len(colors))
        for btn, c in zip(self._color_buttons, colors):
            btn.set_color(c)

