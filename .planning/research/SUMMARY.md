# Project Research Summary

**Project:** arrowdantic
**Domain:** Rust/PyO3 Arrow-to-Pydantic data conversion library
**Researched:** 2026-03-21
**Confidence:** HIGH

## Executive Summary

Arrowdantic fills a genuine gap in the Python data ecosystem: no existing library converts Arrow columnar data (RecordBatch/Table) to Pydantic model instances via a compiled Rust hot loop. Today, users resort to `to_pylist()` + `model_construct()` -- two full materializations through Python that are ~20x slower than necessary. The competitive landscape (patito, pydantic-to-pyarrow, poldantic) addresses adjacent problems (Polars-specific validation, schema-only conversion) but none performs Arrow-buffer-to-model-instance conversion in compiled code. This is a clear, defensible niche.

The recommended architecture splits responsibility cleanly: Python handles Pydantic model introspection (alias resolution, schema cross-referencing) at converter initialization time, producing a flat `FieldMapping` list. Rust handles the hot loop -- zero-copy Arrow ingestion via `pyo3-arrow`'s PyCapsule interface, column-oriented value extraction from `arrow-rs` arrays, and direct model instance construction via `object.__setattr__` (mirroring Pydantic's own `model_construct` internals). The stack is well-constrained: `pyo3-arrow 0.17` pins `pyo3 0.28` + `arrow-rs 58`, and `maturin` replaces the current `uv_build` backend. All version choices are high-confidence, based on official releases and well-documented compatibility matrices.

The primary risks are correctness-related, not architectural. Arrow's validity bitmap must be checked before every value extraction (undefined data at null slots causes garbage values or panics). Pydantic's `model_construct` contract requires setting four internal attributes (`__dict__`, `__pydantic_fields_set__`, `__pydantic_extra__`, `__pydantic_private__`) -- missing any one breaks serialization downstream. Both `Utf8` and `LargeUtf8` variants must be handled from day one for Polars compatibility. These pitfalls are well-understood and preventable with disciplined implementation and targeted test coverage. The validated path (`serde_json` to `model_validate_json`) provides a safety net for untrusted data.

## Key Findings

### Recommended Stack

The version linchpin is **pyo3-arrow 0.17**, which requires pyo3 0.28 and arrow-rs 58. All Rust dependencies are pinned transitively through this constraint. The current `uv_build` backend must be replaced with **maturin** (the canonical PyO3 build tool), with `uv` cache-keys configured to invalidate on Rust source changes. Pydantic >= 2.11 is required for the modern `validate_by_name`/`validate_by_alias` config API.

**Core technologies:**
- **pyo3-arrow 0.17**: Arrow PyCapsule ingestion -- accepts data from any Arrow-compatible library (pyarrow, polars, nanoarrow) via zero-copy FFI
- **pyo3 0.28**: Rust-Python FFI bindings -- supports Python 3.11-3.14 including free-threaded 3.14t, MSRV Rust 1.83
- **arrow-rs 58** (sub-crates): Arrow in-memory format -- use individual crates (arrow-array, arrow-schema, etc.) to minimize compile times
- **maturin >= 1.12**: Build backend -- replaces uv_build, integrates with pyproject.toml and uv
- **serde_json 1**: JSON serialization for the validated path -- serialize rows to JSON bytes, pass to Pydantic's `model_validate_json`
- **pydantic >= 2.11**: Data model validation -- v2.11+ required for `validate_by_name` config

### Expected Features

**Must have (table stakes):**
- RecordBatch and Table to list of Pydantic model instances (the core use case)
- Full primitive type coverage (Int8-64, UInt8-64, Float16/32/64, Bool, Utf8/LargeUtf8)
- Null handling via Arrow validity bitmap (non-negotiable for correctness)
- Nested models via Arrow Struct type (recursive `model_construct`)
- List/LargeList support for array-valued columns
- Temporal types (Date32, Timestamp with naive/aware distinction, Duration)
- Schema cross-reference at converter init (amortize introspection across rows)
- Pydantic alias resolution (validation_alias > alias > field_name priority)
- `from_arrow()` one-liner convenience function
- Type stubs (.pyi) for the Rust extension
- Clear, actionable error messages on schema mismatch

