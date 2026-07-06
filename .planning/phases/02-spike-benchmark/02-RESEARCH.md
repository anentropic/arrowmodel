# Phase 2: Spike & Benchmark - Research

**Researched:** 2026-03-22
**Domain:** Rust/PyO3 Arrow column extraction, Pydantic model_construct interop, benchmarking
**Confidence:** HIGH

## Summary

Phase 2 implements a minimal end-to-end conversion path from an Arrow `RecordBatch` to Pydantic model instances for primitive types (int, uint, float, bool, string), with null handling and a benchmark proving speedup over `to_pylist()` + `model_construct`. The Rust core needs: (1) column-oriented downcasting of Arrow arrays to concrete types, (2) per-row validity bitmap checks before value extraction, (3) PyObject creation for each extracted value, and (4) calling Pydantic's `model_construct` with a PyDict as kwargs. The Python wrapper needs: (1) an `ArrowModelConverter` class that cross-references Arrow schema against Pydantic `model_fields` at init time, and (2) a `convert()` method that delegates to the Rust hot loop.

The critical PyO3 patterns are well-established: `call_method("model_construct", (), Some(&kwargs_dict))` for model construction, `PyString::intern(py, &field_name)` for runtime string interning (since `intern!()` only works with compile-time literals), and arrow-rs's `as_primitive_array`/`as_string_array`/`as_boolean_array` convenience casts for column downcasting. The benchmark should use `pytest-benchmark` (v5.2.3) for reproducible, statistically-sound comparisons with proper warm-up and calibration.

**Primary recommendation:** Implement the spike as a single Rust function `convert_record_batch` that accepts `PyRecordBatch`, the model class, and a list of field mappings (column index, field name, type tag). Use `model_construct(**dict)` via `call_method` for the initial spike; defer the `object.__setattr__` optimization to Phase 3 (FAST-02).

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCHEMA-01 | ArrowModelConverter cross-references Arrow schema against Pydantic model fields at construction time | Python-side `model_fields` introspection pattern documented; field-name matching (no aliases in spike) |
| SCHEMA-02 | Schema mapping compiled once at converter init, reused across all batches | FieldMapping list pattern: build once in Python `__init__`, pass to Rust, reuse per batch |
| TYPE-01 | Int8, Int16, Int32, Int64 -> int | arrow-rs `as_primitive_array::<Int8Type>()` etc. + PyO3 auto-converts Rust i8/i16/i32/i64 to Python int |
| TYPE-02 | UInt8, UInt16, UInt32, UInt64 -> int | Same pattern with UInt8Type..UInt64Type; PyO3 auto-converts u8/u16/u32/u64 to Python int |
| TYPE-03 | Float32, Float64 -> float | `as_primitive_array::<Float32Type>()` etc.; PyO3 auto-converts f32/f64 to Python float |
| TYPE-04 | Boolean -> bool (bit-packed, unpack via validity bitmap) | BooleanArray.value(i) returns bool, bit-unpacking is internal; validity bitmap is separate |
| TYPE-05 | Utf8, LargeUtf8 -> str | `as_string_array()` / `as_largestring_array()` + `value(i)` returns `&str`; PyO3 converts to Python str |
| NULL-01 | Null detection via Arrow validity bitmap before value extraction | Array trait `is_valid(i)` / `is_null(i)` checks physical null buffer |
| NULL-02 | Null values emit None for nullable/optional Pydantic fields | When `is_null(i)` is true, emit `py.None()` instead of extracting value |
| NULL-03 | Value buffer at null indices never read | Pattern: `if array.is_valid(i) { array.value(i) } else { py.None() }` -- value() never called at null indices |
| FAST-01 | Default conversion uses model_construct -- no Pydantic validation, dict-free row construction | `call_method("model_construct", (), Some(&kwargs))` from Rust; kwargs is a PyDict with field values |
| FAST-03 | Column values extracted directly from Arrow buffers in Rust, no intermediate Python dict | Arrow column values extracted in Rust via typed array access; PyDict built per-row is the kwargs target, not an intermediate representation |
| INPUT-01 | Accept pyarrow RecordBatch as input | pyo3-arrow `PyRecordBatch` auto-converts any PyCapsule-compatible RecordBatch |
| API-01 | ArrowModelConverter(Model, validate=False) constructor | Python class with `__init__` that introspects model_fields and builds field mappings |
| API-02 | converter.convert(data) returns list[Model] | Python method that calls Rust `convert_record_batch` and returns the result list |
</phase_requirements>

