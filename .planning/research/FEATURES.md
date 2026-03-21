# Feature Landscape

**Domain:** Arrow-to-Pydantic data conversion library (Rust/PyO3)
**Researched:** 2026-03-21

## Current User Pain Points

Users converting Arrow data to Pydantic models today follow one of these paths:

1. **`batch.to_pylist()` + `Model(**row)`** -- The naive approach. Materializes every row as a Python dict, then constructs a Pydantic model from each dict. Two full materializations: Arrow buffers to Python dicts, then dicts to model instances. `to_pylist()` itself is ~20x slower than NumPy equivalents due to per-element Scalar wrapping overhead (Apache Arrow issue #28694).

2. **`batch.to_pylist()` + `Model.model_construct(**row)`** -- The "careful user" path. Skips Pydantic validation for trusted Arrow data. Still pays the full `to_pylist()` materialization cost. This is arrowdantic's primary comparison target.

3. **`batch.to_pydict()` + manual zip** -- Slightly faster than `to_pylist()` since it produces column-oriented dicts, but requires manual row assembly and loses type clarity.

4. **Pandas intermediary** -- `batch.to_pandas()` + `itertuples()`. Common but introduces a pandas dependency and another full copy. PyArrow issue #28689 (requesting native row accessors) was closed as "not planned."

5. **Stay in Arrow, never convert** -- Viable for analytics but impossible when models need to cross API boundaries (FastAPI responses, ORM layers, business logic that requires named fields).

No existing library solves the Arrow-to-Pydantic-instance direction with a Rust hot loop. This is a genuine gap.

## Existing Ecosystem (What Exists Today)

| Library | Direction | Scope | Notes |
|---------|-----------|-------|-------|
| `pydantic-to-pyarrow` | Pydantic schema -> Arrow schema | Schema only, no data conversion | Active (v0.1.6, Jan 2025). Supports aliases via `by_alias`. |
| `arrowdantic` (Carleitao) | Arrow file I/O with Pydantic-style API | File I/O, not model conversion | Rust-backed, 8MB disk. Does NOT convert Arrow data to Pydantic models despite the name. |
| `patito` | Polars DataFrame <-> Pydantic models | Full data + validation | Active (v0.8.6, Feb 2026). `df.get()` returns model instance. Polars-only, row-at-a-time. |
| `poldantic` | Polars schema <-> Pydantic schema | Schema only, no data conversion | Active (v0.3.1, Oct 2025). Bidirectional schema mapping. |
| `pandera` | DataFrame validation with Pydantic | Validation, not conversion | PydanticModel dtype applies BaseModel to each row. Explicitly warns "might not scale with larger datasets." |
| LanceDB | Pydantic -> Arrow schema (via LanceModel) | Schema + ingestion for LanceDB | Tied to LanceDB ecosystem. Not a general conversion library. |

**Key finding:** Nothing in the ecosystem does Arrow buffers -> Pydantic model instances via a compiled hot loop. The gap is real.

## Table Stakes

Features users expect. Missing any of these and the library feels incomplete or untrustworthy.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| RecordBatch to list of models | This IS the core use case. Without it, the library has no reason to exist. | High | Hot loop in Rust over Arrow buffers, constructing Python model instances via `model_construct`. |
| Table to list of models | Tables are multi-batch containers. Users will pass Tables as often as RecordBatches. | Low | Iterate internal batches, delegate to RecordBatch logic. |
| Primitive type coverage (int, float, bool, string) | These are >90% of real-world Arrow columns. | Medium | Int8-64, UInt8-64, Float16/32/64, Boolean, Utf8/LargeUtf8. Must handle all width variants. |
| Null handling via validity bitmap | Arrow nulls are not sentinel values -- the value buffer is undefined at null positions. Reading without bitmap checking produces garbage. | Medium | Check validity bit before extracting value. Emit `None` for null slots. |
| Optional field support | Pydantic `Optional[T]` and `T | None` are ubiquitous. Must map cleanly to nullable Arrow columns. | Low | Map Arrow null to Python `None` when field type allows it. Raise on null in non-optional field. |
| Nested models via Arrow Struct | Arrow Struct type maps naturally to nested Pydantic models. Data pipelines with nested schemas are common. | High | Recursive descent: Struct fields -> nested model fields. Must handle `model_construct` recursively. |
| List/LargeList support | `List[int]`, `List[str]`, `List[NestedModel]` are standard in real schemas. | Medium | Arrow List -> Python list. List-of-Struct -> list of nested model instances. |
| Temporal types (Date, Timestamp, Duration) | Date32, Timestamp (with/without timezone), Duration are standard in data pipelines. | Medium | Map to Python `date`, `datetime`, `timedelta`. Timezone-aware vs naive timestamps need distinct handling. |
| Schema cross-reference at init | Compile the mapping between Arrow schema and Pydantic model fields once, not per row. Amortizes introspection cost. | Medium | Compare Arrow field names to model field names (accounting for aliases). Cache column indices and type converters. |
| Clear error messages on schema mismatch | Users need to know which field failed and why. "Column X has type Int64 but model expects str" is actionable. | Low | Raise `ValueError` at converter init, not deep in the hot loop. |
| `from_arrow(Model, data)` convenience function | One-liner API for simple cases. Users should not need to understand the converter lifecycle for basic usage. | Low | Thin wrapper: create converter, call convert, return list. |
| Extra columns silently ignored | Arrow data often has more columns than the model needs. This matches how `model_construct` and `model_validate` work with `extra='ignore'` (the default). | Low | Only process columns that match model fields. |
| Type stubs (.pyi) for Rust extension | Type checkers (mypy, pyright) need stubs. Without them, every call to the Rust extension is `Any`. | Low | Ship `_core.pyi` alongside the compiled extension. |

## Differentiators

Features that set arrowdantic apart. Not expected (no competitors do this), but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Dict-free construction via Rust | The core competitive advantage. Skip the Python dict intermediate entirely. Extract values from Arrow buffers in Rust, set `__dict__` directly on model instances. No other library does this. | High | This is the fundamental architecture decision. All performance gains flow from this. |
| Pre-interned Python field name strings | Allocate Python string objects for field names once at converter init, reuse across all rows. Eliminates per-row string creation overhead. | Medium | `pyo3::intern!` or manual `PyString` caching. Small per-row savings that compound over millions of rows. |
| Validated path via `serde_json` + `validate_json` | When users want Pydantic validation on Arrow data, serialize rows to JSON in Rust, then call `validate_json` (which uses pydantic-core's `jiter` parser). Keeps serialization AND validation in Rust. | High | Alternative to the fast path. Users opt in with `validate=True`. Useful for untrusted data sources or models with complex validators. |
| Arrow C Data Interface / PyCapsule support | Accept Arrow data from ANY source implementing the Arrow PyCapsule Interface (pyarrow, polars, nanoarrow, pandas 2.2+, Daft, etc.) without requiring pyarrow as a dependency. | Medium | Via `pyo3-arrow`. This makes arrowdantic source-agnostic. Users can pass a Polars DataFrame directly. |
| Pydantic alias resolution (validation_alias > alias > field_name) | Full support for Pydantic v2's alias hierarchy. Arrow column names can match validation_alias, alias, or field_name with correct priority. Most Arrow-adjacent tools ignore aliases entirely. | Medium | Must introspect `model_fields` to extract alias chain. Priority: `validation_alias` > `alias` > `field_name`. |
| `populate_by_name` support | When a Pydantic model has `model_config = ConfigDict(populate_by_name=True)`, accept both the alias and the field name for the same field. | Low | Check model config at init, expand the column-to-field mapping accordingly. |
| Iterator/generator API | Yield model instances lazily instead of materializing the full list. Important for large datasets where memory is constrained. | Medium | `iter_models(Model, data)` that yields instances. Processes one batch at a time for Tables. |
| Dictionary-encoded column support | Arrow Dictionary type (categorical data) is common in real datasets. Map to the logical value type, not the index type. | Medium | Resolve dictionary indices to values before extraction. Users see `str` values, not integer codes. |
| Batch-level progress callback | For large conversions, allow users to pass a callback that receives progress info (rows processed, batch number). | Low | Optional `on_batch` parameter. Useful for progress bars in notebooks. |

## Anti-Features

Features to explicitly NOT build. Each exclusion is deliberate.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Pydantic v1 support | v1 has different internals (`__fields__`, `construct()` vs `model_construct()`, no `validate_json`). Supporting both doubles the API surface for a shrinking user base. v1 is end-of-life. | Require `pydantic >= 2.0`. Document clearly. |
| Arrow writing (Pydantic -> Arrow) | Different problem, different hot path, doubles scope. `pydantic-to-pyarrow` already handles the schema direction. Data writing can use `pa.Table.from_pylist([m.model_dump() for m in models])`. | Out of scope for v1. Revisit if users demand it. |
| ORM / database layer integration | This is a data conversion library, not a framework. Adding SQLAlchemy/Django integration creates coupling and maintenance burden. | Users compose arrowdantic with their own ORM layer. |
| Full DataFrame abstraction (like patito) | Building a DataFrame wrapper around Pydantic models is a different product. Patito already does this well for Polars. | Focus on conversion, not DataFrame operations. |
| Schema inference from Pydantic models | Generating Arrow schemas from Pydantic models is the reverse direction. `pydantic-to-pyarrow` and `poldantic` already solve this. Adding it dilutes focus. | Recommend `pydantic-to-pyarrow` for this direction. |
| `AliasPath` and `AliasGenerator` support | These involve complex resolution logic (nested paths into dicts, callable generators). Arrow columns are flat names -- AliasPath makes no sense for columnar data. | Raise `NotImplementedError` if encountered. Document the limitation. |
| `FixedSizeList` mapping | Ambiguous target type: Python `list`, `tuple`, or `numpy.ndarray`? Each has different semantics. Needs a resolution heuristic that risks surprising users. | Defer to post-v1. Support regular `List`/`LargeList` which map unambiguously to Python `list`. |
| `strict=True` mode for extra Arrow columns | Erroring on extra columns is rarely what data pipeline users want. Arrow data commonly has metadata columns, partition columns, etc. | Default to silent ignore. Add strict mode later if requested. |
| Polars-specific code paths | Polars exports via the Arrow PyCapsule Interface. arrowdantic consumes Arrow data generically -- no need for Polars-specific handling. | Document that Polars works via PyCapsule. No special code needed. |
| Replacing pyarrow or Polars | arrowdantic is a conversion utility, not an Arrow implementation. It should complement pyarrow/Polars, not compete with them. | Position as "the last mile" -- converting Arrow data to typed Python objects. |
| DataFrame validation (like pandera) | Statistical validation (uniqueness, ranges, schema conformance) is a separate concern. Pandera does this. arrowdantic converts data, it does not validate datasets. | Users validate with pandera/polars before passing to arrowdantic. |

## Feature Dependencies

```
Schema cross-reference at init ──> RecordBatch to list of models
                                      │
                                      ├── Table to list of models (iterates batches)
                                      ├── Iterator/generator API (lazy variant)
                                      │
                                      ├── Null handling (validity bitmap check)
                                      ├── Primitive type coverage
                                      ├── Temporal types
                                      ├── List/LargeList support
                                      ├── Dictionary-encoded columns
                                      │
                                      └── Nested models via Struct ──> Recursive model_construct

Pydantic alias resolution ──> Schema cross-reference at init
populate_by_name support ──> Pydantic alias resolution

from_arrow() convenience ──> RecordBatch to list of models

Dict-free construction ──> Pre-interned field name strings (optimization within)

Validated path (validate=True) ──> serde_json serialization + validate_json call
                                   (independent of fast path, shares schema cross-ref)

Arrow C Data Interface ──> All conversion features (this is the input mechanism)
```

## MVP Recommendation

### Phase 1: Core Conversion (must ship first)

Prioritize in this order:

1. **Schema cross-reference at init** -- Everything depends on this. Map Arrow columns to Pydantic fields, resolve aliases, cache converters.
2. **Primitive type coverage** -- Int, UInt, Float, Bool, Utf8/LargeUtf8. Covers the vast majority of real schemas.
3. **Null handling via validity bitmap** -- Non-negotiable. Without this, null columns produce garbage values.
4. **RecordBatch to list of models** (fast path via `model_construct`) -- The core deliverable.
5. **Table to list of models** -- Trivial wrapper over RecordBatch conversion.
6. **`from_arrow()` convenience function** -- One-liner API.
7. **Type stubs** -- Ship with type safety from day one.
8. **Error messages on schema mismatch** -- Users need actionable diagnostics.

### Phase 2: Type Completeness

9. **Temporal types** (Date32, Timestamp naive/aware, Duration) -- Common in data pipelines.
10. **List/LargeList support** -- Needed for array-valued columns.
11. **Nested models via Struct** -- Required for hierarchical data.
12. **Dictionary-encoded columns** -- Common optimization in real Arrow data.

### Phase 3: Advanced Features

13. **Validated path** (`validate=True` via serde_json + validate_json) -- For untrusted data.
14. **Iterator/generator API** -- For memory-constrained large datasets.
15. **Pre-interned field name strings** -- Performance polish (ideally included from Phase 1 if straightforward).
16. **Batch-level progress callback** -- Nice-to-have for large conversions.

### Defer

- **`AliasPath`/`AliasGenerator`**: Raise `NotImplementedError`. Revisit if users request.
- **`FixedSizeList`**: Needs design decision on target type. Defer.
- **Arrow writing direction**: Different problem. Out of scope for v1.

## Sources

- [pydantic-to-pyarrow (GitHub)](https://github.com/simw/pydantic-to-pyarrow) -- Pydantic schema to Arrow schema conversion, active
- [arrowdantic by Carleitao (GitHub)](https://github.com/jorgecarleitao/arrowdantic) -- Arrow I/O with Pydantic-style API, Rust-backed
- [patito (GitHub)](https://github.com/JakobGM/patito) -- Polars + Pydantic data modelling layer, active
- [poldantic (PyPI)](https://pypi.org/project/poldantic/) -- Polars <-> Pydantic schema conversion
- [Arrow PyCapsule Interface (Apache docs)](https://arrow.apache.org/docs/format/CDataInterface/PyCapsuleInterface.html) -- Standard for cross-library Arrow interop
- [PyArrow to_pylist() performance (Arrow #28694)](https://github.com/apache/arrow/issues/28694) -- Documents 20x slowdown vs NumPy, root cause analysis
- [PyArrow row accessor request (Arrow #28689)](https://github.com/apache/arrow/issues/28689) -- Closed as not planned, confirms gap
- [Pydantic v2 performance docs](https://docs.pydantic.dev/latest/concepts/performance/) -- model_construct vs model_validate guidance
- [Pydantic v2 alias docs](https://docs.pydantic.dev/latest/concepts/alias/) -- validation_alias > alias > field_name priority
- [pyo3-arrow (docs.rs)](https://docs.rs/pyo3-arrow/latest/pyo3_arrow/index.html) -- Rust crate for Arrow PyCapsule Interface via PyO3
- [PyArrow to_pylist() memory issues (Arrow #36100)](https://github.com/apache/arrow/issues/36100) -- Memory not released until program termination
- [LanceDB Pydantic integration](https://docs.lancedb.com/integrations/data/pydantic) -- Pydantic schema to Arrow for LanceDB
- [Pandera Pydantic integration](https://pandera.readthedocs.io/en/stable/pydantic_integration.html) -- Row-wise validation, warns about scalability
