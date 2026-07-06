---
phase: 02-spike-benchmark
plan: 02
subsystem: testing
tags: [pytest, pytest-benchmark, pydantic, pyarrow, correctness-tests, performance-benchmark]

# Dependency graph
requires:
  - phase: 02-spike-benchmark
    provides: ArrowModelConverter class, convert_record_batch Rust function, ColumnExtractor with null-safe extraction
provides:
  - 18 conversion correctness tests covering all 15 Phase 2 requirement IDs
  - 7 typed RecordBatch fixtures for all primitive types and nulls
  - Benchmark comparison script (arrowdantic vs to_pylist + model_construct)
  - Benchmark results showing ~1.7x speedup at 100k rows
affects: [03-core-conversion, 04-extended-types, 05-validated-path]

# Tech tracking
tech-stack:
  added: [pytest-benchmark>=5.2.3]
  patterns: [fixture-per-type-family, benchmark-setup-outside-measurement, class-per-requirement-area]

key-files:
  created: [tests/test_convert.py, benchmarks/bench_convert.py]
  modified: [tests/conftest.py, pyproject.toml, src/arrowdantic/__init__.py]

key-decisions:
  - "Models defined in test file rather than conftest.py to avoid import issues with pytest conftest auto-loading"
  - "Benchmark measures converter.convert() only, batch creation in setup (per Pitfall 4)"
  - "model_fields_set test verifies kwargs are tracked (Pydantic v2 model_construct sets fields_set from kwargs)"

patterns-established:
  - "Class-per-requirement-area: TestSchemaMapping, TestPrimitiveTypes, TestNullHandling, TestModelConstruct, TestAPI, TestEndToEnd"
  - "Fixture-per-type-family: int_batch, uint_batch, float_batch, bool_batch, string_batch, mixed_batch, nullable_batch, all_null_batch"
  - "Benchmark setup: make_batch() and converter creation outside benchmark() call"

requirements-completed: [SCHEMA-01, SCHEMA-02, TYPE-01, TYPE-02, TYPE-03, TYPE-04, TYPE-05, NULL-01, NULL-02, NULL-03, FAST-01, FAST-03, INPUT-01, API-01, API-02]

# Metrics
duration: 4min
completed: 2026-03-22
---

# Phase 2 Plan 2: Conversion Tests & Benchmark Summary

**18 correctness tests covering all 15 requirement IDs plus pytest-benchmark comparison showing ~1.7x speedup over to_pylist+model_construct at 100k rows**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-22T00:44:02Z
- **Completed:** 2026-03-22T00:48:17Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Created 18 tests in 6 classes verifying all primitive type conversions, null handling, schema cross-referencing, API contract, and end-to-end integration
- Added 7 typed RecordBatch fixtures covering int, uint, float, bool, string, mixed, and nullable scenarios
- Created benchmark script comparing arrowdantic vs to_pylist+model_construct at 10k and 100k rows
- Benchmark results: arrowdantic is ~1.7x faster at 100k rows (276ms vs 478ms median)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create conversion correctness tests and fixtures** - `b1f64b7` (test)
2. **Task 2: Create benchmark script and add pytest-benchmark dependency** - `ffa3cfb` (feat)

## Files Created/Modified
- `tests/test_convert.py` - 18 tests in 6 classes covering all 15 Phase 2 requirement IDs
- `tests/conftest.py` - 7 new typed RecordBatch fixtures (preserved existing sample_record_batch)
- `benchmarks/bench_convert.py` - 4 benchmark functions comparing arrowdantic vs baseline at 10k and 100k rows
- `pyproject.toml` - Added pytest-benchmark>=5.2.3 to dev dependencies
- `src/arrowdantic/__init__.py` - Fixed get_field_index bug (returns -1, not KeyError)

