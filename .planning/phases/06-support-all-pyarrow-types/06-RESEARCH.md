# Phase 6: Support All PyArrow Types - Research

**Researched:** 2026-03-22
**Domain:** Arrow data type coverage -- extending Rust ColumnExtractor to handle every remaining Arrow DataType variant
**Confidence:** HIGH

## Summary

Phase 6 adds support for all remaining Arrow data types not covered in Phases 2-5. The existing codebase handles primitives (Int/UInt/Float32/64, Bool, Utf8/LargeUtf8), temporal types (Date32, Timestamp, Duration), and complex types (List, LargeList, Struct, Dictionary, Null). This phase fills the gaps: Float16, Decimal128/256, Date64, Time32/64, Interval (all 3 variants), Binary/LargeBinary/FixedSizeBinary, Utf8View/BinaryView, FixedSizeList, Map, RunEndEncoded, and Union (sparse + dense).

The implementation follows the established `ColumnExtractor` enum pattern in `extract.rs`. Each new type gets a variant, a `prepare_extractor` match arm, and both `extract_value` (fast path) and `extract_json_value` (validated path) implementations. The approach for RunEndEncoded mirrors the existing Dictionary pre-unpacking pattern via `arrow_cast::cast`. No new Cargo crate dependencies are needed -- all required types are available through `arrow-array` and `arrow-schema` already in `Cargo.toml`, with `arrow-cast` providing the REE unpacking.

**Primary recommendation:** Add one `ColumnExtractor` variant per type family, following the established pattern. Pre-unpack RunEndEncoded columns in `lib.rs::unpack_columns` alongside dictionaries. Use `arrow_cast::cast` for REE-to-flat conversion. Decimal values go through string representation to preserve precision. Intervals become Python tuples of `(months, days, nanos)` with no pyarrow dependency.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXT-FLOAT16 | Float16 -> Python float (upcast to f32) | arrow-array Float16Type provides f16 native values; use `.to_f32()` then `into_pyobject` |
| EXT-DEC128 | Decimal128 -> Python Decimal (via string) | PrimitiveArray::value_as_string on Decimal128Array; pass string to Python `Decimal()` |
| EXT-DEC256 | Decimal256 -> Python Decimal (via string) | Same pattern as Dec128 via value_as_string |
| EXT-DATE64 | Date64 -> Python datetime.datetime | Date64Type stores ms-epoch i64; arrow temporal_conversions::date64_to_datetime gives NaiveDateTime |
| EXT-TIME32 | Time32 (sec/ms) -> Python datetime.time | Time32SecondType/Time32MillisecondType value -> construct PyTime |
| EXT-TIME64 | Time64 (us/ns) -> Python datetime.time | Time64MicrosecondType/Time64NanosecondType value -> construct PyTime |
| EXT-INTERVAL | Interval (all variants) -> tuple[int, int, int] | IntervalMonthDayNanoType.to_parts(); YearMonth is just months; DayTime.to_parts() |
| EXT-BINARY | Binary/LargeBinary -> bytes | GenericByteArray::value(i) returns &[u8]; wrap in PyBytes |
| EXT-FSBINARY | FixedSizeBinary -> bytes | FixedSizeBinaryArray::value(i) returns &[u8]; wrap in PyBytes |
| EXT-UTF8VIEW | Utf8View -> str | StringViewArray::value(i) returns &str; same as Utf8 path |
| EXT-BINVIEW | BinaryView -> bytes | BinaryViewArray::value(i) returns &[u8]; same as Binary path |
| EXT-FSLIST | FixedSizeList -> list | FixedSizeListArray::value(i) returns ArrayRef; same as List path |
| EXT-MAP | Map -> list[tuple[K, V]] | MapArray::value(i) returns StructArray with keys/values; iterate entries |
| EXT-REE | RunEndEncoded -> underlying value type | Pre-unpack via arrow_cast::cast like Dictionary; then existing extractors handle it |
| EXT-UNION | Union (sparse + dense) -> active variant value | UnionArray::type_id(i) + child(type_id) + value_offset for dense; direct index for sparse |
| EXT-DEC32 | Decimal32 -> Python Decimal (via string) | Same pattern as Dec128 via value_as_string (pyarrow 18+ only) |
| EXT-DEC64 | Decimal64 -> Python Decimal (via string) | Same pattern as Dec128 via value_as_string (pyarrow 18+ only) |
</phase_requirements>

## Standard Stack

### Core (already in Cargo.toml -- no new dependencies needed)

