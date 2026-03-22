# Phase 5: Validated Path and API Polish - Research

**Researched:** 2026-03-22
**Domain:** Pydantic validated conversion, Python iterator protocol, type stubs for PyO3
**Confidence:** HIGH

## Summary

Phase 5 introduces three distinct capabilities: (1) a validated conversion path that serializes Arrow rows to JSON bytes in Rust and passes them through Pydantic's `model_validate_json`, (2) a lazy iterator/generator API for memory-constrained scenarios, and (3) `.pyi` type stubs for the `_core` Rust extension module to enable IDE autocompletion and satisfy basedpyright strict mode.

The validated path is the most architecturally significant piece. The existing fast path extracts column values as Python objects and calls `model_construct`. The validated path must instead serialize each row to JSON bytes using `serde_json::Value` in Rust, then pass those bytes to `model_validate_json` on the Python side. This requires a parallel "to JSON value" conversion alongside the existing "to Python object" extraction, with careful handling of temporal types (dates as ISO 8601 strings, durations as ISO 8601 duration strings).

The iterator API is straightforward: a Python-side generator function that yields from batches one model at a time, avoiding full list materialization. The type stubs are manually authored `.pyi` files that describe the Rust module's public API.

**Primary recommendation:** Add `convert_record_batch_validated` Rust function that builds `serde_json::Map` per row and returns JSON bytes to Python, where `model_validate_json` handles validation. Implement the iterator as a Python generator wrapping existing Rust batch functions. Write `_core.pyi` manually.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VALID-01 | Opt-in `validate=True` mode on `ArrowModelConverter` | `ArrowModelConverter.__init__` already accepts `validate` param (API-01 done). The `convert()` method needs branching to call validated Rust path when `self._validate is True`. |
| VALID-02 | Validated path serialises each row to JSON bytes via `serde_json` in Rust | New Rust function `convert_record_batch_validated` builds `serde_json::Map<String, Value>` per row from Arrow columns and calls `serde_json::to_vec` to produce `Vec<u8>`. Temporal types need ISO 8601 string representation. |
| VALID-03 | JSON bytes passed to `model_validate_json` for full Pydantic validation | Rust returns `PyBytes` to Python; Python calls `model_cls.model_validate_json(json_bytes)`. Pydantic's `model_validate_json` accepts `str | bytes | bytearray` and raises `ValidationError` on failure. |
| API-04 | Iterator/generator API for lazy model yielding | Python generator function using `yield` that processes one batch at a time via existing Rust functions. No new Rust code needed -- pure Python wrapper. |
| API-05 | Type stubs (`.pyi`) for the Rust extension module | Manual `_core.pyi` file at `src/arrowdantic/_core.pyi` describing all `#[pyfunction]` signatures. Combined with existing `py.typed` marker, enables basedpyright strict mode without suppressions. |
</phase_requirements>

## Standard Stack

### Core (already in Cargo.toml)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| serde_json | 1.0 | Row-to-JSON serialization | Already a dependency. `serde_json::Map` + `serde_json::Value` to build per-row JSON, `serde_json::to_vec` for byte output. |
| chrono | 0.4 | ISO 8601 formatting for temporal types | Already a dependency. `NaiveDate::format`, `NaiveDateTime::format`, `TimeDelta` to ISO 8601 duration. |
| pyo3 | 0.28 | PyBytes for returning JSON bytes to Python | Already a dependency. `PyBytes::new(py, &bytes)` to pass serialized JSON to Python. |

### Python (no new dependencies needed)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic | >=2.11 | `model_validate_json` | Already a dependency. Called from Python side to validate JSON bytes from Rust. |

### No New Dependencies Required
This phase requires zero new Rust crate or Python package dependencies. Everything needed is already in Cargo.toml and pyproject.toml.

## Architecture Patterns

### Validated Path Data Flow

```
Arrow columns (Rust)
    |
    v
serde_json::Map<String, Value>  (one per row, in Rust)
    |
    v
serde_json::to_vec()  (Rust -> Vec<u8>)
    |
    v
PyBytes::new(py, &bytes)  (Rust -> Python bytes)
    |
    v
model_cls.model_validate_json(json_bytes)  (Python Pydantic)
    |
    v
Model instance (validated)
```

