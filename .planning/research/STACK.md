# Technology Stack

**Project:** arrowdantic
**Researched:** 2026-03-21

## Recommended Stack

### Build System

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| maturin | >=1.12,<2.0 | Rust/Python build backend | The standard build tool for PyO3 crates. Integrates with pyproject.toml, handles wheel generation, supports `maturin develop` for fast dev builds. v1.12.6 is latest stable. | HIGH |
| uv | (project tooling) | Python package/project management | Already in use (uv.lock present). Works with maturin as build backend via `[build-system] requires = ["maturin>=1.12,<2.0"]`. | HIGH |
| maturin-import-hook | >=0.1 | Auto-rebuild on import during dev | Automatically rebuilds the Rust extension when source changes are detected on import. Eliminates the `maturin develop` / `uv sync` cache staleness problem. Optional dev dependency. | MEDIUM |

**Critical build system change:** The project currently uses `uv_build` as build-backend. This must change to `maturin` to compile the Rust extension. The `pyproject.toml` `[build-system]` section needs:

```toml
[build-system]
requires = ["maturin>=1.12,<2.0"]
build-backend = "maturin"

[tool.maturin]
features = ["pyo3/extension-module"]
python-source = "src"
module-name = "arrowdantic._core"
```

And add to `[tool.uv]`:

```toml
[tool.uv]
cache-keys = [{ file = "pyproject.toml" }, { file = "Cargo.toml" }, { file = "**/*.rs" }]
```

This tells uv to invalidate its build cache when Rust source files change, solving the stale-build problem when using `uv run` or `uv sync`.

### Rust Core Dependencies

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| pyo3 | 0.28 | Rust-Python FFI bindings | Latest stable (0.28.2). Supports Python 3.11-3.14 including free-threaded 3.14t. MSRV Rust 1.83. Required features: `extension-module`, `chrono`. | HIGH |
| pyo3-arrow | 0.17 | Arrow C Data Interface for PyO3 | The purpose-built crate for this project's core need. Provides `PyRecordBatch`, `PyTable` etc. that accept any Arrow-PyCapsule-compatible input (pyarrow, polars, nanoarrow) via zero-copy FFI. Depends on pyo3 0.28 + arrow 58. | HIGH |
| arrow (arrow-rs) | 58 | Arrow in-memory format | Required by pyo3-arrow 0.17. Use individual sub-crates (`arrow-array`, `arrow-schema`, `arrow-data`, `arrow-buffer`, `arrow-cast`, `arrow-select`) to minimize compile times. v58.0.0 released Feb 2026. | HIGH |
| serde | 1 | Serialization framework | Required by serde_json. Derive macros for any Rust structs that need serialization. | HIGH |
| serde_json | 1 | JSON serialization | For the validated path: serialize Arrow rows to JSON bytes, then pass to Pydantic's `model_validate_json`. v1.0.149 is latest. | HIGH |
| chrono | 0.4 | Date/time types | Arrow date/timestamp types convert to chrono types. pyo3 has a `chrono` feature for automatic Python datetime conversion. v0.4.43 is latest. | HIGH |
| thiserror | 2 | Error type derivation | Ergonomic error types for the conversion layer. Use v2 (not v1) -- v2 is the current major. | MEDIUM |

**Version pinning rationale:** pyo3-arrow 0.17 is the version gate. It requires pyo3 ^0.28 and arrow ^58. All other Rust deps should use standard semver ranges. Do NOT pin arrow independently of pyo3-arrow -- let pyo3-arrow's Cargo.toml drive the arrow version to avoid version conflicts.

### Python Dependencies

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| pydantic | >=2.11 | Data model validation | v2.11+ required (not just v2.0) because v2.11 introduced `validate_by_name`/`validate_by_alias` config which replaces the older `populate_by_name`. The project needs these for alias resolution. v2.12.5 is latest stable. | HIGH |
| pyarrow | (optional) | Arrow provider for testing | Not a hard dependency. Any Arrow-PyCapsule-compatible library works (pyarrow, polars, nanoarrow). Optional for type stubs and testing. | HIGH |

### Dev Dependencies (Python)

