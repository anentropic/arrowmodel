# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0.0 — Core Library

**Shipped:** 2026-07-05
**Phases:** 7 | **Plans:** 16 | **Tasks:** 29

### What Was Built
- A Rust (PyO3/maturin) core converting Arrow `RecordBatch`/`Table` directly to Pydantic v2 instances, dict-free, via the Arrow C Data Interface (`pyo3-arrow`).
- Complete Arrow DataType coverage: primitives, temporals, Decimal(128/256/32/64), Float16, Binary/View types, List/LargeList/FixedSizeList, Struct (recursive nested models), Map, Dictionary, RunEndEncoded, and Union (sparse + dense).
- Dual conversion paths: fast (`model_construct`, no validation) and validated (`serde_json` → `model_validate_json`), plus a lazy iterator API and `_core.pyi` type stubs (basedpyright strict, no suppressions).
- Alias resolution (`validation_alias` > `alias` > `field_name`), schema mismatch errors, and a `from_arrow()` convenience function with `validate` parameter.
- ~1.7x faster than `to_pylist()` + `model_construct` at 100k rows.

### What Worked
- Spike-first sequencing (Phase 2) proved the performance hypothesis before committing to the full implementation.
- The `ColumnExtractor` enum pattern scaled cleanly from 13 primitive types to full Arrow coverage by adding variants, without reshaping the hot loop.
- Compiling schema cross-referencing once at converter init (Python-side introspection) kept the Rust hot loop free of per-row Pydantic logic.

### What Was Inefficient
- Type coverage was split across Phase 4 and a later Phase 6 ("Support All PyArrow Types") plus a Phase 7 tech-debt pass — a fuller type inventory up front might have folded these together.
- REE Table-input handling shipped with a bug that needed a gap-closure plan (06-03).
- Release hygiene lagged the code: the package rename (arrowdantic → arrowmodel) and a mkdocs→sphinx docs migration were left uncommitted/partial and had to be finished at milestone-close time (including two sphinx wiring gaps — napoleon, mermaid — that would have failed CI).

### Patterns Established
- Pre-unpacking encoded columns (Dictionary, RunEndEncoded) before the hot loop rather than decoding per row.
- Normalizing families of Arrow types to a single Python shape (e.g. all 3 interval variants → `(months, days, nanos)` tuple).
- Every new type must work on both the fast and validated paths — treated as one unit of work.

### Key Lessons
1. Keep release-hygiene tasks (naming, versioning, docs toolchain) close to the code that motivates them — deferring them lets them rot into half-finished working-tree state.
2. Verify generated/migrated artifacts under the same strictness as CI (`sphinx-build -W`) before considering them done; a clean local render is not the same as a clean strict build.
3. Enumerate the full type/coverage surface early when the domain is a closed set (the Arrow type system) — incremental discovery cost extra phases.

### Cost Observations
- Model mix: opus (planner + executor profile "quality").
- Notable: the milestone body (Phases 1–7) executed in short per-plan cycles (mostly 2–10 min each per the velocity log); the long tail was release prep, not feature work.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0.0 | 7 | 16 | Initial library; spike-first, enum-based type coverage |

### Cumulative Quality

| Milestone | Tests | Notable |
|-----------|-------|---------|
| v1.0.0 | 193 | Full Arrow type coverage on both conversion paths; strict docs build |

### Top Lessons (Verified Across Milestones)

1. (Established v1.0.0) Keep release hygiene close to the code that motivates it.
2. (Established v1.0.0) Verify migrated/generated artifacts under CI-strict settings before calling them done.
