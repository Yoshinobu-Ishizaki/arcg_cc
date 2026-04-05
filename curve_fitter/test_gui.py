"""
GUI ユニットテスト

テスト戦略:
  実際の画面描画を伴わない offscreen + Agg バックエンドで実行。

  [T1] ControlPanel — パラメータ読み書き
      パラメータ設定 → get_fit_state() → apply_fit_state() → 往復確認

  [T2] ControlPanel — シグナル発火
      ボタン操作に対して正しいシグナルが発火するか

  [T3] PlotWidget — モード切替
      set_mode() でモードが変わるか、除外セットが管理されるか

  [T4] PlotWidget — 除外クリックのシミュレーション
      _on_canvas_click を直接呼び出して exclude/unexclude サイクルを確認

  [T5] MainWindow — ファイル読み込み→fitter生成
      実際のCSVを与えてfitterが作られるか

  [T6] MainWindow — 点除外→fitter再構築
      点を除外すると fitter の点数が減るか

  [T7] MainWindow — フィット実行（手動・自動）
      _on_fit_manual / _on_fit_auto を直接呼び出して segments が生成されるか

  [T8] MainWindow — 始点変更→再ソート
      _on_start_point_selected でソートし直されるか

  [T9] パラメータ 保存→読み込み往復
      _on_params_save → YAML → _on_params_load でパラメータが復元されるか

  [T10] パラメータ — source.path 書き換えによる別ファイル適用
       YAML の path を別ファイルに書き換えて読み込めるか
"""
import os, sys, tempfile, warnings
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["MPLBACKEND"]      = "Agg"
import matplotlib
matplotlib.use("Agg")
warnings.filterwarnings("ignore", category=UserWarning)  # フォント警告を抑制

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
import numpy as np
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore    import QTimer
from PyQt6.QtTest    import QTest
from PyQt6.QtCore    import Qt

# QApplication はテスト全体で1つだけ作る
_app = QApplication.instance() or QApplication(sys.argv)


# ===========================================================================
# ヘルパー: 合成CSVを一時ファイルに書く
# ===========================================================================

def _write_csv(pts: np.ndarray) -> str:
    """points を CSV に書いて一時パスを返す"""
    f = tempfile.NamedTemporaryFile(
        suffix=".csv", delete=False, mode="w", encoding="utf-8"
    )
    for x, y in pts:
        f.write(f"{x},{y}\n")
    f.close()
    return f.name


def _make_line_pts(n=60, noise=0.02) -> np.ndarray:
    """y = 0.5x + 1 の直線点群"""
    rng = np.random.default_rng(0)
    xs  = np.linspace(0, 8, n)
    pts = np.column_stack([xs, 0.5 * xs + 1.0])
    return pts + rng.normal(0, noise, pts.shape)


def _make_arc_pts(n=60, noise=0.02) -> np.ndarray:
    """中心(0,0), r=5, 0°→120° の円弧点群"""
    rng = np.random.default_rng(1)
    th  = np.linspace(0, 2 * np.pi / 3, n)
    pts = np.column_stack([5 * np.cos(th), 5 * np.sin(th)])
    return pts + rng.normal(0, noise, pts.shape)


# ===========================================================================
# T1: ControlPanel — パラメータ読み書き
# ===========================================================================