| Technology | Version | Purpose | Confidence |
|------------|---------|---------|------------|
| pytest | >=8.0 | Testing framework | HIGH |
| pytest-benchmark | >=5.0 | Performance benchmarks | MEDIUM |
| pyarrow | >=14.0 | Test fixture data creation | HIGH |
| maturin-import-hook | >=0.1 | Auto-rebuild during dev | MEDIUM |
| basedpyright | >=1.38 | Type checking (already in project) | HIGH |
| ruff | >=0.15 | Linting/formatting (already in project) | HIGH |

### Dev Dependencies (Rust)

| Technology | Version | Purpose | Confidence |
|------------|---------|---------|------------|
| criterion | 0.5 | Rust-side benchmarks (optional, for micro-benchmarks) | LOW |

## Key Version Compatibility Matrix

This is the critical constraint. pyo3-arrow is the linchpin that ties PyO3 and arrow-rs versions together.

| pyo3-arrow | pyo3 | arrow-rs | Status |
|------------|------|----------|--------|
| 0.17 | 0.28 | 58 | **Current recommended** |
| 0.16 | 0.23 | 54 | Outdated, skip |

**Use pyo3-arrow 0.17.** It is the latest release and tracks the latest pyo3 (0.28) and arrow-rs (58). Earlier versions are not worth considering because they lag significantly on both pyo3 and arrow-rs.

## Alternatives Considered

### Arrow FFI Approach: pyo3-arrow vs arrow-pyarrow

| Criterion | pyo3-arrow (recommended) | arrow-pyarrow |
|-----------|-------------------------|---------------|
| Input flexibility | Any PyCapsule-compatible lib (pyarrow, polars, nanoarrow) | pyarrow only |
| Extension types | Supported (stores Field + Array) | Dropped (loses field metadata) |
| ChunkedArray/Table | Full support via PyTable, PyChunkedArray | Limited (no ChunkedArray) |
| Output targets | arro3, nanoarrow, pyarrow | pyarrow only |
| Release coupling | Independent release cadence | Locked to arrow-rs releases (version skew risk) |
| Buffer protocol | Auto-converts numpy/memoryview to PyArray | Not supported |
| Maturity | Used in production by arro3, lonboard, geoarrow-rs | Official Apache project but narrower scope |

**Use pyo3-arrow.** The input flexibility is critical -- arrowdantic should accept data from any Arrow-compatible Python library, not just pyarrow. The independent release cadence also matters because arrow-pyarrow's pyo3 version often lags behind (arrow-rs waits for its own release cycle before bumping pyo3).

### Pydantic Version Floor: >=2.11 vs >=2.0

| Criterion | >=2.11 (recommended) | >=2.0 |
|-----------|----------------------|-------|
| Alias config | `validate_by_name`/`validate_by_alias` (cleaner API) | `populate_by_name` only |
| model_construct | Same API across all v2 | Same |
| model_validate_json | Same API across all v2 | Same |
| User base impact | Anyone on v2 should be on 2.11+ by now | Wider compat but adds alias handling complexity |

**Use >=2.11.** The `validate_by_name`/`validate_by_alias` config is the modern API for alias resolution. `populate_by_name` still works but is pending deprecation in v3. Setting the floor at 2.11 simplifies alias introspection code and future-proofs the library.

### Build Backend: maturin vs setuptools-rust

| Criterion | maturin (recommended) | setuptools-rust |
|-----------|----------------------|-----------------|
| Configuration | pyproject.toml only | setup.py + pyproject.toml |
| uv integration | First-class (cache-keys, build backend) | Partial |
| Community | Standard for new PyO3 projects | Legacy, fewer new adopters |
| Features | Editable installs, import hook, abi3 | Editable installs |

**Use maturin.** It is the canonical build tool for PyO3 projects. setuptools-rust exists but is the older approach with no advantages for new projects.

## pyo3-arrow API Patterns

These are the key types from pyo3-arrow 0.17 that arrowdantic will use:

### Receiving Arrow Data from Python