| Crate | Version | Purpose | Notes |
|-------|---------|---------|-------|
| arrow-array | 58 | Array types for all data types | Float16Array, Decimal128/256Array, Time32/64Array, IntervalArrays, BinaryArray, MapArray, UnionArray, RunArray, FixedSizeListArray, FixedSizeBinaryArray, StringViewArray, BinaryViewArray |
| arrow-schema | 58 | DataType enum, TimeUnit, IntervalUnit | All new DataType variants matched here |
| arrow-cast | 58 | cast() for RunEndEncoded pre-unpacking | Same pattern as existing Dictionary unpacking |
| pyo3 | 0.28 | Python FFI | PyBytes for binary, PyTuple for intervals, PyTime for time types |
| serde_json | 1 | JSON serialization for validated path | String encoding for decimals, base64 for binary |
| chrono | 0.4 | Temporal helpers | NaiveTime for Time types, date64_to_datetime |

### New Imports Required (from existing crates)

| Import | Crate | Purpose |
|--------|-------|---------|
| `arrow_array::types::{Float16Type, Decimal128Type, Decimal256Type, Decimal32Type, Decimal64Type}` | arrow-array | Decimal and Float16 primitive types |
| `arrow_array::types::{Date64Type, Time32SecondType, Time32MillisecondType, Time64MicrosecondType, Time64NanosecondType}` | arrow-array | Date64 and Time types |
| `arrow_array::types::{IntervalYearMonthType, IntervalDayTimeType, IntervalMonthDayNanoType}` | arrow-array | Interval type decomposition |
| `arrow_array::types::{IntervalMonthDayNano, IntervalDayTime}` | arrow-array (re-exported from arrow-buffer) | Interval value structs |
| `arrow_array::{BinaryArray, LargeBinaryArray, FixedSizeBinaryArray}` | arrow-array | Binary array types |
| `arrow_array::{StringViewArray, BinaryViewArray}` | arrow-array | View array types |
| `arrow_array::{FixedSizeListArray, MapArray, UnionArray}` | arrow-array | Complex array types |
| `arrow_array::RunArray` | arrow-array | RunEndEncoded arrays |
| `arrow_schema::IntervalUnit` | arrow-schema | Interval variant matching |
| `arrow_schema::UnionMode` | arrow-schema | Sparse vs Dense union matching |
| `pyo3::types::{PyBytes, PyTuple, PyTime}` | pyo3 | Python type constructors |

### No New Cargo Dependencies

All types are available from existing crate dependencies. The project already uses `arrow-array = "58"`, `arrow-schema = "58"`, and `arrow-cast = "58"`.

## Architecture Patterns

### Pattern 1: ColumnExtractor Enum Extension

**What:** Add new variants to the existing `ColumnExtractor<'a>` enum in `extract.rs` and corresponding match arms in `prepare_extractor`, `extract_value`, and `extract_json_value`.

**Current structure (to extend):**
```rust
pub enum ColumnExtractor<'a> {
    // ... existing variants ...
    // New variants to add:
    Float16(&'a arrow_array::Float16Array),
    Decimal128(&'a arrow_array::Decimal128Array),
    Decimal256(&'a arrow_array::Decimal256Array),
    Decimal32(&'a arrow_array::Decimal32Array),    // pyarrow 18+ only
    Decimal64(&'a arrow_array::Decimal64Array),    // pyarrow 18+ only
    Date64(&'a arrow_array::Date64Array),
    Time32(&'a dyn Array, TimeUnit),
    Time64(&'a dyn Array, TimeUnit),
    IntervalYearMonth(&'a arrow_array::IntervalYearMonthArray),
    IntervalDayTime(&'a arrow_array::IntervalDayTimeArray),
    IntervalMonthDayNano(&'a arrow_array::IntervalMonthDayNanoArray),
    Binary(&'a arrow_array::BinaryArray),
    LargeBinary(&'a arrow_array::LargeBinaryArray),
    FixedSizeBinary(&'a FixedSizeBinaryArray),
    Utf8View(&'a StringViewArray),
    BinaryView(&'a BinaryViewArray),
    FixedSizeList(&'a FixedSizeListArray, DataType),
    Map(&'a MapArray, DataType, DataType),  // key_dt, value_dt
    Union(&'a UnionArray, Vec<(i8, DataType)>),  // type_id -> DataType mapping
}
```

### Pattern 2: RunEndEncoded Pre-Unpacking (mirrors Dictionary pattern)

**What:** Extend `unpack_columns` in `lib.rs` to also unpack RunEndEncoded columns using `arrow_cast::cast`, exactly as it already does for Dictionary columns.

