"""Type stubs for the arrowdantic._core Rust extension module."""

from collections.abc import Sequence
from typing import Any

def record_batch_info(batch: Any, /) -> tuple[int, int]: ...
def convert_record_batch(
    batch: Any,
    model_cls: type[Any],
    field_specs: Sequence[tuple[int, str, type[Any] | None]],
    /,
) -> list[Any]: ...
def convert_table(
    table: Any,
    model_cls: type[Any],
    field_specs: Sequence[tuple[int, str, type[Any] | None]],
    /,
) -> list[Any]: ...
def convert_record_batch_validated(
    batch: Any,
    model_cls: type[Any],
    field_specs: Sequence[tuple[int, str, type[Any] | None]],
    /,
) -> list[Any]: ...
def convert_table_validated(
    table: Any,
    model_cls: type[Any],
    field_specs: Sequence[tuple[int, str, type[Any] | None]],
    /,
) -> list[Any]: ...
