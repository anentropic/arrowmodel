---
quick_id: 260705-ti7
title: Complete package rename arrowdantic → arrowmodel (remaining references and filenames)
date: 2026-07-05
status: complete
---

## What changed

Closed out the tail of the `arrowdantic` → `arrowmodel` rename. The bulk (package dir,
`pyproject.toml`, `rust/Cargo.toml`, README, imports) was already committed; this task removed
the last stragglers.

- `src/arrowmodel/_core.pyi` — stub module docstring `arrowdantic._core` → `arrowmodel._core`
- `benchmarks/bench_convert.py` — 4 code comments `# arrowdantic` → `arrowmodel`
- `tests/test_arrowdantic.py` → `tests/test_arrowmodel.py` (`git mv`; 0 content references)
- `_notes/arrowdantic-design.md` → `_notes/arrowmodel-design.md` (`git mv` + 6 internal
  name references updated)
- `.planning/PROJECT.md` — title `# arrowdantic` → `# arrowmodel` and two `arrowdantic._core`
  references (so progress reports show the correct project name)

## Verification

- `git ls-files | grep -i arrowdantic` (excluding `.planning/` history) → empty
- No `arrowdantic` filenames remain in tracked source
- `uv run pytest tests/test_arrowmodel.py` → 2 passed (renamed file discovered correctly)
- Remaining `arrowdantic` strings live only in `rust/target/` build artifacts (regenerated on
  next build) and historical `.planning/` phase logs

## Deliberately out of scope

The working tree still holds an unrelated **mkdocs → sphinx docs migration** (`README.md`
rewrite, `docs/`, `.doc-writer/`, `MAINTAINER.md`, `justfile`, `pyproject.toml` docs group,
`uv.lock`, an `__init__.py` docstring fix). None of it is rename-related, so it was left
uncommitted and untouched to keep this an atomic rename commit.
