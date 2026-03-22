---
phase: 4
slug: extended-types
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-22
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x with pytest-benchmark |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_convert.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_convert.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | TEMP-01, TEMP-02, TEMP-03, TEMP-04, TEMP-05 | unit | `uv run pytest tests/test_convert.py -k temporal -x -q` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | CPLX-04, CPLX-05 | unit | `uv run pytest tests/test_convert.py -k "dict or null_type" -x -q` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 2 | CPLX-01, CPLX-02 | unit | `uv run pytest tests/test_convert.py -k list -x -q` | ❌ W0 | ⬜ pending |
| 04-02-02 | 02 | 2 | CPLX-03 | unit | `uv run pytest tests/test_convert.py -k struct -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_convert.py` — add test stubs for temporal types, dictionary, null type, list, struct
- [ ] `tests/conftest.py` — add fixtures for temporal batches, list batches, struct batches, dictionary batches

*Existing test infrastructure covers the framework — Wave 0 only adds new test stubs and fixtures.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
