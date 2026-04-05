"""
プロットウィジェット: Matplotlib を PyQt6 に埋め込む

モード:
  通常モード  : Matplotlib 標準のズーム/パン
  始点指定モード : クリックで最近傍点を始点として選択
  点除外モード  : クリックで最近傍点を計算から除外（赤×表示）
"""
from __future__ import annotations
import numpy as np
import matplotlib
matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# Use a CJK-capable font for Japanese labels in the plot canvas.
# Falls back to the default font if none of the candidates are found.
_JP_FONT_CANDIDATES = ["Noto Sans CJK JP", "IPAGothic", "IPAMincho", "TakaoPGothic"]
for _fp in _JP_FONT_CANDIDATES:
    if fm.findfont(_fp, fallback_to_default=False):
        matplotlib.rcParams["font.family"] = _fp
        break
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar,
)
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QCursor

from ..core.fitter import Segment, LineSegment, ArcSegment

_DEFAULT_COLORS = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
    "#42d4f4", "#f032e6", "#bfef45", "#fabed4", "#469990",
]

# インタラクションモード
_MODE_NORMAL  = "normal"
_MODE_PICK    = "pick"     # 始点指定
_MODE_EXCLUDE = "exclude"  # 点除外


class PlotWidget(QWidget):
    start_point_selected = pyqtSignal(int)          # 始点指定: points上のindex
    point_excluded       = pyqtSignal(int, float, float)  # 除外: index, x, y
    point_unexcluded     = pyqtSignal(int)          # 除外取消: index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fig, self.ax = plt.subplots(figsize=(7, 6), dpi=100)
        self.canvas  = FigureCanvas(self.fig)
        self.toolbar = NavigationToolbar(self.canvas, self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

        self._points:       np.ndarray | None = None
        self._segments:     list[Segment]     = []
        self._seg_colors:   list[str]         = []
        self._start_idx:    int | None        = None
        self._excluded:     set[int]          = set()   # 除外点インデックス集合
        self._mode:         str               = _MODE_NORMAL

        self._cid = self.canvas.mpl_connect(
            "button_press_event", self._on_canvas_click
        )
        self._setup_axes()

    # ------------------------------------------------------------------
    # 軸初期化・タイトル
    # ------------------------------------------------------------------
    def _setup_axes(self):
        self.ax.set_aspect("equal")
        self.ax.grid(True, linestyle="--", alpha=0.4)
        self._update_title()
        self.fig.tight_layout(rect=[0.05, 0, 1, 1])

    def _update_title(self):
        if self._mode == _MODE_PICK:
            self.ax.set_title(
                "【始点指定】クリックで始点を選択",
                color="#cc0000", fontsize=10,
            )
        elif self._mode == _MODE_EXCLUDE:
            self.ax.set_title(
                "【点除外】クリックで点を除外（再クリックで除外取消）",
                color="#bb5500", fontsize=10,
            )
        else:
            n_ex = len(self._excluded)
            n_total = len(self._points) if self._points is not None else 0
            suffix = f"  [除外中: {n_ex}点]" if n_ex else ""
            self.ax.set_title(
                f"点群 / セグメントプロット{suffix}", fontsize=10
            )

    # ------------------------------------------------------------------
    # 公開インターフェース
    # ------------------------------------------------------------------
    def set_points(self, points: np.ndarray):
        self._points    = points
        self._start_idx = None
        self._excluded  = set()
        self._redraw(reset_view=True)

    def set_segments(self, segments: list[Segment],
                     colors: list[str] | None = None):
        self._segments   = segments
        self._seg_colors = list(colors) if colors else []
        self._redraw()

    def set_start_index(self, idx: int | None):
        self._start_idx = idx
        self._redraw()

    def set_excluded(self, excluded: set[int]):
        """外部から除外セットを設定して再描画（reset 時など）"""
        self._excluded = set(excluded)
        self._redraw()

    def clear(self):
        self._points     = None
        self._segments   = []
        self._seg_colors = []
        self._start_idx  = None
        self._excluded   = set()
        self._redraw()

    def set_mode(self, mode: str):
        """
        モード切替: 'normal' / 'pick' / 'exclude'
        モード変更時に NavigationToolbar の有効/無効も切り替える。
        """
        assert mode in (_MODE_NORMAL, _MODE_PICK, _MODE_EXCLUDE)
        self._mode = mode
        cross = mode in (_MODE_PICK, _MODE_EXCLUDE)
        self.canvas.setCursor(
            QCursor(Qt.CursorShape.CrossCursor if cross
                    else Qt.CursorShape.ArrowCursor)
        )
        self.toolbar.setEnabled(not cross)
        self._update_title()
        self.canvas.draw_idle()

    # 後方互換: 始点指定モード用
    def set_pick_mode(self, enabled: bool):
        self.set_mode(_MODE_PICK if enabled else _MODE_NORMAL)

    def _color_for(self, i: int) -> str:
        if i < len(self._seg_colors) and self._seg_colors[i]:
            return self._seg_colors[i]
        return _DEFAULT_COLORS[i % len(_DEFAULT_COLORS)]

    # ------------------------------------------------------------------
    # クリックハンドラ
    # ------------------------------------------------------------------
    def _on_canvas_click(self, event):
        if self._mode == _MODE_NORMAL:
            return
        if event.inaxes is not self.ax:
            return
        if self._points is None or len(self._points) == 0:
            return
        if event.xdata is None or event.ydata is None:
            return

        click = np.array([event.xdata, event.ydata])
        dists = np.linalg.norm(self._points - click, axis=1)
        idx   = int(np.argmin(dists))

        if self._mode == _MODE_PICK:
            self._start_idx = idx
            self._redraw()
            self.start_point_selected.emit(idx)

        elif self._mode == _MODE_EXCLUDE:
            pt = self._points[idx]
            if idx in self._excluded:
                # 再クリック → 除外取消
                self._excluded.discard(idx)
                self._redraw()
                self.point_unexcluded.emit(idx)
            else:
                # 除外
                self._excluded.add(idx)
                self._redraw()
                self.point_excluded.emit(idx, float(pt[0]), float(pt[1]))

    # ------------------------------------------------------------------
    # 描画
    # ------------------------------------------------------------------
    def _redraw(self, reset_view: bool = False):
        try:
            xlim     = self.ax.get_xlim()
            ylim     = self.ax.get_ylim()
            had_data = self.ax.has_data() and not reset_view
        except Exception:
            had_data = False

        self.ax.cla()
        self._setup_axes()

        if self._points is not None and len(self._points):
            N = len(self._points)
            inc_mask = np.array([i not in self._excluded for i in range(N)])
            exc_mask = ~inc_mask

            # 有効点（青）
            if inc_mask.any():
                self.ax.scatter(
                    self._points[inc_mask, 0], self._points[inc_mask, 1],
                    s=6, c="#4a90d9", alpha=0.6,
                    label=f"点群 ({inc_mask.sum()} pts)", zorder=2,
                )

            # 除外点（赤×）
            if exc_mask.any():
                self.ax.scatter(
                    self._points[exc_mask, 0], self._points[exc_mask, 1],
                    s=40, c="#ff4444", alpha=0.8, marker="x", linewidths=1.5,
                    label=f"除外点 ({exc_mask.sum()} pts)", zorder=3,
                )

            # 自動始点（グレーひし形）
            self.ax.plot(
                *self._points[0], "D", color="#999999", ms=9, zorder=6,
                label="自動始点",
            )

            # ユーザー指定始点（赤星）
            if self._start_idx is not None and self._start_idx != 0:
                p = self._points[self._start_idx]
                self.ax.plot(
                    *p, "*", color="#dd0000", ms=14, zorder=7,
                    label=f"指定始点 (idx={self._start_idx})",
                )

        if self._segments:
            self._draw_segments()

        self.ax.legend(loc="best", fontsize=8)

        if had_data and self._points is not None:
            self.ax.set_xlim(xlim)
            self.ax.set_ylim(ylim)

        self.canvas.draw_idle()

    def _draw_segments(self):
        for i, seg in enumerate(self._segments):
            color = self._color_for(i)
            label = f"Seg{i+1} ({seg.kind})"
            if seg.kind == "line":
                self._draw_line(seg, color, label)
            else:
                self._draw_arc(seg, color, label)
            self.ax.plot(*seg.p0, "o", color=color, ms=5, zorder=5)
            self.ax.plot(*seg.p1, "s", color=color, ms=5, zorder=5)

    def _draw_line(self, seg: LineSegment, color: str, label: str):
        self.ax.plot(
            [seg.p0[0], seg.p1[0]], [seg.p0[1], seg.p1[1]],
            "-", color=color, lw=2.5, label=label, zorder=4,
        )

    def _draw_arc(self, seg: ArcSegment, color: str, label: str):
        ts, te = seg.theta_start, seg.theta_end
        if seg.ccw:
            if te < ts: te += 2 * np.pi
        else:
            if te > ts: te -= 2 * np.pi
        thetas = np.linspace(ts, te, max(50, int(abs(te - ts) / 0.05)))
        xs = seg.center[0] + seg.radius * np.cos(thetas)
        ys = seg.center[1] + seg.radius * np.sin(thetas)
        self.ax.plot(xs, ys, "-", color=color, lw=2.5, label=label, zorder=4)