**Example:**
```rust
fn unpack_columns(
    columns: &[ArrayRef],
    schema: &arrow_schema::SchemaRef,
    col_indices: &[usize],
) -> Result<Vec<ArrayRef>, PyErr> {
    col_indices.iter().map(|&idx| {
        let col = &columns[idx];
        let dt = schema.field(idx).data_type();
        match dt {
            DataType::Dictionary(_, value_type) => {
                arrow_cast::cast(col.as_ref(), value_type.as_ref()).map_err(...)
            }
            DataType::RunEndEncoded(_, value_field) => {
                // Unpack REE to flat array of the value type
                arrow_cast::cast(col.as_ref(), value_field.data_type()).map_err(|e| {
                    PyErr::new::<pyo3::exceptions::PyTypeError, _>(format!(
                        "Failed to unpack run-end encoded array: {e}"
                    ))
                })
            }
            _ => Ok(col.clone()),
        }
    }).collect()
}
```

### Pattern 3: Decimal via String (precision-preserving)

**What:** Convert Decimal128/256/32/64 values to Python `Decimal` objects by going through the string representation. arrow-rs `PrimitiveArray::value_as_string()` handles the scale/precision formatting. Then call Python's `decimal.Decimal(string)`.

**Example (extract_value):**
```rust
ColumnExtractor::Decimal128(arr) => {
    if arr.is_null(row) {
        Ok(py.None())
    } else {
        let s = arr.value_as_string(row);
        let decimal_mod = py.import("decimal")?;
        let decimal_cls = decimal_mod.getattr("Decimal")?;
        Ok(decimal_cls.call1((s,))?.unbind())
    }
}
```

**For extract_json_value (validated path):**
```rust
// Pydantic accepts decimal as JSON string
ColumnExtractor::Decimal128(arr) => {
    if arr.is_null(row) {
        Ok(Value::Null)
    } else {
        Ok(Value::String(arr.value_as_string(row)))
    }
}
```

### Pattern 4: Interval to Python Tuple

**What:** All three interval variants normalize to `tuple[int, int, int]` = `(months, days, nanos)`.

**Example:**
```rust
ColumnExtractor::IntervalMonthDayNano(arr) => {
    if arr.is_null(row) {
        Ok(py.None())
    } else {
        let val = arr.value(row);  // IntervalMonthDayNano struct
        let months = val.months as i64;
        let days = val.days as i64;
        let nanos = val.nanoseconds;
        let tuple = PyTuple::new(py, &[months.into_pyobject(py)?.into_any().unbind(),
                                        days.into_pyobject(py)?.into_any().unbind(),
                                        nanos.into_pyobject(py)?.into_any().unbind()])?;
        Ok(tuple.into_any().unbind())
    }
}

ColumnExtractor::IntervalYearMonth(arr) => {
    if arr.is_null(row) {
        Ok(py.None())
    } else {
        let months = arr.value(row);  // i32 = total months
        let tuple = PyTuple::new(py, &[
            (months as i64).into_pyobject(py)?.into_any().unbind(),
            0i64.into_pyobject(py)?.into_any().unbind(),
            0i64.into_pyobject(py)?.into_any().unbind(),
        ])?;
        Ok(tuple.into_any().unbind())
    }
}

ColumnExtractor::IntervalDayTime(arr) => {
    if arr.is_null(row) {
        Ok(py.None())
    } else {
        let val = arr.value(row);  // IntervalDayTime struct
        let (days, ms) = IntervalDayTimeType::to_parts(val);
        let nanos = ms as i64 * 1_000_000;
        let tuple = PyTuple::new(py, &[
            0i64.into_pyobject(py)?.into_any().unbind(),
            (days as i64).into_pyobject(py)?.into_any().unbind(),
            nanos.into_pyobject(py)?.into_any().unbind(),
        ])?;
        Ok(tuple.into_any().unbind())
    }
}
```

### Pattern 5: Time32/Time64 to Python `datetime.time`

**What:** Construct `PyTime` from arrow time values by decomposing into hours/minutes/seconds/microseconds.

**Example:**
```rust
ColumnExtractor::Time32(arr, TimeUnit::Second) => {
    if arr.is_null(row) {
        Ok(py.None())
    } else {
        let val = as_primitive_array::<Time32SecondType>(arr).value(row); // seconds since midnight
        let h = (val / 3600) as u8;
        let m = ((val % 3600) / 60) as u8;
        let s = (val % 60) as u8;
        let t = PyTime::new(py, h, m, s, 0, None)?;
        Ok(t.into_any().unbind())
    }
}
```

### Pattern 6: Map to `list[tuple[K, V]]`

**What:** `MapArray::value(i)` returns a StructArray with two children (keys, values). Iterate entries, extract key-value pairs, wrap each in a PyTuple.

