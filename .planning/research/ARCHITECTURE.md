# Architecture Research

**Domain:** Rust/PyO3 Arrow-to-Pydantic conversion library
**Researched:** 2026-03-21
**Confidence:** HIGH

## Standard Architecture

### System Overview

```
                          Python User Code
                               |
                    from_arrow(MyModel, batch)
                               |
            +-----------------------------------------+
            |         Python Wrapper Layer             |
            |    src/arrowdantic/__init__.py           |
            |    src/arrowdantic/_typing.py            |
            |                                         |
            |  - model_fields introspection           |
            |  - alias resolution                     |
            |  - type mapping (Arrow <-> Python)       |
            |  - ArrowModelConverter Python class      |
            |  - from_arrow() convenience function    |
            +-----------------------------------------+
                               |
                   FieldMapping[] passed to Rust
                               |
            +-----------------------------------------+
            |         Rust Extension Module            |
            |    arrowdantic._core  (PyO3/maturin)    |
            |                                         |
            |  +-----------+    +------------------+  |
            |  | Ingestion |    | Row Construction |  |
            |  | (pyo3-    |    | (fast path:      |  |
            |  |  arrow)   |    |  __setattr__ on  |  |
            |  |           |    |  model instance)  |  |
            |  +-----+-----+   +--------+---------+  |
            |        |                  |             |
            |  +-----v------------------v---------+   |
            |  |       Type Extractors            |   |
            |  |  (arrow-rs column -> PyObject)   |   |
            |  |  Int, Float, Bool, Utf8,         |   |
            |  |  Date, Timestamp, List, Struct   |   |
            |  +----------------------------------+   |
            |                                         |
            |  +----------------------------------+   |
            |  |    Validated Path (optional)      |   |
            |  |  serde_json row -> validate_json  |   |
            |  +----------------------------------+   |
            +-----------------------------------------+
                               |
                   Arrow C Data Interface (PyCapsule)
                               |
            +-----------------------------------------+
            |  pyarrow / polars / any Arrow producer   |
            +-----------------------------------------+
```

### Component Responsibilities

| Component | Responsibility | Implementation |
|-----------|----------------|----------------|
| **Python Wrapper** | Pydantic introspection, schema mapping, public API | Pure Python in `src/arrowdantic/` |
| **Schema Mapper** | Cross-reference Arrow schema with Pydantic model_fields, resolve aliases, build field mapping list | Python -- because `model_fields` is a Python dict requiring Pydantic API access |
| **Rust Core** | Hot loop: iterate rows, extract values from Arrow columns, construct Pydantic instances | `arrowdantic._core` via PyO3 |
| **Ingestion** | Receive Arrow data from Python via PyCapsule interface | `pyo3-arrow` crate (`PyRecordBatch`) |
| **Type Extractors** | Downcast arrow-rs arrays to concrete types, extract Python-compatible values | Rust match on `DataType`, column-oriented extraction |
| **Row Constructor** | Create Pydantic model instances without validation using `object.__setattr__` | PyO3 calls into Python object protocol |
| **Validated Path** | Serialize rows to JSON via serde_json, pass to `model_validate_json` | Rust serde_json + Pydantic Python API |

## Recommended Project Structure

```
arrowdantic/
+-- Cargo.toml                    # Rust crate configuration
+-- pyproject.toml                # Python project config (build-backend = maturin)
+-- src/
|   +-- arrowdantic/              # Python package
|   |   +-- __init__.py           # Public API: from_arrow(), ArrowModelConverter
|   |   +-- _typing.py            # FieldMapping, type resolution helpers
|   |   +-- _core.pyi             # Type stubs for Rust extension
|   |   +-- py.typed              # PEP 561 marker
|   +-- lib.rs                    # PyO3 module entrypoint (#[pymodule])
|   +-- convert.rs                # Core conversion loop
|   +-- extract.rs                # Arrow column -> PyObject extractors
|   +-- types.rs                  # FieldMapping struct, shared types
|   +-- validated.rs              # serde_json validated path
+-- tests/
|   +-- conftest.py               # Shared fixtures (models, batches)
|   +-- test_basic.py             # Scalar type conversions
|   +-- test_nested.py            # List/Struct/nested model tests
|   +-- test_aliases.py           # Alias resolution tests
|   +-- test_validated.py         # validate=True path tests
```

### Structure Rationale

