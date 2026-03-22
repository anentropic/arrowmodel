# Phase 4: Extended Types - Research

**Researched:** 2026-03-22
**Domain:** Arrow temporal types, nested/complex types, dictionary arrays, PyO3 datetime FFI
**Confidence:** HIGH

## Summary

Phase 4 extends the existing `ColumnExtractor` enum with temporal types (Date32, Timestamp, Duration), complex types (List, LargeList, Struct, Dictionary), and the Null type. The core approach is adding new enum variants to `ColumnExtractor` and corresponding match arms in `prepare_extractor` and `extract_value`.

The most significant technical decision is **enabling the `chrono` feature on pyo3** in Cargo.toml. This unlocks automatic `IntoPyObject` conversions from `chrono::NaiveDate` to `PyDate`, `chrono::NaiveDateTime` to `PyDateTime`, and `chrono::TimeDelta` to `PyDelta`. Without this feature, we would need to manually construct Python datetime objects via the C API wrappers (`PyDate::new()`, `PyDateTime::new()`, etc.), which is more code and more error-prone. The chrono crate is already a dependency but the pyo3 feature gate is not enabled.

For timezone-aware timestamps, the user decision specifies using `zoneinfo.ZoneInfo` with IANA names, caching the ZoneInfo object per batch (not per row). This means importing `zoneinfo.ZoneInfo` from Python at batch preparation time and passing it to `PyDateTime::new()` as the `tzinfo` argument. We do NOT use pyo3's `chrono-tz` feature because it would add a compile-time dependency on the chrono-tz crate (which embeds the entire IANA timezone database in the binary). Instead, we leverage Python's built-in `zoneinfo` module (guaranteed available on Python 3.11+).

For Struct columns, the user locked decision is Rust-side recursive construction: `ColumnExtractor::Struct` holds child extractors and the nested model class, calling `model_construct` from Rust for nested models.

**Primary recommendation:** Enable `pyo3 = { features = ["extension-module", "chrono"] }`, add `arrow-cast = "58"` for dictionary unpacking, then extend `ColumnExtractor` with ~10 new variants covering all required types.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TEMP-01 | Date32 -> `datetime.date` | arrow-rs `Date32Array` + `value_as_date()` returns `chrono::NaiveDate`; pyo3 chrono feature converts `NaiveDate` to `PyDate` automatically |
| TEMP-02 | Timestamp (no tz) -> naive `datetime.datetime` | arrow-rs `value_as_datetime()` returns `chrono::NaiveDateTime`; pyo3 chrono converts to `PyDateTime` |
| TEMP-03 | Timestamp (with tz) -> aware `datetime.datetime` | Extract naive datetime from arrow, construct `PyDateTime::new()` with `ZoneInfo` tzinfo from Python's zoneinfo module |
| TEMP-04 | Duration -> `datetime.timedelta` | arrow-rs `value_as_duration()` returns `chrono::TimeDelta`; pyo3 chrono converts to `PyDelta` |
| TEMP-05 | Nanosecond truncation to microsecond | Python datetime max precision is microsecond (0-999999). Nanosecond timestamps must truncate: `ns / 1000` for microsecond component |
| CPLX-01 | List -> `list` with element types | `GenericListArray<i32>` with `value(i)` returning child `ArrayRef`; recursive extraction of elements |
| CPLX-02 | LargeList -> `list` | Same as List but `GenericListArray<i64>`, identical code path via generic |
| CPLX-03 | Struct -> nested Pydantic model | `StructArray` child columns + recursive `ColumnExtractor` tree + nested `model_construct` calls |
| CPLX-04 | Dictionary -> value type | `DictionaryArray<K>` with `key(i)` -> index into `values()` array; decode transparently |
| CPLX-05 | Null type -> `None` always | `NullArray` -- extractor always returns `py.None()` regardless of row index |
</phase_requirements>

## Standard Stack

### Core (already in Cargo.toml)
| Library | Version | Purpose | Change Needed |
|---------|---------|---------|---------------|
| pyo3 | 0.28 | Rust-Python FFI | **Add `chrono` feature**: `features = ["extension-module", "chrono"]` |
| arrow-array | 58 | Arrow array types | Already present, has all needed types (Date32Array, TimestampArray, StructArray, ListArray, DictionaryArray, NullArray) |
| arrow-schema | 58 | Arrow DataType enum | Already present, has all needed variants |
| chrono | 0.4 | Date/time types | Already present as dependency |

