"""Walk-forward chronological dataset splitting with purge windows to prevent financial data leakage."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple
from pydantic import BaseModel, Field


class SplitFold(BaseModel):
    """Represents a single walk-forward train/test split fold."""
    fold_id: int
    train_indices: List[int]
    test_indices: List[int]
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    purge_window_hours: float


class WalkForwardSplitter:
    """Partitions time-ordered financial observations into chronological walk-forward folds.
    
    Guarantees:
    1. Temporal Ordering: Train observations strictly precede test observations.
    2. Purge Window: An embargo period between train_end and test_start prevents label overlap
       or event horizon contamination.
    3. Zero Lookahead: No future information is accessible to the training partition.
    """

    def __init__(
        self,
        n_splits: int = 3,
        purge_window_hours: float = 24.0,
        min_train_fraction: float = 0.4,
    ):
        if n_splits < 1:
            raise ValueError("n_splits must be at least 1")
        if purge_window_hours < 0:
            raise ValueError("purge_window_hours cannot be negative")
        self.n_splits = n_splits
        self.purge_window = timedelta(hours=purge_window_hours)
        self.purge_window_hours = purge_window_hours
        self.min_train_fraction = min_train_fraction

    def split(
        self,
        records: Sequence[Dict[str, Any]],
        timestamp_key: str = "timestamp",
    ) -> List[SplitFold]:
        """Generate chronological train/test folds from records.
        
        Args:
            records: List of sample dictionaries containing timestamp_key.
            timestamp_key: Key name containing ISO-8601 or datetime timestamp.
            
        Returns:
            List of SplitFold objects.
        """
        n = len(records)
        if n < 4:
            raise ValueError(f"Need at least 4 records for walk-forward splitting, got {n}")

        # Parse and sort by timestamp
        parsed_items: List[Tuple[int, datetime, Dict[str, Any]]] = []
        for orig_idx, rec in enumerate(records):
            raw_ts = rec[timestamp_key]
            if isinstance(raw_ts, str):
                # Replace 'Z' with '+00:00' for standard fromisoformat
                cleaned = raw_ts.replace("Z", "+00:00")
                dt = datetime.fromisoformat(cleaned)
            elif isinstance(raw_ts, datetime):
                dt = raw_ts
            else:
                raise TypeError(f"Invalid timestamp type: {type(raw_ts)}")
            
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            parsed_items.append((orig_idx, dt, rec))

        # Strict sort by datetime
        parsed_items.sort(key=lambda x: x[1])

        # Verify monotonicity
        for i in range(1, len(parsed_items)):
            if parsed_items[i][1] < parsed_items[i - 1][1]:
                raise ValueError("Records could not be sorted strictly monotonically")

        folds: List[SplitFold] = []
        min_train_size = max(2, int(n * self.min_train_fraction))
        remaining = n - min_train_size

        if remaining <= 0:
            raise ValueError(f"Insufficient samples ({n}) for min_train_fraction ({self.min_train_fraction})")

        # Step size for expanding train window
        test_chunk_size = max(1, remaining // self.n_splits)

        for fold_idx in range(self.n_splits):
            train_cutoff_idx = min_train_size + (fold_idx * test_chunk_size)
            test_start_target_idx = train_cutoff_idx
            test_end_target_idx = min(n, train_cutoff_idx + test_chunk_size) if fold_idx < self.n_splits - 1 else n

            train_items = parsed_items[:train_cutoff_idx]
            train_end_dt = train_items[-1][1]
            train_start_dt = train_items[0][1]

            # Enforce purge window: test records must be at least train_end_dt + purge_window
            eligible_test_items = [
                item for item in parsed_items[test_start_target_idx:test_end_target_idx]
                if item[1] >= (train_end_dt + self.purge_window)
            ]

            if not eligible_test_items:
                # If purge window filtered all records in this chunk, expand forward
                eligible_test_items = [
                    item for item in parsed_items[test_start_target_idx:]
                    if item[1] >= (train_end_dt + self.purge_window)
                ][:test_chunk_size]

            if not eligible_test_items:
                continue

            test_indices = [item[0] for item in eligible_test_items]
            train_indices = [item[0] for item in train_items]

            folds.append(SplitFold(
                fold_id=fold_idx + 1,
                train_indices=train_indices,
                test_indices=test_indices,
                train_start=train_start_dt,
                train_end=train_end_dt,
                test_start=eligible_test_items[0][1],
                test_end=eligible_test_items[-1][1],
                purge_window_hours=self.purge_window_hours,
            ))

        return folds
