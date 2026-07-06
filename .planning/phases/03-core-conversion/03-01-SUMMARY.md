---
phase: 03-core-conversion
plan: 01
subsystem: api
tags: [pydantic, alias, schema-validation, arrow, python]

# Dependency graph
requires:
  - phase: 02-spike-benchmark
    provides: ArrowModelConverter with field-name-only matching and convert_record_batch Rust function
provides:
  - _build_field_map function for alias-aware column name resolution
  - _resolve_columns method for schema validation with required/optional awareness
  - Alias priority chain (validation_alias > alias > field_name)
  - populate_by_name / validate_by_name support
  - NotImplementedError for AliasPath, AliasChoices, AliasGenerator
affects: [03-core-conversion, 04-extended-types, 05-validated-path]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_build_field_map as module-level function for Pydantic model introspection"
    - "_resolve_columns with resolved_fields set to handle duplicate field_map entries"
    - "Schema validation at convert() time (not init) per Phase 2 decision"

key-files:
  created: []
  modified:
    - src/arrowdantic/__init__.py
    - tests/test_convert.py

key-decisions:
  - "Schema validation stays at convert() time per Phase 2 decision -- SCHEMA-03 interpreted as 'before row processing' not 'at construction'"
  - "_build_field_map is module-level (not a method) for testability and reuse"
  - "_resolve_columns uses resolved_fields set to handle populate_by_name producing multiple lookup names for same field"

patterns-established:
  - "Alias-aware field map: {arrow_column_name: pydantic_field_name} built once at init"
  - "Multiple lookup names per field: resolved_fields set prevents duplicate resolution"
  - "Optional fields missing from Arrow silently skipped (model_construct uses defaults)"

requirements-completed: [SCHEMA-03, SCHEMA-04, ALIAS-01, ALIAS-02, ALIAS-03]

# Metrics
duration: 5min
completed: 2026-03-22
---

# Phase 3 Plan 1: Schema Validation and Alias Resolution Summary

**Alias-aware ArrowModelConverter with validation_alias > alias > field_name priority, schema validation for missing required columns, and NotImplementedError for unsupported alias types**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-22T02:04:49Z
- **Completed:** 2026-03-22T02:09:33Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Implemented `_build_field_map` with full Pydantic alias resolution (validation_alias > alias > field_name)
- Implemented `_resolve_columns` with required/optional field awareness and extra-column tolerance
- Added populate_by_name and validate_by_name support with duplicate-safe resolution
- Added NotImplementedError for AliasPath, AliasChoices, and AliasGenerator
- 27 new tests covering all alias resolution and schema validation behaviors
- Zero regressions -- all 55 tests pass (18 Phase 2 + 10 smoke/arrowdantic + 27 new)

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement _build_field_map and _resolve_columns** - `76ff915` (test: RED), `02265d2` (feat: GREEN)
2. **Task 2: Add alias resolution and schema validation tests** - `011009f` (test: end-to-end tests + Rule 1 auto-fix)

_Note: TDD tasks have multiple commits (test -> feat)_

## Files Created/Modified
- `src/arrowdantic/__init__.py` - Added `_build_field_map` function, `_resolve_columns` method, updated `ArrowModelConverter.__init__` and `convert()` to use alias-aware resolution
- `tests/test_convert.py` - Added 9 test models (ValidationAliasModel, AliasModel, etc.), TestBuildFieldMap (9 tests), TestResolveColumns (5 tests), TestAliasResolution (9 tests), TestSchemaValidation (4 tests)

## Decisions Made
- Schema validation stays at `convert()` time per Phase 2 decision -- SCHEMA-03 interpreted as "before row processing" not "at construction" (Arrow schema not available at init)
- `_build_field_map` is module-level (not a method) for testability and reuse by future `from_arrow()` function
- `_resolve_columns` uses a `resolved_fields` set to handle `populate_by_name` producing multiple lookup names for the same Pydantic field

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed _resolve_columns for populate_by_name duplicate entries**
- **Found during:** Task 2 (end-to-end tests)
- **Issue:** When `populate_by_name=True`, field_map contained both `"userId"` and `"user_id"` mapping to `"user_id"`. The initial _resolve_columns iterated all entries and raised ValueError when the second lookup name wasn't found, even though the field was already resolved via the first lookup name.
- **Fix:** Added `resolved_fields` set to track which Pydantic fields have been resolved. Skip lookup names for already-resolved fields. Check missing required fields separately by iterating `model_fields`.
- **Files modified:** `src/arrowdantic/__init__.py`
- **Verification:** `test_populate_by_name` passes with both alias and field_name column names
- **Committed in:** `011009f` (Task 2 commit)

**2. [Rule 1 - Bug] Updated existing test regex for new error message format**
- **Found during:** Task 1 GREEN phase
- **Issue:** `test_raises_on_missing_field` matched old error message "Arrow schema has no column" but new `_resolve_columns` produces "missing required columns"
- **Fix:** Updated regex to `match="missing required columns"`
- **Files modified:** `tests/test_convert.py`
- **Verification:** Test passes with new error message
- **Committed in:** `02265d2` (Task 1 GREEN commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both auto-fixes necessary for correctness. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Alias-aware field map and schema validation are complete, ready for Phase 3 Plan 2 (Table support, from_arrow, string interning)
- All 55 tests pass, providing solid regression safety net

## Self-Check: PASSED

All files exist, all commits verified.

---
*Phase: 03-core-conversion*
*Completed: 2026-03-22*
