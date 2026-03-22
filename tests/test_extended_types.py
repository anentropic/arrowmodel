"""Tests for Phase 6: Extended Arrow type support.

Covers requirement IDs:
- EXT-FLOAT16: Float16 -> float
- EXT-DEC128: Decimal128 -> Decimal
- EXT-DEC256: Decimal256 -> Decimal
- EXT-DEC32: Decimal32 -> Decimal
- EXT-DEC64: Decimal64 -> Decimal
- EXT-DATE64: Date64 -> datetime
- EXT-TIME32: Time32 -> time
- EXT-TIME64: Time64 -> time
- EXT-BINARY: Binary/LargeBinary -> bytes
- EXT-FSBINARY: FixedSizeBinary -> bytes
- EXT-UTF8VIEW: Utf8View -> str
- EXT-BINVIEW: BinaryView -> bytes
"""

from __future__ import annotations

import datetime
import decimal

import pyarrow as pa
import pytest
from pydantic import BaseModel

from arrowdantic import ArrowModelConverter


# ---------------------------------------------------------------------------
# Pydantic models for extended types
# ---------------------------------------------------------------------------


class Float16Model(BaseModel):
    val: float | None = None


class DecimalModel(BaseModel):
    amount: decimal.Decimal | None = None


class Decimal256Model(BaseModel):
    big_amount: decimal.Decimal | None = None


class DateTimeModel(BaseModel):
    ts: datetime.datetime | None = None


class TimeModel(BaseModel):
    t: datetime.time | None = None


class BinaryModel(BaseModel):
    data: bytes | None = None


class FixedBinaryModel(BaseModel):
    hash: bytes | None = None


class NameModel(BaseModel):
    name: str | None = None


# ---------------------------------------------------------------------------
# Float16 tests
# ---------------------------------------------------------------------------


