"""
セグメントエクスポーター

出力形式:
    default : 人間可読テキスト（LINE / ARC）
    csv     : CSV
    dxf     : 2D DXF R2010（LINE / ARC エンティティ）
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
from .fitter import Segment, LineSegment, ArcSegment


def export_segments(
    segments: list[Segment],
    filepath: str | Path,
    fmt: str = "default",
    precision: int = 6,
) -> None:
    """
    Parameters
    ----------
    segments : フィット済みセグメントリスト
    filepath : 出力先パス
    fmt      : 'default' | 'csv' | 'dxf'
    precision: 小数点以下桁数（dxf 以外で使用）
    """
    path = Path(filepath)
    if fmt == "dxf":
        _export_dxf(segments, path)
    else:
        lines = _format(segments, fmt, precision)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ------------------------------------------------------------------
# DXF 出力
# ------------------------------------------------------------------

def _export_dxf(segments: list[Segment], path: Path) -> None:
    """
    ezdxf を使って 2D DXF（R2010）を出力する。

    LINE セグメント → LINE エンティティ
    ARC  セグメント → ARC  エンティティ
        ezdxf の ARC は常に CCW 方向で定義する。
        CW セグメントは開始角・終了角を入れ替えて CCW に変換する。
    """
    try:
        import ezdxf
        from ezdxf import units
    except ImportError:
        raise ImportError("ezdxf が必要です: uv add ezdxf")

    doc = ezdxf.new(dxfversion="R2010")
    doc.units = units.MM          # 単位（必要に応じて変更可）

    # レイヤー定義
    LAYER = "ARCG_CC_SEGMENTS"
    doc.layers.add(LAYER, color=7)   # 7 = white/black (BYLAYER)

    msp = doc.modelspace()

    for seg in segments:
        if seg.kind == "line":
            msp.add_line(
                start=(float(seg.p0[0]), float(seg.p0[1]), 0.0),
                end  =(float(seg.p1[0]), float(seg.p1[1]), 0.0),
                dxfattribs={"layer": LAYER},
            )
        else:
            # ezdxf ARC: start_angle → end_angle を CCW 方向で描く
            cx, cy = float(seg.center[0]), float(seg.center[1])
            r      = float(seg.radius)
            ts_deg = float(np.degrees(seg.theta_start))
            te_deg = float(np.degrees(seg.theta_end))

            if seg.ccw:
                # CCW: そのまま
                start_angle, end_angle = ts_deg, te_deg
            else:
                # CW → ezdxf の ARC（常に CCW）に変換するため
                # 開始と終了を入れ替える
                start_angle, end_angle = te_deg, ts_deg

            # 角度を 0〜360 範囲に正規化
            start_angle = start_angle % 360.0
            end_angle   = end_angle   % 360.0

            msp.add_arc(
                center=(cx, cy, 0.0),
                radius=r,
                start_angle=start_angle,
                end_angle=end_angle,
                dxfattribs={"layer": LAYER},
            )

    doc.saveas(str(path))


def _format(segments: list[Segment], fmt: str, prec: int) -> list[str]:
    if fmt == "csv":
        return _format_csv(segments, prec)
    else:
        return _format_default(segments, prec)


def _format_default(segments: list[Segment], prec: int) -> list[str]:
    f = f".{prec}f"
    out = ["# Segment output (G1-continuous)"]
    out.append(f"# COUNT {len(segments)}")
    out.append("")

    for i, seg in enumerate(segments):
        out.append(f"# Segment {i + 1}")
        if seg.kind == "line":
            seg: LineSegment
            out.append(
                f"LINE  "
                f"{seg.p0[0]:{f}} {seg.p0[1]:{f}}  "
                f"{seg.p1[0]:{f}} {seg.p1[1]:{f}}"
            )
        else:
            seg: ArcSegment
            ts_deg = np.degrees(seg.theta_start)
            te_deg = np.degrees(seg.theta_end)
            direction = "CCW" if seg.ccw else "CW"
            out.append(
                f"ARC   "
                f"{seg.center[0]:{f}} {seg.center[1]:{f}}  "
                f"{seg.radius:{f}}  "
                f"{ts_deg:{f}} {te_deg:{f}}  {direction}"
            )
    return out


def _format_csv(segments: list[Segment], prec: int) -> list[str]:
    out = ["type,cx_or_x0,cy_or_y0,r_or_x1,theta_start_or_y1,theta_end,direction"]
    for seg in segments:
        if seg.kind == "line":
            out.append(
                f"LINE,{seg.p0[0]:.{prec}f},{seg.p0[1]:.{prec}f},"
                f"{seg.p1[0]:.{prec}f},{seg.p1[1]:.{prec}f},,"
            )
        else:
            ts = np.degrees(seg.theta_start)
            te = np.degrees(seg.theta_end)
            d = "CCW" if seg.ccw else "CW"
            out.append(
                f"ARC,{seg.center[0]:.{prec}f},{seg.center[1]:.{prec}f},"
                f"{seg.radius:.{prec}f},{ts:.{prec}f},{te:.{prec}f},{d}"
            )
    return out