**Example:**
```rust
ColumnExtractor::Map(arr, key_dt, val_dt) => {
    if arr.is_null(row) {
        Ok(py.None())
    } else {
        let entries = arr.value(row); // StructArray with 2 children
        let keys_arr = entries.column(0);
        let vals_arr = entries.column(1);
        let key_ext = prepare_extractor(py, keys_arr.as_ref(), key_dt, None)?;
        let val_ext = prepare_extractor(py, vals_arr.as_ref(), val_dt, None)?;
        let len = entries.len();
        let mut items: Vec<PyObject> = Vec::with_capacity(len);
        for j in 0..len {
            let k = key_ext.extract_value(py, j)?;
            let v = val_ext.extract_value(py, j)?;
            let pair = PyTuple::new(py, &[k, v])?;
            items.push(pair.into_any().unbind());
        }
        Ok(PyList::new(py, &items)?.into_any().unbind())
    }
}
```

### Pattern 7: Union Value Extraction

**What:** For each row, get `type_id(i)` to find which child array holds the value. For dense unions, use `value_offset(i)` to find the index in the child. For sparse unions, use `i` directly.

**Example:**
```rust
ColumnExtractor::Union(arr, type_map) => {
    if arr.is_null(row) {
        Ok(py.None())
    } else {
        let tid = arr.type_id(row);
        let child = arr.child(tid);
        let child_idx = if arr.offsets().is_some() {
            // Dense: use offset
            arr.value_offset(row) as usize
        } else {
            // Sparse: same logical index
            row
        };
        // Find the DataType for this type_id
        let child_dt = type_map.iter()
            .find(|(id, _)| *id == tid)
            .map(|(_, dt)| dt)
            .unwrap();
        let child_ext = prepare_extractor(py, child.as_ref(), child_dt, None)?;
        child_ext.extract_value(py, child_idx)
    }
}
```

### Pattern 8: Binary -> bytes (fast path) and base64 (validated path)

**For extract_value:** Wrap `&[u8]` in `PyBytes::new(py, bytes)`.

**For extract_json_value:** JSON has no binary type. Use base64 encoding:
```rust
ColumnExtractor::Binary(arr) => {
    if arr.is_null(row) {
        Ok(Value::Null)
    } else {
        use base64::Engine;
        let bytes = arr.value(row);
        let encoded = base64::engine::general_purpose::STANDARD.encode(bytes);
        Ok(Value::String(encoded))
    }
}
```

**NOTE:** This requires adding `base64` crate to Cargo.toml for the validated path. Alternative: Pydantic accepts `bytes` fields from JSON strings -- could use latin-1 encoding or hex. Base64 is the most standard approach. However, Pydantic's `model_validate_json` accepts base64-encoded strings for `bytes` fields by default.

### Anti-Patterns to Avoid

- **Creating Python Decimal from f64:** Never convert Decimal128/256 through floating point. Always go through string to preserve precision.
- **Treating Date64 as Date32:** Date64 stores milliseconds since epoch (returns `datetime.datetime`), Date32 stores days since epoch (returns `datetime.date`). Different Python types.
- **Checking is_null() on NullArray:** Already handled in existing code. NullArray has no validity bitmap, `is_null()` returns false. The `Null` variant unconditionally returns `None`.
- **Trying to extract elements from RunEndEncoded directly:** Pre-unpack via cast, do not try to do per-row `get_physical_index` lookups.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Decimal formatting with scale | Manual i128 division/string formatting | `PrimitiveArray::value_as_string()` | Handles all edge cases (negative scale, leading zeros, precision) |
| RunEndEncoded value access | Per-row `get_physical_index` + value lookup | `arrow_cast::cast` to flat array | One O(n) pass vs O(n log n) binary searches; mirrors existing Dictionary pattern |
| Interval struct decomposition | Manual bit manipulation on i128 | `IntervalMonthDayNanoType::to_parts()` / struct field access | Structs have public fields; `to_parts()` handles DayTime correctly |
| Time decomposition | Manual division of epoch values | Compute h/m/s/us from stored integer | Simple arithmetic, but must match TimeUnit correctly |
| Base64 encoding for binary JSON | Manual encoding | `base64` crate (or avoid: Pydantic handles bytes) | Standard, well-tested |

## Common Pitfalls

### Pitfall 1: Float16 Has No Direct Python Conversion in PyO3
**What goes wrong:** `half::f16` does not implement `IntoPyObject`. Calling `.into_pyobject(py)` on an f16 value fails to compile.
**Why it happens:** PyO3 only implements conversions for f32 and f64, not half-precision floats.
**How to avoid:** Upcast to f32 first: `arr.value(row).to_f32().into_pyobject(py)`.
**Warning signs:** Compilation error on `into_pyobject`.

