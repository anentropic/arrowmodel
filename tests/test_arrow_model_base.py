"""
Tests for ArrowModel base class.

Covers the ergonomic API where users define `class User(ArrowModel)` and call
`User.convert(batch)` without manually creating converters.
"""

from __future__ import annotations

from collections.abc import Iterator

import pyarrow as pa
from pydantic import Field

from arrowmodel import ArrowModel, ArrowModelConverter


class SimpleUser(ArrowModel):
    id: int
    name: str
    score: float


class AliasedModel(ArrowModel):
    user_id: int = Field(alias="uid")
    display_name: str = Field(alias="dname")


class AdminUser(SimpleUser):
    role: str


class TestArrowModel:
    """Tests for ArrowModel base class with convert/iter classmethods."""

    def test_converter_created_at_definition_time(self) -> None:
        """_arrow_converter is created when the subclass is defined, not lazily."""
        assert hasattr(SimpleUser, "_arrow_converter")
        assert isinstance(SimpleUser._arrow_converter, ArrowModelConverter)

    def test_converter_uses_fast_path_by_default(self) -> None:
        """Default converter has validate=False (fast path via model_construct)."""
        assert SimpleUser._arrow_converter._validate is False

    def test_convert_returns_list_of_subclass_instances(self) -> None:
        """SubClass.convert(batch) returns list of SubClass instances."""
        batch = pa.record_batch(
            {
                "id": pa.array([1, 2], type=pa.int64()),
                "name": pa.array(["alice", "bob"]),
                "score": pa.array([9.5, 8.0], type=pa.float64()),
            }
        )
        results = SimpleUser.convert(batch)
        assert len(results) == 2
        assert all(isinstance(r, SimpleUser) for r in results)
        assert results[0].id == 1
        assert results[0].name == "alice"
        assert results[0].score == 9.5
        assert results[1].id == 2
        assert results[1].name == "bob"
        assert results[1].score == 8.0

    def test_convert_works_with_table(self) -> None:
        """SubClass.convert(table) works for Table input."""
        batch = pa.record_batch(
            {
                "id": pa.array([1, 2], type=pa.int64()),
                "name": pa.array(["alice", "bob"]),
                "score": pa.array([9.5, 8.0], type=pa.float64()),
            }
        )
        table = pa.Table.from_batches([batch])
        results = SimpleUser.convert(table)
        assert len(results) == 2
        assert all(isinstance(r, SimpleUser) for r in results)
        assert results[0].id == 1
        assert results[1].name == "bob"

    def test_iter_yields_instances(self) -> None:
        """SubClass.iter(table) yields instances one at a time (returns Iterator)."""
        batch = pa.record_batch(
            {
                "id": pa.array([1, 2, 3], type=pa.int64()),
                "name": pa.array(["a", "b", "c"]),
                "score": pa.array([1.0, 2.0, 3.0], type=pa.float64()),
            }
        )
        table = pa.Table.from_batches([batch])
        result = SimpleUser.iter(table)
        assert isinstance(result, Iterator)
        items = list(result)
        assert len(items) == 3
        assert all(isinstance(i, SimpleUser) for i in items)
        assert items[2].name == "c"

    def test_convert_validate_true_uses_validated_path(self) -> None:
        """convert(batch, validate=True) creates and caches a validating converter."""
        batch = pa.record_batch(
            {
                "id": pa.array([1], type=pa.int64()),
                "name": pa.array(["alice"]),
                "score": pa.array([9.5], type=pa.float64()),
            }
        )
        # Remove any previously cached validated converter
        if hasattr(SimpleUser, "_arrow_converter_validated"):
            delattr(SimpleUser, "_arrow_converter_validated")

        results = SimpleUser.convert(batch, validate=True)
        assert len(results) == 1
        assert isinstance(results[0], SimpleUser)
        assert results[0].id == 1
        # Validated converter should now be cached
        assert hasattr(SimpleUser, "_arrow_converter_validated")
        assert isinstance(SimpleUser._arrow_converter_validated, ArrowModelConverter)
        assert SimpleUser._arrow_converter_validated._validate is True

    def test_convert_validate_false_uses_fast_path(self) -> None:
        """convert(batch, validate=False) uses the default fast converter."""
        batch = pa.record_batch(
            {
                "id": pa.array([1], type=pa.int64()),
                "name": pa.array(["alice"]),
                "score": pa.array([9.5], type=pa.float64()),
            }
        )
        results = SimpleUser.convert(batch, validate=False)
        assert len(results) == 1
        assert isinstance(results[0], SimpleUser)

    def test_arrow_model_base_has_no_converter(self) -> None:
        """ArrowModel itself does NOT have _arrow_converter (abstract base)."""
        assert not hasattr(ArrowModel, "_arrow_converter")

    def test_subclass_with_aliases(self) -> None:
        """Subclass with Field(alias=...) has correct field map at definition time."""
        batch = pa.record_batch(
            {
                "uid": pa.array([1, 2], type=pa.int64()),
                "dname": pa.array(["Alice", "Bob"]),
            }
        )
        results = AliasedModel.convert(batch)
        assert len(results) == 2
        assert results[0].user_id == 1
        assert results[0].display_name == "Alice"
        assert results[1].user_id == 2
        assert results[1].display_name == "Bob"

    def test_arrow_model_in_all(self) -> None:
        """ArrowModel appears in arrowmodel.__all__."""
        import arrowmodel

        assert "ArrowModel" in arrowmodel.__all__

    def test_subclass_of_subclass_gets_own_converter(self) -> None:
        """Sub-subclass gets its own converter, distinct from parent's."""
        assert hasattr(AdminUser, "_arrow_converter")
        assert isinstance(AdminUser._arrow_converter, ArrowModelConverter)
        assert AdminUser._arrow_converter is not SimpleUser._arrow_converter

    def test_subclass_of_subclass_convert(self) -> None:
        """Sub-subclass.convert() returns instances of the sub-subclass."""
        batch = pa.record_batch(
            {
                "id": pa.array([1, 2], type=pa.int64()),
                "name": pa.array(["alice", "bob"]),
                "score": pa.array([9.5, 8.0], type=pa.float64()),
                "role": pa.array(["admin", "superadmin"]),
            }
        )
        results = AdminUser.convert(batch)
        assert len(results) == 2
        assert all(isinstance(r, AdminUser) for r in results)
        assert results[0].id == 1
        assert results[0].name == "alice"
        assert results[0].role == "admin"
        assert results[1].role == "superadmin"

    def test_subclass_of_subclass_iter(self) -> None:
        """Sub-subclass.iter() yields instances of the sub-subclass."""
        batch = pa.record_batch(
            {
                "id": pa.array([1], type=pa.int64()),
                "name": pa.array(["alice"]),
                "score": pa.array([9.5], type=pa.float64()),
                "role": pa.array(["admin"]),
            }
        )
        items = list(AdminUser.iter(batch))
        assert len(items) == 1
        assert isinstance(items[0], AdminUser)
        assert items[0].role == "admin"

    def test_subclass_of_subclass_does_not_affect_parent(self) -> None:
        """Parent class still works independently after sub-subclass is defined."""
        batch = pa.record_batch(
            {
                "id": pa.array([1], type=pa.int64()),
                "name": pa.array(["alice"]),
                "score": pa.array([9.5], type=pa.float64()),
            }
        )
        results = SimpleUser.convert(batch)
        assert len(results) == 1
        assert type(results[0]) is SimpleUser

    def test_iter_validate_true(self) -> None:
        """iter(data, validate=True) uses the validated path."""
        batch = pa.record_batch(
            {
                "id": pa.array([1, 2], type=pa.int64()),
                "name": pa.array(["a", "b"]),
                "score": pa.array([1.0, 2.0], type=pa.float64()),
            }
        )
        items = list(SimpleUser.iter(batch, validate=True))
        assert len(items) == 2
        assert all(isinstance(i, SimpleUser) for i in items)


class FieldlessModel(ArrowModel):
    """An ArrowModel subclass with no fields."""


class TestFieldlessSubclass:
    def test_fieldless_subclass_gets_converter(self) -> None:
        """A field-less subclass still gets a converter (no AttributeError)."""
        batch = pa.record_batch({"ignored": pa.array([1, 2, 3], type=pa.int64())})
        results = FieldlessModel.convert(batch)
        assert len(results) == 3
        assert all(type(r) is FieldlessModel for r in results)
