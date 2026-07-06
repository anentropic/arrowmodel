---
quick_id: 260706-nlm
title: PR #16 review fixes + list[NestedModel] container support
date: 2026-07-06
status: complete
retroactive: true
commits: [5ed2de2, 810897b, 2ec2198]
---

## What changed

Post-milestone hardening and one new public capability, all on `gsd/v1.0-milestone`
(PR #16). Captured retroactively — see PLAN.md for origin.

### `5ed2de2` — PR #16 review fixes

- **tz-aware timestamp instant (correctness, was silently wrong).**
  `extract_aware_datetime` attached the target `ZoneInfo` to the UTC wall-clock,
  shifting the absolute instant by the zone offset. Now builds the UTC instant
  (`dt.and_utc()`) and `astimezone(tz)`. Fast and validated paths now agree on
  the instant. `rust/src/extract.rs`.
- **Per-row `decimal` import (perf).** The four Decimal variants imported the
  `decimal` module and looked up `Decimal` every row; now cached in the extractor
  variant at `prepare_extractor` time (mirrors the ZoneInfo pattern).
- **Negative sub-second duration sign.** `timedelta_to_iso8601` derived the sign
  from `num_seconds()` (truncates to 0 for |Δ|<1s); now derives it from the whole
  `TimeDelta` and formats the absolute magnitude.
- **Field-less `ArrowModel` subclass.** `__pydantic_init_subclass__` now always
  creates `_arrow_converter`, so a no-field subclass returns results instead of
  raising `AttributeError`. `src/arrowmodel/__init__.py`.
- **bytes validated-path contract** documented (base64 requires `Base64Bytes` /
  `val_json_bytes="base64"`), with a round-trip test.

### `810897b` — list[NestedModel] container support

Previously `list[NestedModel]` (Arrow `List(Struct)`) failed on **both** paths:
the nested-model class was only threaded through `Struct` children, never through
container children, so the per-row Struct extractor was built with no model.

- `_get_nested_model` now walks the annotation's type args and returns the leaf
  `BaseModel` (`list[Model]`, `list[list[Model]]`, `dict[str, Model]` → `Model`).
- `List` / `LargeList` / `FixedSizeList` / `Map` extractors carry that model and
  thread it into their per-row child extractor; consumed only when a child is a
  `Struct`, so it propagates safely through nested containers.
- The Struct "no matching model" error now names the struct fields and the
  accepted annotations.

Supported on both paths: `list[Model]`, `list[list[Model]]`, `large_list[Model]`,
`fixed_size_list[Model]`, and struct fields containing `list[Model]`.

### `2ec2198` — Map dict-guard + docs

- A `dict`/`Mapping`-typed field over a `Map` column now raises an actionable
  `TypeError` at `convert()` time (Map is materialised as `list[tuple[K, V]]` —
  lossless for non-string / duplicate keys). Best-effort: skipped if pyarrow is
  not importable.
- Documented the Map contract and `list[NestedModel]` support in
  `docs/explanation/type-mappings.rst` and `docs/how-to/convert-nested-models.rst`.

## Verification

- `uv run pytest` → **210 passed** (193 at milestone close; +17)
- `ruff check` / `ruff format --check` clean; `basedpyright` clean (pre-commit gate)
- `sphinx-build -W` (strict) clean
- All 7 PR #16 review threads resolved

## Notes for the milestone record

`list[NestedModel]` is a genuine new public capability that landed after v1.0.0
was archived. It ships in the same v1.0.0 line via PR #16 (not yet merged/tagged
at time of capture). No new requirement ID was assigned; if a formal trace is
wanted, add a CPLX-* entry for "nested models inside containers" when the next
milestone opens.