- **`src/arrowdantic/` (Python):** Houses introspection logic that must call Pydantic's Python API (`model_fields`, `model_construct`, `model_validate_json`). This is the public-facing package users import.
- **`src/lib.rs` + Rust modules:** The `_core` extension module. Maturin's `module-name = "arrowdantic._core"` makes this a submodule. Users never import `_core` directly.
- **Separation rationale:** Pydantic introspection is easy in Python and hard in Rust (would require repeated Python callback overhead). Arrow iteration is fast in Rust and slow in Python (per-row overhead). The boundary is drawn exactly where the language advantage flips.

### Build System Change

The current project uses `uv_build` as its build backend. This **must change to `maturin`** because `uv_build` does not support native extension modules. The `pyproject.toml` will need:

```toml
[build-system]
requires = ["maturin>=1.0,<2.0"]
build-backend = "maturin"

[tool.maturin]
python-source = "src"
module-name = "arrowdantic._core"
features = ["pyo3/extension-module"]
```

## Architectural Patterns

### Pattern 1: Schema Mapper in Python, Hot Loop in Rust

**What:** Python code introspects the Pydantic model once at `ArrowModelConverter.__init__` time, producing a list of `FieldMapping` objects (column index, Python field name, Arrow data type, whether nullable). This list crosses the FFI boundary once. The Rust hot loop uses it for every row without calling back into Python for schema information.

**When to use:** Always -- this is the fundamental architecture of the library.

**Trade-offs:**
- Pro: Pydantic introspection uses the native Python API (trivial to implement)
- Pro: Rust loop touches zero Python API for schema resolution
- Pro: Mapping compiled once, amortized across potentially millions of rows
- Con: Requires defining a shared FieldMapping structure that both sides understand

**Example (Python side):**
```python
class ArrowModelConverter:
    def __init__(self, model_class: type[BaseModel], schema: pa.Schema):
        mappings = []
        for field_name, field_info in model_class.model_fields.items():
            # Resolve: validation_alias > alias > field_name
            arrow_name = _resolve_arrow_column_name(field_name, field_info)
            col_idx = schema.get_field_index(arrow_name)
            if col_idx == -1 and is_required(field_info):
                raise ValueError(f"Required field {arrow_name!r} not in Arrow schema")
            mappings.append(FieldMapping(
                col_idx=col_idx,
                py_field_name=field_name,
                arrow_type=schema.field(col_idx).type,
                nullable=field_info.is_required() is False,
            ))
        self._rust_converter = _core.BatchConverter(model_class, mappings)
```

### Pattern 2: Column-Oriented Extraction with Pre-Interned Strings

**What:** Rather than iterating row-by-row and extracting each cell, prepare column extractors once per batch, then iterate row indices. For each row, build a Python dict (or directly set attributes) using pre-interned Python string keys.

**When to use:** Always in the fast path. This avoids per-row string allocation.

**Trade-offs:**
- Pro: `intern!()` macro in PyO3 caches Python string objects in static storage -- zero allocation after first use
- Pro: Column-oriented access matches Arrow's memory layout (sequential reads within a column)
- Con: Must downcast each column to its concrete type before the row loop (type dispatch per column, not per cell)

**Example (Rust side):**
```rust
use pyo3::intern;

fn extract_row<'py>(
    py: Python<'py>,
    columns: &[ExtractedColumn],
    row_idx: usize,
    field_names: &[Bound<'py, PyString>],  // pre-interned
) -> PyResult<Bound<'py, PyDict>> {
    let dict = PyDict::new(py);
    for (col, name) in columns.iter().zip(field_names.iter()) {
        let value = col.extract_value(py, row_idx)?;
        dict.set_item(name, value)?;
    }
    Ok(dict)
}
```

### Pattern 3: Direct Model Construction via object.__setattr__

**What:** Instead of building a Python dict and passing it to `model_construct(**dict)`, create a bare model instance (via `cls.__new__(cls)`) and directly set `__dict__`, `__pydantic_fields_set__`, and `__pydantic_extra__` using `object.__setattr__`. This mirrors exactly what Pydantic's own `model_construct` does internally.

**When to use:** Fast path (default, `validate=False`). This eliminates dict unpacking overhead.

**Trade-offs:**
- Pro: Eliminates the Python-level `model_construct` call overhead (kwarg unpacking, default resolution)
- Pro: Pydantic's own implementation does exactly this (`_object_setattr = object.__setattr__`)
- Con: Tightly coupled to Pydantic v2 internals -- must set `__dict__`, `__pydantic_fields_set__`, `__pydantic_extra__`, `__pydantic_private__`
- Con: Must handle default values for fields not present in the Arrow data