```rust
use pyo3::prelude::*;
use pyo3_arrow::PyRecordBatch;

// Accept a RecordBatch -- any PyCapsule-compatible object auto-converts
#[pyfunction]
fn process_batch(batch: PyRecordBatch) -> PyResult<()> {
    let record_batch = batch.into_inner(); // arrow::record_batch::RecordBatch
    // ... iterate columns, extract values
    Ok(())
}
```

### Receiving a Table (multiple batches)

```rust
use pyo3_arrow::PyTable;

#[pyfunction]
fn process_table(table: PyTable) -> PyResult<()> {
    let batches = table.batches(); // &[RecordBatch]
    for batch in batches {
        // process each batch
    }
    Ok(())
}
```

### Key Types

| pyo3-arrow Type | Arrow Type | Python Input |
|-----------------|------------|--------------|
| `PyRecordBatch` | `RecordBatch` | pyarrow.RecordBatch, polars chunk |
| `PyTable` | `Vec<RecordBatch>` + Schema | pyarrow.Table, polars DataFrame |
| `PySchema` | `Schema` | pyarrow.Schema |
| `PyField` | `Field` | pyarrow.Field |
| `PyArray` | `ArrayRef` | pyarrow.Array, numpy array |

## Pydantic Integration Patterns

### Fast Path: model_construct (no validation)

From Rust, call Pydantic's `model_construct` class method via PyO3:

```rust
// Pseudocode for the hot loop
fn construct_model(
    py: Python<'_>,
    model_cls: &Bound<'_, PyAny>,  // The Pydantic model class
    field_values: &Bound<'_, PyDict>,  // {field_name: value}
) -> PyResult<Bound<'_, PyAny>> {
    model_cls.call_method1("model_construct", (field_values,))
    // model_construct accepts **kwargs, but from Rust we pass a dict
}
```

**Critical detail:** `model_construct` accepts **field names** (not aliases) as keyword arguments. It sets `__dict__` directly. This means the schema cross-reference in Python must resolve Arrow column names to Pydantic field names, and the Rust hot loop uses the field names as dict keys.

### Validated Path: serde_json + model_validate_json

```rust
// Serialize row to JSON bytes in Rust
let json_bytes: Vec<u8> = serde_json::to_vec(&row_map)?;
// Pass to Pydantic's model_validate_json
let py_bytes = PyBytes::new(py, &json_bytes);
model_cls.call_method1("model_validate_json", (py_bytes,))
```

**Key insight:** `model_validate_json` accepts `bytes` (not just `str`), avoiding a UTF-8 copy. Pydantic v2's internal jiter parser handles the bytes directly.

### Alias Resolution (Python-side, at converter init)

```python
# Introspect Pydantic model to build column-name -> field-name mapping
for field_name, field_info in Model.model_fields.items():
    # Resolution priority: validation_alias > alias > field_name
    if field_info.validation_alias is not None:
        if isinstance(field_info.validation_alias, str):
            lookup_name = field_info.validation_alias
        else:
            raise NotImplementedError("AliasPath/AliasChoices not supported")
    elif field_info.alias is not None:
        lookup_name = field_info.alias
    else:
        lookup_name = field_name

    # Also check populate_by_name / validate_by_name
    config = Model.model_config
    accept_field_name_too = config.get('populate_by_name', False) or config.get('validate_by_name', False)
```

This introspection happens once at `ArrowModelConverter.__init__` (Python), producing a mapping that the Rust hot loop uses.

## Cargo.toml Template

```toml
[package]
name = "arrowdantic-core"
version = "0.1.0"
edition = "2021"
rust-version = "1.83"

[lib]
name = "_core"
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "0.28", features = ["extension-module", "chrono"] }
pyo3-arrow = "0.17"
arrow-array = "58"
arrow-schema = "58"
arrow-data = "58"
arrow-buffer = "58"
arrow-cast = "58"
arrow-select = "58"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
chrono = "0.4"
thiserror = "2"
```

