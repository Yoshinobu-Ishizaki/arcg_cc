"""
パラメータ設定ウィンドウ（非モーダル）

メイン画面の「パラメータ設定」ボタンを押すと表示される。
計算パラメータをすべてここで設定し、メイン画面の「フィット実行」を押した時点で
このウィンドウの現在値が読み取られて計算に使用される。
"""
from __future__ import annotations
import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QDoubleSpinBox, QComboBox, QGroupBox,
    QScrollArea, QTabWidget,
    QFileDialog, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPalette

from ._widgets import _EndpointWidget, render_mathtext_pixmap, note_style


class ParameterWindow(QWidget):
    """計算パラメータ設定ウィンドウ（非モーダル・常時開けたままでよい）"""

    # シグナル
    pick_mode_toggled      = pyqtSignal(bool)
    start_reset_requested  = pyqtSignal()
    exclude_mode_toggled   = pyqtSignal(bool)
    exclude_undo_requested = pyqtSignal(int)
    exclude_all_reset      = pyqtSignal()
    alpha_changed          = pyqtSignal(float)   # α変更時に MainWindow へ通知
    params_save_requested  = pyqtSignal(str)
    params_load_requested  = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("パラメータ設定")
        self.setMinimumSize(520, 480)
        self.resize(560, 560)
        self._ex_rows: dict[int, QWidget] = {}
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # ---- タブウィジェット ----
        tabs = QTabWidget()

        # ======== タブ1: データ前処理 ========
        tab1 = QWidget()
        t1 = QVBoxLayout(tab1)
        t1.setSpacing(5)
        t1.setContentsMargins(6, 6, 6, 6)

        # ---- 始点指定 ----
        sg = QGroupBox("始点指定")
        sl = QVBoxLayout(sg)
        sl.addWidget(QLabel("自動始点が不正確な場合は\nプロットをクリックして指定。"))
        sp_row = QHBoxLayout()
        self._btn_pick = QPushButton("🖱 始点をクリック指定")
        self._btn_pick.setCheckable(True)
        self._btn_pick.setStyleSheet(
            "QPushButton { font-weight: bold; padding: 3px; }"
            "QPushButton:checked { background: #dd2200; color: white; "
            "font-weight: bold; padding: 3px; }"
        )
        self._btn_pick.toggled.connect(self._on_pick_toggled)
        sp_row.addWidget(self._btn_pick, stretch=1)
        self._btn_reset = QPushButton("↺ リセット")
        self._btn_reset.setToolTip("自動始点に戻す")
        self._btn_reset.clicked.connect(self._on_start_reset)
        sp_row.addWidget(self._btn_reset, stretch=1)
        sl.addLayout(sp_row)
        self._start_label = QLabel("始点: 自動選択")
        self._start_label.setStyleSheet(note_style(11))
        sl.addWidget(self._start_label)
        t1.addWidget(sg)

        # ---- 重複点除去 ----
        dg = QGroupBox("重複点除去")
        dl = QVBoxLayout(dg)
        lbl_dist = QLabel("隣接距離がこの値以下の点を削除:")
        lbl_dist.setWordWrap(True)
        dl.addWidget(lbl_dist)
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
        lbl_dist_note = QLabel("※0=除去なし。変更後は再読込で反映。")
        lbl_dist_note.setWordWrap(True)
        lbl_dist_note.setStyleSheet(note_style())
        dl.addWidget(lbl_dist_note)
        t1.addWidget(dg)

        # ---- 点除外 ----
        exg = QGroupBox("点除外")
        exl = QVBoxLayout(exg)
        lbl_exclude = QLabel("点をクリックして除外。再クリックで取消。")
        lbl_exclude.setWordWrap(True)
        exl.addWidget(lbl_exclude)
        ex_btn_row = QHBoxLayout()
        self._btn_exclude = QPushButton("✂ 点除外モード")
        self._btn_exclude.setCheckable(True)
        self._btn_exclude.setStyleSheet(
            "QPushButton { font-weight: bold; padding: 3px; }"
            "QPushButton:checked { background: #bb5500; color: white;"
            " font-weight: bold; padding: 3px; }"
        )
        self._btn_exclude.toggled.connect(self._on_exclude_toggled)
        ex_btn_row.addWidget(self._btn_exclude, stretch=1)
        self._btn_exclude_all_reset = QPushButton("↺ 全て戻す")
        self._btn_exclude_all_reset.clicked.connect(self._on_exclude_all_reset)
        ex_btn_row.addWidget(self._btn_exclude_all_reset, stretch=1)
        exl.addLayout(ex_btn_row)
        lbl_ex_list = QLabel("除外点一覧（クリックした点の座標）:")
        lbl_ex_list.setWordWrap(True)
        exl.addWidget(lbl_ex_list)
        ex_scroll = QScrollArea()
        ex_scroll.setWidgetResizable(True)
        ex_scroll.setMaximumHeight(160)
        self._ex_list_widget = QWidget()
        self._ex_list_layout = QVBoxLayout(self._ex_list_widget)
        self._ex_list_layout.setSpacing(1)
        self._ex_list_layout.setContentsMargins(2, 2, 2, 2)
        ex_scroll.setWidget(self._ex_list_widget)
        exl.addWidget(ex_scroll)
        t1.addWidget(exg)

        t1.addStretch()
        tabs.addTab(tab1, "前処理")

        # ======== タブ2: フィットパラメータ ========
        tab2 = QWidget()
        t2 = QVBoxLayout(tab2)
        t2.setSpacing(5)
        t2.setContentsMargins(6, 6, 6, 6)

        # ---- 誤差分散 閾値 ----
        thresh_row = QHBoxLayout()
        thresh_row.setSpacing(4)
        thresh_row.addWidget(QLabel("誤差分散 閾値"))
        bg = QApplication.palette().color(QPalette.ColorRole.Window)
        lum = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
        _tc = "white" if lum < 128 else "black"
        _formula_lbl = QLabel()
        try:
            _formula_lbl.setPixmap(
                render_mathtext_pixmap(
                    r"$(\Sigma d_i^2/n < \mathrm{threshold})$",
                    fontsize=11, color=_tc,
                )
            )
        except Exception:
            _formula_lbl.setText("(Σdi²/n < threshold)")
        thresh_row.addWidget(_formula_lbl)
        self._threshold_spin = QDoubleSpinBox()
        self._threshold_spin.setRange(1e-10, 1e10)
        self._threshold_spin.setValue(0.01)
        self._threshold_spin.setDecimals(6)
        self._threshold_spin.setSingleStep(0.001)
        thresh_row.addWidget(self._threshold_spin)
        thresh_row.addStretch()
        t2.addLayout(thresh_row)

        # ---- 最大セグメント数 ----
        seg_row = QHBoxLayout()
        seg_row.addWidget(QLabel("最大セグメント数:"))
        self._max_seg_spin = QSpinBox()
        self._max_seg_spin.setRange(1, 50)
        self._max_seg_spin.setValue(15)
        seg_row.addWidget(self._max_seg_spin)
        seg_row.addStretch()
        t2.addLayout(seg_row)

        # ---- 最大反復数 ----
        iter_row = QHBoxLayout()
        iter_row.addWidget(QLabel("境界最適化 最大反復数:"))
        self._max_iter_spin = QSpinBox()
        self._max_iter_spin.setRange(1, 50)
        self._max_iter_spin.setValue(8)
        iter_row.addWidget(self._max_iter_spin)
        iter_row.addStretch()
        t2.addLayout(iter_row)

        # ---- 許容残差 ----
        tol_row = QHBoxLayout()
        tol_row.addWidget(QLabel("許容残差:"))
        self._tol_auto = QDoubleSpinBox()
        self._tol_auto.setRange(1e-6, 1e6)
        self._tol_auto.setValue(0.1)
        self._tol_auto.setDecimals(4)
        tol_row.addWidget(self._tol_auto)
        tol_row.addStretch()
        t2.addLayout(tol_row)

        # ---- α係数 ----
        ag = QGroupBox("評価スコア")
        al = QVBoxLayout(ag)
        alpha_row = QHBoxLayout()
        alpha_row.addWidget(QLabel("α（ペナルティ係数）:"))
        self._alpha_spin = QDoubleSpinBox()
        self._alpha_spin.setRange(0.0, 10.0)
        self._alpha_spin.setValue(0.1)
        self._alpha_spin.setDecimals(3)
        self._alpha_spin.setSingleStep(0.01)
        self._alpha_spin.setFixedWidth(70)
        alpha_row.addWidget(self._alpha_spin)
        alpha_row.addStretch()
        al.addLayout(alpha_row)
        lbl_alpha = QLabel("複合評価値 = Σdi²/n × (1 + α × n)")
        lbl_alpha.setStyleSheet(note_style())
        al.addWidget(lbl_alpha)
        t2.addWidget(ag)
        self._alpha_spin.valueChanged.connect(
            lambda v: self.alpha_changed.emit(v)
        )

        # ---- 半径制約 ----
        rg = QGroupBox("半径制約")
        rl = QVBoxLayout(rg)

        max_row = QHBoxLayout()
        max_row.addWidget(QLabel("許容最大半径 R_max:"))
        self._max_radius_spin = QDoubleSpinBox()
        self._max_radius_spin.setRange(0.0, 1e9)
        self._max_radius_spin.setSpecialValueText("∞ (制約なし)")
        self._max_radius_spin.setValue(0.0)
        self._max_radius_spin.setDecimals(2)
        self._max_radius_spin.setSingleStep(10.0)
        self._max_radius_spin.setFixedWidth(120)
        max_row.addWidget(self._max_radius_spin)
        max_row.addStretch()
        rl.addLayout(max_row)
        lbl_max = QLabel("R > R_max の円弧は直線に置換")
        lbl_max.setStyleSheet(note_style())
        rl.addWidget(lbl_max)

        min_row = QHBoxLayout()
        min_row.addWidget(QLabel("許容最小半径 R_min:"))
        self._min_radius_spin = QDoubleSpinBox()
        self._min_radius_spin.setRange(0.0, 1e9)
        self._min_radius_spin.setSpecialValueText("制約なし")
        self._min_radius_spin.setValue(0.0)
        self._min_radius_spin.setDecimals(2)
        self._min_radius_spin.setSingleStep(1.0)
        self._min_radius_spin.setFixedWidth(120)
        min_row.addWidget(self._min_radius_spin)
        min_row.addStretch()
        rl.addLayout(min_row)
        lbl_min = QLabel("R < R_min の円弧は削除し隣接要素を接続")
        lbl_min.setStyleSheet(note_style())
        rl.addWidget(lbl_min)

        t2.addWidget(rg)

        t2.addStretch()
        tabs.addTab(tab2, "フィット")

        # ======== タブ3: 端点・区間 ========
        tab3 = QWidget()
        t3 = QVBoxLayout(tab3)
        t3.setSpacing(5)
        t3.setContentsMargins(6, 6, 6, 6)

        epg = QGroupBox("端点拘束")
        epl = QVBoxLayout(epg)
        self._start_ep = _EndpointWidget("始点")
        self._end_ep   = _EndpointWidget("終点")
        epl.addWidget(self._start_ep)
        ep_sep = QLabel()
        ep_sep.setFixedHeight(1)
        ep_sep.setStyleSheet("background: #ccc;")
        epl.addWidget(ep_sep)
        epl.addWidget(self._end_ep)
        t3.addWidget(epg)

        # ---- セグメント種別 ----
        pp = QGroupBox("セグメント種別")
        pl = QVBoxLayout(pp)
        pl.addWidget(QLabel("ポリシー:"))
        self._policy_combo = QComboBox()
        self._policy_combo.addItems(["auto", "line", "arc"])
        pl.addWidget(self._policy_combo)
        t3.addWidget(pp)

        t3.addStretch()
        tabs.addTab(tab3, "端点・区間")

        outer.addWidget(tabs, stretch=1)

        # ---- 下部: パラメータ保存・読込ボタン ----
        h_sep = QLabel()
        h_sep.setFixedHeight(1)
        h_sep.setStyleSheet("background: #ccc; margin: 2px 0;")
        outer.addWidget(h_sep)

        params_row = QHBoxLayout()
        params_row.setSpacing(8)
        btn_params_save = QPushButton("💾 パラメータ情報保存…")
        btn_params_save.setToolTip(
            "ソースファイルパス・前処理・フィットパラメータ・結果をYAMLで保存"
        )
        btn_params_save.clicked.connect(self._on_params_save)
        params_row.addWidget(btn_params_save)

        btn_params_load = QPushButton("📂 パラメータ情報読込…")
        btn_params_load.setToolTip(
            "YAMLを読み込んで同じ処理を再現\n"
            "（source.path を書き換えると別ファイルに同じ処理を適用）"
        )
        btn_params_load.clicked.connect(self._on_params_load)
        params_row.addWidget(btn_params_load)
        params_row.addStretch()
        outer.addLayout(params_row)

    # ------------------------------------------------------------------
    # 公開メソッド
    # ------------------------------------------------------------------
    def get_alpha(self) -> float:
        return self._alpha_spin.value()

    def get_min_dist(self) -> float:
        return self._min_dist_spin.value()

    def get_fit_state(self) -> dict:
        """現在のフィットパラメータを辞書で返す（パラメータ保存用）"""
        sp = self._start_ep.tangent()
        ep = self._end_ep.tangent()
        return {
            "fit_mode":    "auto",
            "alpha":       self._alpha_spin.value(),
            "min_dist":    self._min_dist_spin.value(),
            "threshold":    self._threshold_spin.value(),
            "type_policy":  self._policy_combo.currentText(),
            "max_segments": self._max_seg_spin.value(),
            "max_iter":     self._max_iter_spin.value(),
            "tol_type":     self._tol_auto.value(),
            # 端点拘束
            "start_pin":     self._start_ep.pin(),
            "start_tangent": sp.tolist() if sp is not None else None,
            "end_pin":       self._end_ep.pin(),
            "end_tangent":   ep.tolist() if ep is not None else None,
            # 半径制約
            "max_radius": self._max_radius_spin.value() or None,
            "min_radius": self._min_radius_spin.value() or None,
        }

    def apply_fit_state(self, state: dict) -> None:
        """辞書からフィットパラメータを UI に反映する（パラメータ読み込み用）"""
        if "alpha" in state:
            self._alpha_spin.setValue(float(state["alpha"]))
        if "min_dist" in state:
            self._min_dist_spin.setValue(float(state["min_dist"]))

        if "threshold" in state:
            self._threshold_spin.setValue(float(state["threshold"]))
        if "max_segments" in state:
            self._max_seg_spin.setValue(int(state["max_segments"]))
        if "max_iter" in state:
            self._max_iter_spin.setValue(int(state["max_iter"]))
        if "tol_type" in state:
            self._tol_auto.setValue(float(state["tol_type"]))

        if "type_policy" in state:
            self._policy_combo.setCurrentText(state["type_policy"])

        if "max_radius" in state:
            v = state["max_radius"]
            self._max_radius_spin.setValue(float(v) if v is not None else 0.0)
        if "min_radius" in state:
            v = state["min_radius"]
            self._min_radius_spin.setValue(float(v) if v is not None else 0.0)

    def update_start_label(self, idx: int, pt: "np.ndarray"):
        """始点が選択されたときにラベルを更新し、ピックモードを解除する"""
        self._btn_pick.setChecked(False)
        self._start_label.setText(
            f"始点: idx={idx}  ({pt[0]:.4f}, {pt[1]:.4f})"
        )
        self._start_label.setStyleSheet(note_style(11))

    def add_excluded_point(self, idx: int, x: float, y: float):
        """除外点をリストに追加する"""
        if idx in self._ex_rows:
            return

        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)

        coord_lbl = QLabel(f"({x:.6g}, {y:.6g})")
        coord_lbl.setStyleSheet("font-size: 10px; font-family: monospace;")
        coord_lbl.setToolTip(f"idx={idx}  x={x:.10g}  y={y:.10g}")
        row_layout.addWidget(coord_lbl, stretch=1)

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

    # ------------------------------------------------------------------
    # スロット
    # ------------------------------------------------------------------
    def _on_pick_toggled(self, checked: bool):
        if checked:
            self._btn_exclude.blockSignals(True)
            self._btn_exclude.setChecked(False)
            self._btn_exclude.blockSignals(False)
            self._btn_pick.setText("⏹ 指定完了（クリックして確定）")
        else:
            self._btn_pick.setText("🖱 始点をクリック指定")
        self.pick_mode_toggled.emit(checked)

    def _on_exclude_toggled(self, checked: bool):
        if checked:
            self._btn_pick.blockSignals(True)
            self._btn_pick.setChecked(False)
            self._btn_pick.blockSignals(False)
            self._btn_exclude.setText("⏹ 除外完了（モード終了）")
            self.pick_mode_toggled.emit(False)
        else:
            self._btn_exclude.setText("✂ 点除外モード")
        self.exclude_mode_toggled.emit(checked)

    def _on_start_reset(self):
        self._btn_pick.setChecked(False)
        self._start_label.setText("始点: 自動選択")
        self._start_label.setStyleSheet(note_style(11))
        self.start_reset_requested.emit()

    def _on_exclude_all_reset(self):
        self._btn_exclude.setChecked(False)
        self._clear_ex_list()
        self.exclude_all_reset.emit()

    def _on_undo_one(self, idx: int):
        self.remove_excluded_point(idx)
        self.exclude_undo_requested.emit(idx)

    def _on_params_save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "パラメータを保存", "parameters.yaml",
            "YAML パラメータ (*.yaml *.yml);;全ファイル (*)"
        )
        if path:
            self.params_save_requested.emit(path)

    def _on_params_load(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "パラメータを読み込む", "",
            "YAML パラメータ (*.yaml *.yml);;全ファイル (*)"
        )
        if path:
            self.params_load_requested.emit(path)