## Standard Stack

### Core (already installed from Phase 1)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pyo3 | 0.28.2 | Rust-Python FFI | Already in Cargo.toml; `call_method` for model_construct, `PyDict` for kwargs, `PyString::intern` for field names |
| pyo3-arrow | 0.17 | Arrow C Data Interface | Already in Cargo.toml; `PyRecordBatch` for zero-copy ingestion |
| arrow-array | 58 | Typed array access | Already in Cargo.toml; `as_primitive_array`, `as_string_array`, `as_boolean_array` for column downcasting |
| arrow-schema | 58 | Schema/DataType inspection | Already in Cargo.toml; `DataType` enum matching for type dispatch |
| pydantic | >=2.11 | Model construction | Already in pyproject.toml; `model_fields` introspection, `model_construct(**kwargs)` |

### New Dependencies for Phase 2

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-benchmark | >=5.2.3 | Performance benchmarks | Benchmark script comparing arrowdantic vs to_pylist() + model_construct |

**Installation:**
```bash
uv add --dev "pytest-benchmark>=5.2.3"
```

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pytest-benchmark | timeit module | timeit is simpler but lacks statistical rigor (no warm-up calibration, no outlier detection, no comparison tables). pytest-benchmark integrates with existing pytest infrastructure. |
| pytest-benchmark | richbench | richbench has nice output but no pytest integration, no statistical analysis |

## Architecture Patterns

### Recommended Project Structure (Phase 2 additions)

```
arrowdantic/
+-- rust/
|   +-- src/
|   |   +-- lib.rs              # Add convert_record_batch function
|   |   +-- extract.rs          # NEW: Column extractor enum + value extraction
+-- src/
|   +-- arrowdantic/
|   |   +-- __init__.py         # Add ArrowModelConverter class, from_arrow convenience
+-- tests/
|   +-- test_smoke.py           # Existing Phase 1 tests
|   +-- test_convert.py         # NEW: Conversion correctness tests
|   +-- conftest.py             # Add typed fixtures (int, float, bool, string, null batches)
+-- benchmarks/
|   +-- bench_convert.py        # NEW: pytest-benchmark comparisons
```

### Pattern 1: Field Mapping Struct

**What:** A simple data structure passed from Python to Rust containing the pre-computed column-to-field mapping. For the spike, this is minimal: column index, Python field name, and a type tag.

**When to use:** Always. Built once at `ArrowModelConverter.__init__`, reused for every `convert()` call.

**Example (Python side):**
```python
class ArrowModelConverter:
    def __init__(self, model_class: type[BaseModel], *, validate: bool = False):
        self._model_class = model_class
        self._validate = validate
        # Store field names for schema matching at convert() time
        self._field_names = list(model_class.model_fields.keys())

    def convert(self, data: pa.RecordBatch) -> list[BaseModel]:
        schema = data.schema
        # Build mappings: match Arrow column names to Pydantic field names
        col_indices = []
        field_names = []
        for field_name in self._field_names:
            col_idx = schema.get_field_index(field_name)
            if col_idx < 0:
                raise ValueError(f"Arrow schema missing field: {field_name!r}")
            col_indices.append(col_idx)
            field_names.append(field_name)
        return _core.convert_record_batch(
            data, self._model_class, col_indices, field_names
        )
```

### Pattern 2: Column-Oriented Downcast-Once in Rust

**What:** Before the row loop, downcast every needed column from `dyn Array` to its concrete typed array (e.g., `Int32Array`, `StringArray`). Store these typed references. In the row loop, index into pre-downcast arrays.

**When to use:** Always. This avoids dynamic dispatch per cell.

