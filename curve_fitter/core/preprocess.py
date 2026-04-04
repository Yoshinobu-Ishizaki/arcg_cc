"""
点群前処理: 散乱した点群を近傍探索でソートし、曲線に沿った順序に整列する

アルゴリズム:
    1. 最近傍貪欲法（Greedy Nearest Neighbor）で点列を一筆書き順に並べる
    2. 始点は「端点らしい点」（近傍が片側にしかない点）から選ぶ
    3. 必要に応じて外れ値除去（近傍距離が中央値の k 倍を超える点を除外）も行う

使い方:
    from curve_fitter.core.preprocess import sort_points, remove_outliers

    pts_clean = remove_outliers(pts, k=5.0)
    pts_sorted = sort_points(pts_clean)
"""
from __future__ import annotations
import numpy as np
from scipy.spatial import KDTree


def sort_points(
    points: np.ndarray,
    start_idx: int | None = None,
) -> np.ndarray:
    """
    散乱点群を近傍探索でソートし、曲線に沿った順序の配列を返す。

    Parameters
    ----------
    points    : shape (N, 2) の点群
    start_idx : 始点のインデックス。None の場合は「端点らしい点」を自動選択

    Returns
    -------
    ソート済み点群 shape (N, 2)
    """
    pts = np.asarray(points, dtype=float)
    N = len(pts)
    if N <= 2:
        return pts.copy()

    tree = KDTree(pts)

    if start_idx is None:
        start_idx = _find_endpoint(pts, tree)

    visited = np.zeros(N, dtype=bool)
    order = np.empty(N, dtype=int)
    order[0] = start_idx
    visited[start_idx] = True

    for step in range(1, N):
        prev = order[step - 1]
        # 未訪問点の中から最近傍を探す
        # k=N は大きすぎるので段階的に増やす
        k = min(N, 8)
        while True:
            dists, idxs = tree.query(pts[prev], k=k)
            # スカラー対策（k=1 のとき）
            if np.ndim(dists) == 0:
                dists = np.array([dists])
                idxs = np.array([idxs])
            found = False
            for idx in idxs:
                if not visited[idx]:
                    order[step] = idx
                    visited[idx] = True
                    found = True
                    break
            if found:
                break
            if k >= N:
                # 残り全点を強制的に追加（孤立点対策）
                remaining = np.where(~visited)[0]
                order[step:] = remaining
                return pts[order]
            k = min(k * 2, N)

    return pts[order]


def remove_outliers(
    points: np.ndarray,
    k: float = 5.0,
    n_neighbors: int = 3,
) -> np.ndarray:
    """
    近傍距離が中央値の k 倍を超える点を外れ値として除去する。

    Parameters
    ----------
    points      : shape (N, 2) の点群
    k           : 外れ値判定の倍率（大きいほど寛容）
    n_neighbors : 近傍距離の計算に使う近傍数

    Returns
    -------
    外れ値を除いた点群 shape (M, 2)
    """
    pts = np.asarray(points, dtype=float)
    N = len(pts)
    if N <= n_neighbors + 1:
        return pts.copy()

    tree = KDTree(pts)
    # 自分自身を除いた n_neighbors 近傍の平均距離
    dists, _ = tree.query(pts, k=n_neighbors + 1)
    mean_nn_dist = dists[:, 1:].mean(axis=1)  # 自分(距離0)を除く

    median_d = np.median(mean_nn_dist)
    threshold = k * median_d

    mask = mean_nn_dist <= threshold
    removed = int(np.sum(~mask))
    if removed > 0:
        print(f"[preprocess] 外れ値除去: {removed} 点 (閾値={threshold:.4f})")

    return pts[mask]


def remove_duplicates(
    points: np.ndarray,
    min_dist: float = 0.1,
) -> np.ndarray:
    """
    ソート済み点列において、隣り合う点間の距離が min_dist 以下の点を削除する。

    先頭から順に走査し、直前の採用点との距離が min_dist 以下なら
    その点を同一点とみなしてスキップする（先頭側を残す）。

    Parameters
    ----------
    points   : shape (N, 2) の点群（ソート済みを想定）
    min_dist : 同一点判定の距離閾値（デフォルト 0.1）

    Returns
    -------
    重複除去後の点群 shape (M, 2)

    Notes
    -----
    - ソート前の散乱点群に適用すると意図しない点が削除される場合がある。
      sort_points() でソートしてから呼ぶことを推奨。
    - remove_outliers() との推奨順序:
        remove_outliers → sort_points → remove_duplicates
    """
    pts = np.asarray(points, dtype=float)
    N = len(pts)
    if N <= 1:
        return pts.copy()

    keep = np.ones(N, dtype=bool)
    last_kept = 0  # 直前に採用した点のインデックス

    for i in range(1, N):
        d = float(np.linalg.norm(pts[i] - pts[last_kept]))
        if d <= min_dist:
            keep[i] = False          # 近すぎるので削除
        else:
            last_kept = i            # 採用して基準を更新

    removed = int(np.sum(~keep))
    if removed > 0:
        print(f"[preprocess] 重複除去: {removed} 点 (min_dist={min_dist})")

    return pts[keep]


def estimate_curve_length(points: np.ndarray) -> float:
    """ソート済み点群の折れ線長を返す（セグメント長の目安に使用）"""
    pts = np.asarray(points, dtype=float)
    if len(pts) < 2:
        return 0.0
    diffs = np.diff(pts, axis=0)
    return float(np.sum(np.linalg.norm(diffs, axis=1)))


# ------------------------------------------------------------------
# 内部ユーティリティ
# ------------------------------------------------------------------

def _find_endpoint(pts: np.ndarray, tree: KDTree) -> int:
    """
    「端点らしい点」を返す。

    近傍点が空間的に片側に偏っている点 = 端点と判定する。
    具体的には: 最近傍 k 点の重心ベクトルのノルムが大きい点。
    両端の候補のうち、x 座標が最小の点を始点とする（一貫性のため）。
    """
    N = len(pts)
    k = min(6, N - 1)
    dists, idxs = tree.query(pts, k=k + 1)  # 自分込み

    # 各点から近傍重心へのベクトルのノルム（端点ほど大きい）
    scores = np.zeros(N)
    for i in range(N):
        neighbors = pts[idxs[i, 1:]]  # 自分を除く
        centroid = neighbors.mean(axis=0)
        scores[i] = np.linalg.norm(pts[i] - centroid)

    # スコア上位 10% を候補として x 最小を選ぶ（再現性のため）
    top_n = max(1, N // 10)
    candidates = np.argsort(scores)[-top_n:]
    best = candidates[np.argmin(pts[candidates, 0])]
    return int(best)