class TestFloat16:
    def test_float16_value(self, float16_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(Float16Model)
        results = converter.convert(float16_batch)
        assert len(results) == 3
        assert isinstance(results[0].val, float)
        assert results[0].val == pytest.approx(1.5, abs=0.01)
        assert isinstance(results[2].val, float)
        assert results[2].val == pytest.approx(-2.5, abs=0.01)

    def test_float16_null(self, float16_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(Float16Model)
        results = converter.convert(float16_batch)
        assert results[1].val is None


# ---------------------------------------------------------------------------
# Decimal128 tests
# ---------------------------------------------------------------------------


class TestDecimal128:
    def test_decimal128_value(self, decimal128_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(DecimalModel)
        results = converter.convert(decimal128_batch)
        assert len(results) == 3
        assert isinstance(results[0].amount, decimal.Decimal)
        assert results[0].amount == decimal.Decimal("12345.6789")
        assert results[2].amount == decimal.Decimal("-99999.9999")

    def test_decimal128_null(self, decimal128_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(DecimalModel)
        results = converter.convert(decimal128_batch)
        assert results[1].amount is None

    def test_decimal128_precision(self) -> None:
        """Verify full 38-digit precision is preserved (no float truncation)."""
        val = decimal.Decimal("12345678901234567890.123456789012345678")
        batch = pa.record_batch(
            {
                "amount": pa.array([val], type=pa.decimal128(38, 18)),
            }
        )
        converter = ArrowModelConverter(DecimalModel)
        results = converter.convert(batch)
        assert results[0].amount == val


# ---------------------------------------------------------------------------
# Decimal256 tests
# ---------------------------------------------------------------------------


class TestDecimal256:
    def test_decimal256_value(self, decimal256_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(Decimal256Model)
        results = converter.convert(decimal256_batch)
        assert len(results) == 2
        assert isinstance(results[0].big_amount, decimal.Decimal)
        assert results[0].big_amount == decimal.Decimal(
            "123456789012345678901234567890.12345678"
        )

    def test_decimal256_null(self, decimal256_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(Decimal256Model)
        results = converter.convert(decimal256_batch)
        assert results[1].big_amount is None


# ---------------------------------------------------------------------------
# Date64 tests
# ---------------------------------------------------------------------------


class TestDate64:
    def test_date64_to_datetime(self, date64_batch: pa.RecordBatch) -> None:
        """Date64 should produce datetime.datetime (not datetime.date)."""
        converter = ArrowModelConverter(DateTimeModel)
        results = converter.convert(date64_batch)
        assert len(results) == 3
        assert isinstance(results[0].ts, datetime.datetime)
        # Not just a date -- has time component
        assert not isinstance(results[0].ts, datetime.date) or isinstance(
            results[0].ts, datetime.datetime
        )
        # 1705312200000 ms since epoch = 2024-01-15 09:50:00 UTC
        assert results[0].ts == datetime.datetime(2024, 1, 15, 9, 50, 0)

    def test_date64_null(self, date64_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(DateTimeModel)
        results = converter.convert(date64_batch)
        assert results[1].ts is None

    def test_date64_epoch_zero(self, date64_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(DateTimeModel)
        results = converter.convert(date64_batch)
        assert results[2].ts == datetime.datetime(1970, 1, 1, 0, 0, 0)


# ---------------------------------------------------------------------------
# Time32 tests
# ---------------------------------------------------------------------------


class TestTime32:
    def test_time32_second(self, time32_second_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(TimeModel)
        results = converter.convert(time32_second_batch)
        assert results[0].t == datetime.time(10, 30, 0)
        assert results[2].t == datetime.time(0, 0, 0)

    def test_time32_millisecond(self, time32_ms_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(TimeModel)
        results = converter.convert(time32_ms_batch)
        assert results[0].t == datetime.time(10, 30, 0, 500000)
        assert results[2].t == datetime.time(0, 0, 0)

    def test_time32_null(self, time32_second_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(TimeModel)
        results = converter.convert(time32_second_batch)
        assert results[1].t is None


# ---------------------------------------------------------------------------
# Time64 tests
# ---------------------------------------------------------------------------


class TestTime64:
    def test_time64_microsecond(self, time64_us_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(TimeModel)
        results = converter.convert(time64_us_batch)
        assert results[0].t == datetime.time(10, 30, 0, 500123)
        assert results[2].t == datetime.time(0, 0, 0)

    def test_time64_nanosecond_truncation(
        self, time64_ns_batch: pa.RecordBatch
    ) -> None:
        """Time64(ns) should truncate nanoseconds to microseconds."""
        converter = ArrowModelConverter(TimeModel)
        results = converter.convert(time64_ns_batch)
        # 37800500123456 ns -> 37800500123 us (truncate, not round)
        # = 10:30:00.500123
        assert results[0].t == datetime.time(10, 30, 0, 500123)
        assert results[2].t == datetime.time(0, 0, 0)

    def test_time64_null(self, time64_us_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(TimeModel)
        results = converter.convert(time64_us_batch)
        assert results[1].t is None


# ---------------------------------------------------------------------------
# Binary tests
# ---------------------------------------------------------------------------


class TestBinary:
    def test_binary_value(self, binary_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(BinaryModel)
        results = converter.convert(binary_batch)
        assert isinstance(results[0].data, bytes)
        assert results[0].data == b"\x00\x01\x02"
        assert results[2].data == b"\xff"

    def test_binary_null(self, binary_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(BinaryModel)
        results = converter.convert(binary_batch)
        assert results[1].data is None

    def test_large_binary_value(self, large_binary_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(BinaryModel)
        results = converter.convert(large_binary_batch)
        assert isinstance(results[0].data, bytes)
        assert results[0].data == b"hello"
        assert results[2].data == b"world"


# ---------------------------------------------------------------------------
# FixedSizeBinary tests
# ---------------------------------------------------------------------------


class TestFixedSizeBinary:
    def test_fixed_size_binary_value(
        self, fixed_size_binary_batch: pa.RecordBatch
    ) -> None:
        converter = ArrowModelConverter(FixedBinaryModel)
        results = converter.convert(fixed_size_binary_batch)
        assert isinstance(results[0].hash, bytes)
        assert results[0].hash == b"\x01\x02\x03\x04"
        assert len(results[0].hash) == 4
        assert results[2].hash == b"\xaa\xbb\xcc\xdd"

    def test_fixed_size_binary_null(
        self, fixed_size_binary_batch: pa.RecordBatch
    ) -> None:
        converter = ArrowModelConverter(FixedBinaryModel)
        results = converter.convert(fixed_size_binary_batch)
        assert results[1].hash is None


# ---------------------------------------------------------------------------
# Utf8View tests
# ---------------------------------------------------------------------------


class TestUtf8View:
    def test_utf8view_value(self, utf8view_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(NameModel)
        results = converter.convert(utf8view_batch)
        assert isinstance(results[0].name, str)
        assert results[0].name == "hello_world_test"
        assert results[2].name == "world_hello_test"

    def test_utf8view_null(self, utf8view_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(NameModel)
        results = converter.convert(utf8view_batch)
        assert results[1].name is None


# ---------------------------------------------------------------------------
# BinaryView tests
# ---------------------------------------------------------------------------


class TestBinaryView:
    def test_binaryview_value(self, binaryview_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(BinaryModel)
        results = converter.convert(binaryview_batch)
        assert isinstance(results[0].data, bytes)
        assert results[0].data == b"abc_data_padding!"
        assert results[2].data == b"xyz_data_padding!"

    def test_binaryview_null(self, binaryview_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(BinaryModel)
        results = converter.convert(binaryview_batch)
        assert results[1].data is None


# ---------------------------------------------------------------------------
# Validated path tests for all new types
# ---------------------------------------------------------------------------


class TestValidatedScalarTypes:
    def test_float16_validated(self, float16_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(Float16Model, validate=True)
        results = converter.convert(float16_batch)
        assert results[0].val == pytest.approx(1.5, abs=0.01)
        assert results[1].val is None

    def test_decimal128_validated(self, decimal128_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(DecimalModel, validate=True)
        results = converter.convert(decimal128_batch)
        assert results[0].amount == decimal.Decimal("12345.6789")
        assert results[1].amount is None

    def test_date64_validated(self, date64_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(DateTimeModel, validate=True)
        results = converter.convert(date64_batch)
        # 1705312200000 ms since epoch = 2024-01-15 09:50:00 UTC
        assert results[0].ts == datetime.datetime(2024, 1, 15, 9, 50, 0)
        assert results[1].ts is None

    def test_time32_validated(self, time32_second_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(TimeModel, validate=True)
        results = converter.convert(time32_second_batch)
        assert results[0].t == datetime.time(10, 30, 0)
        assert results[1].t is None

    def test_binary_validated(self, binary_batch: pa.RecordBatch) -> None:
        """Validated path sends base64-encoded binary in JSON.
        Pydantic treats JSON string as UTF-8 bytes, not base64-decoded.
        So the result is the base64 string encoded as bytes.
        """
        import base64

        converter = ArrowModelConverter(BinaryModel, validate=True)
        results = converter.convert(binary_batch)
        expected = base64.b64encode(b"\x00\x01\x02")
        assert results[0].data == expected
        assert results[1].data is None

    def test_utf8view_validated(self, utf8view_batch: pa.RecordBatch) -> None:
        converter = ArrowModelConverter(NameModel, validate=True)
        results = converter.convert(utf8view_batch)
        assert results[0].name == "hello_world_test"
        assert results[1].name is None
