---
phase: 5
slug: validated-path-and-api-polish
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-22
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8.0 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_convert.py -x` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_convert.py -x`
- **After every plan wave:** Run `uv run pytest && uv run basedpyright`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | VALID-01, VALID-02 | unit | `uv run pytest tests/test_convert.py -k "TestValidatedPath" -x` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | VALID-03 | unit | `uv run pytest tests/test_convert.py -k "test_validation_error" -x` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 1 | API-04 | unit | `uv run pytest tests/test_convert.py -k "TestIteratorAPI" -x` | ❌ W0 | ⬜ pending |
| 05-03-01 | 03 | 2 | API-05 | smoke | `uv run basedpyright` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_convert.py` — add `TestValidatedPath` class with tests for VALID-01, VALID-02, VALID-03
- [ ] `tests/test_convert.py` — add `TestIteratorAPI` class for API-04
- [ ] Verify `uv run basedpyright` passes after stub addition and suppression removal — covers API-05

*Existing pytest infrastructure covers framework setup.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| IDE autocompletion works | API-05 | Requires visual IDE check | Open `__init__.py` in VS Code, verify `_core.` triggers autocomplete for all public functions |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