**Example (Rust side):**
```rust
fn construct_model_instance<'py>(
    py: Python<'py>,
    model_cls: &Bound<'py, PyType>,
    fields_dict: Bound<'py, PyDict>,
    fields_set: Bound<'py, PyFrozenSet>,
) -> PyResult<Bound<'py, PyAny>> {
    let object_setattr = py
        .import("builtins")?
        .getattr("object")?
        .getattr("__setattr__")?;

    // cls.__new__(cls) -- bare instance, no __init__
    let instance = model_cls.call_method1("__new__", (model_cls,))?;

    object_setattr.call1((&instance, intern!(py, "__dict__"), &fields_dict))?;
    object_setattr.call1((&instance, intern!(py, "__pydantic_fields_set__"), &fields_set))?;
    object_setattr.call1((&instance, intern!(py, "__pydantic_extra__"), py.None()))?;
    object_setattr.call1((&instance, intern!(py, "__pydantic_private__"), py.None()))?;
    Ok(instance)
}
```

### Pattern 4: Arrow C Data Interface via PyCapsule (Zero-Copy Ingestion)

**What:** Use `pyo3-arrow`'s `PyRecordBatch` type in function signatures. PyO3 automatically converts any Python object that implements `__arrow_c_array__` (pyarrow RecordBatch, polars DataFrame exported via Arrow, etc.) into an arrow-rs `RecordBatch` via zero-copy FFI through PyCapsules.

**When to use:** Always. This is how Arrow data enters Rust.

**Trade-offs:**
- Pro: Zero-copy -- no serialization, no memory duplication
- Pro: Library-agnostic -- works with pyarrow, polars, any Arrow PyCapsule producer
- Pro: `pyo3-arrow` handles all the C FFI pointer management
- Con: Requires owned `PyRecordBatch` in function signatures (not references)

**Example (Rust side):**
```rust
use pyo3_arrow::PyRecordBatch;

#[pyfunction]
fn convert_batch(
    py: Python<'_>,
    batch: PyRecordBatch,  // auto-converts from any Arrow-compatible Python object
    /* ... */
) -> PyResult<Vec<PyObject>> {
    let record_batch = batch.into_inner();  // arrow-rs RecordBatch
    let schema = record_batch.schema();
    let num_rows = record_batch.num_rows();
    // ... iterate columns and rows
}
```

## Data Flow

### Fast Path (default, validate=False)

```
Python caller: from_arrow(MyModel, pyarrow_batch)
    |
    v
ArrowModelConverter.__init__(MyModel, batch.schema)
    |-- introspect model_fields
    |-- resolve aliases (validation_alias > alias > field_name)
    |-- build FieldMapping[] (col_idx, py_name, arrow_type, nullable)
    |-- validate: all required fields present in schema
    |-- store pre-computed mapping
    |
    v
ArrowModelConverter.convert(batch)
    |
    v
_core.convert_batch(batch, model_cls, mappings)   [FFI boundary]
    |
    v
PyRecordBatch.into_inner() -> arrow-rs RecordBatch  [zero-copy via PyCapsule]
    |
    v
For each FieldMapping:
    downcast column to concrete type (Int32Array, StringArray, etc.)
    prepare column extractor
    |
    v
For each row (0..num_rows):
    For each column extractor:
        check validity bitmap -> None or extract value -> PyObject
    Build PyDict with pre-interned field name keys
    |
    v
    cls.__new__(cls)
    object.__setattr__(instance, "__dict__", fields_dict)
    object.__setattr__(instance, "__pydantic_fields_set__", fields_set)
    object.__setattr__(instance, "__pydantic_extra__", None)
    object.__setattr__(instance, "__pydantic_private__", None)
    |
    v
    Append instance to results list
    |
    v
Return list[MyModel] to Python caller
```

### Validated Path (validate=True)

```
Python caller: from_arrow(MyModel, batch, validate=True)
    |
    v
[Same schema mapping as fast path]
    |
    v
_core.convert_batch_validated(batch, model_cls, mappings)
    |
    v
For each row (0..num_rows):
    Build serde_json::Value object from column values
    Serialize to JSON bytes via serde_json::to_vec()
    |
    v
    model_cls.model_validate_json(json_bytes)
    (Pydantic's jiter parser + SchemaValidator in pydantic-core)
    |
    v
    Append validated instance to results list
    |
    v
Return list[MyModel] to Python caller
```