### Pattern 1: Parallel Value Extraction (JSON Path)

**What:** A new function in `extract.rs` that converts an Arrow value at a given row into a `serde_json::Value` instead of a `PyObject`. This parallels the existing `extract_value` method.

**When to use:** When `validate=True` is set on the converter.

**Example:**
```rust
// Source: serde_json docs + arrow-rs types
use serde_json::{Map, Value, Number};

impl<'a> ColumnExtractor<'a> {
    pub fn extract_json_value(&self, row: usize) -> Result<Value, PyErr> {
        match self {
            ColumnExtractor::Int64(arr) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    Ok(Value::Number(Number::from(arr.value(row))))
                }
            }
            ColumnExtractor::Utf8(arr) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    Ok(Value::String(arr.value(row).to_owned()))
                }
            }
            ColumnExtractor::Date32(arr) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    // Pydantic expects ISO 8601: "2024-01-15"
                    match arr.value_as_date(row) {
                        Some(d) => Ok(Value::String(d.format("%Y-%m-%d").to_string())),
                        None => Ok(Value::Null),
                    }
                }
            }
            // ... other variants
            _ => todo!()
        }
    }
}
```

### Pattern 2: Rust-Side Batch Validated Conversion

**What:** A new `#[pyfunction]` that builds JSON bytes per row and calls `model_validate_json` from Rust.

**When to use:** When the converter's `validate=True` flag is set.

**Example:**
```rust
// Source: PyO3 docs, serde_json docs
#[pyfunction]
fn convert_record_batch_validated(
    py: Python<'_>,
    batch: PyRecordBatch,
    model_cls: Bound<'_, PyAny>,
    field_specs: Vec<(usize, String, Option<PyObject>)>,
) -> PyResult<PyObject> {
    let rb = batch.into_inner();
    let num_rows = rb.num_rows();
    // ... setup extractors same as fast path ...

    let mut results: Vec<PyObject> = Vec::with_capacity(num_rows);

    for row in 0..num_rows {
        let mut map = serde_json::Map::new();
        for (extractor, field_name) in extractors.iter().zip(field_names.iter()) {
            let json_val = extractor.extract_json_value(row)?;
            map.insert(field_name.to_string(), json_val);
        }
        let json_bytes = serde_json::to_vec(&map)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("JSON serialization failed: {e}")
            ))?;
        let py_bytes = PyBytes::new(py, &json_bytes);
        let instance = model_cls.call_method1("model_validate_json", (py_bytes,))?;
        results.push(instance.unbind());
    }

    let py_list = PyList::new(py, &results)?;
    Ok(py_list.into_any().unbind())
}
```

### Pattern 3: Python Generator for Lazy Iteration

**What:** A Python generator method on `ArrowModelConverter` that yields one model at a time.

**When to use:** When users call `converter.iter(data)` or `iter_arrow(Model, data)`.

**Example:**
```python
# Source: Python generator protocol
from collections.abc import Iterator

class ArrowModelConverter:
    def iter(self, data: pa.RecordBatch | pa.Table) -> Iterator[BaseModel]:
        """Lazily yield model instances one at a time (API-04)."""
        field_specs = self._resolve_columns(data.schema)

        if hasattr(data, "to_batches"):
            batches = data.to_batches()
        else:
            batches = [data]

        for batch in batches:
            # Use existing Rust function per batch, but could also
            # yield individual models from a batch-level function
            results = _core.convert_record_batch(batch, self._model_class, field_specs)
            yield from results
```

**Design note:** The simplest approach yields from per-batch results. This means each batch is fully materialized but only one batch at a time lives in memory. For Tables with many small batches, this is effective. A truly per-row lazy approach would require a Rust-side iterator holding the RecordBatch, which adds complexity for marginal benefit since batches are typically 64K-1M rows.

### Pattern 4: Type Stub File

**What:** A `.pyi` file describing the public API of the `_core` Rust extension.

**Where:** `src/arrowdantic/_core.pyi`

