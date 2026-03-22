"""Shared pytest fixtures for arrowdantic test suite."""

from __future__ import annotations

import datetime

import pyarrow as pa
import pytest


@pytest.fixture
def sample_record_batch() -> pa.RecordBatch:
    """A simple RecordBatch with int and string columns."""
    return pa.record_batch({"x": [1, 2, 3], "y": ["a", "b", "c"]})


@pytest.fixture
def int_batch() -> pa.RecordBatch:
    """RecordBatch with all signed integer types."""
    return pa.record_batch(
        {
            "i8": pa.array([1, -1, 127], type=pa.int8()),
            "i16": pa.array([1, -1, 32767], type=pa.int16()),
            "i32": pa.array([1, -1, 2147483647], type=pa.int32()),
            "i64": pa.array([1, -1, 9223372036854775807], type=pa.int64()),
        }
    )


@pytest.fixture
def uint_batch() -> pa.RecordBatch:
    """RecordBatch with all unsigned integer types."""
    return pa.record_batch(
        {
            "u8": pa.array([0, 1, 255], type=pa.uint8()),
            "u16": pa.array([0, 1, 65535], type=pa.uint16()),
            "u32": pa.array([0, 1, 4294967295], type=pa.uint32()),
            "u64": pa.array([0, 1, 18446744073709551615], type=pa.uint64()),
        }
    )


@pytest.fixture
def float_batch() -> pa.RecordBatch:
    """RecordBatch with float types."""
    return pa.record_batch(
        {
            "f32": pa.array([1.5, -2.5, 0.0], type=pa.float32()),
            "f64": pa.array([1.5, -2.5, 0.0], type=pa.float64()),
        }
    )


@pytest.fixture
def bool_batch() -> pa.RecordBatch:
    """RecordBatch with boolean type."""
    return pa.record_batch(
        {
            "flag": pa.array([True, False, True]),
        }
    )


@pytest.fixture
def string_batch() -> pa.RecordBatch:
    """RecordBatch with utf8 string type."""
    return pa.record_batch(
        {
            "name": pa.array(["alice", "bob", "charlie"]),
        }
    )


@pytest.fixture
def mixed_batch() -> pa.RecordBatch:
    """RecordBatch with mixed primitive types."""
    return pa.record_batch(
        {
            "id": pa.array([1, 2, 3], type=pa.int64()),
            "name": pa.array(["alice", "bob", "charlie"]),
            "score": pa.array([9.5, 8.0, 7.5], type=pa.float64()),
            "active": pa.array([True, False, True]),
        }
    )


@pytest.fixture
def nullable_batch() -> pa.RecordBatch:
    """RecordBatch with null values in some columns."""
    return pa.record_batch(
        {
            "id": pa.array([1, 2, 3], type=pa.int64()),
            "name": pa.array(["alice", None, "charlie"]),
            "score": pa.array([9.5, None, 7.5], type=pa.float64()),
        }
    )


@pytest.fixture
def all_null_batch() -> pa.RecordBatch:
    """RecordBatch where nullable columns are entirely null."""
    return pa.record_batch(
        {
            "id": pa.array([1, 2], type=pa.int64()),
            "name": pa.array([None, None], type=pa.string()),
            "score": pa.array([None, None], type=pa.float64()),
        }
    )


# ---------------------------------------------------------------------------
# Phase 4: Temporal, dictionary, and null type fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def date32_batch() -> pa.RecordBatch:
    """RecordBatch with Date32 column including a null."""
    return pa.record_batch(
        {
            "event_date": pa.array(
                [datetime.date(2024, 1, 15), None, datetime.date(2020, 6, 30)],
                type=pa.date32(),
            ),
        }
    )


@pytest.fixture
def timestamp_us_batch() -> pa.RecordBatch:
    """RecordBatch with microsecond-precision naive timestamp."""
    return pa.record_batch(
        {
            "created_at": pa.array(
                [
                    datetime.datetime(2024, 1, 15, 10, 30, 0, 123456),
                    None,
                    datetime.datetime(2020, 6, 30, 23, 59, 59, 999999),
                ],
                type=pa.timestamp("us"),
            ),
        }
    )


@pytest.fixture
def timestamp_ns_batch() -> pa.RecordBatch:
    """Nanosecond timestamp for TEMP-05 truncation test."""
    return pa.record_batch(
        {
            "created_at": pa.array(
                [1705312200123456789], type=pa.timestamp("ns")
            ),
        }
    )


@pytest.fixture
def timestamp_tz_batch() -> pa.RecordBatch:
    """RecordBatch with timezone-aware timestamp (America/New_York)."""
    return pa.record_batch(
        {
            "created_at": pa.array(
                [datetime.datetime(2024, 1, 15, 10, 30, 0)],
                type=pa.timestamp("us", tz="America/New_York"),
            ),
        }
    )


@pytest.fixture
def duration_batch() -> pa.RecordBatch:
    """RecordBatch with microsecond-precision duration column."""
    return pa.record_batch(
        {
            "elapsed": pa.array(
                [3600000000, None, 1000000], type=pa.duration("us")
            ),
        }
    )


@pytest.fixture
def dict_string_batch() -> pa.RecordBatch:
    """RecordBatch with dictionary-encoded string column."""
    return pa.record_batch(
        {
            "category": pa.array(["a", "b", "a"]).dictionary_encode(),
        }
    )


@pytest.fixture
def dict_int_batch() -> pa.RecordBatch:
    """RecordBatch with dictionary-encoded int column."""
    indices = pa.array([0, 1, 0], type=pa.int8())
    dictionary = pa.array([100, 200], type=pa.int64())
    return pa.record_batch(
        {
            "code": pa.DictionaryArray.from_arrays(indices, dictionary),
        }
    )


# ---------------------------------------------------------------------------
# Phase 4 Plan 2: List, LargeList, and Struct type fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def list_int_batch() -> pa.RecordBatch:
    """RecordBatch with List(Int64) column."""
    return pa.record_batch(
        {
            "values": pa.array(
                [[1, 2, 3], [4, 5], [6]], type=pa.list_(pa.int64())
            ),
        }
    )


@pytest.fixture
def list_str_batch() -> pa.RecordBatch:
    """RecordBatch with List(Utf8) column."""
    return pa.record_batch(
        {
            "tags": pa.array(
                [["a", "b"], ["c"]], type=pa.list_(pa.utf8())
            ),
        }
    )


@pytest.fixture
def struct_batch() -> pa.RecordBatch:
    """RecordBatch with a name column and a Struct(city, zip_code) column."""
    return pa.record_batch(
        {
            "name": pa.array(["Alice", "Bob"]),
            "address": pa.StructArray.from_arrays(
                [
                    pa.array(["NYC", "LA"]),
                    pa.array([10001, 90001], type=pa.int32()),
                ],
                names=["city", "zip_code"],
            ),
        }
    )
