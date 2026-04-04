# ARCG_CC — Claude Code 引き継ぎプロンプト

このファイルを Claude Code の最初のメッセージに貼り付けてください。

---

## プロジェクト概要

**ARCG_CC**（Arc & Curve G1 Continuous Curve Fitter）

DXF / CSV から読み込んだ 2D 点群を、G1 連続（接線連続）な直線・円弧セグメントで近似するデスクトップアプリ。

- **UI**: PyQt6 + Matplotlib（FigureCanvasQTAgg 埋め込み）
- **パッケージ管理**: uv（`pyproject.toml`）
- **CSV 読み込み**: polars（pandas 不使用）

---

## フォルダ構成

```
curve_fitter/
├── main.py                  エントリポイント  python curve_fitter/main.py
├── pyproject.toml           uv 用プロジェクト定義
├── requirements.txt         pip 用（polars, pyyaml 含む）
├── core/
│   ├── __init__.py
│   ├── fitter.py            SegmentFitter, EndpointConstraint, FitResult  (867行)
│   ├── loader.py            DXF/CSV → numpy (N,2)  polars 使用  (90行)
│   ├── preprocess.py        remove_outliers, sort_points, remove_duplicates  (204行)
│   ├── exporter.py          テキスト/CSV/DXF 出力  (154行)
│   └── session.py           YAML セッション保存・読み込み  (289行)
└── ui/
    ├── main_window.py       MainWindow  (383行)
    ├── control_panel.py     ControlPanel（右パネル）  (733行)
    └── plot_widget.py       PlotWidget（Matplotlib 埋め込み）  (269行)
```

---

## コアロジック（fitter.py）

### データクラス

```python
@dataclass
class LineSegment:
    p0: np.ndarray          # 始点
    p1: np.ndarray          # 終点
    tangent_start/end       # 接線（単位ベクトル）

@dataclass
class ArcSegment:
    center: np.ndarray
    radius: float
    theta_start/end: float  # rad
    ccw: bool
    p0, p1                  # 端点（プロパティ）
    tangent_start/end       # 接線（プロパティ）

@dataclass
class EndpointConstraint:
    pin: bool               # 点群端点を必ず通る
    tangent: np.ndarray | None  # 接線方向（自動正規化）

@dataclass
class FitResult:
    segments, n_segments, score, converged, message, history
```

### 主要メソッド

```python
fitter = SegmentFitter(points)          # points: np.ndarray (N,2)

# セグメント数指定フィット
segs = fitter.fit(
    n_segments=3,
    seg_types=["line","arc","line"],    # "line"/"arc"/"auto"
    tolerance=0.5,
    start_constraint=EndpointConstraint(pin=True, tangent=[1,0]),
    end_constraint=EndpointConstraint(pin=False, tangent=None),
)

# 自動探索（誤差分散閾値で最小セグメント数を探す）
result = fitter.fit_auto(
    threshold=0.01,
    type_policy="auto",                 # "auto"/"line"/"arc"
    max_segments=15,
    max_iter=8,
    tol_type=0.5,
    start_constraint=...,
    end_constraint=...,
)

# 評価
fitter.variance_score(segs)            # Σdi²/n
fitter.composite_score(segs, alpha=0.1) # Σdi²/n × (1 + α×n)
```

### G1 補正アルゴリズム

各セグメント境界点を Nelder-Mead で最適化。目的関数 = 接線外積² + 逆向きペナルティ + 正則化項。縮退ガード（境界点が元位置から 0.3×scale 以上動いたら中点に戻す）あり。

### 評価関数

```
Σdi²/n    : 各点→最近接セグメントへの垂線距離²の平均
            直線: クランプ付き射影距離
            円弧: 角度範囲内は |dist_from_center - r|、範囲外は端点距離

複合評価値: Σdi²/n × (1 + α × n)   デフォルト α=0.1
           α > 0.01/(V₁₀ - 0.11) のとき n=10 が n=11 より良い評価になる
```

---

## 前処理パイプライン（preprocess.py）

```python
# 推奨実行順序
pts = remove_outliers(pts_raw, k=5.0)       # 近傍距離 > 中央値×k の点を除去
pts = sort_points(pts, start_idx=None)       # 貪欲法で一筆書き順に整列
pts = remove_duplicates(pts, min_dist=0.1)   # 隣接距離 ≤ min_dist の点を除去
```

`_find_endpoint()` で「近傍が片側に偏っている点」を始点として自動選択。
殆ど閉じた曲線（楕円など）では自動検出が失敗しやすい → UI で手動指定可能。

---

## UI 構成（PyQt6）

### モード

| モード | 操作 | シグナル |
|--------|------|---------|
| 通常 | Matplotlib ズーム/パン | — |
| 始点指定 (`pick`) | クリックで始点を変更してソートし直す | `start_point_selected(idx)` |
| 点除外 (`exclude`) | クリックで除外、再クリックで取消 | `point_excluded(idx,x,y)` / `point_unexcluded(idx)` |