**Example (Rust side):**
```rust
use arrow_array::cast::{as_primitive_array, as_string_array, as_boolean_array};
use arrow_array::types::*;
use arrow_schema::DataType;

enum ColumnExtractor<'a> {
    Int8(&'a Int8Array),
    Int16(&'a Int16Array),
    Int32(&'a Int32Array),
    Int64(&'a Int64Array),
    UInt8(&'a UInt8Array),
    UInt16(&'a UInt16Array),
    UInt32(&'a UInt32Array),
    UInt64(&'a UInt64Array),
    Float32(&'a Float32Array),
    Float64(&'a Float64Array),
    Boolean(&'a BooleanArray),
    Utf8(&'a StringArray),
    LargeUtf8(&'a LargeStringArray),
}

fn prepare_extractor<'a>(
    col: &'a dyn Array,
    data_type: &DataType,
) -> Result<ColumnExtractor<'a>, PyErr> {
    match data_type {
        DataType::Int8 => Ok(ColumnExtractor::Int8(as_primitive_array(col))),
        DataType::Int32 => Ok(ColumnExtractor::Int32(as_primitive_array(col))),
        DataType::Utf8 => Ok(ColumnExtractor::Utf8(as_string_array(col))),
        DataType::Boolean => Ok(ColumnExtractor::Boolean(as_boolean_array(col))),
        // ... other types
        _ => Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
            format!("Unsupported Arrow type: {data_type:?}")
        )),
    }
}
```

### Pattern 3: Null-Safe Value Extraction to PyObject

**What:** For each cell, check `is_valid(i)` before calling `value(i)`. If null, produce `py.None()`. If valid, extract the typed value and convert to PyObject via PyO3's automatic conversions.

**When to use:** Always. Arrow spec states value buffer at null indices contains undefined data.

**Example (Rust side):**
```rust
impl<'a> ColumnExtractor<'a> {
    fn extract_value<'py>(
        &self,
        py: Python<'py>,
        row: usize,
    ) -> PyResult<PyObject> {
        match self {
            ColumnExtractor::Int32(arr) => {
                if arr.is_null(row) {
                    Ok(py.None())
                } else {
                    Ok(arr.value(row).into_pyobject(py)?.into_any().unbind())
                }
            }
            ColumnExtractor::Utf8(arr) => {
                if arr.is_null(row) {
                    Ok(py.None())
                } else {
                    Ok(PyString::new(py, arr.value(row)).into_any().unbind())
                }
            }
            ColumnExtractor::Boolean(arr) => {
                if arr.is_null(row) {
                    Ok(py.None())
                } else {
                    Ok(arr.value(row).into_pyobject(py)?.into_any().unbind())
                }
            }
            // ... other types follow same pattern
        }
    }
}
```

### Pattern 4: model_construct via call_method with kwargs PyDict

**What:** For each row, build a `PyDict` with field names as keys and extracted values as values, then call `model_class.call_method("model_construct", (), Some(&kwargs))`.

**When to use:** Phase 2 spike. The `object.__setattr__` optimization (Pattern 3 from ARCHITECTURE.md) is deferred to Phase 3.

**Why model_construct first:** It is the documented public API. Starting with `model_construct` gives us a correct baseline before optimizing with internal `__setattr__` calls.

**Example (Rust side):**
```rust
fn construct_models<'py>(
    py: Python<'py>,
    record_batch: &RecordBatch,
    model_cls: &Bound<'py, PyAny>,
    col_indices: &[usize],
    field_names: &[Bound<'py, PyString>],  // pre-interned
) -> PyResult<Bound<'py, PyList>> {
    let num_rows = record_batch.num_rows();
    let result = PyList::empty(py);

    // 1. Prepare column extractors (downcast once)
    let extractors: Vec<ColumnExtractor> = col_indices.iter()
        .map(|&idx| {
            let col = record_batch.column(idx);
            let dt = record_batch.schema().field(idx).data_type();
            prepare_extractor(col.as_ref(), dt)
        })
        .collect::<Result<_, _>>()?;

    // 2. Row loop
    for row in 0..num_rows {
        let kwargs = PyDict::new(py);
        for (extractor, name) in extractors.iter().zip(field_names.iter()) {
            let value = extractor.extract_value(py, row)?;
            kwargs.set_item(name, value)?;
        }
        // model_construct(**kwargs) -- no validation
        let instance = model_cls.call_method("model_construct", (), Some(&kwargs))?;
        result.append(instance)?;
    }

    Ok(result)
}
```

