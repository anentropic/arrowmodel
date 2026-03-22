"""Arrowdantic: dict-free conversion from Arrow buffers to Pydantic model instances."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import AliasChoices, AliasPath, BaseModel

from arrowdantic import _core as _core

if TYPE_CHECKING:
    import pyarrow as pa

__all__ = ["ArrowModelConverter", "_build_field_map", "_core"]


def _build_field_map(model_class: type[BaseModel]) -> dict[str, str]:
    """Build ``{arrow_column_name: pydantic_field_name}`` mapping.

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
    accept_by_name = config.get("validate_by_name", False) or config.get(
        "populate_by_name", False
    )
    if accept_by_name:
        for field_name in model_class.model_fields:
            # Only add if not already present (alias takes priority)
            if field_name not in field_map:
                field_map[field_name] = field_name

    return field_map


class ArrowModelConverter:
    """Convert Arrow RecordBatch data to Pydantic model instances.

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

    def _resolve_columns(
        self, schema: pa.Schema
    ) -> tuple[list[int], list[str]]:
        """Resolve Arrow column indices from schema using the field map.

        Returns ``(col_indices, field_names)`` for Rust.
        Raises ValueError for missing required columns (SCHEMA-03).
        Extra Arrow columns are silently ignored (SCHEMA-04).
        """
        col_indices: list[int] = []
        field_names: list[str] = []
        missing: list[str] = []

        for lookup_name, field_name in self._field_map.items():
            col_idx = schema.get_field_index(lookup_name)
            if col_idx < 0:
                # Check if field is optional (has a default)
                field_info = self._model_class.model_fields[field_name]
                if field_info.is_required():
                    missing.append(lookup_name)
                # Skip optional fields that aren't in Arrow schema
                continue
            col_indices.append(col_idx)
            field_names.append(field_name)

        if missing:
            raise ValueError(
                f"Arrow schema is missing required columns: {missing}. "
                f"Available columns: {schema.names}"
            )

        return col_indices, field_names

    def convert(self, data: pa.RecordBatch) -> list[BaseModel]:
        """Convert an Arrow RecordBatch to a list of Pydantic model instances.

        Per API-02: Returns list[Model].
        Per INPUT-01: Accepts pyarrow RecordBatch.
        Per SCHEMA-03: Raises ValueError for missing required Arrow columns.
        Per SCHEMA-04: Extra Arrow columns silently ignored.
        """
        col_indices, field_names = self._resolve_columns(data.schema)

        return _core.convert_record_batch(
            data,
            self._model_class,
            col_indices,
            field_names,
        )