## Decisions Made
- Pydantic model classes defined in test_convert.py rather than conftest.py to avoid `from conftest import` issues (pytest auto-loads conftest but it is not directly importable as a Python module)
- Benchmark batch creation placed outside benchmark() measurement to ensure fair comparison (per research Pitfall 4)
- model_construct test updated to match actual Pydantic v2 behavior: model_fields_set contains kwargs keys, not empty set

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed get_field_index missing field detection**
- **Found during:** Task 1 (test_raises_on_missing_field)
- **Issue:** ArrowModelConverter.convert() caught KeyError from get_field_index, but pyarrow returns -1 for missing fields instead of raising KeyError. The -1 was passed as a usize to Rust, causing OverflowError.
- **Fix:** Changed from try/except KeyError to checking `col_idx < 0` with explicit ValueError
- **Files modified:** src/arrowdantic/__init__.py
- **Verification:** test_raises_on_missing_field passes
- **Committed in:** b1f64b7 (Task 1 commit)

**2. [Rule 1 - Bug] Fixed model_construct model_fields_set assertion**
- **Found during:** Task 1 (test_uses_model_construct_not_validate)
- **Issue:** Plan assumed model_construct produces empty model_fields_set, but Pydantic v2 model_construct with kwargs sets model_fields_set to the provided field names
- **Fix:** Updated assertion to check model_fields_set equals the set of provided field names
- **Files modified:** tests/test_convert.py
- **Verification:** test_uses_model_construct_not_validate passes
- **Committed in:** b1f64b7 (Task 1 commit)

**3. [Rule 3 - Blocking] Fixed conftest import in test_convert.py**
- **Found during:** Task 1 (test collection)
- **Issue:** `from conftest import ...` fails because conftest.py is not a regular importable module (pytest auto-loads it but it is not on sys.path by default in all configurations)
- **Fix:** Moved Pydantic model definitions into test_convert.py and kept conftest.py for fixtures only
- **Files modified:** tests/test_convert.py, tests/conftest.py
- **Verification:** All tests collect and pass
- **Committed in:** b1f64b7 (Task 1 commit)

---

**Total deviations:** 3 auto-fixed (2 bugs, 1 blocking)
**Impact on plan:** All auto-fixes necessary for correctness. No scope creep. The plan's code examples had minor misunderstandings of pyarrow API (get_field_index returns -1) and Pydantic v2 behavior (model_fields_set semantics).

## Benchmark Results

| Test | Mean | Median | Rounds |
|------|------|--------|--------|
| arrowdantic 10k | 42.5ms | 32.0ms | 32 |
| baseline 10k | 42.4ms | 40.1ms | 27 |
| arrowdantic 100k | 275.6ms | 261.1ms | 5 |
| baseline 100k | 478.3ms | 476.9ms | 3 |

**Speedup at 100k rows:** ~1.7x (arrowdantic 276ms vs baseline 478ms mean)
**Speedup at 10k rows:** ~1.0x (roughly equivalent, overhead dominates)

The speedup at 100k rows validates the Phase 2 performance hypothesis. The Rust hot loop eliminates dict allocation and Python loop overhead for larger batches. Phase 3 optimizations (pre-interned strings, __setattr__ bypass) should widen this gap further.

## Issues Encountered
None beyond the auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 15 Phase 2 requirement IDs tested and verified
- Benchmark baseline established for future comparison
- ArrowModelConverter API stable with 28 total tests green
- Ready for Phase 3 (Core Conversion) with confidence in correctness and measurable performance

---
*Phase: 02-spike-benchmark*
*Completed: 2026-03-22*

## Self-Check: PASSED

- [x] tests/test_convert.py exists
- [x] tests/conftest.py exists
- [x] benchmarks/bench_convert.py exists
- [x] 02-02-SUMMARY.md exists
- [x] Commit b1f64b7 exists
- [x] Commit ffa3cfb exists
- [x] All 6 test classes present
- [x] All 7 fixtures present (+ sample_record_batch preserved)
- [x] pytest-benchmark in pyproject.toml
- [x] All acceptance criteria grep checks pass
