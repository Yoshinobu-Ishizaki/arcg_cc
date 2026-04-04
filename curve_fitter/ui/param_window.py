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
    QScrollArea, QStackedWidget,
    QRadioButton, QButtonGroup,
    QSizePolicy, QFileDialog, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPalette

from ._widgets import _EndpointWidget, render_mathtext_pixmap


class ParameterWindow(QWidget):
    """計算パラメータ設定ウィンドウ（非モーダル・常時開けたままでよい）"""

    # シグナル
    pick_mode_toggled      = pyqtSignal(bool)
    start_reset_requested  = pyqtSignal()
    exclude_mode_toggled   = pyqtSignal(bool)
    exclude_undo_requested = pyqtSignal(int)
    exclude_all_reset      = pyqtSignal()
    alpha_changed          = pyqtSignal(float)   # α変更時に MainWindow へ通知
    session_save_requested = pyqtSignal(str)
    session_load_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("パラメータ設定")
        self.setMinimumSize(860, 480)
        self.resize(960, 520)
        self._ex_rows: dict[int, QWidget] = {}
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # ---- 3カラムコンテンツ ----
        columns = QHBoxLayout()
        columns.setSpacing(0)

        def _vsep():
            w = QWidget()
            w.setFixedWidth(1)
            w.setStyleSheet("background: #ccc;")
            return w

        # ======== 左カラム: データ前処理 ========
        col1 = QWidget()
        c1 = QVBoxLayout(col1)
        c1.setSpacing(5)
        c1.setContentsMargins(4, 4, 8, 4)

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
        self._start_label.setStyleSheet("font-size: 11px; color: #555;")
        sl.addWidget(self._start_label)
        c1.addWidget(sg)

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
        lbl_dist_note.setStyleSheet("font-size: 10px; color: #777;")
        dl.addWidget(lbl_dist_note)
        c1.addWidget(dg)

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
        ex_scroll.setMaximumHeight(120)
        self._ex_list_widget = QWidget()
        self._ex_list_layout = QVBoxLayout(self._ex_list_widget)
        self._ex_list_layout.setSpacing(1)
        self._ex_list_layout.setContentsMargins(2, 2, 2, 2)
        ex_scroll.setWidget(self._ex_list_widget)
        exl.addWidget(ex_scroll)
        c1.addWidget(exg)

        c1.addStretch()

        # ======== 中カラム: フィットパラメータ ========
        col2 = QWidget()
        c2 = QVBoxLayout(col2)
        c2.setSpacing(5)
        c2.setContentsMargins(8, 4, 8, 4)

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
        c2.addWidget(mode_box)

        # ---- パラメータスタック ----
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_manual_panel())
        self._stack.addWidget(self._build_auto_panel())
        self._stack.setCurrentIndex(1)
        c2.addWidget(self._stack)

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
        lbl_alpha.setStyleSheet("font-size: 10px; color: #555;")
        al.addWidget(lbl_alpha)
        c2.addWidget(ag)
        self._alpha_spin.valueChanged.connect(
            lambda v: self.alpha_changed.emit(v)
        )

        c2.addStretch()

        # ======== 右カラム: 端点拘束 ========
        col3 = QWidget()
        c3 = QVBoxLayout(col3)
        c3.setSpacing(5)
        c3.setContentsMargins(8, 4, 4, 4)

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
        c3.addWidget(epg)

        # ---- セグメント種別 ----
        pp = QGroupBox("セグメント種別")
        pl = QVBoxLayout(pp)
        pl.addWidget(QLabel("ポリシー:"))
        self._policy_combo = QComboBox()
        self._policy_combo.addItems(["auto", "line", "arc"])
        pl.addWidget(self._policy_combo)
        lbl_seg_type = QLabel("手動モード 各セグメント:")
        lbl_seg_type.setWordWrap(True)
        pl.addWidget(lbl_seg_type)
        scroll_t = QScrollArea()
        scroll_t.setWidgetResizable(True)
        scroll_t.setMaximumHeight(100)
        self._type_container = QWidget()
        self._type_layout    = QVBoxLayout(self._type_container)
        self._type_layout.setSpacing(2)
        scroll_t.setWidget(self._type_container)
        pl.addWidget(scroll_t)
        self._type_combos: list[QComboBox] = []
        self._rebuild_type_selectors(3)
        c3.addWidget(pp)

        c3.addStretch()

        columns.addWidget(col1, stretch=1)
        columns.addWidget(_vsep())
        columns.addWidget(col2, stretch=1)
        columns.addWidget(_vsep())
        columns.addWidget(col3, stretch=1)
        outer.addLayout(columns, stretch=1)

        # ---- 下部: パラメータ保存・読込ボタン ----
        h_sep = QLabel()
        h_sep.setFixedHeight(1)
        h_sep.setStyleSheet("background: #ccc; margin: 2px 0;")
        outer.addWidget(h_sep)

        sess_row = QHBoxLayout()
        sess_row.setSpacing(8)
        btn_sess_save = QPushButton("💾 パラメータ情報保存…")
        btn_sess_save.setToolTip(
            "ソースファイルパス・前処理・フィットパラメータ・結果をYAMLで保存"
        )
        btn_sess_save.clicked.connect(self._on_session_save)
        sess_row.addWidget(btn_sess_save)

        btn_sess_load = QPushButton("📂 パラメータ情報読込…")
        btn_sess_load.setToolTip(
            "YAMLを読み込んで同じ処理を再現\n"
            "（source.path を書き換えると別ファイルに同じ処理を適用）"
        )
        btn_sess_load.clicked.connect(self._on_session_load)
        sess_row.addWidget(btn_sess_load)
        sess_row.addStretch()
        outer.addLayout(sess_row)

    def _build_manual_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel("セグメント数:"))
        self._seg_spin = QSpinBox()
        self._seg_spin.setRange(1, 50)
        self._seg_spin.setValue(3)
        self._seg_spin.valueChanged.connect(self._rebuild_type_selectors)
        lay.addWidget(self._seg_spin)
        lay.addWidget(QLabel("auto判定 許容残差:"))
        self._tol_manual = QDoubleSpinBox()
        self._tol_manual.setRange(1e-6, 1e6)
        self._tol_manual.setValue(0.5)
        self._tol_manual.setDecimals(4)
        lay.addWidget(self._tol_manual)
        return w

    def _build_auto_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        threshold_row = QHBoxLayout()
        threshold_row.setSpacing(4)
        threshold_row.addWidget(QLabel("誤差分散 閾値"))
        _tc = QApplication.palette().color(QPalette.ColorRole.WindowText).name()
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
        threshold_row.addWidget(_formula_lbl)
        threshold_row.addStretch()
        lay.addLayout(threshold_row)
        self._threshold_spin = QDoubleSpinBox()
        self._threshold_spin.setRange(1e-10, 1e10)
        self._threshold_spin.setValue(0.01)
        self._threshold_spin.setDecimals(6)
        self._threshold_spin.setSingleStep(0.001)
        lay.addWidget(self._threshold_spin)
        lay.addWidget(QLabel("最大セグメント数:"))
        self._max_seg_spin = QSpinBox()
        self._max_seg_spin.setRange(1, 50)
        self._max_seg_spin.setValue(15)
        lay.addWidget(self._max_seg_spin)
        lay.addWidget(QLabel("境界最適化 最大反復数:"))
        self._max_iter_spin = QSpinBox()
        self._max_iter_spin.setRange(1, 50)
        self._max_iter_spin.setValue(8)
        lay.addWidget(self._max_iter_spin)
        lay.addWidget(QLabel("auto判定 許容残差:"))
        self._tol_auto = QDoubleSpinBox()
        self._tol_auto.setRange(1e-6, 1e6)
        self._tol_auto.setValue(0.5)
        self._tol_auto.setDecimals(4)
        lay.addWidget(self._tol_auto)
        return w

    def _rebuild_type_selectors(self, n: int):
        for c in self._type_combos:
            c.setParent(None)
        self._type_combos.clear()
        for i in range(n):
            row = QHBoxLayout()
            lbl = QLabel(f"  Seg {i+1}:")
            lbl.setFixedWidth(50)
            combo = QComboBox()
            combo.addItems(["auto", "line", "arc"])
            row.addWidget(lbl)
            row.addWidget(combo)
            self._type_layout.addLayout(row)
            self._type_combos.append(combo)

    # ------------------------------------------------------------------
    # 公開メソッド
    # ------------------------------------------------------------------
    def get_alpha(self) -> float:
        return self._alpha_spin.value()

    def get_min_dist(self) -> float:
        return self._min_dist_spin.value()

    def get_fit_state(self) -> dict:
        """現在のフィットパラメータを辞書で返す（セッション保存用）"""
        sp = self._start_ep.tangent()
        ep = self._end_ep.tangent()
        return {
            "fit_mode":    "manual" if self._radio_manual.isChecked() else "auto",
            "alpha":       self._alpha_spin.value(),
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
        """辞書からフィットパラメータを UI に反映する（セッション読み込み用）"""
        mode = state.get("fit_mode", "auto")
        if mode == "manual":
            self._radio_manual.setChecked(True)
            self._stack.setCurrentIndex(0)
        else:
            self._radio_auto.setChecked(True)
            self._stack.setCurrentIndex(1)

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

        if "n_segments" in state:
            n = int(state["n_segments"])
            self._seg_spin.setValue(n)
            self._rebuild_type_selectors(n)
        if "seg_types" in state:
            for i, combo in enumerate(self._type_combos):
                if i < len(state["seg_types"]):
                    combo.setCurrentText(state["seg_types"][i])
        if "tolerance" in state:
            self._tol_manual.setValue(float(state["tolerance"]))

    def update_start_label(self, idx: int, pt: "np.ndarray"):
        """始点が選択されたときにラベルを更新し、ピックモードを解除する"""
        self._btn_pick.setChecked(False)
        self._start_label.setText(
            f"始点: idx={idx}  ({pt[0]:.4f}, {pt[1]:.4f})"
        )
        self._start_label.setStyleSheet(
            "font-size: 11px; color: #cc0000; font-weight: bold;"
        )

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
    def _on_mode_changed(self, idx: int):
        self._stack.setCurrentIndex(idx)

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
        self._start_label.setStyleSheet("font-size: 11px; color: #555;")
        self.start_reset_requested.emit()

    def _on_exclude_all_reset(self):
        self._btn_exclude.setChecked(False)
        self._clear_ex_list()
        self.exclude_all_reset.emit()

    def _on_undo_one(self, idx: int):
        self.remove_excluded_point(idx)
        self.exclude_undo_requested.emit(idx)

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