### Pitfall 2: Decimal Precision Loss via Float
**What goes wrong:** Converting i128 decimal to f64 loses precision for values with >15 significant digits.
**Why it happens:** f64 has only ~15.9 decimal digits of precision; Decimal128 supports up to 38.
**How to avoid:** Always use `value_as_string()` -> Python `Decimal(str)`. Never go through float.
**Warning signs:** Test values with 20+ digits coming back rounded.

### Pitfall 3: Date64 vs Date32 Confusion
**What goes wrong:** Treating Date64 the same as Date32, returning `datetime.date` instead of `datetime.datetime`.
**Why it happens:** Both are "date" types, but Date64 stores millisecond-precision timestamps.
**How to avoid:** Date32 -> `datetime.date`, Date64 -> `datetime.datetime` (with millisecond resolution). Arrow spec: Date64 values are "the elapsed time since UNIX epoch in milliseconds" and "must be divisible by 86,400,000".
**Warning signs:** Time component always 00:00:00 suggests date-only handling instead of datetime.

### Pitfall 4: Time Nanosecond Truncation
**What goes wrong:** Python `datetime.time` only supports microsecond precision. Nanosecond Time64 values lose 3 digits.
**Why it happens:** Python datetime module limitation (same as TEMP-05 for timestamps).
**How to avoid:** Truncate nanoseconds to microseconds: `nanos / 1000`. Document this limitation.
**Warning signs:** Round-trip test with nanosecond values shows inequality.

### Pitfall 5: Interval JSON Serialization
**What goes wrong:** No standard JSON representation for Arrow intervals. Pydantic has no built-in interval type.
**Why it happens:** Intervals are Arrow-specific; JSON and Pydantic don't have a native concept.
**How to avoid:** For the validated path, serialize intervals as JSON arrays `[months, days, nanos]`. The user's Pydantic model would annotate the field as `tuple[int, int, int]`.
**Warning signs:** `model_validate_json` fails with "unexpected type" for interval fields.

### Pitfall 6: Union Null Handling
**What goes wrong:** Union arrays may or may not have a top-level null bitmap. Arrow spec says union null semantics are determined by the child arrays.
**Why it happens:** The Arrow spec states "A union does not have its own validity bitmap buffer." Nulls are in the child arrays.
**How to avoid:** Check `arr.is_null(row)` first (which delegates to child array null checking in arrow-rs), then extract from the active child.
**Warning signs:** Values that should be null coming through as non-null.

### Pitfall 7: MapArray Entry StructArray Has No Null Keys
**What goes wrong:** Trying to handle null map keys. Arrow spec requires map keys to be non-null.
**Why it happens:** MapArray spec guarantees non-null keys, but values can be null.
**How to avoid:** Only check nulls on values, not keys, when extracting map entries.
**Warning signs:** Unnecessary null-checking overhead on keys.

### Pitfall 8: FixedSizeList vs List -- Same Extraction Logic
**What goes wrong:** Writing separate complex extraction logic for FixedSizeList.
**Why it happens:** Assuming FixedSizeList needs different handling.
**How to avoid:** `FixedSizeListArray::value(i)` returns `ArrayRef` just like `ListArray::value(i)`. Reuse the exact same child extraction pattern. The only difference is `as_fixed_size_list_array` for downcasting.
**Warning signs:** Duplicated code between List and FixedSizeList variants.

### Pitfall 9: Binary in Validated Path (base64 dependency)
**What goes wrong:** Pydantic `model_validate_json` with a `bytes` field expects specific encoding in JSON.
**Why it happens:** JSON has no binary type. Pydantic expects base64-encoded strings for bytes fields.
**How to avoid:** Either add `base64` crate or use the `data:` URI format. Test that Pydantic accepts the chosen encoding.
**Warning signs:** `ValidationError` when validating binary data through JSON path.

### Pitfall 10: ListView/LargeListView Existence
**What goes wrong:** Missing support for ListView and LargeListView types that pyarrow 23+ can produce.
**Why it happens:** ListView is a relatively new Arrow type (alternative layout to List). Easy to overlook.
**How to avoid:** Add ListView/LargeListView variants that use the same extraction logic as List/LargeList. `GenericListViewArray::value(i)` returns `ArrayRef` just like ListArray.
**Warning signs:** "Unsupported Arrow type" error when encountering ListView columns.

## Code Examples

### Downcasting Helpers Available (from arrow_array::cast)

