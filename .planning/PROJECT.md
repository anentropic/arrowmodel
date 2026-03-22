# arrowdantic

## What This Is

A Python library with a Rust core (via PyO3/maturin) that converts Apache Arrow `RecordBatch` and `Table` objects directly into lists of Pydantic v2 model instances. It eliminates the intermediate Python dict representation that arises from `to_pylist()` + Pydantic construction, replacing a two-step materialisation with a single tight Rust loop over Arrow buffers accessed via the Arrow C Data Interface.

## Core Value

Dict-free, single-step conversion from Arrow buffers to Pydantic model instances — faster and with less allocation pressure than any Python-level approach.

## Requirements

### Validated

- ✓ Rust/PyO3 extension module built with maturin, importable as `arrowdantic._core` — Phase 1
- ✓ Arrow C Data Interface for zero-copy buffer handoff (via `pyo3-arrow`) — Phase 1
- ✓ `ArrowModelConverter` class that cross-references Arrow schema against Pydantic model fields at construction time — Phase 2
- ✓ Schema cross-referencing compiled once at converter init, not per batch — Phase 2
- ✓ Fast path (default): `model_construct` with no Pydantic validation, dict-free row construction — Phase 2
- ✓ Null handling via Arrow validity bitmap — check before extract, emit `None` for null values — Phase 2
- ✓ Primitive type coverage: Int8–64, UInt8–64, Float32/64, Boolean, Utf8/LargeUtf8 — Phase 2
- ✓ Benchmark: ~1.7x faster than to_pylist() + model_construct at 100k rows — Phase 2

### Active

- [ ] Full support for Pydantic v2 field aliases and `validation_alias` (resolution priority: validation_alias > alias > field_name)
- [ ] `populate_by_name` support — accept both alias and field name when enabled
- [ ] Validated path (`validate=True`): serde_json row serialisation → `validate_json` for full Pydantic validation
- [ ] Accept both pyarrow `RecordBatch` and `Table` as input (iterate batches internally for Table)
- [ ] Extended type coverage: Date32, Timestamp (naive + aware), Duration, List/LargeList, Struct (recursive nested models), Dictionary, Null
- [ ] `ValueError` at converter construction for: missing required fields, unresolvable types, ambiguous matches
- [ ] Extra Arrow columns silently ignored (no error for unmapped columns)
- [ ] Convenience `from_arrow(Model, batch)` one-shot function
- [ ] Pre-interned Python field name strings reused across rows (no per-row string allocation)
- [ ] Type stubs (`_core.pyi`) for the Rust extension

### Out of Scope

- Pydantic v1 support — v2 only, leverages v2-specific APIs (model_construct, validate_json, model_fields)
- Arrow writing (Pydantic → Arrow) — read-only for v1
- ORM or database layer integration — this is a data conversion library
- `AliasPath` and `AliasGenerator` support — complex alias resolution deferred, raise `NotImplementedError` if encountered
- `FixedSizeList` mapping — needs resolution heuristic (list vs tuple vs ndarray), deferred
- `strict=True` mode for extra columns — document silent-ignore behaviour, add strict flag later
- Polars-specific handling — Polars exports via C Data Interface so it works, but no Polars-specific code paths
- Replacing pyarrow or Polars for general Arrow work

## Context

- **Arrow C Data Interface** is the interop standard — two raw pointers (`ArrowArray*`, `ArrowSchema*`) passed across the FFI boundary. The `pyo3-arrow` crate wraps this for PyO3.
- **`model_construct`** bypasses pydantic-core validation entirely — correct for trusted Arrow pipelines. The validated path uses `serde_json` → `validate_json` to keep validation in Rust (pydantic-core's `jiter` + `SchemaValidator`).
- Arrow stores nulls as a separate validity bitmap, not sentinel values. The value buffer at null indices is undefined and must not be read.
- The conventional path (`to_pylist()` + Model construction) materialises the full dataset as Python dicts — significant allocation pressure for large batches that arrowdantic eliminates.
- Primary comparison target: `to_pylist()` + `model_construct()` in a Python loop (what a careful user writes today).

## Constraints

- **Tech stack**: Rust (PyO3) + Python, built with maturin. No C/C++ extensions.
- **Python version**: >=3.11 (per cookiecutter template)
- **Dependencies (Rust)**: pyo3, arrow-rs, pyo3-arrow, serde_json, chrono
- **Dependencies (Python)**: pydantic >= 2.0 (required), pyarrow (optional — for type stubs and testing)
- **Build system**: maturin with pyproject.toml integration

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use `pyo3-arrow` for C Data Interface | Ergonomic PyO3 wrapper, avoids manual FFI pointer handling | — Pending |
| Schema cross-reference in Python, hot loop in Rust | `model_fields` introspection is easy in Python; Rust loop avoids per-row Python overhead | — Pending |
| Validated path via serde_json → validate_json | Keeps both serialisation and validation in Rust (pydantic-core), avoids Python dict intermediate | — Pending |
| Silently ignore extra Arrow columns | Matches common data pipeline patterns; strict mode deferred | — Pending |
| Pre-intern Python field name strings | Eliminates per-row string allocation in the hot loop | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-22 after Phase 2 completion*
