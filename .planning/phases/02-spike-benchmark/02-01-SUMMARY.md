---
phase: 02-spike-benchmark
plan: 01
subsystem: core-conversion
tags: [pyo3, arrow, pydantic, model_construct, null-handling, column-extraction]

# Dependency graph
requires:
  - phase: 01-build-foundation
    provides: PyO3 extension module (_core), Cargo.toml with pyo3/arrow deps, maturin build system
provides:
  - ColumnExtractor enum with null-safe value extraction for 13 primitive types
  - convert_record_batch Rust pyfunction for Arrow-to-Pydantic conversion
  - ArrowModelConverter Python class with convert() method
affects: [02-spike-benchmark, 03-core-conversion, 04-extended-types, 05-validated-path]

# Tech tracking
tech-stack:
  added: []
  patterns: [column-oriented-downcast-once, null-check-before-value, interned-field-names, model_construct-with-kwargs]

key-files:
  created: [rust/src/extract.rs]
  modified: [rust/src/lib.rs, src/arrowdantic/__init__.py]

key-decisions:
  - "Schema matching at convert() time (not init time) because each batch may have different column order"
  - "model_construct via call_method with kwargs PyDict (not call_method1 with positional arg)"
  - "Runtime PyString::intern for field names (not intern! macro which requires compile-time literals)"
  - "Collect into Vec<PyObject> then PyList::new (not PyList append loop) per Pitfall 5"
  - "Boolean extraction uses to_owned().into_any().unbind() due to PyO3 Borrowed type semantics"

patterns-established:
  - "Column-oriented downcast-once: match DataType before row loop, store typed array refs"
  - "Null-safe extraction: always check is_null(row) before value(row)"
  - "Runtime string interning: PyString::intern(py, &name) for field names"
  - "kwargs model construction: PyDict + call_method(model_construct, (), Some(&kwargs))"

requirements-completed: [SCHEMA-01, SCHEMA-02, TYPE-01, TYPE-02, TYPE-03, TYPE-04, TYPE-05, NULL-01, NULL-02, NULL-03, FAST-01, FAST-03, INPUT-01, API-01, API-02]

# Metrics
duration: 4min
completed: 2026-03-22
---

# Phase 2 Plan 1: Core Conversion Pipeline Summary

**Rust ColumnExtractor with null-safe extraction for 13 Arrow primitive types, convert_record_batch pyfunction, and Python ArrowModelConverter class producing Pydantic instances via model_construct**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-22T00:37:46Z
- **Completed:** 2026-03-22T00:41:32Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Implemented ColumnExtractor enum covering all 13 primitive Arrow types (Int8-64, UInt8-64, Float32/64, Boolean, Utf8, LargeUtf8) with null-safe value extraction
- Added convert_record_batch Rust function that interns field names once, downcasts columns once, then loops rows building kwargs PyDict and calling model_construct
- Created ArrowModelConverter Python class that cross-references Arrow schema against Pydantic model_fields and delegates to the Rust hot loop
- Verified end-to-end pipeline: ArrowModelConverter(Model).convert(batch) produces correct list[Model] for all primitive types including null handling

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement Rust ColumnExtractor and convert_record_batch** - `fd165b9` (feat)
2. **Task 2: Create Python ArrowModelConverter class** - `80bbd49` (feat)

## Files Created/Modified
- `rust/src/extract.rs` - ColumnExtractor enum with prepare_extractor and extract_value methods for 13 primitive types
- `rust/src/lib.rs` - Added extract module and convert_record_batch pyfunction with interned names and kwargs model_construct
- `src/arrowdantic/__init__.py` - ArrowModelConverter class with schema cross-referencing and convert() delegation to Rust

## Decisions Made
- Schema matching at convert() time rather than init time, because each batch may have different column order (per research Open Question 2)
- Used `call_method("model_construct", (), Some(&kwargs))` for correct kwargs unpacking (avoiding Pitfall 3)
- Used `PyString::intern(py, &name)` for runtime string interning instead of `intern!()` macro (avoiding Pitfall 1)
- Collected results into `Vec<PyObject>` then `PyList::new` instead of append loop (avoiding Pitfall 5)
- Boolean extraction requires `.to_owned().into_any().unbind()` chain due to PyO3 0.28 `Borrowed` type for `bool.into_pyobject()`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed PyObject type alias for PyO3 0.28**
- **Found during:** Task 1 (ColumnExtractor implementation)
- **Issue:** `PyObject` is not in scope with `pyo3::prelude::*` in PyO3 0.28; the type was renamed/reorganized
- **Fix:** Added `type PyObject = Py<PyAny>;` type alias in both extract.rs and lib.rs
- **Files modified:** rust/src/extract.rs, rust/src/lib.rs
- **Verification:** cargo check passes
- **Committed in:** fd165b9 (Task 1 commit)

**2. [Rule 1 - Bug] Fixed schema temporary lifetime in convert_record_batch**
- **Found during:** Task 1 (convert_record_batch implementation)
- **Issue:** `rb.schema().field(idx).data_type()` creates a temporary `SchemaRef` that is dropped before the borrow is used
- **Fix:** Bound schema to a `let` binding before the loop: `let schema = rb.schema();`
- **Files modified:** rust/src/lib.rs
- **Verification:** cargo check passes
- **Committed in:** fd165b9 (Task 1 commit)

**3. [Rule 1 - Bug] Fixed Boolean into_pyobject Borrowed type handling**
- **Found during:** Task 1 (ColumnExtractor implementation)
- **Issue:** `bool.into_pyobject(py)` returns `Borrowed<'_, '_, PyBool>` which cannot be consumed by `into_any()`
- **Fix:** Used `.to_owned()` to convert `Borrowed` to `Bound` before calling `.into_any().unbind()`
- **Files modified:** rust/src/extract.rs
- **Verification:** cargo check passes
- **Committed in:** fd165b9 (Task 1 commit)

---

**Total deviations:** 3 auto-fixed (3 bugs - PyO3 0.28 API specifics)
**Impact on plan:** All auto-fixes necessary for compilation. No scope creep. The plan's code examples were close but needed minor adjustments for PyO3 0.28's actual API surface.

## Issues Encountered
None beyond the auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Core conversion pipeline complete and verified for all primitive types
- Ready for Plan 02-02 (benchmark comparison against to_pylist + model_construct baseline)
- ArrowModelConverter API stable for tests and benchmarks
- All 10 existing Phase 1 tests continue to pass

---
*Phase: 02-spike-benchmark*
*Completed: 2026-03-22*

## Self-Check: PASSED

- [x] rust/src/extract.rs exists
- [x] rust/src/lib.rs exists
- [x] src/arrowdantic/__init__.py exists
- [x] 02-01-SUMMARY.md exists
- [x] Commit fd165b9 exists
- [x] Commit 80bbd49 exists
