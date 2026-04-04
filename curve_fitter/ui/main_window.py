"""
メインウィンドウ: PlotWidget + ControlPanel を統合
"""
from __future__ import annotations
import numpy as np
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QMessageBox

from .plot_widget import PlotWidget
from .control_panel import ControlPanel
from ..core.loader import load_points
from ..core.fitter import SegmentFitter, EndpointConstraint
from ..core.exporter import export_segments
from ..core.preprocess import remove_outliers, sort_points, remove_duplicates
from ..core.session import save_session, load_session


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("曲線フィッター — G1連続セグメント近似")
        screen = QApplication.primaryScreen().availableGeometry()
        w = min(1100, int(screen.width() * 0.85))
        h = min(700, int(screen.height() * 0.88))
        self.resize(w, h)
        self._pts_raw_clean: np.ndarray | None = None  # 外れ値除去済み・未ソート
        self._points:        np.ndarray | None = None  # ソート済み（fitter に渡す）
        self._excluded:      set[int]          = set() # 除外点インデックス（_points 上）
        self._segments = []
        self._fitter   = None
        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        self.plot_widget   = PlotWidget()
        self.control_panel = ControlPanel()
        layout.addWidget(self.plot_widget, stretch=1)
        layout.addWidget(self.control_panel)

    def _connect_signals(self):
        cp = self.control_panel
        pw = self.plot_widget
        cp.file_load_requested.connect(self._on_load_file)
        cp.fit_manual_requested.connect(self._on_fit_manual)
        cp.fit_auto_requested.connect(self._on_fit_auto)
        cp.save_requested.connect(self._on_save)
        cp.colors_changed.connect(self._on_colors_changed)
        cp.pick_mode_toggled.connect(self._on_pick_mode_toggled)
        cp.start_reset_requested.connect(self._on_start_reset)
        cp.exclude_mode_toggled.connect(self._on_exclude_mode_toggled)
        cp.exclude_undo_requested.connect(self._on_exclude_undo)
        cp.exclude_all_reset.connect(self._on_exclude_all_reset)
        pw.start_point_selected.connect(self._on_start_point_selected)
        pw.point_excluded.connect(self._on_point_excluded)
        pw.point_unexcluded.connect(self._on_point_unexcluded)
        cp.session_save_requested.connect(self._on_session_save)
        cp.session_load_requested.connect(self._on_session_load)

    # ------------------------------------------------------------------
    @staticmethod
    def _make_constraint(pin: bool, tangent) -> EndpointConstraint:
        t = np.asarray(tangent) if tangent is not None else None
        return EndpointConstraint(pin=pin, tangent=t)

    def _active_points(self) -> np.ndarray | None:
        """除外点を除いた点群を返す（fitter に渡す用）"""
        if self._points is None:
            return None
        if not self._excluded:
            return self._points
        mask = np.array([i not in self._excluded
                         for i in range(len(self._points))])
        return self._points[mask]

    def _rebuild_fitter(self):
        """除外状態が変わったときに fitter を再構築する"""
        pts = self._active_points()
        if pts is None or len(pts) < 2:
            self._fitter = None
            return
        self._fitter   = SegmentFitter(pts)
        self._segments = []
        self.plot_widget.set_segments([])
        self.control_panel.update_result(float("inf"), 0, "", True)

    def _resort(self, start_idx: int | None = None):
        """_pts_raw_clean を start_idx 指定でソートし直し、fitter を更新する"""
        if self._pts_raw_clean is None:
            return
        pts_sorted = sort_points(self._pts_raw_clean, start_idx=start_idx)
        min_dist   = self.control_panel.get_min_dist()
        if min_dist > 0:
            pts_sorted = remove_duplicates(pts_sorted, min_dist=min_dist)
        self._points   = pts_sorted
        self._excluded = set()   # ソートし直したら除外リストもリセット
        self._rebuild_fitter()
        self.plot_widget.set_points(pts_sorted)
        self.plot_widget.set_excluded(set())
        self.plot_widget.set_start_index(0 if start_idx is None else None)

    def _on_load_file(self, path: str):
        try:
            pts_raw   = load_points(path)
            pts_clean = remove_outliers(pts_raw)
            self._pts_raw_clean = pts_clean
            self._source_path   = path
            self._resort(start_idx=None)
            self.statusBar().showMessage(
                f"読み込み完了: {path}  ({len(self._points)} 点, "
                f"外れ値 {len(pts_raw)-len(pts_clean)} 点除外)", 6000
            )
        except Exception as e:
            QMessageBox.critical(self, "読み込みエラー", str(e))

    # ------------------------------------------------------------------
    # 始点指定
    # ------------------------------------------------------------------
    def _on_pick_mode_toggled(self, enabled: bool):
        self.plot_widget.set_mode("pick" if enabled else "normal")

    def _on_start_point_selected(self, idx: int):
        if self._pts_raw_clean is None:
            return
        selected_pt = self._points[idx]
        dists   = np.linalg.norm(self._pts_raw_clean - selected_pt, axis=1)
        raw_idx = int(np.argmin(dists))
        self._resort(start_idx=raw_idx)
        self.control_panel.update_start_label(idx, selected_pt)
        self.statusBar().showMessage(
            f"始点変更: ({selected_pt[0]:.4f}, {selected_pt[1]:.4f}) → 再ソート", 5000
        )

    def _on_start_reset(self):
        self._resort(start_idx=None)
        self.statusBar().showMessage("始点を自動選択に戻しました", 4000)

    # ------------------------------------------------------------------
    # 点除外
    # ------------------------------------------------------------------
    def _on_exclude_mode_toggled(self, enabled: bool):
        self.plot_widget.set_mode("exclude" if enabled else "normal")

    def _on_point_excluded(self, idx: int, x: float, y: float):
        """PlotWidget で点が除外された → 管理セットに追加 & fitter 再構築"""
        self._excluded.add(idx)
        self.control_panel.add_excluded_point(idx, x, y)
        self._rebuild_fitter()
        n = len(self._excluded)
        self.statusBar().showMessage(
            f"点除外: ({x:.6g}, {y:.6g})  [計 {n} 点除外中]", 4000
        )

    def _on_point_unexcluded(self, idx: int):
        """PlotWidget で除外取消（再クリック） → 管理セットから削除"""
        self._excluded.discard(idx)
        self.control_panel.remove_excluded_point(idx)
        self._rebuild_fitter()
        self.statusBar().showMessage(
            f"除外取消: idx={idx}  [計 {len(self._excluded)} 点除外中]", 4000
        )

    def _on_exclude_undo(self, idx: int):
        """コントロールパネルの「戻す」ボタン → プロットの除外も解除"""
        self._excluded.discard(idx)
        self.plot_widget.set_excluded(self._excluded)
        self._rebuild_fitter()
        self.statusBar().showMessage(
            f"除外取消: idx={idx}  [計 {len(self._excluded)} 点除外中]", 4000
        )

    def _on_exclude_all_reset(self):
        """全除外をリセット"""
        self._excluded.clear()
        self.plot_widget.set_excluded(set())
        self._rebuild_fitter()
        self.statusBar().showMessage("全除外点をリセットしました", 4000)

    # ------------------------------------------------------------------
    # フィット
    # ------------------------------------------------------------------
    def _on_fit_manual(self, n_seg, types, tol,
                       start_pin, start_tan, end_pin, end_tan):
        if self._fitter is None:
            QMessageBox.warning(self, "警告", "先にファイルを読み込んでください。")
            return
        try:
            sc = self._make_constraint(start_pin, start_tan)
            ec = self._make_constraint(end_pin, end_tan)
            segs = self._fitter.fit(
                n_segments=n_seg, seg_types=types, tolerance=tol,
                start_constraint=sc, end_constraint=ec,
            )
            variance = self._fitter.variance_score(segs)
            composite = self._fitter.composite_score(segs, self.control_panel._alpha_spin.value())
            self._last_variance  = variance
            self._last_composite = composite
            self._last_converged = True
            self._last_message   = f"手動フィット: {n_seg} セグメント"
            self.control_panel.update_result(
                variance, n_seg, f"手動フィット: {n_seg} セグメント", True,
            )
            self._segments = segs
            self.plot_widget.set_segments(segs, self.control_panel.get_colors())
            self.statusBar().showMessage(
                f"手動フィット完了: {n_seg} セグメント  Σdi²/n={variance:.6g}", 5000
            )
        except Exception as e:
            QMessageBox.critical(self, "フィットエラー", str(e))

    def _on_fit_auto(self, threshold, policy, max_seg, max_iter, tol,
                     start_pin, start_tan, end_pin, end_tan):
        if self._fitter is None:
            QMessageBox.warning(self, "警告", "先にファイルを読み込んでください。")
            return
        try:
            sc = self._make_constraint(start_pin, start_tan)
            ec = self._make_constraint(end_pin, end_tan)
            self.statusBar().showMessage("自動フィット中…", 0)
            result = self._fitter.fit_auto(
                threshold=threshold, type_policy=policy,
                max_segments=max_seg, max_iter=max_iter, tol_type=tol,
                start_constraint=sc, end_constraint=ec,
            )
            self._last_variance  = result.score
            self._last_composite = result.score * (
                1.0 + self.control_panel._alpha_spin.value() * result.n_segments
            )
            self._last_converged = result.converged
            self._last_message   = result.message
            self.control_panel.update_result(
                result.score, result.n_segments,
                result.message, result.converged,
            )
            self._segments = result.segments
            self.plot_widget.set_segments(
                result.segments, self.control_panel.get_colors()
            )
            self.statusBar().showMessage(
                f"自動フィット完了: {result.n_segments} セグメント  "
                f"Σdi²/n={result.score:.6g}  "
                f"{'✓ 収束' if result.converged else '△ 未収束'}",
                8000,
            )
            if not result.converged:
                QMessageBox.warning(
                    self, "収束しませんでした",
                    result.message + "\n\n最終結果を表示しています。",
                )
        except Exception as e:
            QMessageBox.critical(self, "フィットエラー", str(e))

    def _on_colors_changed(self, colors: list):
        if self._segments:
            self.plot_widget.set_segments(self._segments, colors)

    def _on_save(self, path: str, fmt: str):
        if not self._segments:
            QMessageBox.warning(self, "警告", "先にフィットを実行してください。")
            return
        try:
            export_segments(self._segments, path, fmt=fmt)
            self.statusBar().showMessage(f"保存完了: {path}", 5000)
        except Exception as e:
            QMessageBox.critical(self, "保存エラー", str(e))

    # ------------------------------------------------------------------
    # セッション保存・読み込み
    # ------------------------------------------------------------------
    def _collect_session_state(self) -> dict:
        """現在のアプリ状態を state 辞書にまとめる"""
        cp = self.control_panel
        state = cp.get_fit_state()

        # ソースファイルパス（ウィンドウタイトルから取得できないので別管理）
        state["source_path"] = getattr(self, "_source_path", "")

        # 始点座標（インデックスではなく座標で保存）
        start_coord = None
        if self._points is not None and self.plot_widget._start_idx is not None:
            idx = self.plot_widget._start_idx
            if 0 <= idx < len(self._points):
                p = self._points[idx]
                start_coord = [float(p[0]), float(p[1])]
        state["start_point_coord"] = start_coord

        # 除外点座標リスト
        ex_coords = []
        if self._points is not None:
            for idx in sorted(self._excluded):
                if 0 <= idx < len(self._points):
                    p = self._points[idx]
                    ex_coords.append([float(p[0]), float(p[1])])
        state["excluded_coords"] = ex_coords

        # 評価結果
        state["variance"]          = getattr(self, "_last_variance", None)
        state["composite"]         = getattr(self, "_last_composite", None)
        state["result_n_segments"] = len(self._segments) if self._segments else None
        state["converged"]         = getattr(self, "_last_converged", None)
        state["message"]           = getattr(self, "_last_message", "")

        return state

    def _on_session_save(self, path: str):
        try:
            state = self._collect_session_state()
            save_session(path, state)
            self.statusBar().showMessage(f"セッション保存完了: {path}", 5000)
        except Exception as e:
            QMessageBox.critical(self, "セッション保存エラー", str(e))

    def _on_session_load(self, path: str):
        try:
            state = load_session(path)
        except Exception as e:
            QMessageBox.critical(self, "セッション読み込みエラー", str(e))
            return

        # ---- UI パラメータを復元 ----
        self.control_panel.apply_fit_state(state)

        # ---- ソースファイルを読み込む ----
        src_path = state.get("source_path", "")
        if not src_path:
            QMessageBox.warning(
                self, "警告",
                "source.path が空です。\nYAML ファイルの source.path にデータファイルのパスを記入してください。"
            )
            return

        try:
            pts_raw   = load_points(src_path)
            pts_clean = remove_outliers(pts_raw)
            self._pts_raw_clean = pts_clean
            self._source_path   = src_path
        except Exception as e:
            QMessageBox.critical(
                self, "ソースファイル読み込みエラー",
                f"{src_path}\n\n{e}"
            )
            return

        # ---- 始点指定を座標から復元 ----
        sp_coord = state.get("start_point_coord")
        start_raw_idx = None
        if sp_coord is not None:
            sp = np.array(sp_coord)
            dists = np.linalg.norm(pts_clean - sp, axis=1)
            start_raw_idx = int(np.argmin(dists))

        # ---- ソート & 重複除去 ----
        pts_sorted = sort_points(pts_clean, start_idx=start_raw_idx)
        min_dist   = state.get("min_dist", 0.0)
        if min_dist > 0:
            pts_sorted = remove_duplicates(pts_sorted, min_dist=min_dist)
        self._points   = pts_sorted
        self._excluded = set()

        # ---- 除外点を座標から復元 ----
        ex_coords = state.get("excluded_coords", []) or []
        for coord in ex_coords:
            ec = np.array(coord)
            dists = np.linalg.norm(pts_sorted - ec, axis=1)
            idx   = int(np.argmin(dists))
            if idx not in self._excluded:
                self._excluded.add(idx)
                pt = pts_sorted[idx]
                self.control_panel.add_excluded_point(idx, float(pt[0]), float(pt[1]))

        # ---- プロット更新 ----
        self.plot_widget.set_points(pts_sorted)
        self.plot_widget.set_excluded(self._excluded)
        if start_raw_idx is not None:
            self.plot_widget.set_start_index(0)   # ソート後の先頭が始点

        # ---- fitter 再構築 ----
        self._rebuild_fitter()

        self.statusBar().showMessage(
            f"セッション読み込み完了: {path}  "
            f"(ソース: {src_path}  {len(pts_sorted)} 点)", 7000
        )
