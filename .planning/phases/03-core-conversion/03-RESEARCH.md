# Phase 3: Core Conversion - Research

**Researched:** 2026-03-22
**Domain:** Pydantic alias introspection, Arrow Table handling, PyO3 string interning, schema error reporting
**Confidence:** HIGH

## Summary

Phase 3 completes the conversion API surface built on the Phase 2 spike. The work spans four distinct technical areas: (1) Python-side Pydantic model introspection for alias resolution, (2) Rust-side Arrow Table support via pyo3-arrow's `PyTable`, (3) schema mismatch error handling at converter construction time, and (4) a `from_arrow()` convenience function. All eight requirements are well-understood and have clear implementation paths using existing APIs in Pydantic v2.11+ and pyo3-arrow 0.17.

The alias resolution logic belongs entirely in Python (`__init__.py`) because Pydantic's `model_fields` dict and `model_config` are trivially introspectable from Python but would require complex PyO3 attribute access from Rust. The Rust side gains `PyTable` support (trivially -- it decomposes into `Vec<RecordBatch>`) and the existing `convert_record_batch` function is reused without modification. The pre-interned string optimization (FAST-02) is already partially implemented via `PyString::intern` in the Rust hot loop; the Phase 3 improvement is to ensure the interned names are computed once per converter lifetime rather than re-interned on every `convert()` call.

**Primary recommendation:** Keep all alias resolution, schema validation, and `from_arrow()` dispatch in Python; modify Rust only for Table input acceptance and string interning persistence.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCHEMA-03 | `ValueError` raised at init for missing required fields, unresolvable types, or ambiguous matches | Python-side schema validation at `__init__` by cross-referencing `model_fields` keys (with alias resolution) against Arrow schema column names. Collect all mismatches and report them in a single error. |
| SCHEMA-04 | Extra Arrow columns silently ignored (no error for unmapped columns) | Natural consequence of the current "pull" approach: only columns matching a Pydantic field name/alias are selected. Extra columns are never accessed. |
| ALIAS-01 | Alias resolution priority: `validation_alias` > `alias` > `field_name` | `FieldInfo` attributes `validation_alias` and `alias` are directly accessible from `model_fields.items()`. Check `validation_alias` first (must be `str`, not `AliasPath`/`AliasChoices`), then `alias`, then use the dict key. |
| ALIAS-02 | `populate_by_name` support -- accept both alias and field name when enabled | Check `model_config.get('validate_by_name', False) or model_config.get('populate_by_name', False)`. If true, add both the resolved alias AND the field name to the lookup map. |
| ALIAS-03 | `NotImplementedError` raised for `AliasPath` or `AliasGenerator` if encountered | Check `isinstance(validation_alias, (AliasPath, AliasChoices))` on each field. Check `model_config.get('alias_generator')` for `AliasGenerator` instances. Raise `NotImplementedError` with clear message. |
| FAST-02 | Pre-interned Python field name strings reused across all rows (no per-row string allocation) | `PyString::intern(py, name)` is already called before the row loop. Phase 3 improvement: intern once at converter construction or first call, cache across all `convert()` calls for multi-batch reuse. |
| INPUT-02 | Accept pyarrow `Table` as input (iterate batches internally) | pyo3-arrow `PyTable` decomposes via `into_inner()` into `(Vec<RecordBatch>, SchemaRef)`. Add a Rust `convert_table` function or handle dispatch in Python by iterating batches. |
| API-03 | `from_arrow(Model, data)` convenience one-shot function | Python-only function: construct a temporary `ArrowModelConverter(model_class)` and call `convert(data)`. Dispatch on input type (RecordBatch vs Table). |
</phase_requirements>

## Standard Stack

No new dependencies are needed for Phase 3. All required libraries are already in the project.

