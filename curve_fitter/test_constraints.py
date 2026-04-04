"""
端点拘束のテスト（GUIなし）
4つの拘束スイッチの組合せを網羅的にテストする:
  pin, tangent の独立制御 × 始点/終点
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import numpy as np
from curve_fitter.core.fitter import SegmentFitter, EndpointConstraint

# -------------------------------------------------------------------
# 合成点群: 直線 → 円弧 → 直線
# -------------------------------------------------------------------
def make_pts(noise=0.02):
    rng = np.random.default_rng(0)
    line1  = np.column_stack([np.linspace(0, 5, 40), np.zeros(40)])
    thetas = np.linspace(-np.pi/2, 0, 40)
    arc    = np.column_stack([5 + 3*np.cos(thetas), 3 + 3*np.sin(thetas)])
    line2  = np.column_stack([np.linspace(8, 13, 40), np.full(40, 3.0)])
    pts    = np.vstack([line1, arc[1:], line2[1:]])
    return pts + rng.normal(0, noise, pts.shape)

pts = make_pts()
FIRST_PT = pts[0]
LAST_PT  = pts[-1]

def check(label, segments, *, pin_start=None, tan_start=None,
          pin_end=None, tan_end=None, tol=0.05):
    ok = True
    msgs = []

    if pin_start is not None:
        d = np.linalg.norm(segments[0].p0 - pin_start)
        status = "✓" if d < tol else "✗"
        if d >= tol: ok = False
        msgs.append(f"  始点 pin: d={d:.5f} {status}")

    if tan_start is not None:
        t = segments[0].tangent_start
        cross = abs(t[0]*tan_start[1] - t[1]*tan_start[0])
        status = "✓" if cross < tol else "✗"
        if cross >= tol: ok = False
        msgs.append(f"  始点 tan: |cross|={cross:.5f} {status}")

    if pin_end is not None:
        d = np.linalg.norm(segments[-1].p1 - pin_end)
        status = "✓" if d < tol else "✗"
        if d >= tol: ok = False
        msgs.append(f"  終点 pin: d={d:.5f} {status}")

    if tan_end is not None:
        t = segments[-1].tangent_end
        cross = abs(t[0]*tan_end[1] - t[1]*tan_end[0])
        status = "✓" if cross < tol else "✗"
        if cross >= tol: ok = False
        msgs.append(f"  終点 tan: |cross|={cross:.5f} {status}")

    result = "PASS" if ok else "FAIL"
    print(f"[{result}] {label}")
    for m in msgs:
        print(m)
    return ok


fitter = SegmentFitter(pts)

# -------------------------------------------------------------------
# Case 1: 拘束なし（ベースライン）
# -------------------------------------------------------------------
print("=" * 60)
print("Case 1: 拘束なし")
segs = fitter.fit(3, ["line","arc","line"])
print(f"  始点={segs[0].p0.round(4)}  終点={segs[-1].p1.round(4)}")
print(f"  score={fitter.variance_score(segs):.6g}")

# -------------------------------------------------------------------
# Case 2: 始点 pin のみ
# -------------------------------------------------------------------
print("=" * 60)
print("Case 2: 始点 pin のみ")
segs = fitter.fit(3, ["line","arc","line"],
                  start_constraint=EndpointConstraint(pin=True))
check("始点 pin", segs, pin_start=FIRST_PT)

# -------------------------------------------------------------------
# Case 3: 終点 pin のみ
# -------------------------------------------------------------------
print("=" * 60)
print("Case 3: 終点 pin のみ")
segs = fitter.fit(3, ["line","arc","line"],
                  end_constraint=EndpointConstraint(pin=True))
check("終点 pin", segs, pin_end=LAST_PT)

# -------------------------------------------------------------------
# Case 4: 始点 + 終点 両方 pin
# -------------------------------------------------------------------
print("=" * 60)
print("Case 4: 始終点 両方 pin")
segs = fitter.fit(3, ["line","arc","line"],
                  start_constraint=EndpointConstraint(pin=True),
                  end_constraint=EndpointConstraint(pin=True))
check("両端 pin", segs, pin_start=FIRST_PT, pin_end=LAST_PT)

# -------------------------------------------------------------------
# Case 5: 始点 接線のみ（x方向）
# -------------------------------------------------------------------
print("=" * 60)
print("Case 5: 始点 接線のみ [1,0]")
t_x = np.array([1.0, 0.0])
segs = fitter.fit(3, ["line","arc","line"],
                  start_constraint=EndpointConstraint(tangent=t_x))
check("始点 tan=[1,0]", segs, tan_start=t_x)

# -------------------------------------------------------------------
# Case 6: 終点 接線のみ（x方向）
# -------------------------------------------------------------------
print("=" * 60)
print("Case 6: 終点 接線のみ [1,0]")
segs = fitter.fit(3, ["line","arc","line"],
                  end_constraint=EndpointConstraint(tangent=t_x))
check("終点 tan=[1,0]", segs, tan_end=t_x)

# -------------------------------------------------------------------
# Case 7: 始点 pin + 接線（通過かつ接線指定）
# -------------------------------------------------------------------
print("=" * 60)
print("Case 7: 始点 pin + tan=[1,0]")
segs = fitter.fit(3, ["line","arc","line"],
                  start_constraint=EndpointConstraint(pin=True, tangent=t_x))
check("始点 pin+tan", segs, pin_start=FIRST_PT, tan_start=t_x)

# -------------------------------------------------------------------
# Case 8: 始点 pin のみ・終点 tan のみ（質問の例と同じ組合せ）
# -------------------------------------------------------------------
print("=" * 60)
print("Case 8: 始点 pin なし + tan=[1,0]、終点 拘束なし")
segs = fitter.fit(3, ["line","arc","line"],
                  start_constraint=EndpointConstraint(pin=False, tangent=t_x),
                  end_constraint=EndpointConstraint(pin=False, tangent=None))
check("始点 tan 終点 free", segs, tan_start=t_x)

# -------------------------------------------------------------------
# Case 9: fit_auto + 拘束
# -------------------------------------------------------------------
print("=" * 60)
print("Case 9: fit_auto + 始点 pin + tan=[1,0]")
result = fitter.fit_auto(
    threshold=0.01, type_policy="auto", max_segments=8, max_iter=4,
    start_constraint=EndpointConstraint(pin=True, tangent=t_x),
)
print(f"  収束: {result.converged}  n={result.n_segments}  score={result.score:.6g}")
print(f"  {result.message}")
check("auto 始点 pin+tan", result.segments, pin_start=FIRST_PT, tan_start=t_x)

print("=" * 60)
print("全テスト完了")