### Key Data Flows

1. **Schema mapping (once):** `Pydantic model_fields` -> Python alias resolution -> `FieldMapping[]` list -> passed to Rust at converter init. No per-batch or per-row schema work in Rust.
2. **Arrow ingestion (per batch):** Python Arrow object -> PyCapsule FFI -> arrow-rs `RecordBatch` in Rust. Zero-copy.
3. **Value extraction (per cell):** arrow-rs typed array -> `is_valid(row)` bitmap check -> downcast to concrete value -> `PyObject` conversion via PyO3. Column-oriented.
4. **Instance creation (per row):** `PyDict` + `object.__setattr__` (fast path) or `serde_json::Value` -> `model_validate_json` (validated path).

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1-10K rows | No special handling needed. Single batch, single-threaded. |
| 10K-1M rows | Table with multiple batches. Iterate `table.to_batches()` in Python, process each in Rust. Pre-allocate result list with capacity hint. |
| 1M+ rows | Consider streaming API (`RecordBatchReader` -> iterator of model lists). Optionally release GIL during pure-Rust Arrow extraction (not during PyObject creation). |

### Scaling Priorities

1. **First bottleneck:** PyObject creation per cell. Every extracted value crosses the Rust-Python boundary. Mitigation: batch values where possible, minimize per-cell PyO3 overhead, use pre-interned strings.
2. **Second bottleneck:** `object.__setattr__` calls per row (4 calls per row for `__dict__`, `__pydantic_fields_set__`, `__pydantic_extra__`, `__pydantic_private__`). Mitigation: cache the `object.__setattr__` reference, use `intern!()` for attribute names.
3. **Third bottleneck:** Python list growth for results. Mitigation: pre-allocate `PyList` with known capacity (`num_rows`).

## Anti-Patterns

### Anti-Pattern 1: Schema Resolution in Rust via Python Callbacks

**What people do:** Pass the Pydantic model class to Rust and have Rust call `model_fields`, `field.alias`, etc. via PyO3 for each batch.
**Why it's wrong:** Every `getattr` / `call_method` from Rust into Python is an FFI crossing. Doing this per-batch (or worse, per-row) destroys performance. Pydantic's `model_fields` is a Python dict with Python `FieldInfo` objects -- natural to work with in Python, verbose to traverse from Rust.
**Do this instead:** Resolve schema entirely in Python at converter construction time. Pass a flat list of `FieldMapping` structs to Rust. Rust never touches Pydantic APIs.

### Anti-Pattern 2: Row-Oriented Arrow Access

**What people do:** For each row, iterate through columns and call `array.value(row_idx)` on the dynamically-typed `dyn Array`.
**Why it's wrong:** Dynamic dispatch per cell. Arrow's memory layout is columnar -- you should downcast each column once and then do typed, sequential access within that column.
**Do this instead:** Before the row loop, downcast all columns to concrete types (e.g., `Int32Array`, `StringArray`). Store typed references. In the row loop, index into pre-downcast arrays.

### Anti-Pattern 3: Building Python Dicts via model_construct(**kwargs)

**What people do:** Build a `PyDict`, convert to kwargs, call `model_construct(**dict)` from Rust.
**Why it's wrong:** `model_construct` does kwargs unpacking, default value resolution, and internal `object.__setattr__` -- all work you can do more efficiently from Rust by calling `object.__setattr__` directly.
**Do this instead:** Call `cls.__new__(cls)` to get a bare instance, then `object.__setattr__` for `__dict__`, `__pydantic_fields_set__`, `__pydantic_extra__`, `__pydantic_private__` directly. This is literally what `model_construct` does internally.

### Anti-Pattern 4: Holding GIL During Pure-Rust Computation

**What people do:** Keep the GIL held while doing arrow-rs column downcasting or serde_json serialization.
**Why it's wrong:** Blocks other Python threads unnecessarily during work that doesn't touch Python objects.
**Do this instead:** Release the GIL with `py.allow_threads(|| { ... })` for pure-Rust operations (column prep, JSON serialization). Re-acquire for PyObject creation.

## Integration Points

### External Libraries