### Core (already installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | >=2.11 | Model introspection for aliases | `model_fields`, `model_config`, `FieldInfo.validation_alias`/`alias` API |
| pyo3-arrow | 0.17 | `PyTable` type for Table input | `PyTable.into_inner()` returns `(Vec<RecordBatch>, SchemaRef)` |
| pyo3 | 0.28 | `PyString::intern` for string caching | Interns Python strings for reuse across rows |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic.fields.FieldInfo | (part of pydantic) | Alias attribute introspection | At converter `__init__` for alias resolution |
| pydantic.AliasPath | (part of pydantic) | Type checking for unsupported alias types | `isinstance` check to raise `NotImplementedError` |
| pydantic.AliasChoices | (part of pydantic) | Type checking for unsupported alias types | `isinstance` check to raise `NotImplementedError` |

## Architecture Patterns

### Current Architecture (from Phase 2)

```
Python __init__.py                     Rust lib.rs + extract.rs
---------------------                  -----------------------
ArrowModelConverter                    convert_record_batch(
  .__init__(model_cls)                   batch, model_cls,
    -> stores field_names list           col_indices, field_names)
  .convert(batch)                        -> builds extractors
    -> resolves col_indices              -> row loop: kwargs + model_construct
    -> calls Rust convert_record_batch   -> returns PyList
```

### Phase 3 Architecture (target)

```
Python __init__.py                     Rust lib.rs
---------------------                  -----------------------
ArrowModelConverter                    convert_record_batch(...)  [unchanged]
  .__init__(model_cls)                 convert_table(
    -> alias resolution                  table, model_cls,
    -> builds lookup_names list          col_names, field_names)
    -> stores field_names (for kwargs)   -> into_inner() -> batches
    -> stores lookup_names (for Arrow)   -> for each batch: same row loop
  .convert(data)                         -> concatenated PyList
    -> dispatch RecordBatch vs Table
    -> resolve col_indices per batch
    -> call Rust

from_arrow(model_cls, data)            [no Rust changes needed]
  -> ArrowModelConverter(model_cls)
  -> converter.convert(data)
```

### Pattern 1: Alias Resolution at Init (Python-side)

**What:** Build a mapping from Arrow column names to Pydantic field names by introspecting `model_fields`.
**When to use:** Always -- at `ArrowModelConverter.__init__`.
**Example:**

```python
# Source: Pydantic docs (https://docs.pydantic.dev/latest/concepts/alias/)
from pydantic import AliasChoices, AliasPath
from pydantic.fields import FieldInfo

def _build_field_map(model_class: type[BaseModel]) -> dict[str, str]:
    """Build {arrow_column_name: pydantic_field_name} mapping.

    Resolution priority (ALIAS-01):
      1. validation_alias (if str)
      2. alias (if str)
      3. field_name (dict key)
    """
    config = model_class.model_config

    # ALIAS-03: Reject AliasGenerator on model config
    alias_gen = config.get("alias_generator")
    if alias_gen is not None:
        raise NotImplementedError(
            f"AliasGenerator on {model_class.__name__} is not supported. "
            "Use explicit per-field aliases instead."
        )

    field_map: dict[str, str] = {}

    for field_name, field_info in model_class.model_fields.items():
        # ALIAS-03: Reject AliasPath/AliasChoices
        va = field_info.validation_alias
        if va is not None:
            if isinstance(va, (AliasPath, AliasChoices)):
                raise NotImplementedError(
                    f"Field {field_name!r} uses {type(va).__name__} as "
                    "validation_alias, which is not supported."
                )
            lookup_name = va  # str
        elif field_info.alias is not None:
            lookup_name = field_info.alias  # always str
        else:
            lookup_name = field_name

        field_map[lookup_name] = field_name

    # ALIAS-02: populate_by_name / validate_by_name support
    accept_by_name = (
        config.get("validate_by_name", False)
        or config.get("populate_by_name", False)
    )
    if accept_by_name:
        for field_name in model_class.model_fields:
            # Only add if not already present (alias takes priority)
            if field_name not in field_map:
                field_map[field_name] = field_name

    return field_map
```

### Pattern 2: Schema Validation at Init (SCHEMA-03)