### New Dependencies Required
| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| arrow-cast | 58 | Array casting/conversion | Provides `arrow_cast::cast()` for dictionary array unpacking (decoding dictionary-encoded arrays to their value type). Also provides `as_dictionary_array` and related cast helpers. |

### Not Needed
| Library | Why Not |
|---------|---------|
| chrono-tz (crate) | Embeds entire IANA tz database in binary. Python's `zoneinfo.ZoneInfo` is better -- already available on Python 3.11+ |
| pyo3 `chrono-tz` feature | Would require chrono-tz crate dependency |
| arrow-select | Not needed for this phase |

**Cargo.toml changes:**
```toml
[dependencies]
pyo3 = { version = "0.28", features = ["extension-module", "chrono"] }
pyo3-arrow = "0.17"
arrow-array = "58"
arrow-schema = "58"
arrow-cast = "58"       # NEW: for dictionary array unpacking
serde = { version = "1", features = ["derive"] }
serde_json = "1"
chrono = "0.4"
thiserror = "2"
```

## Architecture Patterns

### Extended ColumnExtractor Enum

The existing `ColumnExtractor` enum gets ~10 new variants. The pattern follows the established design: downcast once in `prepare_extractor`, extract per-row in `extract_value`.

```
ColumnExtractor<'a>
  // Existing: Int8..UInt64, Float32, Float64, Boolean, Utf8, LargeUtf8
  // NEW temporal:
  Date32(&'a Date32Array)
  TimestampNaive(&'a dyn Array, TimeUnit)          // no timezone
  TimestampAware(&'a dyn Array, TimeUnit, PyObject) // with cached ZoneInfo
  Duration(&'a dyn Array, TimeUnit)
  // NEW complex:
  List(&'a ListArray, Box<ColumnExtractor<'a>>)     // child extractor
  LargeList(&'a LargeListArray, Box<ColumnExtractor<'a>>)
  Struct(&'a StructArray, Vec<(Py<PyString>, ColumnExtractor<'a>)>, PyObject) // fields + model_cls
  Dictionary(&'a dyn Array)  // pre-unpacked to value array via arrow-cast
  // NEW null:
  Null(usize)  // just the length, always returns None
```

### Pattern 1: Temporal Type Extraction (with chrono feature)

**What:** Use arrow-rs `value_as_date()` / `value_as_datetime()` / `value_as_duration()` to get chrono types, then rely on pyo3's chrono feature for automatic `IntoPyObject` conversion.

**When to use:** Date32, naive timestamps, durations.

```rust
// Source: arrow-rs PrimitiveArray + pyo3 chrono feature
// Date32 extraction
ColumnExtractor::Date32(arr) => {
    if arr.is_null(row) {
        Ok(py.None())
    } else {
        // value_as_date returns Option<NaiveDate>
        match arr.value_as_date(row) {
            Some(date) => Ok(date.into_pyobject(py)?.into_any().unbind()),
            None => Ok(py.None()),
        }
    }
}
```

### Pattern 2: Timezone-Aware Timestamp Extraction

**What:** Extract the raw timestamp value, convert to naive datetime components, then construct a `PyDateTime` with a cached `ZoneInfo` object.

**When to use:** `Timestamp(unit, Some(tz_string))` columns.

**Why not use chrono's IntoPyObject for DateTime<FixedOffset>:** chrono's `DateTime<FixedOffset>` loses IANA timezone names (converts "America/New_York" to a fixed offset like "-05:00"). The user decision requires preserving IANA names via `zoneinfo.ZoneInfo`.

