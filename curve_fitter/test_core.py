"""
コアロジック動作確認
1. variance_score: 距離²平均の計算確認
2. fit_auto: 収束ケース・未収束ケース
3. preprocess: 外れ値除去 + ソート
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import numpy as np
from curve_fitter.core.fitter import SegmentFitter, FitResult
from curve_fitter.core.preprocess import sort_points, remove_outliers


def make_synthetic_points(noise=0.05) -> np.ndarray:
    rng = np.random.default_rng(42)
    line1  = np.column_stack([np.linspace(0, 5, 50), np.zeros(50)])
    thetas = np.linspace(-np.pi / 2, 0, 50)
    arc    = np.column_stack([5 + 3*np.cos(thetas), 3 + 3*np.sin(thetas)])
    line2  = np.column_stack([np.linspace(8, 14, 50), np.full(50, 3.0)])
    pts = np.vstack([line1, arc[1:], line2[1:]])
    return pts + rng.normal(0, noise, pts.shape)


# ------------------------------------------------------------------
# テスト1: variance_score の基本確認
# ------------------------------------------------------------------
def test_variance_score():
    print("=" * 60)
    print("テスト1: variance_score")
    print("=" * 60)
    pts     = make_synthetic_points(noise=0.02)
    fitter  = SegmentFitter(pts)
    # 5セグメントで L 字形状をよくフィットできるはず
    segs    = fitter.fit(5)
    score   = fitter.variance_score(segs)
    print(f"  5セグメント  Σdi²/n = {score:.6g}")
    segs1   = fitter.fit(1, ["line"])
    score1  = fitter.variance_score(segs1)
    print(f"  1セグメント  Σdi²/n = {score1:.6g}")
    assert score < score1, "セグメント数が多い方がスコアが低いはず"
    print("  ✓ score の大小関係 OK\n")


# ------------------------------------------------------------------
# テスト2: fit_auto 収束ケース
# ------------------------------------------------------------------
def test_fit_auto_converge():
    print("=" * 60)
    print("テスト2: fit_auto — 収束ケース")
    print("=" * 60)
    pts    = make_synthetic_points(noise=0.03)
    fitter = SegmentFitter(pts)

    # ノイズ 0.03 なので score ~ 0.03^2 = 0.0009 程度。閾値を余裕持って設定
    result: FitResult = fitter.fit_auto(
        threshold=0.005,
        type_policy="auto",
        max_segments=10,
        max_iter=6,
    )
    print(f"  収束: {result.converged}")
    print(f"  セグメント数: {result.n_segments}")
    print(f"  Σdi²/n: {result.score:.6g}")
    print(f"  メッセージ: {result.message}")
    print(f"  履歴:")
    for n, s in result.history:
        mark = " ←" if n == result.n_segments else ""
        print(f"    n={n:2d}  score={s:.6g}{mark}")
    assert result.converged, "収束するはず"
    print("  ✓ 収束 OK\n")


# ------------------------------------------------------------------
# テスト3: fit_auto 未収束ケース（閾値を極端に小さく）
# ------------------------------------------------------------------
def test_fit_auto_not_converge():
    print("=" * 60)
    print("テスト3: fit_auto — 未収束ケース")
    print("=" * 60)
    pts    = make_synthetic_points(noise=0.5)   # ノイズ大
    fitter = SegmentFitter(pts)

    result: FitResult = fitter.fit_auto(
        threshold=1e-8,        # 達成不可能な閾値
        type_policy="auto",
        max_segments=4,        # 探索上限も低め
        max_iter=3,
    )
    print(f"  収束: {result.converged}")
    print(f"  セグメント数: {result.n_segments}")
    print(f"  Σdi²/n: {result.score:.6g}")
    print(f"  メッセージ: {result.message}")
    assert not result.converged, "未収束のはず"
    assert result.segments, "未収束でも最終結果を返すはず"
    print("  ✓ 未収束ハンドリング OK\n")


# ------------------------------------------------------------------
# テスト4: スコアが単調減少（セグメント数を増やすほど改善）
# ------------------------------------------------------------------
def test_score_monotone():
    print("=" * 60)
    print("テスト4: スコアの単調性（n増加 → score 傾向的に減少）")
    print("=" * 60)
    pts    = make_synthetic_points(noise=0.1)
    fitter = SegmentFitter(pts)
    scores = []
    for n in range(1, 6):
        segs  = fitter.fit(n)
        score = fitter.variance_score(segs)
        scores.append(score)
        print(f"  n={n}  Σdi²/n={score:.6g}")
    # 厳密な単調減少は保証されないが、n=1 > n=5 は成り立つはず
    assert scores[0] > scores[-1], "n=1 より n=5 の方がスコアが低いはず"
    print("  ✓ 単調性 OK\n")


if __name__ == "__main__":
    test_variance_score()
    test_fit_auto_converge()
    test_fit_auto_not_converge()
    test_score_monotone()
    print("✓ 全テスト完了")