```rust
// Already used in codebase:
use arrow_array::cast::{as_boolean_array, as_string_array, as_largestring_array,
    as_primitive_array, as_list_array, as_large_list_array, as_struct_array};

// New ones needed:
use arrow_array::cast::{as_fixed_size_list_array, as_map_array, as_union_array, as_run_array};
// For generic binary: as_generic_binary_array

// For view types, use AsArray trait methods on dyn Array:
// col.as_string_view()  -> &StringViewArray
// col.as_binary_view()  -> &BinaryViewArray
```

### FixedSizeBinary Downcasting

```rust
// FixedSizeBinaryArray has no as_* helper; use downcast_ref
use arrow_array::FixedSizeBinaryArray;
let arr = col.as_any().downcast_ref::<FixedSizeBinaryArray>()
    .expect("expected FixedSizeBinaryArray");
let bytes: &[u8] = arr.value(row);
```

### Decimal Value as String

```rust
use arrow_array::types::{Decimal128Type, Decimal256Type};
// Source: https://docs.rs/arrow-array/latest/arrow_array/array/struct.PrimitiveArray.html

// PrimitiveArray<Decimal128Type> has value_as_string(row) -> String
let decimal_str = arr.value_as_string(row);
// Returns e.g. "123.45" with correct scale
```

### Date64 to Python datetime

```rust
use arrow_array::types::Date64Type;
// Date64 stores ms since epoch; use chrono for conversion
let ms = as_primitive_array::<Date64Type>(arr).value(row);  // i64
let secs = ms / 1000;
let subsec_ms = (ms % 1000) as u32;
let dt = chrono::DateTime::from_timestamp(secs, subsec_ms * 1_000_000)
    .map(|utc| utc.naive_utc());
// Then convert NaiveDateTime to Python via chrono feature
```

### Time32/Time64 to Python time

```rust
use pyo3::types::PyTime;

// Time32Second: value is seconds since midnight (i32)
let total_secs = as_primitive_array::<Time32SecondType>(arr).value(row);
let h = (total_secs / 3600) as u8;
let m = ((total_secs % 3600) / 60) as u8;
let s = (total_secs % 60) as u8;
let t = PyTime::new(py, h, m, s, 0, None)?;

// Time32Millisecond: value is ms since midnight (i32)
let total_ms = as_primitive_array::<Time32MillisecondType>(arr).value(row);
let total_secs = total_ms / 1000;
let us = ((total_ms % 1000) * 1000) as u32;
let h = (total_secs / 3600) as u8;
let m = ((total_secs % 3600) / 60) as u8;
let s = (total_secs % 60) as u8;
let t = PyTime::new(py, h, m, s, us, None)?;

// Time64Microsecond: value is us since midnight (i64)
let total_us = as_primitive_array::<Time64MicrosecondType>(arr).value(row);
let total_secs = (total_us / 1_000_000) as i32;
let us = (total_us % 1_000_000) as u32;
// ... same decomposition ...

// Time64Nanosecond: value is ns since midnight (i64) -- truncate to us
let total_ns = as_primitive_array::<Time64NanosecondType>(arr).value(row);
let total_us = total_ns / 1000;  // Pitfall 4: truncate to microsecond
// ... same as Time64Microsecond from here ...
```

### Union Value Extraction

```rust
use arrow_array::UnionArray;
use arrow_schema::UnionMode;

// Source: https://docs.rs/arrow-array/latest/arrow_array/array/struct.UnionArray.html
let union_arr = as_union_array(col);
let tid = union_arr.type_id(row);
let child = union_arr.child(tid);

// Dense vs Sparse index
let child_idx = match union_arr.offsets() {
    Some(_) => union_arr.value_offset(row) as usize,  // Dense
    None => row,                                        // Sparse
};
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Dictionary columns handled inline | Pre-unpack via arrow_cast::cast in unpack_columns | Phase 4 | Solves lifetime issues; same pattern now applies to REE |
| Only Decimal128/256 | Decimal32/64 added to Arrow spec | Arrow 18.0.0 (2024) | Must handle 4 decimal variants, not 2 |
| No ListView type | ListView/LargeListView added | Arrow 15.0.0+ | Alternative to List; same value extraction API |
| StringView/BinaryView not common | Increasingly used by DataFusion, DuckDB | 2024+ | Must handle view types for interop |

**Deprecated/outdated:**
- Nothing in the current codebase is deprecated. The existing ColumnExtractor pattern is sound and extensible.

## Open Questions

1. **Base64 crate for binary JSON serialization**
   - What we know: Pydantic `model_validate_json` expects base64-encoded strings for `bytes` fields.
   - What's unclear: Whether to add the `base64` crate dependency or use a different encoding. Python's standard base64 could be called from Rust via PyO3 but that defeats the purpose.
   - Recommendation: Add `base64` crate (~zero overhead, widely used). Version 0.22 is current stable.

2. **Decimal32/Decimal64 support scope**
   - What we know: pyarrow 18+ supports these. arrow-rs 58 has Decimal32Type and Decimal64Type.
   - What's unclear: How common these are in practice. Most data uses Decimal128.
   - Recommendation: Include them -- the implementation is identical to Decimal128/256 (just different type parameters). Minimal effort.

3. **ListView/LargeListView inclusion**
   - What we know: pyarrow 23+ can produce these. arrow-rs supports them.
   - What's unclear: Whether users will encounter these in practice.
   - Recommendation: Include them. `GenericListViewArray::value(i)` has the same API as ListArray. Trivial to add.

4. **Union JSON serialization strategy**
   - What we know: Unions produce values of varying types per row.
   - What's unclear: How to serialize a union value in JSON for the validated path when the Pydantic field is a Python `Union[str, int, ...]`.
   - Recommendation: Delegate to the child extractor's `extract_json_value` -- each row's JSON value will be the type of the active variant. Pydantic's `Union` discriminator should handle it.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 8.0 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_convert.py -x` |