**Notes:**
- `crate-type = ["cdylib"]` is required for maturin to produce a Python extension module.
- Use individual `arrow-*` sub-crates instead of the umbrella `arrow` crate to reduce compile times. Only pull in what you actually use.
- The `extension-module` feature on pyo3 is required for building as a Python extension (prevents linking against libpython).
- The `chrono` feature on pyo3 enables automatic conversion between `chrono::NaiveDateTime`/`chrono::DateTime<Utc>` and Python `datetime`.

## pyproject.toml Changes Required

The current `pyproject.toml` uses `uv_build` and has no Rust dependencies declared. It needs these changes:

```toml
[build-system]
requires = ["maturin>=1.12,<2.0"]
build-backend = "maturin"

[project]
dependencies = [
    "pydantic>=2.11",
]

[project.optional-dependencies]
pyarrow = ["pyarrow>=14.0"]

[tool.maturin]
features = ["pyo3/extension-module"]
python-source = "src"
module-name = "arrowdantic._core"

[tool.uv]
cache-keys = [{ file = "pyproject.toml" }, { file = "Cargo.toml" }, { file = "**/*.rs" }]
```

## Development Workflow

### Recommended: maturin develop + import hook

```bash
# One-time setup
uv add --dev maturin-import-hook

# Development iteration
maturin develop --uv        # Initial build, installs into uv venv
# OR use import hook for auto-rebuild:
python -c "import maturin_import_hook; maturin_import_hook.install()"
```

### Alternative: uv sync (slower but integrated)

```bash
uv sync    # Rebuilds via maturin build backend if cache-keys changed
uv run pytest
```

The `uv sync` approach rebuilds in release mode (slower compile, faster runtime). `maturin develop` builds in debug mode by default (faster compile, adequate for dev). For development iteration speed, prefer `maturin develop`.

## Minimum Rust Version

**Rust 1.83** -- set by pyo3 0.28's MSRV. arrow-rs 58 requires Rust 1.75 (subsumed). Declare `rust-version = "1.83"` in Cargo.toml.

## Python Version Support

**Python >=3.11** -- already declared in pyproject.toml. PyO3 0.28 supports 3.8+, so 3.11 floor is fine. pyo3-arrow 0.17 has no additional Python version constraints.

PyO3 0.28 also supports Python 3.14 and free-threaded Python 3.14t, so the >=3.11 floor is forward-compatible.

## Sources

- PyO3 releases: https://github.com/pyo3/pyo3/releases (latest: 0.28.2, Feb 2025) -- HIGH confidence
- pyo3-arrow Cargo.toml: https://github.com/kylebarron/arro3/blob/main/pyo3-arrow/Cargo.toml (v0.17, pyo3 0.28, arrow 58) -- HIGH confidence
- pyo3-arrow docs: https://docs.rs/pyo3-arrow/latest/pyo3_arrow/ -- HIGH confidence
- arrow-rs releases: https://github.com/apache/arrow-rs/releases (latest: 58.0.0, Feb 2026) -- HIGH confidence
- maturin releases: https://github.com/pyo3/maturin/releases (latest: 1.12.6, Mar 2026) -- HIGH confidence
- Pydantic docs (model_construct): https://docs.pydantic.dev/latest/api/base_model/ -- HIGH confidence
- Pydantic docs (aliases): https://docs.pydantic.dev/latest/concepts/alias/ -- HIGH confidence
- Pydantic v2.11 release (validate_by_name): https://pydantic.dev/articles/pydantic-v2-11-release -- HIGH confidence
- Pydantic releases: https://github.com/pydantic/pydantic/releases (latest: 2.12.5, Nov 2025) -- HIGH confidence
- serde_json: https://crates.io/crates/serde_json (latest: 1.0.149) -- HIGH confidence
- chrono: https://crates.io/crates/chrono (latest: 0.4.43) -- HIGH confidence
- maturin + uv integration: https://github.com/PyO3/maturin/issues/2314 -- MEDIUM confidence
- maturin import hook: https://github.com/PyO3/maturin-import-hook -- MEDIUM confidence
- pyo3-arrow vs arrow-pyarrow comparison: https://docs.rs/pyo3-arrow/latest/pyo3_arrow/ and https://arrow.apache.org/rust/arrow_pyarrow/index.html -- MEDIUM confidence (synthesized from multiple sources)