### Pattern 5: Runtime String Interning for Field Names

**What:** The `intern!()` macro only works with compile-time string literals. Since field names are determined at runtime (from Pydantic model introspection), use `PyString::intern(py, &field_name)` instead. This calls Python's `sys.intern()` under the hood, ensuring the same PyString object is reused for identical field names across all rows.

**When to use:** When caching field name strings that are known at converter-init time but not at compile time. Intern once per field name when the converter is created or at the start of `convert_record_batch`, then reuse the interned `Bound<'py, PyString>` for every row.

**Critical detail:** `PyString::intern` is slightly slower than `intern!()` for the first call (allocates a temporary string), but subsequent lookups return the same Python string object. For field names interned once and reused across 100k+ rows, the amortized cost is negligible.

**Example:**
```rust
// At the start of convert_record_batch, intern all field names once
let interned_names: Vec<Bound<'py, PyString>> = field_names
    .iter()
    .map(|name| PyString::intern(py, name))
    .collect();

// In the row loop, use interned_names[i] as dict keys -- zero allocation per row
```

### Anti-Patterns to Avoid

- **Row-oriented Arrow access:** Do not iterate rows first and extract columns within each row. Arrow's memory layout is columnar; downcast each column once before the row loop.
- **Dynamic dispatch per cell:** Do not match on `DataType` inside the row loop. Match once per column to create a `ColumnExtractor`, then the row loop uses the enum variant directly.
- **Calling model_fields from Rust:** Do not introspect Pydantic's model_fields dict from Rust via PyO3. Each `getattr`/`call_method` is an FFI crossing. Do all introspection in Python and pass flat data to Rust.
- **Creating new PyString per row:** Do not call `PyString::new(py, &field_name)` inside the row loop. Intern once before the loop.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Arrow column downcasting | Manual `as_any().downcast_ref()` chains | `as_primitive_array::<T>()`, `as_string_array()`, `as_boolean_array()` from `arrow_array::cast` | Convenience functions handle the downcast and panic on type mismatch; cleaner code |
| Null bitmap checking | Manual bit manipulation on null buffer | `Array::is_valid(i)` / `Array::is_null(i)` trait methods | Arrow-rs encapsulates all bitmap logic; handles missing null buffer (all-valid) automatically |
| Python string interning | Manual HashMap of string references | `PyString::intern(py, &s)` from pyo3 | Uses Python's native `sys.intern()` machinery with proper memory management |
| Benchmark statistics | Manual timing with `time.time()` | `pytest-benchmark` fixture | Handles warm-up, calibration, outlier detection, statistical comparison tables |
| Model construction | Custom `__new__` + `__setattr__` calls (in spike) | `model_construct(**kwargs)` via `call_method` | Public API, handles defaults, sets all required internal attributes correctly. Optimization deferred to Phase 3. |

**Key insight:** The spike should use established APIs (`model_construct`, `as_primitive_array`, `is_valid`) rather than internal optimizations. The benchmark will tell us whether `model_construct` overhead is the bottleneck, guiding Phase 3 optimization decisions.

## Common Pitfalls

### Pitfall 1: intern!() vs PyString::intern confusion

**What goes wrong:** Developer uses `intern!(py, field_name)` where `field_name` is a runtime `&str` variable, expecting it to work like `PyString::intern`. The `intern!()` macro requires a string literal at compile time and will fail to compile with a variable.

**Why it happens:** The naming similarity is misleading. `intern!()` is a macro that creates a `static` Python string; `PyString::intern()` is a method that calls Python's `sys.intern()` at runtime.

**How to avoid:** Use `intern!(py, "known_literal")` only for fixed strings like `"model_construct"`, `"__dict__"`, etc. Use `PyString::intern(py, &runtime_string)` for field names discovered at runtime.

**Warning signs:** Compile error mentioning "expected a string literal" or "cannot use a variable in macro invocation".