| Full suite command | `uv run pytest tests/ -x -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXT-FLOAT16 | Float16 -> float, null handling | unit | `uv run pytest tests/test_extended_types.py::TestFloat16 -x` | Wave 0 |
| EXT-DEC128 | Decimal128 -> Decimal, precision preservation | unit | `uv run pytest tests/test_extended_types.py::TestDecimal128 -x` | Wave 0 |
| EXT-DEC256 | Decimal256 -> Decimal, precision preservation | unit | `uv run pytest tests/test_extended_types.py::TestDecimal256 -x` | Wave 0 |
| EXT-DEC32 | Decimal32 -> Decimal | unit | `uv run pytest tests/test_extended_types.py::TestDecimal32 -x` | Wave 0 |
| EXT-DEC64 | Decimal64 -> Decimal | unit | `uv run pytest tests/test_extended_types.py::TestDecimal64 -x` | Wave 0 |
| EXT-DATE64 | Date64 -> datetime, null handling | unit | `uv run pytest tests/test_extended_types.py::TestDate64 -x` | Wave 0 |
| EXT-TIME32 | Time32 (sec+ms) -> time, null handling | unit | `uv run pytest tests/test_extended_types.py::TestTime32 -x` | Wave 0 |
| EXT-TIME64 | Time64 (us+ns) -> time, null handling, ns truncation | unit | `uv run pytest tests/test_extended_types.py::TestTime64 -x` | Wave 0 |
| EXT-INTERVAL | All 3 interval variants -> tuple, null | unit | `uv run pytest tests/test_extended_types.py::TestInterval -x` | Wave 0 |
| EXT-BINARY | Binary/LargeBinary -> bytes, null | unit | `uv run pytest tests/test_extended_types.py::TestBinary -x` | Wave 0 |
| EXT-FSBINARY | FixedSizeBinary -> bytes, null | unit | `uv run pytest tests/test_extended_types.py::TestFixedSizeBinary -x` | Wave 0 |
| EXT-UTF8VIEW | Utf8View -> str, null | unit | `uv run pytest tests/test_extended_types.py::TestUtf8View -x` | Wave 0 |
| EXT-BINVIEW | BinaryView -> bytes, null | unit | `uv run pytest tests/test_extended_types.py::TestBinaryView -x` | Wave 0 |
| EXT-FSLIST | FixedSizeList -> list, null | unit | `uv run pytest tests/test_extended_types.py::TestFixedSizeList -x` | Wave 0 |
| EXT-MAP | Map -> list[tuple], null | unit | `uv run pytest tests/test_extended_types.py::TestMap -x` | Wave 0 |
| EXT-REE | RunEndEncoded -> unpacked value, null | unit | `uv run pytest tests/test_extended_types.py::TestRunEndEncoded -x` | Wave 0 |
| EXT-UNION | Union (sparse + dense) -> active variant | unit | `uv run pytest tests/test_extended_types.py::TestUnion -x` | Wave 0 |
| ALL-VALIDATED | All new types work with validate=True | integration | `uv run pytest tests/test_extended_types.py::TestValidatedPath -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_extended_types.py -x`
- **Per wave merge:** `uv run pytest tests/ -x -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_extended_types.py` -- covers all EXT-* requirements and validated path
- [ ] `tests/conftest.py` additions -- fixtures for new types (float16_batch, decimal128_batch, time32_batch, interval_batch, binary_batch, map_batch, union_batch, ree_batch, etc.)
- [ ] Possible `base64` crate addition to Cargo.toml for binary JSON serialization

## Sources

### Primary (HIGH confidence)
- [arrow-schema DataType enum](https://docs.rs/arrow-schema/latest/arrow_schema/enum.DataType.html) - complete list of 41 Arrow type variants
- [arrow-array types module](https://docs.rs/arrow-array/latest/arrow_array/types/index.html) - Float16Type, Decimal types, Time types, Interval types
- [arrow-array PrimitiveArray](https://docs.rs/arrow-array/latest/arrow_array/array/struct.PrimitiveArray.html) - value_as_string for Decimal, precision(), scale()
- [arrow-array MapArray](https://docs.rs/arrow-array/latest/arrow_array/array/struct.MapArray.html) - value(i) returns StructArray, keys()/values()
- [arrow-array UnionArray](https://docs.rs/arrow-array/latest/arrow_array/array/struct.UnionArray.html) - type_id(), child(), value_offset(), is_dense()
- [arrow-array RunArray](https://docs.rs/arrow-array/latest/arrow_array/array/struct.RunArray.html) - get_physical_index(), values(), run_ends()
- [arrow-array GenericByteViewArray](https://docs.rs/arrow-array/latest/arrow_array/array/struct.GenericByteViewArray.html) - StringViewArray/BinaryViewArray value access
- [arrow-array FixedSizeListArray](https://docs.rs/arrow-array/latest/arrow_array/array/struct.FixedSizeListArray.html) - value(i) returns ArrayRef
- [arrow-array FixedSizeBinaryArray](https://docs.rs/arrow-array/latest/arrow_array/array/struct.FixedSizeBinaryArray.html) - value(i) returns &[u8]
- [arrow-buffer IntervalMonthDayNano](https://docs.rs/arrow-buffer/latest/arrow_buffer/struct.IntervalMonthDayNano.html) - months/days/nanoseconds fields
- [arrow-array cast module](https://docs.rs/arrow-array/latest/arrow_array/cast/index.html) - as_map_array, as_union_array, as_fixed_size_list_array, as_run_array
- [DecimalType trait](https://docs.rs/arrow/latest/arrow/datatypes/trait.DecimalType.html) - format_decimal, validate_decimal_precision
- [IntervalMonthDayNanoType](https://docs.rs/arrow-array/latest/arrow_array/types/struct.IntervalMonthDayNanoType.html) - to_parts(), make_value()
- [IntervalDayTimeType](https://docs.rs/arrow-array/latest/arrow_array/types/struct.IntervalDayTimeType.html) - to_parts() returns (days, ms)
- [IntervalYearMonthType](https://docs.rs/arrow-array/latest/arrow_array/types/struct.IntervalYearMonthType.html) - to_months(), value is i32

### Secondary (MEDIUM confidence)
- [Pydantic Decimal handling](https://docs.pydantic.dev/latest/api/standard_library_types/) - Decimal validated from string, serialized as string in JSON
- [Pydantic conversion table](https://docs.pydantic.dev/latest/concepts/conversion_table/) - JSON string -> Decimal, base64 -> bytes
- [pyarrow Decimal32Type](https://arrow.apache.org/docs/python/generated/pyarrow.Decimal32Type.html) - available since pyarrow 18.0.0
- [pyarrow MonthDayNanoIntervalArray](https://arrow.apache.org/docs/python/generated/pyarrow.MonthDayNanoIntervalArray.html) - Python representation of intervals
- [arrow-cast RunEndEncoded support](https://www.mail-archive.com/github@arrow.apache.org/msg367127.html) - REE-to-flat casting confirmed

### Tertiary (LOW confidence)
- PyO3 f16 conversion: No official documentation found confirming or denying `half::f16` IntoPyObject support. Assumed not supported based on PyO3 conversion tables listing only f32/f64. Needs validation during implementation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all crates already in Cargo.toml; types verified in docs.rs
- Architecture: HIGH - directly extends established ColumnExtractor pattern with same structure
- Pitfalls: HIGH - verified against Arrow spec and Pydantic behavior; similar patterns already solved in Phases 4-5
- Float16 PyO3 conversion: MEDIUM - need to validate at compile time whether .to_f32() is needed
- Base64 for binary JSON: MEDIUM - need to confirm Pydantic's exact expectation for bytes fields in model_validate_json

**Research date:** 2026-03-22
**Valid until:** 2026-04-22 (stable -- arrow-rs 58 and pyo3 0.28 are current)
