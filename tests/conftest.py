"""Shared pytest fixtures for arrowdantic test suite."""

from __future__ import annotations

import pyarrow as pa
import pytest


@pytest.fixture
def sample_record_batch() -> pa.RecordBatch:
    """A simple RecordBatch with int and string columns."""
    return pa.record_batch({"x": [1, 2, 3], "y": ["a", "b", "c"]})


@pytest.fixture
def int_batch() -> pa.RecordBatch:
    """RecordBatch with all signed integer types."""
    return pa.record_batch({
        "i8": pa.array([1, -1, 127], type=pa.int8()),
        "i16": pa.array([1, -1, 32767], type=pa.int16()),
        "i32": pa.array([1, -1, 2147483647], type=pa.int32()),
        "i64": pa.array([1, -1, 9223372036854775807], type=pa.int64()),
    })


@pytest.fixture
def uint_batch() -> pa.RecordBatch:
    """RecordBatch with all unsigned integer types."""
    return pa.record_batch({
        "u8": pa.array([0, 1, 255], type=pa.uint8()),
        "u16": pa.array([0, 1, 65535], type=pa.uint16()),
        "u32": pa.array([0, 1, 4294967295], type=pa.uint32()),
        "u64": pa.array([0, 1, 18446744073709551615], type=pa.uint64()),
    })


@pytest.fixture
def float_batch() -> pa.RecordBatch:
    """RecordBatch with float types."""
    return pa.record_batch({
        "f32": pa.array([1.5, -2.5, 0.0], type=pa.float32()),
        "f64": pa.array([1.5, -2.5, 0.0], type=pa.float64()),
    })


@pytest.fixture
def bool_batch() -> pa.RecordBatch:
    """RecordBatch with boolean type."""
    return pa.record_batch({
        "flag": pa.array([True, False, True]),
    })


@pytest.fixture
def string_batch() -> pa.RecordBatch:
    """RecordBatch with utf8 string type."""
    return pa.record_batch({
        "name": pa.array(["alice", "bob", "charlie"]),
    })


@pytest.fixture
def mixed_batch() -> pa.RecordBatch:
    """RecordBatch with mixed primitive types."""
    return pa.record_batch({
        "id": pa.array([1, 2, 3], type=pa.int64()),
        "name": pa.array(["alice", "bob", "charlie"]),
        "score": pa.array([9.5, 8.0, 7.5], type=pa.float64()),
        "active": pa.array([True, False, True]),
    })


@pytest.fixture
def nullable_batch() -> pa.RecordBatch:
    """RecordBatch with null values in some columns."""
    return pa.record_batch({
        "id": pa.array([1, 2, 3], type=pa.int64()),
        "name": pa.array(["alice", None, "charlie"]),
        "score": pa.array([9.5, None, 7.5], type=pa.float64()),
    })


@pytest.fixture
def all_null_batch() -> pa.RecordBatch:
    """RecordBatch where nullable columns are entirely null."""
    return pa.record_batch({
        "id": pa.array([1, 2], type=pa.int64()),
        "name": pa.array([None, None], type=pa.string()),
        "score": pa.array([None, None], type=pa.float64()),
    })
