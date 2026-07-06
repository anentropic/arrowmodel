---
quick_id: 260706-nlm
title: PR #16 review fixes + list[NestedModel] container support
date: 2026-07-06
status: complete
retroactive: true
---

## Origin

This task is captured **retroactively**. The work was not pre-planned — it emerged
from a code review of PR #16 (`gsd/v1.0-milestone` → `main`, which brings the
archived v1.0.0 milestone onto `main`). The review surfaced correctness/perf
findings, and follow-up discussion added one new public capability
(`list[NestedModel]`). It is recorded here to close the traceability gap: real
functionality shipped on the PR branch after the v1.0.0 milestone was marked
100% complete and archived (2026-07-05).

## Objective

1. Fix the correctness/perf findings from the PR #16 review.
2. Support nested Pydantic models inside container columns (`list[NestedModel]`
   and friends) — previously unsupported on both conversion paths.
3. Guard + document the `Map` → `list[tuple[K, V]]` representation.

## Scope (three commits on gsd/v1.0-milestone)

| Commit | Kind | Summary |
|--------|------|---------|
| `5ed2de2` | fix | tz-aware timestamp instant, cached `Decimal` class, negative sub-second duration sign, field-less subclass, bytes-contract docs |
| `810897b` | feat | `list[NestedModel]` across List/LargeList/FixedSizeList/Map, incl. nested/recursive |
| `2ec2198` | feat | `Map` dict-annotation guard + type-mapping / how-to docs |

## Out of scope (deliberately deferred)

- True `dict[str, Model]` output from `Map` columns (kept as `list[tuple[K, V]]`
  — lossless for non-string / duplicate keys). A dict-typed field over a Map now
  raises an actionable error instead.
- The schema-model bridge ecosystem research (existing pending todo; future
  milestone).

## Tasks

1. Apply the six review fixes; add regression tests (tz instant, fast/validated
   agreement, negative durations, `Base64Bytes` round-trip, field-less subclass).
2. Thread the leaf nested model through container extractors in Rust; recurse
   `_get_nested_model` through container annotations in Python.
3. Add the Map dict-annotation guard; document Map + `list[NestedModel]`.

## Verify

- `uv run pytest` → 210 passed (was 193 at milestone close)
- `ruff check` / `ruff format --check` clean; `basedpyright` clean (pre-commit)
- `sphinx-build -W` (strict) clean
- All 7 PR #16 review threads resolved
