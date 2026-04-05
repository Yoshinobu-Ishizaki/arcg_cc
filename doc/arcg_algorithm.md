## ALGORITHM FOR ARCG

Find arc and line segments to fit given points in 2D space.

### TARGET

Given N points $(x_i, y_i)$ where $i \in (1,N)$, find series of G1 continuous M segments to fit them within given distance threshold delta.

Segments are Line or Arc.

Distance between segment and point is calculated by normal distance from the point to the segment.

Suppose the nearest segment to i-th point is j-th segment. Then i-th point distance $d_i$ to the segment is calculated by distance beween i-th point and j-th segment.

We use L2 evaluation to sum up those distance. 

```math
D_t = \frac{1}{N} \sum_{i=1}^{N} d_i^2 
```

is the total distance between given points to fitted segment.

And this $D_t$ must be smaller than given threshold.

```math
D_t < \delta
```

Line or Arc segments are handled samely if you consider curvature $\rho = 1/R$ where R is the radius of an arc. If $\rho = 0$, it is a line.

### FORMULATION

1. Sort N-points with neibouring so that every i-th,(i+1)-th points having minimum distance than any other combination.
2. Select one of two end points as the starting point $p_1$.
3. Suppose that we can fit points into M segments.
4. M starts from 1 to M_max. M_max will be given by user.
5. Divide N-points into M group (initially evenly). 
6. Take first subgroup of points $p_1,p_2,...,p_{m1}$. 
7. Find a segment with curvature $\rho_1$ which fits them. Perhaps initial point constraints such as pinned to $p_1$ or tangent must be considered.
8. Check if a distance between subgroup and that segment $\delta_1 < \delta / M$. 
9. If not, move the last point of its group into next subgroup reducsing the number of points of subgroup considering.
10. Recalculate fitting segments for it until the condition \delta_1 < \delta /M is satisfied.
11. If condition is satisfied, move to next subgroup. And calculate fitting segment for it as step 7. 
12. Notice that for j-th segment, its starting point and vecor is fixed by the last point of previous segment and its ending tangent.
13. Loop with point reducing until distance \delta_2 satisfies condition.
14. If 2nd segment is found, move to 3rd, then 4th, so on.
15. Finally, evaluate total distance beween points and segments and see if condition $D_t < \delta$ is satisfied. 
16. If not, count up M and start over from step 5.
17. If total distance conditioin is satisfied, the target segments are found. Stop calculation here and report its result.

### ADDITIONAL CONDITIONS

- User can specify, R_max, R_min. If a found segment has curvature less then 1/R_max, it must be fall back to line where curvature is zero. If a found segment has curvature larger than 1/R_min, the subgroup points must be enlarged by including next point from next subgroup.
- User can pin last point $p_N$ and its vector. In that case, the M-th segment must satisfy that its end point is pinned to $p_N$ or its tangent at the end is equal to the specified one or both. The distance condition may not be satisfied because of this constraints and then we should count M up one.



