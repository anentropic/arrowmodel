---
phase: 05-validated-path-and-api-polish
plan: 02
subsystem: api
tags: [iterator, generator, type-stubs, pyright, pyi, lazy-iteration]

# Dependency graph
requires:
  - phase: 05-validated-path-and-api-polish/01
    provides: "Validated path (convert_record_batch_validated, convert_table_validated)"
provides:
  - "iter() method on ArrowModelConverter for lazy batch-by-batch yielding"
  - "iter_arrow() one-shot convenience function for lazy iteration"
  - "_core.pyi type stubs for all Rust extension functions"
  - "Clean basedpyright strict mode (no suppression flags for src/)"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Generator-based lazy iteration via yield from per-batch results"
    - "Sequence in stubs for covariant parameter types"
    - "executionEnvironments in pyright config for per-directory rule scoping"
    - "typing.cast for duck-type narrowing in union parameters"

key-files:
  created:
    - "src/arrowdantic/_core.pyi"
  modified:
    - "src/arrowdantic/__init__.py"
    - "pyproject.toml"
    - "tests/test_convert.py"

key-decisions:
  - "Use typing.cast for Table/RecordBatch narrowing instead of isinstance (preserves duck-typing for non-pyarrow inputs)"
  - "Scope pyarrow-stub-caused pyright rules to tests/ via executionEnvironments (src/ fully strict)"
  - "Use Sequence in _core.pyi stubs for field_specs param (Sequence is covariant, list is invariant)"

patterns-established:
  - "Pattern: Generator API wraps batch-level Rust calls with yield from for lazy memory semantics"
  - "Pattern: Type stubs use Sequence for input params, list for output returns"

requirements-completed: [API-04, API-05]

# Metrics
duration: 5min
completed: 2026-03-22
---

# Phase 05 Plan 02: Iterator API and Type Stubs Summary

**Lazy iterator/generator API (iter, iter_arrow) for memory-constrained scenarios plus _core.pyi stubs for IDE autocompletion with clean basedpyright strict mode**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-22T12:43:59Z
- **Completed:** 2026-03-22T12:49:28Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Added `iter()` method to ArrowModelConverter for lazy batch-by-batch model yielding (only one batch materialized at a time)
- Added `iter_arrow()` convenience function as one-shot lazy iteration entry point
- Created `_core.pyi` type stubs covering all 5 Rust extension functions with proper Sequence/list variance
- Removed 4 basedpyright suppressions from pyproject.toml; src/ now passes strict mode with zero suppressions
- Added executionEnvironments config to scope pyarrow-stub-related relaxations to tests/ only

## Task Commits

Each task was committed atomically:

1. **Task 1: Add iterator API (iter method and iter_arrow convenience function)** - `cf04f6d` (feat)
2. **Task 2: Add type stubs and remove basedpyright suppressions** - `4716343` (feat)

## Files Created/Modified
- `src/arrowdantic/__init__.py` - Added iter() method, iter_arrow() function, Iterator import, cast() for type narrowing
- `src/arrowdantic/_core.pyi` - Type stubs for record_batch_info, convert_record_batch, convert_table, convert_record_batch_validated, convert_table_validated
- `pyproject.toml` - Removed 4 pyright suppressions, added executionEnvironments for tests/
- `tests/test_convert.py` - Added TestIteratorAPI class with 6 tests

## Decisions Made
- Used `typing.cast` instead of `isinstance` for Table/RecordBatch type narrowing to preserve duck-typing compatibility with non-pyarrow Arrow implementations
- Scoped pyarrow-stub-caused pyright rules (reportUnknownMemberType, reportUnknownArgumentType, reportAttributeAccessIssue) to tests/ directory only via executionEnvironments, keeping src/ fully strict
- Used `Sequence` (covariant) instead of `list` (invariant) for `field_specs` parameter in stubs to accept `list[tuple[int, str, type[BaseModel] | None]]` without type errors

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed list invariance type errors in _core.pyi stubs**
- **Found during:** Task 2 (type stubs)
- **Issue:** `list[tuple[int, str, type[Any] | None]]` in stubs rejected `list[tuple[int, str, type[BaseModel] | None]]` due to list invariance
- **Fix:** Changed `list` to `Sequence` (covariant) for field_specs parameter in all stubs
- **Files modified:** src/arrowdantic/_core.pyi
- **Verification:** basedpyright passes clean
- **Committed in:** 4716343

**2. [Rule 1 - Bug] Fixed _get_nested_model parameter annotation**
- **Found during:** Task 2 (basedpyright errors)
- **Issue:** `type | None` annotation caused "unnecessary isinstance" error since generic aliases (e.g., `Optional[X]`) are not `type` instances
- **Fix:** Changed parameter annotation to `Any` to reflect runtime reality of Pydantic field annotations
- **Files modified:** src/arrowdantic/__init__.py
- **Verification:** basedpyright passes clean
- **Committed in:** 4716343

**3. [Rule 1 - Bug] Fixed union type narrowing for Table/RecordBatch dispatch**
- **Found during:** Task 2 (basedpyright errors)
- **Issue:** `hasattr(data, "to_batches")` doesn't narrow union types in basedpyright strict mode, causing reportAttributeAccessIssue and reportUnknownVariableType errors
- **Fix:** Added `typing.cast()` calls after hasattr checks to explicitly narrow types while preserving duck-typing runtime behavior
- **Files modified:** src/arrowdantic/__init__.py
- **Verification:** basedpyright passes clean, all tests pass
- **Committed in:** 4716343

**4. [Rule 3 - Blocking] Added executionEnvironments for tests/ pyarrow stub issues**
- **Found during:** Task 2 (basedpyright errors)
- **Issue:** Removing global suppressions exposed 647 errors in tests/ from incomplete pyarrow-stubs (third-party, not our code)
- **Fix:** Added pyright executionEnvironments config to relax 3 pyarrow-stub-caused rules specifically for tests/ directory
- **Files modified:** pyproject.toml
- **Verification:** basedpyright passes clean on entire project
- **Committed in:** 4716343

---

**Total deviations:** 4 auto-fixed (3 bugs, 1 blocking)
**Impact on plan:** All auto-fixes necessary for basedpyright strict mode compliance. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 05 is now complete with both plans (validated path + iterator API + type stubs)
- All requirements for v1.0 milestone are implemented
- Ready for milestone completion review

## Self-Check: PASSED

- All 5 files verified present on disk
- Both commit hashes (cf04f6d, 4716343) verified in git log
- No stubs/placeholders found in created/modified source files

---
*Phase: 05-validated-path-and-api-polish*
*Completed: 2026-03-22*
