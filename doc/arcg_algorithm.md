## ALGORITHM FOR ARCG

Find arc and line segments to fit given points in 2D space.

### TARGET

Given N points $(x_i, y_i)$ where $i \in (1,N)$, find a series of G1-continuous M segments (Line or Arc) that fit them within a given variance threshold $\delta$.

The distance $d_i$ from point $i$ to its nearest segment is the perpendicular distance to that segment (clamped to the segment's extent). The global score is:

```math
D_t = \frac{1}{N} \sum_{i=1}^{N} d_i^2
```

where $d_i$ is the distance to the nearest segment across all M segments. Convergence is declared when:

```math
D_t < \delta
```

---

### PREPROCESSING

Before fitting, the raw point cloud is prepared in this order:

1. **Outlier removal** (`remove_outliers`): For each point, compute the mean distance to its $k$ nearest neighbors. Remove points whose mean distance exceeds $k \times \text{median}$ of all mean distances (default $k=5.0$, $n\_neighbors=3$).

2. **Sorting** (`sort_points`): Reorder the unordered point cloud into a curve-following sequence using greedy nearest-neighbor traversal. The start point is auto-selected as the point whose neighbors are most one-sided (largest norm of centroid-offset vector among top-10% candidates; among ties, the leftmost x-coordinate wins).

3. **Duplicate removal** (`remove_duplicates`): Scan the sorted sequence and discard points closer than `min_dist` to the previously kept point (default `min_dist=0.1`).

---

### DATA STRUCTURES

**LineSegment**
- `p0`, `p1`: start and end coordinates `[x, y]`
- `tangent_start` = `tangent_end` = unit vector along `p1 - p0`

**ArcSegment**
- `center`: circle center `[cx, cy]`
- `radius`: float
- `theta_start`, `theta_end`: start/end angles in radians
- `ccw`: bool — counterclockwise if True
- `tangent_start`: perpendicular to radius at `theta_start` (ccw-aware)
- `tangent_end`: perpendicular to radius at `theta_end` (ccw-aware)

**EndpointConstraint**
- `pin`: bool — force the endpoint to pass through the corresponding point-cloud endpoint
- `tangent`: unit vector or None — force the tangent direction at this endpoint

**FitResult**
- `segments`: list of Segment objects (G1-continuous)
- `n_segments`: count
- `score`: $D_t = \Sigma d_i^2 / N$
- `converged`: bool
- `message`: convergence description
- `history`: list of `(n_segments, score)` per trial

---

### SCORE METRICS

**`variance_score(segments)`**

For each point $i$, compute the perpendicular distance $d_i$ to the nearest segment. Return $\Sigma d_i^2 / N$.

- For a **LineSegment**: project the point onto the infinite line; clamp the projection parameter $t \in [0,1]$ to stay on the finite segment; if $t$ is clamped, use the nearest endpoint distance.
- For an **ArcSegment**: check if the point's angle (from center) falls within the arc range `[theta_start, theta_end]`. If yes, $d_i = |\text{dist\_from\_center} - R|$. If not, $d_i = \min(d_{p0}, d_{p1})$.

**`composite_score(segments, alpha=0.1)`**

$$\text{composite} = D_t \times (1 + \alpha \times n)$$

Penalizes solutions with more segments. Used for display/analysis; the main convergence check uses `variance_score` only.

---

### SEGMENT TYPE FITTING

**`_fit_line(chunk)`** — SVD least-squares line

1. Compute centroid of `chunk`.
2. SVD of `chunk - centroid`; take first right-singular vector as the line direction.
3. Project `chunk[0]` and `chunk[-1]` onto this axis to get `p0`, `p1`.

**`_fit_arc(chunk)`** — Algebraic least-squares circle + angle mapping

1. **`_fit_circle(chunk)`**: Solve the linear system $\mathbf{A} [c_x, c_y, C]^T = x^2 + y^2$ where $A = [x, y, 1]$, using `np.linalg.lstsq`. Recover $c_x = \text{result}[0]/2$, $c_y = \text{result}[1]/2$, $R = \sqrt{\text{result}[2] + c_x^2 + c_y^2}$.
2. Compute $\theta_i = \text{arctan2}(y_i - c_y,\; x_i - c_x)$ for each point.
3. Determine direction: `ccw = True` if the angular span from `theta_start` to `theta_end` (normalized to $[0, 2\pi)$) is $\le \pi$.

**Type selection** (`_resolve_type`)

```
line_err = mean perpendicular distance of chunk from line through endpoints
arc_err  = mean |dist_from_center - R|  (from _fit_circle)

if stype == "line":   → line
if stype == "arc":    candidate = "arc"
if stype == "auto":   candidate = "arc"  if arc_err < line_err AND line_err > tol×0.1
                                 "line"  otherwise
if candidate == "arc" AND max_radius is set AND R > max_radius:  → line
```

---

### CORE FITTING ALGORITHM

#### `fit(n_segments, seg_types, tolerance, start_constraint, end_constraint)`

Fit a fixed number of segments:

1. Divide the N points into `n_segments` chunks using `linspace(0, N-1, n+1)`.
2. For each chunk, call `_resolve_type` then `_fit_line` or `_fit_arc`.
3. Call `_enforce_g1(segments)` to make boundaries G1-continuous.
4. Call `_apply_endpoint_constraints(segments, pts, sc, ec)`.
5. If endpoint constraints exist and `n_segments > 1`, re-call `_enforce_g1(segments, sc, ec)` up to 3 times (constraints change geometry so G1 needs re-enforcement).
6. Call `_remove_small_arcs(segments)` as post-processing.

#### `fit_auto(threshold, type_policy, max_segments, max_iter, tol_type, start_constraint, end_constraint)`

Automatically search for the minimum segment count that achieves $D_t < \delta$:

```
for n = 1 to max_segments:
    segs, score, boundaries = _fit_with_boundary_opt(n, ...)
    record (n, score) in history
    track best_score and best_segments
    if score < threshold:
        converged = True
        break
post-process best_segments with _remove_small_arcs()
return FitResult
```

If the loop completes without convergence, returns the best result with `converged=False`.

#### `_fit_with_boundary_opt(n_segments, seg_types, tol_type, max_iter, start_constraint, end_constraint)`

Fit n segments while iteratively optimizing the boundary positions:

1. **Initialize** boundaries as `linspace(0, N-1, n+1)` (integer indices, even split).
2. **Initial fit**: build segments, enforce G1, apply endpoint constraints (+ up to 3 G1 re-enforcements if constraints present). Compute `best_score`.
3. **Iterative boundary search** (up to `max_iter` rounds):
   - For each internal boundary index `bi` (1 to n-1):
     - Let `lo = boundaries[bi-1] + 1`, `hi = boundaries[bi+1] - 1`.
     - Compute `search_radius = max(1, (hi - lo) // 4)`.
     - Generate candidates: integer range `[orig - search_radius, orig + search_radius]` clamped to `[lo, hi]`.
     - For each candidate (skip if equal to current):
       - Rebuild segments, enforce G1, apply constraints, compute score.
       - If score improves: accept this boundary position, update `best_score`.
       - Else: revert.
   - If no boundary improved in this round: **break early**.
4. Return `(best_segs, best_score, best_boundaries)`.

---

### G1 CONTINUITY ENFORCEMENT (`_enforce_g1`)

Applied after every segment build. Uses two phases:

#### Phase 1 — Boundary point optimization

For each internal boundary between segment $i$ and segment $i+1$:

- **Initial boundary point** $b_0$: midpoint of `curr.p1` and `nxt.p0`.
- **Scale**: max of the two adjacent segment lengths (used for regularization and degenerate-move guard).

**General case** — 2D Nelder-Mead minimization over $b = (b_x, b_y)$:

$$\text{obj}(b) = \text{cross}(t_\text{curr\_end},\; t_\text{nxt\_start})^2 + \max(0,\; -t_\text{curr} \cdot t_\text{nxt}) \times 10 + 0.5 \times \left(\frac{||b - b_0||}{\text{scale}}\right)^2$$

where the cross product being zero enforces G1 tangent matching; the dot penalty discourages opposite-facing tangents; the regularization keeps $b$ near $b_0$. If the optimal $b$ moves more than $1.0 \times \text{scale}$ from $b_0$, revert to $b_0$ (degenerate-move guard).

**Start-constrained case** (first boundary + start has tangent constraint + first segment is a line): restrict to 1D search along `sc.tangent` from the fixed start point. Minimizes the same objective restricted to $b = p_0 + s \cdot t_\text{dir}$.

**End-constrained case** (last boundary + end has tangent constraint + last segment is a line): restrict to 1D search backward along `ec.tangent` from the fixed end point.

#### Phase 2 — Segment reconstruction

For each segment $i$, call `_apply_segment_endpoints(seg, boundaries[i], boundaries[i+1])`:

- **Line**: directly set `p0 = boundaries[i]`, `p1 = boundaries[i+1]`.
- **Arc**: find a new circle center (preserving existing radius) that passes through both boundary points using the perpendicular bisector method. Of the two candidate centers, keep the one closest to the existing center (preserves arc direction/ccw). Update `center`, `theta_start`, `theta_end`.

---

### ENDPOINT CONSTRAINTS (`_apply_endpoint_constraints`)

Applied independently to the first and last segment after G1 enforcement.

**Processing order: pin → tangent**

**`pin=True`**: Force the endpoint to the exact first/last point of the sorted point cloud.
- Line: set `p0` or `p1` directly.
- Arc: update `theta_start`/`theta_end` and recenter using perpendicular bisector from the other arc endpoint.

**`tangent` (unit vector)**: Force the tangent direction at the endpoint.
- Line: adjust the far endpoint to achieve the target tangent while preserving segment length. If `pin=True`, the pinned endpoint is fixed and the far endpoint is moved; otherwise the near endpoint is adjusted.
- Arc: compute `theta` from the tangent via inverse tangent formula, then recenter if pin is also set.

---

### POST-PROCESSING: SMALL ARC REMOVAL (`_remove_small_arcs`)

Called after convergence (in both `fit` and `fit_auto`). Only active when `min_radius` is set.

Iterates until no more removals are needed:
- Find first arc with `radius < min_radius`.
- **Only segment**: replace with `LineSegment(p0, p1)`.
- **Head arc**: extend `segments[1]` start to `arc.p0`; remove arc.
- **Tail arc**: extend `segments[-2]` end to `arc.p1`; remove arc.
- **Middle arc**: connect the previous segment end and next segment start at the arc midpoint `(arc.p0 + arc.p1) / 2`; remove arc.

After all removals, re-enforce G1 if more than one segment remains.

---

### PARAMETERS

| Parameter | Default | Description |
|-----------|---------|-------------|
| `threshold` | (required) | Variance score $D_t$ convergence target |
| `max_segments` | 20 | Upper bound for segment count search |
| `max_iter` | 5 | Boundary search iterations per segment count |
| `tol_type` | 1.0 | Tolerance for line/arc auto-selection |
| `alpha` | 0.1 | Segment count penalty for `composite_score` |
| `max_radius` | None | Arc radius upper bound; exceeding → downgrade to line (applied during type selection) |
| `min_radius` | None | Arc radius lower bound; below → removed in post-processing |
| `start_constraint` | None | `EndpointConstraint` for start (pin and/or tangent) |
| `end_constraint` | None | `EndpointConstraint` for end (pin and/or tangent) |
