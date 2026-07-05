"""Arrowmodel: dict-free conversion from Arrow buffers to Pydantic model instances."""

from __future__ import annotations

import types
import typing
from typing import TYPE_CHECKING, Any, ClassVar, Self, cast

from pydantic import AliasChoices, AliasPath, BaseModel

from arrowmodel import _core as _core

if TYPE_CHECKING:
    from collections.abc import Iterator

    import pyarrow as pa

__all__ = [
    "ArrowModel",
    "ArrowModelConverter",
    "model_convert",
    "model_iter",
    "_build_field_map",
    "_get_nested_model",
    "_core",
]


def _get_nested_model(annotation: Any) -> type[BaseModel] | None:
    """
    Extract nested BaseModel class from a Pydantic field annotation.

    Handles:
    - Direct BaseModel subclass: ``NestedModel`` -> ``NestedModel``
    - Optional[NestedModel] (Union[NestedModel, None]): -> ``NestedModel``
    - Non-model types: -> ``None``
    """
    if annotation is None:
        return None
    # Direct BaseModel subclass
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    # Optional[NestedModel] = Union[NestedModel, None]
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        args = typing.get_args(annotation)
        for arg in args:
            if isinstance(arg, type) and issubclass(arg, BaseModel):
                return arg
    return None


def _build_field_map(model_class: type[BaseModel]) -> dict[str, str]:
    """
    Build ``{arrow_column_name: pydantic_field_name}`` mapping.

    Resolution priority (ALIAS-01): validation_alias > alias > field_name.
    Raises NotImplementedError for AliasPath, AliasChoices (ALIAS-03).
    Raises NotImplementedError for AliasGenerator on model config (ALIAS-03).
    When populate_by_name or validate_by_name is enabled (ALIAS-02),
    both alias and field name are accepted for column lookup.
    """
    config = model_class.model_config

    # ALIAS-03: Reject AliasGenerator on model config
    alias_gen = config.get("alias_generator")
    if alias_gen is not None:
        raise NotImplementedError(
            f"AliasGenerator on {model_class.__name__} is not supported. "
            "Use explicit per-field aliases instead."
        )

    field_map: dict[str, str] = {}

    for field_name, field_info in model_class.model_fields.items():
        va = field_info.validation_alias
        if va is not None:
            # ALIAS-03: Reject AliasPath / AliasChoices
            if isinstance(va, (AliasPath, AliasChoices)):
                raise NotImplementedError(
                    f"Field {field_name!r} uses {type(va).__name__} as "
                    "validation_alias, which is not supported."
                )
            lookup_name = va  # str
        elif field_info.alias is not None:
            lookup_name = field_info.alias
        else:
            lookup_name = field_name

        field_map[lookup_name] = field_name

    # ALIAS-02: populate_by_name / validate_by_name support
    accept_by_name = config.get("validate_by_name", False) or config.get("populate_by_name", False)
    if accept_by_name:
        for field_name in model_class.model_fields:
            # Only add if not already present (alias takes priority)
            if field_name not in field_map:
                field_map[field_name] = field_name

    return field_map


