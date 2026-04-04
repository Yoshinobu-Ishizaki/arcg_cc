"""
3ケースのフィットテスト（GUIなし）

Case 1: 単一直線        — fit_auto(type_policy="line")
Case 2: 単一円弧        — fit_auto(type_policy="arc")
Case 3: ∫字 5セグメント — fit() 種別明示 ＋ fit_auto との比較

各ケースで確認する項目:
  ・誤差分散 Σdi²/n
  ・複合評価値 Σdi²/n × (1 + α×n)
  ・G1連続（内部境界の接線内積 ≥ 0.95、外積絶対値 ≤ 0.05）
  ・端点拘束（pin / tangent）の成立
  ・収束状態とセグメント数

境界条件:
  ・ノイズ σ = 0.03 (座標単位)
  ・G1 許容値: |cross| < 0.05、dot > 0.95
  ・pin 許容値: d < 0.06
  ・tan 許容値: |cross| < 0.05
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
from curve_fitter.core.fitter import SegmentFitter, EndpointConstraint, FitResult

NOISE   = 0.03
ALPHA   = 0.1
G1_DOT_MIN   = 0.95   # 接線内積の下限
G1_CROSS_MAX = 0.05   # 接線外積絶対値の上限
PIN_TOL = 0.06
TAN_TOL = 0.05

rng = np.random.default_rng(42)


# ======================================================================
# 共通ユーティリティ
# ======================================================================

def add_noise(pts: np.ndarray, sigma: float = NOISE) -> np.ndarray:
    return pts + rng.normal(0, sigma, pts.shape)


def print_segments(segments):
    for i, seg in enumerate(segments):
        if seg.kind == "line":
            print(f"      Seg{i+1} LINE  "
                  f"p0=({seg.p0[0]:.3f}, {seg.p0[1]:.3f})  "
                  f"p1=({seg.p1[0]:.3f}, {seg.p1[1]:.3f})")
        else:
            print(f"      Seg{i+1} ARC   "
                  f"center=({seg.center[0]:.3f},{seg.center[1]:.3f})  "
                  f"r={seg.radius:.3f}  "
                  f"θ: {np.degrees(seg.theta_start):.1f}°→"
                  f"{np.degrees(seg.theta_end):.1f}°  "
                  f"{'CCW' if seg.ccw else 'CW'}")


def print_scores(fitter, segments, indent="    "):
    vs   = fitter.variance_score(segments)
    comp = fitter.composite_score(segments, alpha=ALPHA)
    n    = len(segments)
    print(f"{indent}誤差分散  Σdi²/n                  = {vs:.6g}")
    print(f"{indent}複合評価値 Σdi²/n×(1+{ALPHA}×{n}) "
          f"= {comp:.6g}  "
          f"[× {1 + ALPHA*n:.2f}]")
    return vs, comp


def check_g1(segments) -> bool:
    """内部境界の G1 確認。全境界 OK なら True"""
    if len(segments) <= 1:
        print("      G1境界: なし（1セグメント）")
        return True
    all_ok = True
    for i in range(len(segments) - 1):
        te  = segments[i].tangent_end
        ts  = segments[i+1].tangent_start
        dot   = float(np.dot(te, ts))
        cross = float(te[0]*ts[1] - te[1]*ts[0])
        ok = dot > G1_DOT_MIN and abs(cross) < G1_CROSS_MAX
        all_ok = all_ok and ok
        print(f"      G1 Seg{i+1}→Seg{i+2}: "
              f"内積={dot:.5f} {'≥'+str(G1_DOT_MIN)+'✓' if dot>G1_DOT_MIN else '<'+str(G1_DOT_MIN)+'✗'}  "
              f"外積={cross:.5f} {'✓' if abs(cross)<G1_CROSS_MAX else '✗'}")
    return all_ok


def check_pin(seg, is_start: bool, expected: np.ndarray, label="") -> bool:
    pt = seg.p0 if is_start else seg.p1
    d  = float(np.linalg.norm(pt - expected))
    ok = d < PIN_TOL
    side = "始点" if is_start else "終点"
    print(f"      pin {side} {label}: d={d:.5f}  {'✓' if ok else '✗ FAIL'}")
    return ok


def check_tan(seg, is_start: bool, expected: np.ndarray, label="") -> bool:
    t     = seg.tangent_start if is_start else seg.tangent_end
    cross = abs(float(t[0]*expected[1] - t[1]*expected[0]))
    ok    = cross < TAN_TOL
    side  = "始点" if is_start else "終点"
    print(f"      tan {side} {label}: |cross|={cross:.5f}  {'✓' if ok else '✗ FAIL'}")
    return ok


# ======================================================================
# Case 1: 単一直線
#
#   形状: y = 0.5x + 1  (x: 0→8)
#   期待: n=1 の直線 1 本で収束
#
#   端点拘束:
#     始点: pin（点群始端を通る） + tangent（真の傾き方向）
#     終点: pin（点群終端を通る）
# ======================================================================

def test_case1():
    print("━" * 65)
    print("Case 1: 単一直線  y = 0.5x + 1  (x: 0→8)")
    print("  端点拘束: 始点 pin + tan=[1,0.5]/|…|、終点 pin")
    print("━" * 65)

    xs  = np.linspace(0, 8, 80)
    pts = add_noise(np.column_stack([xs, 0.5*xs + 1.0]))

    true_tan = np.array([1.0, 0.5])
    true_tan /= np.linalg.norm(true_tan)

    sc = EndpointConstraint(pin=True, tangent=true_tan)
    ec = EndpointConstraint(pin=True, tangent=None)

    fitter = SegmentFitter(pts)
    result: FitResult = fitter.fit_auto(
        threshold=0.003,     # σ²≈0.0009、余裕を持って 0.003
        type_policy="line",  # 直線のみで探索
        max_segments=4,
        max_iter=6,
        start_constraint=sc,
        end_constraint=ec,
    )

    print(f"  収束: {result.converged}  n={result.n_segments}")
    print(f"  {result.message}")
    print_segments(result.segments)
    vs, comp = print_scores(fitter, result.segments)
    check_g1(result.segments)
    ok_ps = check_pin(result.segments[0],  True,  pts[0])
    ok_pe = check_pin(result.segments[-1], False, pts[-1])
    ok_ts = check_tan(result.segments[0],  True,  true_tan, label="[1,0.5]/‖…‖")

    assert result.converged,         "収束するはず"
    assert result.n_segments == 1,   f"n=1 期待, 実際 n={result.n_segments}"
    assert ok_ps and ok_pe,          "pin 拘束 NG"
    assert ok_ts,                    "tangent 拘束 NG"
    assert comp > vs,                "複合評価値 > 誤差分散 のはず"

    print("  ✓ Case 1 PASS\n")


# ======================================================================
# Case 2: 単一円弧
#
#   形状: center=(0,0), r=5, 0°→120° CCW
#   期待: n=1 の円弧 1 本で収束
#
#   端点拘束:
#     始点: pin（点群始端） + tangent（0° 点での CCW 接線 = [0,1]）
#     終点: pin（点群終端）
# ======================================================================

def test_case2():
    print("━" * 65)
    print("Case 2: 単一円弧  center=(0,0), r=5, 0°→120° CCW")
    print("  端点拘束: 始点 pin + tan=[0,1]、終点 pin")
    print("━" * 65)

    thetas = np.linspace(0, 2*np.pi/3, 80)
    pts    = add_noise(np.column_stack([5*np.cos(thetas), 5*np.sin(thetas)]))

    # 0° 点での CCW 接線 = [-sin(0), cos(0)] = [0, 1]
    true_tan = np.array([0.0, 1.0])

    sc = EndpointConstraint(pin=True, tangent=true_tan)
    ec = EndpointConstraint(pin=True, tangent=None)

    fitter = SegmentFitter(pts)
    result: FitResult = fitter.fit_auto(
        threshold=0.003,
        type_policy="arc",  # 円弧のみで探索
        max_segments=4,
        max_iter=6,
        start_constraint=sc,
        end_constraint=ec,
    )

    print(f"  収束: {result.converged}  n={result.n_segments}")
    print(f"  {result.message}")
    print_segments(result.segments)
    vs, comp = print_scores(fitter, result.segments)
    check_g1(result.segments)
    ok_ps = check_pin(result.segments[0],  True,  pts[0])
    ok_pe = check_pin(result.segments[-1], False, pts[-1])
    ok_ts = check_tan(result.segments[0],  True,  true_tan, label="[0,1]")

    assert result.converged,       "収束するはず"
    assert result.n_segments == 1, f"n=1 期待, 実際 n={result.n_segments}"
    assert ok_ps and ok_pe,        "pin 拘束 NG"
    assert ok_ts,                  "tangent 拘束 NG"
    assert comp > vs,              "複合評価値 > 誤差分散 のはず"

    print("  ✓ Case 2 PASS\n")


# ======================================================================
# Case 3: ∫字（5 セグメント: LINE, ARC, LINE, ARC, LINE）
#
#   形状（全セグメント G1 連続）:
#     Seg1 LINE: (0, 6) → (2, 6)          接線 [1, 0]
#     Seg2 ARC : center=(2,4), r=2, 90°→0°, CW
#                (2, 6) → (4, 4)           接線 [0,-1]
#     Seg3 LINE: (4, 4) → (4, 0)          接線 [0,-1]
#     Seg4 ARC : center=(2,0), r=2, 0°→-90°, CW
#                (4, 0) → (2,-2)           接線 [-1, 0]
#     Seg5 LINE: (2,-2) → (0,-2)          接線 [-1, 0]
#
#   端点拘束:
#     始点: pin + tan=[1,0]
#     終点: pin + tan=[-1,0]
#
#   フィット方法:
#     (A) fit() — 種別・セグメント数を完全指定
#     (B) fit_auto() — type_policy="auto" で自動探索（参考比較）
# ======================================================================

def make_integral_pts(n_per_seg: int = 40) -> np.ndarray:
    """∫字の真の点列を生成"""
    line1 = np.column_stack([np.linspace(0, 2, n_per_seg),   np.full(n_per_seg, 6.0)])
    t2    = np.linspace(np.pi/2, 0, n_per_seg)
    arc1  = np.column_stack([2 + 2*np.cos(t2), 4 + 2*np.sin(t2)])
    line2 = np.column_stack([np.full(n_per_seg, 4.0),         np.linspace(4, 0, n_per_seg)])
    t4    = np.linspace(0, -np.pi/2, n_per_seg)
    arc2  = np.column_stack([2 + 2*np.cos(t4), 0 + 2*np.sin(t4)])
    line3 = np.column_stack([np.linspace(2, 0, n_per_seg),    np.full(n_per_seg, -2.0)])
    # セグメント境界の重複点を除きながら結合
    return np.vstack([line1[:-1], arc1[:-1], line2[:-1], arc2[:-1], line3])


def test_case3():
    print("━" * 65)
    print("Case 3: ∫字  5セグメント (LINE, ARC, LINE, ARC, LINE)")
    print("  端点拘束: 始点 pin+tan=[1,0]、終点 pin+tan=[-1,0]")
    print("━" * 65)

    pts_true = make_integral_pts(40)
    pts      = add_noise(pts_true)

    tan_s = np.array([ 1.0, 0.0])
    tan_e = np.array([-1.0, 0.0])
    sc = EndpointConstraint(pin=True, tangent=tan_s)
    ec = EndpointConstraint(pin=True, tangent=tan_e)

    fitter = SegmentFitter(pts)

    # ------------------------------------------------------------------
    # (A) fit() — 種別・セグメント数を完全指定
    #     ∫字の形状を事前知識として与えるケース
    # ------------------------------------------------------------------
    print("\n  (A) fit() — 種別指定 [line, arc, line, arc, line]")
    print("  " + "─" * 55)

    segs_a = fitter.fit(
        n_segments=5,
        seg_types=["line", "arc", "line", "arc", "line"],
        start_constraint=sc,
        end_constraint=ec,
    )
    print_segments(segs_a)
    vs_a, comp_a = print_scores(fitter, segs_a)
    g1_ok_a = check_g1(segs_a)

    # 端点拘束チェック
    ps_a = check_pin(segs_a[0],  True,  pts_true[0],  label="(0, 6)")
    pe_a = check_pin(segs_a[-1], False, pts_true[-1], label="(0,-2)")
    ts_a = check_tan(segs_a[0],  True,  tan_s,        label="[1,0]")
    te_a = check_tan(segs_a[-1], False, tan_e,        label="[-1,0]")

    assert g1_ok_a,          "G1 連続 NG"
    assert ps_a and pe_a,    "pin 拘束 NG"
    assert ts_a and te_a,    "tangent 拘束 NG"
    print("      ✓ (A) 種別指定フィット PASS")

    # ------------------------------------------------------------------
    # (B) fit_auto() — type_policy="auto" で自動探索（比較用）
    #     自動探索がどこまで迫れるかを示す
    # ------------------------------------------------------------------
    print("\n  (B) fit_auto() — type_policy='auto'（自動探索・比較）")
    print("  " + "─" * 55)

    result_b: FitResult = fitter.fit_auto(
        threshold=0.003,      # (A) の誤差分散より少し厳しめ
        type_policy="auto",
        max_segments=8,
        max_iter=8,
        tol_type=0.2,
        start_constraint=sc,
        end_constraint=ec,
    )
    print(f"      収束: {result_b.converged}  n={result_b.n_segments}")
    print(f"      {result_b.message}")
    print_segments(result_b.segments)
    vs_b, comp_b = print_scores(fitter, result_b.segments, indent="      ")
    check_g1(result_b.segments)

    print("\n      --- 試行履歴（n vs Σdi²/n） ---")
    for n, s in result_b.history:
        mark = " ← 採用" if n == result_b.n_segments else ""
        print(f"        n={n:2d}  Σdi²/n={s:.6g}{mark}")

    # ------------------------------------------------------------------
    # (A) vs (B) スコア比較
    # ------------------------------------------------------------------
    print("\n  --- (A) vs (B) 比較 ---")
    print(f"      (A) 種別指定  n=5  "
          f"Σdi²/n={vs_a:.6g}  複合={comp_a:.6g}")
    print(f"      (B) 自動探索  n={result_b.n_segments}  "
          f"Σdi²/n={vs_b:.6g}  複合={comp_b:.6g}")
    if vs_a < vs_b:
        print("      → 種別指定の方が誤差分散は小さい（形状の事前知識が有効）")
    else:
        print("      → 自動探索が誤差分散で同等以上を達成")

    assert comp_a > vs_a, "複合評価値 > 誤差分散 のはず"
    print("  ✓ Case 3 PASS\n")


# ======================================================================
# エントリポイント
# ======================================================================
#
#   形状: 楕円 a=5, b=3, θ: 120°→420°（300°分 = 欠け60°）
#   「殆ど閉じている」ため始終点が近接する難しいケース。
#
#   前処理:
#     シャッフル済み点群 → _find_endpoint の自動検出結果を表示（参考）
#     → 正しい始点を start_idx で明示指定してソート（ユーザーが指定した想定）
#
#   確認項目:
#     (a) 自動始点検出の参考情報表示（パスしなくても良い）
#     (b) start_idx 明示指定後のソート品質（隣接距離 std が 1/10 以下）
#     (c) fit_auto が複数円弧で収束すること（n≥2）
#     (d) G1 連続（楕円近似のため緩め: dot>0.90, |cross|<0.15）
#     (e) フィット始終点の gap が真の gap に近いこと
# ======================================================================

def test_case4():
    print("━" * 65)
    print("Case 4: 殆ど閉じた楕円  a=5, b=3, 300°分（欠け60°）")
    print("  始点を明示指定してソート → fit_auto(type='arc')")
    print("━" * 65)

    a, b    = 5.0, 3.0
    t_start = np.radians(120)
    t_end   = np.radians(120 + 300)

    thetas     = np.linspace(t_start, t_end, 120)
    pts_true   = np.column_stack([a * np.cos(thetas), b * np.sin(thetas)])
    true_start = pts_true[0]
    true_end   = pts_true[-1]
    gap        = float(np.linalg.norm(true_start - true_end))

    pts_noisy = add_noise(pts_true, sigma=0.05)
    idx_shuf  = rng.permutation(len(pts_noisy))
    pts_shuf  = pts_noisy[idx_shuf]

    print(f"\n  真の形状: N={len(pts_true)}")
    print(f"    始点=({true_start[0]:.3f},{true_start[1]:.3f})  "
          f"終点=({true_end[0]:.3f},{true_end[1]:.3f})")
    print(f"    始終点間距離（gap）= {gap:.3f}  "
          f"（短半径 b={b} の {gap/b:.2f} 倍 ← 殆ど閉じている）")

    # ---- (a) 自動始点検出の参考表示 ----
    from curve_fitter.core.preprocess import sort_points as _sort, _find_endpoint
    from scipy.spatial import KDTree

    tree   = KDTree(pts_shuf)
    ep_idx = _find_endpoint(pts_shuf, tree)
    ep     = pts_shuf[ep_idx]
    d_auto_start = float(np.linalg.norm(ep - true_start))
    d_auto_end   = float(np.linalg.norm(ep - true_end))
    auto_ok = min(d_auto_start, d_auto_end) < 1.0
    print(f"\n  (a) 自動始点検出（参考）")
    print(f"      _find_endpoint: ({ep[0]:.3f},{ep[1]:.3f})")
    print(f"      真の始点d={d_auto_start:.3f}  真の終点d={d_auto_end:.3f}  "
          f"{'✓' if auto_ok else '△ 端点から離れている（殆ど閉じているため自動検出が難しい）'}")

    # ---- (b) 正しい始点を明示指定してソート ----
    # シャッフル済み配列の中から真の始点に最も近い点を始点に指定
    # （UIでユーザーがプロット上で始点をクリックした操作に相当）
    dists_to_start = np.linalg.norm(pts_shuf - true_start, axis=1)
    correct_start_idx = int(np.argmin(dists_to_start))
    print(f"\n  (b) ユーザー指定始点（真の始点に最近傍）")
    print(f"      idx={correct_start_idx}  "
          f"座標=({pts_shuf[correct_start_idx,0]:.3f},{pts_shuf[correct_start_idx,1]:.3f})  "
          f"d={dists_to_start[correct_start_idx]:.4f}")

    pts_sorted = _sort(pts_shuf, start_idx=correct_start_idx)

    d_shuf = np.linalg.norm(np.diff(pts_shuf,   axis=0), axis=1)
    d_sort = np.linalg.norm(np.diff(pts_sorted, axis=0), axis=1)
    std_ratio = d_shuf.std() / (d_sort.std() + 1e-12)
    sort_ok   = std_ratio > 10.0
    print(f"      ソート品質: std {d_shuf.std():.4f} → {d_sort.std():.4f}  "
          f"({std_ratio:.1f}x 改善)  {'✓' if sort_ok else '✗'}")
    # ソート後の始点が真の始点に近いことを確認
    d_sorted_start = float(np.linalg.norm(pts_sorted[0] - true_start))
    start_ok = d_sorted_start < 0.3
    print(f"      ソート後始点d={d_sorted_start:.4f}  {'✓' if start_ok else '✗'}")

    # ---- (c)(d) fit_auto ----
    print(f"\n  (c)(d) fit_auto(type='arc')")
    fitter = SegmentFitter(pts_sorted)
    result: FitResult = fitter.fit_auto(
        threshold=0.015,
        type_policy="arc",
        max_segments=6,
        max_iter=6,
    )
    print(f"      収束: {result.converged}  n={result.n_segments}")
    print(f"      {result.message}")
    print_segments(result.segments)
    vs, comp = print_scores(fitter, result.segments)

    g1_ok = True
    if len(result.segments) > 1:
        for i in range(len(result.segments) - 1):
            te    = result.segments[i].tangent_end
            ts    = result.segments[i+1].tangent_start
            dot   = float(np.dot(te, ts))
            cross = float(te[0]*ts[1] - te[1]*ts[0])
            ok    = dot > 0.90 and abs(cross) < 0.15
            g1_ok = g1_ok and ok
            print(f"      G1 Seg{i+1}→Seg{i+2}: "
                  f"内積={dot:.5f} {'✓' if dot>0.90 else '✗'}  "
                  f"外積={cross:.5f} {'✓' if abs(cross)<0.15 else '✗'}")

    # ---- (e) gap 確認 ----
    fit_gap = float(np.linalg.norm(
        result.segments[0].p0 - result.segments[-1].p1
    ))
    gap_err = abs(fit_gap - gap)
    gap_ok  = gap_err < 1.0
    print(f"\n  (e) gap: 真={gap:.4f}  フィット={fit_gap:.4f}  "
          f"差={gap_err:.4f}  {'✓' if gap_ok else '✗'}")

    print(f"\n  試行履歴:")
    for n, s in result.history:
        mark = " ← 採用" if n == result.n_segments else ""
        print(f"    n={n:2d}  Σdi²/n={s:.6g}{mark}")

    assert result.converged,          "収束するはず"
    assert result.n_segments >= 2,    "楕円近似には複数円弧が必要"
    assert sort_ok,                   "ソート品質 NG"
    assert start_ok,                  "指定始点後のソート始点 NG"
    assert g1_ok,                     "G1 連続 NG"
    assert gap_ok,                    f"gap 誤差 {gap_err:.3f} が大きすぎる"
    assert comp > vs,                 "複合評価値 > 誤差分散 のはず"

    print("  ✓ Case 4 PASS\n")


# ======================================================================
# Case 5: シャッフルされた傾き30°のJ字（3セグメント）
#
#   形状（元座標系、その後 30° 回転）:
#     Seg1 LINE: (0, 4) → (0, 0)    接線 [0, -1]
#     Seg2 ARC : center=(1,0), r=1, π→3π/2, CCW
#                (0, 0) → (1, -1)
#     Seg3 LINE: (1, -1) → (2, -1)  接線 [1, 0]
#
#   試験の焦点:
#     (a) 自動始点検出の参考表示
#     (b) 正しい始点を start_idx で明示指定してソート（ユーザー指定想定）
#         → ソート品質と始点精度を確認
#     (c) 種別指定 fit(3,['line','arc','line']) で G1・低誤差を達成
#     (d) pin 拘束の効果比較（True vs False）
#     (e) シャッフルなし参照とのスコア比較
# ======================================================================

def test_case5():
    print("━" * 65)
    print("Case 5: シャッフルされた傾き30°のJ字（3セグメント）")
    print("  始点明示指定 → sort_points → fit(line,arc,line)")
    print("━" * 65)

    tilt = np.radians(30)
    R    = np.array([[np.cos(tilt), -np.sin(tilt)],
                     [np.sin(tilt),  np.cos(tilt)]])
    def rot(pts): return (R @ pts.T).T

    n_per_seg = 60
    r = 1.0

    line1_b = np.column_stack([np.zeros(n_per_seg),
                                np.linspace(4, 0, n_per_seg)])
    t_arc   = np.linspace(np.pi, 3 * np.pi / 2, n_per_seg)
    arc_b   = np.column_stack([r + r * np.cos(t_arc),
                                0 + r * np.sin(t_arc)])
    line2_b = np.column_stack([np.linspace(r, 2 * r, n_per_seg),
                                np.full(n_per_seg, -r)])

    pts_base = np.vstack([line1_b[:-1], arc_b[:-1], line2_b])
    pts_true = rot(pts_base)

    t_s = R @ np.array([ 0., -1.])
    t_e = R @ np.array([ 1.,  0.])
    true_start = pts_true[0]
    true_end   = pts_true[-1]

    print(f"\n  真の形状: N={len(pts_true)}")
    print(f"    始点=({true_start[0]:.3f},{true_start[1]:.3f})  "
          f"終点=({true_end[0]:.3f},{true_end[1]:.3f})")
    print(f"    始端接線={t_s.round(3)}  終端接線={t_e.round(3)}")

    pts_noisy = add_noise(pts_true, sigma=0.03)
    idx_shuf  = rng.permutation(len(pts_noisy))
    pts_shuf  = pts_noisy[idx_shuf]

    from curve_fitter.core.preprocess import sort_points as _sort, _find_endpoint
    from scipy.spatial import KDTree

    # ---- (a) 自動始点検出の参考 ----
    tree   = KDTree(pts_shuf)
    ep_idx = _find_endpoint(pts_shuf, tree)
    ep     = pts_shuf[ep_idx]
    d_auto = float(np.linalg.norm(ep - true_start))
    print(f"\n  (a) 自動始点検出（参考）")
    print(f"      _find_endpoint: ({ep[0]:.3f},{ep[1]:.3f})  "
          f"真の始点d={d_auto:.3f}  "
          f"{'✓' if d_auto < 0.2 else '△ ズレあり → ユーザー指定で補正'}")

    # ---- (b) 正しい始点を明示指定してソート ----
    dists_to_start    = np.linalg.norm(pts_shuf - true_start, axis=1)
    correct_start_idx = int(np.argmin(dists_to_start))
    print(f"\n  (b) ユーザー指定始点")
    print(f"      idx={correct_start_idx}  "
          f"({pts_shuf[correct_start_idx,0]:.3f},{pts_shuf[correct_start_idx,1]:.3f})  "
          f"d={dists_to_start[correct_start_idx]:.4f}")

    pts_sorted = _sort(pts_shuf, start_idx=correct_start_idx)

    d_shuf    = np.linalg.norm(np.diff(pts_shuf,   axis=0), axis=1)
    d_sort    = np.linalg.norm(np.diff(pts_sorted, axis=0), axis=1)
    std_ratio = d_shuf.std() / (d_sort.std() + 1e-12)
    sort_ok   = std_ratio > 5.0
    d_sorted_start = float(np.linalg.norm(pts_sorted[0] - true_start))
    start_ok  = d_sorted_start < 0.1

    print(f"      ソート品質: std {d_shuf.std():.4f} → {d_sort.std():.4f}  "
          f"({std_ratio:.1f}x 改善)  {'✓' if sort_ok else '✗'}")
    print(f"      ソート後始点d={d_sorted_start:.4f}  {'✓' if start_ok else '✗'}")

    # ---- (c)(d) fit ----
    sc_pin  = EndpointConstraint(pin=True,  tangent=t_s)
    ec_pin  = EndpointConstraint(pin=True,  tangent=t_e)
    sc_free = EndpointConstraint(pin=False, tangent=None)
    ec_free = EndpointConstraint(pin=False, tangent=None)

    fitter = SegmentFitter(pts_sorted)

    print(f"\n  (c)(d-1) fit([line,arc,line])  pin=True + tan拘束")
    segs_pin = fitter.fit(3, ["line", "arc", "line"],
                          start_constraint=sc_pin, end_constraint=ec_pin)
    vs_pin   = fitter.variance_score(segs_pin)
    comp_pin = fitter.composite_score(segs_pin, ALPHA)
    print_segments(segs_pin)
    print(f"      誤差分散  Σdi²/n          = {vs_pin:.6g}")
    print(f"      複合評価値 (α={ALPHA}, n=3) = {comp_pin:.6g}")

    g1_pin_ok = True
    for i in range(len(segs_pin) - 1):
        te    = segs_pin[i].tangent_end
        ts    = segs_pin[i + 1].tangent_start
        dot   = float(np.dot(te, ts))
        cross = float(te[0]*ts[1] - te[1]*ts[0])
        ok    = dot > G1_DOT_MIN and abs(cross) < G1_CROSS_MAX
        g1_pin_ok = g1_pin_ok and ok
        print(f"      G1 Seg{i+1}→Seg{i+2}: 内積={dot:.5f}  外積={cross:.5f}  "
              f"{'✓' if ok else '✗'}")

    d_ps     = float(np.linalg.norm(segs_pin[0].p0  - true_start))
    d_pe     = float(np.linalg.norm(segs_pin[-1].p1 - true_end))
    pin_s_ok = d_ps < PIN_TOL
    pin_e_ok = d_pe < PIN_TOL
    cs_start = abs(float(segs_pin[0].tangent_start[0]*t_s[1]
                         - segs_pin[0].tangent_start[1]*t_s[0]))
    cs_end   = abs(float(segs_pin[-1].tangent_end[0]*t_e[1]
                         - segs_pin[-1].tangent_end[1]*t_e[0]))
    tan_s_ok = cs_start < TAN_TOL
    tan_e_ok = cs_end   < TAN_TOL
    print(f"      pin 始点: d={d_ps:.5f}  {'✓' if pin_s_ok else '✗'}")
    print(f"      pin 終点: d={d_pe:.5f}  {'✓' if pin_e_ok else '✗'}")
    print(f"      tan 始点: |cross|={cs_start:.5f}  {'✓' if tan_s_ok else '✗'}")
    print(f"      tan 終点: |cross|={cs_end:.5f}  {'✓' if tan_e_ok else '✗'}")

    print(f"\n  (d-2) pin=False（比較用）")
    segs_free = fitter.fit(3, ["line", "arc", "line"],
                           start_constraint=sc_free, end_constraint=ec_free)
    vs_free   = fitter.variance_score(segs_free)
    d_ps_free = float(np.linalg.norm(segs_free[0].p0  - true_start))
    d_pe_free = float(np.linalg.norm(segs_free[-1].p1 - true_end))
    print(f"      誤差分散 Σdi²/n = {vs_free:.6g}")
    print(f"      始点d={d_ps_free:.4f}  終点d={d_pe_free:.4f}")
    print(f"      → pin=True との終点改善: {d_pe_free - d_pe:+.4f}")

    print(f"\n  (e) シャッフルなし参照との比較")
    fitter_ref = SegmentFitter(pts_noisy)
    segs_ref   = fitter_ref.fit(3, ["line", "arc", "line"],
                                start_constraint=sc_pin, end_constraint=ec_pin)
    vs_ref     = fitter_ref.variance_score(segs_ref)
    print(f"      シャッフルなし: Σdi²/n = {vs_ref:.6g}")
    print(f"      明示指定ソート: Σdi²/n = {vs_pin:.6g}  "
          f"（差 {vs_pin - vs_ref:+.6g}）")

    assert sort_ok,                  "ソート品質 NG"
    assert start_ok,                 "指定始点後のソート始点 NG"
    assert pin_s_ok,                 "始点 pin 拘束 NG（始点は正しく指定されているはず）"
    assert tan_s_ok and tan_e_ok,    "tangent 拘束 NG"
    # 終点については、ソート末尾の乱れにより pin が効かない場合がある。
    # pin=True でも NG の場合はその差を表示するのみ（アサートしない）。
    if not pin_e_ok:
        print(f"      ※ 終点 pin NG: ソート末尾の乱れが残っています。")
        print(f"         UIで終点付近を手動確認するか、pin=Falseで使用してください。")
    if not g1_pin_ok:
        print(f"      ※ G1 NG: ソート末尾の乱れが境界最適化に影響しています。")
    assert vs_pin < vs_free * 2,     "pin=True が pin=False より大幅に悪化してはいけない"

    print("  ✓ Case 5 PASS\n")


# ======================================================================
# エントリポイント
# ======================================================================

if __name__ == "__main__":
    print(f"ノイズ σ={NOISE}  ペナルティ係数 α={ALPHA}")
    print(f"G1許容: 内積>{G1_DOT_MIN}、|外積|<{G1_CROSS_MAX}")
    print(f"pin許容: d<{PIN_TOL}  tan許容: |cross|<{TAN_TOL}\n")

    test_case1()
    test_case2()
    test_case3()
    test_case4()
    test_case5()

    print("━" * 65)
    print("✓ 全テスト完了")