```rust
// Cache ZoneInfo once per batch in prepare_extractor:
let zoneinfo_mod = py.import("zoneinfo")?;
let zone_info_cls = zoneinfo_mod.getattr("ZoneInfo")?;
let tz_obj = zone_info_cls.call1((tz_string,))?;

// Per-row extraction:
ColumnExtractor::TimestampAware(arr, unit, tz_obj) => {
    if arr.is_null(row) {
        Ok(py.None())
    } else {
        let raw_value = as_primitive_array::<TimestampXType>(arr).value(row);
        // Convert to components (year, month, day, hour, min, sec, us)
        // Truncate nanoseconds to microseconds for TEMP-05
        let dt = PyDateTime::new(py, year, month, day, hour, min, sec, us, Some(&tz_obj))?;
        Ok(dt.into_any().unbind())
    }
}
```

### Pattern 3: Nanosecond Truncation (TEMP-05)

**What:** Python `datetime.datetime` supports microsecond precision (max 999999). Nanosecond timestamps must truncate.

**How:** When `TimeUnit::Nanosecond`, divide the sub-second component by 1000 to get microseconds:

```rust
// For TimestampNanosecondType:
let ns_value: i64 = arr.value(row);
let secs = ns_value / 1_000_000_000;
let ns_remainder = (ns_value % 1_000_000_000) as u32;
let us = ns_remainder / 1000;  // Truncate to microseconds
```

Note: `value_as_datetime()` on `TimestampNanosecondArray` already handles this correctly because chrono's `NaiveDateTime` stores microsecond precision. The truncation happens naturally in chrono's conversion.

### Pattern 4: List/LargeList Extraction

**What:** `ListArray.value(i)` returns an `ArrayRef` containing the elements for row `i`. Recursively extract each element using a child `ColumnExtractor`.

```rust
ColumnExtractor::List(arr, child_extractor) => {
    if arr.is_null(row) {
        Ok(py.None())
    } else {
        let child_array = arr.value(row);  // ArrayRef for this row's list
        let len = child_array.len();
        let mut items: Vec<PyObject> = Vec::with_capacity(len);
        for j in 0..len {
            items.push(child_extractor.extract_from_array(py, &child_array, j)?);
        }
        let py_list = PyList::new(py, &items)?;
        Ok(py_list.into_any().unbind())
    }
}
```

**Key design note:** The child extractor needs to work with a dynamically obtained `ArrayRef` (the sub-array for each row), not a pre-downcast reference. This means list element extraction uses a slightly different code path than top-level column extraction. Consider adding an `extract_from_array(&self, py, array, row)` method or using a separate `ElementExtractor` for list items that downcasts per-list-value.

**Alternative (simpler):** Since each row's list sub-array has the same element type (from the List's Field), create a temporary `ColumnExtractor` for the child type once in `prepare_extractor`, but call it per-element on the sliced array. The child array type is consistent across rows.

### Pattern 5: Struct Extraction (Recursive model_construct)

**What:** `StructArray` has child columns accessible via `column(i)`. Build child `ColumnExtractor`s for each child field, extract values, call `model_construct` on the nested Pydantic model class.

**User decision:** Rust-side recursive construction (Option A).

```rust
ColumnExtractor::Struct(arr, child_extractors, nested_model_cls) => {
    if arr.is_null(row) {
        Ok(py.None())  // null struct -> None for entire nested model
    } else {
        let kwargs = PyDict::new(py);
        for (field_name, extractor) in child_extractors.iter() {
            let value = extractor.extract_value(py, row)?;
            kwargs.set_item(field_name, value)?;
        }
        let instance = nested_model_cls.call_method(py, "model_construct", (), Some(&kwargs))?;
        Ok(instance)
    }
}
```

**Important:** The nested model class must be determined at `prepare_extractor` time. This requires passing the Pydantic model's field type information down from Python. The Python `_resolve_columns` method needs to pass nested model class references to Rust alongside column indices. This is a significant API change to `convert_record_batch` and `convert_table`.

### Pattern 6: Dictionary Array Extraction

**What:** Dictionary-encoded columns store values as indices into a value array. Resolution approach: use `arrow_cast::cast()` to unpack the dictionary into a plain array of the value type, then use the standard extractor for that type.

**Why cast, not manual key lookup:** Manual key-to-value lookup requires knowing the key type (Int8, Int16, Int32, Int64) and value type separately, creating a combinatorial explosion of match arms. `arrow_cast::cast()` handles all key types automatically.

