"""
セグメントフィッティング: 直線 / 円弧 のフィット + G1連続補正（厳密版）

G1連続補正の方針:
    各セグメント境界点について、以下を scipy.optimize.minimize で最適化する。
    - 境界点座標 (bx, by) を変数とする
    - 前セグメントの終端接線 == 後セグメントの始端接線（等号拘束）
    - 各セグメントへのフィット残差を最小化（目的関数）

    境界ごとに独立した2変数最適化なので計算コストは低い。

使い方:
    fitter = SegmentFitter(points)
    segments = fitter.fit(
        n_segments=5,
        seg_types=["auto", "auto", ...],   # 'line' / 'arc' / 'auto'
        tol=0.5,
    )
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
from scipy.optimize import least_squares, minimize
from typing import Literal


SegType = Literal["line", "arc"]


@dataclass
class LineSegment:
    kind: Literal["line"] = field(default="line", init=False)
    p0: np.ndarray   # 始点 [x, y]
    p1: np.ndarray   # 終点 [x, y]

    @property
    def tangent_start(self) -> np.ndarray:
        v = self.p1 - self.p0
        return v / (np.linalg.norm(v) + 1e-12)

    @property
    def tangent_end(self) -> np.ndarray:
        return self.tangent_start


@dataclass
class ArcSegment:
    kind: Literal["arc"] = field(default="arc", init=False)
    center: np.ndarray   # 円弧中心 [cx, cy]
    radius: float
    theta_start: float   # rad
    theta_end: float     # rad
    ccw: bool = True     # 反時計回り

    @property
    def p0(self) -> np.ndarray:
        return self.center + self.radius * np.array(
            [np.cos(self.theta_start), np.sin(self.theta_start)]
        )

    @property
    def p1(self) -> np.ndarray:
        return self.center + self.radius * np.array(
            [np.cos(self.theta_end), np.sin(self.theta_end)]
        )

    @property
    def tangent_start(self) -> np.ndarray:
        # 接線 = 半径方向に垂直
        r = np.array([np.cos(self.theta_start), np.sin(self.theta_start)])
        t = np.array([-r[1], r[0]]) if self.ccw else np.array([r[1], -r[0]])
        return t

    @property
    def tangent_end(self) -> np.ndarray:
        r = np.array([np.cos(self.theta_end), np.sin(self.theta_end)])
        t = np.array([-r[1], r[0]]) if self.ccw else np.array([r[1], -r[0]])
        return t


Segment = LineSegment | ArcSegment


@dataclass
class FitResult:
    """
    fit_auto() の返却値。

    Attributes
    ----------
    segments    : G1連続セグメントのリスト
    n_segments  : セグメント数
    score       : Σdi²/n  （垂線距離²の平均 = 誤差分散）
    converged   : 閾値以下に収束したか
    message     : 収束状態の説明
    history     : [(n_seg, score), ...] — 各試行の履歴
    """
    segments:   list
    n_segments: int
    score:      float
    converged:  bool
    message:    str
    history:    list[tuple[int, float]] = field(default_factory=list)


@dataclass
class EndpointConstraint:
    """
    始点または終点への拘束条件。

    Attributes
    ----------
    pin     : True のとき、その端点は点群の始端/終端を必ず通る
    tangent : None でなければ、その方向を端点での接線ベクトルとして強制する
              （単位ベクトルに正規化して使用。向きは曲線の進行方向に揃える）

    Examples
    --------
    EndpointConstraint(pin=True,  tangent=None)            # 通過のみ
    EndpointConstraint(pin=False, tangent=np.array([1,0])) # 接線のみ
    EndpointConstraint(pin=True,  tangent=np.array([1,0])) # 両方
    EndpointConstraint(pin=False, tangent=None)            # 拘束なし（デフォルト）
    """
    pin:     bool                    = False
    tangent: np.ndarray | None       = None

    def __post_init__(self):
        if self.tangent is not None:
            t = np.asarray(self.tangent, dtype=float)
            norm = np.linalg.norm(t)
            if norm < 1e-10:
                raise ValueError("接線ベクトルのノルムが 0 です")
            self.tangent = t / norm


class SegmentFitter:
    """点群を n_segments 個の直線/円弧セグメント（G1連続）でフィット"""

    def __init__(
        self,
        points: np.ndarray,
        max_radius: float | None = None,
        min_radius: float | None = None,
    ):
        self.points = points  # shape (N, 2)
        self.max_radius = max_radius  # これより大きい半径の円弧は直線に置き換え
        self.min_radius = min_radius  # これより小さい半径の円弧は削除して隣接要素を接続

    # ------------------------------------------------------------------
    # メインエントリポイント
    # ------------------------------------------------------------------
    def fit(
        self,
        n_segments: int = 3,
        seg_types: list[str] | None = None,
        tolerance: float = 1.0,
        start_constraint: "EndpointConstraint | None" = None,
        end_constraint:   "EndpointConstraint | None" = None,
    ) -> list[Segment]:
        """
        Parameters
        ----------
        n_segments        : セグメント数
        seg_types         : 各セグメントの種別リスト ('line' / 'arc' / 'auto')
                            None の場合は全て 'auto'
        tolerance         : 許容残差（'auto' 判定に使用）
        start_constraint  : 始点への拘束（EndpointConstraint）。None は拘束なし
        end_constraint    : 終点への拘束（EndpointConstraint）。None は拘束なし

        Returns
        -------
        G1連続を満たす Segment のリスト
        """
        pts = self.points
        N = len(pts)
        if n_segments < 1 or N < 2:
            return []

        if seg_types is None:
            seg_types = ["auto"] * n_segments
        seg_types = list(seg_types)
        while len(seg_types) < n_segments:
            seg_types.append("auto")

        # 点群をセグメント数で均等分割
        split_indices = np.linspace(0, N - 1, n_segments + 1, dtype=int)
        chunks = [
            pts[split_indices[i]: split_indices[i + 1] + 1]
            for i in range(n_segments)
        ]

        segments: list[Segment] = []
        for i, (chunk, stype) in enumerate(zip(chunks, seg_types)):
            resolved = self._resolve_type(chunk, stype, tolerance)
            if resolved == "line":
                seg = self._fit_line(chunk)
            else:
                seg = self._fit_arc(chunk)
            segments.append(seg)

        sc = start_constraint or EndpointConstraint()
        ec = end_constraint   or EndpointConstraint()

        # 内部境界の G1 補正
        segments = self._enforce_g1(segments)

        # 両端の拘束適用
        segments = self._apply_endpoint_constraints(segments, pts, sc, ec)

        # 端点拘束で隣接境界の G1 が崩れるため再補正する（収束まで繰り返す）
        if len(segments) > 1 and (sc.pin or sc.tangent is not None
                                   or ec.pin or ec.tangent is not None):
            for _ in range(3):
                segments = self._enforce_g1(segments, sc, ec)

        # R_min 後処理: 小さすぎる円弧を削除し隣接要素を接続
        segments = self._remove_small_arcs(segments)
        return segments

    # ------------------------------------------------------------------
    # 自動セグメント数探索（誤差分散ベース）
    # ------------------------------------------------------------------
    def fit_auto(
        self,
        threshold:   float,
        seg_types:   list[str] | None = None,
        type_policy: str = "auto",
        max_segments: int = 20,
        max_iter:    int  = 5,
        tol_type:    float = 1.0,
        start_constraint: "EndpointConstraint | None" = None,
        end_constraint:   "EndpointConstraint | None" = None,
    ) -> FitResult:
        """
        誤差分散 Σdi²/n が threshold 未満となる最小セグメント数を探索する。

        Parameters
        ----------
        threshold    : 誤差分散の閾値。この値未満を「合格」とする
        seg_types    : セグメント種別リスト。None なら type_policy に従う
        type_policy  : seg_types が None のときの種別戦略
                       'auto'  ... 各区間の残差で自動判定（デフォルト）
                       'line'  ... 全て直線
                       'arc'   ... 全て円弧
        max_segments : 試みる最大セグメント数
        max_iter     : 同一セグメント数での境界最適化の繰り返し上限
        tol_type     : _resolve_type に渡す許容残差

        Returns
        -------
        FitResult
        """
        history: list[tuple[int, float]] = []
        best_segments: list[Segment] = []
        best_score = float("inf")
        converged = False

        for n in range(1, max_segments + 1):
            # 種別リストを構築
            if seg_types is not None:
                # 長さが足りなければ末尾を type_policy で補完
                types = list(seg_types)
                while len(types) < n:
                    types.append(type_policy)
                types = types[:n]
            else:
                types = [type_policy] * n

            # 境界位置を反復最適化
            segs, score, boundaries = self._fit_with_boundary_opt(
                n_segments=n,
                seg_types=types,
                tol_type=tol_type,
                max_iter=max_iter,
                start_constraint=start_constraint or EndpointConstraint(),
                end_constraint=end_constraint     or EndpointConstraint(),
            )
            history.append((n, score))

            if score < best_score:
                best_score = score
                best_segments = segs

            # アルゴリズム仕様ステップ15-16: 全体 D_t < δ で収束判定
            if score < threshold:
                converged = True
                msg = (
                    f"収束: セグメント数 {n} で誤差分散 {score:.6g} < "
                    f"閾値 {threshold:.6g} を達成"
                )
                break
        else:
            msg = (
                f"未収束: セグメント数を {max_segments} まで増やしても "
                f"誤差分散 {best_score:.6g} が閾値 {threshold:.6g} を下回りませんでした。"
                f"最終結果（セグメント数 {len(best_segments)}）を返します。"
            )

        # R_min 後処理: 小さすぎる円弧を削除し隣接要素を接続
        best_segments = self._remove_small_arcs(best_segments)

        return FitResult(
            segments=best_segments,
            n_segments=len(best_segments),
            score=best_score,
            converged=converged,
            message=msg,
            history=history,
        )

    def _fit_with_boundary_opt(
        self,
        n_segments: int,
        seg_types:  list[str],
        tol_type:   float,
        max_iter:   int,
        start_constraint: "EndpointConstraint | None" = None,
        end_constraint:   "EndpointConstraint | None" = None,
    ) -> tuple[list[Segment], float, list[int]]:
        """
        境界インデックスを反復的に最適化しながらフィットする。
        返り値は (segments, score, boundaries) の3要素タプル。
        """
        pts = self.points
        N = len(pts)
        sc = start_constraint or EndpointConstraint()
        ec = end_constraint   or EndpointConstraint()

        # 初期境界インデックス（均等分割）
        boundaries = np.linspace(0, N - 1, n_segments + 1, dtype=int).tolist()
        best_boundaries = list(boundaries)

        has_constraint = sc.pin or sc.tangent is not None or ec.pin or ec.tangent is not None

        best_segs  = self._build_segments(boundaries, seg_types, tol_type)
        best_segs  = self._enforce_g1(best_segs)
        best_segs  = self._apply_endpoint_constraints(best_segs, pts, sc, ec)
        if len(best_segs) > 1 and has_constraint:
            for _ in range(3):
                best_segs = self._enforce_g1(best_segs, sc, ec)
        best_score = self.variance_score(best_segs)

        for _ in range(max_iter):
            improved = False
            for bi in range(1, len(boundaries) - 1):
                orig = boundaries[bi]
                lo = boundaries[bi - 1] + 1
                hi = boundaries[bi + 1] - 1
                if lo >= hi:
                    continue

                search_radius = max(1, (hi - lo) // 4)
                candidates = list(range(
                    max(lo, orig - search_radius),
                    min(hi, orig + search_radius) + 1
                ))

                for cand in candidates:
                    if cand == orig:
                        continue
                    boundaries[bi] = cand
                    segs  = self._build_segments(boundaries, seg_types, tol_type)
                    segs  = self._enforce_g1(segs)
                    segs  = self._apply_endpoint_constraints(segs, pts, sc, ec)
                    if len(segs) > 1 and has_constraint:
                        for _ in range(3):
                            segs = self._enforce_g1(segs, sc, ec)
                    score = self.variance_score(segs)
                    if score < best_score:
                        best_score = score
                        best_segs  = segs
                        best_boundaries = list(boundaries)
                        orig = cand
                        improved = True
                    else:
                        boundaries[bi] = orig

            if not improved:
                break

        return best_segs, best_score, best_boundaries

    def _build_segments(
        self,
        boundaries: list[int],
        seg_types:  list[str],
        tol_type:   float,
    ) -> list[Segment]:
        """境界インデックスリストから各区間をフィットしてセグメントリストを返す"""
        pts = self.points
        n = len(boundaries) - 1
        segments: list[Segment] = []
        for i in range(n):
            chunk = pts[boundaries[i]: boundaries[i + 1] + 1]
            if len(chunk) < 2:
                chunk = pts[boundaries[i]: boundaries[i] + 2]
            stype = seg_types[i] if i < len(seg_types) else "auto"
            resolved = self._resolve_type(chunk, stype, tol_type)
            if resolved == "line":
                segments.append(self._fit_line(chunk))
            else:
                segments.append(self._fit_arc(chunk))
        return segments

    # ------------------------------------------------------------------
    # R_min 後処理: 小さすぎる円弧を削除して隣接要素を直接接続
    # ------------------------------------------------------------------
    def _remove_small_arcs(self, segments: list) -> list:
        """
        半径 < min_radius の円弧セグメントを削除し、隣接要素を直接接続する。

        - 中間にある場合: 前後のセグメントを円弧の中点で接続
        - 先頭にある場合: 次のセグメントを円弧の始点まで延長
        - 末尾にある場合: 前のセグメントを円弧の終点まで延長
        - セグメントが 1 つだけの場合: 直線にフォールバック

        削除後は _enforce_g1 で G1 連続性を再保証する。
        """
        if self.min_radius is None:
            return segments

        changed = True
        while changed:
            changed = False
            for i, seg in enumerate(segments):
                if seg.kind != "arc":
                    continue
                if seg.radius >= self.min_radius:
                    continue

                n = len(segments)
                if n == 1:
                    # セグメントが 1 つだけ → 直線にフォールバック
                    segments[0] = LineSegment(p0=seg.p0.copy(), p1=seg.p1.copy())
                    changed = True
                    break

                if i == 0:
                    # 先頭: 次のセグメントを円弧の始点まで延長
                    _apply_segment_endpoints(segments[1], seg.p0, segments[1].p1)
                    segments.pop(0)
                elif i == n - 1:
                    # 末尾: 前のセグメントを円弧の終点まで延長
                    _apply_segment_endpoints(segments[-2], segments[-2].p0, seg.p1)
                    segments.pop()
                else:
                    # 中間: 前後のセグメントを円弧の中点で接続
                    mid = (seg.p0 + seg.p1) / 2.0
                    _apply_segment_endpoints(segments[i - 1], segments[i - 1].p0, mid)
                    _apply_segment_endpoints(segments[i + 1], mid, segments[i + 1].p1)
                    segments.pop(i)

                changed = True
                break  # リストが変わったので再走査

        # G1 連続性を再適用
        if len(segments) > 1:
            segments = self._enforce_g1(segments)

        return segments

    # ------------------------------------------------------------------
    # 種別自動判定
    # ------------------------------------------------------------------
    def _resolve_type(self, chunk: np.ndarray, stype: str, tol: float) -> SegType:
        if stype == "line":
            return "line"

        # 明示的 "arc" または "auto" の結果を候補として取得
        if stype == "arc":
            candidate: SegType = "arc"
        else:  # "auto"
            line_err = self._line_residual(chunk)
            arc_err = self._arc_residual(chunk)
            candidate = "arc" if arc_err < line_err and line_err > tol * 0.1 else "line"

        if candidate == "line":
            return "line"

        # R_max チェック: R > max_radius なら直線に置き換え
        if self.max_radius is not None and len(chunk) >= 3:
            _, _, r = SegmentFitter._fit_circle(chunk)
            if r > self.max_radius:
                return "line"

        return "arc"

    # ------------------------------------------------------------------
    # 直線フィット
    # ------------------------------------------------------------------
    @staticmethod
    def _fit_line(chunk: np.ndarray) -> LineSegment:
        if len(chunk) < 3:
            return LineSegment(p0=chunk[0].copy(), p1=chunk[-1].copy())
        # SVD による最小二乗直線フィット（全点を使用）
        centroid = chunk.mean(axis=0)
        _, _, Vt = np.linalg.svd(chunk - centroid)
        direction = Vt[0]  # 主軸方向（最小二乗直線の方向）
        t0 = np.dot(chunk[0]  - centroid, direction)
        t1 = np.dot(chunk[-1] - centroid, direction)
        p0 = centroid + t0 * direction
        p1 = centroid + t1 * direction
        return LineSegment(p0=p0, p1=p1)

    @staticmethod
    def _line_residual(chunk: np.ndarray) -> float:
        p0, p1 = chunk[0], chunk[-1]
        d = p1 - p0
        norm = np.linalg.norm(d)
        if norm < 1e-10:
            return np.mean(np.linalg.norm(chunk - p0, axis=1))
        d_unit = d / norm
        # 各点の直線からの垂直距離
        vecs = chunk - p0
        proj = vecs @ d_unit
        perp = vecs - np.outer(proj, d_unit)
        return float(np.mean(np.linalg.norm(perp, axis=1)))

    # ------------------------------------------------------------------
    # 円弧フィット（代数的最小二乗法）
    # ------------------------------------------------------------------
    @staticmethod
    def _fit_arc(chunk: np.ndarray) -> ArcSegment:
        cx, cy, r = SegmentFitter._fit_circle(chunk)
        center = np.array([cx, cy])

        angles = np.arctan2(chunk[:, 1] - cy, chunk[:, 0] - cx)
        theta_start = float(angles[0])
        theta_end = float(angles[-1])

        # 反時計回り判定: 角度が増加方向か
        diff = theta_end - theta_start
        if diff < 0:
            diff += 2 * np.pi
        ccw = diff <= np.pi

        return ArcSegment(
            center=center,
            radius=float(r),
            theta_start=theta_start,
            theta_end=theta_end,
            ccw=ccw,
        )

    @staticmethod
    def _fit_circle(pts: np.ndarray) -> tuple[float, float, float]:
        """代数的最小二乗法で円(cx, cy, r)を推定"""
        x, y = pts[:, 0], pts[:, 1]
        A = np.column_stack([x, y, np.ones(len(x))])
        b = x**2 + y**2
        result, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
        cx = result[0] / 2
        cy = result[1] / 2
        r = np.sqrt(result[2] + cx**2 + cy**2)
        return cx, cy, r

    @staticmethod
    def _arc_residual(chunk: np.ndarray) -> float:
        if len(chunk) < 3:
            return float("inf")
        cx, cy, r = SegmentFitter._fit_circle(chunk)
        dists = np.sqrt((chunk[:, 0] - cx)**2 + (chunk[:, 1] - cy)**2)
        return float(np.mean(np.abs(dists - r)))

    # ------------------------------------------------------------------
    # G1連続補正（厳密版: 境界点ごとの接線拘束付き最適化）
    # ------------------------------------------------------------------
    @staticmethod
    def _enforce_g1(
        segments: list[Segment],
        start_constraint: "EndpointConstraint | None" = None,
        end_constraint:   "EndpointConstraint | None" = None,
    ) -> list[Segment]:
        """
        各セグメント境界において G1 連続（接線方向一致）を実現する。

        2 フェーズで処理する:
          Phase 1: 各内部境界について最適境界点 b を求める（Nelder-Mead 最適化）
          Phase 2: 全セグメントを境界点リストに合わせて再構築する
                   (_apply_segment_endpoints による両端同時更新で G0 を保証)

        Phase 1 の目的関数:
          接線外積² + 逆向きペナルティ + 弱い正則化（重み 0.5）

        Phase 2 の再構築:
          直線: p0, p1 を直接セット
          円弧: p0, p1 を通る円（半径は既存値を保持）を垂直二等分線法で求め
                中心・theta_start・theta_end を一括更新

        start_constraint / end_constraint が与えられた場合:
          端点に接線拘束がある直線セグメントについては、境界点の最適化を接線方向
          への 1 次元探索に制限し、Phase 2 後も接線方向が保持されるようにする。
        """
        n = len(segments)
        if n <= 1:
            return segments

        sc = start_constraint
        ec = end_constraint

        # --- Phase 1: 境界点を収集 ---
        boundaries: list[np.ndarray] = [segments[0].p0.copy()]

        for i in range(n - 1):
            curr = segments[i]
            nxt  = segments[i + 1]

            # 初期値: 両端点の中点
            b0    = (curr.p1 + nxt.p0) / 2.0
            scale = max(np.linalg.norm(curr.p1 - curr.p0),
                        np.linalg.norm(nxt.p1 - nxt.p0), 1e-6)

            # 始端拘束: 最初の境界かつ直線セグメントに接線拘束がある場合は 1 次元探索
            if (i == 0 and sc is not None and sc.tangent is not None
                    and curr.kind == "line"):
                p0_fixed = boundaries[0]
                t_dir    = sc.tangent
                init_s   = max(1e-3, float((b0 - p0_fixed) @ t_dir))

                def make_1d_obj_start(nx, s0, p0f, td):
                    def obj(s_arr: np.ndarray) -> float:
                        s     = float(s_arr[0])
                        b     = p0f + td * s
                        t_nxt = _tangent_at_start(nx, b)
                        cross = td[0] * t_nxt[1] - td[1] * t_nxt[0]
                        dot   = float(td @ t_nxt)
                        dir_pen = max(0.0, -dot) * 10.0
                        reg   = ((s - s0) / (s0 + 1e-6)) ** 2 * 0.5
                        return float(cross**2 + dir_pen + reg)
                    return obj

                res   = minimize(
                    make_1d_obj_start(nxt, init_s, p0_fixed, t_dir),
                    [init_s],
                    method="Nelder-Mead",
                    options={"xatol": 1e-6, "fatol": 1e-9, "maxiter": 1000},
                )
                b_opt = p0_fixed + t_dir * float(res.x[0])

            # 終端拘束: 最後の境界かつ直線セグメントに接線拘束がある場合は 1 次元探索
            elif (i == n - 2 and ec is not None and ec.tangent is not None
                    and nxt.kind == "line"):
                # Phase 1 ではまだ boundaries[-1] は未確定のため segments[-1].p1 を使用
                p1_fixed = segments[-1].p1.copy()
                t_dir    = ec.tangent
                # 逆方向: 終端の接線は進行方向なので p1 側から逆向きに探索
                init_s   = max(1e-3, float((p1_fixed - b0) @ t_dir))

                def make_1d_obj_end(c, s0, p1f, td):
                    def obj(s_arr: np.ndarray) -> float:
                        s     = float(s_arr[0])
                        b     = p1f - td * s
                        t_curr = _tangent_at_end(c, b)
                        cross  = t_curr[0] * td[1] - t_curr[1] * td[0]
                        dot    = float(t_curr @ td)
                        dir_pen = max(0.0, -dot) * 10.0
                        reg    = ((s - s0) / (s0 + 1e-6)) ** 2 * 0.5
                        return float(cross**2 + dir_pen + reg)
                    return obj

                res   = minimize(
                    make_1d_obj_end(curr, init_s, p1_fixed, t_dir),
                    [init_s],
                    method="Nelder-Mead",
                    options={"xatol": 1e-6, "fatol": 1e-9, "maxiter": 1000},
                )
                b_opt = p1_fixed - t_dir * float(res.x[0])

            else:
                # 解析的 G1 ソルバー（境界タイプに応じて分岐）
                # 各ソルバーはG1を満たす候補点を返す。接線方向（dot>0）も確認。
                b_opt: np.ndarray | None = None

                def _dot_ok(b: np.ndarray) -> bool:
                    return float(_tangent_at_end(curr, b) @ _tangent_at_start(nxt, b)) > 0.0

                if curr.kind == "line" and nxt.kind == "line":
                    cand = _g1_line_line(curr.p0, nxt.p1, b0)
                    if _dot_ok(cand):
                        b_opt = cand
                elif curr.kind == "arc" and nxt.kind == "arc":
                    cand = _g1_arc_arc(curr.center, nxt.center, b0, curr.ccw, nxt.ccw)
                    b_opt = cand  # 方向考慮済みのため _dot_ok チェック不要
                elif curr.kind == "arc" and nxt.kind == "line":
                    cands = _g1_arc_line(curr.center, curr.radius, nxt.p1, b0)
                    if cands is not None:
                        for cand in cands:
                            if _dot_ok(cand):
                                b_opt = cand
                                break
                elif curr.kind == "line" and nxt.kind == "arc":
                    cands = _g1_line_arc(curr.p0, nxt.center, nxt.radius, b0)
                    if cands is not None:
                        for cand in cands:
                            if _dot_ok(cand):
                                b_opt = cand
                                break

                # 退化ケースのフォールバック（Nelder-Mead）
                if b_opt is None:
                    def make_objective(c, nx, init, sc):
                        def total(b: np.ndarray) -> float:
                            t_curr = _tangent_at_end(c, b)
                            t_nxt  = _tangent_at_start(nx, b)
                            cross  = t_curr[0] * t_nxt[1] - t_curr[1] * t_nxt[0]
                            dot    = float(t_curr @ t_nxt)
                            dir_pen = max(0.0, -dot) * 10.0
                            reg = (np.linalg.norm(b - init) / sc) ** 2 * 0.5
                            return float(cross**2 + dir_pen + reg)
                        return total

                    result = minimize(
                        make_objective(curr, nxt, b0, scale),
                        b0,
                        method="Nelder-Mead",
                        options={"xatol": 1e-6, "fatol": 1e-9, "maxiter": 500},
                    )
                    b_opt = result.x
                    # 縮退ガード（Nelder-Mead フォールバック時のみ）
                    if np.linalg.norm(b_opt - b0) > scale * 1.0:
                        b_opt = b0

            boundaries.append(b_opt)

        boundaries.append(segments[-1].p1.copy())

        # --- Phase 2: 境界点に合わせて各セグメントを再構築 ---
        for i, seg in enumerate(segments):
            _apply_segment_endpoints(seg, boundaries[i], boundaries[i + 1])

        return segments

    # ------------------------------------------------------------------
    # 両端点の拘束適用
    # ------------------------------------------------------------------
    @staticmethod
    def _apply_endpoint_constraints(
        segments: list[Segment],
        pts: np.ndarray,
        sc: "EndpointConstraint",
        ec: "EndpointConstraint",
    ) -> list[Segment]:
        """
        フィット＆G1補正済みセグメント列の両端に拘束を適用する。

        始点 (sc) / 終点 (ec) それぞれについて独立に処理する。

        pin=True   → 端点座標を点群の始端/終端に強制上書き
        tangent    → 端点での接線ベクトルを指定値に固定した微小補正を実施
                     （端点を固定し、隣接セグメントの内部パラメータを調整）

        pin と tangent の組合せは全 4 通り対応。
        """
        if not segments:
            return segments

        first = segments[0]
        last  = segments[-1]

        # ---- 始点 ----
        pin_pt_start = pts[0] if sc.pin else None
        SegmentFitter._apply_one_end(
            seg=first,
            is_start=True,
            pin_pt=pin_pt_start,
            tangent=sc.tangent,
        )

        # ---- 終点 ----
        pin_pt_end = pts[-1] if ec.pin else None
        SegmentFitter._apply_one_end(
            seg=last,
            is_start=False,
            pin_pt=pin_pt_end,
            tangent=ec.tangent,
        )

        return segments

    @staticmethod
    def _apply_one_end(
        seg: Segment,
        is_start: bool,
        pin_pt: "np.ndarray | None",
        tangent: "np.ndarray | None",
    ) -> None:
        """
        セグメントの一端（始端 or 終端）に pin / tangent 拘束を適用する（in-place）。

        pin_pt  : None でなければ端点をこの座標に強制する
        tangent : None でなければ端点での接線をこの方向に合わせる

        処理順序: pin → tangent
          pin を先に適用してから、tangent に合わせてパラメータを微調整する。
          これにより「通過 + 接線指定」の組合せで両拘束が成立する。
        """
        # ---------- STEP 1: pin 拘束 ----------
        if pin_pt is not None:
            _set_start(seg, pin_pt) if is_start else _set_end(seg, pin_pt)

        # ---------- STEP 2: tangent 拘束 ----------
        if tangent is None:
            return

        t_target = np.asarray(tangent, dtype=float)
        t_target /= np.linalg.norm(t_target) + 1e-12

        if is_start:
            # 始端接線を t_target に合わせる
            if seg.kind == "line":
                # 始点を固定し、終点を「始点 + 元の長さ × t_target 方向」に調整
                # ただし pin=True なら p0 は既に固定済み
                length = np.linalg.norm(seg.p1 - seg.p0)
                if pin_pt is not None:
                    seg.p1 = seg.p0 + t_target * length
                else:
                    # pin なし: 始点を少し動かして接線を合わせる
                    # p0 を p1 - length*t_target に設定
                    seg.p0 = seg.p1 - t_target * length
            else:  # arc
                # 始端角度 theta_start を t_target に対応する角度に更新
                # 接線 = [-sin(theta), cos(theta)] (ccw) → theta を逆算
                seg.theta_start = _theta_from_tangent(t_target, seg.ccw)
                # pin 拘束があれば中心も更新して端点が pin_pt を通るようにする
                if pin_pt is not None:
                    _recenter_arc_at_start(seg, pin_pt)
        else:
            # 終端接線を t_target に合わせる
            if seg.kind == "line":
                length = np.linalg.norm(seg.p1 - seg.p0)
                if pin_pt is not None:
                    seg.p0 = seg.p1 - t_target * length
                else:
                    seg.p1 = seg.p0 + t_target * length
            else:
                seg.theta_end = _theta_from_tangent(t_target, seg.ccw)
                if pin_pt is not None:
                    _recenter_arc_at_end(seg, pin_pt)
    def variance_score(self, segments: list[Segment]) -> float:
        """
        全点について「最近接セグメントへの垂線距離²」の平均を返す。

        di = 点 i から最も近いセグメントへの垂線距離
        score = Σdi² / N

        Parameters
        ----------
        segments : G1補正済みセグメントのリスト

        Returns
        -------
        float : Σdi²/N
        """
        if not segments:
            return float("inf")
        pts = self.points
        N   = len(pts)
        sq_dists = np.full(N, np.inf)

        for seg in segments:
            d = _point_to_segment_distances(pts, seg)
            sq_dists = np.minimum(sq_dists, d ** 2)

        return float(np.mean(sq_dists))

    def per_segment_scores(
        self, segments: list[Segment], boundaries: list[int]
    ) -> list[float]:
        """
        各セグメントについて、割り当て点群からの誤差分散 Σdi²/ni を返す。

        アルゴリズム仕様の「δ_j < δ/M チェック」に使用する。

        Parameters
        ----------
        segments   : フィット済みセグメントのリスト
        boundaries : 各セグメントの点群インデックス境界リスト (len = n+1)

        Returns
        -------
        list[float] : 各セグメントの誤差分散
        """
        scores = []
        for i, seg in enumerate(segments):
            chunk = self.points[boundaries[i]: boundaries[i + 1] + 1]
            if len(chunk) == 0:
                scores.append(float("inf"))
                continue
            d = _point_to_segment_distances(chunk, seg)
            scores.append(float(np.mean(d ** 2)))
        return scores

    def composite_score(self, segments: list[Segment], alpha: float = 0.1) -> float:
        """
        セグメント数の少なさを考慮した複合評価値。

        composite = variance_score × (1 + α × n)

        n=1 のとき penalty=0 で variance_score と等しい。
        n が増えるほど penalty が加算され、セグメント数の多い解を抑制する。
        alpha=0 のときは variance_score と完全に一致する。

        Parameters
        ----------
        segments : G1補正済みセグメントのリスト
        alpha    : セグメント数ペナルティ係数（デフォルト 0.1）

        Returns
        -------
        float : variance_score × (1 + alpha × n)
        """
        n   = len(segments)
        vs  = self.variance_score(segments)
        return vs * (1.0 + alpha * n)

    # ------------------------------------------------------------------
    # 残差統計（UI表示用・セグメントごとの旧来のメトリクス）
    # ------------------------------------------------------------------
    def residuals(self, segments: list[Segment]) -> dict:
        """各セグメントの点群からの平均残差を返す"""
        pts = self.points
        N = len(pts)
        n = len(segments)
        if n == 0:
            return {}

        split = np.linspace(0, N - 1, n + 1, dtype=int)
        stats = {}
        for i, seg in enumerate(segments):
            chunk = pts[split[i]: split[i + 1] + 1]
            if seg.kind == "line":
                err = self._line_residual(chunk)
            else:
                cx, cy = seg.center
                dists = np.sqrt((chunk[:, 0] - cx)**2 + (chunk[:, 1] - cy)**2)
                err = float(np.mean(np.abs(dists - seg.radius)))
            stats[i] = {"type": seg.kind, "mean_error": round(err, 6)}
        return stats


# ===========================================================================
# モジュールレベルヘルパー: _enforce_g1 から呼ばれる
# ===========================================================================

def _tangent_at_end(seg: "Segment", b: np.ndarray) -> np.ndarray:
    """
    境界点 b を終点とみなしたときの終端接線ベクトル（単位ベクトル）。
    LineSegment: b が p1 に対応 → p0→b 方向
    ArcSegment : b が円周上の点に対応 → theta を b から計算
    """
    if seg.kind == "line":
        v = b - seg.p0
        norm = np.linalg.norm(v)
        return v / (norm + 1e-12)
    else:
        # theta を b の位置から再計算
        v = b - seg.center
        theta = np.arctan2(v[1], v[0])
        r = np.array([np.cos(theta), np.sin(theta)])
        return np.array([-r[1], r[0]]) if seg.ccw else np.array([r[1], -r[0]])


def _tangent_at_start(seg: "Segment", b: np.ndarray) -> np.ndarray:
    """
    境界点 b を始点とみなしたときの始端接線ベクトル（単位ベクトル）。
    LineSegment: b が p0 に対応 → b→p1 方向
    ArcSegment : b が円周上の点に対応 → theta を b から計算
    """
    if seg.kind == "line":
        v = seg.p1 - b
        norm = np.linalg.norm(v)
        return v / (norm + 1e-12)
    else:
        v = b - seg.center
        theta = np.arctan2(v[1], v[0])
        r = np.array([np.cos(theta), np.sin(theta)])
        return np.array([-r[1], r[0]]) if seg.ccw else np.array([r[1], -r[0]])


def _g1_line_line(p0_curr: np.ndarray, p1_nxt: np.ndarray, b0: np.ndarray) -> np.ndarray:
    """line→line G1: p0_curr, b, p1_nxt が共線 → b0 を直線に射影"""
    d = p1_nxt - p0_curr
    ld = float(np.dot(d, d))
    if ld < 1e-20:
        return b0
    t = np.clip(float(np.dot(b0 - p0_curr, d)) / ld, 0.01, 0.99)
    return p0_curr + t * d


def _g1_arc_arc(
    c_curr: np.ndarray, c_nxt: np.ndarray, b0: np.ndarray,
    ccw_curr: bool, ccw_nxt: bool,
) -> np.ndarray:
    """arc→arc G1: c_curr, b, c_nxt が共線 → b0 を直線に射影（方向考慮）

    接線方向が一致するための条件:
      同方向 (ccw_curr == ccw_nxt): t ∉ (0, 1)  →  t < 0 or t > 1
      逆方向 (ccw_curr != ccw_nxt): t ∈ (0, 1)   →  t に 0.01..0.99 クランプ
    """
    d = c_nxt - c_curr
    ld = float(np.dot(d, d))
    if ld < 1e-20:
        return b0
    t = float(np.dot(b0 - c_curr, d)) / ld
    if ccw_curr != ccw_nxt:
        # 逆方向: t ∈ (0,1) が有効。t > 1 のときだけ失敗するのでクランプ。
        t = min(t, 0.99)
    else:
        # 同方向: t ∉ (0,1) が有効。t ∈ (0,1) のときは外側に押し出す。
        if 0.0 < t < 1.0:
            t = -0.01 if t <= 0.5 else 1.01
    return c_curr + t * d


def _g1_arc_line(
    c_curr: np.ndarray, r_curr: float, p1_nxt: np.ndarray, b0: np.ndarray
) -> list[np.ndarray] | None:
    """arc→line G1: (b−c_curr)⊥(p1_nxt−b) → 両交点リストを返す（b0 近い順）"""
    D_vec = p1_nxt - c_curr
    D = float(np.linalg.norm(D_vec))
    if D < 1e-10 or r_curr > D + 1e-9:
        return None
    a = r_curr ** 2 / D
    h2 = r_curr ** 2 - a ** 2
    if h2 < 0.0:
        return None
    h = float(np.sqrt(max(0.0, h2)))
    u = D_vec / D
    perp = np.array([-u[1], u[0]])
    P = c_curr + a * u
    cands = [P + h * perp, P - h * perp]
    return sorted(cands, key=lambda c: float(np.linalg.norm(c - b0)))


def _g1_line_arc(
    p0_curr: np.ndarray, c_nxt: np.ndarray, r_nxt: float, b0: np.ndarray
) -> list[np.ndarray] | None:
    """line→arc G1: (b−p0_curr)⊥(b−c_nxt) → 両交点リストを返す（b0 近い順）"""
    D_vec = p0_curr - c_nxt
    D = float(np.linalg.norm(D_vec))
    if D < 1e-10 or r_nxt > D + 1e-9:
        return None
    a = r_nxt ** 2 / D
    h2 = r_nxt ** 2 - a ** 2
    if h2 < 0.0:
        return None
    h = float(np.sqrt(max(0.0, h2)))
    u = D_vec / D
    perp = np.array([-u[1], u[0]])
    P = c_nxt + a * u
    cands = [P + h * perp, P - h * perp]
    return sorted(cands, key=lambda c: float(np.linalg.norm(c - b0)))


def _set_end(seg: "Segment", b: np.ndarray) -> None:
    """セグメントの終端を境界点 b に更新する"""
    if seg.kind == "line":
        seg.p1 = b.copy()
    else:
        v = b - seg.center
        seg.theta_end = float(np.arctan2(v[1], v[0]))
        _recenter_arc_at_end(seg, b)


def _set_start(seg: "Segment", b: np.ndarray) -> None:
    """セグメントの始端を境界点 b に更新する"""
    if seg.kind == "line":
        seg.p0 = b.copy()
    else:
        v = b - seg.center
        seg.theta_start = float(np.arctan2(v[1], v[0]))
        _recenter_arc_at_start(seg, b)


def _apply_segment_endpoints(seg: "Segment", p0: np.ndarray, p1: np.ndarray) -> None:
    """
    セグメントの両端点を p0, p1 に合わせて再構築する（G0 保証）。

    直線: p0, p1 を直接更新。
    円弧: p0, p1 を通る円（既存半径を保持）を垂直二等分線法で求め
          center, theta_start, theta_end を一括更新する。
          既存 center に最も近い候補を選ぶことで向き（ccw）を保持する。
    """
    if seg.kind == "line":
        seg.p0 = p0.copy()
        seg.p1 = p1.copy()
    else:
        chord = p1 - p0
        chord_len = float(np.linalg.norm(chord))

        if chord_len < 1e-12:
            return  # 縮退（p0 == p1）: スキップ

        half_chord = chord_len / 2.0
        r = seg.radius

        # 半径が弦の半分より小さい場合は半径を最小限拡大
        if r < half_chord:
            r = half_chord + 1e-9
            seg.radius = r

        # 中点から垂直二等分線方向への距離
        h = float(np.sqrt(r**2 - half_chord**2))
        mid = (p0 + p1) / 2.0
        # chord に垂直な単位ベクトル（2 候補方向）
        perp = np.array([-chord[1], chord[0]]) / chord_len

        c1 = mid + h * perp
        c2 = mid - h * perp

        # 既存 center に近い方を選択（弧の向きを保持）
        if np.linalg.norm(c1 - seg.center) <= np.linalg.norm(c2 - seg.center):
            seg.center = c1
        else:
            seg.center = c2

        seg.theta_start = float(np.arctan2(p0[1] - seg.center[1],
                                            p0[0] - seg.center[0]))
        seg.theta_end   = float(np.arctan2(p1[1] - seg.center[1],
                                            p1[0] - seg.center[0]))


def _point_to_segment_distances(pts: np.ndarray, seg: "Segment") -> np.ndarray:
    """
    点群 pts (N,2) から seg への垂線距離の配列 (N,) を返す。

    LineSegment:
        線分の有限長を考慮したクランプ付き垂線距離。
        線分外の点には端点への距離を使う。

    ArcSegment:
        中心からの距離 - 半径 の絶対値。
        ただし角度範囲外の点には最近端点への距離を使う。
    """
    if seg.kind == "line":
        return _dist_to_line_segment(pts, seg.p0, seg.p1)
    else:
        return _dist_to_arc_segment(pts, seg)


def _dist_to_line_segment(
    pts: np.ndarray, p0: np.ndarray, p1: np.ndarray
) -> np.ndarray:
    """有限線分 p0→p1 への最短距離（クランプ付き）"""
    d  = p1 - p0
    ld = float(np.dot(d, d))
    if ld < 1e-20:
        return np.linalg.norm(pts - p0, axis=1)

    # 各点の線分への射影パラメータ t ∈ [0, 1]
    t = np.clip(((pts - p0) @ d) / ld, 0.0, 1.0)
    proj = p0 + np.outer(t, d)
    return np.linalg.norm(pts - proj, axis=1)


def _dist_to_arc_segment(pts: np.ndarray, seg: "ArcSegment") -> np.ndarray:
    """
    円弧セグメントへの最短距離。
    角度範囲内: |dist_from_center - r|
    角度範囲外: 端点への距離
    """
    cx, cy = seg.center
    r      = seg.radius
    ts, te = seg.theta_start, seg.theta_end

    # 各点の中心からの角度
    dx = pts[:, 0] - cx
    dy = pts[:, 1] - cy
    angles = np.arctan2(dy, dx)

    # 角度が円弧範囲内かを判定
    in_arc = _angle_in_arc(angles, ts, te, seg.ccw)

    # 中心距離ベースの距離
    dist_from_center = np.sqrt(dx**2 + dy**2)
    d_arc = np.abs(dist_from_center - r)

    # 端点への距離
    d_p0 = np.linalg.norm(pts - seg.p0, axis=1)
    d_p1 = np.linalg.norm(pts - seg.p1, axis=1)
    d_endpoint = np.minimum(d_p0, d_p1)

    return np.where(in_arc, d_arc, d_endpoint)


def _angle_in_arc(
    angles: np.ndarray, ts: float, te: float, ccw: bool
) -> np.ndarray:
    """angles (rad配列) が円弧範囲 [ts, te] (ccw/cw) 内かを返す bool 配列"""
    if ccw:
        span = te - ts
        if span < 0:
            span += 2 * np.pi
        delta = angles - ts
        delta = delta % (2 * np.pi)
        return delta <= span
    else:
        span = ts - te
        if span < 0:
            span += 2 * np.pi
        delta = ts - angles
        delta = delta % (2 * np.pi)
        return delta <= span


def _theta_from_tangent(tangent: np.ndarray, ccw: bool) -> float:
    """
    接線ベクトルから円弧の角度 theta を逆算する。

    CCW 円弧の接線: t = [-sin(theta), cos(theta)]
    CW  円弧の接線: t = [ sin(theta), -cos(theta)]

    CCW: sin(theta) = -tx, cos(theta) = ty  → theta = atan2(-tx, ty)
    CW : sin(theta) =  tx, cos(theta) = -ty → theta = atan2(tx, -ty)
    """
    tx, ty = float(tangent[0]), float(tangent[1])
    if ccw:
        return float(np.arctan2(-tx, ty))
    else:
        return float(np.arctan2(tx, -ty))


def _recenter_arc_at_start(seg: "ArcSegment", pin_pt: np.ndarray) -> None:
    """
    始端点が pin_pt を通るよう、中心を theta_start の方向を保ったまま移動する。
    center = pin_pt - r * [cos(theta_start), sin(theta_start)]
    """
    r = seg.radius
    direction = np.array([np.cos(seg.theta_start), np.sin(seg.theta_start)])
    seg.center = pin_pt - r * direction


def _recenter_arc_at_end(seg: "ArcSegment", pin_pt: np.ndarray) -> None:
    """
    終端点が pin_pt を通るよう、中心を theta_end の方向を保ったまま移動する。
    center = pin_pt - r * [cos(theta_end), sin(theta_end)]
    """
    r = seg.radius
    direction = np.array([np.cos(seg.theta_end), np.sin(seg.theta_end)])
    seg.center = pin_pt - r * direction
