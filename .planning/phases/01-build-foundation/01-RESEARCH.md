# Phase 1: Build Foundation - Research

**Researched:** 2026-03-21
**Domain:** Rust/Python build pipeline (maturin + PyO3 + pyo3-arrow)
**Confidence:** HIGH

## Summary

Phase 1 establishes the maturin build pipeline that compiles a Rust extension module importable as `arrowdantic._core`. The project currently has a pure-Python cookiecutter scaffold using `uv_build` as build backend, which must be replaced with `maturin`. The key version constraint is pyo3-arrow 0.17, which pins pyo3 to 0.28 and arrow-rs to 58.

The project uses a `src/arrowdantic/` Python layout. Maturin auto-detects a `rust/` directory layout where Cargo.toml and Rust source live under `rust/`, keeping Python (`src/`) and Rust (`rust/`) cleanly separated. This avoids the conflict of having both `src/lib.rs` (Rust) and `src/arrowdantic/` (Python) under the same `src/` directory.

**Primary recommendation:** Use the auto-detected `rust/` layout with `rust/Cargo.toml` and `rust/src/lib.rs`. Configure `python-source = "src"` and `module-name = "arrowdantic._core"` in `[tool.maturin]`. Verify the build with `maturin develop --uv` followed by `python -c "from arrowdantic import _core"`.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BUILD-01 | Rust/PyO3 extension module built with maturin, importable as `arrowdantic._core` | Covered by maturin config, Cargo.toml template, `#[pymodule]` macro with `#[pyo3(name = "_core")]`, project layout pattern |
| BUILD-02 | `pyproject.toml` configured for maturin with `uv` integration | Covered by pyproject.toml changes section -- build-system, tool.maturin, tool.uv cache-keys |
| BUILD-03 | `Cargo.toml` with pyo3, arrow-rs, pyo3-arrow, serde_json, chrono dependencies | Covered by Cargo.toml template with exact versions pinned to pyo3-arrow 0.17 compatibility matrix |
| INPUT-03 | Arrow C Data Interface via pyo3-arrow for zero-copy buffer handoff | Covered by pyo3-arrow API patterns -- PyRecordBatch as function parameter auto-converts via PyCapsule |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| maturin | >=1.12,<2.0 | Build backend for Rust/Python | Canonical build tool for PyO3 crates. v1.12.6 latest stable. |
| pyo3 | 0.28 | Rust-Python FFI | Latest stable (0.28.2). Required by pyo3-arrow 0.17. MSRV Rust 1.83. |
| pyo3-arrow | 0.17 | Arrow C Data Interface for PyO3 | Provides PyRecordBatch/PyTable with PyCapsule support. Pins pyo3 0.28 + arrow 58. |
| arrow-array | 58 | Arrow array types | Required by pyo3-arrow 0.17. Use sub-crate, not umbrella. |
| arrow-schema | 58 | Arrow schema types | Schema inspection for column name/type mapping. |
| serde | 1 | Serialization framework | Required by serde_json. Features: `derive`. |
| serde_json | 1 | JSON serialization | For validated path (Phase 5). Include now to avoid adding later. |
| chrono | 0.4 | Date/time types | Arrow temporal types convert to chrono. pyo3 `chrono` feature enables Python datetime conversion. |
| thiserror | 2 | Error derivation | Ergonomic error types. Use v2 (current major). |

### Supporting (Phase 1 only)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| arrow-data | 58 | Arrow data structures | Only if needed for buffer inspection |
| arrow-buffer | 58 | Arrow buffer types | Only if needed for direct buffer access |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pyo3-arrow | arrow-pyarrow (Apache) | arrow-pyarrow only accepts pyarrow, not polars/nanoarrow. Narrower scope. |
| maturin | setuptools-rust | setuptools-rust is legacy. No advantages for new projects. |
| Individual arrow-* sub-crates | Umbrella `arrow` crate | Umbrella pulls all sub-crates, slower compile. Use individual crates. |

**Installation (Python-side):**
```bash
# Build backend change is in pyproject.toml, not pip install
# Dev dependencies
uv add --dev pyarrow pytest-benchmark maturin-import-hook
```

**Version verification:** Versions verified against pyo3-arrow 0.17 Cargo.toml which declares `pyo3 = "0.28"` and `arrow-array = { version = "58" }`. All other Rust crate versions are stable semver ranges from crates.io.

## Architecture Patterns

### Recommended Project Structure