```rust
// In prepare_extractor:
DataType::Dictionary(_, value_type) => {
    // Unpack dictionary to plain array of value type
    let unpacked = arrow_cast::cast(col, value_type)?;
    prepare_extractor(unpacked.as_ref(), value_type)
}
```

**Alternative (avoid arrow-cast dependency):** Manually match on key type and resolve values per-row using `key(i)` + `values()[key_idx]`. This avoids the `arrow-cast` dependency but requires 4x key type variants (Int8, Int16, Int32, Int64) combined with all value types. The cast approach is strongly preferred.

### Pattern 7: Null Type Extraction

**What:** `DataType::Null` columns have `NullArray` where every element is null. The extractor always returns `py.None()`.

```rust
ColumnExtractor::Null => {
    Ok(py.None())
}
```

### API Changes Required

The current Rust functions `convert_record_batch` and `convert_table` receive `col_indices: Vec<usize>` and `field_names: Vec<String>`. For Struct columns, we additionally need to pass:

1. **Nested model classes** for Struct fields
2. **Type metadata** so `prepare_extractor` knows what Pydantic model to use for nested structs

**Recommended approach:** Pass a `field_specs` parameter instead of separate `col_indices` + `field_names`. Each spec includes the column index, the Pydantic field name, and optionally a nested model class reference. This can be a Python list of tuples or a structured object.

**Simpler alternative:** Keep the current API for non-struct columns. For struct columns, pass an additional mapping from column index to nested model class. This minimizes API disruption.

### Anti-Patterns to Avoid

- **Matching on all 4 TimeUnit variants x all temporal types:** Instead, use the generic `as_primitive_array::<T>` with the specific type, or compute components from the raw i64 value + TimeUnit arithmetic.
- **Creating ZoneInfo per row:** Cache it once per batch. The `zoneinfo.ZoneInfo` constructor is relatively expensive.
- **Using `is_null()` on NullArray:** `NullArray.is_null()` returns `false` (no physical null buffer). Use `logical_nulls()` or just always return None since all elements are logically null by definition.
- **Hand-rolling dictionary decoding:** Use `arrow_cast::cast()` to unpack. Manual key-type x value-type combinatorics is fragile.
- **Passing nested model class via global state:** Pass it explicitly through `prepare_extractor` parameters.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| chrono -> Python datetime | Manual `PyDate::new(y,m,d)` construction | pyo3 `chrono` feature + `IntoPyObject` | Handles edge cases (leap seconds, overflow), well-tested |
| Dictionary array unpacking | Manual key-type matching + index lookup | `arrow_cast::cast()` to value type | Handles all key types (Int8/16/32/64) automatically |
| Nanosecond -> microsecond | Custom division logic | chrono's NaiveDateTime (stores microsecond precision) | Truncation is built into chrono's conversion |
| Date32 -> NaiveDate | Manual epoch arithmetic | `PrimitiveArray::value_as_date(i)` | Built into arrow-rs, handles edge cases |
| Timestamp -> NaiveDateTime | Manual unit conversion | `PrimitiveArray::value_as_datetime(i)` | Handles all TimeUnits (s, ms, us, ns) |

**Key insight:** Both arrow-rs and pyo3 provide well-tested conversion paths for temporal types. The main work is wiring them together, not reimplementing the conversions.

## Common Pitfalls

### Pitfall 1: NullArray.is_null() Returns False
**What goes wrong:** Code checks `arr.is_null(row)` expecting `true` for NullArray, but NullArray has no physical null buffer so `is_null()` returns `false`.
**Why it happens:** NullArray stores no buffers at all (not even a null bitmap). The `is_null()` method checks the physical null buffer which doesn't exist.
**How to avoid:** For the `Null` extractor variant, always return `py.None()` unconditionally. Don't check `is_null()`.
**Warning signs:** NullArray tests passing values instead of None.

### Pitfall 2: Timezone String is Arc<str>, Not &str
**What goes wrong:** The `Timestamp(TimeUnit, Option<Arc<str>>)` DataType stores the timezone as `Arc<str>`, not `&str` or `String`.
**Why it happens:** Arrow schema uses `Arc<str>` for string storage to enable zero-copy sharing.
**How to avoid:** Use `tz.as_ref()` to get `&str` when passing to Python's `ZoneInfo` constructor.
**Warning signs:** Compilation error about `Arc<str>` not implementing expected trait.

