"""Benchmark: arrowdantic vs to_pylist() + model_construct.

Both benchmarks start from the same pre-created RecordBatch.
Only the conversion path is measured (not batch creation).

Per Pitfall 4 from research: both paths must start from same
RecordBatch object to avoid apples-to-oranges comparison.
"""

from __future__ import annotations

import pyarrow as pa
from pydantic import BaseModel

from arrowdantic import ArrowModelConverter


class BenchModel(BaseModel):
    id: int
    name: str
    score: float
    active: bool


def make_batch(n: int) -> pa.RecordBatch:
    """Create a RecordBatch with n rows of mixed primitive types."""
    return pa.record_batch({
        "id": list(range(n)),
        "name": [f"item_{i}" for i in range(n)],
        "score": [float(i) * 0.1 for i in range(n)],
        "active": [i % 2 == 0 for i in range(n)],
    })


# --- arrowdantic path ---


def test_arrowdantic_100k(benchmark):
    """Benchmark arrowdantic conversion on 100k rows."""
    batch = make_batch(100_000)
    converter = ArrowModelConverter(BenchModel)
    result = benchmark(converter.convert, batch)
    assert len(result) == 100_000
    assert isinstance(result[0], BenchModel)


def test_arrowdantic_10k(benchmark):
    """Benchmark arrowdantic conversion on 10k rows."""
    batch = make_batch(10_000)
    converter = ArrowModelConverter(BenchModel)
    result = benchmark(converter.convert, batch)
    assert len(result) == 10_000


# --- baseline: to_pylist + model_construct ---


def test_baseline_to_pylist_100k(benchmark):
    """Benchmark to_pylist() + model_construct on 100k rows."""
    batch = make_batch(100_000)

    def baseline():
        return [BenchModel.model_construct(**row) for row in batch.to_pylist()]

    result = benchmark(baseline)
    assert len(result) == 100_000
    assert isinstance(result[0], BenchModel)


def test_baseline_to_pylist_10k(benchmark):
    """Benchmark to_pylist() + model_construct on 10k rows."""
    batch = make_batch(10_000)

    def baseline():
        return [BenchModel.model_construct(**row) for row in batch.to_pylist()]

    result = benchmark(baseline)
    assert len(result) == 10_000