```
arrowdantic/
├── pyproject.toml              # Build config (maturin backend)
├── rust/                       # Rust source (auto-detected by maturin)
│   ├── Cargo.toml              # Rust dependencies
│   └── src/
│       └── lib.rs              # PyO3 module definition
├── src/
│   └── arrowdantic/
│       ├── __init__.py          # Public API
│       ├── _core.pyi           # Type stubs for Rust module (Phase 5)
│       └── py.typed            # PEP 561 marker (exists)
├── tests/
│   ├── conftest.py
│   └── test_build.py           # Build verification tests
└── .gitignore                  # Already has target/, *.so
```

**Why `rust/` layout (not root Cargo.toml):** The project uses `src/arrowdantic/` for Python (src-layout). Maturin cannot have both `src/lib.rs` (Rust) and `src/arrowdantic/` (Python) under the same `src/` directory -- the Rust `src/` conflicts with the Python `src/`. The `rust/` layout is auto-detected by maturin and avoids this conflict entirely.

### Pattern 1: Declarative PyO3 Module

**What:** Use PyO3 0.28's declarative `#[pymodule]` syntax for the extension module.
**When to use:** Always for new PyO3 0.28 projects. Replaces the older function-based init pattern.
**Example:**

```rust
// rust/src/lib.rs
// Source: https://pyo3.rs/v0.28.0/module

use pyo3::prelude::*;
use pyo3_arrow::PyRecordBatch;

#[pymodule(name = "_core")]
mod _core {
    use super::*;

    /// Accept a RecordBatch via Arrow C Data Interface and return row count.
    /// This is the Phase 1 smoke test -- proves pyo3-arrow works.
    #[pyfunction]
    fn record_batch_info(batch: PyRecordBatch) -> PyResult<(usize, usize)> {
        let rb = batch.into_inner();
        Ok((rb.num_rows(), rb.num_columns()))
    }
}
```

### Pattern 2: pyo3-arrow PyCapsule Input

**What:** Use `PyRecordBatch` as a function parameter type. PyO3 + pyo3-arrow auto-convert any PyCapsule-compatible object (pyarrow.RecordBatch, polars DataFrame chunk, nanoarrow array) via the Arrow C Data Interface.
**When to use:** Any function that receives Arrow data from Python.
**Example:**

```rust
// Source: https://docs.rs/pyo3-arrow/0.17.0/pyo3_arrow/struct.PyRecordBatch.html

use pyo3_arrow::PyRecordBatch;

#[pyfunction]
fn process(batch: PyRecordBatch) -> PyResult<()> {
    // batch.into_inner() -> arrow::record_batch::RecordBatch
    // batch.as_ref()     -> &RecordBatch (borrow without consuming)
    let rb = batch.into_inner();
    let schema = rb.schema();
    for field in schema.fields() {
        println!("{}: {:?}", field.name(), field.data_type());
    }
    Ok(())
}
```

**Critical:** Use owned `PyRecordBatch`, NOT `&PyRecordBatch`. pyo3-arrow requires owned parameters for PyCapsule extraction.

### Pattern 3: Cargo.toml for Maturin

**What:** The Cargo.toml must use `crate-type = ["cdylib"]` and the crate name should be the module name.
**Example:**

```toml
# rust/Cargo.toml

[package]
name = "arrowdantic-core"
version = "0.1.0"
edition = "2021"
rust-version = "1.83"

[lib]
name = "_core"
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "0.28", features = ["extension-module"] }
pyo3-arrow = "0.17"
arrow-array = "58"
arrow-schema = "58"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
chrono = "0.4"
thiserror = "2"
```

**Notes:**
- `lib.name = "_core"` must match the Python module name (`arrowdantic._core`)
- `crate-type = ["cdylib"]` produces a shared library loadable by Python
- `extension-module` feature prevents linking against libpython
- Do NOT add the `chrono` feature to pyo3 yet -- it is only needed in Phase 4 (temporal types). Adding it now increases compile time with no benefit.
- Individual arrow sub-crates (`arrow-array`, `arrow-schema`) instead of umbrella `arrow` crate to minimize compile time
- `arrow-data`, `arrow-buffer`, `arrow-cast`, `arrow-select` should be added only when needed (Phase 2+)

### Anti-Patterns to Avoid