**Should have (differentiators):**
- Dict-free construction via Rust (`object.__setattr__` directly, skipping Python dict intermediary)
- Pre-interned Python field name strings (eliminates per-row string allocation)
- Validated path via `serde_json` + `model_validate_json` (for untrusted data, `validate=True`)
- Arrow C Data Interface / PyCapsule support (source-agnostic: pyarrow, polars, nanoarrow)
- Dictionary-encoded column support (common in Parquet-loaded data)
- Iterator/generator API for memory-constrained large datasets

**Defer (v2+):**
- Arrow writing direction (Pydantic to Arrow) -- different problem, doubles scope
- `AliasPath`/`AliasGenerator` support -- Arrow columns are flat names, these are irrelevant
- `FixedSizeList` mapping -- ambiguous target type needs design decision
- Full DataFrame abstraction -- patito already covers this for Polars

### Architecture Approach

The architecture cleanly separates concerns by language advantage: Python handles Pydantic introspection (easy in Python, verbose in Rust) while Rust handles the hot loop over Arrow buffers (fast in Rust, slow in Python). The FFI boundary is crossed once per batch, not per row. Arrow data enters Rust via zero-copy PyCapsule (pyo3-arrow), columns are downcast to concrete types once before the row loop, and model instances are constructed using the same `object.__setattr__` pattern that Pydantic's own `model_construct` uses internally.

**Major components:**
1. **Python Wrapper** (`src/arrowdantic/`) -- Pydantic model_fields introspection, alias resolution, schema cross-referencing, public API (`from_arrow()`, `ArrowModelConverter`)
2. **Rust Core** (`arrowdantic._core`) -- Hot loop: Arrow ingestion via pyo3-arrow, column-oriented type extractors, row construction via `object.__setattr__`, validated path via serde_json
3. **Schema Mapper** (Python, at init) -- Cross-references Arrow schema with Pydantic model fields, resolves aliases, produces `FieldMapping[]` list that Rust consumes without any Python callbacks
4. **Type Extractors** (Rust) -- Match on Arrow `DataType`, downcast to concrete array types, extract values with validity bitmap checks, handle Utf8/LargeUtf8, List/LargeList, Struct, Dictionary

### Critical Pitfalls

1. **Reading undefined values at null Arrow slots** -- Arrow value buffers contain garbage at null indices. Every extractor must check `is_valid(i)` before `value(i)`. Encapsulate this in a shared helper to prevent omission when adding new types. Build this abstraction first.

2. **Incomplete model_construct replication** -- Directly setting `__dict__` without also setting `__pydantic_fields_set__`, `__pydantic_extra__`, and `__pydantic_private__` produces models that break on `model_dump()`. Phase 1 should call `model_construct` as a Python method; optimize to direct `__setattr__` only after writing round-trip serialization tests.

3. **Utf8/LargeUtf8 and List/LargeList type duplication** -- Polars uses `LargeUtf8` by default, pyarrow uses `Utf8`. Handling only one variant means "works with pyarrow, fails with Polars." Always match both variants together in the type dispatch.

