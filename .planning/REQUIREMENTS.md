# Requirements: arrowdantic

**Defined:** 2026-03-21
**Core Value:** Dict-free, single-step conversion from Arrow buffers to Pydantic model instances

## v1 Requirements

### Build System

- [ ] **BUILD-01**: Rust/PyO3 extension module built with maturin, importable as `arrowdantic._core`
- [ ] **BUILD-02**: `pyproject.toml` configured for maturin with `uv` integration
- [ ] **BUILD-03**: `Cargo.toml` with pyo3, arrow-rs, pyo3-arrow, serde_json, chrono dependencies

### Schema Cross-Reference

- [ ] **SCHEMA-01**: `ArrowModelConverter` class cross-references Arrow schema against Pydantic model fields at construction time
- [ ] **SCHEMA-02**: Schema mapping compiled once at converter init, reused across all batches
- [ ] **SCHEMA-03**: `ValueError` raised at init for missing required fields, unresolvable types, or ambiguous matches
- [ ] **SCHEMA-04**: Extra Arrow columns silently ignored (no error for unmapped columns)

### Alias Resolution

- [ ] **ALIAS-01**: Alias resolution priority: `validation_alias` > `alias` > `field_name`
- [ ] **ALIAS-02**: `populate_by_name` support — accept both alias and field name when enabled
- [ ] **ALIAS-03**: `NotImplementedError` raised for `AliasPath` or `AliasGenerator` if encountered

### Fast Path (model_construct)

- [ ] **FAST-01**: Default conversion uses `model_construct` — no Pydantic validation, dict-free row construction
- [ ] **FAST-02**: Pre-interned Python field name strings reused across all rows (no per-row string allocation)
- [ ] **FAST-03**: Column values extracted directly from Arrow buffers in Rust, no intermediate Python dict

### Validated Path

- [ ] **VALID-01**: Opt-in `validate=True` mode on `ArrowModelConverter`
- [ ] **VALID-02**: Validated path serialises each row to JSON bytes via `serde_json` in Rust
- [ ] **VALID-03**: JSON bytes passed to `model_validate_json` for full Pydantic validation in pydantic-core's Rust layer

### Primitive Types

- [ ] **TYPE-01**: Int8, Int16, Int32, Int64 → `int`
- [ ] **TYPE-02**: UInt8, UInt16, UInt32, UInt64 → `int`
- [ ] **TYPE-03**: Float32, Float64 → `float`
- [ ] **TYPE-04**: Boolean → `bool` (bit-packed, unpack via validity bitmap)
- [ ] **TYPE-05**: Utf8, LargeUtf8 → `str`

### Null Handling

- [ ] **NULL-01**: Null detection via Arrow validity bitmap before value extraction
- [ ] **NULL-02**: Null values emit `None` for nullable/optional Pydantic fields
- [ ] **NULL-03**: Value buffer at null indices is never read (Arrow spec: undefined data)

### Temporal Types

