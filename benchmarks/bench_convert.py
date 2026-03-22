"""
Benchmark: arrowdantic vs to_pylist() + model_construct.

Both benchmarks start from the same pre-created RecordBatch.
Only the conversion path is measured (not batch creation).

Usage:
    uv run python benchmarks/bench_convert.py 50 100 250 500 1000
    uv run python benchmarks/bench_convert.py  # defaults: 1000 10000 100000
"""

from __future__ import annotations

import sys
import time

import pyarrow as pa
from pydantic import BaseModel

from arrowdantic import ArrowModelConverter

DEFAULT_SIZES = [1000, 10_000, 100_000]
ROUNDS = 500


# ---------------------------------------------------------------------------
# Flat benchmark models and data
# ---------------------------------------------------------------------------


class BenchModel(BaseModel):
    id: int
    name: str
    score: float
    active: bool


def make_batch(n: int) -> pa.RecordBatch:
    """Create a RecordBatch with n rows of mixed primitive types."""
    return pa.record_batch(
        {
            "id": list(range(n)),
            "name": [f"item_{i}" for i in range(n)],
            "score": [float(i) * 0.1 for i in range(n)],
            "active": [i % 2 == 0 for i in range(n)],
        }
    )


# ---------------------------------------------------------------------------
# Nested benchmark models (10-level deep structs with list fields)
# ---------------------------------------------------------------------------


class Level10(BaseModel):
    value: int
    label: str


class Level9(BaseModel):
    child: Level10 | None
    score: float


class Level8(BaseModel):
    child: Level9 | None
    tags: list[str] | None = None


class Level7(BaseModel):
    child: Level8 | None
    count: int


class Level6(BaseModel):
    child: Level7 | None
    active: bool


class Level5(BaseModel):
    child: Level6 | None
    name: str


class Level4(BaseModel):
    child: Level5 | None
    ids: list[int] | None = None


class Level3(BaseModel):
    child: Level4 | None
    ratio: float


class Level2(BaseModel):
    child: Level3 | None
    code: str


class Level1(BaseModel):
    child: Level2 | None
    timestamp: float


class NestedBenchModel(BaseModel):
    id: int
    name: str
    data: Level1 | None


def make_nested_batch(n: int) -> pa.RecordBatch:
    """Create a RecordBatch with n rows of 10-level nested structs + lists."""
    # Build struct arrays bottom-up
    # Level10: struct{value: int32, label: utf8}
    level10_arr = pa.StructArray.from_arrays(
        [
            pa.array([i for i in range(n)], type=pa.int32()),
            pa.array([f"val_{i}" for i in range(n)], type=pa.utf8()),
        ],
        names=["value", "label"],
    )

    # Level9: struct{child: Level10, score: float64}
    level9_arr = pa.StructArray.from_arrays(
        [
            level10_arr,
            pa.array([float(i) * 0.1 for i in range(n)], type=pa.float64()),
        ],
        names=["child", "score"],
    )

    # Level8: struct{child: Level9, tags: list(utf8)} -- 3 tags per row
    tags_arr = pa.array(
        [[f"t_{i}_0", f"t_{i}_1", f"t_{i}_2"] for i in range(n)],
        type=pa.list_(pa.utf8()),
    )
    level8_arr = pa.StructArray.from_arrays(
        [level9_arr, tags_arr],
        names=["child", "tags"],
    )

    # Level7: struct{child: Level8, count: int32}
    level7_arr = pa.StructArray.from_arrays(
        [
            level8_arr,
            pa.array([i * 10 for i in range(n)], type=pa.int32()),
        ],
        names=["child", "count"],
    )

    # Level6: struct{child: Level7, active: bool}
    level6_arr = pa.StructArray.from_arrays(
        [
            level7_arr,
            pa.array([i % 2 == 0 for i in range(n)], type=pa.bool_()),
        ],
        names=["child", "active"],
    )

    # Level5: struct{child: Level6, name: utf8}
    level5_arr = pa.StructArray.from_arrays(
        [
            level6_arr,
            pa.array([f"name_{i}" for i in range(n)], type=pa.utf8()),
        ],
        names=["child", "name"],
    )

    # Level4: struct{child: Level5, ids: list(int32)} -- 5 ids per row
    ids_arr = pa.array(
        [list(range(i, i + 5)) for i in range(n)],
        type=pa.list_(pa.int32()),
    )
    level4_arr = pa.StructArray.from_arrays(
        [level5_arr, ids_arr],
        names=["child", "ids"],
    )

    # Level3: struct{child: Level4, ratio: float64}
    level3_arr = pa.StructArray.from_arrays(
        [
            level4_arr,
            pa.array([float(i) * 1.5 for i in range(n)], type=pa.float64()),
        ],
        names=["child", "ratio"],
    )

    # Level2: struct{child: Level3, code: utf8}
    level2_arr = pa.StructArray.from_arrays(
        [
            level3_arr,
            pa.array([f"code_{i}" for i in range(n)], type=pa.utf8()),
        ],
        names=["child", "code"],
    )

    # Level1: struct{child: Level2, timestamp: float64}
    level1_arr = pa.StructArray.from_arrays(
        [
            level2_arr,
            pa.array([float(i) * 0.01 for i in range(n)], type=pa.float64()),
        ],
        names=["child", "timestamp"],
    )

    # Top level: int64 "id", utf8 "name", Level1 struct "data"
    return pa.record_batch(
        {
            "id": pa.array(list(range(n)), type=pa.int64()),
            "name": pa.array([f"item_{i}" for i in range(n)], type=pa.utf8()),
            "data": level1_arr,
        }
    )


