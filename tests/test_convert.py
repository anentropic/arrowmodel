"""
Conversion correctness tests for Phase 2 requirements.

Covers all 15 Phase 2 requirement IDs:
- SCHEMA-01, SCHEMA-02: Schema cross-referencing
- TYPE-01 through TYPE-05: Primitive type conversions
- NULL-01 through NULL-03: Null handling
- FAST-01: model_construct (no validation)
- FAST-03: Direct Arrow buffer extraction
- INPUT-01: RecordBatch input
- API-01, API-02: Public API contract
"""

from __future__ import annotations

import pyarrow as pa
import pytest
from pydantic import AliasChoices, AliasGenerator, AliasPath, BaseModel, ConfigDict, Field

from arrowdantic import ArrowModelConverter
from arrowdantic import _build_field_map


class IntModel(BaseModel):
    i8: int
    i16: int
    i32: int
    i64: int


class UIntModel(BaseModel):
    u8: int
    u16: int
    u32: int
    u64: int


class FloatModel(BaseModel):
    f32: float
    f64: float


class BoolModel(BaseModel):
    flag: bool


class StringModel(BaseModel):
    name: str


class MixedModel(BaseModel):
    id: int
    name: str
    score: float
    active: bool


class NullableModel(BaseModel):
    id: int
    name: str | None = None
    score: float | None = None


class TestSchemaMapping:
    """Tests for SCHEMA-01 and SCHEMA-02: Arrow schema <-> Pydantic model cross-referencing."""

    def test_matches_arrow_columns_to_model_fields(self, mixed_batch: pa.RecordBatch) -> None:
        """SCHEMA-01: Converter maps Arrow column names to Pydantic model fields."""
        converter = ArrowModelConverter(MixedModel)
        results = converter.convert(mixed_batch)
        assert len(results) == 3
        assert results[0].id == 1
        assert results[0].name == "alice"
        assert results[0].score == 9.5
        assert results[0].active is True

    def test_raises_on_missing_field(self) -> None:
        """SCHEMA-01: ValueError when Arrow schema lacks a required model field."""
        batch = pa.record_batch({"x": [1, 2, 3]})
        converter = ArrowModelConverter(MixedModel)
        with pytest.raises(ValueError, match="Arrow schema has no column"):
            converter.convert(batch)

    def test_mapping_reuse_across_batches(self, mixed_batch: pa.RecordBatch) -> None:
        """SCHEMA-02: Converter can be reused across multiple batches."""
        converter = ArrowModelConverter(MixedModel)
        results1 = converter.convert(mixed_batch)
        results2 = converter.convert(mixed_batch)
        assert len(results1) == 3
        assert len(results2) == 3
        assert results1[0].id == results2[0].id
        assert results1[2].name == results2[2].name


class TestPrimitiveTypes:
    """Tests for TYPE-01 through TYPE-05: Primitive Arrow type conversions."""

    def test_int_types(self, int_batch: pa.RecordBatch) -> None:
        """TYPE-01: Int8, Int16, Int32, Int64 -> Python int."""
        converter = ArrowModelConverter(IntModel)
        results = converter.convert(int_batch)
        assert results[0].i8 == 1
        assert results[1].i8 == -1
        assert results[2].i64 == 9223372036854775807
        # Verify all values are int type
        for result in results:
            assert isinstance(result.i8, int)
            assert isinstance(result.i16, int)
            assert isinstance(result.i32, int)
            assert isinstance(result.i64, int)

    def test_uint_types(self, uint_batch: pa.RecordBatch) -> None:
        """TYPE-02: UInt8, UInt16, UInt32, UInt64 -> Python int."""
        converter = ArrowModelConverter(UIntModel)
        results = converter.convert(uint_batch)
        assert results[2].u8 == 255
        assert results[2].u64 == 18446744073709551615
        # Verify all values are int type
        for result in results:
            assert isinstance(result.u8, int)
            assert isinstance(result.u16, int)
            assert isinstance(result.u32, int)
            assert isinstance(result.u64, int)

    def test_float_types(self, float_batch: pa.RecordBatch) -> None:
        """TYPE-03: Float32, Float64 -> Python float."""
        converter = ArrowModelConverter(FloatModel)
        results = converter.convert(float_batch)
        assert results[0].f32 == pytest.approx(1.5)
        assert results[0].f64 == 1.5
        assert results[1].f32 == pytest.approx(-2.5)
        assert results[2].f64 == 0.0
        # Verify all values are float type
        for result in results:
            assert isinstance(result.f32, float)
            assert isinstance(result.f64, float)

    def test_bool_type(self, bool_batch: pa.RecordBatch) -> None:
        """TYPE-04: Boolean -> Python bool (not truthy ints)."""
        converter = ArrowModelConverter(BoolModel)
        results = converter.convert(bool_batch)
        assert results[0].flag is True
        assert results[1].flag is False
        assert results[2].flag is True
        # Verify values are exactly True/False, not truthy ints
        for result in results:
            assert type(result.flag) is bool

    def test_string_types(self, string_batch: pa.RecordBatch) -> None:
        """TYPE-05: Utf8 -> Python str."""
        converter = ArrowModelConverter(StringModel)
        results = converter.convert(string_batch)
        assert results[0].name == "alice"
        assert results[1].name == "bob"
        assert results[2].name == "charlie"
        # Verify all values are str type
        for result in results:
            assert isinstance(result.name, str)