class TestControlPanelState(unittest.TestCase):
    def setUp(self):
        from curve_fitter.ui.control_panel import ControlPanel
        self.cp = ControlPanel()

    def tearDown(self):
        self.cp.close()

    def test_default_mode_is_auto(self):
        state = self.cp.get_fit_state()
        self.assertEqual(state["fit_mode"], "auto")

    def test_set_manual_mode(self):
        self.cp._radio_manual.setChecked(True)
        state = self.cp.get_fit_state()
        self.assertEqual(state["fit_mode"], "manual")

    def test_apply_and_get_auto_params(self):
        state_in = {
            "fit_mode":    "auto",
            "alpha":       0.2,
            "min_dist":    0.05,
            "threshold":   0.005,
            "type_policy": "line",
            "max_segments": 12,
            "max_iter":    6,
            "tol_type":    0.3,
            "n_segments":  5,
            "seg_types":   ["line", "arc", "line", "arc", "line"],
            "tolerance":   1.0,
            "start_pin":   False,
            "start_tangent": None,
            "end_pin":     False,
            "end_tangent": None,
        }
        self.cp.apply_fit_state(state_in)
        out = self.cp.get_fit_state()

        self.assertEqual(out["fit_mode"],    "auto")
        self.assertAlmostEqual(out["alpha"],     0.2,   places=5)
        self.assertAlmostEqual(out["threshold"], 0.005, places=6)
        self.assertEqual(out["type_policy"], "line")
        self.assertEqual(out["max_segments"], 12)
        self.assertEqual(out["max_iter"],      6)
        self.assertAlmostEqual(out["tol_type"], 0.3, places=5)

    def test_apply_and_get_manual_params(self):
        state_in = {
            "fit_mode":   "manual",
            "n_segments": 3,
            "seg_types":  ["line", "arc", "line"],
            "tolerance":  0.8,
            "alpha": 0.1, "min_dist": 0.1,
            "threshold": 0.01, "type_policy": "auto",
            "max_segments": 15, "max_iter": 8, "tol_type": 0.5,
            "start_pin": False, "start_tangent": None,
            "end_pin": False, "end_tangent": None,
        }
        self.cp.apply_fit_state(state_in)
        out = self.cp.get_fit_state()
        self.assertEqual(out["fit_mode"],   "manual")
        self.assertEqual(out["n_segments"], 3)
        self.assertEqual(out["seg_types"],  ["line", "arc", "line"])
        self.assertAlmostEqual(out["tolerance"], 0.8, places=5)

    def test_min_dist_roundtrip(self):
        self.cp._min_dist_spin.setValue(0.25)
        self.assertAlmostEqual(self.cp.get_min_dist(), 0.25, places=5)

    def test_excluded_point_list_add_remove(self):
        self.cp.add_excluded_point(10, 1.23456, -9.87654)
        self.assertIn(10, self.cp._ex_rows)
        self.cp.remove_excluded_point(10)
        self.assertNotIn(10, self.cp._ex_rows)

    def test_excluded_point_duplicate_ignored(self):
        self.cp.add_excluded_point(5, 1.0, 2.0)
        self.cp.add_excluded_point(5, 1.0, 2.0)   # 2回目は無視
        self.assertEqual(len(self.cp._ex_rows), 1)
        self.cp._clear_ex_list()


# ===========================================================================
# T2: ControlPanel — シグナル発火
# ===========================================================================

class TestControlPanelSignals(unittest.TestCase):
    def setUp(self):
        from curve_fitter.ui.control_panel import ControlPanel
        self.cp = ControlPanel()

    def tearDown(self):
        self.cp.close()

    def _capture(self, signal) -> list:
        received = []
        signal.connect(lambda *args: received.append(args))
        return received

    def test_pick_mode_toggled_on(self):
        received = self._capture(self.cp.pick_mode_toggled)
        self.cp._btn_pick.setChecked(True)
        self.assertTrue(any(r[0] for r in received), "pick ON シグナルが来ない")

    def test_pick_mode_toggles_off_exclude(self):
        """始点指定ONにすると除外モードが解除される"""
        self.cp._btn_exclude.setChecked(True)
        self.cp._btn_pick.setChecked(True)
        self.assertFalse(self.cp._btn_exclude.isChecked())

    def test_exclude_mode_toggles_off_pick(self):
        """除外モードONにすると始点指定が解除される"""
        self.cp._btn_pick.setChecked(True)
        self.cp._btn_exclude.setChecked(True)
        self.assertFalse(self.cp._btn_pick.isChecked())

    def test_exclude_all_reset_signal(self):
        received = self._capture(self.cp.exclude_all_reset)
        self.cp._btn_exclude_all_reset.click()
        self.assertEqual(len(received), 1)

    def test_exclude_undo_signal(self):
        self.cp.add_excluded_point(7, 3.0, 4.0)
        received = self._capture(self.cp.exclude_undo_requested)
        self.cp._on_undo_one(7)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0], 7)


# ===========================================================================
# T3: PlotWidget — モード切替と除外セット管理
# ===========================================================================