### Pitfall 2: Reading Arrow value buffer at null indices

**What goes wrong:** Calling `array.value(i)` without checking `is_valid(i)` first. The Arrow spec states that value buffer contents at null indices are undefined (could be zero, garbage, or even out-of-bounds offsets for variable-length types like Utf8).

**Why it happens:** The Rust API does not panic on null reads -- it returns whatever bytes are in the buffer, which may appear valid.

**How to avoid:** Always check `is_valid(i)` (or `is_null(i)`) before `value(i)`. The `if is_valid { value(i) } else { py.None() }` pattern is the canonical approach.

**Warning signs:** Incorrect values in output for rows that should be None; random-looking data; potential panics on malformed offset buffers in string arrays.

### Pitfall 3: PyDict kwargs vs positional arg for model_construct

**What goes wrong:** Calling `model_cls.call_method1("model_construct", (dict,))` passes the dict as a single positional argument. `model_construct` expects `**kwargs`, not a dict positional arg.

**Why it happens:** `call_method1` only takes positional args. The dict is passed as the first positional arg, which gets bound to `_fields_set` (wrong semantics).

**How to avoid:** Use `call_method("model_construct", (), Some(&kwargs_dict))` -- this unpacks the dict as keyword arguments, which is what `model_construct(**values)` expects.

**Warning signs:** `TypeError` or models constructed with empty fields. `model_fields_set` containing the dict itself rather than field names.

### Pitfall 4: Benchmark comparing apples to oranges

**What goes wrong:** Benchmark includes pyarrow `RecordBatch` creation time in the arrowdantic measurement but not in the baseline, or vice versa.

**Why it happens:** The arrowdantic path accepts a RecordBatch and returns models. The baseline path starts from `batch.to_pylist()` (which is pyarrow work). If the benchmark measures from different starting points, the comparison is meaningless.

**How to avoid:** Both benchmark paths should start from the same pre-created `RecordBatch` object. The benchmark should measure only: (a) arrowdantic: `converter.convert(batch)`, (b) baseline: `[Model.model_construct(**row) for row in batch.to_pylist()]`. The batch creation is in the fixture/setup, not in the measured code.

**Warning signs:** Speedup numbers that seem too good (>100x) or too bad (<1x) for primitive types.

### Pitfall 5: Forgetting to pre-allocate the result list

**What goes wrong:** Using `PyList::empty(py)` and appending one-by-one causes Python list to resize multiple times for large batches.

**Why it happens:** Python lists grow by ~12.5% when they need to resize. For 100k+ rows, this means many reallocations.

**How to avoid:** Use `PyList::new(py, &vec![py.None(); num_rows])` or collect into a `Vec<PyObject>` in Rust first and then convert to `PyList` at the end.

**Warning signs:** Memory allocation showing up as a hot spot in profiles.

### Pitfall 6: BooleanArray validity bitmap vs value bitmap confusion

**What goes wrong:** Boolean values in Arrow are bit-packed (1 bit per value). The null/validity bitmap is a separate bit-packed buffer. Confusing the two leads to reading validity as value or vice versa.

**Why it happens:** Both are bit-packed buffers accessed by index, and `BooleanArray` has both.

**How to avoid:** Use the typed API: `array.is_valid(i)` for null checking, `array.value(i)` for the boolean value. Never access the underlying buffers directly in the spike.

**Warning signs:** Booleans that appear inverted or that flip between `True` and `None`.

## Code Examples

Verified patterns from official sources:

### PyO3: Calling model_construct with kwargs
```rust
// Source: PyO3 user guide - Calling Python functions
// https://pyo3.rs/main/python-from-rust/function-calls.html
use pyo3::prelude::*;
use pyo3::types::PyDict;

fn construct_model<'py>(
    py: Python<'py>,
    model_cls: &Bound<'py, PyAny>,
    field_names: &[Bound<'py, PyString>],
    values: &[PyObject],
) -> PyResult<Bound<'py, PyAny>> {
    let kwargs = PyDict::new(py);
    for (name, val) in field_names.iter().zip(values.iter()) {
        kwargs.set_item(name, val)?;
    }
    model_cls.call_method("model_construct", (), Some(&kwargs))
}
```