### Pitfall 3: List Element Extraction Requires Dynamic Dispatch
**What goes wrong:** Trying to use a pre-downcast `ColumnExtractor<'a>` reference for list element extraction, but each row's sub-array is a new `ArrayRef`.
**Why it happens:** `ListArray.value(i)` returns an `ArrayRef` (owned), and the child extractor was prepared against a different array reference.
**How to avoid:** Either: (a) prepare a new temporary extractor per list-row using the child array, or (b) design the element extractor to work with `ArrayRef` + row index, downcasting on each call (acceptable since list elements are small).
**Warning signs:** Lifetime errors or incorrect values from list extraction.

### Pitfall 4: Struct Nullability vs Child Nullability
**What goes wrong:** A struct-level null means the entire nested model should be `None`, but child arrays at that row index may have arbitrary (undefined) values.
**Why it happens:** Arrow spec says: when a struct element is null, child values at that index are undefined.
**How to avoid:** Check `struct_array.is_null(row)` BEFORE accessing any child values. If null, return `py.None()` immediately.
**Warning signs:** Nested model instances with garbage values instead of None for null structs.

### Pitfall 5: Dictionary Key Type Combinatorics
**What goes wrong:** Attempting to match on all key types (Int8, Int16, Int32, Int64, UInt8...) for dictionary arrays creates ~8 variants times all value types.
**Why it happens:** `DictionaryArray<K>` is generic over key type.
**How to avoid:** Use `arrow_cast::cast(dict_array, value_data_type)` to unpack the dictionary to a plain array, then use the normal extractor for the value type.
**Warning signs:** Massive match statement, many test combinations needed.

### Pitfall 6: Chrono Feature Not Enabled on pyo3
**What goes wrong:** `chrono::NaiveDate` has no `IntoPyObject` implementation, compilation fails.
**Why it happens:** The `chrono` feature on pyo3 must be explicitly enabled in Cargo.toml.
**How to avoid:** Add `"chrono"` to pyo3 features: `pyo3 = { version = "0.28", features = ["extension-module", "chrono"] }`.
**Warning signs:** Compilation error: "the trait `IntoPyObject` is not implemented for `NaiveDate`".

### Pitfall 7: Passing Nested Model Class to Rust
**What goes wrong:** The current `convert_record_batch` signature has no way to pass nested Pydantic model classes for struct fields.
**Why it happens:** The original API only needed column indices and field names.
**How to avoid:** Design the API change early. Pass a structured spec from Python that includes nested model class references alongside column indices and field names.
**Warning signs:** Struct tests requiring API refactoring mid-implementation.

## Code Examples

### Example 1: Enabling chrono feature in Cargo.toml

```toml
# Source: pyo3 docs https://pyo3.rs/v0.28.0/features
[dependencies]
pyo3 = { version = "0.28", features = ["extension-module", "chrono"] }
```

### Example 2: Date32 Extraction

```rust
// Source: arrow-rs PrimitiveArray docs + pyo3 chrono feature
use arrow_array::types::Date32Type;
use arrow_array::cast::as_primitive_array;

// In prepare_extractor:
DataType::Date32 => {
    let arr = as_primitive_array::<Date32Type>(col);
    Ok(ColumnExtractor::Date32(arr))
}

// In extract_value:
ColumnExtractor::Date32(arr) => {
    if arr.is_null(row) {
        Ok(py.None())
    } else {
        match arr.value_as_date(row) {
            Some(date) => Ok(date.into_pyobject(py)?.into_any().unbind()),
            None => Ok(py.None()),
        }
    }
}
```

### Example 3: Timestamp with Timezone