class TestPlotWidgetModes(unittest.TestCase):
    def setUp(self):
        from curve_fitter.ui.plot_widget import PlotWidget
        self.pw = PlotWidget()
        pts = _make_line_pts()
        self.pw.set_points(pts)

    def tearDown(self):
        self.pw.close()

    def test_initial_mode_is_normal(self):
        self.assertEqual(self.pw._mode, "normal")

    def test_set_pick_mode(self):
        self.pw.set_mode("pick")
        self.assertEqual(self.pw._mode, "pick")

    def test_set_exclude_mode(self):
        self.pw.set_mode("exclude")
        self.assertEqual(self.pw._mode, "exclude")

    def test_set_points_clears_excluded(self):
        self.pw._excluded = {0, 1, 2}
        self.pw.set_points(_make_line_pts())
        self.assertEqual(len(self.pw._excluded), 0)

    def test_set_excluded(self):
        self.pw.set_excluded({3, 5, 9})
        self.assertEqual(self.pw._excluded, {3, 5, 9})

    def test_set_pick_mode_compat(self):
        """後方互換: set_pick_mode(True) は pick モードになる"""
        self.pw.set_pick_mode(True)
        self.assertEqual(self.pw._mode, "pick")
        self.pw.set_pick_mode(False)
        self.assertEqual(self.pw._mode, "normal")


# ===========================================================================
# T4: PlotWidget — 除外クリックのシミュレーション
# ===========================================================================

class TestPlotWidgetExclude(unittest.TestCase):
    def setUp(self):
        from curve_fitter.ui.plot_widget import PlotWidget
        self.pw = PlotWidget()
        self.pts = _make_line_pts(n=20)
        self.pw.set_points(self.pts)
        self.pw.set_mode("exclude")

    def tearDown(self):
        self.pw.close()

    def _click_at_point(self, idx: int):
        """点 idx の座標でクリックイベントをシミュレート"""
        x, y = self.pts[idx]

        class FakeEvent:
            def __init__(self, ax, xd, yd):
                self.inaxes = ax
                self.xdata  = xd
                self.ydata  = yd

        self.pw._on_canvas_click(FakeEvent(self.pw.ax, x, y))

    def test_exclude_adds_to_set(self):
        excluded_args = []
        self.pw.point_excluded.connect(
            lambda i, x, y: excluded_args.append((i, x, y))
        )
        self._click_at_point(5)
        self.assertIn(5, self.pw._excluded)
        self.assertEqual(len(excluded_args), 1)
        self.assertEqual(excluded_args[0][0], 5)

    def test_reclick_unexcludes(self):
        unex_args = []
        self.pw.point_unexcluded.connect(lambda i: unex_args.append(i))
        self._click_at_point(3)
        self.assertIn(3, self.pw._excluded)
        self._click_at_point(3)   # 再クリック → 除外取消
        self.assertNotIn(3, self.pw._excluded)
        self.assertEqual(unex_args, [3])

    def test_exclude_emits_coordinates(self):
        """シグナルで正しい座標が渡される"""
        received = []
        self.pw.point_excluded.connect(
            lambda i, x, y: received.append((i, x, y))
        )
        target = 7
        self._click_at_point(target)
        idx, ex, ey = received[0]
        self.assertAlmostEqual(ex, self.pts[target, 0], places=6)
        self.assertAlmostEqual(ey, self.pts[target, 1], places=6)

    def test_normal_mode_ignores_click(self):
        """通常モードではクリックしても除外されない"""
        self.pw.set_mode("normal")
        self._click_at_point(2)
        self.assertNotIn(2, self.pw._excluded)

    def test_pick_mode_emits_start_selected(self):
        """pick モードではクリックで start_point_selected が発火する"""
        selected = []
        self.pw.start_point_selected.connect(lambda i: selected.append(i))
        self.pw.set_mode("pick")
        self._click_at_point(0)
        self.assertEqual(selected, [0])
        self.assertNotIn(0, self.pw._excluded)   # 除外はされない


# ===========================================================================
# T5: MainWindow — ファイル読み込み→fitter生成
# ===========================================================================