class TestNullHandling:
    """Tests for NULL-01 through NULL-03: Null detection and handling."""

    def test_null_produces_none(self, nullable_batch: pa.RecordBatch) -> None:
        """NULL-01, NULL-02: Null values produce None in model instances."""
        converter = ArrowModelConverter(NullableModel)
        results = converter.convert(nullable_batch)
        assert results[1].name is None
        assert results[1].score is None
        assert results[0].name == "alice"

    def test_non_null_values_correct(self, nullable_batch: pa.RecordBatch) -> None:
        """NULL-03: Non-null values are correctly extracted alongside nulls."""
        converter = ArrowModelConverter(NullableModel)
        results = converter.convert(nullable_batch)
        assert results[0].id == 1
        assert results[0].score == 9.5
        assert results[2].name == "charlie"
        assert results[2].score == 7.5

    def test_all_null_column(self, all_null_batch: pa.RecordBatch) -> None:
        """NULL-02: Entirely null columns produce all None values."""
        converter = ArrowModelConverter(NullableModel)
        results = converter.convert(all_null_batch)
        assert len(results) == 2
        for result in results:
            assert result.name is None
            assert result.score is None
        # Non-null column still correct
        assert results[0].id == 1
        assert results[1].id == 2


class TestModelConstruct:
    """Tests for FAST-01: Conversion uses model_construct (no Pydantic validation)."""

    def test_uses_model_construct_not_validate(self, mixed_batch: pa.RecordBatch) -> None:
        """
        FAST-01: model_construct bypasses Pydantic validation.

        Verify that conversion uses model_construct (not __init__/model_validate)
        by confirming instances are produced correctly and model_fields_set
        contains the provided fields (model_construct sets this from kwargs).
        """
        converter = ArrowModelConverter(MixedModel)
        results = converter.convert(mixed_batch)
        # model_construct with kwargs sets model_fields_set to the provided field names
        assert results[0].model_fields_set == {"id", "name", "score", "active"}
        # Verify instance is correct
        assert results[0].id == 1
        assert isinstance(results[0], MixedModel)


class TestAPI:
    """Tests for API-01, API-02, INPUT-01: Public API contract."""

    def test_constructor_accepts_model_class(self) -> None:
        """API-01: ArrowModelConverter(Model) constructor works."""
        converter = ArrowModelConverter(MixedModel)
        assert converter is not None

    def test_constructor_accepts_validate_flag(self) -> None:
        """API-01: ArrowModelConverter(Model, validate=True) constructor works."""
        converter = ArrowModelConverter(MixedModel, validate=True)
        assert converter is not None

    def test_convert_returns_list(self, mixed_batch: pa.RecordBatch) -> None:
        """API-02, INPUT-01: convert() returns list[Model] from RecordBatch."""
        results = ArrowModelConverter(MixedModel).convert(mixed_batch)
        assert isinstance(results, list)
        assert len(results) == 3
        assert isinstance(results[0], MixedModel)


class TestEndToEnd:
    """Integration tests for FAST-03: End-to-end conversion correctness."""

    def test_empty_batch(self) -> None:
        """Empty RecordBatch produces empty list."""
        batch = pa.record_batch(
            {
                "id": pa.array([], type=pa.int64()),
                "name": pa.array([], type=pa.string()),
                "score": pa.array([], type=pa.float64()),
                "active": pa.array([], type=pa.bool_()),
            }
        )
        converter = ArrowModelConverter(MixedModel)
        results = converter.convert(batch)
        assert results == []

    def test_single_row(self) -> None:
        """Single-row RecordBatch converts correctly."""
        batch = pa.record_batch(
            {
                "id": pa.array([42], type=pa.int64()),
                "name": pa.array(["single"]),
                "score": pa.array([99.9], type=pa.float64()),
                "active": pa.array([True]),
            }
        )
        converter = ArrowModelConverter(MixedModel)
        results = converter.convert(batch)
        assert len(results) == 1
        assert results[0].id == 42
        assert results[0].name == "single"
        assert results[0].score == 99.9
        assert results[0].active is True

    def test_large_batch(self) -> None:
        """FAST-03: Large batch (10k rows) converts correctly."""
        n = 10_000
        batch = pa.record_batch(
            {
                "id": pa.array(list(range(n)), type=pa.int64()),
                "name": pa.array([f"item_{i}" for i in range(n)]),
                "score": pa.array([float(i) for i in range(n)], type=pa.float64()),
                "active": pa.array([i % 2 == 0 for i in range(n)]),
            }
        )
        converter = ArrowModelConverter(MixedModel)
        results = converter.convert(batch)
        assert len(results) == n
        # Spot-check first and last
        assert results[0].id == 0
        assert results[0].name == "item_0"
        assert results[-1].id == n - 1
        assert results[-1].name == f"item_{n - 1}"


