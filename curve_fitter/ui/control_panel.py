"""
コントロールパネル（メイン画面右側）

4つのボタンと計算結果評価値のみを表示するシンプルなパネル。
詳細な計算パラメータは ParameterWindow で設定する。
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QGroupBox, QFileDialog,
)
from PyQt6.QtCore import pyqtSignal

from ._widgets import render_mathtext_pixmap


class ControlPanel(QWidget):
    """メイン画面右側パネル（4ボタン＋評価値表示）"""

    # シグナル
    file_load_requested    = pyqtSignal(str)
    fit_requested          = pyqtSignal()
    save_requested         = pyqtSignal(str, str)
    param_window_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(200)
        self.setMaximumWidth(260)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 6, 6, 6)
        root.setSpacing(6)

        # ---- ファイル情報 ----
        self._file_label = QLabel("（未選択）")
        self._file_label.setWordWrap(True)
        self._file_label.setStyleSheet("color: gray; font-size: 11px;")
        root.addWidget(self._file_label)

        # ---- メインボタン 4つ ----
        btn_open = QPushButton("開く")
        btn_open.setStyleSheet("font-weight: bold; padding: 6px;")
        btn_open.clicked.connect(self._on_open)
        root.addWidget(btn_open)

        btn_params = QPushButton("パラメータ設定")
        btn_params.setStyleSheet("padding: 6px;")
        btn_params.clicked.connect(self.param_window_requested.emit)
        root.addWidget(btn_params)

        btn_fit = QPushButton("▶ フィット実行")
        btn_fit.setStyleSheet("font-weight: bold; padding: 6px; background: #1a6ec7; color: white;")
        btn_fit.clicked.connect(self.fit_requested.emit)
        root.addWidget(btn_fit)

        # 保存（形式選択付き）
        save_row = QHBoxLayout()
        self._fmt_combo = QComboBox()
        self._fmt_combo.addItems(["default", "csv", "dxf"])
        self._fmt_combo.setToolTip(
            "default: 人間可読テキスト\n"
            "csv: CSV形式\n"
            "dxf: 2D DXF（LINE/ARCエンティティ）"
        )
        self._fmt_combo.setFixedWidth(80)
        save_row.addWidget(self._fmt_combo)
        btn_save = QPushButton("保存")
        btn_save.setStyleSheet("padding: 6px;")
        btn_save.clicked.connect(self._on_save)
        save_row.addWidget(btn_save)
        root.addLayout(save_row)

        # ---- セパレータ ----
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #ccc; margin: 4px 0;")
        root.addWidget(sep)

        # ---- 評価値表示 ----
        rg = QGroupBox("評価値")
        rl = QVBoxLayout(rg)
        rl.setSpacing(4)

        # 誤差分散ラベル（数式 pixmap + 値）
        var_row = QHBoxLayout()
        var_row.setSpacing(2)
        self._var_formula_lbl = QLabel()
        self._var_formula_lbl.setToolTip("誤差分散 Σdi²/n")
        try:
            px = render_mathtext_pixmap(r"$\Sigma d_i^2 / n$", fontsize=12)
            self._var_formula_lbl.setPixmap(px)
        except Exception:
            self._var_formula_lbl.setText("Σdi²/n")
        var_row.addWidget(self._var_formula_lbl)
        var_row.addWidget(QLabel(" : "))
        self._var_value_label = QLabel("—")
        self._var_value_label.setStyleSheet("font-weight: bold;")
        var_row.addWidget(self._var_value_label)
        var_row.addStretch()
        rl.addLayout(var_row)

        # 複合評価値ラベル（数式 pixmap + 値）
        comp_row = QHBoxLayout()
        comp_row.setSpacing(2)
        self._comp_formula_lbl = QLabel()
        self._comp_formula_lbl.setToolTip("複合評価値 Σdi²/n × (1 + α × n)")
        try:
            px2 = render_mathtext_pixmap(
                r"$\Sigma d_i^2/n \cdot (1 + \alpha \cdot n)$", fontsize=12
            )
            self._comp_formula_lbl.setPixmap(px2)
        except Exception:
            self._comp_formula_lbl.setText("Σdi²/n·(1+α·n)")
        comp_row.addWidget(self._comp_formula_lbl)
        comp_row.addWidget(QLabel(" : "))
        self._comp_value_label = QLabel("—")
        self._comp_value_label.setStyleSheet("font-weight: bold;")
        comp_row.addWidget(self._comp_value_label)
        comp_row.addStretch()
        rl.addLayout(comp_row)

        # セグメント数
        self._nseg_label = QLabel("セグメント数 n : —")
        self._nseg_label.setStyleSheet("font-size: 11px;")
        rl.addWidget(self._nseg_label)

        # 収束メッセージ
        self._msg_label = QLabel("")
        self._msg_label.setWordWrap(True)
        self._msg_label.setStyleSheet("font-size: 11px;")
        rl.addWidget(self._msg_label)

        root.addWidget(rg)
        root.addStretch()

    # ------------------------------------------------------------------
    # スロット
    # ------------------------------------------------------------------
    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "ファイルを開く", "",
            "対応ファイル (*.dxf *.csv);;DXF (*.dxf);;CSV (*.csv)"
        )
        if path:
            self._file_label.setText(path.split("/")[-1])
            self.file_load_requested.emit(path)

    def _on_save(self):
        fmt = self._fmt_combo.currentText()
        if fmt == "dxf":
            default_name = "segments.dxf"
            file_filter  = "DXF (*.dxf);;全ファイル (*)"
        elif fmt == "csv":
            default_name = "segments.csv"
            file_filter  = "CSV (*.csv);;全ファイル (*)"
        else:
            default_name = "segments.txt"
            file_filter  = "テキスト (*.txt);;全ファイル (*)"

        path, _ = QFileDialog.getSaveFileName(
            self, "セグメントを保存", default_name, file_filter
        )
        if path:
            self.save_requested.emit(path, fmt)

    # ------------------------------------------------------------------
    # 外部から呼び出すメソッド
    # ------------------------------------------------------------------
    def update_result(
        self,
        variance:  float,
        composite: float,
        n_seg:     int,
        message:   str,
        converged: bool,
    ):
        """評価値を更新する"""
        self._var_value_label.setText(f"{variance:.6g}")
        self._comp_value_label.setText(f"{composite:.6g}")
        self._nseg_label.setText(f"セグメント数 n : {n_seg}")

        color = "#007700" if converged else "#cc5500"
        self._msg_label.setStyleSheet(f"font-size: 11px; color: {color};")
        self._msg_label.setText(message)

    def update_composite(self, composite: float):
        """複合評価値のみを更新する（α変更時）"""
        self._comp_value_label.setText(f"{composite:.6g}")

    def set_file_label(self, name: str):
        self._file_label.setText(name)