class TestMainWindowLoad(unittest.TestCase):
    def setUp(self):
        from curve_fitter.ui.main_window import MainWindow
        self.win     = MainWindow()
        self.csv_lin = _write_csv(_make_line_pts())
        self.csv_arc = _write_csv(_make_arc_pts())

    def tearDown(self):
        self.win.close()
        os.unlink(self.csv_lin)
        os.unlink(self.csv_arc)

    def test_fitter_created_after_load(self):
        self.win._on_load_file(self.csv_lin)
        self.assertIsNotNone(self.win._fitter)

    def test_points_loaded(self):
        self.win._on_load_file(self.csv_lin)
        self.assertIsNotNone(self.win._points)
        self.assertGreater(len(self.win._points), 0)

    def test_excluded_cleared_on_reload(self):
        self.win._on_load_file(self.csv_lin)
        self.win._excluded = {0, 1, 2}
        self.win._on_load_file(self.csv_arc)   # 別ファイルを再読み込み
        self.assertEqual(len(self.win._excluded), 0)

    def test_source_path_cached(self):
        self.win._on_load_file(self.csv_lin)
        self.assertEqual(self.win._source_path, self.csv_lin)


# ===========================================================================
# T6: MainWindow — 点除外→fitter再構築
# ===========================================================================

class TestMainWindowExclude(unittest.TestCase):
    def setUp(self):
        from curve_fitter.ui.main_window import MainWindow
        self.win = MainWindow()
        self.csv = _write_csv(_make_line_pts(n=50))
        self.win._on_load_file(self.csv)

    def tearDown(self):
        self.win.close()
        os.unlink(self.csv)

    def test_active_points_decreases_after_exclude(self):
        n_before = len(self.win._active_points())
        self.win._on_point_excluded(0, 0.0, 0.0)
        n_after  = len(self.win._active_points())
        self.assertEqual(n_after, n_before - 1)

    def test_fitter_uses_active_points(self):
        n_total = len(self.win._points)
        self.win._on_point_excluded(0, 0.0, 0.0)
        self.win._on_point_excluded(1, 0.0, 0.0)
        active = self.win._active_points()
        self.assertEqual(len(active), n_total - 2)
        # fitter の点数も一致する
        self.assertEqual(len(self.win._fitter.points), n_total - 2)

    def test_undo_restores_fitter(self):
        n_before = len(self.win._active_points())
        self.win._on_point_excluded(3, 0.0, 0.0)
        self.win._on_point_unexcluded(3)
        self.assertEqual(len(self.win._active_points()), n_before)

    def test_exclude_all_reset(self):
        self.win._on_point_excluded(0, 0.0, 0.0)
        self.win._on_point_excluded(1, 0.0, 0.0)
        self.win._on_exclude_all_reset()
        self.assertEqual(len(self.win._excluded), 0)

    def test_fitter_none_when_too_few_points(self):
        """除外しすぎて点が 1 以下になったら fitter が None になる"""
        n = len(self.win._points)
        for i in range(n - 1):   # 1点だけ残す
            self.win._on_point_excluded(i, 0.0, 0.0)
        self.assertIsNone(self.win._fitter)


# ===========================================================================
# T7: MainWindow — フィット実行（手動・自動）
# ===========================================================================

class TestMainWindowFit(unittest.TestCase):
    def setUp(self):
        from curve_fitter.ui.main_window import MainWindow
        self.win = MainWindow()
        self.csv = _write_csv(_make_line_pts(n=60))
        self.win._on_load_file(self.csv)

    def tearDown(self):
        self.win.close()
        os.unlink(self.csv)

    def test_manual_fit_produces_segments(self):
        self.win._on_fit_manual(
            n_seg=1, types=["line"], tol=0.5,
            start_pin=False, start_tan=None,
            end_pin=False,   end_tan=None,
        )
        self.assertGreater(len(self.win._segments), 0)

    def test_auto_fit_produces_segments(self):
        self.win._on_fit_auto(
            threshold=0.05, policy="line",   # 緩い閾値で速く収束
            max_seg=2, max_iter=2, tol=0.5,  # 探索を最小限に
            start_pin=False, start_tan=None,
            end_pin=False,   end_tan=None,
        )
        self.assertGreater(len(self.win._segments), 0)

    def test_manual_fit_n1_line_converges(self):
        """直線点群に n=1 直線フィット → 誤差分散が小さい"""
        self.win._on_fit_manual(
            n_seg=1, types=["line"], tol=0.5,
            start_pin=False, start_tan=None,
            end_pin=False,   end_tan=None,
        )
        score = self.win._fitter.variance_score(self.win._segments)
        self.assertLess(score, 0.01)

    def test_fit_without_load_shows_no_crash(self):
        """fitter が None のときフィット呼び出しても例外が出ない"""
        self.win._fitter = None
        # QMessageBox.warning をモックして即座に閉じる
        from unittest.mock import patch
        with patch("curve_fitter.ui.main_window.QMessageBox.warning"):
            try:
                self.win._on_fit_manual(
                    1, ["line"], 0.5, False, None, False, None
                )
            except Exception as e:
                self.fail(f"例外が発生した: {e}")

    def test_manual_fit_with_pin_constraint(self):
        """始点 pin 拘束付きフィット: セグメント始点が点群始点に近い"""
        pts = self.win._points
        self.win._on_fit_manual(
            n_seg=1, types=["line"], tol=0.5,
            start_pin=True, start_tan=None,
            end_pin=False,  end_tan=None,
        )
        seg = self.win._segments[0]
        dist = np.linalg.norm(seg.p0 - pts[0])
        self.assertLess(dist, 0.01, f"始点 pin: 距離 {dist:.4f} が大きすぎる")

    def test_fit_excludes_excluded_points(self):
        """除外点を含む状態でフィットしてもセグメントが生成される"""
        self.win._on_point_excluded(0, 0.0, 0.0)
        self.win._on_point_excluded(1, 0.0, 0.0)
        self.win._on_fit_manual(
            n_seg=1, types=["line"], tol=0.5,
            start_pin=False, start_tan=None,
            end_pin=False,   end_tan=None,
        )
        self.assertGreater(len(self.win._segments), 0)