```rust
// Source: pyo3 PyDateTime docs, Python zoneinfo module
use pyo3::types::{PyDateTime, PyTzInfo};

// In prepare_extractor (cache ZoneInfo per batch):
DataType::Timestamp(unit, Some(tz_str)) => {
    let zoneinfo = py.import("zoneinfo")?;
    let zi_cls = zoneinfo.getattr("ZoneInfo")?;
    let tz_obj: PyObject = zi_cls.call1((tz_str.as_ref(),))?.unbind();
    // ... store tz_obj in the extractor variant
}

// In extract_value:
// 1. Get raw i64 value
// 2. Convert to datetime components (year, month, day, h, m, s, us)
//    using timestamp_X_to_datetime() from arrow temporal_conversions
// 3. Create PyDateTime with tzinfo
let naive = timestamp_us_to_datetime(raw_value).unwrap();
let dt = PyDateTime::new(
    py,
    naive.year(), naive.month() as u8, naive.day() as u8,
    naive.hour() as u8, naive.minute() as u8, naive.second() as u8,
    (naive.nanosecond() / 1000) as u32,  // TEMP-05: truncate to microseconds
    Some(&tz_obj.bind(py).downcast::<PyTzInfo>()?),
)?;
```

### Example 4: List Extraction

```rust
// Source: arrow-rs GenericListArray docs
use arrow_array::{ListArray, cast::as_list_array};

// In prepare_extractor:
DataType::List(field) => {
    let list_arr = as_list_array(col);
    let child_dt = field.data_type();
    // child_extractor will be used to extract elements from each row's sub-array
    Ok(ColumnExtractor::List(list_arr, child_dt.clone()))
}

// In extract_value:
ColumnExtractor::List(arr, child_dt) => {
    if arr.is_null(row) {
        Ok(py.None())
    } else {
        let child_array = arr.value(row);  // ArrayRef for this row
        let len = child_array.len();
        let child_extractor = prepare_extractor(child_array.as_ref(), child_dt)?;
        let mut items = Vec::with_capacity(len);
        for j in 0..len {
            items.push(child_extractor.extract_value(py, j)?);
        }
        Ok(PyList::new(py, &items)?.into_any().unbind())
    }
}
```

### Example 5: Struct Extraction

```rust
// Source: arrow-rs StructArray docs
use arrow_array::{StructArray, cast::as_struct_array};

// In prepare_extractor (receives nested model class from Python):
DataType::Struct(fields) => {
    let struct_arr = as_struct_array(col);
    let mut child_extractors = Vec::new();
    for (i, field) in fields.iter().enumerate() {
        let child_col = struct_arr.column(i);
        let child_ext = prepare_extractor(child_col.as_ref(), field.data_type())?;
        let field_name = PyString::intern(py, field.name());
        child_extractors.push((field_name.unbind(), child_ext));
    }
    Ok(ColumnExtractor::Struct(struct_arr, child_extractors, nested_model_cls))
}

// In extract_value:
ColumnExtractor::Struct(arr, children, model_cls) => {
    if arr.is_null(row) {
        Ok(py.None())  // null struct -> None for entire nested model
    } else {
        let kwargs = PyDict::new(py);
        for (field_name, extractor) in children.iter() {
            let value = extractor.extract_value(py, row)?;
            kwargs.set_item(field_name.bind(py), value)?;
        }
        Ok(model_cls.bind(py).call_method("model_construct", (), Some(&kwargs))?.unbind())
    }
}
```

### Example 6: Dictionary Unpacking via arrow-cast

```rust
// Source: arrow-cast docs
use arrow_cast::cast;

// In prepare_extractor:
DataType::Dictionary(_, value_type) => {
    // Unpack dictionary-encoded array to plain value array
    let unpacked = cast(col, value_type.as_ref())
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyTypeError, _>(
            format!("Failed to unpack dictionary array: {e}")
        ))?;
    // Now use the standard extractor for the value type
    // NOTE: unpacked is owned -- need to handle lifetime carefully
    // May need to store the owned ArrayRef alongside the extractor
    prepare_extractor(unpacked.as_ref(), value_type.as_ref())
}
```

**Lifetime consideration:** `cast()` returns an owned `ArrayRef`. The `ColumnExtractor` currently borrows with lifetime `'a`. For dictionary arrays, the unpacked array must be stored somewhere with the same lifetime as the batch. Options:
1. Store owned `ArrayRef` in the extractor variant (change `ColumnExtractor` to hold `Arc<dyn Array>` for this case)
2. Pre-unpack dictionary columns in `convert_record_batch` before building extractors
3. Use a `Vec<ArrayRef>` "arena" alongside the extractors to hold owned arrays