4. **Timestamp timezone semantics** -- Arrow timestamps with `tz=None` must produce naive Python datetimes; timestamps with a timezone must produce aware datetimes. Nanosecond precision must be truncated to microseconds (Python's max) with documentation. Test with naive, UTC, and named timezone data.

5. **Struct null propagation** -- A null struct value means the entire nested model is `None`, but child arrays still contain undefined data at that index. Check the struct's own validity bitmap before descending into children. Also, `model_construct` does not recursively construct nested models -- nested instances must be built explicitly.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Build System and Rust Skeleton
**Rationale:** Everything depends on the maturin build system working. The current `uv_build` backend cannot compile Rust extensions. This is the foundation that unblocks all subsequent work.
**Delivers:** Working maturin + PyO3 build pipeline; Cargo.toml with correct dependency versions; pyproject.toml changes; a minimal `_core` module that can be imported from Python; CI configuration for Rust compilation.
**Addresses:** Build system setup, project structure from ARCHITECTURE.md
**Avoids:** Pitfall 6 (pyo3-arrow owned types -- get function signatures right from the start)

### Phase 2: Core Conversion (Fast Path)
**Rationale:** This is the library's reason to exist. Schema mapping, value extraction, and model construction form a tight dependency chain that must be built together.
**Delivers:** `ArrowModelConverter` class, `from_arrow()` convenience function, scalar type extraction (Int, UInt, Float, Bool, Utf8/LargeUtf8), null handling via validity bitmap, `model_construct`-based row construction, clear error messages on schema mismatch.
**Addresses:** Table stakes features: RecordBatch/Table conversion, primitive types, null handling, schema cross-reference, alias resolution, `from_arrow()`, type stubs
**Avoids:** Pitfall 1 (model_construct replication -- start with Python method call), Pitfall 2 (null slots -- build validity check abstraction first), Pitfall 4 (Utf8/LargeUtf8 -- handle both from day one)

### Phase 3: Extended Type Support
**Rationale:** With the core loop working for primitives, adding new types is incremental. Temporal types, lists, structs, and dictionary arrays each add value but share the same extraction pattern.
**Delivers:** Date32/Date64 to `datetime.date`, Timestamp (naive and aware) to `datetime.datetime`, Duration to `timedelta`, List/LargeList to Python list, Struct to nested Pydantic model instances, Dictionary-encoded column resolution.
**Addresses:** Type completeness features from FEATURES.md Phase 2
**Avoids:** Pitfall 5 (timestamp timezone -- implement naive/aware distinction correctly), Pitfall 7 (dictionary indirection -- handle double lookup), Pitfall 8 (struct null propagation -- check struct validity before descending)

### Phase 4: Validated Path and Performance
**Rationale:** The validated path (`validate=True`) is architecturally independent of the fast path and shares the schema mapping. Performance optimizations (direct `__setattr__`, pre-interned strings, GIL release) should only happen after correctness is proven.
**Delivers:** `validate=True` mode via serde_json + `model_validate_json`, direct `__dict__` construction bypassing `model_construct`, pre-interned field name strings, iterator/generator API for large datasets, benchmarks.
**Addresses:** Differentiator features: validated path, dict-free construction, iterator API, progress callback
**Avoids:** Pitfall 3 (GIL memory accumulation -- offer chunked iteration), serde_json/jiter compatibility issues (test against Pydantic's own `model_validate_json`)

### Phase Ordering Rationale

- **Build system first** because nothing compiles without maturin. This is a one-time setup that de-risks the entire project.
- **Core conversion before extended types** because the extraction pattern (downcast, validity check, extract, convert to PyObject) is established once with primitives and then replicated for each new type. Getting the abstraction right with simple types prevents rework.
- **Schema mapping and alias resolution in Phase 2** because they are prerequisites for the hot loop. The Rust core cannot function without knowing which Arrow columns map to which Pydantic fields.
- **Extended types before validated path** because type coverage directly determines library usefulness. A library that handles only int/string but has a validated path is less useful than one that handles all common types without validation.
- **Performance optimization last** because premature optimization (direct `__setattr__`, GIL release strategies) adds complexity and coupling to Pydantic internals. The safe `model_construct` call is correct and adequate for Phase 2-3.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (Core Conversion):** The `object.__setattr__` vs `model_construct` decision needs benchmarking to determine if the Python method call is adequate or if direct attribute setting is needed from the start. The alias resolution logic needs testing against edge cases (models with both `alias` and `validation_alias`, `populate_by_name` enabled).
- **Phase 3 (Extended Types):** Timestamp timezone handling has subtleties (zoneinfo vs pytz, nanosecond truncation policy). Struct recursion needs careful design for the null propagation and nested model construction ordering.
- **Phase 4 (Validated Path):** serde_json and Pydantic's jiter parser have different float handling (`inf`/`NaN` support differs). Needs verification.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Build System):** Maturin + PyO3 setup is thoroughly documented. The exact pyproject.toml and Cargo.toml configurations are specified in STACK.md.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified against official releases. pyo3-arrow 0.17 compatibility matrix confirmed from Cargo.toml. Maturin and uv integration documented. |
| Features | HIGH | Competitive landscape surveyed thoroughly. No existing library fills this niche. Feature prioritization grounded in real user pain points (to_pylist overhead, PyCapsule adoption). |
| Architecture | HIGH | Pattern validated against arro3 reference implementation and Pydantic source code. model_construct internals confirmed from pydantic source. pyo3-arrow API confirmed from docs.rs. |
| Pitfalls | HIGH | All critical pitfalls verified against official documentation (PyO3 user guide, Pydantic API docs, arrow-rs source, Arrow spec). Recovery strategies are concrete and tested. |

**Overall confidence:** HIGH

### Gaps to Address

- **model_post_init handling:** If a Pydantic model defines `model_post_init`, arrowdantic must detect and call it after construction. The exact detection mechanism (`hasattr(cls, '__pydantic_post_init__')`) needs verification during Phase 2 implementation.
- **Utf8View/BinaryView types:** Arrow-rs 52+ introduced these new types. They are increasingly common but not yet covered in the type extraction plan. Should be assessed during Phase 3 and added if encountered in real data.
- **Free-threaded Python (3.14t):** PyO3 0.28 supports it, but GIL release strategies and memory management may behave differently. Needs testing if targeting 3.14t.
- **Performance baseline:** No benchmarks exist yet for the `model_construct` Python call overhead vs direct `__setattr__`. Phase 2 should establish this baseline before committing to optimization in Phase 4.
- **Pydantic v3 compatibility:** Pydantic v3 is on the horizon. The `populate_by_name` config is pending deprecation. The v2.11+ floor future-proofs alias handling but v3 may change `model_construct` internals.

## Sources

### Primary (HIGH confidence)
- [pyo3-arrow docs](https://docs.rs/pyo3-arrow/latest/pyo3_arrow/) -- PyRecordBatch API, PyCapsule interface, version compatibility
- [pyo3-arrow Cargo.toml](https://github.com/kylebarron/arro3/blob/main/pyo3-arrow/Cargo.toml) -- version pinning: pyo3 0.28, arrow 58
- [PyO3 releases](https://github.com/pyo3/pyo3/releases) -- v0.28.2 latest, Python 3.14/3.14t support
- [arrow-rs releases](https://github.com/apache/arrow-rs/releases) -- v58.0.0, Feb 2026
- [Pydantic BaseModel API](https://docs.pydantic.dev/latest/api/base_model/) -- model_construct, model_validate_json contracts
- [Pydantic alias docs](https://docs.pydantic.dev/latest/concepts/alias/) -- validation_alias > alias > field_name priority
- [Pydantic v2.11 release](https://pydantic.dev/articles/pydantic-v2-11-release) -- validate_by_name/validate_by_alias config
- [Pydantic model_construct source](https://github.com/pydantic/pydantic/blob/main/pydantic/main.py) -- confirms object.__setattr__ internals
- [Maturin project layout](https://www.maturin.rs/project_layout.html) -- mixed Rust/Python layout, module-name config
- [Arrow PyCapsule Interface](https://arrow.apache.org/docs/format/CDataInterface/PyCapsuleInterface.html) -- cross-library Arrow interop standard

### Secondary (MEDIUM confidence)
- [arro3 repository](https://github.com/kylebarron/arro3) -- reference architecture for pyo3-arrow usage patterns
- [maturin + uv integration](https://github.com/PyO3/maturin/issues/2314) -- cache-keys configuration
- [maturin import hook](https://github.com/PyO3/maturin-import-hook) -- dev workflow optimization
- [pyo3-arrow vs arrow-pyarrow](https://docs.rs/pyo3-arrow/latest/pyo3_arrow/) -- synthesized comparison from multiple sources
- [PyO3 Discussion #2321](https://github.com/PyO3/pyo3/discussions/2321) -- bypassing custom __setattr__ from Rust
- [pydantic-core Issue #1364](https://github.com/pydantic/pydantic-core/issues/1364) -- no native Rust Pydantic construction API

### Tertiary (LOW confidence)
- [PyArrow to_pylist() performance (Arrow #28694)](https://github.com/apache/arrow/issues/28694) -- 20x slowdown claim (single issue, but well-documented root cause)
- [PyO3 Memory Leak Issue #2853](https://github.com/PyO3/pyo3/issues/2853) -- memory patterns in object creation loops (may be resolved in 0.28)

---
*Research completed: 2026-03-21*
*Ready for roadmap: yes*