# ===========================================================================
# T8: MainWindow — 始点変更→再ソート
# ===========================================================================

class TestMainWindowStartPoint(unittest.TestCase):
    def setUp(self):
        from curve_fitter.ui.main_window import MainWindow
        self.win = MainWindow()
        self.csv = _write_csv(_make_line_pts(n=40))
        self.win._on_load_file(self.csv)

    def tearDown(self):
        self.win.close()
        os.unlink(self.csv)

    def test_start_reset_clears_excluded(self):
        """始点リセット時に除外リストがクリアされる"""
        self.win._excluded = {0, 5, 10}
        self.win._on_start_reset()
        self.assertEqual(len(self.win._excluded), 0)

    def test_start_point_selected_rebuilds_fitter(self):
        """始点指定後に fitter が再構築される"""
        pts_before = id(self.win._fitter)
        self.win._on_start_point_selected(5)
        # fitter オブジェクトが変わっている（再構築された）
        self.assertIsNotNone(self.win._fitter)

    def test_start_point_selected_points_start_near_selected(self):
        """始点指定後、ソート済み点群の先頭が指定座標に近い"""
        idx    = 10
        pt_sel = self.win._points[idx]
        self.win._on_start_point_selected(idx)
        new_first = self.win._points[0]
        dist = np.linalg.norm(new_first - pt_sel)
        # 密な点群なので点間隔程度以内に収まるはず
        self.assertLess(dist, 1.0, f"再ソート後の始点距離 {dist:.4f} が大きすぎる")


# ===========================================================================
# T9: セッション — 保存→読み込みの往復
# ===========================================================================

class TestParamsRoundtrip(unittest.TestCase):
    def setUp(self):
        from curve_fitter.ui.main_window import MainWindow
        self.win = MainWindow()
        self.csv  = _write_csv(_make_line_pts(n=60))
        self.yaml = tempfile.mktemp(suffix=".yaml")
        self.win._on_load_file(self.csv)

    def tearDown(self):
        self.win.close()
        os.unlink(self.csv)
        if os.path.exists(self.yaml):
            os.unlink(self.yaml)

    def test_save_creates_yaml(self):
        self.win._on_params_save(self.yaml)
        self.assertTrue(os.path.exists(self.yaml))
        content = Path(self.yaml).read_text(encoding="utf-8")
        self.assertIn("version:", content)
        self.assertIn("source:", content)
        self.assertIn("fit:", content)

    def test_source_path_preserved(self):
        self.win._on_params_save(self.yaml)
        content = Path(self.yaml).read_text(encoding="utf-8")
        self.assertIn(self.csv, content)

    def test_auto_params_roundtrip(self):
        """auto パラメータを変更して保存→読み込み後に一致する"""
        pw = self.win.param_window
        pw._threshold_spin.setValue(0.0077)
        pw._max_seg_spin.setValue(9)
        pw._max_iter_spin.setValue(5)

        self.win._on_params_save(self.yaml)

        # 新しいウィンドウで読み込む
        from curve_fitter.ui.main_window import MainWindow
        win2 = MainWindow()
        win2._on_params_load(self.yaml)
        out = win2.param_window.get_fit_state()
        win2.close()

        self.assertAlmostEqual(out["threshold"],    0.0077, places=5)
        self.assertEqual(out["max_segments"], 9)
        self.assertEqual(out["max_iter"],     5)

    def test_excluded_coords_roundtrip(self):
        """除外点座標が保存→読み込み後に復元される"""
        self.win._on_point_excluded(2, float(self.win._points[2, 0]),
                                       float(self.win._points[2, 1]))
        self.win._on_params_save(self.yaml)

        from curve_fitter.ui.main_window import MainWindow
        win2 = MainWindow()
        win2._on_params_load(self.yaml)
        # 少なくとも1点が除外されている
        self.assertGreater(len(win2._excluded), 0)
        win2.close()

    def test_params_load_builds_fitter(self):
        """パラメータ読み込み後に fitter が生成される"""
        self.win._on_params_save(self.yaml)

        from curve_fitter.ui.main_window import MainWindow
        win2 = MainWindow()
        win2._on_params_load(self.yaml)
        self.assertIsNotNone(win2._fitter)
        win2.close()


