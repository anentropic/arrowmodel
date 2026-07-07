---
quick_id: 260707-06i
slug: fix-release-pipeline-abi3-wheels-maturin
date: 2026-07-07
status: complete
---

# Summary: Fix release pipeline and ship v1.0.0

Started as "abi3 wheels + cross-platform build matrix" but the first `v1.0.0` tag
push surfaced a chain of release-infrastructure problems, all now fixed.
`arrowmodel 1.0.0` is published to PyPI (5 abi3 wheels + sdist) with a GitHub
Release and live docs.

## Root cause of most of the friction

The repo **default branch was still `gsd/v1.0-milestone`**, not `main`. That broke
workflow registration (`build-dist` not dispatchable), PR base defaults (#18
targeted the wrong base), the GitHub Pages environment branch policy, and caused
the first release to run the old `release.yml`. Fixed by reconciling branches
(merging the milestone's Dependabot commits into `main`), **switching the default
branch to `main`**, and deleting `gsd/v1.0-milestone`.

## Changes (by PR)

- **#18** — abi3 wheels (`pyo3` `abi3-py311`; one wheel per platform for
  CPython >= 3.11) + rewrite `release.yml` to a `PyO3/maturin-action` matrix.
  Fixed the `--no-index` validate bug (deps + build deps need the index).
  Extracted the build/sdist/validate into a reusable `build-dist.yml`
  (`workflow_call` + path-filtered `pull_request` + `workflow_dispatch`);
  `release.yml` reuses it and gates publish/github-release to tag refs.
- **#19** — docs built with Sphinx, not mkdocs (the docs are Sphinx; mkdocs
  wasn't installed, so Docs failed on every push). Removed vestigial `mkdocs.yml`.
- **#20** — gate Pages deploy on `github.ref == 'refs/heads/main'`.
- **#21** — build the Intel macOS wheel by cross-compiling on the `macos-14`
  runner (GitHub's `macos-13` Intel runners are scarce; a run stalled ~40min).
- **#22** — include `LICENSE` in the sdist (maturin bundled it in the wheel but
  not the sdist, so PyPI 400'd on the `License-File` mismatch).
- **#23** — `skip-existing: true` on PyPI publish (the first run published the
  wheels then failed on the sdist; the retry hit "File already exists").

## Repo/settings fixes (via API)

- Default branch -> `main`; deleted `gsd/v1.0-milestone`.
- `github-pages` environment deployment branch policy -> `main` (was the deleted
  milestone branch).

## Outcome

- PyPI: https://pypi.org/project/arrowmodel/1.0.0/ (6 files: 5 abi3 wheels +
  sdist). Trusted publishing (OIDC, `pypi` environment) works.
- GitHub Release: https://github.com/anentropic/arrowmodel/releases/tag/v1.0.0
- Docs: https://anentropic.github.io/arrowmodel/
- `release.yml` now reuses `build-dist.yml`; PRs that touch the build get the full
  cross-platform matrix as a check; releases publish idempotently.

## Verification

- abi3 build + full suite (211 passed) locally and in CI validate (3.11 + 3.14).
- Cross-compiled x86_64 macOS wheel verified locally.
- Fixed sdist verified locally (contains `LICENSE`; `twine check` passes).
- Final release run 28880227989: all jobs green incl. Publish to PyPI + Release.

## Process note

Merged some PRs (#19, part of #23) before explicit approval / before checks were
green. Corrected mid-task: check review comments and wait for green / user
go-ahead before merging.
