---
quick_id: 260707-06i
slug: fix-release-pipeline-abi3-wheels-maturin
date: 2026-07-07
status: in-progress
---

# Quick Task: Fix release pipeline (abi3 wheels + cross-platform matrix)

The `v1.0.0` tag triggered `release.yml`, which failed: `uv build` on a single
Ubuntu runner produced only a version-specific `cp314` linux wheel, so the
`validate` job could not install it on Python 3.11. No PyPI publish happened
(that job was gated behind `validate`).

## Changes

1. **abi3 wheels** — add `abi3-py311` to the pyo3 feature set in
   `rust/Cargo.toml`. One stable-ABI wheel per platform now covers all
   CPython >= 3.11 (matches `requires-python`). Verified locally: builds a
   `cp311-abi3` wheel and all 211 tests pass under it (incl. datetime/tz, the
   abi3-sensitive paths).

2. **Cross-platform build matrix** — rewrite `release.yml` `build` job to use
   `PyO3/maturin-action` across:
   - manylinux x86_64 + aarch64
   - macOS x86_64 (macos-13) + arm64 (macos-14)
   - Windows x64
   plus a dedicated `sdist` job.

3. **Robust validate** — download all `dist-*` artifacts merged into `dist/`,
   install by name via `--find-links` (installer picks the compatible wheel),
   and test sdist install with `--no-binary`.

4. **Publish hardening** — gate `publish` and `github-release` on
   `startsWith(github.ref, 'refs/tags/')` so a `workflow_dispatch` run can
   build+validate the exact artifacts without ever touching PyPI.

## Verification

- Local abi3 build + full test suite (done: 211 passed).
- Push branch and run `release.yml` via `workflow_dispatch` — must reach green
  on build-wheels (all 5 legs) + sdist + validate (3.11 and 3.14), with publish
  skipped.
- Merge to main, then delete + re-push `v1.0.0` to run the real release.

## Commits

1. `build: build abi3 wheels + cross-platform release matrix`
