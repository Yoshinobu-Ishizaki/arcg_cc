"""
コントロールパネル

モード切替:
  [手動モード] セグメント数を直接指定してフィット
  [自動モード] 誤差分散の閾値を指定し、最小セグメント数を自動探索

共通:
  ・ファイル選択（DXF/CSV）
  ・端点拘束（始点/終点ごとに: 通過スイッチ + 接線ベクトル入力）
  ・セグメント色指定（セグメントごとに色ボタン）
  ・各セグメント種別ポリシー（auto / line / arc）
  ・結果表示（誤差分散・複合評価値・セグメント数）
  ・保存ボタン
"""
from __future__ import annotations
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QDoubleSpinBox, QComboBox, QGroupBox,
    QScrollArea, QFileDialog, QStackedWidget,
    QRadioButton, QButtonGroup, QCheckBox, QLineEdit,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDoubleValidator, QColor, QPalette
from PyQt6.QtWidgets import QColorDialog

# デフォルト色（ColorButton 初期値として使用）
_DEFAULT_COLORS = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
    "#42d4f4", "#f032e6", "#bfef45", "#469990", "#9a6324",
]


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
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(3)
        lay.addWidget(QLabel(f"<b>{label}</b>"))
        self._pin_cb = QCheckBox("この点を必ず通る（pin）")
        lay.addWidget(self._pin_cb)
        self._tan_cb = QCheckBox("接線ベクトルを指定")
        lay.addWidget(self._tan_cb)
        tan_row = QHBoxLayout()
        dv = QDoubleValidator(-1e9, 1e9, 6)
        tan_row.addWidget(QLabel("  tx:"))
        self._tx_edit = QLineEdit("1.0")
        self._tx_edit.setValidator(dv)
        self._tx_edit.setFixedWidth(58)
        tan_row.addWidget(self._tx_edit)
        tan_row.addWidget(QLabel("ty:"))
        self._ty_edit = QLineEdit("0.0")
        self._ty_edit.setValidator(dv)
        self._ty_edit.setFixedWidth(58)
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