**What:** Cross-reference the field map against expectations. Since we don't have an Arrow schema at init time (schemas arrive with data), schema validation must happen at `convert()` time. However, the field map is built at init.
**When to use:** At `convert()` when resolving column indices.
**Example:**

```python
def _resolve_columns(
    self, schema: pa.Schema
) -> tuple[list[int], list[str]]:
    """Resolve Arrow column indices from schema using the field map.

    Returns (col_indices, field_names) for Rust.
    Raises ValueError for missing required columns (SCHEMA-03).
    Extra Arrow columns are silently ignored (SCHEMA-04).
    """
    col_indices = []
    field_names = []
    missing = []

    for lookup_name, field_name in self._field_map.items():
        col_idx = schema.get_field_index(lookup_name)
        if col_idx < 0:
            # Check if field is optional (has a default)
            field_info = self._model_class.model_fields[field_name]
            if field_info.is_required():
                missing.append(lookup_name)
            # Skip optional fields that aren't in Arrow schema
            continue
        col_indices.append(col_idx)
        field_names.append(field_name)

    if missing:
        raise ValueError(
            f"Arrow schema is missing required columns: {missing}. "
            f"Available columns: {schema.names}"
        )

    return col_indices, field_names
```

**Important design decision:** SCHEMA-03 says "ValueError at construction" but the current architecture resolves column indices at `convert()` time (because each batch may have different column order -- see Phase 2 decision). The requirement should be interpreted as "raise ValueError when required fields cannot be matched", which happens at the first `convert()` call. An alternative is to accept an Arrow schema at init time for eager validation, but this changes the API.

**Recommendation:** Keep schema validation at `convert()` time per the Phase 2 decision. This satisfies the intent of SCHEMA-03 (early error, before row processing). The success criteria says "at construction" -- if strict adherence is needed, add an optional `schema` parameter to `__init__`.

### Pattern 3: Table Support via PyTable (INPUT-02)

**What:** Accept `pyarrow.Table` in addition to `RecordBatch`.
**When to use:** When `convert()` receives a Table.

Two implementation options:

**Option A: Python-side dispatch (recommended)**
```python
def convert(self, data: pa.RecordBatch | pa.Table) -> list[BaseModel]:
    if hasattr(data, "to_batches"):
        # Table: iterate batches
        results = []
        for batch in data.to_batches():
            results.extend(self._convert_batch(batch))
        return results
    else:
        return self._convert_batch(data)
```

**Option B: Rust-side convert_table function**
```rust
#[pyfunction]
fn convert_table(
    py: Python<'_>,
    table: PyTable,
    model_cls: Bound<'_, PyAny>,
    col_names: Vec<String>,  // Arrow column names to look up
    field_names: Vec<String>, // Pydantic field names for kwargs
) -> PyResult<PyObject> {
    let (batches, schema) = table.into_inner();
    // ... iterate batches, resolve col_indices per schema, convert each
}
```

**Recommendation:** Option A (Python-side dispatch) is simpler and keeps Rust changes minimal. The per-batch column index resolution already handles different column orders. Option B adds marginal performance benefit (avoids Python loop overhead for batch iteration) but `Table.to_batches()` is cheap and batch count is typically small (1-10).

### Pattern 4: String Interning Persistence (FAST-02)

**What:** Cache interned `PyString` objects across multiple `convert()` calls.
**When to use:** When processing Tables with multiple batches or calling `convert()` repeatedly.

