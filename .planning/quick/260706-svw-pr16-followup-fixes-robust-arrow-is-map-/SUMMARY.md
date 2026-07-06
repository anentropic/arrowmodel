---
quick_id: 260706-svw
slug: pr16-followup-fixes-robust-arrow-is-map-
date: 2026-07-06
status: complete
commits:
  - 9dccb12
  - 89b8aed
---

# Summary: PR #16 follow-up review fixes

Addressed the two fixable findings raised in the follow-up review of PR #16
(posted as inline review comments at
https://github.com/anentropic/arrowmodel/pull/16#pullrequestreview-4639225725).
Both were non-design, behaviour-preserving improvements to code added in
`810897b` / `2ec2198`.

## Finding 1 — `_arrow_is_map` best-effort robustness (`9dccb12`)

`src/arrowmodel/__init__.py`: the Map-column guard only wrapped `import pyarrow`
in `try/except`, so a non-pyarrow `arrow_type` (polars/nanoarrow via the Arrow C
Data Interface) could make `pa.types.is_map` raise instead of returning `False`.
Moved the `is_map` call inside the `try` and broadened to `except Exception`, so
any failure degrades to `False` as documented.

- Test: `test_arrow_is_map_best_effort_on_non_pyarrow_type` (asserts `False` for
  `object()` / `str` / `None`, `True` for a real `pa.map_`).

## Finding 2 — precompute nested-model tree (`89b8aed`)

`rust/src/extract.rs`: for `list[Model]` / `map[Model]`, `prepare_extractor` was
called per row and re-ran Python introspection (`py.import("arrowmodel")` +
`_get_nested_model` per struct field) every row.

Introduced a `ModelPlan` tree, built once per column by `build_model_plan` (the
sole place that touches Python), mirroring the Arrow type tree and pre-resolving
each Struct's model class plus per-field child plans. `prepare_extractor` is now a
thin wrapper that builds the plan and delegates to a private
`prepare_extractor_with_plan`; recursive Struct children and per-row container
children read from the plan and never re-enter Python. Container extractor
variants carry their owned child `ModelPlan`(s) (Map carries separate key/value
plans); cloning a plan is refcount-only.

Behaviour-preserving: the "Struct column has no matching Pydantic model" error is
now raised at plan-build time (still within `convert()`), same message; covered
by the existing `test_struct_without_model_raises_actionable_error` and the
parametrized (fast + validated) `TestListOfModel` suite.

## Verification

- `cargo build` / `cargo clippy` clean — no new warnings (the two pre-existing
  `usize -> usize` cast warnings in the Union arm are untouched).
- `maturin develop` rebuild succeeds.
- Full suite: **211 passed** (210 baseline + 1 new `_arrow_is_map` test).

## Not addressed (deliberate, from the review)

Two Low findings remain documented rather than reconciled — they are design
decisions, not defects: plain `bytes` fields differ between fast/validated paths
(validated needs `Base64Bytes`), and the validated tz path displays the UTC zone
label while agreeing on the instant. Left as-is.
