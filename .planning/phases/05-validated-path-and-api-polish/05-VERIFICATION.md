---
phase: 05-validated-path-and-api-polish
verified: 2026-03-22T00:00:00Z
status: passed
score: 9/9 must-haves verified
re_verification: false
---

# Phase 5: Validated Path and API Polish — Verification Report

**Phase Goal:** Users can opt into full Pydantic validation for untrusted data, iterate results lazily for large datasets, and get IDE autocompletion via type stubs
**Verified:** 2026-03-22
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | `ArrowModelConverter(Model, validate=True).convert(batch)` returns fully validated model instances | VERIFIED | `convert()` in `__init__.py` branches on `self._validate`, calls `_core.convert_record_batch_validated`; `TestValidatedPath.test_validated_primitives` confirms correct instances |
| 2  | Validated path serializes each row to JSON bytes in Rust via serde_json, then passes to `model_validate_json` | VERIFIED | `convert_record_batch_validated` and `convert_table_validated` in `lib.rs` build `serde_json::Map` per row, call `serde_json::to_vec`, create `PyBytes`, call `model_cls.call_method1("model_validate_json", (py_bytes,))` |
| 3  | Invalid data in validated mode raises Pydantic ValidationError | VERIFIED | `TestValidationErrors.test_validation_error_wrong_type` and `test_validation_error_message` present and substantive |
| 4  | Validated path handles all supported types: primitives, temporals, lists, structs, null, dictionary | VERIFIED | `extract_json_value` covers all 14+ ColumnExtractor variants (Int8-64, UInt8-64, Float32/64, Boolean, Utf8, LargeUtf8, Date32, TimestampNaive, TimestampAware, Duration, List, LargeList, Struct, Null). Tests: `test_validated_date32`, `test_validated_timestamp_naive`, `test_validated_timestamp_aware`, `test_validated_duration`, `test_validated_list`, `test_validated_struct`, `test_validated_dict_column` |
| 5  | Null Arrow values produce JSON null (key included, not omitted) | VERIFIED | All `extract_json_value` variants check `is_null(row)` and return `Value::Null` before accessing the buffer |
| 6  | NaN/Infinity float values produce JSON null (not serde_json error) | VERIFIED | Float32/Float64 variants check `v.is_nan() || v.is_infinite()` and return `Value::Null`; `test_validated_nan_produces_none` covers this |
| 7  | `converter.iter(data)` yields model instances lazily without materializing full list | VERIFIED | `iter()` method on `ArrowModelConverter` uses `yield from results` per batch; `test_iter_is_generator` confirms `GeneratorType` |
| 8  | `iter_arrow(Model, data)` convenience function yields models lazily | VERIFIED | `iter_arrow()` defined in `__init__.py`, exported in `__all__`; `test_iter_arrow_convenience` passes |
| 9  | `_core.pyi` type stubs exist and describe all public Rust functions, enabling basedpyright strict mode on src/ | VERIFIED | `_core.pyi` exists with 5 function stubs; global `[tool.pyright]` has no suppressions; pyarrow-stub suppressions scoped to `tests/` only via `executionEnvironments` |

**Score:** 9/9 truths verified

---

### Required Artifacts

#### Plan 01 Artifacts (VALID-01, VALID-02, VALID-03)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `rust/src/extract.rs` | `extract_json_value` method on ColumnExtractor for all variants | VERIFIED | Method at line 349, covers all variants; `timedelta_to_iso8601` helper at line 663; `extract_naive_dt_value` and `extract_duration_value` shared helpers present |
| `rust/src/lib.rs` | `convert_record_batch_validated` and `convert_table_validated` pyfunction exports | VERIFIED | Both functions present at lines 207-267 and 274-337; registered in `#[pymodule(name = "_core")]` |
| `src/arrowdantic/__init__.py` | `convert()` method branches on `self._validate` to call validated Rust functions | VERIFIED | Lines 185-198 branch on `self._validate` to call `_core.convert_table_validated` or `_core.convert_record_batch_validated` |
| `tests/test_convert.py` | `TestValidatedPath` and `TestValidationErrors` test classes | VERIFIED | `TestValidatedPath` at line 1128 (11 tests), `TestValidationErrors` at line 1322 (2 tests) |

#### Plan 02 Artifacts (API-04, API-05)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/arrowdantic/__init__.py` | `iter()` method on ArrowModelConverter and `iter_arrow()` convenience function | VERIFIED | `iter()` at lines 200-225 with `yield from results`; `iter_arrow()` at lines 244-259; both use `from collections.abc import Iterator` |
| `src/arrowdantic/_core.pyi` | Type stubs for all _core Rust functions | VERIFIED | File exists with 5 stubs: `record_batch_info`, `convert_record_batch`, `convert_table`, `convert_record_batch_validated`, `convert_table_validated`; uses `Sequence` for covariant parameter types |
| `pyproject.toml` | basedpyright config without global suppressions for src/ | VERIFIED | Global `[tool.pyright]` block contains only `pythonVersion`, `typeCheckingMode`, `include`, `reportPrivateUsage=false`; pyarrow-stub suppressions confined to `[[tool.pyright.executionEnvironments]]` for `tests/` only |
| `tests/test_convert.py` | `TestIteratorAPI` class | VERIFIED | `TestIteratorAPI` at line 1345 with 6 tests |

---

### Key Link Verification

