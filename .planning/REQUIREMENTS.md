# Requirements: arrowdantic

**Defined:** 2026-03-21
**Core Value:** Dict-free, single-step conversion from Arrow buffers to Pydantic model instances

## v1 Requirements

### Build System

- [x] **BUILD-01**: Rust/PyO3 extension module built with maturin, importable as `arrowdantic._core`
- [x] **BUILD-02**: `pyproject.toml` configured for maturin with `uv` integration
- [x] **BUILD-03**: `Cargo.toml` with pyo3, arrow-rs, pyo3-arrow, serde_json, chrono dependencies

### Schema Cross-Reference

- [x] **SCHEMA-01**: `ArrowModelConverter` class cross-references Arrow schema against Pydantic model fields at construction time
- [x] **SCHEMA-02**: Schema mapping compiled once at converter init, reused across all batches
- [x] **SCHEMA-03**: `ValueError` raised at init for missing required fields, unresolvable types, or ambiguous matches
- [x] **SCHEMA-04**: Extra Arrow columns silently ignored (no error for unmapped columns)

### Alias Resolution

- [x] **ALIAS-01**: Alias resolution priority: `validation_alias` > `alias` > `field_name`
- [x] **ALIAS-02**: `populate_by_name` support — accept both alias and field name when enabled
- [x] **ALIAS-03**: `NotImplementedError` raised for `AliasPath` or `AliasGenerator` if encountered

### Fast Path (model_construct)

- [x] **FAST-01**: Default conversion uses `model_construct` — no Pydantic validation, dict-free row construction
- [x] **FAST-02**: Pre-interned Python field name strings reused across all rows (no per-row string allocation)
- [x] **FAST-03**: Column values extracted directly from Arrow buffers in Rust, no intermediate Python dict

### Validated Path

- [x] **VALID-01**: Opt-in `validate=True` mode on `ArrowModelConverter`
- [x] **VALID-02**: Validated path serialises each row to JSON bytes via `serde_json` in Rust
- [x] **VALID-03**: JSON bytes passed to `model_validate_json` for full Pydantic validation in pydantic-core's Rust layer

### Primitive Types

- [x] **TYPE-01**: Int8, Int16, Int32, Int64 → `int`
- [x] **TYPE-02**: UInt8, UInt16, UInt32, UInt64 → `int`
- [x] **TYPE-03**: Float32, Float64 → `float`
- [x] **TYPE-04**: Boolean → `bool` (bit-packed, unpack via validity bitmap)
- [x] **TYPE-05**: Utf8, LargeUtf8 → `str`

### Null Handling

- [x] **NULL-01**: Null detection via Arrow validity bitmap before value extraction
- [x] **NULL-02**: Null values emit `None` for nullable/optional Pydantic fields
- [x] **NULL-03**: Value buffer at null indices is never read (Arrow spec: undefined data)

### Temporal Types