class ArrowModelConverter:
    """
    Convert Arrow RecordBatch data to Pydantic model instances.

    Cross-references Arrow schema against Pydantic model fields at
    construction time (alias-aware field map built once) and at convert()
    time (column indices resolved per-batch schema).  Uses model_construct
    for zero-validation fast path.

    Per SCHEMA-01: Cross-references Arrow schema against Pydantic model fields.
    Per SCHEMA-02: Schema mapping compiled once at init, reused across batches.
    Per SCHEMA-03: ValueError raised at convert() for missing required fields.
    Per SCHEMA-04: Extra Arrow columns silently ignored.
    Per ALIAS-01: validation_alias > alias > field_name priority.
    Per ALIAS-02: populate_by_name / validate_by_name support.
    Per ALIAS-03: AliasPath, AliasChoices, AliasGenerator raise NotImplementedError.
    Per API-01: Constructor accepts model class and optional validate flag.
    """

    def __init__(
        self,
        model_class: type[BaseModel],
        *,
        validate: bool = False,
    ) -> None:
        self._model_class = model_class
        self._validate = validate
        # SCHEMA-01, SCHEMA-02, ALIAS-01: Build alias-aware field map once at init
        self._field_map: dict[str, str] = _build_field_map(model_class)

    def _resolve_columns(self, schema: pa.Schema) -> list[tuple[int, str, type[BaseModel] | None]]:
        """
        Resolve Arrow column indices from schema using the field map.

        Returns ``field_specs``: list of ``(col_index, field_name, nested_model_cls)``
        for Rust. ``nested_model_cls`` is non-None when the Pydantic field's
        annotation is a BaseModel subclass (for Struct column conversion).

        Raises ValueError for missing required columns (SCHEMA-03).
        Extra Arrow columns are silently ignored (SCHEMA-04).

        When populate_by_name / validate_by_name is enabled, the field_map
        may contain multiple lookup names mapping to the same Pydantic field.
        A field is considered resolved if ANY of its lookup names match an
        Arrow column.
        """
        field_specs: list[tuple[int, str, type[BaseModel] | None]] = []
        # Track which Pydantic fields have been resolved (handles multiple
        # lookup names mapping to the same field, e.g. populate_by_name)
        resolved_fields: set[str] = set()

        for lookup_name, field_name in self._field_map.items():
            if field_name in resolved_fields:
                continue
            col_idx = schema.get_field_index(lookup_name)
            if col_idx < 0:
                continue
            # Detect nested BaseModel for Struct columns
            field_info = self._model_class.model_fields[field_name]
            nested_model = _get_nested_model(field_info.annotation)
            field_specs.append((col_idx, field_name, nested_model))
            resolved_fields.add(field_name)

        # Check for missing required fields
        missing: list[str] = []
        for field_name, field_info in self._model_class.model_fields.items():
            if field_name not in resolved_fields and field_info.is_required():
                # Find the lookup name(s) for this field for the error message
                lookup_names = [ln for ln, fn in self._field_map.items() if fn == field_name]
                missing.extend(lookup_names[:1])  # report primary lookup name

        if missing:
            raise ValueError(
                f"Arrow schema is missing required columns: {missing}. "
                f"Available columns: {schema.names}"
            )

        return field_specs

    def convert(self, data: pa.RecordBatch | pa.Table) -> list[BaseModel]:
        """
        Convert Arrow RecordBatch or Table to a list of Pydantic model instances.

        Per API-02: Returns list[Model].
        Per INPUT-01: Accepts pyarrow RecordBatch.
        Per INPUT-02: Accepts pyarrow Table (iterates batches internally via Rust).
        Per SCHEMA-03: Raises ValueError when required fields cannot be matched.
        Per SCHEMA-04: Extra Arrow columns silently ignored.
        """
        field_specs = self._resolve_columns(data.schema)

        if hasattr(data, "to_batches"):
            # Table input: delegate to Rust convert_table (fast or validated)
            table = cast("pa.Table", data)
            if self._validate:
                return _core.convert_table_validated(table, self._model_class, field_specs)
            return _core.convert_table(table, self._model_class, field_specs)
        else:
            # RecordBatch input: delegate to Rust convert_record_batch (fast or validated)
            batch = cast("pa.RecordBatch", data)
            if self._validate:
                return _core.convert_record_batch_validated(batch, self._model_class, field_specs)
            return _core.convert_record_batch(batch, self._model_class, field_specs)

    def iter(self, data: pa.RecordBatch | pa.Table) -> Iterator[BaseModel]:
        """
        Lazily yield individual model instances from Arrow data.

        For Tables with multiple batches, only one batch's worth of instances
        is materialized in memory at a time, but each instance is yielded
        individually. For RecordBatch input, behavior is equivalent to
        iterating over convert() results.

        Per API-04: Iterator/generator API for lazy model yielding.
        """
        field_specs = self._resolve_columns(data.schema)

        if hasattr(data, "to_batches"):
            batches: list[pa.RecordBatch] = cast("pa.Table", data).to_batches()
        else:
            batches = [cast("pa.RecordBatch", data)]

        for batch in batches:
            if self._validate:
                results = _core.convert_record_batch_validated(
                    batch, self._model_class, field_specs
                )
            else:
                results = _core.convert_record_batch(batch, self._model_class, field_specs)
            yield from results