### PyO3: Runtime string interning
```rust
// Source: PyO3 docs - PyString::intern
// https://pyo3.rs/main/doc/pyo3/types/struct.pystring
use pyo3::types::PyString;

// Intern once, reuse across all rows
let interned: Bound<'py, PyString> = PyString::intern(py, "field_name");
// Every subsequent call with the same string returns the same Python object
let same_ref: Bound<'py, PyString> = PyString::intern(py, "field_name");
// interned and same_ref point to the same Python string object
```

### Arrow-rs: Column downcast and value extraction
```rust
// Source: arrow-array cast module
// https://docs.rs/arrow-array/latest/arrow_array/cast/index.html
use arrow_array::cast::{as_primitive_array, as_string_array, as_boolean_array};
use arrow_array::types::Int32Type;
use arrow_array::Array;

let col = record_batch.column(0);
let int_array = as_primitive_array::<Int32Type>(col);

for row in 0..int_array.len() {
    if int_array.is_valid(row) {
        let val: i32 = int_array.value(row);
        // convert to PyObject
    } else {
        // emit py.None()
    }
}
```

### Arrow-rs: BooleanArray extraction
```rust
// Source: arrow-array BooleanArray
// https://docs.rs/arrow-array/latest/arrow_array/array/struct.BooleanArray.html
use arrow_array::BooleanArray;

let bool_col: &BooleanArray = as_boolean_array(record_batch.column(idx));
for row in 0..bool_col.len() {
    if bool_col.is_valid(row) {
        let val: bool = bool_col.value(row);  // bit-unpacked automatically
    }
}
```

### PyO3: Receiving RecordBatch from Python
```rust
// Source: pyo3-arrow docs
// https://docs.rs/pyo3-arrow/latest/pyo3_arrow/
use pyo3_arrow::PyRecordBatch;

#[pyfunction]
fn convert_record_batch(
    py: Python<'_>,
    batch: PyRecordBatch,
    model_cls: Bound<'_, PyAny>,
    col_indices: Vec<usize>,
    field_names: Vec<String>,
) -> PyResult<Bound<'_, PyList>> {
    let rb = batch.into_inner();
    // ... extraction and construction logic
}
```

