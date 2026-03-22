---
phase: 04-extended-types
plan: 02
subsystem: conversion
tags: [arrow, pyo3, list, largelist, struct, nested-model, model-construct, pydantic, complex-types]

# Dependency graph
requires:
  - phase: 04-extended-types
    plan: 01
    provides: "ColumnExtractor with temporal/dictionary/null variants, prepare_extractor with Python<'_> parameter"
provides:
  - "List(T) -> Python list extraction with recursive element handling"
  - "LargeList(T) -> Python list extraction identical to List"
  - "Struct -> nested Pydantic model instances via recursive model_construct"
  - "field_specs API replacing col_indices+field_names for nested model class passing"
  - "_get_nested_model helper for Pydantic BaseModel annotation introspection"
affects: [05-validated-path]

# Tech tracking
tech-stack:
  added: []
  patterns: [field_specs API, recursive struct introspection, temporary extractor per list row]

key-files:
  created: []
  modified:
    - rust/src/extract.rs
    - rust/src/lib.rs
    - src/arrowdantic/__init__.py
    - tests/test_convert.py
    - tests/conftest.py

key-decisions:
  - "Replace col_indices+field_names with field_specs tuples (col_index, field_name, nested_model_cls) for passing nested model classes to Rust"
  - "Recursive struct introspection: Rust calls back into Python _get_nested_model to discover child struct model classes"
  - "Temporary extractor per list row: create fresh ColumnExtractor for each list element sub-array (avoids lifetime issues)"
  - "Store child DataType in List/LargeList variants rather than pre-built child extractor (solves ListArray.value() ownership)"

patterns-established:
  - "field_specs API: Python passes (col_index, field_name, nested_model_cls) tuples to Rust"
  - "Recursive struct preparation: prepare_extractor introspects Pydantic model_fields for child struct types"
  - "List extraction: arr.value(row) returns ArrayRef, create temporary extractor, extract elements"
  - "Nested model_construct: Struct extractor calls model_construct on nested Pydantic model class"

requirements-completed: [CPLX-01, CPLX-02, CPLX-03]

# Metrics
duration: 5min
completed: 2026-03-22
---

# Phase 4 Plan 2: List, LargeList, Struct Types Summary

**List/LargeList/Struct ColumnExtractor variants with recursive nested model construction via field_specs API**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-22T11:15:25Z
- **Completed:** 2026-03-22T11:20:25Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Extended ColumnExtractor with 3 new variants: List, LargeList, Struct
- Replaced col_indices+field_names API with field_specs for passing nested model class references
- Added _get_nested_model Python helper for Pydantic BaseModel annotation introspection
- 11 new Python tests covering list types (6 tests) and struct types (5 tests)
- All 85 tests pass (75 convert tests + 10 other tests)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add List, LargeList, and Struct extractors with API changes** - `3a30f12` (feat)
2. **Task 2: Add Python tests for list, large list, and struct types** - `4392c28` (test)

## Files Created/Modified
- `rust/src/extract.rs` - Added List, LargeList, Struct variants to ColumnExtractor; updated prepare_extractor with nested_model parameter and recursive struct introspection
- `rust/src/lib.rs` - Replaced col_indices+field_names with field_specs in convert_record_batch and convert_table
- `src/arrowdantic/__init__.py` - Added _get_nested_model helper; updated _resolve_columns to return field_specs with nested model classes; updated convert() calls
- `tests/test_convert.py` - Added TestListTypes (6 tests), TestStructTypes (5 tests), Pydantic models (AddressModel, PersonModel, ListIntModel, etc.)
- `tests/conftest.py` - Added fixtures: list_int_batch, list_str_batch, struct_batch

## Decisions Made
- Replaced col_indices+field_names with field_specs tuples to support passing nested model classes from Python to Rust without a separate mapping parameter
- Rust-side recursive struct preparation: prepare_extractor calls back into Python _get_nested_model to discover child struct model classes, enabling arbitrary nesting depth
- Temporary extractor per list row: each ListArray.value(row) returns an owned ArrayRef, so a fresh ColumnExtractor is created per row's sub-array (avoids lifetime issues with borrowed references)
- Store child DataType (not pre-built extractor) in List/LargeList variants because the child array changes per row

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed recursive struct introspection for nested struct models**
- **Found during:** Task 2 (test_struct_nested)
- **Issue:** prepare_extractor for Struct passed None for all child nested_model parameters, causing nested structs (struct inside struct) to fail with "Struct column requires a nested Pydantic model class"
- **Fix:** Added Pydantic model_fields introspection in Rust prepare_extractor: calls Python _get_nested_model on each child field's annotation to discover nested BaseModel subclasses
- **Files modified:** rust/src/extract.rs
- **Verification:** test_struct_nested passes with doubly-nested OuterModel/InnerModel
- **Committed in:** 4392c28

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Required for nested struct correctness. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All complex types (List, LargeList, Struct) fully working alongside temporal types from Plan 01
- Phase 4 is complete -- ready for Phase 5 (Validated Path)
- field_specs API established for passing nested model metadata to Rust

## Self-Check: PASSED

All files exist, all commits verified, all 14 acceptance criteria met. 85/85 tests pass.

---
*Phase: 04-extended-types*
*Completed: 2026-03-22*