class ArrowModel(BaseModel):
    """
    Pydantic BaseModel subclass with Arrow conversion classmethods.

    Subclasses auto-generate an ``ArrowModelConverter`` at class definition
    time (via ``__pydantic_init_subclass__``), so users can call
    ``MyModel.convert(batch)`` without manually creating a converter.

    Example::

        class User(ArrowModel):
            id: int
            name: str

        users: list[User] = User.convert(batch)

    The fast path (``model_construct``, no validation) is used by default.
    Pass ``validate=True`` to use the validated path
    (``model_validate_json``).
    """

    _arrow_converter: ClassVar[ArrowModelConverter]
    _arrow_converter_validated: ClassVar[ArrowModelConverter]

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        # Only create converter for concrete subclasses that have fields.
        # __pydantic_init_subclass__ runs after Pydantic's metaclass has
        # populated model_fields, unlike __init_subclass__ which fires
        # before field resolution.
        if cls.model_fields:
            cls._arrow_converter = ArrowModelConverter(cls, validate=False)

    @classmethod
    def convert(cls, data: pa.RecordBatch | pa.Table, *, validate: bool = False) -> list[Self]:
        """
        Convert Arrow RecordBatch or Table to a list of model instances.

        Args:
            data: Arrow RecordBatch or Table to convert.
            validate: If True, use the validated path (model_validate_json).
                Defaults to False (fast path via model_construct).

        Returns:
            List of model instances.
        """
        if validate:
            if not hasattr(cls, "_arrow_converter_validated"):
                cls._arrow_converter_validated = ArrowModelConverter(cls, validate=True)
            return cls._arrow_converter_validated.convert(data)  # type: ignore[return-value]
        return cls._arrow_converter.convert(data)  # type: ignore[return-value]

    @classmethod
    def iter(cls, data: pa.RecordBatch | pa.Table, *, validate: bool = False) -> Iterator[Self]:
        """
        Lazily yield individual model instances from Arrow data.

        Args:
            data: Arrow RecordBatch or Table to convert.
            validate: If True, use the validated path (model_validate_json).
                Defaults to False (fast path via model_construct).

        Yields:
            Model instances one at a time.
        """
        if validate:
            if not hasattr(cls, "_arrow_converter_validated"):
                cls._arrow_converter_validated = ArrowModelConverter(cls, validate=True)
            yield from cls._arrow_converter_validated.iter(data)  # type: ignore[misc]
        else:
            yield from cls._arrow_converter.iter(data)  # type: ignore[misc]


def model_convert(
    model_class: type[BaseModel],
    data: pa.RecordBatch | pa.Table,
    *,
    validate: bool = False,
) -> list[BaseModel]:
    """
    One-shot conversion from Arrow data to Pydantic model instances.

    Convenience function that creates a temporary ArrowModelConverter
    and calls convert(). For repeated conversions of the same model,
    prefer creating an ArrowModelConverter instance and reusing it.

    Per API-03: Convenience one-shot function.
    Per DEBT-04: Accepts validate parameter for API symmetry with model_iter.
    """
    converter = ArrowModelConverter(model_class, validate=validate)
    return converter.convert(data)


def model_iter(
    model_class: type[BaseModel],
    data: pa.RecordBatch | pa.Table,
    *,
    validate: bool = False,
) -> Iterator[BaseModel]:
    """
    Lazily yield individual model instances from Arrow data.

    Convenience function that creates a temporary ArrowModelConverter
    and calls iter(). For repeated conversions of the same model,
    prefer creating an ArrowModelConverter instance and reusing it.

    Per API-04: Iterator/generator API for lazy model yielding.
    """
    converter = ArrowModelConverter(model_class, validate=validate)
    yield from converter.iter(data)
