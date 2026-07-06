# arrowmodel — Design Document

## Overview

`arrowmodel` is a Python library with a Rust core that converts Apache Arrow `RecordBatch` and
`Table` objects directly into lists of Pydantic v2 model instances. It eliminates the intermediate
Python dict representation that arises when using pyarrow's `to_pylist()` followed by Pydantic
construction, replacing a two-step materialisation with a single tight Rust loop.

---

## Motivation

The conventional Arrow → Pydantic path is:

```
Arrow buffer → [dict, dict, …] → [Model, Model, …]
```

`to_pylist()` is already implemented in C++ inside pyarrow, so it is fast — but it still
materialises the full dataset as Python dicts, allocating heap objects that are immediately
discarded once Pydantic consumes them. For large batches this is significant unnecessary
allocation pressure.

`arrowmodel` collapses this to:

```
Arrow buffer → [Model, Model, …]
```

The Arrow buffers are accessed in Rust via the **Arrow C Data Interface** (a pointer handoff,
no copy). Column values are read directly from those buffers in a Rust loop, and Pydantic model
instances are constructed via PyO3 without any intermediate dict.

---

## Goals

- Single-step, dict-free conversion from Arrow → Pydantic model instances.
- Schema cross-referencing and field mapping compiled **once** at converter construction time,
  not per batch.
- Full support for Pydantic v2 field aliases and `validation_alias`.
- Compatibility with both **pyarrow** and **Polars** as Arrow sources, via the C Data Interface.
- An opt-in **validated path** for untrusted data sources that preserves Pydantic's validation
  guarantees.
- A Rust crate and Python package with clean, minimal public API surface.

---

## Non-Goals

- Replacing pyarrow or Polars for general Arrow work.
- Supporting Pydantic v1.
- ORM or database layer integration.
- Arrow *writing* (Pydantic → Arrow) — out of scope for the initial version.

---

## Architecture

### Crate / Package Layout

```
arrowmodel/
├── src/
│   ├── lib.rs           — PyO3 module entry point
│   ├── converter.rs     — ArrowModelConverter pyclass
│   ├── schema.rs        — Arrow↔Pydantic schema cross-referencing
│   ├── handlers.rs      — TypeHandler enum and per-type extract() impls
│   └── ffi.rs           — Arrow C Data Interface glue (via pyo3-arrow)
├── python/
│   └── arrowmodel/
│       ├── __init__.py  — public API, alias resolution helper
│       └── _core.pyi    — type stubs for the Rust extension
├── tests/
│   ├── test_types.py
│   ├── test_aliases.py
│   └── test_polars.py
└── Cargo.toml           — pyo3, arrow-rs, pyo3-arrow deps
```

---

## Key Data Structures

### `FieldMapping` (Rust)

Built once per field during `ArrowModelConverter.__init__`. Encodes everything the hot loop
needs to process a single field across all rows:

```rust
struct FieldMapping {
    column_index:  usize,           // index into RecordBatch columns
    python_name:   Py<PyString>,    // pre-interned — reused every row
    handler:       TypeHandler,     // how to convert Arrow value → Python object
    nullable:      bool,
}
```

`python_name` is always the Pydantic **field name** (not alias) — `model_construct` takes field
names regardless of how the Arrow column was matched.

### `TypeHandler` (Rust)

A statically-dispatched enum covering the full Arrow type system:

```rust
enum TypeHandler {
    Int8, Int16, Int32, Int64,
    UInt8, UInt16, UInt32, UInt64,
    Float32, Float64,
    Boolean,
    Utf8, LargeUtf8,
    Date32,
    Timestamp { timezone: Option<String> },
    Duration,
    List(Box<TypeHandler>),
    Struct(Box<ArrowModelConverterInner>),  // recursive for nested models
    Dictionary(Box<TypeHandler>),           // categorical — decode to value type
    Null,
}
```

---

## Conversion Flow

### 1. Compiler phase (`__init__`)

Schema cross-referencing happens entirely in Python (where `model_fields` is easy to
introspect) and the resulting field map is passed into Rust:

