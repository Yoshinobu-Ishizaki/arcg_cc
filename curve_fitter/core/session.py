"""
パラメータ保存・読み込み

YAML 形式でアプリケーション状態全体を保存・復元する。
ソースファイルパスを書き換えて読み込めば、別のデータに
同じ前処理・フィットパラメータを適用できる。

保存内容:
  - ソースファイルパス・前処理パラメータ
  - 始点座標（インデックスではなく座標で保存）
  - 除外点座標リスト
  - フィットモード・パラメータ一式
  - 端点拘束
  - セグメント色
  - フィット結果の評価値（参照用）
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import numpy as np
import yaml


# ============================================================
# バージョン
# ============================================================
SESSION_VERSION = "1.0"


# ============================================================
# 保存
# ============================================================

def save_session(path: str | Path, state: dict) -> None:
    """
    パラメータ状態を YAML ファイルに書き出す。

    Parameters
    ----------
    path  : 保存先パス（.yaml 推奨）
    state : collect_state() で収集した辞書
    """
    doc = _build_doc(state)
    text = _dump_yaml(doc)
    Path(path).write_text(text, encoding="utf-8")


def _build_doc(state: dict) -> dict:
    """state 辞書から YAML 用ドキュメントを構築する"""
    doc: dict[str, Any] = {}
    doc["version"] = SESSION_VERSION

    # ---- ソースファイル ----
    src: dict[str, Any] = {}
    src["path"]     = state.get("source_path", "")
    src["min_dist"] = float(state.get("min_dist", 0.1))
    doc["source"] = src

    # ---- 前処理 ----
    pre: dict[str, Any] = {}
    sp = state.get("start_point_coord")
    pre["start_point_coord"] = (
        [float(sp[0]), float(sp[1])] if sp is not None else None
    )
    ex_coords = state.get("excluded_coords", [])
    pre["excluded_coords"] = [
        [float(c[0]), float(c[1])] for c in ex_coords
    ]
    doc["preprocessing"] = pre

    # ---- フィットパラメータ ----
    fit: dict[str, Any] = {}
    fit["mode"]       = state.get("fit_mode", "auto")   # "auto" | "manual"
    fit["alpha"]      = float(state.get("alpha", 0.1))
    fit["seg_colors"] = list(state.get("seg_colors", []))

    # auto モードパラメータ
    fit["auto"] = {
        "threshold":    float(state.get("threshold", 0.01)),
        "type_policy":  state.get("type_policy", "auto"),
        "max_segments": int(state.get("max_segments", 15)),
        "max_iter":     int(state.get("max_iter", 8)),
        "tol_type":     float(state.get("tol_type", 0.5)),
    }

    # manual モードパラメータ
    fit["manual"] = {
        "n_segments": int(state.get("n_segments", 3)),
        "seg_types":  list(state.get("seg_types", [])),
        "tolerance":  float(state.get("tolerance", 0.5)),
    }

    # 端点拘束
    fit["start_constraint"] = _encode_constraint(
        state.get("start_pin", False),
        state.get("start_tangent"),
    )
    fit["end_constraint"] = _encode_constraint(
        state.get("end_pin", False),
        state.get("end_tangent"),
    )
    doc["fit"] = fit

    # ---- 結果（参照用） ----
    res: dict[str, Any] = {}
    res["variance"]   = _maybe_float(state.get("variance"))
    res["composite"]  = _maybe_float(state.get("composite"))
    res["n_segments"] = state.get("result_n_segments")
    res["converged"]  = state.get("converged")
    res["message"]    = state.get("message", "")
    doc["results"] = res

    return doc


def _encode_constraint(pin: bool, tangent) -> dict:
    t = None
    if tangent is not None:
        arr = np.asarray(tangent, dtype=float)
        t = [float(arr[0]), float(arr[1])]
    return {"pin": bool(pin), "tangent": t}


def _maybe_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if (f != f or abs(f) == float("inf")) else round(f, 10)
    except (TypeError, ValueError):
        return None


def _dump_yaml(doc: dict) -> str:
    """コメントヘッダー付きの YAML 文字列を生成する"""
    header = (
        "# curve_fitter パラメータファイル\n"
        "# source.path を書き換えて読み込むと、別のファイルに同じ処理を適用できます。\n"
        "#\n"
        "# 保存項目:\n"
        "#   source       : ソースファイルパス・前処理パラメータ\n"
        "#   preprocessing: 始点座標・除外点座標\n"
        "#   fit          : フィットモード・パラメータ・端点拘束・セグメント色\n"
        "#   results      : 評価値（参照用、再計算時に上書きされる）\n"
        "#\n"
    )
    body = yaml.dump(
        doc,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=120,
    )
    return header + body


# ============================================================
# 読み込み
# ============================================================

def load_session(path: str | Path) -> dict:
    """
    YAML パラメータファイルを読み込み、state 辞書を返す。

    Returns
    -------
    dict : save_session() に渡したものと同じキー構造の辞書
    """
    text = Path(path).read_text(encoding="utf-8")
    doc  = yaml.safe_load(text)

    ver = doc.get("version", "1.0")
    if ver != SESSION_VERSION:
        raise ValueError(
            f"パラメータファイルのバージョン '{ver}' は "
            f"現在のバージョン '{SESSION_VERSION}' と異なります。"
        )

    state: dict[str, Any] = {}

    # ---- ソース ----
    src = doc.get("source", {})
    state["source_path"] = src.get("path", "")
    state["min_dist"]    = float(src.get("min_dist", 0.1))

    # ---- 前処理 ----
    pre = doc.get("preprocessing", {})
    sp  = pre.get("start_point_coord")
    state["start_point_coord"] = (
        [float(sp[0]), float(sp[1])] if sp else None
    )
    ex = pre.get("excluded_coords", []) or []
    state["excluded_coords"] = [
        [float(c[0]), float(c[1])] for c in ex
    ]

    # ---- フィット ----
    fit = doc.get("fit", {})
    state["fit_mode"]    = fit.get("mode", "auto")
    state["alpha"]       = float(fit.get("alpha", 0.1))
    state["seg_colors"]  = list(fit.get("seg_colors", []))

    auto = fit.get("auto", {})
    state["threshold"]    = float(auto.get("threshold", 0.01))
    state["type_policy"]  = auto.get("type_policy", "auto")
    state["max_segments"] = int(auto.get("max_segments", 15))
    state["max_iter"]     = int(auto.get("max_iter", 8))
    state["tol_type"]     = float(auto.get("tol_type", 0.5))

    manual = fit.get("manual", {})
    state["n_segments"] = int(manual.get("n_segments", 3))
    state["seg_types"]  = list(manual.get("seg_types", []))
    state["tolerance"]  = float(manual.get("tolerance", 0.5))

    sc = fit.get("start_constraint", {}) or {}
    state["start_pin"]     = bool(sc.get("pin", False))
    state["start_tangent"] = sc.get("tangent")   # None or [tx, ty]

    ec = fit.get("end_constraint", {}) or {}
    state["end_pin"]     = bool(ec.get("pin", False))
    state["end_tangent"] = ec.get("tangent")

    # ---- 結果（参照用） ----
    res = doc.get("results", {}) or {}
    state["variance"]         = res.get("variance")
    state["composite"]        = res.get("composite")
    state["result_n_segments"] = res.get("n_segments")
    state["converged"]        = res.get("converged")
    state["message"]          = res.get("message", "")

    return state


# ============================================================
# 動作確認用
# ============================================================

if __name__ == "__main__":
    import tempfile, json

    sample = {
        "source_path":       "/data/shape.csv",
        "min_dist":          0.1,
        "start_point_coord": [1.23456789, -0.98765432],
        "excluded_coords":   [[2.0, 3.0], [5.5, 1.1]],
        "fit_mode":          "auto",
        "alpha":             0.1,
        "threshold":         0.005,
        "type_policy":       "auto",
        "max_segments":      10,
        "max_iter":          8,
        "tol_type":          0.3,
        "n_segments":        3,
        "seg_types":         ["line", "arc", "line"],
        "tolerance":         0.5,
        "start_pin":         True,
        "start_tangent":     [1.0, 0.0],
        "end_pin":           False,
        "end_tangent":       None,
        "seg_colors":        ["#e6194b", "#3cb44b", "#4363d8"],
        "variance":          0.00122,
        "composite":         0.00183,
        "result_n_segments": 3,
        "converged":         True,
        "message":           "収束: セグメント数 3 で達成",
    }

    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False,
                                     mode="w") as f:
        tmp = f.name

    save_session(tmp, sample)
    print("--- 保存された YAML ---")
    print(Path(tmp).read_text(encoding="utf-8"))

    restored = load_session(tmp)
    print("--- 復元された state ---")
    for k, v in restored.items():
        print(f"  {k}: {v}")

    # ラウンドトリップ確認
    assert restored["source_path"]       == sample["source_path"]
    assert restored["start_point_coord"] == sample["start_point_coord"]
    assert restored["excluded_coords"]   == sample["excluded_coords"]
    assert restored["start_pin"]         == sample["start_pin"]
    assert restored["start_tangent"]     == sample["start_tangent"]
    assert restored["end_tangent"]       is None
    assert restored["converged"]         == sample["converged"]
    print("\n✓ ラウンドトリップ OK")
