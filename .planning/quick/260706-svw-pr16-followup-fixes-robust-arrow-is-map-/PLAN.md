---
quick_id: 260706-svw
slug: pr16-followup-fixes-robust-arrow-is-map-
date: 2026-07-06
status: complete
---

# Quick Task: PR #16 follow-up review fixes

Address two fixable findings from the follow-up review of PR #16
(https://github.com/anentropic/arrowmodel/pull/16). Both are non-design,
non-breaking improvements to code added in commits `810897b` / `2ec2198`.

## Finding 1 — `_arrow_is_map` best-effort robustness (Python)

`src/arrowmodel/__init__.py`: `_arrow_is_map` only wraps `import pyarrow` in
`try/except`, not the `pa.types.is_map(arrow_type)` call. A non-pyarrow
`arrow_type` (polars/nanoarrow arriving via the Arrow C Data Interface) can make
`pa.types.is_map` raise instead of returning `False`. The guard is documented as
best-effort, so it must degrade to `False` on any failure.

**Fix:** wrap the `is_map` call so any exception returns `False`.

## Finding 2 — precompute nested-model tree for container-of-struct (Rust)

`rust/src/extract.rs`: for `list[Model]` / `map[Model]` (List/LargeList/
FixedSizeList/Map over a Struct child), `prepare_extractor` is called per row and,
when the child is a Struct, re-runs Python introspection every row
(`py.import("arrowmodel")`, `getattr("_get_nested_model")`, and per struct-field
`model_fields.get_item` + `getattr("annotation")` + a `_get_nested_model` call).
The model→field resolution is invariant per column; only the per-row sub-array
pointers change.

**Fix:** resolve the nested-model tree once per column into a Rust-side structure
and thread that through the container extractors, so the per-row child extractor
build does zero Python introspection. Preserve behaviour exactly (all existing
nested-model tests must still pass).

## Verification

- `maturin develop` builds cleanly; `cargo clippy` introduces no new warnings.
- Full pytest suite passes (currently 210).
- Add a Python-level regression test for `_arrow_is_map` returning `False` on a
  non-pyarrow type.
- Existing `TestListOfModel` tests (fast + validated) continue to pass, confirming
  the precompute refactor is behaviour-preserving.

## Atomic commits

1. `fix: make _arrow_is_map best-effort (return False on non-pyarrow type)`
2. `perf: precompute nested-model tree for container-of-struct extractors`
