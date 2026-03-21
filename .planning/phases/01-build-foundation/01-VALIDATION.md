---
phase: 1
slug: build-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-21
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | BUILD-01 | smoke | `uv run python -c "import arrowdantic._core"` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | BUILD-02 | config | `grep 'maturin' pyproject.toml` | ✅ | ⬜ pending |
| 01-01-03 | 01 | 1 | BUILD-03 | config | `grep 'pyo3-arrow' rust/Cargo.toml` | ❌ W0 | ⬜ pending |
| 01-01-04 | 01 | 1 | INPUT-03 | integration | `uv run pytest tests/test_smoke.py -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `rust/Cargo.toml` — Rust crate with pyo3, arrow-rs, pyo3-arrow dependencies
- [ ] `rust/src/lib.rs` — Minimal PyO3 module with smoke test function
- [ ] `tests/test_smoke.py` — Import test + Arrow PyCapsule round-trip test

*Existing `tests/conftest.py` covers shared fixtures.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `maturin develop` succeeds | BUILD-01 | Build step, not runtime | Run `uv run maturin develop` and verify exit code 0 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