**Example:**
```python
# Source: PyO3 typing hints guide, PEP 561
from typing import Any

def record_batch_info(batch: Any) -> tuple[int, int]: ...
def convert_record_batch(
    batch: Any,
    model_cls: type[Any],
    field_specs: list[tuple[int, str, type[Any] | None]],
) -> list[Any]: ...
def convert_table(
    table: Any,
    model_cls: type[Any],
    field_specs: list[tuple[int, str, type[Any] | None]],
) -> list[Any]: ...
def convert_record_batch_validated(
    batch: Any,
    model_cls: type[Any],
    field_specs: list[tuple[int, str, type[Any] | None]],
) -> list[Any]: ...
def convert_table_validated(
    table: Any,
    model_cls: type[Any],
    field_specs: list[tuple[int, str, type[Any] | None]],
) -> list[Any]: ...
```

### Anti-Patterns to Avoid
- **Building JSON strings via string concatenation in Rust:** Use `serde_json::Map` + `serde_json::to_vec` instead. String concatenation risks injection and encoding bugs.
- **Calling `model_validate` (dict-based) instead of `model_validate_json`:** The JSON path is faster because pydantic-core parses JSON in Rust internally, avoiding Python dict overhead.
- **Implementing a full Rust-side per-row iterator with `#[pyclass]`:** Adds significant complexity (lifetime management for borrowed Arrow data) for marginal memory savings over per-batch iteration. Python generator wrapping batch calls is simpler and nearly as effective.
- **Using `arrow-json` crate for row serialization:** The `record_batches_to_json_rows` function is deprecated. Building `serde_json::Value` directly from our existing extractors is more efficient and gives us control over temporal type formatting.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON serialization | Custom JSON string builder | `serde_json::Map` + `serde_json::to_vec` | Handles escaping, encoding, nested structures correctly |
| ISO 8601 date formatting | Custom date formatter | `chrono::NaiveDate::format("%Y-%m-%d")` | Edge cases with leap years, negative dates |
| ISO 8601 duration formatting | Custom duration formatter | Build from `TimeDelta` components | Pydantic expects `PxDTxHxMxS` format |
| Pydantic validation | Custom validation logic | `model_validate_json` | Pydantic-core handles coercion, error aggregation, nested models |
| Type stub generation | pyo3-stub-gen automation | Manual `.pyi` file | Only 5-6 functions to stub; automation adds build complexity |

**Key insight:** The validated path's complexity is in JSON value conversion for temporal types, not in the serialization mechanics. `serde_json` handles all the actual JSON output; our job is mapping Arrow values to the right `serde_json::Value` variants with correct formatting.

## Common Pitfalls

### Pitfall 1: Temporal Type JSON Format Mismatch
**What goes wrong:** Serializing dates/datetimes as epoch integers or wrong string formats causes `model_validate_json` to reject the input or misinterpret values.
**Why it happens:** Arrow stores dates as epoch days (i32) and timestamps as epoch microseconds (i64). Simply outputting the raw number does not match Pydantic's expected JSON format.
**How to avoid:** Convert to chrono types first, then format as ISO 8601 strings. Dates must be `"YYYY-MM-DD"`, datetimes `"YYYY-MM-DDTHH:MM:SS"` (with optional fractional seconds and timezone), durations `"PTxHxMxS"`.
**Warning signs:** `ValidationError` mentioning "invalid datetime format" or "value is not a valid date".

### Pitfall 2: Duration ISO 8601 Format
**What goes wrong:** Pydantic's `model_validate_json` in strict mode only accepts ISO 8601 duration strings (`PxDTxHxMxS`), not numeric seconds.
**Why it happens:** In Python mode (`model_validate`), Pydantic accepts seconds as int/float. In JSON mode, it only accepts the ISO 8601 string representation.
**How to avoid:** Convert `chrono::TimeDelta` to ISO 8601 duration format: decompose into days, hours, minutes, seconds components and format as `PxDTxHxMxS`. For example, 3661 seconds becomes `"PT1H1M1S"`.
**Warning signs:** `ValidationError` mentioning "invalid duration" when passing numeric values in JSON.

### Pitfall 3: Nested Struct JSON Serialization
**What goes wrong:** Struct columns need to produce nested JSON objects. If not handled recursively, nested models fail validation.
**Why it happens:** The `extract_json_value` for Struct variants must recursively build nested `serde_json::Map` objects, not flat key-value pairs.
**How to avoid:** Recurse into struct children the same way `extract_value` does, but building `Value::Object(map)` instead of calling `model_construct`.
**Warning signs:** `ValidationError` for nested model fields, or flat structures where nested objects were expected.