- **Cargo.toml at project root with src-layout Python:** Maturin cannot distinguish `src/lib.rs` (Rust) from `src/arrowdantic/` (Python). Use `rust/` directory layout instead.
- **Using `&PyRecordBatch` reference parameters:** pyo3-arrow requires owned types for PyCapsule extraction. Always use `PyRecordBatch` (owned).
- **Pinning arrow-rs independently of pyo3-arrow:** Let pyo3-arrow's Cargo.toml drive the arrow version. Pinning separately causes version conflicts.
- **Using the umbrella `arrow` crate:** Pulls in all sub-crates including parquet I/O, CSV, JSON readers, etc. Use only the sub-crates you need.
- **Old-style `#[pymodule] fn init(m: ...)` syntax:** PyO3 0.28 supports declarative modules. Use `#[pymodule] mod _core { }` for cleaner code.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Arrow C Data Interface | Manual PyCapsule parsing | pyo3-arrow `PyRecordBatch` | PyCapsule protocol has safety invariants, memory ownership rules, schema negotiation |
| Rust/Python build pipeline | Custom build.rs + setuptools | maturin | Handles wheel naming, platform tags, abi3, Python version matrix |
| Error type boilerplate | Manual `impl From<X> for PyErr` | thiserror + `#[derive(Error)]` | thiserror 2 generates Display + Error impls, easy conversion to PyErr |
| Cache invalidation for Rust builds | Manual file watching | uv `cache-keys` config | uv watches Cargo.toml + *.rs files, rebuilds when changed |

**Key insight:** The build pipeline is the most fragile part of a mixed Rust/Python project. Maturin + uv cache-keys eliminates the "stale build" class of bugs entirely.

## Common Pitfalls

### Pitfall 1: Stale Extension Module After Rust Changes

**What goes wrong:** `uv run pytest` uses a cached wheel built from old Rust source. Tests pass/fail on stale code.
**Why it happens:** uv caches build artifacts and only rebuilds when pyproject.toml changes, not when .rs files change.
**How to avoid:** Add `cache-keys = [{ file = "pyproject.toml" }, { file = "Cargo.toml" }, { file = "**/*.rs" }]` to `[tool.uv]`. This tells uv to invalidate its cache when any Rust source file changes.
**Warning signs:** Tests pass when they should fail, or `maturin develop` fixes a "bug" that `uv run` doesn't see.

### Pitfall 2: ImportError Due to Module Name Mismatch

**What goes wrong:** `from arrowdantic import _core` raises ImportError even though build succeeded.
**Why it happens:** The compiled `.so` filename must match the Python import path. Three names must agree: (1) `lib.name` in Cargo.toml, (2) `module-name` in `[tool.maturin]`, (3) `#[pymodule(name = "...")]` in lib.rs.
**How to avoid:** Set all three to `_core` / `arrowdantic._core`:
  - Cargo.toml: `[lib] name = "_core"`
  - pyproject.toml: `module-name = "arrowdantic._core"`
  - lib.rs: `#[pymodule(name = "_core")]`
**Warning signs:** Build succeeds but import fails. Check the `.so` file name in the installed package.

### Pitfall 3: Missing `extension-module` Feature on pyo3

**What goes wrong:** Build fails on Linux/macOS with undefined symbol errors, or the module loads but crashes.
**Why it happens:** Without `extension-module`, pyo3 tries to link against libpython, which is not available at build time for extension modules.
**How to avoid:** Always include `features = ["pyo3/extension-module"]` in `[tool.maturin]`. This is the maturin-standard way to enable it project-wide.
**Warning signs:** Linker errors mentioning `_PyObject` or `_Py_Initialize`.

### Pitfall 4: Version Conflict Between pyo3 and arrow-rs

