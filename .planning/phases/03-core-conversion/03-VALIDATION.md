---
phase: 3
slug: core-conversion
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-22
---

# Phase 3 — Validation Strategy

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
| 03-01-01 | 01 | 1 | ALIAS-01, ALIAS-02, ALIAS-03 | unit | `uv run pytest tests/test_convert.py -k alias -x -q` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | SCHEMA-03, SCHEMA-04 | unit | `uv run pytest tests/test_convert.py -k schema -x -q` | ❌ W0 | ⬜ pending |
| 03-02-01 | 02 | 2 | INPUT-02 | unit | `uv run pytest tests/test_convert.py -k table -x -q` | ❌ W0 | ⬜ pending |
| 03-02-02 | 02 | 2 | API-03 | unit | `uv run pytest tests/test_convert.py -k from_arrow -x -q` | ❌ W0 | ⬜ pending |
| 03-02-03 | 02 | 2 | FAST-02 | unit | `uv run pytest tests/test_convert.py -k intern -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_convert.py` — add test classes/stubs for alias resolution, schema errors, Table input, from_arrow, string interning
- [ ] `tests/conftest.py` — add fixtures for aliased models, Table objects, models with optional fields

*Existing test infrastructure (pytest, conftest.py, test_convert.py) covers the framework — Wave 0 only adds new test stubs and fixtures.*

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
