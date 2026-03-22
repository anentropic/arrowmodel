# Roadmap: arrowdantic

## Overview

Arrowdantic delivers dict-free, single-step conversion from Arrow buffers to Pydantic model instances via a Rust core. The roadmap moves from build infrastructure through a minimal spike that proves the performance hypothesis, then completes the core conversion API with alias resolution and full error handling, extends type coverage to temporals and nested structures, and finally adds the validated path and API polish. Each phase delivers a testable, coherent capability.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Build Foundation** - Maturin/PyO3 build system producing an importable `arrowdantic._core` Rust extension (completed 2026-03-21)
- [x] **Phase 2: Spike & Benchmark** - Minimal end-to-end primitive conversion with benchmark to prove performance hypothesis (completed 2026-03-22)
- [x] **Phase 3: Core Conversion** - Alias resolution, schema error handling, Table input, convenience API, and pre-interned strings
- [ ] **Phase 4: Extended Types** - Temporal types, lists, structs, dictionary arrays, and null type
- [ ] **Phase 5: Validated Path and API Polish** - Opt-in Pydantic validation, iterator API, and type stubs
- [ ] **Phase 6: Support All PyArrow Types** - Float16, Decimal, Date64, Time, Interval, Binary, Views, FixedSizeList, Map, REE, Union (gap closure in progress)

## Phase Details

### Phase 1: Build Foundation
**Goal**: A working maturin + PyO3 build pipeline that produces an importable Rust extension module
**Depends on**: Nothing (first phase)
**Requirements**: BUILD-01, BUILD-02, BUILD-03, INPUT-03
**Success Criteria** (what must be TRUE):
  1. `import arrowdantic._core` succeeds in a Python 3.11+ environment after `maturin develop`
  2. `pyproject.toml` is configured with maturin as build backend and `Cargo.toml` contains all required Rust dependencies (pyo3, arrow-rs, pyo3-arrow, serde_json, chrono)
  3. The Rust module can accept Arrow data via the PyCapsule/C Data Interface (pyo3-arrow) and return a Python object
**Plans**: 2 plans

Plans:
- [x] 01-01-PLAN.md -- Create Rust crate, configure maturin build backend, build and verify importable _core module
- [x] 01-02-PLAN.md -- Create build verification tests and update CI workflows for Rust toolchain

### Phase 2: Spike & Benchmark
**Goal**: A minimal end-to-end conversion path from Arrow RecordBatch to Pydantic models for primitive types, with a benchmark script that quantifies speedup over pyarrow's `to_pylist()` + `model_construct`
**Depends on**: Phase 1
**Requirements**: SCHEMA-01, SCHEMA-02, TYPE-01, TYPE-02, TYPE-03, TYPE-04, TYPE-05, NULL-01, NULL-02, NULL-03, FAST-01, FAST-03, INPUT-01, API-01, API-02
**Success Criteria** (what must be TRUE):
  1. `ArrowModelConverter(MyModel).convert(record_batch)` returns a list of `MyModel` instances with correct field values for int, uint, float, bool, and string columns, using field-name matching only (no alias resolution yet)
  2. Null values in Arrow columns produce `None` on the corresponding Pydantic field (value buffer at null indices is never read)
  3. A benchmark script comparing arrowdantic vs `to_pylist()` + `model_construct` demonstrates measurable speedup on a RecordBatch with 100k+ rows of primitive columns
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md -- Implement Rust ColumnExtractor and convert_record_batch, create Python ArrowModelConverter wrapper
- [x] 02-02-PLAN.md -- Create conversion correctness tests and pytest-benchmark comparison script

### Phase 3: Core Conversion
**Goal**: The full conversion API surface with alias resolution, schema mismatch errors, extra column handling, Table input, convenience function, and pre-interned string optimization
**Depends on**: Phase 2
**Requirements**: SCHEMA-03, SCHEMA-04, ALIAS-01, ALIAS-02, ALIAS-03, FAST-02, INPUT-02, API-03
**Success Criteria** (what must be TRUE):
  1. `ArrowModelConverter.convert()` raises `ValueError` before row processing when required Pydantic fields have no matching Arrow column, and silently ignores extra Arrow columns
  2. Pydantic alias resolution works correctly: `validation_alias` takes priority over `alias` over `field_name`, and `populate_by_name` allows both alias and field name when enabled
  3. `from_arrow(MyModel, data)` convenience function works as a one-shot conversion for both RecordBatch and Table inputs
  4. Pre-interned Python field name strings are reused across all rows (no per-row string allocation)
**Plans**: 2 plans

Plans:
- [x] 03-01-PLAN.md -- Alias resolution, schema error handling, and extra column handling
- [x] 03-02-PLAN.md -- Table input support, from_arrow convenience function, and pre-interned strings

