"""Evaluation and benchmarking framework for JEV financial intelligence subsystem."""

from .metrics import ClassificationMetrics, compute_all_metrics
from .splits import WalkForwardSplitter, SplitFold
from .baselines import (
    MajorityClassBaseline,
    TfidfLogisticRegressionBaseline,
    FrontierReferenceBaseline,
)
from .benchmark import BenchmarkRunner, BenchmarkReport

__all__ = [
    "ClassificationMetrics",
    "compute_all_metrics",
    "WalkForwardSplitter",
    "SplitFold",
    "MajorityClassBaseline",
    "TfidfLogisticRegressionBaseline",
    "FrontierReferenceBaseline",
    "BenchmarkRunner",
    "BenchmarkReport",
]