Option 2 (pre-unpack) is cleanest -- unpack all dictionary columns to their value types before preparing extractors.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pyo3 `ToPyObject` trait | pyo3 `IntoPyObject` trait | pyo3 0.23+ | Use `into_pyobject(py)?` not `to_object(py)` |
| `PyDate::new_bound()` | `PyDate::new()` | pyo3 0.28 | Bound API is now the default |
| `chrono::Duration` | `chrono::TimeDelta` (alias) | chrono 0.4.35+ | Same type, `TimeDelta` is the preferred name |
| Manual datetime construction | pyo3 chrono feature | pyo3 0.20+ | Automatic IntoPyObject for chrono types |

**Deprecated/outdated:**
- `pyo3::ToPyObject`: Replaced by `IntoPyObject` in pyo3 0.23+
- `chrono::Duration::try_seconds().unwrap()`: Use `try_duration_s_to_duration` (returns Option)

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_convert.py -x -q` |
| Full suite command | `uv run pytest -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TEMP-01 | Date32 -> `datetime.date` | unit | `uv run pytest tests/test_extended_types.py::TestTemporalTypes::test_date32 -x` | Wave 0 |
| TEMP-02 | Timestamp (naive) -> `datetime.datetime` | unit | `uv run pytest tests/test_extended_types.py::TestTemporalTypes::test_timestamp_naive -x` | Wave 0 |
| TEMP-03 | Timestamp (tz-aware) -> `datetime.datetime` | unit | `uv run pytest tests/test_extended_types.py::TestTemporalTypes::test_timestamp_aware -x` | Wave 0 |
| TEMP-04 | Duration -> `datetime.timedelta` | unit | `uv run pytest tests/test_extended_types.py::TestTemporalTypes::test_duration -x` | Wave 0 |
| TEMP-05 | Nanosecond truncation | unit | `uv run pytest tests/test_extended_types.py::TestTemporalTypes::test_nanosecond_truncation -x` | Wave 0 |
| CPLX-01 | List -> `list` | unit | `uv run pytest tests/test_extended_types.py::TestComplexTypes::test_list -x` | Wave 0 |
| CPLX-02 | LargeList -> `list` | unit | `uv run pytest tests/test_extended_types.py::TestComplexTypes::test_large_list -x` | Wave 0 |
| CPLX-03 | Struct -> nested model | unit | `uv run pytest tests/test_extended_types.py::TestComplexTypes::test_struct -x` | Wave 0 |
| CPLX-04 | Dictionary -> value type | unit | `uv run pytest tests/test_extended_types.py::TestComplexTypes::test_dictionary -x` | Wave 0 |
| CPLX-05 | Null type -> None | unit | `uv run pytest tests/test_extended_types.py::TestComplexTypes::test_null_type -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_extended_types.py -x -q`
- **Per wave merge:** `uv run pytest -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_extended_types.py` -- covers TEMP-01 through CPLX-05 (all 10 requirements)
- [ ] Fixtures in `tests/conftest.py` for temporal and complex type batches
- [ ] Existing tests continue to pass after ColumnExtractor refactoring

## Open Questions

1. **Struct field -> nested model class mapping**
   - What we know: The Rust `prepare_extractor` needs the nested Pydantic model class to call `model_construct`. Currently, Python only passes column indices and field names to Rust.
   - What's unclear: The exact API for passing nested model class references from Python to Rust. Options: (a) pass a dict mapping column index to model class, (b) introspect Pydantic field annotations in Python and build a tree structure, (c) pass model classes as part of a structured `field_specs` parameter.
   - Recommendation: Introspect Pydantic model field annotations in `_resolve_columns` to detect `BaseModel` subclass annotations. Build a parallel structure of nested model classes that maps to the column index tree. Pass this to Rust as an additional parameter.

2. **List element extraction lifetime management**
   - What we know: `ListArray.value(i)` returns an owned `ArrayRef`. The current `ColumnExtractor<'a>` borrows.
   - What's unclear: Whether to create a temporary extractor per list-row (slight overhead) or redesign the extraction approach.
   - Recommendation: Create a temporary extractor per list-row. The overhead is negligible since list elements are typically small. This avoids a major refactor of the extractor lifetime model.