```python
# python/arrowmodel/__init__.py


def _build_field_map(model_cls) -> dict[str, str]:
    """Returns {arrow_column_name -> python_field_name}"""
    result = {}
    for field_name, field_info in model_cls.model_fields.items():
        # resolution priority: validation_alias > alias > field_name
        arrow_name = field_info.validation_alias or field_info.alias or field_name
        result[arrow_name] = field_name
        if model_cls.model_config.get("populate_by_name"):
            result[field_name] = field_name  # accept both
    return result
```

The Rust constructor receives the Arrow schema and this field map, pairs them up, resolves
column indices, selects `TypeHandler` variants, and stores the compiled `Vec<FieldMapping>`.

Any schema mismatch (required Pydantic field absent from Arrow schema, unresolvable type) is
raised as a `ValueError` here — **not** during batch conversion.

### 2. Hot loop (`convert`)

```rust
fn convert(&self, py: Python, batch: RecordBatch) -> PyResult<Vec<PyObject>> {
    let n_rows = batch.num_rows();
    let mut result = Vec::with_capacity(n_rows);

    for row_idx in 0..n_rows {
        let kwargs = PyDict::new(py);

        for mapping in &self.field_mappings {
            let col = batch.column(mapping.column_index);

            let value: PyObject = if mapping.nullable && col.is_null(row_idx) {
                py.None()
            } else {
                mapping.handler.extract(py, col, row_idx)?
            };

            // python_name is pre-interned — no per-row string allocation
            kwargs.set_item(&mapping.python_name, value)?;
        }

        let instance = self.model_cls
            .call_method(py, "model_construct", (), Some(kwargs))?;
        result.push(instance);
    }

    Ok(result)
}
```

No Python involvement in the loop other than the unavoidable `PyDict` construction and
`model_construct` call at the end of each row.

---

## Arrow Type Mapping

The mapping follows pyarrow's existing Python type mapping for all primitive and temporal types,
extending it for complex types:

| Arrow type | Python target | Notes |
|---|---|---|
| `Int8/16/32/64` | `int` | Direct |
| `UInt8/16/32` | `int` | Direct |
| `UInt64` | `int` | Watch overflow |
| `Float32` | `float` | Precision narrowing |
| `Float64` | `float` | Direct |
| `Boolean` | `bool` | Bit-packed — unpack via validity bitmap |
| `Utf8 / LargeUtf8` | `str` | `PyString::new` per value |
| `Date32` | `datetime.date` | Days-since-epoch conversion |
| `Timestamp(tz=None)` | `datetime.datetime` | Naive |
| `Timestamp(tz=UTC)` | `datetime.datetime` | Aware, `timezone.utc` |
| `Duration` | `datetime.timedelta` | |
| `List<T>` | `list` | Recurse `TypeHandler` for T |
| `LargeList<T>` | `list` | As above |
| `Struct` | nested `BaseModel` | Recursive `ArrowModelConverter` |
| `Dictionary<K, Utf8>` | `str` | Decode to value; important for categoricals |
| `Null` | `None` | Always null |

### Null Handling

Arrow stores nulls as a **separate validity bitmap**, not as a sentinel value in the value
buffer. The value at a null index in the value buffer is undefined and must not be read.
The hot loop checks `col.is_null(row_idx)` before calling `handler.extract()`. With
`model_construct`, null values reaching non-optional fields are silently accepted — this
is by design on the fast path (see Validation section below).

---

## Validation Mode

`model_construct` bypasses pydantic-core validation entirely. For data from trusted sources
(your own Arrow pipeline) this is correct. For untrusted external data, an opt-in validated
path is available.

```python
# Fast path — no validation (default)
converter = ArrowModelConverter(MyModel, validate=False)

# Validated path — preserves Pydantic guarantees
converter = ArrowModelConverter(MyModel, validate=True)
```

On the validated path, the Rust loop serialises each row to JSON bytes via `serde_json` and
calls `model.__pydantic_validator__.validate_json(bytes)` — keeping the JSON parsing and
schema validation inside pydantic-core's Rust layer (`jiter` + `SchemaValidator`). This is
worse throughput than the fast path but better than going via Python dicts:

