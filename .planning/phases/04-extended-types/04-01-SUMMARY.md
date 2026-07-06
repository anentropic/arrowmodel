---
phase: 04-extended-types
plan: 01
subsystem: conversion
tags: [arrow, pyo3, chrono, temporal, datetime, dictionary, null, date32, timestamp, duration, zoneinfo]

# Dependency graph
requires:
  - phase: 03-core-conversion
    provides: "ColumnExtractor enum with primitive types, prepare_extractor, extract_value pattern"
provides:
  - "Date32 -> datetime.date extraction via chrono feature"
  - "Timestamp (naive/aware) -> datetime.datetime extraction"
  - "Duration -> datetime.timedelta extraction"
  - "Dictionary array pre-unpacking via arrow-cast"
  - "Null type extraction (always None)"
  - "ZoneInfo caching per batch for timezone-aware timestamps"
affects: [04-extended-types, 05-validated-path]

# Tech tracking
tech-stack:
  added: [arrow-cast 58, pyo3 chrono feature]
  patterns: [dictionary pre-unpacking, temporal extraction via chrono, ZoneInfo caching]

key-files:
  created: []
  modified:
    - rust/Cargo.toml
    - rust/src/extract.rs
    - rust/src/lib.rs
    - tests/test_convert.py
    - tests/conftest.py

key-decisions:
  - "Enable pyo3 chrono feature for automatic NaiveDate/NaiveDateTime/TimeDelta to Python datetime conversion"
  - "Pre-unpack dictionary columns in lib.rs before building extractors to solve lifetime ownership"
  - "Cache ZoneInfo object per batch in TimestampAware variant (not per row)"
  - "Use Bound::cast instead of deprecated downcast for PyTzInfo"

patterns-established:
  - "Temporal extraction: arrow-rs value_as_date/datetime/duration + pyo3 chrono IntoPyObject"
  - "Timezone-aware timestamps: extract naive components then PyDateTime::new with cached ZoneInfo"
  - "Dictionary handling: arrow_cast::cast to unpack before extractor preparation"
  - "Null type: unconditional py.None() without is_null check (NullArray has no null buffer)"

requirements-completed: [TEMP-01, TEMP-02, TEMP-03, TEMP-04, TEMP-05, CPLX-04, CPLX-05]

# Metrics
duration: 5min
completed: 2026-03-22
---

# Phase 4 Plan 1: Extended Types Summary

**Temporal extractors (Date32, Timestamp naive/aware, Duration), dictionary pre-unpacking via arrow-cast, and null type support added to ColumnExtractor**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-22T11:07:50Z
- **Completed:** 2026-03-22T11:13:06Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Extended ColumnExtractor with 5 new variants: Date32, TimestampNaive, TimestampAware, Duration, Null
- Dictionary columns auto-unpacked to value type via arrow_cast::cast before extractor preparation
- 12 new Python tests covering all temporal types, dictionary decoding, and null type handling
- All 74 tests pass (52 existing + 12 new + 10 other test files)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add temporal, dictionary, and null ColumnExtractor variants in Rust** - `284fce7` (feat)
2. **Task 2: Add Python tests for temporal types, dictionary, and null type** - `2c11f0c` (test)

## Files Created/Modified
- `rust/Cargo.toml` - Added chrono feature on pyo3, added arrow-cast dependency
- `rust/src/extract.rs` - Extended ColumnExtractor with Date32, TimestampNaive, TimestampAware, Duration, Null variants
- `rust/src/lib.rs` - Added unpack_columns helper for dictionary pre-unpacking, updated convert_record_batch and convert_table
- `tests/test_convert.py` - Added TestTemporalTypes (7 tests), TestDictionaryType (3 tests), TestNullType (2 tests)
- `tests/conftest.py` - Added fixtures for date32, timestamp, duration, and dictionary batches

## Decisions Made
- Enabled pyo3 chrono feature for automatic IntoPyObject conversions (NaiveDate -> PyDate, NaiveDateTime -> PyDateTime, TimeDelta -> PyDelta)
- Pre-unpack dictionary columns in lib.rs unpack_columns helper to solve the lifetime issue (cast returns owned ArrayRef, extractors borrow)
- Cache ZoneInfo once per batch in TimestampAware variant to avoid per-row Python import overhead
- Used Bound::cast instead of deprecated downcast method for PyTzInfo downcasting

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed deprecated downcast method warning**
- **Found during:** Task 1
- **Issue:** pyo3 0.28 deprecates `downcast()` in favor of `cast()`
- **Fix:** Changed `tz_bound.downcast::<PyTzInfo>()` to `tz_bound.cast::<PyTzInfo>()`
- **Files modified:** rust/src/extract.rs
- **Verification:** Clean compile with no warnings
- **Committed in:** 284fce7

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Minor API update to avoid deprecation warning. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Temporal type extractors ready for Phase 4 Plan 2 (List, LargeList, Struct complex types)
- Dictionary pre-unpacking pattern established and working for any dictionary key/value type combination
- prepare_extractor now accepts Python<'_> parameter, required for future complex type extractors

## Self-Check: PASSED

All files exist, all commits verified, all acceptance criteria met. 74/74 tests pass.

---
*Phase: 04-extended-types*
*Completed: 2026-03-22*