### Pitfall 4: List Type JSON Serialization
**What goes wrong:** List columns must produce JSON arrays. Element types within lists need correct JSON representation too.
**Why it happens:** `extract_json_value` for List/LargeList must call `extract_json_value` recursively on each element.
**How to avoid:** Create temporary extractors for list element arrays (same pattern as fast path), but call `extract_json_value` on each element.
**Warning signs:** `ValidationError` for list fields or type mismatch errors.

### Pitfall 5: Float NaN/Infinity in JSON
**What goes wrong:** `serde_json::to_vec` fails (returns Err) if a `Value::Number` contains NaN or Infinity, which are not valid JSON.
**Why it happens:** Arrow Float32/Float64 columns can contain NaN, +Inf, -Inf values. `serde_json::Number` cannot represent these.
**How to avoid:** Check for NaN/Infinity before converting to `Value::Number`. Convert NaN to `Value::Null`, and consider erroring on Infinity (or converting to null).
**Warning signs:** `serde_json::to_vec` returning `Err` with "NaN" or "infinity" message.

### Pitfall 6: basedpyright Stub Completeness
**What goes wrong:** Removing the `reportUnknownVariableType` etc. suppressions from `pyproject.toml` causes new type errors because the `.pyi` stubs don't cover all used symbols.
**Why it happens:** The stubs must describe every function and class accessed from `_core` in `__init__.py` -- if any are missing, basedpyright reports unknown types.
**How to avoid:** Cross-reference every `_core.xxx` usage in `__init__.py` against the `.pyi` file. Run `uv run basedpyright` to verify before removing suppressions.
**Warning signs:** basedpyright errors mentioning "reportUnknownVariableType" or "reportAttributeAccessIssue" after removing suppressions.

### Pitfall 7: Null Handling in JSON Differs from Fast Path
**What goes wrong:** Null values in Arrow columns should produce `null` in JSON (not omit the key). If keys are omitted for null fields, Pydantic may raise errors for required fields.
**Why it happens:** Some JSON writers omit null keys by default. But Pydantic needs to see the key with a `null` value to distinguish "field is null" from "field is missing".
**How to avoid:** Always include the key in the JSON map with `Value::Null` for null Arrow values. The `extract_json_value` should return `Value::Null` (not skip the key).
**Warning signs:** `ValidationError` for "field required" on nullable fields that have null values.

## Code Examples

### ISO 8601 Duration Formatting in Rust
```rust
// Source: chrono docs, ISO 8601 spec
fn timedelta_to_iso8601(td: &chrono::TimeDelta) -> String {
    let total_secs = td.num_seconds();
    let is_negative = total_secs < 0;
    let total_secs = total_secs.unsigned_abs();

    let days = total_secs / 86400;
    let remaining = total_secs % 86400;
    let hours = remaining / 3600;
    let remaining = remaining % 3600;
    let minutes = remaining / 60;
    let seconds = remaining % 60;

    // Include subsecond microseconds from the TimeDelta
    let subsec_nanos = td.subsec_nanos().unsigned_abs();
    let micros = subsec_nanos / 1000;

    let mut result = String::new();
    if is_negative {
        result.push('-');
    }
    result.push('P');
    if days > 0 {
        result.push_str(&format!("{days}D"));
    }
    // Always include T section if there are time components
    if hours > 0 || minutes > 0 || seconds > 0 || micros > 0 || days == 0 {
        result.push('T');
        if hours > 0 {
            result.push_str(&format!("{hours}H"));
        }
        if minutes > 0 {
            result.push_str(&format!("{minutes}M"));
        }
        if micros > 0 {
            result.push_str(&format!("{seconds}.{micros:06}S"));
        } else if seconds > 0 || (hours == 0 && minutes == 0 && days == 0) {
            result.push_str(&format!("{seconds}S"));
        }
    }
    result
}
```

