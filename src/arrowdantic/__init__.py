"""Arrowdantic: dict-free conversion from Arrow buffers to Pydantic model instances."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arrowdantic import _core as _core

if TYPE_CHECKING:
    import pyarrow as pa
    from pydantic import BaseModel

__all__ = ["ArrowModelConverter", "_core"]


class ArrowModelConverter:
    """Convert Arrow RecordBatch data to Pydantic model instances.

    Cross-references Arrow schema against Pydantic model fields at
    construction time (field names stored) and at convert() time
    (column indices resolved per-batch schema). Uses model_construct
    for zero-validation fast path.

    Per SCHEMA-01: Cross-references Arrow schema against Pydantic model fields.
    Per SCHEMA-02: Schema mapping (field names list) compiled once at init, reused.
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
        # SCHEMA-01, SCHEMA-02: Extract field names once at init, reuse across batches
        self._field_names: list[str] = list(model_class.model_fields.keys())

    def convert(self, data: pa.RecordBatch) -> list[BaseModel]:
        """Convert an Arrow RecordBatch to a list of Pydantic model instances.

        Per API-02: Returns list[Model].
        Per INPUT-01: Accepts pyarrow RecordBatch.
        Per SCHEMA-01: Matches Arrow column names to stored Pydantic field names.

        Raises ValueError if a Pydantic field name is not found in the Arrow schema.
        """
        schema = data.schema
        col_indices: list[int] = []
        for field_name in self._field_names:
            try:
                col_idx = schema.get_field_index(field_name)
            except KeyError:
                msg = (
                    f"Arrow schema has no column named {field_name!r}. "
                    f"Available columns: {schema.names}"
                )
                raise ValueError(msg) from None
            col_indices.append(col_idx)

        return _core.convert_record_batch(
            data,
            self._model_class,
            col_indices,
            self._field_names,
        )