### Phase 4: Extended Types
**Goal**: Users can convert Arrow data containing temporal columns, nested structures, lists, and dictionary-encoded columns into Pydantic models
**Depends on**: Phase 3
**Requirements**: TEMP-01, TEMP-02, TEMP-03, TEMP-04, TEMP-05, CPLX-01, CPLX-02, CPLX-03, CPLX-04, CPLX-05
**Success Criteria** (what must be TRUE):
  1. Date32 columns produce `datetime.date`, Timestamp columns produce naive or aware `datetime.datetime` depending on timezone presence, and Duration columns produce `datetime.timedelta` (nanosecond timestamps truncate to microsecond precision)
  2. List and LargeList columns produce Python `list` values with correct element types
  3. Struct columns produce nested Pydantic model instances (recursive construction), and a null struct value produces `None` for the entire nested model
  4. Dictionary-encoded columns resolve to the value type (indices decoded to values transparently)
  5. Null-typed columns produce `None` for every row
**Plans**: 2 plans

Plans:
- [x] 04-01-PLAN.md -- Temporal types (Date32, Timestamp, Duration), dictionary array unpacking, and null type support
- [x] 04-02-PLAN.md -- List, LargeList, and Struct type support with nested model class passing API

### Phase 5: Validated Path and API Polish
**Goal**: Users can opt into full Pydantic validation for untrusted data, iterate results lazily for large datasets, and get IDE autocompletion via type stubs
**Depends on**: Phase 4
**Requirements**: VALID-01, VALID-02, VALID-03, API-04, API-05
**Success Criteria** (what must be TRUE):
  1. `ArrowModelConverter(Model, validate=True)` passes each row through full Pydantic validation (serde_json serialization in Rust, then `model_validate_json`), and validation errors surface as Pydantic `ValidationError`
  2. An iterator/generator API yields model instances lazily without materializing the full list in memory
  3. Type stubs (`.pyi` file) exist for the `_core` extension module, providing IDE autocompletion and type checking for all public functions and classes
  4. Basedpyright suppressions in `pyproject.toml` (`reportUnknownVariableType`, `reportUnknownMemberType`, `reportUnknownArgumentType`, `reportAttributeAccessIssue`) are removed and `basedpyright` passes cleanly
**Plans**: 2 plans

Plans:
- [x] 05-01-PLAN.md -- Validated conversion path: serde_json row serialization in Rust + model_validate_json
- [x] 05-02-PLAN.md -- Iterator API, type stubs, and basedpyright suppression removal

### Phase 6: Support All PyArrow Types
**Goal**: Complete Arrow DataType coverage by adding support for Float16, Decimal (128/256/32/64), Date64, Time32/64, Interval (all 3 variants), Binary/LargeBinary/FixedSizeBinary, Utf8View/BinaryView, FixedSizeList, Map, RunEndEncoded, and Union (sparse + dense)
**Depends on**: Phase 5
**Requirements**: EXT-FLOAT16, EXT-DEC128, EXT-DEC256, EXT-DEC32, EXT-DEC64, EXT-DATE64, EXT-TIME32, EXT-TIME64, EXT-INTERVAL, EXT-BINARY, EXT-FSBINARY, EXT-UTF8VIEW, EXT-BINVIEW, EXT-FSLIST, EXT-MAP, EXT-REE, EXT-UNION
**Success Criteria** (what must be TRUE):
  1. All scalar types convert correctly: Float16 to float, Decimal128/256/32/64 to Decimal (precision preserved), Date64 to datetime.datetime, Time32/64 to datetime.time
  2. Binary types produce bytes: Binary, LargeBinary, FixedSizeBinary, BinaryView
  3. View types work identically to their non-view counterparts: Utf8View to str, BinaryView to bytes
  4. Interval types produce (months, days, nanos) tuples for all 3 variants
  5. FixedSizeList and Map container types extract elements correctly with recursive handling
  6. RunEndEncoded columns are transparently pre-unpacked (same pattern as Dictionary)
  7. Union columns (sparse and dense) extract the active variant's value per row
  8. All new types work in both fast path (model_construct) and validated path (model_validate_json)
**Plans**: 4 plans

Plans:
- [x] 06-01-PLAN.md -- Scalar, temporal, and binary types: Float16, Decimal128/256/32/64, Date64, Time32/64, Binary, FixedSizeBinary, Utf8View, BinaryView
- [x] 06-02-PLAN.md -- Container and compound types: Interval (3 variants), FixedSizeList, Map, RunEndEncoded, Union (sparse + dense)
- [ ] 06-03-PLAN.md -- Gap closure: Fix REE bug in convert_table/convert_table_validated, add Decimal32/64 test coverage
- [x] 06-04-PLAN.md -- Gap closure: Add Phase 6 requirement IDs to REQUIREMENTS.md traceability

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Build Foundation | 2/2 | Complete    | 2026-03-21 |
| 2. Spike & Benchmark | 2/2 | Complete    | 2026-03-22 |
| 3. Core Conversion | 2/2 | Complete    | 2026-03-22 |
| 4. Extended Types | 0/2 | In Progress | - |
| 5. Validated Path and API Polish | 1/2 | In Progress|  |
| 6. Support All PyArrow Types | 2/4 | Gap Closure | - |
