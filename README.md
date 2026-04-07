# ARCG_CC

G1-continuous arc/line curve fitter. Fits a series of arc and line segments to a 2D point cloud, maintaining smooth (G1) tangent continuity at segment boundaries.

## セットアップ (uv)

```bash
uv sync
uv run curve_fitter/main.py
```

またはインストール済みの場合:

```bash
arcg-cc
```

## 使い方

1. **Load** — CSV ファイル（x, y 列）またはポイントデータを読み込む。`sample/` ディレクトリにサンプルデータあり。
2. **Configure** — パラメータウィンドウでフィット条件（閾値、セグメント数上限、端点拘束など）を設定。
3. **Fit** — "Fit" ボタンでフィッティングを実行。結果はプロットに表示。
4. **Export** — DXF または RTX 形式でエクスポート。

## 出力形式

- **DXF** — LINE/ARC エンティティの 2D DXF ファイル。CAD ソフトで直接利用可能。
- **RTX** — 管設独自フォーマット。点・線分・円弧を CSV ライクなテキストで表現。→ [RTX ファイル形式](doc/rtx_spec.md)

## アルゴリズム

与えられた点群に対し、分散スコア $D_t < \delta$ を満たす最小セグメント数の G1 連続曲線を自動探索する。詳細は [arcg_algorithm.md](doc/arcg_algorithm.md) を参照。

## サンプルデータ

`sample/` ディレクトリに以下の CSV ファイルが含まれる:

| ファイル | 内容 |
|----------|------|
| `arc_120deg.csv` | 120度円弧 |
| `s_curve.csv` | S字曲線 |
| `j_shape.csv` | J字形状 |

## Related Projects

- https://github.com/Yoshinobu-Ishizaki/arcg-wx2

    wxPython を使用した類似プログラム。端点から順にセグメントを増加させるアルゴリズム。