# ---------------------------------------------------------------------------
# Benchmark runners
# ---------------------------------------------------------------------------


def _format_time(seconds: float) -> str:
    """Format a time duration as a human-readable string."""
    if seconds < 1e-3:
        return f"{seconds * 1e6:.0f} \u00b5s"
    return f"{seconds * 1e3:.1f} ms"


def _print_header() -> None:
    print(f"{'Rows':>8} | {'arrowdantic':>14} | {'to_pylist+mc':>14} | {'Speedup':>8}")
    print(f"{'-' * 8}-+-{'-' * 14}-+-{'-' * 14}-+-{'-' * 8}")


def run_benchmark(sizes: list[int]) -> None:
    _print_header()

    for n in sizes:
        batch = make_batch(n)
        converter = ArrowModelConverter(BenchModel)
        rounds = max(10, ROUNDS // max(1, n // 1000))

        # warmup
        converter.convert(batch)
        [BenchModel.model_construct(**row) for row in batch.to_pylist()]

        # arrowdantic
        t0 = time.perf_counter()
        for _ in range(rounds):
            converter.convert(batch)
        t_ad = (time.perf_counter() - t0) / rounds

        # baseline
        t0 = time.perf_counter()
        for _ in range(rounds):
            [BenchModel.model_construct(**row) for row in batch.to_pylist()]
        t_bl = (time.perf_counter() - t0) / rounds

        speedup = t_bl / t_ad
        print(f"{n:>8} | {_format_time(t_ad):>14} | {_format_time(t_bl):>14} | {speedup:>6.2f}x")


def run_nested_benchmark(sizes: list[int]) -> None:
    _print_header()

    for n in sizes:
        batch = make_nested_batch(n)
        converter = ArrowModelConverter(NestedBenchModel)
        rounds = max(10, ROUNDS // max(1, n // 1000))

        # warmup
        converter.convert(batch)
        [NestedBenchModel.model_construct(**row) for row in batch.to_pylist()]

        # arrowdantic
        t0 = time.perf_counter()
        for _ in range(rounds):
            converter.convert(batch)
        t_ad = (time.perf_counter() - t0) / rounds

        # baseline: model_construct only constructs top-level model (no recursive
        # construction of nested dicts). This is a known limitation -- the benchmark
        # still shows the cost difference of the full operation since in practice
        # users need the nested models too, which arrowdantic provides.
        t0 = time.perf_counter()
        for _ in range(rounds):
            [NestedBenchModel.model_construct(**row) for row in batch.to_pylist()]
        t_bl = (time.perf_counter() - t0) / rounds

        speedup = t_bl / t_ad
        print(f"{n:>8} | {_format_time(t_ad):>14} | {_format_time(t_bl):>14} | {speedup:>6.2f}x")


if __name__ == "__main__":
    sizes = [int(arg) for arg in sys.argv[1:]] if len(sys.argv) > 1 else DEFAULT_SIZES
    print("=== Flat Primitives ===\n")
    run_benchmark(sizes)
    print("\n=== Nested (10-level struct + lists) ===\n")
    run_nested_benchmark(sizes)