class ControlPanel(QWidget):
    """右側コントロールパネル"""

    # シグナル
    file_load_requested  = pyqtSignal(str)
    fit_manual_requested = pyqtSignal(int, list, float,
                                      bool, object, bool, object)
    fit_auto_requested   = pyqtSignal(float, str, int, int, float,
                                      bool, object, bool, object)
    save_requested       = pyqtSignal(str, str)
    colors_changed       = pyqtSignal(list)
    pick_mode_toggled     = pyqtSignal(bool)
    start_reset_requested = pyqtSignal()
    exclude_mode_toggled  = pyqtSignal(bool)
    exclude_undo_requested = pyqtSignal(int)
    exclude_all_reset     = pyqtSignal()
    # セッション
    session_save_requested = pyqtSignal(str)   # 保存先パス
    session_load_requested = pyqtSignal(str)   # 読み込みパス

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(260)
        self.setMaximumWidth(310)
        self._color_buttons: list[_ColorButton] = []
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setSpacing(5)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        # ---- ファイル ----
        fg = QGroupBox("ファイル")
        fl = QVBoxLayout(fg)
        self._file_label = QLabel("（未選択）")
        self._file_label.setWordWrap(True)
        self._file_label.setStyleSheet("color: gray; font-size: 11px;")
        btn_open = QPushButton("開く (DXF / CSV)…")
        btn_open.clicked.connect(self._on_open)
        fl.addWidget(btn_open)
        fl.addWidget(self._file_label)

        # セッション保存・読み込み
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #ccc; margin: 2px 0;")
        fl.addWidget(sep)
        sess_row = QHBoxLayout()
        btn_sess_save = QPushButton("💾 セッション保存…")
        btn_sess_save.setToolTip(
            "ソースファイルパス・前処理・フィットパラメータ・結果をYAMLで保存"
        )
        btn_sess_save.clicked.connect(self._on_session_save)
        btn_sess_load = QPushButton("📂 セッション読込…")
        btn_sess_load.setToolTip(
            "YAMLを読み込んで同じ処理を再現\n"
            "（source.path を書き換えると別ファイルに同じ処理を適用）"
        )
        btn_sess_load.clicked.connect(self._on_session_load)
        sess_row.addWidget(btn_sess_save)
        sess_row.addWidget(btn_sess_load)
        fl.addLayout(sess_row)
        root.addWidget(fg)

        # ---- 始点指定 ----
        sg = QGroupBox("始点指定")
        sl = QVBoxLayout(sg)
        sl.addWidget(QLabel("自動始点が不正確な場合は\nプロットをクリックして指定。"))
        sp_row = QHBoxLayout()
        self._btn_pick = QPushButton("🖱 始点をクリック指定")
        self._btn_pick.setCheckable(True)
        self._btn_pick.setStyleSheet(
            "QPushButton { font-weight: bold; padding: 5px; }"
            "QPushButton:checked { background: #dd2200; color: white; "
            "font-weight: bold; padding: 5px; }"
        )
        self._btn_pick.toggled.connect(self._on_pick_toggled)
        sp_row.addWidget(self._btn_pick)

        self._btn_reset = QPushButton("↺ リセット")
        self._btn_reset.setToolTip("自動始点に戻す")
        self._btn_reset.clicked.connect(self._on_start_reset)
        sp_row.addWidget(self._btn_reset)
        sl.addLayout(sp_row)

        self._start_label = QLabel("始点: 自動選択")
        self._start_label.setStyleSheet("font-size: 11px; color: #555;")
        sl.addWidget(self._start_label)
        root.addWidget(sg)

        # ---- 重複点除去 ----
        dg = QGroupBox("重複点除去")
        dl = QVBoxLayout(dg)
        dl.addWidget(QLabel("隣接距離がこの値以下の点を削除:"))
        dist_row = QHBoxLayout()
        dist_row.addWidget(QLabel("最小距離:"))
        self._min_dist_spin = QDoubleSpinBox()
        self._min_dist_spin.setRange(0.0, 1e6)
        self._min_dist_spin.setValue(0.1)
        self._min_dist_spin.setDecimals(4)
        self._min_dist_spin.setSingleStep(0.01)
        self._min_dist_spin.setFixedWidth(90)
        dist_row.addWidget(self._min_dist_spin)
        dist_row.addStretch()
        dl.addLayout(dist_row)
        dl.addWidget(QLabel(
            "※0=除去なし。変更後は再読込で反映。",
            styleSheet="font-size: 10px; color: #777;"
        ))
        root.addWidget(dg)

        # ---- 点除外 ----
        exg = QGroupBox("点除外")
        exl = QVBoxLayout(exg)
        exl.addWidget(QLabel("点をクリックして除外。再クリックで取消。"))

        ex_btn_row = QHBoxLayout()
        self._btn_exclude = QPushButton("✂ 点除外モード")
        self._btn_exclude.setCheckable(True)
        self._btn_exclude.setStyleSheet(
            "QPushButton { font-weight: bold; padding: 5px; }"
            "QPushButton:checked { background: #bb5500; color: white;"
            " font-weight: bold; padding: 5px; }"
        )
        self._btn_exclude.toggled.connect(self._on_exclude_toggled)
        ex_btn_row.addWidget(self._btn_exclude)
        self._btn_exclude_all_reset = QPushButton("↺ 全て戻す")
        self._btn_exclude_all_reset.clicked.connect(self._on_exclude_all_reset)
        ex_btn_row.addWidget(self._btn_exclude_all_reset)
        exl.addLayout(ex_btn_row)

        # 除外点リスト（スクロール）
        exl.addWidget(QLabel("除外点一覧（クリックした点の座標）:"))
        ex_scroll = QScrollArea()
        ex_scroll.setWidgetResizable(True)
        ex_scroll.setMaximumHeight(140)
        self._ex_list_widget = QWidget()
        self._ex_list_layout = QVBoxLayout(self._ex_list_widget)
        self._ex_list_layout.setSpacing(1)
        self._ex_list_layout.setContentsMargins(2, 2, 2, 2)
        ex_scroll.setWidget(self._ex_list_widget)
        exl.addWidget(ex_scroll)

        self._ex_rows: dict[int, QWidget] = {}   # idx → row widget
        root.addWidget(exg)
        epg = QGroupBox("端点拘束")
        epl = QVBoxLayout(epg)
        self._start_ep = _EndpointWidget("始点")
        self._end_ep   = _EndpointWidget("終点")
        epl.addWidget(self._start_ep)
        sep = QLabel(); sep.setFixedHeight(1)
        sep.setStyleSheet("background: #ccc;")
        epl.addWidget(sep)
        epl.addWidget(self._end_ep)
        root.addWidget(epg)

        # ---- モード切替 ----
        mode_box = QGroupBox("フィットモード")
        ml = QHBoxLayout(mode_box)
        self._radio_manual = QRadioButton("手動")
        self._radio_auto   = QRadioButton("自動（閾値）")
        self._radio_auto.setChecked(True)
        self._mode_group = QButtonGroup()
        self._mode_group.addButton(self._radio_manual, 0)
        self._mode_group.addButton(self._radio_auto,   1)
        self._mode_group.idClicked.connect(self._on_mode_changed)
        ml.addWidget(self._radio_manual)
        ml.addWidget(self._radio_auto)
        root.addWidget(mode_box)

        # ---- パラメータスタック ----
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_manual_panel())
        self._stack.addWidget(self._build_auto_panel())
        self._stack.setCurrentIndex(1)
        root.addWidget(self._stack)

        # ---- セグメント種別 ----
        pp = QGroupBox("セグメント種別")
        pl = QVBoxLayout(pp)
        pl.addWidget(QLabel("ポリシー:"))
        self._policy_combo = QComboBox()
        self._policy_combo.addItems(["auto", "line", "arc"])
        pl.addWidget(self._policy_combo)
        pl.addWidget(QLabel("手動モード 各セグメント:"))
        scroll_t = QScrollArea(); scroll_t.setWidgetResizable(True)
        scroll_t.setMaximumHeight(120)
        self._type_container = QWidget()
        self._type_layout    = QVBoxLayout(self._type_container)
        self._type_layout.setSpacing(2)
        scroll_t.setWidget(self._type_container)
        pl.addWidget(scroll_t)
        self._type_combos: list[QComboBox] = []
        self._rebuild_type_selectors(3)
        root.addWidget(pp)

        # ---- セグメント色 ----
        cg = QGroupBox("セグメント色")
        cl = QVBoxLayout(cg)
        cl.addWidget(QLabel("（フィット後に自動生成。クリックで変更）"))
        scroll_c = QScrollArea(); scroll_c.setWidgetResizable(True)
        scroll_c.setMaximumHeight(110)
        self._color_container = QWidget()
        self._color_layout    = QVBoxLayout(self._color_container)
        self._color_layout.setSpacing(2)
        scroll_c.setWidget(self._color_container)
        cl.addWidget(scroll_c)
        root.addWidget(cg)

        # ---- フィット実行 ----
        btn_fit = QPushButton("▶ フィット実行")
        btn_fit.setStyleSheet("font-weight: bold; padding: 6px;")
        btn_fit.clicked.connect(self._on_fit)
        root.addWidget(btn_fit)

        # ---- 結果表示 ----
        rg = QGroupBox("評価値")
        rl = QVBoxLayout(rg)
        rl.setSpacing(3)

        # 誤差分散
        self._var_label = QLabel("誤差分散  Σdi²/n : —")
        self._var_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        rl.addWidget(self._var_label)

        # 複合評価値（ペナルティ係数α付き）
        alpha_row = QHBoxLayout()
        alpha_row.addWidget(QLabel("α（ペナルティ係数）:"))
        self._alpha_spin = QDoubleSpinBox()
        self._alpha_spin.setRange(0.0, 10.0)
        self._alpha_spin.setValue(0.1)
        self._alpha_spin.setDecimals(3)
        self._alpha_spin.setSingleStep(0.01)
        self._alpha_spin.setFixedWidth(70)
        alpha_row.addWidget(self._alpha_spin)
        rl.addLayout(alpha_row)

        self._comp_label = QLabel("複合評価値 Σdi²/n×(1+α×n) : —")
        self._comp_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        rl.addWidget(self._comp_label)

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

        # α変更時に複合評価値を再計算（最新スコアを保持）
        self._last_variance: float | None = None
        self._last_n: int | None = None
        self._alpha_spin.valueChanged.connect(self._refresh_composite)

        # ---- 保存 ----
        sg = QGroupBox("保存")
        sl = QVBoxLayout(sg)
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("形式:"))
        self._fmt_combo = QComboBox()
        self._fmt_combo.addItems(["default", "csv", "dxf"])
        self._fmt_combo.setToolTip(
            "default: 人間可読テキスト\n"
            "csv: CSV形式\n"
            "dxf: 2D DXF（LINE/ARCエンティティ）"
        )
        fmt_row.addWidget(self._fmt_combo)
        sl.addLayout(fmt_row)
        btn_save = QPushButton("保存…")
        btn_save.clicked.connect(self._on_save)
        sl.addWidget(btn_save)
        root.addWidget(sg)

        root.addStretch()

    def _build_manual_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w); lay.setContentsMargins(0,0,0,0)
        lay.addWidget(QLabel("セグメント数:"))
        self._seg_spin = QSpinBox()
        self._seg_spin.setRange(1, 50); self._seg_spin.setValue(3)
        self._seg_spin.valueChanged.connect(self._rebuild_type_selectors)
        lay.addWidget(self._seg_spin)
        lay.addWidget(QLabel("auto判定 許容残差:"))
        self._tol_manual = QDoubleSpinBox()
        self._tol_manual.setRange(1e-6,1e6); self._tol_manual.setValue(0.5)
        self._tol_manual.setDecimals(4)
        lay.addWidget(self._tol_manual)
        return w

    def _build_auto_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w); lay.setContentsMargins(0,0,0,0)
        lay.addWidget(QLabel("誤差分散 閾値 (Σdi²/n < threshold):"))
        self._threshold_spin = QDoubleSpinBox()
        self._threshold_spin.setRange(1e-10,1e10); self._threshold_spin.setValue(0.01)
        self._threshold_spin.setDecimals(6); self._threshold_spin.setSingleStep(0.001)
        lay.addWidget(self._threshold_spin)
        lay.addWidget(QLabel("最大セグメント数:"))
        self._max_seg_spin = QSpinBox()
        self._max_seg_spin.setRange(1,50); self._max_seg_spin.setValue(15)
        lay.addWidget(self._max_seg_spin)
        lay.addWidget(QLabel("境界最適化 最大反復数:"))
        self._max_iter_spin = QSpinBox()
        self._max_iter_spin.setRange(1,50); self._max_iter_spin.setValue(8)
        lay.addWidget(self._max_iter_spin)
        lay.addWidget(QLabel("auto判定 許容残差:"))
        self._tol_auto = QDoubleSpinBox()
        self._tol_auto.setRange(1e-6,1e6); self._tol_auto.setValue(0.5)
        self._tol_auto.setDecimals(4)
        lay.addWidget(self._tol_auto)
        return w

    def _rebuild_type_selectors(self, n: int):
        for c in self._type_combos: c.setParent(None)
        self._type_combos.clear()
        for i in range(n):
            row = QHBoxLayout()
            lbl = QLabel(f"  Seg {i+1}:"); lbl.setFixedWidth(50)
            combo = QComboBox(); combo.addItems(["auto","line","arc"])
            row.addWidget(lbl); row.addWidget(combo)
            self._type_layout.addLayout(row)
            self._type_combos.append(combo)

    def _rebuild_color_buttons(self, n: int):
        """セグメント数 n に合わせて色ボタン行を再生成する"""
        # 現在の色を保持しながら再生成
        old_colors = [b.color() for b in self._color_buttons]
        for b in self._color_buttons:
            b.setParent(None)
        self._color_buttons.clear()

        for i in range(n):
            row = QHBoxLayout()
            lbl = QLabel(f"  Seg {i+1}:"); lbl.setFixedWidth(50)
            # 既存色を引き継ぐ、なければデフォルト
            init_color = old_colors[i] if i < len(old_colors) \
                else _DEFAULT_COLORS[i % len(_DEFAULT_COLORS)]
            btn = _ColorButton(init_color)
            # 色変更時に即座に再描画シグナルを出す
            btn.clicked.connect(self._on_color_changed)
            row.addWidget(lbl); row.addWidget(btn); row.addStretch()
            self._color_layout.addLayout(row)
            self._color_buttons.append(btn)

    def _on_color_changed(self):
        self.colors_changed.emit(self.get_colors())

    def get_colors(self) -> list[str]:
        return [b.color() for b in self._color_buttons]

    def get_min_dist(self) -> float:
        return self._min_dist_spin.value()

    def get_fit_state(self) -> dict:
        """現在のフィットパラメータを辞書で返す"""
        sp = self._start_ep.tangent()
        ep = self._end_ep.tangent()
        return {
            "fit_mode":    "manual" if self._radio_manual.isChecked() else "auto",
            "alpha":       self._alpha_spin.value(),
            "seg_colors":  self.get_colors(),
            "min_dist":    self._min_dist_spin.value(),
            # auto
            "threshold":    self._threshold_spin.value(),
            "type_policy":  self._policy_combo.currentText(),
            "max_segments": self._max_seg_spin.value(),
            "max_iter":     self._max_iter_spin.value(),
            "tol_type":     self._tol_auto.value(),
            # manual
            "n_segments":   self._seg_spin.value(),
            "seg_types":    [c.currentText() for c in self._type_combos],
            "tolerance":    self._tol_manual.value(),
            # 端点拘束
            "start_pin":     self._start_ep.pin(),
            "start_tangent": sp.tolist() if sp is not None else None,
            "end_pin":       self._end_ep.pin(),
            "end_tangent":   ep.tolist() if ep is not None else None,
        }

    def apply_fit_state(self, state: dict) -> None:
        """辞書からフィットパラメータを UI に反映する"""
        # モード
        mode = state.get("fit_mode", "auto")
        if mode == "manual":
            self._radio_manual.setChecked(True)
            self._stack.setCurrentIndex(0)
        else:
            self._radio_auto.setChecked(True)
            self._stack.setCurrentIndex(1)

        # 共通
        if "alpha" in state:
            self._alpha_spin.setValue(float(state["alpha"]))
        if "min_dist" in state:
            self._min_dist_spin.setValue(float(state["min_dist"]))

        # auto
        if "threshold"    in state: self._threshold_spin.setValue(float(state["threshold"]))
        if "type_policy"  in state: self._policy_combo.setCurrentText(state["type_policy"])
        if "max_segments" in state: self._max_seg_spin.setValue(int(state["max_segments"]))
        if "max_iter"     in state: self._max_iter_spin.setValue(int(state["max_iter"]))
        if "tol_type"     in state: self._tol_auto.setValue(float(state["tol_type"]))

        # manual
        if "n_segments" in state:
            n = int(state["n_segments"])
            self._seg_spin.setValue(n)
            self._rebuild_type_selectors(n)
        if "seg_types" in state:
            types = list(state["seg_types"])
            for i, combo in enumerate(self._type_combos):
                if i < len(types):
                    combo.setCurrentText(types[i])
        if "tolerance" in state: self._tol_manual.setValue(float(state["tolerance"]))

    # ------------------------------------------------------------------
    # 除外点リスト管理
    # ------------------------------------------------------------------
    def add_excluded_point(self, idx: int, x: float, y: float):
        """除外点をリストに追加する"""
        if idx in self._ex_rows:
            return  # 既に登録済み

        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)

        # 座標ラベル（高精度表示 — 元ファイルで探せるように）
        coord_lbl = QLabel(f"({x:.6g}, {y:.6g})")
        coord_lbl.setStyleSheet("font-size: 10px; font-family: monospace;")
        coord_lbl.setToolTip(f"idx={idx}  x={x:.10g}  y={y:.10g}")
        row_layout.addWidget(coord_lbl, stretch=1)

        # 「戻す」ボタン
        undo_btn = QPushButton("戻す")
        undo_btn.setFixedWidth(42)
        undo_btn.setStyleSheet("font-size: 10px; padding: 1px 4px;")
        undo_btn.clicked.connect(lambda _, i=idx: self._on_undo_one(i))
        row_layout.addWidget(undo_btn)

        self._ex_list_layout.addWidget(row_widget)
        self._ex_rows[idx] = row_widget

    def remove_excluded_point(self, idx: int):
        """除外点をリストから削除する"""
        w = self._ex_rows.pop(idx, None)
        if w is not None:
            w.setParent(None)

    def _clear_ex_list(self):
        for w in list(self._ex_rows.values()):
            w.setParent(None)
        self._ex_rows.clear()

    def _on_undo_one(self, idx: int):
        self.remove_excluded_point(idx)
        self.exclude_undo_requested.emit(idx)

    # ------------------------------------------------------------------
    def _on_mode_changed(self, idx: int):
        self._stack.setCurrentIndex(idx)

    def _on_pick_toggled(self, checked: bool):
        if checked:
            # 始点指定ON → 点除外モードは解除
            self._btn_exclude.blockSignals(True)
            self._btn_exclude.setChecked(False)
            self._btn_exclude.blockSignals(False)
            self._btn_pick.setText("⏹ 指定完了（クリックして確定）")
        else:
            self._btn_pick.setText("🖱 始点をクリック指定")
        self.pick_mode_toggled.emit(checked)

    def _on_exclude_toggled(self, checked: bool):
        if checked:
            # 点除外ON → 始点指定モードは解除
            self._btn_pick.blockSignals(True)
            self._btn_pick.setChecked(False)
            self._btn_pick.blockSignals(False)
            self._btn_exclude.setText("⏹ 除外完了（モード終了）")
            self.pick_mode_toggled.emit(False)   # 念のため始点モードをOFF
        else:
            self._btn_exclude.setText("✂ 点除外モード")
        self.exclude_mode_toggled.emit(checked)

    def _on_start_reset(self):
        self._btn_pick.setChecked(False)
        self._start_label.setText("始点: 自動選択")
        self._start_label.setStyleSheet("font-size: 11px; color: #555;")
        self.start_reset_requested.emit()

    def _on_exclude_all_reset(self):
        """全除外点をリセット"""
        self._btn_exclude.setChecked(False)
        self._clear_ex_list()
        self.exclude_all_reset.emit()

    def update_start_label(self, idx: int, pt: "np.ndarray"):
        """始点が選択されたときにラベルを更新し、ピックモードを解除する"""
        self._btn_pick.setChecked(False)   # モードを自動解除
        self._start_label.setText(
            f"始点: idx={idx}  ({pt[0]:.4f}, {pt[1]:.4f})"
        )
        self._start_label.setStyleSheet(
            "font-size: 11px; color: #cc0000; font-weight: bold;"
        )

    def _on_session_save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "セッションを保存", "session.yaml",
            "YAML セッション (*.yaml *.yml);;全ファイル (*)"
        )
        if path:
            self.session_save_requested.emit(path)

    def _on_session_load(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "セッションを読み込む", "",
            "YAML セッション (*.yaml *.yml);;全ファイル (*)"
        )
        if path:
            self.session_load_requested.emit(path)

    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "ファイルを開く", "",
            "対応ファイル (*.dxf *.csv);;DXF (*.dxf);;CSV (*.csv)"
        )
        if path:
            self._file_label.setText(path.split("/")[-1])
            self.file_load_requested.emit(path)

    def _on_fit(self):
        sp = self._start_ep.pin(); st = self._start_ep.tangent()
        ep = self._end_ep.pin();   et = self._end_ep.tangent()
        if self._radio_manual.isChecked():
            n     = self._seg_spin.value()
            types = [c.currentText() for c in self._type_combos]
            tol   = self._tol_manual.value()
            self.fit_manual_requested.emit(n, types, tol, sp, st, ep, et)
        else:
            self.fit_auto_requested.emit(
                self._threshold_spin.value(),
                self._policy_combo.currentText(),
                self._max_seg_spin.value(),
                self._max_iter_spin.value(),
                self._tol_auto.value(),
                sp, st, ep, et,
            )

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

    def _refresh_composite(self):
        """α変更時に複合評価値だけ再計算して表示更新"""
        if self._last_variance is None or self._last_n is None:
            return
        alpha = self._alpha_spin.value()
        comp  = self._last_variance * (1.0 + alpha * self._last_n)
        self._comp_label.setText(
            f"複合評価値 Σdi²/n×(1+α×n) : {comp:.6g}"
        )

    # ------------------------------------------------------------------
    # 外部から呼び出すメソッド
    # ------------------------------------------------------------------
    def update_result(
        self,
        variance:  float,
        n_seg:     int,
        message:   str,
        converged: bool,
    ):
        """
        Parameters
        ----------
        variance  : Σdi²/n
        n_seg     : セグメント数
        message   : 収束メッセージ
        converged : 収束したか
        """
        self._last_variance = variance
        self._last_n        = n_seg
        alpha = self._alpha_spin.value()
        comp  = variance * (1.0 + alpha * n_seg)

        self._var_label.setText(f"誤差分散  Σdi²/n : {variance:.6g}")
        self._comp_label.setText(
            f"複合評価値 Σdi²/n×(1+α×n) : {comp:.6g}"
        )
        self._nseg_label.setText(f"セグメント数 n : {n_seg}")

        color = "#007700" if converged else "#cc5500"
        self._msg_label.setStyleSheet(f"font-size: 11px; color: {color};")
        self._msg_label.setText(message)

        # セグメント数に合わせて色ボタンを再生成
        self._rebuild_color_buttons(n_seg)