The current code interns strings on every `convert_record_batch` call (line 43-46 of lib.rs). While `PyString::intern` returns the same Python object for the same string value (Python's internal interning), there's overhead in the lookup itself. The improvement is to pass pre-interned strings or cache them.

**Approach:** Since field names are fixed at init time, intern them once in Python and pass the interned objects. Alternatively, maintain a Rust-side `Vec<Py<PyString>>` that persists across calls.

**Simplest approach:** The current code is already correct for FAST-02 as stated ("pre-interned Python field name strings reused across all rows"). `PyString::intern` returns cached strings. The per-call re-interning has negligible overhead compared to the row loop. Mark FAST-02 as satisfied by current implementation.

### Anti-Patterns to Avoid

- **Alias resolution in Rust:** Don't try to introspect `model_fields` from Rust via PyO3 attribute access. It requires multiple `getattr` calls and type checks that are trivial in Python.
- **Schema validation per row:** Validate schema once (at convert time), not per row.
- **Collecting all batches into one before converting:** Don't concatenate Table batches into a single RecordBatch (expensive copy). Process each batch independently and extend the results list.
- **Checking `isinstance(data, pa.Table)` directly:** This requires pyarrow as a runtime dependency. Use duck typing (`hasattr(data, "to_batches")`) or accept both `PyRecordBatch` and `PyTable` at the Rust level.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Alias resolution logic | Custom alias parsing | `FieldInfo.validation_alias`, `FieldInfo.alias` | Pydantic already resolves AliasGenerator output into FieldInfo attributes |
| Table-to-batches iteration | Custom Arrow stream reader | `PyTable.into_inner()` or `Table.to_batches()` | pyo3-arrow and pyarrow handle chunking |
| String interning | Custom string cache HashMap | `PyString::intern(py, name)` | Python's built-in interning is optimal and GC-safe |
| Required-field detection | Custom default/Optional analysis | `FieldInfo.is_required()` | Pydantic handles all edge cases (Optional, default, default_factory) |

## Common Pitfalls

### Pitfall 1: Alias Priority Confusion

**What goes wrong:** Using `alias` when `validation_alias` exists, or vice versa.
**Why it happens:** Pydantic has three alias attributes (`alias`, `validation_alias`, `serialization_alias`) with non-obvious priority.
**How to avoid:** Always check `validation_alias` first. It is the most specific for input/construction. `alias` is the fallback. `serialization_alias` is irrelevant for input construction.
**Warning signs:** Tests pass with simple alias models but fail when `validation_alias` is explicitly set.

### Pitfall 2: AliasGenerator Produces Non-String Aliases

**What goes wrong:** An `AliasGenerator`'s `validation_alias` callable can return `AliasPath` or `AliasChoices`, not just `str`. If you only check the model config for `AliasGenerator` but don't check the resolved `FieldInfo.validation_alias` type, you'll miss these.
**Why it happens:** After the generator runs, the results are stored in `FieldInfo` attributes. The generator itself may be on the config, but the resolved values are on the fields.
**How to avoid:** Check both: (1) `model_config.get('alias_generator')` for early rejection, and (2) `isinstance(field_info.validation_alias, (AliasPath, AliasChoices))` for per-field type safety.
**Warning signs:** No error raised but conversion produces models with wrong field values because column names don't match path-based aliases.

### Pitfall 3: populate_by_name Collision

**What goes wrong:** When `populate_by_name=True`, adding both alias and field name to the lookup map can create duplicate entries if the alias happens to equal another field's name.
**Why it happens:** Two different fields could have aliases that collide with each other's field names.
**How to avoid:** Build the alias map first, then add field names only if they don't collide with existing entries. The alias always wins.
**Warning signs:** `ValueError: duplicate column mapping` or silently wrong field assignment.

### Pitfall 4: Schema Validation Timing

**What goes wrong:** The success criteria says "at construction" but the current architecture resolves schemas at `convert()` time.
**Why it happens:** Phase 2 decision: "Schema matching at convert() time because each batch may have different column order."
**How to avoid:** Clarify that SCHEMA-03 means "before row processing starts" (i.e., at the beginning of `convert()`, not during the row loop). The alias resolution and field map are built at init; column index resolution happens per-batch.
**Warning signs:** Tests expecting `ValueError` at `__init__` fail because the converter doesn't have schema access yet.

### Pitfall 5: Table with Zero Batches

**What goes wrong:** `Table.to_batches()` can return an empty list (e.g., empty Table). Code that assumes at least one batch will crash.
**Why it happens:** Edge case not considered in the happy path.
**How to avoid:** Handle `len(batches) == 0` by returning an empty list.
**Warning signs:** `IndexError` or empty-iterator confusion.

### Pitfall 6: Optional Fields Missing from Arrow Schema

**What goes wrong:** An optional Pydantic field with a default value might not have a corresponding Arrow column. Raising `ValueError` for this is too strict.
**Why it happens:** SCHEMA-03 says "raise for missing required fields" -- but what about optional fields?
**How to avoid:** Only raise for fields where `field_info.is_required()` is True. For optional/defaulted fields missing from Arrow, simply don't include them in the column mapping -- `model_construct` will use the field's default.
**Warning signs:** `ValueError` raised when converting a Table that's missing an optional column.

## Code Examples

### Complete Alias Resolution Implementation

```python
# Source: Pydantic docs (https://docs.pydantic.dev/latest/concepts/alias/)
from pydantic import AliasChoices, AliasPath, BaseModel, ConfigDict, Field


# Test models for alias resolution
class AliasModel(BaseModel):
    # ALIAS-01: validation_alias > alias > field_name
    user_id: int = Field(validation_alias="userId")
    display_name: str = Field(alias="displayName")
    email: str  # no alias, uses field_name


class PopulateByNameModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    user_id: int = Field(alias="userId")


class ValidateByNameModel(BaseModel):
    # Pydantic v2.11+ config
    model_config = ConfigDict(validate_by_name=True)
    user_id: int = Field(alias="userId")


class UnsupportedAliasModel(BaseModel):
    nested_val: str = Field(validation_alias=AliasPath("data", "value"))
```

### PyTable Iteration Pattern (Rust)

```rust
// Source: https://docs.rs/pyo3-arrow/0.17.0/pyo3_arrow/struct.PyTable.html
use pyo3_arrow::PyTable;

#[pyfunction]
fn convert_table(
    py: Python<'_>,
    table: PyTable,
    model_cls: Bound<'_, PyAny>,
    col_indices: Vec<usize>,
    field_names: Vec<String>,
) -> PyResult<PyObject> {
    let (batches, _schema) = table.into_inner();
    let interned_names: Vec<Bound<'_, PyString>> = field_names
        .iter()
        .map(|name| PyString::intern(py, name))
        .collect();

    let total_rows: usize = batches.iter().map(|b| b.num_rows()).sum();
    let mut results: Vec<PyObject> = Vec::with_capacity(total_rows);

    for rb in &batches {
        // Resolve column indices per batch (column order may differ)
        let schema = rb.schema();
        let extractors: Vec<extract::ColumnExtractor<'_>> = col_indices
            .iter()
            .map(|&idx| {
                let col = rb.column(idx);
                let dt = schema.field(idx).data_type();
                extract::prepare_extractor(col.as_ref(), dt)
            })
            .collect::<Result<_, _>>()?;

        for row in 0..rb.num_rows() {
            let kwargs = PyDict::new(py);
            for (extractor, interned_name) in extractors.iter().zip(interned_names.iter()) {
                let value = extractor.extract_value(py, row)?;
                kwargs.set_item(interned_name, value)?;
            }
            let instance = model_cls.call_method("model_construct", (), Some(&kwargs))?;
            results.push(instance.unbind());
        }
    }

    let py_list = PyList::new(py, &results)?;
    Ok(py_list.into_any().unbind())
}
```

**Note on Table column indices:** When processing a Table, all batches share the same schema (Arrow spec guarantees this for a Table), so `col_indices` resolved against the Table schema are valid for all batches. This is different from the current RecordBatch-only path where each call to `convert()` might receive a batch with a different schema.

### from_arrow Convenience Function

```python
def from_arrow(
    model_class: type[BaseModel],
    data: pa.RecordBatch | pa.Table,
) -> list[BaseModel]:
    """One-shot conversion from Arrow data to Pydantic models.

    API-03: Convenience function that creates a temporary converter.
    """
    converter = ArrowModelConverter(model_class)
    return converter.convert(data)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `populate_by_name` config | `validate_by_name` + `validate_by_alias` | Pydantic v2.11 (2025) | More granular control; old config still works but pending deprecation in v3 |
| `alias` for both validation and serialization | Separate `validation_alias` and `serialization_alias` | Pydantic v2.0 | arrowdantic only needs validation aliases |

**Deprecated/outdated:**
- `populate_by_name`: Still functional in v2.11+ but pending deprecation in Pydantic v3. Code should check both `validate_by_name` and `populate_by_name` for backward compatibility.

## Open Questions

1. **SCHEMA-03 Timing: Init vs Convert**
   - What we know: Phase 2 decided "schema matching at convert() time" because batch column order can vary. SCHEMA-03 success criteria says "at construction."
   - What's unclear: Whether "at construction" is strict or means "before row processing."
   - Recommendation: Validate at `convert()` time (first schema encounter). This satisfies the spirit of SCHEMA-03. If strict init-time validation is desired, add an optional `schema` parameter.

2. **Table Column Order Guarantee**
   - What we know: Arrow spec guarantees all batches in a Table share the same schema. `PyTable.into_inner()` returns `(Vec<RecordBatch>, SchemaRef)`.
   - What's unclear: Whether pyo3-arrow's `PyTable` enforces this invariant or if batches could theoretically have reordered columns.
   - Recommendation: Trust the shared schema and resolve column indices once for all batches in a Table. This is safe per Arrow spec.

3. **Optional Fields Not in Arrow Schema**
   - What we know: `model_construct` uses defaults for fields not in kwargs. `FieldInfo.is_required()` detects mandatory fields.
   - What's unclear: Whether the current architecture (fixed list of col_indices/field_names) supports variable-length mappings per batch.
   - Recommendation: Build the mapping from the intersection of Arrow columns and Pydantic fields. Missing optional fields get their defaults via `model_construct`.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/test_convert.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCHEMA-03 | ValueError on missing required columns | unit | `uv run pytest tests/test_phase3.py::TestSchemaValidation::test_missing_required_field_raises -x` | Wave 0 |
| SCHEMA-03 | ValueError lists all missing fields at once | unit | `uv run pytest tests/test_phase3.py::TestSchemaValidation::test_missing_multiple_fields_lists_all -x` | Wave 0 |
| SCHEMA-03 | Optional fields missing from Arrow do not raise | unit | `uv run pytest tests/test_phase3.py::TestSchemaValidation::test_optional_field_missing_uses_default -x` | Wave 0 |
| SCHEMA-04 | Extra Arrow columns silently ignored | unit | `uv run pytest tests/test_phase3.py::TestSchemaValidation::test_extra_columns_ignored -x` | Wave 0 |
| ALIAS-01 | validation_alias > alias > field_name priority | unit | `uv run pytest tests/test_phase3.py::TestAliasResolution::test_validation_alias_priority -x` | Wave 0 |
| ALIAS-01 | alias used when no validation_alias | unit | `uv run pytest tests/test_phase3.py::TestAliasResolution::test_alias_fallback -x` | Wave 0 |
| ALIAS-01 | field_name used when no aliases | unit | `uv run pytest tests/test_phase3.py::TestAliasResolution::test_field_name_fallback -x` | Wave 0 |
| ALIAS-02 | populate_by_name accepts both alias and field name | unit | `uv run pytest tests/test_phase3.py::TestAliasResolution::test_populate_by_name -x` | Wave 0 |
| ALIAS-02 | validate_by_name accepts both alias and field name | unit | `uv run pytest tests/test_phase3.py::TestAliasResolution::test_validate_by_name -x` | Wave 0 |
| ALIAS-03 | AliasPath raises NotImplementedError | unit | `uv run pytest tests/test_phase3.py::TestAliasResolution::test_alias_path_raises -x` | Wave 0 |
| ALIAS-03 | AliasChoices raises NotImplementedError | unit | `uv run pytest tests/test_phase3.py::TestAliasResolution::test_alias_choices_raises -x` | Wave 0 |
| ALIAS-03 | AliasGenerator raises NotImplementedError | unit | `uv run pytest tests/test_phase3.py::TestAliasResolution::test_alias_generator_raises -x` | Wave 0 |
| FAST-02 | Interned strings reused (no per-row allocation) | unit | `uv run pytest tests/test_phase3.py::TestStringInterning::test_field_name_identity -x` | Wave 0 |
| INPUT-02 | Table input produces correct results | integration | `uv run pytest tests/test_phase3.py::TestTableInput::test_table_conversion -x` | Wave 0 |
| INPUT-02 | Table with multiple batches processes all rows | integration | `uv run pytest tests/test_phase3.py::TestTableInput::test_multi_batch_table -x` | Wave 0 |
| INPUT-02 | Empty Table returns empty list | unit | `uv run pytest tests/test_phase3.py::TestTableInput::test_empty_table -x` | Wave 0 |
| API-03 | from_arrow with RecordBatch | unit | `uv run pytest tests/test_phase3.py::TestFromArrow::test_from_arrow_record_batch -x` | Wave 0 |
| API-03 | from_arrow with Table | unit | `uv run pytest tests/test_phase3.py::TestFromArrow::test_from_arrow_table -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_phase3.py -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_phase3.py` -- covers SCHEMA-03, SCHEMA-04, ALIAS-01, ALIAS-02, ALIAS-03, FAST-02, INPUT-02, API-03
- [ ] Test models with aliases in `tests/test_phase3.py` (not conftest -- per Phase 2 convention)

## Sources

### Primary (HIGH confidence)
- Pydantic alias docs: https://docs.pydantic.dev/latest/concepts/alias/ -- alias priority, validation_alias/alias/field_name interaction
- Pydantic FieldInfo API: https://docs.pydantic.dev/latest/api/fields/ -- FieldInfo attributes (validation_alias, alias, serialization_alias types)
- Pydantic aliases API: https://docs.pydantic.dev/latest/api/aliases/ -- AliasPath, AliasChoices, AliasGenerator class signatures and isinstance detection
- Pydantic ConfigDict API: https://docs.pydantic.dev/latest/api/config/ -- validate_by_name (v2.11+), validate_by_alias, populate_by_name defaults
- Pydantic v2.11 release: https://pydantic.dev/articles/pydantic-v2-11-release -- validate_by_name/validate_by_alias introduction
- pyo3-arrow PyTable docs: https://docs.rs/pyo3-arrow/0.17.0/pyo3_arrow/struct.PyTable.html -- into_inner(), batches() methods
- pyo3-arrow PyTable source: https://docs.rs/pyo3-arrow/0.17.0/src/pyo3_arrow/table.rs.html -- struct definition, Vec<RecordBatch> + SchemaRef internals
- PyO3 PyString::intern: https://pyo3.rs/main/doc/pyo3/types/struct.pystring -- intern method signature, memory vs speed tradeoff
- PyO3 intern! macro: https://pyo3.rs/main/doc/pyo3/macro.intern -- compile-time string interning vs runtime
- Project design notes: `_notes/arrowdantic-design.md` lines 130-187 -- alias resolution pseudocode, hot loop design

### Secondary (MEDIUM confidence)
- PyO3 string interning PR: https://github.com/PyO3/pyo3/pull/2268 -- PyString::intern implementation details
- PyO3 intern! macro PR: https://github.com/PyO3/pyo3/pull/2269 -- GILOnceCell-based static interning

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all APIs verified against official docs
- Architecture: HIGH -- extends proven Phase 2 patterns, Python-side alias introspection is well-documented
- Pitfalls: HIGH -- alias priority, populate_by_name collision, and schema timing are all documented in project research and Pydantic docs

**Research date:** 2026-03-22
**Valid until:** 2026-04-22 (stable domain, Pydantic v2.11+ API is settled)
