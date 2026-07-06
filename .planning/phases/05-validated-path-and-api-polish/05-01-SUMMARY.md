---
phase: 05-validated-path-and-api-polish
plan: 01
subsystem: api
tags: [serde_json, pydantic, model_validate_json, validated-path, json-serialization]

# Dependency graph
requires:
  - phase: 04-extended-types
    provides: "ColumnExtractor with all Arrow type variants (primitives, temporals, lists, structs, dictionary, null)"
provides:
  - "extract_json_value method on ColumnExtractor for all variants"
  - "convert_record_batch_validated and convert_table_validated Rust functions"
  - "Python-side branching in convert() on validate=True"
  - "timedelta_to_iso8601 helper for Duration ISO 8601 formatting"
affects: [05-02, benchmarks]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Parallel JSON extraction path alongside PyObject extraction", "serde_json::Map per-row serialization with PyBytes hand-off to Pydantic"]

key-files:
  created: []
  modified:
    - "rust/src/extract.rs"
    - "rust/src/lib.rs"
    - "src/arrowdantic/__init__.py"
    - "tests/test_convert.py"

key-decisions:
  - "Append +00:00 to tz-aware timestamp JSON strings so Pydantic produces aware datetimes"
  - "NaN/Infinity floats serialize as JSON null (not error) per Pitfall 5"
  - "extract_json_value takes py: Python parameter for Struct field name access and List extractor creation"
  - "Shared extract_naive_dt_value and extract_duration_value helpers for DRY temporal extraction"

patterns-established:
  - "Validated path: extract_json_value -> serde_json::to_vec -> PyBytes -> model_validate_json"
  - "Float NaN/Infinity -> Value::Null in JSON serialization"
  - "ISO 8601 duration format (PxDTxHxMxS) for timedelta JSON serialization"

requirements-completed: [VALID-01, VALID-02, VALID-03]

# Metrics
duration: 5min
completed: 2026-03-22
---

# Phase 5 Plan 1: Validated Path Summary

**Dual-path architecture complete: serde_json row serialization to model_validate_json for full Pydantic validation on all Arrow types**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-22T12:35:34Z
- **Completed:** 2026-03-22T12:40:59Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 4

## Accomplishments
- Implemented extract_json_value on ColumnExtractor covering all 21 Arrow type variants (Int8-64, UInt8-64, Float32/64, Boolean, Utf8, LargeUtf8, Date32, TimestampNaive, TimestampAware, Duration, List, LargeList, Struct, Null)
- Added convert_record_batch_validated and convert_table_validated Rust functions with full JSON serialization pipeline
- Python convert() now branches on validate=True to use validated or fast path
- NaN/Infinity floats safely produce JSON null instead of serde_json errors
- 13 new tests (11 validated path + 2 validation error tests), all 98 total tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests for validated path** - `478e72b` (test)
2. **Task 1 (GREEN): Implement validated conversion path** - `a8a5f38` (feat)

_TDD task: RED wrote failing tests, GREEN implemented the feature._

## Files Created/Modified
- `rust/src/extract.rs` - Added extract_json_value method, timedelta_to_iso8601 helper, extract_naive_dt_value and extract_duration_value shared helpers
- `rust/src/lib.rs` - Added convert_record_batch_validated and convert_table_validated pyfunctions, PyBytes import
- `src/arrowdantic/__init__.py` - Branching in convert() on self._validate for validated vs fast path
- `tests/test_convert.py` - TestValidatedPath (11 tests) and TestValidationErrors (2 tests) classes

## Decisions Made
- Append `+00:00` to tz-aware timestamp JSON strings so Pydantic produces tz-aware datetimes (Arrow stores tz timestamps in UTC)
- NaN/Infinity floats serialize as JSON null rather than erroring (Pitfall 5 from research)
- extract_json_value requires `py: Python` parameter because Struct variant stores field names as `Py<PyString>` and List/LargeList need `prepare_extractor`
- Added shared `extract_naive_dt_value` and `extract_duration_value` helpers to avoid duplicating temporal extraction logic between extract_value and extract_json_value

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Timezone-aware timestamp JSON format**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** Plan suggested formatting tz-aware timestamps as naive ISO 8601 strings and letting Pydantic handle timezone. But Pydantic produces naive datetimes from naive strings, even for `datetime.datetime` fields.
- **Fix:** Append `+00:00` to tz-aware timestamp JSON strings since Arrow stores timestamps in UTC.
- **Files modified:** rust/src/extract.rs
- **Verification:** test_validated_timestamp_aware passes (tzinfo is not None)
- **Committed in:** a8a5f38

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Essential for correctness of tz-aware datetime validation. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Validated path complete, ready for Plan 02 (type stubs and API polish)
- All 98 tests pass including full validated path coverage

---
*Phase: 05-validated-path-and-api-polish*
*Completed: 2026-03-22*