### Calling model_validate_json from Rust via PyO3
```rust
// Source: PyO3 0.28 docs, Pydantic model_validate_json API
use pyo3::types::PyBytes;

// Inside the row loop:
let json_bytes = serde_json::to_vec(&map)
    .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
        format!("JSON serialization error: {e}")
    ))?;
let py_bytes = PyBytes::new(py, &json_bytes);
let instance = model_cls.call_method1("model_validate_json", (py_bytes,))?;
results.push(instance.unbind());
// ValidationError from Pydantic propagates naturally as PyErr
```

### Python Generator Method
```python
# Source: Python generator protocol, existing ArrowModelConverter pattern
from collections.abc import Iterator
from pydantic import BaseModel

class ArrowModelConverter:
    def iter(self, data: pa.RecordBatch | pa.Table) -> Iterator[BaseModel]:
        """Lazily yield model instances without materializing full list."""
        field_specs = self._resolve_columns(data.schema)

        if hasattr(data, "to_batches"):
            batches = data.to_batches()
        else:
            batches = [data]

        for batch in batches:
            if self._validate:
                results = _core.convert_record_batch_validated(
                    batch, self._model_class, field_specs
                )
            else:
                results = _core.convert_record_batch(
                    batch, self._model_class, field_specs
                )
            yield from results
```

### Type Stub File (_core.pyi)
```python
# Source: PyO3 typing hints guide, PEP 561
from typing import Any

def record_batch_info(batch: Any, /) -> tuple[int, int]: ...
def convert_record_batch(
    batch: Any,
    model_cls: type[Any],
    field_specs: list[tuple[int, str, type[Any] | None]],
    /,
) -> list[Any]: ...
def convert_table(
    table: Any,
    model_cls: type[Any],
    field_specs: list[tuple[int, str, type[Any] | None]],
    /,
) -> list[Any]: ...
def convert_record_batch_validated(
    batch: Any,
    model_cls: type[Any],
    field_specs: list[tuple[int, str, type[Any] | None]],
    /,
) -> list[Any]: ...
def convert_table_validated(
    table: Any,
    model_cls: type[Any],
    field_specs: list[tuple[int, str, type[Any] | None]],
    /,
) -> list[Any]: ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `record_batches_to_json_rows` (arrow-json) | Deprecated; use Writer API or manual `serde_json::Value` | arrow-rs 50+ | Build JSON values directly from extractors instead |
| `#[pyproto] impl PyIterProtocol` | `#[pymethods]` with `__iter__`/`__next__` | PyO3 0.20 | Old trait-based approach removed; use method-based |
| `populate_by_name` | `validate_by_name` / `validate_by_alias` | Pydantic 2.11 | Both still work; project already handles both |
| pyo3-stub-gen automated stubs | Manual `.pyi` files | Ongoing | pyo3-stub-gen exists but adds build complexity; manual is preferred for small APIs |

**Deprecated/outdated:**
- `arrow_json::writer::record_batches_to_json_rows`: Deprecated. Do not add arrow-json as a dependency.
- `#[pyproto]` trait: Removed in PyO3 0.20+. Use `#[pymethods]` instead.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_convert.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VALID-01 | `ArrowModelConverter(Model, validate=True)` produces validated instances | unit | `uv run pytest tests/test_convert.py -k "TestValidatedPath" -x` | No -- Wave 0 |
| VALID-02 | Validated path serializes rows to JSON via serde_json | unit | `uv run pytest tests/test_convert.py -k "test_validated" -x` | No -- Wave 0 |
| VALID-03 | ValidationError raised for invalid data in validated mode | unit | `uv run pytest tests/test_convert.py -k "test_validation_error" -x` | No -- Wave 0 |
| API-04 | `converter.iter(data)` yields models lazily | unit | `uv run pytest tests/test_convert.py -k "TestIteratorAPI" -x` | No -- Wave 0 |
| API-05 | `.pyi` stubs enable basedpyright strict mode | smoke | `uv run basedpyright` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_convert.py -x`
- **Per wave merge:** `uv run pytest && uv run basedpyright`
- **Phase gate:** Full suite green + basedpyright clean before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] Test classes `TestValidatedPath`, `TestValidationErrors` in `tests/test_convert.py` -- covers VALID-01, VALID-02, VALID-03
- [ ] Test class `TestIteratorAPI` in `tests/test_convert.py` -- covers API-04
- [ ] Verify `uv run basedpyright` passes after stub addition and suppression removal -- covers API-05

## Open Questions

1. **Validated path: field_specs field_name or alias as JSON key?**
   - What we know: The fast path uses Pydantic field names as kwargs keys (since `model_construct` works with field names). For `model_validate_json`, the JSON keys should match what Pydantic expects -- by default this is the field name, but aliases affect this.
   - What's unclear: Should the JSON keys use the Arrow column name (alias) or the Pydantic field name? Pydantic's `model_validate_json` supports both `by_alias` and `by_name` params.
   - Recommendation: Use the Pydantic field name as JSON key (same as fast path) since `model_validate_json` defaults to accepting field names. The `field_specs` already contain the resolved field name. This is simplest and consistent.

2. **Iterator API: per-row vs per-batch granularity?**
   - What we know: A truly per-row lazy iterator from Rust requires a `#[pyclass]` that holds the RecordBatch and current row index, with complex lifetime management. Per-batch iteration yields from each batch result.
   - What's unclear: Whether users expect single-row-at-a-time memory usage or batch-level granularity.
   - Recommendation: Per-batch iteration (yield from batch results). This is the 80/20 solution: for a Table with 100 batches of 10K rows each, only 10K model instances are alive at once (not all 1M). Document this as "batch-level lazy" in the API docs. A per-row Rust iterator can be a v2 enhancement.