- [ ] **TEMP-01**: Date32 → `datetime.date`
- [ ] **TEMP-02**: Timestamp (no timezone) → naive `datetime.datetime`
- [ ] **TEMP-03**: Timestamp (with timezone) → aware `datetime.datetime`
- [ ] **TEMP-04**: Duration → `datetime.timedelta`
- [ ] **TEMP-05**: Nanosecond timestamps truncated to microsecond precision (Python's max)

### Complex Types

- [ ] **CPLX-01**: List → `list` with recursive type handling for element type
- [ ] **CPLX-02**: LargeList → `list` (same handling as List)
- [ ] **CPLX-03**: Struct → nested Pydantic `BaseModel` via recursive `ArrowModelConverter`
- [ ] **CPLX-04**: Dictionary(key, value) → value type (decode indices to values, handle all key types)
- [ ] **CPLX-05**: Null type → `None` always

### Input Types

- [ ] **INPUT-01**: Accept pyarrow `RecordBatch` as input
- [ ] **INPUT-02**: Accept pyarrow `Table` as input (iterate batches internally)
- [ ] **INPUT-03**: Arrow C Data Interface via pyo3-arrow for zero-copy buffer handoff

### API Surface

- [ ] **API-01**: `ArrowModelConverter(Model, validate=False)` constructor
- [ ] **API-02**: `converter.convert(data)` returns `list[Model]`
- [ ] **API-03**: `from_arrow(Model, data)` convenience one-shot function
- [ ] **API-04**: Iterator/generator API for lazy model yielding (memory-constrained large datasets)
- [ ] **API-05**: Type stubs (`.pyi`) for the Rust extension module

## v2 Requirements

### Extended Types

- **EXT-01**: `FixedSizeList<T, N>` mapping (needs resolution heuristic: list vs tuple vs ndarray)
- **EXT-02**: `Utf8View` / `BinaryView` support (arrow-rs 52+)
- **EXT-03**: Binary / LargeBinary → `bytes`

### Extended Features

- **FEAT-01**: `strict=True` mode that raises on extra Arrow columns
- **FEAT-02**: `AliasPath` and `AliasGenerator` support
- **FEAT-03**: Batch-level progress callback (`on_batch` parameter)
- **FEAT-04**: Direct `__setattr__` optimization bypassing `model_construct` call overhead
- **FEAT-05**: Arrow writing (Pydantic → Arrow) — reverse direction

## Out of Scope

| Feature | Reason |
|---------|--------|
| Pydantic v1 support | v1 end-of-life, different internals (`__fields__`, `construct()`) |
| ORM / database integration | Data conversion library, not a framework |
| DataFrame abstraction (patito-style) | Different product; patito exists for this |
| Schema inference (Pydantic → Arrow schema) | Reverse direction; `pydantic-to-pyarrow` exists |
| Polars-specific code paths | Polars works via Arrow PyCapsule Interface — no special handling needed |
| Replacing pyarrow/Polars | Complementary "last mile" tool, not a replacement |
| Dataset validation (pandera-style) | Different concern; validate before conversion |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| BUILD-01 | — | Pending |
| BUILD-02 | — | Pending |
| BUILD-03 | — | Pending |
| SCHEMA-01 | — | Pending |
| SCHEMA-02 | — | Pending |
| SCHEMA-03 | — | Pending |
| SCHEMA-04 | — | Pending |
| ALIAS-01 | — | Pending |
| ALIAS-02 | — | Pending |
| ALIAS-03 | — | Pending |
| FAST-01 | — | Pending |
| FAST-02 | — | Pending |
| FAST-03 | — | Pending |
| VALID-01 | — | Pending |
| VALID-02 | — | Pending |
| VALID-03 | — | Pending |
| TYPE-01 | — | Pending |
| TYPE-02 | — | Pending |
| TYPE-03 | — | Pending |
| TYPE-04 | — | Pending |
| TYPE-05 | — | Pending |
| NULL-01 | — | Pending |
| NULL-02 | — | Pending |
| NULL-03 | — | Pending |
| TEMP-01 | — | Pending |
| TEMP-02 | — | Pending |
| TEMP-03 | — | Pending |
| TEMP-04 | — | Pending |
| TEMP-05 | — | Pending |
| CPLX-01 | — | Pending |
| CPLX-02 | — | Pending |
| CPLX-03 | — | Pending |
| CPLX-04 | — | Pending |
| CPLX-05 | — | Pending |
| INPUT-01 | — | Pending |
| INPUT-02 | — | Pending |
| INPUT-03 | — | Pending |
| API-01 | — | Pending |
| API-02 | — | Pending |
| API-03 | — | Pending |
| API-04 | — | Pending |
| API-05 | — | Pending |

**Coverage:**
- v1 requirements: 41 total
- Mapped to phases: 0
- Unmapped: 41 ⚠️

---
*Requirements defined: 2026-03-21*
*Last updated: 2026-03-21 after initial definition*
