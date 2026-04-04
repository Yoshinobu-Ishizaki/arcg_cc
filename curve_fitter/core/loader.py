"""
点群ローダー: DXF / CSV → numpy array (N×2)
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import polars as pl


def load_points(filepath: str | Path) -> np.ndarray:
    """
    DXF または CSV ファイルから2D点群を読み込み、shape=(N,2) の numpy 配列を返す。

    DXF: POINT / LINE / LWPOLYLINE / POLYLINE エンティティの頂点を収集
    CSV: 1列目=X, 2列目=Y（ヘッダー有無は自動判定）
    """
    path = Path(filepath)
    suffix = path.suffix.lower()

    if suffix == ".dxf":
        return _load_dxf(path)
    elif suffix == ".csv":
        return _load_csv(path)
    else:
        raise ValueError(f"未対応のファイル形式: {suffix}")


def _load_dxf(path: Path) -> np.ndarray:
    try:
        import ezdxf
    except ImportError:
        raise ImportError("ezdxf が必要です: uv add ezdxf")

    doc = ezdxf.readfile(str(path))
    pts: list[tuple[float, float]] = []

    for entity in doc.modelspace():
        dxftype = entity.dxftype()

        if dxftype == "POINT":
            pts.append((entity.dxf.location.x, entity.dxf.location.y))

        elif dxftype == "LINE":
            pts.append((entity.dxf.start.x, entity.dxf.start.y))
            pts.append((entity.dxf.end.x, entity.dxf.end.y))

        elif dxftype in ("LWPOLYLINE", "POLYLINE"):
            for v in entity.vertices():
                if hasattr(v, "dxf"):
                    pts.append((v.dxf.location.x, v.dxf.location.y))
                else:
                    pts.append((v[0], v[1]))

    if not pts:
        raise ValueError("DXF ファイルから点が取得できませんでした")
    return np.array(pts, dtype=float)


def _load_csv(path: Path) -> np.ndarray:
    """
    Polars で CSV を読み込む。ヘッダー有無を自動判定する。

    判定ロジック:
        先頭行の第1フィールドを float に変換できれば「ヘッダーなし」、
        できなければ「ヘッダーあり」とみなす。
    """
    # --- ヘッダー有無の判定 ---
    df_peek = pl.read_csv(path, has_header=False, n_rows=1)
    try:
        float(str(df_peek[0, 0]))
        has_header = False
    except ValueError:
        has_header = True

    # --- 本読み込み ---
    df = pl.read_csv(path, has_header=has_header)
    col0, col1 = df.columns[0], df.columns[1]

    df = (
        df.select([
            pl.col(col0).cast(pl.Float64).alias("x"),
            pl.col(col1).cast(pl.Float64).alias("y"),
        ])
        .drop_nulls()
    )

    if df.is_empty():
        raise ValueError("CSV ファイルから点が取得できませんでした")

    return df.to_numpy()