3. **Nested struct serialization in validated path**
   - What we know: Struct columns currently produce nested `model_construct` calls. In the validated path, they should produce nested JSON objects.
   - What's unclear: Whether the nested JSON object keys should use the nested model's field names or aliases.
   - Recommendation: Use field names as JSON keys for nested objects too, matching the top-level approach. The nested model introspection is only needed for the fast path (to know which model class to construct); for validated path, the JSON structure + field names is sufficient for `model_validate_json` to resolve nested models.

## Sources

### Primary (HIGH confidence)
- Pydantic `model_validate_json` API: https://docs.pydantic.dev/latest/api/base_model/ -- method signature, parameters, return type, exceptions
- Pydantic JSON concepts: https://docs.pydantic.dev/latest/concepts/json/ -- date/tuple coercion from JSON strings
- Pydantic standard library types: https://docs.pydantic.dev/latest/api/standard_library_types/ -- datetime, date, timedelta JSON format requirements (ISO 8601 / RFC 3339)
- PyO3 iterator protocol: https://pyo3.rs/main/class/protocols.html -- `#[pymethods]` `__iter__`/`__next__` pattern
- PyO3 typing hints: https://pyo3.rs/main/python-typing-hints.html -- `.pyi` file structure, `py.typed` marker, maturin integration
- serde_json docs: https://docs.rs/serde_json/latest/serde_json/ -- `Map`, `Value`, `to_vec`

### Secondary (MEDIUM confidence)
- PyO3 `PyBytes`: https://pyo3.rs/main/doc/pyo3/types/struct.pybytes -- `PyBytes::new(py, &data)` for Rust-to-Python bytes transfer
- Pydantic performance: https://docs.pydantic.dev/latest/concepts/performance/ -- `model_validate_json` faster than `model_validate(json.loads(...))`
- maturin stub discussions: https://github.com/PyO3/maturin/discussions/2486 -- `.pyi` file location for sub-packages
- arrow-json deprecation: https://github.com/influxdata/influxdb/issues/24981 -- `record_batches_to_json_rows` deprecated

### Tertiary (LOW confidence)
- pyo3-stub-gen: https://github.com/Jij-Inc/pyo3-stub-gen -- automated stub generation tool (not recommended for this project's small API surface)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all verified in Cargo.toml/pyproject.toml
- Architecture (validated path): HIGH -- serde_json::Value + model_validate_json is the documented pattern; temporal format requirements verified against Pydantic docs
- Architecture (iterator): HIGH -- Python generator pattern is straightforward; per-batch granularity is a pragmatic choice
- Architecture (type stubs): HIGH -- PyO3 docs clearly describe `.pyi` file creation; existing `py.typed` marker already in place
- Pitfalls: HIGH -- temporal format mismatch and float NaN issues are well-documented gotchas

**Research date:** 2026-03-22
**Valid until:** 2026-04-22 (stable domain, no fast-moving dependencies)