3. **Dictionary array lifetime after cast**
   - What we know: `arrow_cast::cast()` returns an owned `ArrayRef`. The extractor borrows.
   - What's unclear: Where to store the owned array so the extractor's borrow remains valid.
   - Recommendation: Pre-unpack dictionary columns in `convert_record_batch` / `convert_table` before building extractors. Store unpacked arrays in a `Vec<ArrayRef>` alongside the batch, then borrow from there.

## Sources

### Primary (HIGH confidence)
- [arrow-rs DataType enum](https://docs.rs/arrow/latest/arrow/datatypes/enum.DataType.html) -- DataType variants for temporal, complex, null types
- [arrow-rs PrimitiveArray](https://docs.rs/arrow/latest/arrow/array/struct.PrimitiveArray.html) -- `value_as_date()`, `value_as_datetime()`, `value_as_duration()` methods
- [arrow-rs GenericListArray](https://arrow.apache.org/rust/arrow_array/array/struct.GenericListArray.html) -- `value(i)`, `offsets()`, `values()` methods
- [arrow-rs StructArray](https://docs.rs/arrow/latest/arrow/array/struct.StructArray.html) -- `column(i)`, `column_by_name()`, struct-level null handling
- [arrow-rs DictionaryArray](https://docs.rs/arrow/latest/arrow/array/struct.DictionaryArray.html) -- `key(i)`, `values()`, `downcast_dict()`
- [arrow-rs NullArray](https://docs.rs/arrow/latest/arrow/array/struct.NullArray.html) -- all-null array, `is_null()` caveat
- [arrow-rs temporal_conversions](https://arrow.apache.org/rust/src/arrow_array/temporal_conversions.rs.html) -- `date32_to_datetime`, `timestamp_X_to_datetime`, duration conversions
- [pyo3 features reference](https://pyo3.rs/v0.28.0/features) -- chrono feature enables NaiveDate/NaiveDateTime/TimeDelta -> PyDate/PyDateTime/PyDelta
- [pyo3 chrono conversions source](https://pyo3.rs/main/doc/src/pyo3/conversions/chrono.rs) -- IntoPyObject implementations for all chrono types
- [pyo3 PyDateTime](https://pyo3.rs/main/doc/pyo3/types/struct.pydatetime) -- `new()` constructor with timezone support
- [pyo3 PyDate](https://docs.rs/pyo3/latest/pyo3/types/struct.PyDate.html) -- `new()` constructor
- [pyo3 PyDelta](https://docs.rs/pyo3/latest/pyo3/types/struct.PyDelta.html) -- `new(days, seconds, microseconds, normalize)` constructor
- [arrow-rs cast module](https://docs.rs/arrow-array/latest/arrow_array/cast/index.html) -- `as_list_array`, `as_struct_array`, `as_dictionary_array`, `as_null_array` helpers

### Secondary (MEDIUM confidence)
- [pyo3 chrono-tz issue #3266](https://github.com/PyO3/pyo3/issues/3266) -- chrono_tz timezone handling limitations
- [pyo3 calling Python from Rust](https://pyo3.rs/v0.28.0/python-from-rust.html) -- `py.import()` pattern for zoneinfo

### Tertiary (LOW confidence)
- Dictionary unpacking via `arrow_cast::cast()` -- inferred from arrow-cast docs, not directly verified with dictionary-to-value casting example

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all crates and versions verified against existing Cargo.toml and docs
- Architecture (temporal types): HIGH -- arrow-rs has built-in `value_as_date/datetime/duration` and pyo3 chrono feature is well-documented
- Architecture (list/struct): MEDIUM -- core APIs verified, but lifetime management for dynamic sub-arrays needs implementation-time validation
- Architecture (dictionary): MEDIUM -- `arrow_cast::cast()` approach is sound but lifetime management of owned unpacked arrays needs care
- Pitfalls: HIGH -- NullArray, timezone caching, struct nullability all confirmed from official docs

**Research date:** 2026-03-22
**Valid until:** 2026-04-22 (30 days -- stable crate ecosystem, no breaking changes expected)
