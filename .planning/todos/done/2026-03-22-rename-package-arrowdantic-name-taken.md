---
created: 2026-03-22T22:31:57.066Z
title: Rename package - arrowdantic name taken
area: general
files:
  - pyproject.toml
  - rust/Cargo.toml
  - src/arrowdantic/__init__.py
  - src/arrowdantic/_core.pyi
  - README.md
---

## Problem

The name "arrowdantic" is already taken on PyPI (or another package registry). The package needs to be renamed before publishing. This affects the Python package name, Rust crate name, module import paths, documentation, and all references throughout the codebase.

## Solution

1. Choose a new name (check availability on PyPI first)
2. Rename across all files:
   - `pyproject.toml` (project name, module-name)
   - `rust/Cargo.toml` (crate name, lib name)
   - `src/arrowdantic/` directory → `src/{newname}/`
   - All `import arrowdantic` references in tests, benchmarks, docs
   - `_core.pyi` module path
   - README.md, CLAUDE.md, and any documentation
3. Verify `maturin develop` and `uv run pytest` still pass after rename