- [x] **TEMP-01**: Date32 → `datetime.date`
- [x] **TEMP-02**: Timestamp (no timezone) → naive `datetime.datetime`
- [x] **TEMP-03**: Timestamp (with timezone) → aware `datetime.datetime`
- [x] **TEMP-04**: Duration → `datetime.timedelta`
- [x] **TEMP-05**: Nanosecond timestamps truncated to microsecond precision (Python's max)

### Complex Types

- [x] **CPLX-01**: List → `list` with recursive type handling for element type
- [x] **CPLX-02**: LargeList → `list` (same handling as List)
- [x] **CPLX-03**: Struct → nested Pydantic `BaseModel` via recursive `ArrowModelConverter`
- [x] **CPLX-04**: Dictionary(key, value) → value type (decode indices to values, handle all key types)
- [x] **CPLX-05**: Null type → `None` always

### Extended Types (Phase 6)

- [x] **EXT-FLOAT16**: Float16 -> `float` (upcast to f32 for Python compatibility)
- [x] **EXT-DEC128**: Decimal128 -> `decimal.Decimal` (precision preserved via string representation)
- [x] **EXT-DEC256**: Decimal256 -> `decimal.Decimal` (precision preserved via string representation)
- [x] **EXT-DEC32**: Decimal32 -> `decimal.Decimal` (precision preserved via string representation)
- [x] **EXT-DEC64**: Decimal64 -> `decimal.Decimal` (precision preserved via string representation)
- [x] **EXT-DATE64**: Date64 -> `datetime.datetime` (millisecond-epoch to datetime)
- [x] **EXT-TIME32**: Time32 (second/millisecond) -> `datetime.time`
- [x] **EXT-TIME64**: Time64 (microsecond/nanosecond) -> `datetime.time` (ns truncated to us)
- [x] **EXT-INTERVAL**: Interval (YearMonth/DayTime/MonthDayNano) -> `tuple[int, int, int]` (months, days, nanos)
- [x] **EXT-BINARY**: Binary/LargeBinary -> `bytes`
- [x] **EXT-FSBINARY**: FixedSizeBinary -> `bytes`
- [x] **EXT-UTF8VIEW**: Utf8View -> `str` (identical to Utf8 path)
- [x] **EXT-BINVIEW**: BinaryView -> `bytes` (identical to Binary path)
- [x] **EXT-FSLIST**: FixedSizeList -> `list` (recursive element type handling)
- [x] **EXT-MAP**: Map -> `list[tuple[K, V]]` (key-value pair extraction)
- [x] **EXT-REE**: RunEndEncoded -> transparently pre-unpacked to underlying value type
- [x] **EXT-UNION**: Union (sparse + dense) -> active variant's value per row

### Input Types

- [x] **INPUT-01**: Accept pyarrow `RecordBatch` as input
- [x] **INPUT-02**: Accept pyarrow `Table` as input (iterate batches internally)
- [x] **INPUT-03**: Arrow C Data Interface via pyo3-arrow for zero-copy buffer handoff

### API Surface

- [x] **API-01**: `ArrowModelConverter(Model, validate=False)` constructor
- [x] **API-02**: `converter.convert(data)` returns `list[Model]`
- [x] **API-03**: `from_arrow(Model, data)` convenience one-shot function
- [x] **API-04**: Iterator/generator API for lazy model yielding (memory-constrained large datasets)
- [x] **API-05**: Type stubs (`.pyi`) for the Rust extension module

## v2 Requirements

### Extended Types (Future)

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
| BUILD-01 | Phase 1 | Complete |
| BUILD-02 | Phase 1 | Complete |
| BUILD-03 | Phase 1 | Complete |
| SCHEMA-01 | Phase 2 | Complete |
| SCHEMA-02 | Phase 2 | Complete |
| SCHEMA-03 | Phase 3 | Complete |
| SCHEMA-04 | Phase 3 | Complete |
| ALIAS-01 | Phase 3 | Complete |
| ALIAS-02 | Phase 3 | Complete |
| ALIAS-03 | Phase 3 | Complete |
| FAST-01 | Phase 2 | Complete |
| FAST-02 | Phase 3 | Complete |
| FAST-03 | Phase 2 | Complete |
| VALID-01 | Phase 5 | Complete |
| VALID-02 | Phase 5 | Complete |
| VALID-03 | Phase 5 | Complete |
| TYPE-01 | Phase 2 | Complete |
| TYPE-02 | Phase 2 | Complete |
| TYPE-03 | Phase 2 | Complete |
| TYPE-04 | Phase 2 | Complete |
| TYPE-05 | Phase 2 | Complete |
| NULL-01 | Phase 2 | Complete |
| NULL-02 | Phase 2 | Complete |
| NULL-03 | Phase 2 | Complete |
| TEMP-01 | Phase 4 | Complete |
| TEMP-02 | Phase 4 | Complete |
| TEMP-03 | Phase 4 | Complete |
| TEMP-04 | Phase 4 | Complete |
| TEMP-05 | Phase 4 | Complete |
| CPLX-01 | Phase 4 | Complete |
| CPLX-02 | Phase 4 | Complete |
| CPLX-03 | Phase 4 | Complete |
| CPLX-04 | Phase 4 | Complete |
| CPLX-05 | Phase 4 | Complete |
| INPUT-01 | Phase 2 | Complete |
| INPUT-02 | Phase 3 | Complete |
| INPUT-03 | Phase 1 | Complete |
| API-01 | Phase 2 | Complete |
| API-02 | Phase 2 | Complete |
| API-03 | Phase 3 | Complete |
| API-04 | Phase 5 | Complete |
| API-05 | Phase 5 | Complete |
| EXT-FLOAT16 | Phase 6 | Complete |
| EXT-DEC128 | Phase 6 | Complete |
| EXT-DEC256 | Phase 6 | Complete |
| EXT-DEC32 | Phase 6 | Complete |
| EXT-DEC64 | Phase 6 | Complete |
| EXT-DATE64 | Phase 6 | Complete |
| EXT-TIME32 | Phase 6 | Complete |
| EXT-TIME64 | Phase 6 | Complete |
| EXT-INTERVAL | Phase 6 | Complete |
| EXT-BINARY | Phase 6 | Complete |
| EXT-FSBINARY | Phase 6 | Complete |
| EXT-UTF8VIEW | Phase 6 | Complete |
| EXT-BINVIEW | Phase 6 | Complete |
| EXT-FSLIST | Phase 6 | Complete |
| EXT-MAP | Phase 6 | Complete |
| EXT-REE | Phase 6 | Complete |
| EXT-UNION | Phase 6 | Complete |

**Coverage:**
- v1 requirements: 59 total
- Mapped to phases: 59
- Unmapped: 0

---
*Requirements defined: 2026-03-21*
*Last updated: 2026-03-22 after Phase 6 gap closure (added 17 EXT-* requirement definitions)*
