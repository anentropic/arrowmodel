---
phase: 03-core-conversion
plan: 02
subsystem: api
tags: [arrow, table, pyo3, pyo3-arrow, string-interning, convenience-api, python, rust]

# Dependency graph
requires:
  - phase: 03-core-conversion
    plan: 01
    provides: ArrowModelConverter with alias-aware _build_field_map and _resolve_columns
provides:
  - Rust convert_table function accepting PyTable with multi-batch iteration
  - Table dispatch in ArrowModelConverter.convert() via duck typing
  - from_arrow() one-shot convenience function (API-03)
  - FAST-02 string interning across all batches in convert_table
affects: [04-extended-types, 05-validated-path]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "PyTable.into_inner() decomposition for multi-batch iteration"
    - "Duck-type dispatch via hasattr(data, 'to_batches') to avoid pyarrow runtime dependency"
    - "PyString::intern for field names shared across all batches in convert_table"
    - "Vec::with_capacity(total_rows) pre-allocation for multi-batch results"

key-files:
  created: []
  modified:
    - rust/src/lib.rs
    - src/arrowdantic/__init__.py
    - tests/test_convert.py

key-decisions:
  - "Duck-type dispatch (hasattr to_batches) instead of isinstance(pa.Table) to avoid pyarrow runtime dependency"
  - "convert_table interns field name strings once and shares across all batches (FAST-02)"
  - "from_arrow creates temporary ArrowModelConverter -- no caching for one-shot use"

patterns-established:
  - "Table dispatch: hasattr(data, 'to_batches') for Table vs RecordBatch detection"
  - "Multi-batch processing: intern names once, iterate batches, concat results"
  - "Convenience function pattern: from_arrow wraps ArrowModelConverter construction + convert"

requirements-completed: [INPUT-02, API-03, FAST-02]

# Metrics
duration: 4min
completed: 2026-03-22
---

# Phase 3 Plan 2: Table Input, from_arrow, and String Interning Summary

**Rust convert_table with PyTable multi-batch iteration, duck-type Table dispatch, from_arrow convenience function, and FAST-02 cross-batch string interning**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-22T02:12:36Z
- **Completed:** 2026-03-22T02:16:45Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Implemented Rust `convert_table` function that accepts PyTable, decomposes into batches, and iterates with shared interned field names (FAST-02)
- Updated `ArrowModelConverter.convert()` with duck-type dispatch for Table vs RecordBatch input (INPUT-02)
- Added `from_arrow()` one-shot convenience function to public API (API-03)
- 7 new tests covering Table input (single, multi-batch, empty, aliased), from_arrow (RecordBatch, Table), and string interning correctness
- Zero regressions -- all 62 tests pass (52 conversion + 10 smoke/arrowdantic)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add convert_table Rust function and Table/from_arrow Python support** - `a4d4e09` (test: RED), `e054a5f` (feat: GREEN)
2. **Task 2: Add tests for Table input, from_arrow, and string interning** - Tests already written in Task 1 RED phase, all passing in GREEN

_Note: TDD tasks have multiple commits (test -> feat)_

## Files Created/Modified
- `rust/src/lib.rs` - Added `convert_table` function with `PyTable` input, multi-batch iteration, and `PyString::intern` for FAST-02 cross-batch string interning
- `src/arrowdantic/__init__.py` - Updated `convert()` with Table dispatch via `hasattr(data, "to_batches")`, added `from_arrow()` convenience function, updated `__all__` exports
- `tests/test_convert.py` - Added `TestTableInput` (4 tests), `TestFromArrow` (2 tests), `TestStringInterning` (1 test), and `from_arrow` import

## Decisions Made
- Used duck-type dispatch (`hasattr(data, "to_batches")`) instead of `isinstance(data, pa.Table)` to avoid requiring pyarrow as a runtime dependency -- any Arrow-PyCapsule-compatible library with a `to_batches` method will work
- `convert_table` interns field name strings once and shares the interned `Vec<Bound<PyString>>` across all batches, satisfying FAST-02 requirement
- `from_arrow` creates a temporary `ArrowModelConverter` on each call -- appropriate for one-shot use; users needing repeated conversions should construct a converter instance

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 3 (core-conversion) is fully complete: alias resolution, schema validation, Table input, from_arrow, string interning
- All 62 tests pass, providing solid regression safety net for Phase 4 (Extended Types)
- The ColumnExtractor enum in `extract.rs` is ready to be extended with date/time/decimal types

## Self-Check: PASSED

All files exist, all commits verified, all acceptance criteria met.

---
*Phase: 03-core-conversion*
*Completed: 2026-03-22*