### pytest-benchmark: Comparison benchmark
```python
# Source: pytest-benchmark usage docs
# https://pytest-benchmark.readthedocs.io/en/latest/usage.html
import pyarrow as pa
from pydantic import BaseModel
from arrowdantic import ArrowModelConverter

class SimpleModel(BaseModel):
    id: int
    name: str
    score: float
    active: bool

def make_batch(n: int) -> pa.RecordBatch:
    return pa.record_batch({
        "id": list(range(n)),
        "name": [f"item_{i}" for i in range(n)],
        "score": [float(i) * 0.1 for i in range(n)],
        "active": [i % 2 == 0 for i in range(n)],
    })

def test_arrowdantic_vs_pylist(benchmark):
    batch = make_batch(100_000)
    converter = ArrowModelConverter(SimpleModel)
    result = benchmark(converter.convert, batch)
    assert len(result) == 100_000
    assert isinstance(result[0], SimpleModel)

def test_baseline_to_pylist(benchmark):
    batch = make_batch(100_000)
    def baseline():
        return [SimpleModel.model_construct(**row) for row in batch.to_pylist()]
    result = benchmark(baseline)
    assert len(result) == 100_000
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `as_any().downcast_ref::<Int32Array>()` | `as_primitive_array::<Int32Type>(col)` | arrow-rs 40+ | Cleaner code, same performance |
| `PyString::new(py, s)` per row | `PyString::intern(py, s)` once + reuse | PyO3 0.17+ (PR #2268) | Eliminates per-row string allocation for dict keys |
| pyo3 `call_method1` for kwargs | `call_method` with `Option<&PyDict>` | PyO3 0.19+ (Bound API) | Correct kwargs unpacking for `model_construct(**values)` |
| `intern!(py, "literal")` for all strings | `intern!` for literals + `PyString::intern` for runtime | Always (different tools) | Compile-time vs runtime interning serve different use cases |

**Deprecated/outdated:**
- `GIL Refs` (e.g., `&PyDict`, `&PyString`): Deprecated in PyO3 0.21+, replaced by `Bound<'py, PyDict>`, `Bound<'py, PyString>`. Must use the `Bound` API throughout.

## Open Questions

1. **Pre-allocating PyList with capacity**
   - What we know: `PyList::empty(py)` does not pre-allocate. PyO3 does not expose a direct `PyList::with_capacity`.
   - What's unclear: Whether collecting into `Vec<PyObject>` in Rust first and then converting to `PyList` via `PyList::new(py, &results_vec)` is faster than appending one-by-one.
   - Recommendation: Start with `Vec<PyObject>` collection + final `PyList::new()`. The benchmark will reveal if this matters.

2. **Schema mismatch handling**
   - What we know: Phase 2 requires field-name matching only (no aliases). If a Pydantic field name is not found in the Arrow schema, it should error at convert() time.
   - What's unclear: Whether schema validation should happen eagerly (at `ArrowModelConverter.__init__`) or lazily (at first `convert()` call). The init-time approach requires passing the schema at init, but the spike description shows only the model class at init.
   - Recommendation: For the spike, do schema matching at `convert()` time since each batch could have a different schema. Cache the mapping after first call if the schema matches.

3. **into_pyobject vs into_py for primitive conversions**
   - What we know: PyO3 0.28 deprecated `IntoPy` in favor of `IntoPyObject`. The new trait provides `into_pyobject(py)` which returns a `Bound<'py, T>`.
   - What's unclear: The exact ergonomics of converting `i32` -> `PyObject` using the new API (`value.into_pyobject(py)?.into_any().unbind()` vs older patterns).
   - Recommendation: Use `into_pyobject(py)?.into_any().unbind()` for the spike. This is the forward-compatible pattern.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ (already installed) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_convert.py -x` |
| Full suite command | `uv run pytest -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCHEMA-01 | Converter cross-references Arrow schema with model fields | unit | `uv run pytest tests/test_convert.py::TestSchemaMapping -x` | No -- Wave 0 |
| SCHEMA-02 | Mapping reused across multiple batches | unit | `uv run pytest tests/test_convert.py::TestSchemaMapping::test_mapping_reuse -x` | No -- Wave 0 |
| TYPE-01 | Int types -> Python int | unit | `uv run pytest tests/test_convert.py::TestPrimitiveTypes::test_int_types -x` | No -- Wave 0 |
| TYPE-02 | UInt types -> Python int | unit | `uv run pytest tests/test_convert.py::TestPrimitiveTypes::test_uint_types -x` | No -- Wave 0 |
| TYPE-03 | Float types -> Python float | unit | `uv run pytest tests/test_convert.py::TestPrimitiveTypes::test_float_types -x` | No -- Wave 0 |
| TYPE-04 | Boolean -> Python bool (bit-packed) | unit | `uv run pytest tests/test_convert.py::TestPrimitiveTypes::test_bool_type -x` | No -- Wave 0 |
| TYPE-05 | Utf8/LargeUtf8 -> Python str | unit | `uv run pytest tests/test_convert.py::TestPrimitiveTypes::test_string_types -x` | No -- Wave 0 |
| NULL-01 | Null detection via validity bitmap | unit | `uv run pytest tests/test_convert.py::TestNullHandling::test_null_detection -x` | No -- Wave 0 |
| NULL-02 | Null values -> None | unit | `uv run pytest tests/test_convert.py::TestNullHandling::test_null_produces_none -x` | No -- Wave 0 |
| NULL-03 | Value buffer at null indices never read | unit | `uv run pytest tests/test_convert.py::TestNullHandling::test_null_indices_not_read -x` | No -- Wave 0 |
| FAST-01 | Uses model_construct, no validation | unit | `uv run pytest tests/test_convert.py::TestModelConstruct -x` | No -- Wave 0 |
| FAST-03 | Values from Arrow buffers, no intermediate Python dict | integration | `uv run pytest tests/test_convert.py::TestEndToEnd -x` | No -- Wave 0 |
| INPUT-01 | Accept pyarrow RecordBatch | integration | `uv run pytest tests/test_convert.py::TestEndToEnd::test_accepts_record_batch -x` | No -- Wave 0 |
| API-01 | ArrowModelConverter(Model) constructor | unit | `uv run pytest tests/test_convert.py::TestAPI::test_constructor -x` | No -- Wave 0 |
| API-02 | converter.convert(data) -> list[Model] | integration | `uv run pytest tests/test_convert.py::TestAPI::test_convert_returns_list -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_convert.py -x`
- **Per wave merge:** `uv run pytest -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_convert.py` -- covers SCHEMA-01, SCHEMA-02, TYPE-01-05, NULL-01-03, FAST-01, FAST-03, INPUT-01, API-01, API-02
- [ ] `tests/conftest.py` -- add fixtures for typed batches (all-int, all-string, mixed, nullable)
- [ ] `benchmarks/bench_convert.py` -- benchmark comparison (pytest-benchmark)
- [ ] Dev dependency: `uv add --dev "pytest-benchmark>=5.2.3"` -- for benchmark tests

