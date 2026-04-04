"""
メインウィンドウ: PlotWidget + ControlPanel + ParameterWindow を統合
"""
from __future__ import annotations
import numpy as np
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QMessageBox
from PyQt6.QtCore import Qt

from .plot_widget import PlotWidget
from .control_panel import ControlPanel
from .param_window import ParameterWindow
from .plot_style_dialog import PlotStyleDialog
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
        self.move(
            screen.x() + (screen.width() - w) // 2,
            screen.y() + (screen.height() - h) // 2,
        )
        self._pts_raw_clean: np.ndarray | None = None
        self._points:        np.ndarray | None = None
        self._excluded:      set[int]          = set()
        self._segments = []
        self._fitter   = None
        self._last_variance:  float | None = None
        self._last_n:         int   | None = None
        self._last_composite: float | None = None
        self._last_converged: bool  | None = None
        self._last_message:   str         = ""

        self.param_window      = ParameterWindow()   # 起動時は非表示
        self.plot_style_dialog = PlotStyleDialog()   # 起動時は非表示

        self._build_ui()
        self._connect_signals()

    def closeEvent(self, event):
        self.param_window.close()
        self.plot_style_dialog.close()
        super().closeEvent(event)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(4, 4, 12, 4)
        layout.setSpacing(6)
        self.plot_widget   = PlotWidget()
        self.control_panel = ControlPanel()
        layout.addWidget(self.plot_widget, stretch=1)
        layout.addWidget(self.control_panel)

    def _connect_signals(self):
        cp = self.control_panel
        pw = self.param_window
        plot = self.plot_widget

        # ControlPanel シグナル
        cp.file_load_requested.connect(self._on_load_file)
        cp.fit_requested.connect(self._on_fit_requested)
        cp.save_requested.connect(self._on_save)
        pw.session_save_requested.connect(self._on_session_save)
        pw.session_load_requested.connect(self._on_session_load)
        cp.param_window_requested.connect(self._on_param_settings)
        cp.plot_style_requested.connect(self._on_plot_style)

        # ParameterWindow シグナル
        pw.pick_mode_toggled.connect(self._on_pick_mode_toggled)
        pw.start_reset_requested.connect(self._on_start_reset)
        pw.exclude_mode_toggled.connect(self._on_exclude_mode_toggled)
        pw.exclude_undo_requested.connect(self._on_exclude_undo)
        pw.exclude_all_reset.connect(self._on_exclude_all_reset)
        pw.alpha_changed.connect(self._on_alpha_changed)

        # PlotStyleDialog シグナル
        self.plot_style_dialog.colors_changed.connect(self._on_colors_changed)

        # PlotWidget シグナル
        plot.start_point_selected.connect(self._on_start_point_selected)
        plot.point_excluded.connect(self._on_point_excluded)
        plot.point_unexcluded.connect(self._on_point_unexcluded)

    # ------------------------------------------------------------------
    def _on_param_settings(self):
        pw = self.param_window
        if pw.isVisible():
            pw.raise_()
            pw.activateWindow()
        else:
            pw.show()
            pw.raise_()

    def _on_plot_style(self):
        d = self.plot_style_dialog
        if d.isVisible():
            d.raise_()
            d.activateWindow()
        else:
            d.show()
            d.raise_()

    # ------------------------------------------------------------------
    @staticmethod
    def _make_constraint(pin: bool, tangent) -> EndpointConstraint:
        t = np.asarray(tangent) if tangent is not None else None
        return EndpointConstraint(pin=pin, tangent=t)

    def _active_points(self) -> np.ndarray | None:
        if self._points is None:
            return None
        if not self._excluded:
            return self._points
        mask = np.array([i not in self._excluded
                         for i in range(len(self._points))])
        return self._points[mask]

    def _rebuild_fitter(self):
        pts = self._active_points()
        if pts is None or len(pts) < 2:
            self._fitter = None
            return
        self._fitter   = SegmentFitter(pts)
        self._segments = []
        self.plot_widget.set_segments([])
        self.control_panel.update_result(float("inf"), float("inf"), 0, "", True)

    def _resort(self, start_idx: int | None = None):
        if self._pts_raw_clean is None:
            return
        pts_sorted = sort_points(self._pts_raw_clean, start_idx=start_idx)
        min_dist   = self.param_window.get_min_dist()
        if min_dist > 0:
            pts_sorted = remove_duplicates(pts_sorted, min_dist=min_dist)
        self._points   = pts_sorted
        self._excluded = set()
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
        self.param_window.update_start_label(idx, selected_pt)
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
        self._excluded.add(idx)
        self.param_window.add_excluded_point(idx, x, y)
        self._rebuild_fitter()
        n = len(self._excluded)
        self.statusBar().showMessage(
            f"点除外: ({x:.6g}, {y:.6g})  [計 {n} 点除外中]", 4000
        )

    def _on_point_unexcluded(self, idx: int):
        self._excluded.discard(idx)
        self.param_window.remove_excluded_point(idx)
        self._rebuild_fitter()
        self.statusBar().showMessage(
            f"除外取消: idx={idx}  [計 {len(self._excluded)} 点除外中]", 4000
        )

    def _on_exclude_undo(self, idx: int):
        self._excluded.discard(idx)
        self.plot_widget.set_excluded(self._excluded)
        self._rebuild_fitter()
        self.statusBar().showMessage(
            f"除外取消: idx={idx}  [計 {len(self._excluded)} 点除外中]", 4000
        )

    def _on_exclude_all_reset(self):
        self._excluded.clear()
        self.plot_widget.set_excluded(set())
        self._rebuild_fitter()
        self.statusBar().showMessage("全除外点をリセットしました", 4000)

    # ------------------------------------------------------------------
    # フィット実行
    # ------------------------------------------------------------------
    def _on_fit_requested(self):
        state = self.param_window.get_fit_state()
        self._run_fit(state)

    def _run_fit(self, state: dict):
        if self._fitter is None:
            QMessageBox.warning(self, "警告", "先にファイルを読み込んでください。")
            return
        original_title = self.windowTitle()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.setWindowTitle("計算中 — 曲線フィッター…")
        QApplication.processEvents()   # カーソル・タイトル変更を画面に反映
        try:
            if state["fit_mode"] == "manual":
                self._run_fit_manual(state)
            else:
                self._run_fit_auto(state)
        finally:
            QApplication.restoreOverrideCursor()
            self.setWindowTitle(original_title)

    def _run_fit_manual(self, state: dict):
        n_seg = state["n_segments"]
        types = state["seg_types"]
        tol   = state["tolerance"]
        sc = self._make_constraint(state["start_pin"], state["start_tangent"])
        ec = self._make_constraint(state["end_pin"],   state["end_tangent"])
        try:
            segs = self._fitter.fit(
                n_segments=n_seg, seg_types=types, tolerance=tol,
                start_constraint=sc, end_constraint=ec,
            )
            variance  = self._fitter.variance_score(segs)
            alpha     = self.param_window.get_alpha()
            composite = variance * (1.0 + alpha * n_seg)
            self._last_variance  = variance
            self._last_n         = n_seg
            self._last_composite = composite
            self._last_converged = True
            self._last_message   = f"手動フィット: {n_seg} セグメント"
            self.control_panel.update_result(
                variance, composite, n_seg,
                f"手動フィット: {n_seg} セグメント", True,
            )
            self._segments = segs
            self.plot_style_dialog.rebuild_color_buttons(n_seg)
            self.plot_widget.set_segments(segs, self.plot_style_dialog.get_colors())
            self.statusBar().showMessage(
                f"手動フィット完了: {n_seg} セグメント  Σdi²/n={variance:.6g}", 5000
            )
        except Exception as e:
            QMessageBox.critical(self, "フィットエラー", str(e))

    def _run_fit_auto(self, state: dict):
        sc = self._make_constraint(state["start_pin"], state["start_tangent"])
        ec = self._make_constraint(state["end_pin"],   state["end_tangent"])
        try:
            self.statusBar().showMessage("自動フィット中…", 0)
            result = self._fitter.fit_auto(
                threshold=state["threshold"],
                type_policy=state["type_policy"],
                max_segments=state["max_segments"],
                max_iter=state["max_iter"],
                tol_type=state["tol_type"],
                start_constraint=sc,
                end_constraint=ec,
            )
            alpha     = self.param_window.get_alpha()
            composite = result.score * (1.0 + alpha * result.n_segments)
            self._last_variance  = result.score
            self._last_n         = result.n_segments
            self._last_composite = composite
            self._last_converged = result.converged
            self._last_message   = result.message
            self.control_panel.update_result(
                result.score, composite, result.n_segments,
                result.message, result.converged,
            )
            self._segments = result.segments
            self.plot_style_dialog.rebuild_color_buttons(result.n_segments)
            self.plot_widget.set_segments(
                result.segments, self.plot_style_dialog.get_colors()
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

    def _on_alpha_changed(self, alpha: float):
        """α変更時に複合評価値をリアルタイム更新"""
        if self._last_variance is not None and self._last_n is not None:
            composite = self._last_variance * (1.0 + alpha * self._last_n)
            self.control_panel.update_composite(composite)

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
        state = self.param_window.get_fit_state()
        state["seg_colors"] = self.plot_style_dialog.get_colors()

        state["source_path"] = getattr(self, "_source_path", "")

        start_coord = None
        if self._points is not None and self.plot_widget._start_idx is not None:
            idx = self.plot_widget._start_idx
            if 0 <= idx < len(self._points):
                p = self._points[idx]
                start_coord = [float(p[0]), float(p[1])]
        state["start_point_coord"] = start_coord

        ex_coords = []
        if self._points is not None:
            for idx in sorted(self._excluded):
                if 0 <= idx < len(self._points):
                    p = self._points[idx]
                    ex_coords.append([float(p[0]), float(p[1])])
        state["excluded_coords"] = ex_coords

        state["variance"]          = self._last_variance
        state["composite"]         = self._last_composite
        state["result_n_segments"] = len(self._segments) if self._segments else None
        state["converged"]         = self._last_converged
        state["message"]           = self._last_message

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

        self.param_window.apply_fit_state(state)
        if "seg_colors" in state:
            self.plot_style_dialog.apply_colors(list(state["seg_colors"]))

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

        sp_coord = state.get("start_point_coord")
        start_raw_idx = None
        if sp_coord is not None:
            sp = np.array(sp_coord)
            dists = np.linalg.norm(pts_clean - sp, axis=1)
            start_raw_idx = int(np.argmin(dists))

        pts_sorted = sort_points(pts_clean, start_idx=start_raw_idx)
        min_dist   = state.get("min_dist", 0.0)
        if min_dist > 0:
            pts_sorted = remove_duplicates(pts_sorted, min_dist=min_dist)
        self._points   = pts_sorted
        self._excluded = set()

        ex_coords = state.get("excluded_coords", []) or []
        for coord in ex_coords:
            ec = np.array(coord)
            dists = np.linalg.norm(pts_sorted - ec, axis=1)
            idx   = int(np.argmin(dists))
            if idx not in self._excluded:
                self._excluded.add(idx)
                pt = pts_sorted[idx]
                self.param_window.add_excluded_point(idx, float(pt[0]), float(pt[1]))

        self.plot_widget.set_points(pts_sorted)
        self.plot_widget.set_excluded(self._excluded)
        if start_raw_idx is not None:
            self.plot_widget.set_start_index(0)

        self._rebuild_fitter()

        self.statusBar().showMessage(
            f"セッション読み込み完了: {path}  "
            f"(ソース: {src_path}  {len(pts_sorted)} 点)", 7000
        )
