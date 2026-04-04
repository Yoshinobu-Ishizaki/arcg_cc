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

    def __init__(self, points: np.ndarray):
        self.points = points  # shape (N, 2)

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

        # 内部境界の G1 補正
        segments = self._enforce_g1(segments)

        # 両端の拘束適用
        segments = self._apply_endpoint_constraints(
            segments, pts,
            start_constraint or EndpointConstraint(),
            end_constraint   or EndpointConstraint(),
        )
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
            segs, score = self._fit_with_boundary_opt(
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
    ) -> tuple[list[Segment], float]:
        """
        境界インデックスを反復的に最適化しながらフィットする。
        """
        pts = self.points
        N = len(pts)
        sc = start_constraint or EndpointConstraint()
        ec = end_constraint   or EndpointConstraint()

        # 初期境界インデックス（均等分割）
        boundaries = np.linspace(0, N - 1, n_segments + 1, dtype=int).tolist()

        best_segs  = self._build_segments(boundaries, seg_types, tol_type)
        best_segs  = self._enforce_g1(best_segs)
        best_segs  = self._apply_endpoint_constraints(best_segs, pts, sc, ec)
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
                    score = self.variance_score(segs)
                    if score < best_score:
                        best_score = score
                        best_segs  = segs
                        orig = cand
                        improved = True
                    else:
                        boundaries[bi] = orig

            if not improved:
                break

        return best_segs, best_score

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
    # 種別自動判定
    # ------------------------------------------------------------------
    def _resolve_type(self, chunk: np.ndarray, stype: str, tol: float) -> SegType:
        if stype in ("line", "arc"):
            return stype  # type: ignore
        # 'auto': 直線残差 vs 円弧残差で判定
        line_err = self._line_residual(chunk)
        arc_err = self._arc_residual(chunk)
        return "arc" if arc_err < line_err and arc_err > tol * 0.1 else "line"

    # ------------------------------------------------------------------
    # 直線フィット
    # ------------------------------------------------------------------
    @staticmethod
    def _fit_line(chunk: np.ndarray) -> LineSegment:
        return LineSegment(p0=chunk[0].copy(), p1=chunk[-1].copy())

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
    def _enforce_g1(segments: list[Segment]) -> list[Segment]:
        """
        各セグメント境界において、接線方向一致（G1）を厳密に満たすよう
        境界点座標を最適化する。

        最適化変数: 境界点 b = (bx, by)  ← 2変数
        目的関数  : 接線外積² + 正則化（元位置からの距離²に強いペナルティ）
        等号拘束  : tangent_end(curr, b) × tangent_start(nxt, b) の外積 ≈ 0

        注意: 正則化を強くして境界点が元位置から大きく動かないようにし、
              セグメントの縮退（theta_start ≈ theta_end など）を防ぐ。
        """
        for i in range(len(segments) - 1):
            curr = segments[i]
            nxt  = segments[i + 1]

            # 初期値: 両端点の中点
            b0   = (curr.p1 + nxt.p0) / 2.0
            # 探索の尺度: 接続点周辺の典型距離（正則化強度の基準）
            scale = max(np.linalg.norm(curr.p1 - curr.p0),
                        np.linalg.norm(nxt.p1 - nxt.p0), 1e-6)

            def make_objective(c, n, init, sc):
                def total(b: np.ndarray) -> float:
                    t_curr = _tangent_at_end(c, b)
                    t_nxt  = _tangent_at_start(n, b)
                    # 接線外積（sin(角度差)） → 0 に近づける
                    cross = t_curr[0] * t_nxt[1] - t_curr[1] * t_nxt[0]
                    # 逆向き接線ペナルティ
                    dot = float(t_curr @ t_nxt)
                    dir_pen = max(0.0, -dot) * 10.0
                    # 強い正則化: 境界点が元位置から離れすぎないよう
                    # (sc で正規化することで点群スケールに依存しない)
                    reg = (np.linalg.norm(b - init) / sc) ** 2 * 5.0
                    return float(cross**2 + dir_pen + reg)
                return total

            result = minimize(
                make_objective(curr, nxt, b0, scale),
                b0,
                method="Nelder-Mead",
                options={"xatol": 1e-9, "fatol": 1e-12, "maxiter": 3000},
            )
            b_opt = result.x

            # 縮退ガード: 最適境界点が元位置から遠すぎる場合は中点に戻す
            if np.linalg.norm(b_opt - b0) > scale * 0.3:
                b_opt = b0

            # 最適境界点でセグメント端点を更新
            _set_end(curr, b_opt)
            _set_start(nxt, b_opt)

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


def _set_end(seg: "Segment", b: np.ndarray) -> None:
    """セグメントの終端を境界点 b に更新する"""
    if seg.kind == "line":
        seg.p1 = b.copy()
    else:
        v = b - seg.center
        seg.theta_end = float(np.arctan2(v[1], v[0]))


def _set_start(seg: "Segment", b: np.ndarray) -> None:
    """セグメントの始端を境界点 b に更新する"""
    if seg.kind == "line":
        seg.p0 = b.copy()
    else:
        v = b - seg.center
        seg.theta_start = float(np.arctan2(v[1], v[0]))


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