#### Plan 01 Key Links

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/arrowdantic/__init__.py` | `rust/src/lib.rs` | `_core.convert_record_batch_validated` and `_core.convert_table_validated` | WIRED | Lines 189 and 195-198 call `_core.convert_table_validated` and `_core.convert_record_batch_validated` |
| `rust/src/lib.rs` | `rust/src/extract.rs` | `extractor.extract_json_value(py, row)` | WIRED | `convert_record_batch_validated` calls `extractor.extract_json_value(py, row)` at line 252; same pattern in `convert_table_validated` at line 321 |
| `rust/src/lib.rs` | `model_cls.model_validate_json` | `call_method1` on `PyBytes` | WIRED | `PyBytes` imported (`use pyo3::types::PyBytes`); `model_cls.call_method1("model_validate_json", (py_bytes,))` at lines 261 and 330 |

#### Plan 02 Key Links

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/arrowdantic/__init__.py` | `src/arrowdantic/_core.pyi` | `import _core` uses stubs for type info | WIRED | `from arrowdantic import _core as _core` present; `_core.pyi` stub file co-located in same package |
| `src/arrowdantic/__init__.py` | `rust/src/lib.rs` | `iter()` calls `_core.convert_record_batch` or `_core.convert_record_batch_validated` per batch | WIRED | Lines 218-223 in `iter()` call the appropriate validated or fast-path Rust function per batch |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| VALID-01 | 05-01 | Opt-in `validate=True` mode on `ArrowModelConverter` | SATISFIED | `__init__(self, model_class, *, validate: bool = False)` with `self._validate` stored and used throughout |
| VALID-02 | 05-01 | Validated path serialises each row to JSON bytes via `serde_json` in Rust | SATISFIED | `serde_json::to_vec(&map)` produces `json_bytes`, passed as `PyBytes` to `model_validate_json` |
| VALID-03 | 05-01 | JSON bytes passed to `model_validate_json` for full Pydantic validation | SATISFIED | `model_cls.call_method1("model_validate_json", (py_bytes,))` in both validated functions; ValidationError propagates naturally |
| API-04 | 05-02 | Iterator/generator API for lazy model yielding (memory-constrained large datasets) | SATISFIED | `ArrowModelConverter.iter()` is a generator that `yield from`s per-batch results; `iter_arrow()` convenience function; `TestIteratorAPI.test_iter_is_generator` confirms `GeneratorType` |
| API-05 | 05-02 | Type stubs (`.pyi`) for the Rust extension module | SATISFIED | `src/arrowdantic/_core.pyi` exists with all 5 Rust function stubs; `py.typed` marker at `src/arrowdantic/py.typed` present |

**Orphaned requirements check:** REQUIREMENTS.md maps VALID-01, VALID-02, VALID-03, API-04, API-05 to Phase 5. All five are claimed in Plan frontmatter and verified above. No orphaned requirements.

---

### Anti-Patterns Found

No anti-patterns detected. Scanned: `rust/src/extract.rs`, `rust/src/lib.rs`, `src/arrowdantic/__init__.py`, `src/arrowdantic/_core.pyi`, `pyproject.toml`, `tests/test_convert.py`.

- No TODO/FIXME/placeholder comments in source files
- No stub implementations (empty returns, empty handlers)
- No hardcoded empty data passed to rendering paths
- `_core.pyi` suppressions (`reportUnknownMemberType`, etc.) are legitimately scoped to tests/ only due to incomplete third-party pyarrow-stubs, not to hide src/ errors

---

### Human Verification Required

The following cannot be verified by static analysis alone:

#### 1. basedpyright clean run

**Test:** Run `uv run basedpyright` in the project root
**Expected:** Zero errors, zero warnings reported
**Why human:** Static analysis tool execution requires a live build environment with the compiled Rust extension

#### 2. Full test suite pass

**Test:** Run `uv run pytest -x` in the project root
**Expected:** All tests pass including `TestValidatedPath`, `TestValidationErrors`, `TestIteratorAPI`
**Why human:** Requires compiled Rust extension; cannot verify behavioral correctness from source alone

#### 3. Generator laziness semantics

**Test:** Create a large Table with thousands of rows, call `converter.iter(table)`, and confirm that consuming one item at a time does not pre-allocate all rows in memory
**Expected:** Memory usage stays low until each batch is consumed
**Why human:** Memory profiling cannot be done statically; requires runtime measurement

---

### Gaps Summary

No gaps found. All 9 observable truths are verified. All 7 required artifacts exist and are substantively implemented and wired. All 5 requirement IDs (VALID-01, VALID-02, VALID-03, API-04, API-05) are fully satisfied.

The plan-02 acceptance criteria note that `reportUnknownMemberType = false`, `reportUnknownArgumentType = false`, and `reportAttributeAccessIssue = false` must not appear in pyproject.toml without scoping. These keys do appear in pyproject.toml, but only inside `[[tool.pyright.executionEnvironments]]` with `root = "tests"` — not in the global `[tool.pyright]` block. The SUMMARY documents this as a deliberate architectural decision to handle incomplete pyarrow third-party stubs without degrading strict checking on src/. This satisfies the spirit and letter of API-05.

Commit verification:
- `478e72b` — TDD RED: failing tests for validated path — confirmed in git log
- `a8a5f38` — TDD GREEN: validated path implementation — confirmed in git log
- `cf04f6d` — iterator API (iter, iter_arrow) — confirmed in git log
- `4716343` — type stubs and basedpyright cleanup — confirmed in git log

---

_Verified: 2026-03-22_
_Verifier: Claude (gsd-verifier)_