```
Arrow buffer (Rust) → serde_json row bytes (Rust) → validate_json (pydantic-core Rust)
```

---

## Alias Resolution

Pydantic v2 alias resolution priority, reflected in `_build_field_map`:

1. `validation_alias` — if set, this is what `validate_python` / `validate_json` read
2. `alias` — general alias used for both validation and serialisation
3. field name — the Python identifier

If `model_config["populate_by_name"] = True`, both the alias and the field name are accepted
as Arrow column names, with the field name taking precedence on collision.

`model_construct` always receives **field names** regardless of alias resolution.

---

## Arrow C Data Interface & Polars Interop

Arrow buffer handoff uses the Arrow C Data Interface — two raw pointer integers
(`ArrowArray*` and `ArrowSchema*`) passed across the language boundary. The `pyo3-arrow`
crate wraps this for ergonomic use in PyO3:

```rust
use pyo3_arrow::PyRecordBatch;

#[pyfunction]
fn convert(py: Python, batch: PyRecordBatch, ...) -> PyResult<Vec<PyObject>> {
    let batch: RecordBatch = batch.into();  // zero-copy pointer handoff
    // ...
}
```

Because the C Data Interface is a standard, **Polars DataFrames work as input without
additional FFI glue**. Polars exports via the same interface, so the same converter accepts
both pyarrow `RecordBatch` / `Table` and Polars `DataFrame`.

Polars-specific edge cases to handle:
- `Categorical` type — similar to `Dictionary` but requires checking Polars' encoding
- `ChunkedArray` within Polars exports — handle chunk boundaries correctly in row indexing

For pyarrow `Table` (which uses `ChunkedArray` internally), the library should either
require callers to pass individual batches, or accept `Table` and iterate over its batches
internally.

---

## Public Python API

```python
from arrowmodel import ArrowModelConverter

# Construction — schema cross-referencing happens here
converter = ArrowModelConverter(
    MyModel,
    validate=False,  # default: fast path, no pydantic validation
)

# Batch conversion
models: list[MyModel] = converter.convert(record_batch)

# Convenience one-shot function for ad-hoc use
from arrowmodel import from_arrow

models = from_arrow(MyModel, record_batch)
```

`ArrowModelConverter` raises `ValueError` on construction if:
- A required (non-optional, no default) Pydantic field has no matching Arrow column
- An Arrow column type has no valid handler for the corresponding Pydantic field type
- The Arrow schema and field map produce an ambiguous match

---

## Dependencies

| Dependency | Role |
|---|---|
| `pyo3` | Python ↔ Rust FFI |
| `arrow-rs` | Arrow buffer types and C Data Interface import |
| `pyo3-arrow` | Ergonomic PyO3 wrapper for Arrow C Data Interface |
| `serde_json` | Row → JSON bytes on validated path |
| `chrono` | Date/timestamp conversion |
| **Python** | |
| `pydantic >= 2.0` | Model introspection and construction |
| `pyarrow` (optional) | Primary Arrow source; not required if using Polars only |
| `polars` (optional) | Alternative Arrow source |

---

## Open Questions

**Extra Arrow columns.** If Arrow has columns that no Pydantic field maps to, the current
design silently ignores them. This is probably correct but should be a documented behaviour,
with an optional `strict=True` flag that raises instead.

**`AliasPath` and `AliasGenerator`.** Pydantic v2 supports `validation_alias=AliasPath(...)`
for nested key access and `AliasGenerator` for model-wide alias patterns. These are more
complex to resolve at compile time and are deferred to a later iteration. The initial version
should raise a clear `NotImplementedError` if these are encountered during schema
cross-referencing.

**`FixedSizeList<T, N>`.** Could reasonably map to `list`, `tuple`, or `numpy.ndarray`
depending on the Pydantic field annotation. Needs a resolution heuristic.

**Benchmark targets.** The primary comparison is `to_pylist()` + `model_construct()` in a
Python loop (i.e. what a careful user would write today). A secondary comparison against
`to_pylist()` + `Model(**row)` (with validation) establishes the validated-path baseline.
