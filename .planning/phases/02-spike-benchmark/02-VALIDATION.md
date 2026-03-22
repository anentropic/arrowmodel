---
phase: 2
slug: spike-benchmark
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-22
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-benchmark 5.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/test_converter.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -v --ignore=benchmarks/` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_converter.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v --ignore=benchmarks/`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | SCHEMA-01, SCHEMA-02, TYPE-01–05, NULL-01–03, FAST-01, FAST-03 | unit | `uv run pytest tests/test_converter.py -x -q` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | API-01, API-02, INPUT-01 | integration | `uv run pytest tests/test_converter.py -x -q` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 2 | FAST-01, FAST-03 | benchmark | `uv run pytest benchmarks/bench_convert.py --benchmark-only` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_converter.py` — tests for ArrowModelConverter with all primitive types and nulls
- [ ] `benchmarks/bench_convert.py` — benchmark comparing arrowdantic vs to_pylist() + model_construct

*Existing `tests/conftest.py` covers shared fixtures.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