## Sources

### Primary (HIGH confidence)
- [PyO3 user guide - Function calls](https://pyo3.rs/main/python-from-rust/function-calls.html) - call_method with kwargs, PyDict patterns
- [PyO3 PyString::intern](https://pyo3.rs/main/doc/pyo3/types/struct.pystring) - runtime string interning, signature `pub fn intern(py, s: &str) -> Bound<'py, PyString>`
- [PyO3 intern! macro](https://pyo3.rs/main/doc/pyo3/macro.intern) - compile-time-only string interning, confirmed literal-only
- [arrow-array cast module](https://docs.rs/arrow-array/latest/arrow_array/cast/index.html) - as_primitive_array, as_string_array, as_boolean_array convenience functions
- [arrow-array Array trait](https://docs.rs/arrow/latest/arrow/array/trait.Array.html) - is_valid(i), is_null(i), null_count()
- [arrow-array PrimitiveArray](https://docs.rs/arrow-array/latest/arrow_array/array/struct.PrimitiveArray.html) - value(i) method, values() buffer access
- [arrow-array BooleanArray](https://docs.rs/arrow-array/latest/arrow_array/array/struct.BooleanArray.html) - bit-packed value(i), separate validity bitmap
- [arrow-array GenericByteArray](https://docs.rs/arrow-array/latest/arrow_array/array/struct.GenericByteArray.html) - StringArray value(i) returns &str
- [pyo3-arrow PyRecordBatch](https://docs.rs/pyo3-arrow/latest/pyo3_arrow/struct.PyRecordBatch.html) - into_inner() for zero-copy RecordBatch
- [Pydantic BaseModel API](https://docs.pydantic.dev/latest/api/base_model/) - model_construct signature: `cls, _fields_set=None, **values`
- [pytest-benchmark docs](https://pytest-benchmark.readthedocs.io/en/latest/usage.html) - fixture-based benchmarking, grouping, parametrize

### Secondary (MEDIUM confidence)
- [PyO3 PyString::intern PR #2268](https://github.com/PyO3/pyo3/pull/2268) - confirms PyString::intern wraps Python's sys.intern()
- [Pydantic model_construct source](https://github.com/pydantic/pydantic/blob/main/pydantic/main.py) - confirms object.__setattr__ used internally
- [arrow-rs downcast_array](https://docs.rs/arrow/latest/arrow/array/cast/fn.downcast_array.html) - generic downcasting example with RecordBatch

### Tertiary (LOW confidence)
- None -- all findings verified against official documentation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already installed from Phase 1 except pytest-benchmark (verified on PyPI)
- Architecture: HIGH - patterns verified against official PyO3/arrow-rs/Pydantic docs
- Pitfalls: HIGH - each pitfall grounded in API documentation (intern! macro limitations, Arrow null spec, call_method vs call_method1 semantics)
- Benchmarking: HIGH - pytest-benchmark 5.2.3 is current and well-documented

**Research date:** 2026-03-22
**Valid until:** 2026-04-22 (stable libraries, no expected breaking changes)