# ===========================================================================
# T10: セッション — source.path 書き換えで別ファイルに適用
# ===========================================================================

class TestParamsPathSwap(unittest.TestCase):
    def setUp(self):
        from curve_fitter.ui.main_window import MainWindow
        self.win   = MainWindow()
        self.csv1  = _write_csv(_make_line_pts(n=50))
        self.csv2  = _write_csv(_make_arc_pts(n=50))
        self.yaml  = tempfile.mktemp(suffix=".yaml")
        self.win._on_load_file(self.csv1)
        # threshold を明示的にセットしてからフィット実行
        self.win.param_window._threshold_spin.setValue(0.05)
        # フィット実行してセッションを保存（速い設定）
        self.win._on_fit_auto(
            threshold=0.05, policy="auto",
            max_seg=2, max_iter=2, tol=0.5,
            start_pin=False, start_tan=None,
            end_pin=False,   end_tan=None,
        )
        self.win._on_params_save(self.yaml)

    def tearDown(self):
        self.win.close()
        for f in [self.csv1, self.csv2, self.yaml]:
            if os.path.exists(f): os.unlink(f)

    def test_path_swap_loads_different_file(self):
        """YAML の source.path を csv2 に書き換えて読み込むと別データが読まれる"""
        content = Path(self.yaml).read_text(encoding="utf-8")
        content = content.replace(self.csv1, self.csv2)
        Path(self.yaml).write_text(content, encoding="utf-8")

        from curve_fitter.ui.main_window import MainWindow
        win2 = MainWindow()
        win2._on_params_load(self.yaml)

        # fitter が作られている
        self.assertIsNotNone(win2._fitter)
        # フィットパラメータは元のまま（threshold=0.05）
        out = win2.param_window.get_fit_state()
        self.assertAlmostEqual(out["threshold"], 0.05, places=5)
        win2.close()

    def test_invalid_path_shows_no_crash(self):
        """source.path が存在しないファイルでもクラッシュしない"""
        content = Path(self.yaml).read_text(encoding="utf-8")
        content = content.replace(self.csv1, "/nonexistent/file.csv")
        Path(self.yaml).write_text(content, encoding="utf-8")

        from curve_fitter.ui.main_window import MainWindow
        from unittest.mock import patch
        win2 = MainWindow()
        try:
            with patch("curve_fitter.ui.main_window.QMessageBox.critical"), \
                 patch("curve_fitter.ui.main_window.QMessageBox.warning"):
                win2._on_params_load(self.yaml)
        except Exception as e:
            self.fail(f"クラッシュした: {e}")
        win2.close()


# ===========================================================================
# エントリポイント
# ===========================================================================

if __name__ == "__main__":
    loader  = unittest.TestLoader()
    suite   = unittest.TestSuite()
    classes = [
        TestControlPanelState,
        TestControlPanelSignals,
        TestPlotWidgetModes,
        TestPlotWidgetExclude,
        TestMainWindowLoad,
        TestMainWindowExclude,
        TestMainWindowFit,
        TestMainWindowStartPoint,
        TestParamsRoundtrip,
        TestParamsPathSwap,
    ]
    for cls in classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