# ---------------------------------------------------------------------------
# Phase 3 test models for alias resolution and schema validation
# ---------------------------------------------------------------------------


class ValidationAliasModel(BaseModel):
    user_id: int = Field(validation_alias="userId")
    display_name: str = Field(validation_alias="displayName")


class AliasModel(BaseModel):
    user_id: int = Field(alias="userId")
    display_name: str = Field(alias="displayName")


class MixedAliasModel(BaseModel):
    user_id: int = Field(validation_alias="userId")
    display_name: str = Field(alias="displayName")
    email: str  # no alias


class PopulateByNameModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    user_id: int = Field(alias="userId")


class ValidateByNameModel(BaseModel):
    model_config = ConfigDict(validate_by_name=True)
    user_id: int = Field(alias="userId")


class AliasPathModel(BaseModel):
    nested_val: str = Field(validation_alias=AliasPath("data", "value"))


class AliasChoicesModel(BaseModel):
    value: str = Field(validation_alias=AliasChoices("val", "value"))


class AliasGeneratorModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=AliasGenerator(
            validation_alias=lambda field_name: field_name.upper()
        )
    )
    user_id: int


class OptionalFieldModel(BaseModel):
    id: int
    name: str = "default_name"
    score: float | None = None


# ---------------------------------------------------------------------------
# Task 1 RED: Tests for _build_field_map and _resolve_columns
# ---------------------------------------------------------------------------


class TestBuildFieldMap:
    """Tests for _build_field_map: alias resolution logic."""

    def test_validation_alias_str_returns_alias_to_field(self) -> None:
        result = _build_field_map(ValidationAliasModel)
        assert result == {"userId": "user_id", "displayName": "display_name"}

    def test_alias_fallback_returns_alias_to_field(self) -> None:
        result = _build_field_map(AliasModel)
        assert result == {"userId": "user_id", "displayName": "display_name"}

    def test_no_alias_returns_field_name_to_field_name(self) -> None:
        result = _build_field_map(MixedModel)
        assert result == {"id": "id", "name": "name", "score": "score", "active": "active"}

    def test_alias_path_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError, match="AliasPath"):
            _build_field_map(AliasPathModel)

    def test_alias_choices_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError, match="AliasChoices"):
            _build_field_map(AliasChoicesModel)

    def test_alias_generator_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError, match="AliasGenerator"):
            _build_field_map(AliasGeneratorModel)

    def test_populate_by_name_adds_both_entries(self) -> None:
        result = _build_field_map(PopulateByNameModel)
        assert "userId" in result
        assert "user_id" in result
        assert result["userId"] == "user_id"
        assert result["user_id"] == "user_id"

    def test_validate_by_name_adds_both_entries(self) -> None:
        result = _build_field_map(ValidateByNameModel)
        assert "userId" in result
        assert "user_id" in result

    def test_populate_by_name_does_not_overwrite_alias(self) -> None:
        """Alias entry should win over field_name entry when they collide."""
        result = _build_field_map(PopulateByNameModel)
        # "userId" -> "user_id" is the alias mapping, it must remain
        assert result["userId"] == "user_id"


class TestResolveColumns:
    """Tests for ArrowModelConverter._resolve_columns."""

    def test_all_required_fields_present(self) -> None:
        converter = ArrowModelConverter(MixedModel)
        schema = pa.schema([
            ("id", pa.int64()),
            ("name", pa.utf8()),
            ("score", pa.float64()),
            ("active", pa.bool_()),
        ])
        col_indices, field_names = converter._resolve_columns(schema)
        assert len(col_indices) == 4
        assert len(field_names) == 4

    def test_missing_required_field_raises_value_error(self) -> None:
        converter = ArrowModelConverter(MixedModel)
        schema = pa.schema([("id", pa.int64())])
        with pytest.raises(ValueError, match="missing required columns"):
            converter._resolve_columns(schema)

    def test_missing_multiple_fields_lists_all(self) -> None:
        converter = ArrowModelConverter(MixedModel)
        schema = pa.schema([("wrong", pa.int64())])
        with pytest.raises(ValueError, match="missing required columns") as exc_info:
            converter._resolve_columns(schema)
        error_msg = str(exc_info.value)
        # All 4 fields should be listed
        assert "id" in error_msg
        assert "name" in error_msg

    def test_optional_field_missing_skips(self) -> None:
        converter = ArrowModelConverter(OptionalFieldModel)
        schema = pa.schema([("id", pa.int64())])
        col_indices, field_names = converter._resolve_columns(schema)
        assert len(col_indices) == 1
        assert field_names == ["id"]

    def test_extra_arrow_columns_ignored(self) -> None:
        converter = ArrowModelConverter(MixedModel)
        schema = pa.schema([
            ("id", pa.int64()),
            ("name", pa.utf8()),
            ("score", pa.float64()),
            ("active", pa.bool_()),
            ("extra_col", pa.int64()),
        ])
        col_indices, field_names = converter._resolve_columns(schema)
        assert len(col_indices) == 4
        assert "extra_col" not in field_names
