"""QN Quantitative Manipulation Model & Inference Engine (Phase 6).

Implements:
1. Trainable QN Quantitative Manipulation Model with class-weight balancing,
   probability calibration, checkpointing, and artifact versioning.
2. Thread-safe, singleton QNManipulationInference engine for real-time stock surveillance.
3. Feature factor attribution and explainability.
4. Concurrency guards protecting against accidental duplicate training runs.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier

from .dataset_builder import dataset_builder, load_ticker_ohlcv
from .evaluation import EvaluationReport, evaluate_predictions
from .features import FEATURE_COLUMNS, compute_window_features
from .universe import surveillance_universe

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
MODELS_DIR = BASE_DIR / "data" / "models"
MODEL_ARTIFACT_PATH = MODELS_DIR / "qn_manipulation_v1.joblib"
MODEL_META_PATH = MODELS_DIR / "qn_manipulation_v1.meta.json"

_TRAINING_LOCK = threading.Lock()
_INFERENCE_LOCK = threading.Lock()
_IS_TRAINING = False
_LAST_TRAINING_ERROR: Optional[str] = None


@dataclass
class QNPrediction:
    ticker: str
    as_of_date: str
    model_score: float  # 0 to 100
    manipulation_probability: float  # 0.0 to 1.0
    risk_band: str  # 'Low', 'Elevated', 'High'
    confidence: float
    margin: float
    contributing_factors: Dict[str, float]
    top_factor_reasons: List[str]
    model_version: str
    is_real_model: bool
    data_freshness: str
    latency_ms: float
    effective_threshold: float = 0.012
    alert_triggered: bool = False
    disclaimer: str = (
        "QN score is an algorithmic surveillance risk indicator based on statistical market anomalies. "
        "It does not constitute a legal or regulatory finding of market manipulation."
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class QNManipulationModel:
    """Trains and serializes the QN Quantitative Manipulation Model."""

    def __init__(self, random_state: int = 42):
        self.random_state = random_state
        self.pipeline: Optional[Any] = None
        self.imputer: Optional[Any] = None
        self.scaler: Optional[Any] = None
        self.feature_importances: Dict[str, float] = {}

    def train(self) -> Tuple[EvaluationReport, EvaluationReport, Dict[str, Any]]:
        """Train QN model with validation-based calibration and holdout evaluation."""
        global _IS_TRAINING
        with _TRAINING_LOCK:
            _IS_TRAINING = True
            try:
                MODELS_DIR.mkdir(parents=True, exist_ok=True)
                start_time = time.perf_counter()
                logger.info("Loading processed walk-forward splits for QN training...")

                train_df, val_df, test_df, imputer, scaler = dataset_builder.load_processed_splits()
                self.imputer = imputer
                self.scaler = scaler

                X_train = train_df[FEATURE_COLUMNS].values
                y_train = train_df["target_binary"].values

                X_val = val_df[FEATURE_COLUMNS].values
                y_val = val_df["target_binary"].values

                X_test = test_df[FEATURE_COLUMNS].values
                y_test = test_df["target_binary"].values

                logger.info(
                    "Training QN Base Estimator on %d samples (pos: %d, neg: %d)...",
                    len(train_df),
                    int(y_train.sum()),
                    len(train_df) - int(y_train.sum()),
                )

                # Base model: Balanced Random Forest with constrained tree depth
                base_clf = RandomForestClassifier(
                    n_estimators=120,
                    max_depth=6,
                    min_samples_split=6,
                    min_samples_leaf=3,
                    class_weight="balanced",
                    random_state=self.random_state,
                    n_jobs=-1,
                )
                base_clf.fit(X_train, y_train)

                # Calibrate probabilities using group-isolated cross-validation
                # to strictly eliminate event and ticker leakage inside calibration folds
                from sklearn.model_selection import StratifiedGroupKFold
                sgkf = StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=self.random_state)
                cv_splits = list(sgkf.split(X_train, y_train, groups=train_df["ticker"].values))

                calibrated_clf = CalibratedClassifierCV(estimator=base_clf, method="sigmoid", cv=cv_splits)
                calibrated_clf.fit(X_train, y_train)
                self.pipeline = calibrated_clf

                # Extract feature importances from base estimator
                raw_importances = base_clf.feature_importances_
                total_imp = float(np.sum(raw_importances)) + 1e-9
                self.feature_importances = {
                    col: round(float(imp / total_imp), 4)
                    for col, imp in zip(FEATURE_COLUMNS, raw_importances)
                }

                # Validation split evaluation & operating threshold policy selection
                # Policy: False-positive workload control on validation split (max alert rate <= 2.5%)
                val_probs = calibrated_clf.predict_proba(X_val)[:, 1]
                val_report_initial = evaluate_predictions(y_val, val_probs, split_name="val")

                best_op_th = 0.012
                best_val_f1 = -1.0
                for th_str, metrics in val_report_initial.threshold_metrics.items():
                    th_flt = float(th_str)
                    total_alerts = metrics["true_positives"] + metrics["false_positives"]
                    alert_rate = total_alerts / len(val_df) if len(val_df) else 0.0
                    if alert_rate <= 0.025 and metrics["f1"] > best_val_f1 and metrics["recall"] > 0:
                        best_val_f1 = metrics["f1"]
                        best_op_th = th_flt

                if best_val_f1 <= 0.0:
                    best_op_th = 0.012

                logger.info(
                    "Selected operating threshold from validation split policy: %.3f (Validation F1: %.4f)",
                    best_op_th,
                    best_val_f1,
                )

                # Re-evaluate validation report with selected operating threshold
                val_report = evaluate_predictions(
                    y_val, val_probs, split_name="val", default_threshold=0.50, operating_threshold=best_op_th
                )

                # Holdout test split evaluation with strictly untouched data using validation-selected threshold
                test_probs = calibrated_clf.predict_proba(X_test)[:, 1]
                test_report = evaluate_predictions(
                    y_test, test_probs, split_name="test", default_threshold=0.50, operating_threshold=best_op_th
                )

                elapsed_seconds = round(time.perf_counter() - start_time, 2)

                # Checkpoint model and preprocessing bundle
                artifact_bundle = {
                    "model": calibrated_clf,
                    "imputer": self.imputer,
                    "scaler": self.scaler,
                    "feature_columns": FEATURE_COLUMNS,
                    "feature_importances": self.feature_importances,
                    "operating_threshold": best_op_th,
                    "version": "1.0.0",
                }
                joblib.dump(artifact_bundle, MODEL_ARTIFACT_PATH)

                # Metadata record
                metadata = {
                    "model_version": "1.0.0",
                    "model_family": "QN-Quantitative-Manipulation-Detector",
                    "architecture": "CalibratedClassifierCV(RandomForestClassifier(class_weight='balanced'))",
                    "trained_at": datetime.now(timezone.utc).isoformat(),
                    "training_duration_seconds": elapsed_seconds,
                    "feature_columns": FEATURE_COLUMNS,
                    "feature_importances": self.feature_importances,
                    "operating_threshold": best_op_th,
                    "train_samples": len(train_df),
                    "val_samples": len(val_df),
                    "test_samples": len(test_df),
                    "validation_metrics": val_report.to_dict(),
                    "holdout_test_metrics": test_report.to_dict(),
                    "artifact_path": str(MODEL_ARTIFACT_PATH),
                }
                MODEL_META_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
                logger.info("QN model successfully trained and serialized to %s", MODEL_ARTIFACT_PATH)

                return val_report, test_report, metadata
            except Exception as e:
                global _LAST_TRAINING_ERROR
                _LAST_TRAINING_ERROR = str(e)
                raise
            finally:
                _IS_TRAINING = False


class QNManipulationInference:
    """Thread-safe inference service for QN Quantitative Manipulation Model."""

    def __init__(self):
        self._bundle: Optional[Dict[str, Any]] = None
        self._metadata: Optional[Dict[str, Any]] = None
        self._last_loaded: float = 0.0
        self._load()

    def _load(self) -> None:
        if MODEL_ARTIFACT_PATH.exists():
            try:
                self._bundle = joblib.load(MODEL_ARTIFACT_PATH)
                if MODEL_META_PATH.exists():
                    self._metadata = json.loads(MODEL_META_PATH.read_text(encoding="utf-8"))
                self._last_loaded = time.time()
                logger.info("Loaded active QN manipulation model v%s", self._bundle.get("version", "1.0.0"))
            except Exception as e:
                logger.warning("Could not load QN model artifact %s: %s", MODEL_ARTIFACT_PATH, e)
                self._bundle = None

    def is_model_available(self) -> bool:
        return self._bundle is not None and "model" in self._bundle

    def get_metadata(self) -> Dict[str, Any]:
        global _IS_TRAINING, _LAST_TRAINING_ERROR
        base = dict(self._metadata) if self._metadata else {
            "model_version": "unavailable",
            "model_family": "QN-Quantitative-Manipulation-Detector",
            "status": "NOT_TRAINED",
        }
        base["is_training"] = _IS_TRAINING
        base["last_training_error"] = _LAST_TRAINING_ERROR
        return base

    def analyze_ticker(
        self,
        ticker: str,
        as_of_date: Optional[str] = None,
        custom_df: Optional[pd.DataFrame] = None,
    ) -> QNPrediction:
        """Run point-in-time quantitative manipulation inference on a stock."""
        clean_t = ticker.upper().strip()
        as_of = as_of_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start = time.perf_counter()

        df = custom_df if custom_df is not None else load_ticker_ohlcv(clean_t)
        raw_feats = compute_window_features(df, as_of_date=as_of)

        with _INFERENCE_LOCK:
            if not self.is_model_available():
                # Fallback to calibrated deterministic heuristic if artifact is not yet trained
                latency = round((time.perf_counter() - start) * 1000.0, 1)
                prob = self._heuristic_fallback_score(raw_feats, clean_t)
                score = round(prob * 100.0, 1)
                op_th = 0.012
                alert_trig = bool(prob >= op_th)
                band = "High" if score >= 70 else ("Elevated" if alert_trig else "Low")
                factors, reasons = self._explain_factors(raw_feats)
                return QNPrediction(
                    ticker=clean_t,
                    as_of_date=as_of,
                    model_score=score,
                    manipulation_probability=round(prob, 4),
                    risk_band=band,
                    confidence=round(max(prob, 1.0 - prob), 4),
                    margin=round(abs(prob - 0.5) * 2.0, 4),
                    contributing_factors=factors,
                    top_factor_reasons=reasons,
                    model_version="QN-heuristic-v0.9",
                    is_real_model=False,
                    data_freshness="SYNTHETIC_FALLBACK",
                    latency_ms=latency,
                    effective_threshold=op_th,
                    alert_triggered=alert_trig,
                )

            # Real model forward pass
            imputer = self._bundle["imputer"]
            scaler = self._bundle["scaler"]
            model = self._bundle["model"]
            feat_cols = self._bundle.get("feature_columns", FEATURE_COLUMNS)

            feat_df = pd.DataFrame([[raw_feats.get(c, 0.0) for c in feat_cols]], columns=feat_cols)
            feat_imputed = imputer.transform(feat_df)
            feat_scaled = scaler.transform(feat_imputed)

            probs = model.predict_proba(feat_scaled)[0]
            prob = float(probs[1])
            op_th = float(self._bundle.get("operating_threshold", 0.012))
            alert_trig = bool(prob >= op_th)
            # Model score (0-100) scaled to market baseline anomaly density (base rate ~0.51%)
            score = round(min(100.0, max(0.0, (prob / 0.020) * 100.0)), 1)
            band = "High" if prob >= 0.015 else ("Elevated" if alert_trig else "Low")

            factors, reasons = self._explain_factors(raw_feats)
            latency = round((time.perf_counter() - start) * 1000.0, 2)

            return QNPrediction(
                ticker=clean_t,
                as_of_date=as_of,
                model_score=score,
                manipulation_probability=round(prob, 4),
                risk_band=band,
                confidence=round(max(prob, 1.0 - prob), 4),
                margin=round(abs(prob - 0.5) * 2.0, 4),
                contributing_factors=factors,
                top_factor_reasons=reasons,
                model_version=f"QN-v{self._bundle.get('version', '1.0.0')}",
                is_real_model=True,
                data_freshness="LIVE_CACHE",
                latency_ms=latency,
                effective_threshold=op_th,
                alert_triggered=alert_trig,
            )

    def _heuristic_fallback_score(self, feats: Dict[str, float], ticker: str) -> float:
        """Deterministic baseline scoring if trained weights are not loaded."""
        prob = 0.05
        # Volume burst
        if feats.get("volume_zscore_20d", 0.0) > 3.0:
            prob += 0.25
        elif feats.get("volume_zscore_20d", 0.0) > 2.0:
            prob += 0.15

        # Upper circuits
        if feats.get("upper_circuit_count_20d", 0.0) >= 3.0:
            prob += 0.30
        elif feats.get("upper_circuit_count_20d", 0.0) >= 1.0:
            prob += 0.15

        # Price-volume divergence
        if feats.get("price_volume_corr_20d", 0.0) < -0.3:
            prob += 0.15

        # 60d rapid return
        if feats.get("return_60d", 0.0) > 1.0:
            prob += 0.20

        return min(0.95, prob)

    def _explain_factors(self, feats: Dict[str, float]) -> Tuple[Dict[str, float], List[str]]:
        """Compute interpretable factor contributions for the prediction."""
        factors: Dict[str, float] = {}
        reasons: List[str] = []

        # 1. Abnormal volume surge
        vz = feats.get("volume_zscore_20d", 0.0)
        factors["abnormal_volume"] = round(min(1.0, max(0.0, vz / 4.0)), 2)
        if vz >= 2.5:
            reasons.append(f"Statistically anomalous 20-day volume surge (z-score: +{vz:.2f}σ)")

        # 2. Circuit locking intensity
        uc = feats.get("upper_circuit_count_20d", 0.0)
        factors["circuit_lock_intensity"] = round(min(1.0, uc / 4.0), 2)
        if uc >= 2.0:
            reasons.append(f"Frequent upper circuit locks detected ({int(uc)} sessions in 20-day window)")

        # 3. Price-Volume divergence
        pv_corr = feats.get("price_volume_corr_20d", 0.0)
        factors["price_volume_divergence"] = round(min(1.0, max(0.0, -pv_corr)), 2)
        if pv_corr <= -0.25:
            reasons.append(f"Negative price-volume divergence (correlation: {pv_corr:.2f}) indicates exit dumping")

        # 4. Volatility anomaly
        v_rat = feats.get("volatility_ratio_5d_20d", 1.0)
        factors["volatility_expansion"] = round(min(1.0, max(0.0, (v_rat - 1.0) / 2.0)), 2)
        if v_rat >= 1.8:
            reasons.append(f"Short-term volatility spike expanding at {v_rat:.1f}x baseline rate")

        # 5. Price momentum
        r60 = feats.get("return_60d", 0.0)
        factors["price_velocity"] = round(min(1.0, max(0.0, r60 / 1.5)), 2)
        if r60 >= 0.80:
            reasons.append(f"Extreme 60-day price ramp (+{r60*100:.1f}%) disproportionate to broad sector")

        if not reasons:
            reasons.append("Trading telemetry aligns with normal market microstructure baselines")

        return factors, reasons


def train_qn_model(random_state: int = 42) -> Tuple[EvaluationReport, EvaluationReport, Dict[str, Any]]:
    """Train and serialize the QN quantitative model."""
    trainer = QNManipulationModel(random_state=random_state)
    return trainer.train()


# Singleton inference engine
qn_inference = QNManipulationInference()