| Library | Integration Pattern | Notes |
|---------|---------------------|-------|
| **pydantic v2** | `model_fields` introspection (Python), `model_validate_json` (validated path), `object.__setattr__` pattern (fast path) | Must handle v2 API only. `model_construct` behavior is stable since Pydantic 2.0. |
| **pyarrow** | Input via `__arrow_c_array__` PyCapsule, optional runtime dependency | Users need pyarrow (or polars, etc.) to produce Arrow data. `pyo3-arrow` handles the rest. |
| **polars** | Input via `__arrow_c_stream__` on DataFrame export | No Polars-specific code needed -- C Data Interface handles it transparently. |
| **arrow-rs** | `RecordBatch` iteration, typed array downcasting, validity bitmap access | Rust-side only. Users never see arrow-rs. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| **Python wrapper <-> Rust _core** | `FieldMapping` list + `PyRecordBatch` via PyO3 function call | One FFI crossing per batch conversion. FieldMapping is a simple struct (col_idx, name, type enum). |
| **Ingestion <-> Extraction** | `RecordBatch` (arrow-rs) passed internally | Pure Rust, no FFI. `into_inner()` gives owned `RecordBatch`. |
| **Extraction <-> Construction** | `Vec<PyObject>` column values assembled into `PyDict` per row | Rust-internal, but creates Python objects (requires GIL). |
| **Fast path <-> Validated path** | Selected by `validate` bool flag | Same input (RecordBatch + mappings), different output strategy. |

## Build Order (Dependencies Between Components)

The components have clear dependency ordering that should guide phase structure:

```
1. Build system (maturin + Cargo.toml)
   |
   v
2. Minimal PyO3 module skeleton (_core with one dummy function)
   |
   v
3. Arrow ingestion (pyo3-arrow PyRecordBatch -> RecordBatch)
   |
   v
4. Scalar type extractors (Int, Float, Bool, Utf8 -> PyObject)
   |
   v
5. Row construction (object.__setattr__ fast path)
   |
   v
6. Python schema mapper (model_fields introspection, alias resolution)
   |
   v
7. Full integration (ArrowModelConverter, from_arrow convenience)
   |
   v
8. Extended types (Date, Timestamp, List, Struct, Dictionary, Null)
   |
   v
9. Validated path (serde_json -> model_validate_json)
   |
   v
10. Performance optimization (GIL release, pre-interned strings, benchmarks)
```

Steps 1-7 form the minimal viable product. Steps 8-10 extend coverage and polish.

## Sources

- [pyo3-arrow API docs](https://docs.rs/pyo3-arrow/latest/pyo3_arrow/index.html) -- PyRecordBatch, PyArray, PyCapsule interface
- [pyo3-arrow PyRecordBatch](https://docs.rs/pyo3-arrow/latest/pyo3_arrow/struct.PyRecordBatch.html) -- `into_inner()`, `as_ref()`, construction methods
- [PyO3 intern! macro](https://pyo3.rs/main/doc/pyo3/macro.intern) -- string interning for performance
- [PyO3 object.__setattr__ discussion](https://github.com/PyO3/pyo3/discussions/2321) -- bypassing custom `__setattr__` from Rust
- [Pydantic model_construct source](https://github.com/pydantic/pydantic/blob/main/pydantic/main.py) -- confirms `object.__setattr__` used internally
- [Pydantic _model_construction.py](https://github.com/pydantic/pydantic/blob/main/pydantic/_internal/_model_construction.py) -- `object_setattr = object.__setattr__`
- [Pydantic BaseModel API](https://docs.pydantic.dev/latest/api/base_model/) -- `model_construct`, `model_validate_json` signatures
- [pydantic-core issue #1364](https://github.com/pydantic/pydantic-core/issues/1364) -- confirms no native Rust Pydantic construction API
- [Maturin project layout](https://www.maturin.rs/project_layout.html) -- mixed Rust/Python layout, `module-name` config, `python-source`
- [arro3 repository](https://github.com/kylebarron/arro3) -- reference architecture for pyo3-arrow usage
- [arrow-rs RecordBatch](https://docs.rs/arrow/latest/arrow/record_batch/struct.RecordBatch.html) -- column access, schema, downcasting patterns
- [uv project init docs](https://docs.astral.sh/uv/concepts/projects/init/) -- confirms `uv_build` cannot build native extensions

---
*Architecture research for: Rust/PyO3 Arrow-to-Pydantic conversion library*
*Researched: 2026-03-21*