### 状態管理（main_window.py）

```python
self._pts_raw_clean   # 外れ値除去済み・未ソート（ソートし直しのベース）
self._points          # ソート済み・重複除去済み（fitter に渡す）
self._excluded        # 除外点インデックス集合 set[int]（_points 上）
self._fitter          # SegmentFitter(_active_points())
self._source_path     # 読み込んだファイルパス
```

`_active_points()` = `_points` から `_excluded` を除いた点群 → `_fitter` に渡す。

除外・始点変更のたびに `_rebuild_fitter()` を呼んで fitter を再構築。

### セッション保存（YAML）

```yaml
version: '1.0'
source:
  path: /path/to/data.csv   # ← ここだけ書き換えで別ファイルに同じ処理を適用
  min_dist: 0.1
preprocessing:
  start_point_coord: null   # [x, y] または null
  excluded_coords: []       # [[x,y], ...] 座標で保存（インデックスでない）
fit:
  mode: auto                # "auto" | "manual"
  alpha: 0.1
  auto:  {threshold, type_policy, max_segments, max_iter, tol_type}
  manual: {n_segments, seg_types, tolerance}
  start_constraint: {pin: false, tangent: null}
  end_constraint:   {pin: false, tangent: null}
  seg_colors: []
results:                    # 参照用（再実行時に上書き）
  variance, composite, n_segments, converged, message
```

### エクスポート（exporter.py）

| 形式 | 内容 |
|------|------|
| `default` | 人間可読テキスト（LINE/ARC） |
| `csv` | CSV |
| `dxf` | 2D DXF R2010（LINE/ARC エンティティ、レイヤー `ARCG_CC_SEGMENTS`） |

DXF の CW 円弧は開始角・終了角を入れ替えて ezdxf の CCW ARC に変換。

---

## テスト

### 実行方法

```bash
# uv
cd curve_fitter
uv sync
uv run python test_core.py          # コアロジック（GUI不要）
uv run python test_shapes.py        # 5ケース形状テスト

# GUI テスト（offscreen）
QT_QPA_PLATFORM=offscreen uv run python -W ignore -m unittest test_gui
# Windows:
# set QT_QPA_PLATFORM=offscreen
# uv run python -W ignore -m unittest test_gui
```

### テストケース

| ファイル | 内容 |
|---------|------|
| `test_core.py` | variance_score, fit_auto 収束・未収束、スコア単調性 |
| `test_constraints.py` | EndpointConstraint 全4パターン × fit/fit_auto |
| `test_shapes.py` | Case1: 直線 / Case2: 円弧 / Case3: ∫字 / Case4: 楕円（シャッフル） / Case5: J字（シャッフル） |
| `test_gui.py` | T1-T10: ControlPanel/PlotWidget/MainWindow/セッション（53テスト、offscreen実行） |

---

## 依存パッケージ

```toml
# pyproject.toml より
dependencies = [
    "PyQt6>=6.6",
    "matplotlib>=3.8",
    "numpy>=1.26",
    "scipy>=1.12",
    "ezdxf>=1.3",
    "polars>=1.0",
    "pyyaml>=6.0",
]
```

---

## 既知の課題・改善候補

- [ ] `test_shapes.py` の `if __name__ == "__main__":` ブロックが重複している（ファイル末尾を確認）
- [ ] `fit_auto` の境界最適化が局所解に陥る場合がある（境界インデックスの探索幅が限定的）
- [ ] 点除外後に始点インデックスが `_points` ベースなので `_excluded` との整合性に注意
- [ ] DXF 出力の単位は `MM` ハードコード（`session.yaml` に単位設定を追加する候補）
- [ ] インストーラ（`Install_ARCG_CC.ps1` / `ARCG_CC_setup.iss`）は未完成（後回し）
- [ ] GUI テストは描画を伴わない offscreen のみ。視覚的回帰テストは未実装

---

## Windows 配布ファイル

```
ARCG_CC/
├── curve_fitter/           アプリ本体
├── windows/
│   ├── ARCG_CC.vbs         ダブルクリック起動（pythonw、コンソールなし）
│   ├── ARCG_CC_debug.bat   デバッグ用（コンソールあり）
│   ├── ARCG_CC.ps1         PowerShell 版 + ショートカット作成
│   └── create_shortcut.vbs デスクトップショートカット作成
├── icons/
│   ├── arcg_cc.ico         Windows（16-256px マルチサイズ）
│   ├── arcg_cc.icns        macOS
│   └── arcg_cc_*.png       Linux 各サイズ
├── Install_ARCG_CC.ps1     PowerShell インストーラ（GUI付き）
└── ARCG_CC_setup.iss       Inno Setup スクリプト（.exe ビルド用）
```