**What goes wrong:** Cargo fails to resolve dependencies with conflicting version requirements.
**Why it happens:** pyo3-arrow 0.17 requires exact pyo3 ^0.28 and arrow ^58. If you pin different versions of pyo3 or arrow sub-crates, Cargo cannot unify them.
**How to avoid:** Let pyo3-arrow drive versions. Use `pyo3 = "0.28"` and `arrow-array = "58"` (matching pyo3-arrow's requirements). Do not pin patch versions.
**Warning signs:** `cargo check` errors about incompatible versions of `pyo3` or `arrow-*`.

### Pitfall 5: Pre-commit Hooks Fail on Rust Files

**What goes wrong:** Pre-commit hooks (ruff, basedpyright) try to process Rust files or fail because the project structure changed.
**Why it happens:** The existing pre-commit config was designed for pure Python. The `uv-lock` hook may fail if `uv.lock` needs regeneration after build-backend change. basedpyright may not find the `_core` module.
**How to avoid:** After changing pyproject.toml, run `uv lock` to regenerate uv.lock before committing. basedpyright will need a `.pyi` stub for `_core` (Phase 5) or temporary `# type: ignore` annotations.
**Warning signs:** Pre-commit rejects commits with lock file errors or type-checking failures on `_core` imports.

### Pitfall 6: CI Workflows Lack Rust Toolchain

**What goes wrong:** CI (quality.yml, pr.yml) fails because `uv sync` triggers a maturin build which requires `rustc` and `cargo`, but the CI image only has Python.
**Why it happens:** The existing CI workflows were scaffolded for pure Python. They use `astral-sh/setup-uv` but not `dtolnay/rust-toolchain`.
**How to avoid:** Add `dtolnay/rust-toolchain@stable` step before `uv sync` in CI. Also add Cargo registry caching for faster builds.
**Warning signs:** CI fails with "cargo not found" or "rustc not found" during `uv sync`.

## Code Examples

### Complete lib.rs (Phase 1 Smoke Test)

```rust
// rust/src/lib.rs
// Source: https://pyo3.rs/v0.28.0/module + https://docs.rs/pyo3-arrow/0.17.0/

use pyo3::prelude::*;
use pyo3_arrow::PyRecordBatch;

#[pymodule(name = "_core")]
mod _core {
    use super::*;

    /// Return (num_rows, num_columns) from an Arrow RecordBatch.
    /// Accepts any PyCapsule-compatible input (pyarrow, polars, nanoarrow).
    #[pyfunction]
    fn record_batch_info(batch: PyRecordBatch) -> PyResult<(usize, usize)> {
        let rb = batch.into_inner();
        Ok((rb.num_rows(), rb.num_columns()))
    }
}
```

### Complete pyproject.toml Changes

```toml
# Replace [build-system] section
[build-system]
requires = ["maturin>=1.12,<2.0"]
build-backend = "maturin"

# Update [project] dependencies
[project]
name = "arrowdantic"
version = "0.1.0"
description = "A Python library for Apache Arrow"
readme = "README.md"
authors = [
    { name = "Anentropic", email = "ego@anentropic.com" }
]
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.11",
]

# Add maturin config
[tool.maturin]
features = ["pyo3/extension-module"]
python-source = "src"
module-name = "arrowdantic._core"

# Add uv cache-keys for Rust change detection
[tool.uv]
cache-keys = [{ file = "pyproject.toml" }, { file = "rust/Cargo.toml" }, { file = "rust/**/*.rs" }]
```

**Note on cache-keys glob:** Since Cargo.toml is in `rust/`, the cache-keys must reference `rust/Cargo.toml` and `rust/**/*.rs` (not `Cargo.toml` or `**/*.rs`).

### Complete Cargo.toml

```toml
# rust/Cargo.toml

[package]
name = "arrowdantic-core"
version = "0.1.0"
edition = "2021"
rust-version = "1.83"

[lib]
name = "_core"
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "0.28", features = ["extension-module"] }
pyo3-arrow = "0.17"
arrow-array = "58"
arrow-schema = "58"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
chrono = "0.4"
thiserror = "2"
```

### Build and Verify Commands

```bash
# Initial build (dev mode, fast compile)
maturin develop --uv

# Verify import
python -c "from arrowdantic import _core; print(dir(_core))"

# Verify pyo3-arrow works with pyarrow input
python -c "
import pyarrow as pa
from arrowdantic._core import record_batch_info
batch = pa.record_batch({'x': [1, 2, 3], 'y': ['a', 'b', 'c']})
rows, cols = record_batch_info(batch)
assert rows == 3 and cols == 2, f'Expected (3, 2), got ({rows}, {cols})'
print(f'OK: {rows} rows, {cols} columns')
"
```

### .gitignore Additions

```gitignore
# Rust build artifacts (target/ already present)
# Cargo.lock for library crates (not committed per Rust convention)
rust/Cargo.lock
```

**Note:** `target/` and `*.so` are already in .gitignore. The Rust build puts `target/` in `rust/target/` which is matched by the existing pattern. `Cargo.lock` should NOT be committed for library crates (Rust convention).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `#[pymodule] fn init(m: &Bound<PyModule>)` | `#[pymodule] mod _core { }` (declarative) | PyO3 0.22+ | Cleaner module definitions, automatic function registration |
| `setuptools-rust` | `maturin` | ~2022 | maturin is now the default for new PyO3 projects |
| `arrow-pyarrow` (Apache) | `pyo3-arrow` (arro3 project) | 2024 | pyo3-arrow supports PyCapsule interface, works with polars/nanoarrow, independent release cycle |
| PyO3 `#[pyo3(name)]` on fn | `#[pymodule(name)]` on mod | PyO3 0.28 | Module name set on the mod attribute directly |

**Deprecated/outdated:**
- `uv_build` as build backend: Cannot compile Rust extensions. Must switch to maturin.
- Function-based `#[pymodule]` init: Still works but declarative modules are the recommended pattern in PyO3 0.28.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >= 8.0 (already configured) |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_build.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BUILD-01 | `import arrowdantic._core` succeeds | smoke | `uv run pytest tests/test_build.py::test_import_core -x` | No -- Wave 0 |
| BUILD-02 | pyproject.toml has maturin backend | unit | `uv run pytest tests/test_build.py::test_pyproject_config -x` | No -- Wave 0 |
| BUILD-03 | Cargo.toml contains required dependencies | unit | `uv run pytest tests/test_build.py::test_cargo_dependencies -x` | No -- Wave 0 |
| INPUT-03 | pyo3-arrow accepts PyCapsule input | integration | `uv run pytest tests/test_build.py::test_pycapsule_roundtrip -x` | No -- Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_build.py -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_build.py` -- covers BUILD-01, BUILD-02, BUILD-03, INPUT-03
- [ ] Update `tests/conftest.py` -- add pyarrow fixtures for RecordBatch creation
- [ ] Dev dependency: `uv add --dev pyarrow` -- needed for test fixtures

## Open Questions

1. **`rust/Cargo.toml` vs root `Cargo.toml` layout**
   - What we know: maturin auto-detects `rust/` layout when `src/` contains Python packages. The STACK.md assumed root Cargo.toml, but this conflicts with `src/arrowdantic/` layout.
   - What's unclear: Whether maturin handles `python-source = "src"` with root Cargo.toml when `src/` contains both `lib.rs` and a Python package directory. Docs say this is problematic.
   - Recommendation: Use `rust/` layout. It is the documented approach for src-layout Python projects. Update STACK.md if needed.

2. **CI workflow updates -- scope for Phase 1**
   - What we know: quality.yml, pr.yml, release.yml all need Rust toolchain setup. release.yml needs maturin wheel building instead of `uv build`.
   - What's unclear: Whether CI changes should be in Phase 1 or deferred.
   - Recommendation: Include basic CI fix (add rust toolchain to quality.yml) in Phase 1. Full release workflow update can wait.

3. **Pre-commit hook compatibility**
   - What we know: `uv-lock` hook will need to run after build-backend change. basedpyright will fail on `_core` imports until stubs exist.
   - What's unclear: Exact failure modes and whether temporary workarounds are needed.
   - Recommendation: Run `uv lock` immediately after pyproject.toml change. Defer basedpyright stub issues to Phase 5 (API-05).

## Sources

### Primary (HIGH confidence)
- [pyo3-arrow 0.17 PyRecordBatch API](https://docs.rs/pyo3-arrow/0.17.0/pyo3_arrow/struct.PyRecordBatch.html) - into_inner(), as_ref(), FromPyObject
- [pyo3-arrow 0.17 PyTable API](https://docs.rs/pyo3-arrow/0.17.0/pyo3_arrow/struct.PyTable.html) - batches(), into_inner(), schema
- [PyO3 0.28 module documentation](https://pyo3.rs/v0.28.0/module) - declarative #[pymodule] syntax
- [Maturin project layout](https://www.maturin.rs/project_layout) - rust/ directory auto-detection, python-source config
- [Maturin configuration](https://www.maturin.rs/config) - tool.maturin options, features, module-name
- STACK.md (project research) - version compatibility matrix, Cargo.toml template, pyproject.toml changes

### Secondary (MEDIUM confidence)
- [Maturin + uv integration](https://github.com/PyO3/maturin/issues/2314) - cache-keys behavior
- [Maturin import hook](https://github.com/PyO3/maturin-import-hook) - auto-rebuild on import

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all versions verified via pyo3-arrow 0.17 Cargo.toml and crates.io
- Architecture: HIGH - maturin project layout docs are explicit about rust/ layout for src-layout Python projects
- Pitfalls: HIGH - based on documented maturin/PyO3 behavior and inspection of existing CI/pre-commit config

**Research date:** 2026-03-21
**Valid until:** 2026-04-21 (stable ecosystem, 30-day window)
