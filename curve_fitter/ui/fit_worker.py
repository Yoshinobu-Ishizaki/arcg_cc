"""
FitWorker — バックグラウンドスレッドでフィットを実行する QObject ワーカー。
"""
from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from ..core.fitter import SegmentFitter, EndpointConstraint


class FitWorker(QObject):
    # 手動フィット成功: (segments, variance, n_seg, composite)
    manual_finished = pyqtSignal(object, float, int, float)
    # 自動フィット成功: (FitResult, composite)
    auto_finished   = pyqtSignal(object, float)
    # エラー発生
    error           = pyqtSignal(str)
    # 常に最後に emit される（スレッドクリーンアップ用）
    finished        = pyqtSignal()

    def __init__(
        self,
        fitter: SegmentFitter,
        state:  dict,
        alpha:  float,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._fitter = fitter
        self._state  = state
        self._alpha  = alpha

    @staticmethod
    def _make_constraint(pin: bool, tangent) -> EndpointConstraint:
        t = np.asarray(tangent) if tangent is not None else None
        return EndpointConstraint(pin=pin, tangent=t)

    def run(self) -> None:
        try:
            if self._state["fit_mode"] == "manual":
                self._run_manual()
            else:
                self._run_auto()
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    def _run_manual(self) -> None:
        state = self._state
        n_seg = state["n_segments"]
        sc = self._make_constraint(state["start_pin"], state["start_tangent"])
        ec = self._make_constraint(state["end_pin"],   state["end_tangent"])
        segs = self._fitter.fit(
            n_segments=n_seg,
            seg_types=state["seg_types"],
            tolerance=state["tolerance"],
            start_constraint=sc,
            end_constraint=ec,
        )
        variance  = self._fitter.variance_score(segs)
        composite = variance * (1.0 + self._alpha * n_seg)
        self.manual_finished.emit(segs, variance, n_seg, composite)

    def _run_auto(self) -> None:
        state = self._state
        sc = self._make_constraint(state["start_pin"], state["start_tangent"])
        ec = self._make_constraint(state["end_pin"],   state["end_tangent"])
        result = self._fitter.fit_auto(
            threshold=state["threshold"],
            type_policy=state["type_policy"],
            max_segments=state["max_segments"],
            max_iter=state["max_iter"],
            tol_type=state["tol_type"],
            start_constraint=sc,
            end_constraint=ec,
        )
        composite = result.score * (1.0 + self._alpha * result.n_segments)
        self.auto_finished.emit(result, composite)
