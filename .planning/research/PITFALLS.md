# Pitfalls Research

**Domain:** Rust/PyO3 Arrow-to-Pydantic conversion library (Arrow C Data Interface, pyo3-arrow, Pydantic v2 model construction)
**Researched:** 2026-03-21
**Confidence:** HIGH (verified against official docs, PyO3 user guide, Pydantic API docs, arrow-rs source, and pyo3-arrow docs)

## Critical Pitfalls

### Pitfall 1: Incomplete Pydantic model_construct Replication

**What goes wrong:**
Calling `model_construct` from Python sets four internal attributes on every model instance: `__dict__`, `__pydantic_fields_set__`, `__pydantic_extra__`, and `__pydantic_private__`. If arrowdantic constructs models from Rust by calling `model_construct` as a Python method, there is no issue. But if arrowdantic tries to bypass `model_construct` entirely (e.g., by directly allocating a BaseModel subclass instance and setting `__dict__` via FFI for performance), it must replicate ALL four attributes correctly. Missing `__pydantic_fields_set__` causes serialization failures. Missing `__pydantic_extra__` (must be `None` when `extra != 'allow'`) causes `AttributeError` on access. Missing `__pydantic_private__` causes crashes in any code that reads private attributes.

Additionally, Pydantic's `__setattr__` is overridden for validation-on-assignment. Setting attributes via normal `setattr` will trigger validation even when you intended to bypass it. You must use `PyObject_GenericSetAttr` (via `pyo3::ffi`) or call Python's `object.__setattr__` to bypass Pydantic's custom `__setattr__`.

**Why it happens:**
The temptation to skip the Python-level `model_construct` call for raw FFI attribute setting is strong because calling a Python method per-row is exactly the overhead arrowdantic is designed to eliminate. But `model_construct` is not just "set `__dict__`" -- it has a contract with `model_post_init`, defaults resolution, and internal state that Pydantic's serializers and validators depend on.

**How to avoid:**
Phase 1 should call `model_construct` as a Python method (via `call_method1` or equivalent). This is the safe baseline. Only in an optimization phase should direct `__dict__` setting be explored, and only after writing tests that verify all four attributes are correctly set and that serialization (`model_dump`, `model_dump_json`) works on the resulting instances.

If bypassing `model_construct`: (1) allocate via `cls.__new__(cls)`, (2) set `__dict__` via `PyObject_GenericSetAttr`, (3) set `__pydantic_fields_set__` to a `frozenset` or `set` of field names, (4) set `__pydantic_extra__` to `None` (or a dict if `extra='allow'`), (5) set `__pydantic_private__` to `None` (or call `model_post_init(None)` if the class defines `__pydantic_post_init__`).

**Warning signs:**
- `AttributeError: __pydantic_fields_set__` when serializing constructed models
- `model_dump()` returns empty dict or raises
- Models work in simple tests but fail when passed to FastAPI/other frameworks that call serialization

**Phase to address:**
Phase 1 (foundation): use `model_construct` as a Python call. Optimization phase: investigate direct `__dict__` setting with full attribute contract.

---

### Pitfall 2: Reading Undefined Values at Null Arrow Slots

**What goes wrong:**
Arrow stores nulls as a separate validity bitmap. The value buffer at null indices contains undefined/garbage data. If arrowdantic reads the value buffer at a null index without first checking the validity bitmap, it will produce corrupt Python values -- wrong numbers, invalid UTF-8 strings (causing panics in Rust), or memory safety violations. For string columns, reading a null slot can yield an offset pair pointing to garbage, causing an out-of-bounds read or invalid UTF-8 panic in `std::str::from_utf8`.

**Why it happens:**
The `arrow-rs` array access methods like `value(i)` do NOT check validity -- they return whatever is in the buffer. The separate `is_null(i)` / `is_valid(i)` check must be called explicitly. Developers accustomed to nullable types in other languages (where null access returns None/null automatically) forget that Arrow's physical layout does not enforce this.

**How to avoid:**
Every value extraction path must follow the pattern: `if array.is_valid(i) { extract_value(i) } else { py.None() }`. Never call `array.value(i)` without a preceding validity check. Encapsulate this in a helper trait or function that all column extractors use, so the pattern cannot be accidentally omitted when adding new type support.

For string/binary columns, this is especially critical: the value at a null slot may contain offsets that point outside the buffer, causing undefined behavior or panics.

**Warning signs:**
- Random garbage values appearing in output where None was expected
- `panicked at 'byte index N is out of bounds'` or UTF-8 validation errors
- Tests pass on small data but crash on production data with nulls at specific positions

**Phase to address:**
Phase 1 (foundation): must be correct from the start. Build the null-check abstraction before implementing any type extractors.

---

### Pitfall 3: GIL-Bound Memory Accumulation in the Row Loop

**What goes wrong:**
For each row, arrowdantic creates Python objects (field values, the kwargs dict or `__dict__`, the model instance). Using PyO3's Bound API, each `Bound<'py, T>` smart pointer releases its reference on drop. However, if the entire batch conversion runs in a single `Python::with_gil` scope (which it must, since Python objects cannot exist outside GIL scope), all created Python objects remain alive until the GIL is released. For a batch of 1M rows, this means 1M model instances plus all their field values are simultaneously alive before any can be garbage collected.

This is correct behavior (the caller asked for a list of 1M models), but the intermediate objects -- the per-row `dict` (if using kwargs), per-row string conversions, per-row date/datetime objects -- accumulate within the GIL scope even after they are logically consumed.

**Why it happens:**
Python's garbage collector only runs when the GIL is held and reference counts reach zero. But within a single `with_gil` call, PyO3's Bound API does decrement refcounts on drop. The real risk is creating temporary Python objects (strings, dicts for kwargs) that are logically transient but whose Python-side memory is not freed until the next GC cycle. The bigger concern is the fundamental memory requirement: the output list of N model instances must all exist simultaneously.

**How to avoid:**
1. Use `intern!` for field name strings so they are allocated once and reused across all rows (the project already plans this).
2. For the fast path, avoid creating a Python dict per row entirely. Instead, call `model_construct` with keyword arguments, or even better, directly set `__dict__` using a freshly created dict that becomes owned by the model (no extra copy).
3. Consider offering a chunked/streaming API for very large tables: yield batches of N models at a time rather than materializing the entire table. This can be a later phase.
4. Profile memory usage with batches of 100K+ rows early to establish baselines.

**Warning signs:**
- RSS grows far beyond expected (2-3x the final list size during construction)
- OOM on large batches that should fit in memory
- Significant time spent in Python GC after the conversion completes

**Phase to address:**
Phase 1: use `intern!` for field names. Phase 2 (optimization): profile memory, consider chunked iteration, minimize transient Python objects.

---

### Pitfall 4: Utf8/LargeUtf8 and List/LargeList Type Duplication

**What goes wrong:**
Arrow has paired types: `Utf8`/`LargeUtf8`, `Binary`/`LargeBinary`, `List`/`LargeList`. They are semantically identical but use 32-bit vs 64-bit offsets. If arrowdantic only handles `Utf8` and not `LargeUtf8`, it will fail on data from Polars (which often uses `LargeUtf8`) or any system that produces large string columns. The failure mode is a type mismatch error or a silent skip of the column, breaking the conversion.

**Why it happens:**
Developers implement `Utf8` first, test with pyarrow (which defaults to `Utf8`), and ship without realizing that Polars, DuckDB, and other Arrow producers use the `Large` variants. The arrow-rs `DataType` enum has distinct variants for each, so a `match` arm that handles `DataType::Utf8` will NOT match `DataType::LargeUtf8`.

**How to avoid:**
In the type-mapping logic, always handle both variants together:
```rust
match data_type {
    DataType::Utf8 | DataType::LargeUtf8 => extract_string(array, i),
    DataType::List(_) | DataType::LargeList(_) => extract_list(array, i),
    // ...
}
```
For strings, use `as_string::<i32>()` and `as_string::<i64>()` (or the `GenericStringArray<O>` trait) to handle both with a single code path parameterized by offset type. Similarly for lists, use `GenericListArray<O>`.

Write tests that create data with both `Utf8` and `LargeUtf8` columns and verify identical output.

**Warning signs:**
- "Unsupported Arrow type" errors when processing Polars DataFrames
- Users report "works with pyarrow, fails with Polars" in issues
- Code has separate `StringArray` and `LargeStringArray` branches that drift out of sync

**Phase to address:**
Phase 1 (type support): handle both variants from the start. Do not defer `Large` variants -- they are table stakes for Polars interop.

---

### Pitfall 5: Arrow Timestamp Timezone Semantics Mismatch

**What goes wrong:**
Arrow `Timestamp` has an optional timezone string. When the timezone is `None`, the timestamp is "naive" (no timezone info). When the timezone is set (e.g., `"UTC"`, `"America/New_York"`), the stored value is the UTC instant, and the timezone indicates display/interpretation context. Arrowdantic must convert these to Python `datetime.datetime` objects -- but the mapping is tricky:

- Naive Arrow timestamp -> Python naive `datetime` (no `tzinfo`)
- Timezone-aware Arrow timestamp -> Python aware `datetime` (with `tzinfo`)

If arrowdantic always produces naive datetimes, timezone-aware data loses its timezone. If it always produces aware datetimes, naive data gets incorrectly annotated. If it converts the UTC value to the target timezone, it needs `zoneinfo.ZoneInfo` (Python 3.9+) or `pytz`, adding complexity.

Additionally, Arrow timestamps have variable resolution (seconds, milliseconds, microseconds, nanoseconds). Python `datetime` only supports microsecond resolution. Nanosecond timestamps must be truncated, and this truncation must be documented or configurable to avoid silent precision loss.

**Why it happens:**
Developers test with simple UTC timestamps and miss the naive/aware distinction. The Arrow spec stores the integer value as UTC regardless of timezone, but Python's datetime semantics differ -- a "naive" datetime is not UTC, it is "unspecified timezone." Conflating the two produces incorrect results that are hard to detect in tests.

**How to avoid:**
1. Check `field.data_type()` for the timezone parameter on every `Timestamp` variant.
2. If timezone is `None`: create `datetime.datetime` from the integer using `datetime.datetime.fromtimestamp()` or direct construction, WITHOUT tzinfo.
3. If timezone is `Some(tz)`: create a UTC-aware datetime, then convert to the target timezone using `zoneinfo.ZoneInfo`.
4. For nanosecond resolution: truncate to microseconds (Python's max) and document this behavior. Consider an option to return the raw integer for users who need nanosecond precision.
5. Write test cases for: naive timestamps, UTC timestamps, non-UTC timezone timestamps, nanosecond timestamps.

**Warning signs:**
- Timestamps appear shifted by hours in output (timezone applied incorrectly)
- Naive datetimes unexpectedly have `tzinfo=UTC`
- Nanosecond precision data silently loses trailing digits

**Phase to address:**
Phase 1 (type support): implement correct naive/aware distinction from the start. Nanosecond truncation can be documented but must not silently corrupt data.

---

### Pitfall 6: Using References Instead of Owned Types in pyo3-arrow Function Signatures

**What goes wrong:**
The pyo3-arrow crate requires owned types (`PyRecordBatch`, `PyTable`) in function signatures, not references (`&PyRecordBatch`). Using references prevents pyo3 from invoking the Arrow C Data Interface extraction logic defined in pyo3-arrow. The function will either fail to compile (if the reference type does not implement `FromPyObject`) or will silently use a different extraction path that does not perform the zero-copy FFI handoff.

**Why it happens:**
Rust developers default to borrowing (`&T`) for function parameters to avoid unnecessary moves. But pyo3-arrow's `FromPyObject` implementation is on the owned type -- the extraction from Python involves consuming a PyCapsule (which transfers ownership of the Arrow data), so borrowing is semantically incorrect.

**How to avoid:**
Always use owned types in `#[pyfunction]` signatures:
```rust
#[pyfunction]
fn convert(batch: PyRecordBatch) -> PyResult<...> {
    let record_batch: RecordBatch = batch.into_inner();
    // ...
}
```
Never use `&PyRecordBatch`. Add a clippy lint or code review checklist item for this pattern.

**Warning signs:**
- Compilation errors about missing `FromPyObject` implementations
- Runtime errors about missing `__arrow_c_array__` or `__arrow_c_schema__` methods
- Data appears empty or has wrong schema after extraction

**Phase to address:**
Phase 1 (foundation): get this right in the initial function signatures. This is a one-time decision that is easy to get right if known about.

---

### Pitfall 7: Dictionary-Encoded Arrays Require Double Indirection

**What goes wrong:**
Arrow dictionary arrays store data as indices into a separate values array. A column of type `Dictionary(Int32, Utf8)` does not contain strings directly -- it contains integer indices, and the strings live in a separate values array. If arrowdantic's type matching sees "this column maps to a `str` field" and tries to downcast to `StringArray`, it will fail. The extraction must: (1) downcast to `DictionaryArray<Int32Type>`, (2) get the values array and downcast it to `StringArray`, (3) for each row, get the index from the keys array, then look up the value in the values array.

Additionally, dictionary key types can vary (`Int8`, `Int16`, `Int32`, `Int64`), requiring generic handling or explicit matches for each key type.

**Why it happens:**
Dictionary encoding is an optimization detail that is invisible in the logical schema -- a column of strings may be stored as a dictionary. Developers test with non-dictionary data and discover the issue only when users pass data from Parquet files or analytics engines that aggressively dictionary-encode.

**How to avoid:**
In the type extraction logic, check for `DataType::Dictionary(key_type, value_type)` before checking for the value type directly. When a dictionary is encountered, unwrap it:
```rust
DataType::Dictionary(key_type, value_type) => {
    // dispatch based on value_type, but extract via dictionary indirection
    extract_dictionary(array, key_type, value_type, row_idx)
}
```
Handle all four key types (`Int8Type`, `Int16Type`, `Int32Type`, `Int64Type`). Use arrow-rs's `downcast_dictionary_array!` macro to reduce boilerplate.

Also handle null values: a null in a dictionary array can be a null key (the index itself is null in the validity bitmap) or a null value (the index points to a null entry in the values array). Both must map to Python `None`.

**Warning signs:**
- "Unsupported type: Dictionary(Int32, Utf8)" errors
- Works with CSV-loaded data but fails with Parquet-loaded data
- Incorrect values (reading raw indices as values instead of looking up the dictionary)

**Phase to address:**
Phase 1 (type support): dictionary arrays are common in real-world data. Must be handled in the initial type support phase, not deferred.

---

### Pitfall 8: Struct Array Recursion Depth and Null Propagation

**What goes wrong:**
Arrow `Struct` columns map to nested Pydantic models. Arrowdantic must recursively convert struct fields to nested model instances. Two things go wrong:

1. **Null propagation:** If a struct value is null (the struct's own validity bitmap says null at row i), the entire nested model should be `None`. But the struct's child arrays still have data at that index -- the child values are undefined/garbage at null struct positions. Arrowdantic must check the STRUCT's validity bitmap BEFORE descending into child extraction.

2. **Recursive model_construct:** `model_construct` does not recursively construct nested models from dicts. If arrowdantic builds a flat dict for the outer model and passes nested data as a dict for a nested field, `model_construct` will store the raw dict, not a model instance. Arrowdantic must explicitly construct nested models first, then pass the model instance as the field value to the outer `model_construct`.

**Why it happens:**
The flat-field case (primitive types) works perfectly with a simple validity check + value extraction. The struct case introduces recursion where null semantics are layered: the outer struct can be null (whole nested model is None) OR the outer struct is non-null but an inner field is null (nested model exists but has None fields). Developers test with non-null data first and miss the null-struct case.

**How to avoid:**
1. Before extracting any child fields of a struct, check `struct_array.is_valid(row_idx)`. If invalid, yield `None` for the entire nested model.
2. Build the nested model instance FIRST (recursively), then pass it as a value when constructing the outer model.
3. Test with: null struct values, non-null structs with null inner fields, deeply nested structs (3+ levels).
4. Consider a recursion depth limit to prevent stack overflow on pathological schemas.

**Warning signs:**
- Nested models contain garbage data instead of None
- `TypeError: expected Model, got dict` from downstream code
- Stack overflow on deeply nested schemas

**Phase to address:**
Phase 1 (type support): struct support is listed as a requirement. The null propagation and recursive construction must be correct from the start.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Calling `model_construct` as Python method per row | Correctness, simplicity | ~1 Python call per row, cannot be parallelized | Phase 1 -- necessary for correctness baseline |
| Hardcoding type dispatch via match arms | Simple, readable | New types require code changes, no plugin mechanism | Always acceptable for a conversion library with finite Arrow types |
| Skipping `model_post_init` support | Simpler construction | Users with `model_post_init` hooks get broken models | Never -- must detect and call if `__pydantic_post_init__` exists |
| Python-side schema introspection | Easy access to `model_fields`, aliases, validators | Startup overhead per converter, harder to cache | Phase 1 -- move field introspection to Rust later if profiling shows it matters |
| Truncating nanosecond timestamps silently | Avoids complexity | Users lose precision without knowing | Never silent -- log warning or raise, or document prominently |
| Ignoring Utf8View/BinaryView types | Less code | Fails on newer Arrow data (arrow-rs 52+) | Phase 1 -- these types are new but increasingly common |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| pyo3-arrow `PyRecordBatch` | Using `&PyRecordBatch` reference in signature | Use owned `PyRecordBatch` to trigger PyCapsule extraction |
| pyo3-arrow `PyTable` | Assuming Table is a single batch | Iterate `table.batches()` and process each RecordBatch |
| Pydantic `model_construct` | Assuming it recursively constructs nested models | Manually construct nested models before passing to parent |
| Pydantic `validation_alias` | Using `alias` when `validation_alias` exists | Check `validation_alias` first, fall back to `alias`, then `field_name` |
| Pydantic `populate_by_name=True` | Only matching on alias | When enabled, accept both alias and original field name for column matching |
| pyarrow vs Polars string types | Testing only with pyarrow (`Utf8`) | Always handle both `Utf8` and `LargeUtf8`; Polars uses `LargeUtf8` |
| arrow-rs `DictionaryArray` | Downcasting dictionary column directly to value type | Unwrap dictionary indirection: keys array -> values array lookup |
| Python `datetime` from Arrow `Timestamp` | Ignoring timezone parameter on Timestamp type | Check timezone: None -> naive datetime, Some(tz) -> aware datetime |
| Arrow `Date32` / `Date64` | Using different conversion logic for each | Both map to `datetime.date`; Date32 = days since epoch, Date64 = ms since epoch |
| `serde_json` for validated path | Assuming Pydantic uses serde_json internally | Pydantic v2.5+ uses `jiter`, not serde_json. The JSON must be valid for jiter. `inf`/`NaN` support differs between serde_json and jiter (jiter supports them, serde_json does not by default) |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Per-row Python string allocation for field names | Conversion is 2-3x slower than expected | Use `pyo3::intern!` to intern field name strings; they are reused across all rows | Noticeable at >1K rows, dominant at >100K rows |
| Creating a Python dict per row for kwargs | High allocation pressure, GC overhead | Set `__dict__` directly or use `call_method` with positional kwargs and interned names | >10K rows |
| Calling `Python::with_gil` inside the row loop | Massive overhead from GIL state checking | Acquire GIL once, pass `py` token into the loop | Any batch size -- this is a 10-100x slowdown |
| Not using `Bound` API (using deprecated GIL refs) | Memory accumulates until end of `with_gil` scope | Use `Bound<'py, T>` smart pointers which release on drop | >10K rows (memory); any size (deprecated API warnings) |
| Schema introspection per batch instead of per converter | Repeated Python calls to read model_fields on every batch | Cache schema mapping at `ArrowModelConverter` construction time | >1 batch (multiplied overhead) |
| Releasing/reacquiring GIL per row for allow_threads | Thrashing overhead worse than holding GIL | Hold GIL for entire batch; only use allow_threads for pure-Rust computation blocks (not applicable here since every row produces Python objects) | Any batch size |
| Allocating a new `Vec<PyObject>` per column extraction | Extra allocation + copy | Pre-allocate the output list with known batch length, fill in-place | >100K rows |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Reading Arrow buffer at null-validity indices for string data | Potential out-of-bounds read if offset pair at null index is garbage | Always check validity bitmap before accessing value buffer |
| Trusting Arrow buffer contents without bounds checking after FFI | Buffer could contain invalid offsets/lengths if producer has bugs | Use arrow-rs's safe array accessors which perform bounds checks; avoid raw pointer arithmetic |
| Passing user-controlled data through `model_construct` without awareness | `model_construct` skips ALL validation -- malformed data becomes a valid-looking model | Document clearly that the fast path is for trusted data; provide `validate=True` for untrusted data |
| Using `unsafe` for `PyObject_GenericSetAttr` without proper error handling | Segfault if the object type does not support `__dict__` (e.g., slotted classes) | Check return value of `PyObject_GenericSetAttr`; handle error case |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Opaque error on schema mismatch | User sees "column X not found" with no guidance | Error message should list available Arrow columns AND expected Pydantic fields, highlighting the mismatch |
| Silent column ignore with no logging | User misspells a field alias and data is silently dropped | Log a debug-level message listing ignored columns; consider a `strict=True` mode that errors on unmapped columns |
| No indication of which path (fast/validated) is active | User assumes validation is happening when it is not | Return value or log message should indicate which path was used |
| Failing on first type mismatch instead of collecting all errors | User fixes one field, hits the next error, iterates slowly | Collect all schema mismatches at converter construction time and report them all at once |
| Unclear error when nested model field does not match struct schema | "Unsupported type" error deep in recursion with no field path | Include the full field path in error messages: `"model.address.zip_code: expected str, got Int32"` |

## "Looks Done But Isn't" Checklist

- [ ] **Null handling:** All Arrow types check validity bitmap -- verify with a column that has nulls at first, middle, and last positions
- [ ] **LargeUtf8/LargeList support:** Tested with Polars DataFrames, not just pyarrow -- Polars defaults to Large variants
- [ ] **Dictionary arrays:** Tested with Parquet-loaded data, which often uses dictionary encoding -- verify string and integer dictionaries
- [ ] **Nested struct nulls:** A null struct value returns `None`, not a model with garbage fields -- verify outer null vs inner null distinction
- [ ] **Timestamp timezone:** Naive timestamps have no tzinfo, aware timestamps have correct tzinfo -- verify UTC and non-UTC timezones
- [ ] **Nanosecond precision:** Timestamps with nanosecond resolution are truncated to microseconds -- verify and document
- [ ] **Pydantic alias resolution:** `validation_alias` takes priority over `alias` over `field_name` -- verify with a model that uses all three
- [ ] **`populate_by_name`:** When enabled, columns matching either the alias or the field name work -- verify both paths
- [ ] **model_construct contract:** Constructed models can be serialized with `model_dump()` and `model_dump_json()` without errors
- [ ] **model_post_init:** Models with `model_post_init` hooks have them called -- verify private attributes are initialized
- [ ] **Extra columns:** Arrow columns not matching any Pydantic field are silently ignored -- verify no error is raised
- [ ] **Empty batches:** A RecordBatch with 0 rows returns an empty list, not an error -- verify
- [ ] **Table with multiple batches:** All batches are processed, not just the first -- verify row count matches

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Incomplete model_construct replication | LOW | Switch to calling `model_construct` as Python method; performance cost but correctness guaranteed |
| Reading null slots | MEDIUM | Add validity checks to all extractors; requires touching every type's extraction code |
| GIL memory accumulation | LOW | Add chunked processing option; does not require changing core logic |
| Missing Large variant support | LOW | Add match arms for Large variants alongside existing ones; mechanical change |
| Timestamp timezone errors | MEDIUM | Requires reworking timestamp extraction logic; may need to add zoneinfo dependency |
| Wrong pyo3-arrow signatures | LOW | Change `&` to owned type; single-line fix per function |
| Dictionary array failures | MEDIUM | Add dictionary dispatch layer before value type dispatch; touches type resolution logic |
| Struct null propagation errors | HIGH | Requires restructuring recursive extraction to check struct validity first; may need to change data flow |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Incomplete model_construct replication | Phase 1 (foundation) | Constructed models pass `model_dump()` / `model_dump_json()` round-trip test |
| Reading null slots | Phase 1 (foundation) | Property-based tests with random null patterns across all types |
| GIL memory accumulation | Phase 2 (optimization) | Memory profiling with 1M-row batch shows RSS < 3x final output size |
| Utf8/LargeUtf8 duplication | Phase 1 (type support) | Integration tests with both pyarrow and Polars DataFrames |
| Timestamp timezone semantics | Phase 1 (type support) | Test matrix: naive, UTC, America/New_York, nanosecond resolution |
| pyo3-arrow owned types | Phase 1 (foundation) | Code compiles and accepts pyarrow RecordBatch / Polars DataFrame |
| Dictionary array indirection | Phase 1 (type support) | Tests with Parquet-loaded data that uses dictionary encoding |
| Struct null propagation | Phase 1 (type support) | Tests with null struct values alongside non-null structs with null inner fields |
| serde_json / jiter compatibility | Phase 1 (validated path) | Validated path produces identical models to Python-side `model_validate_json` |
| Per-row string allocation | Phase 2 (optimization) | Benchmark shows field name interning improves throughput by >20% on 100K rows |
| Pydantic alias priority | Phase 1 (schema mapping) | Tests with models using validation_alias, alias, and field_name in combination |

## Sources

- [PyO3 Performance Guide](https://pyo3.rs/v0.22.3/performance) -- intern!, GIL token reuse, reference pool overhead
- [PyO3 Memory Management](https://pyo3.rs/v0.21.2/memory) -- GILPool behavior, Bound API, memory accumulation in loops
- [PyO3 Migration Guide](https://pyo3.rs/main/migration.html) -- Bound API migration from GIL refs
- [pyo3-arrow docs](https://docs.rs/pyo3-arrow/latest/pyo3_arrow/index.html) -- owned type requirement, PyCapsule extraction
- [Pydantic BaseModel API](https://docs.pydantic.dev/latest/api/base_model/) -- model_construct contract, __dict__, __pydantic_fields_set__
- [Pydantic Models Guide](https://docs.pydantic.dev/latest/concepts/models/) -- model_construct does not recurse into nested models
- [Arrow C Data Interface Spec](https://arrow.apache.org/docs/format/CDataInterface.html) -- lifetime management, release callbacks
- [Arrow PyCapsule Interface](https://arrow.apache.org/docs/format/CDataInterface/PyCapsuleInterface.html) -- Python-specific protocol methods
- [Arrow Timestamp Docs](https://arrow.apache.org/docs/python/timestamps.html) -- naive vs aware, timezone handling
- [arrow-rs DictionaryArray](https://arrow.apache.org/rust/arrow/array/struct.DictionaryArray.html) -- key type constraints, value lookup
- [arrow-rs StructArray](https://docs.rs/arrow/latest/arrow/array/struct.StructArray.html) -- child array alignment requirements
- [pydantic-core Issue #1364](https://github.com/pydantic/pydantic-core/issues/1364) -- creating Pydantic models from Rust, current limitations
- [PyO3 Discussion #2321](https://github.com/PyO3/pyo3/discussions/2321) -- PyObject_GenericSetAttr for bypassing __setattr__
- [arrow-rs LargeUtf8 Issue #3228](https://github.com/apache/arrow-rs/issues/3228) -- Utf8 vs LargeUtf8 documentation gaps
- [PyO3 Memory Leak Issue #2853](https://github.com/PyO3/pyo3/issues/2853) -- memory leak patterns when creating objects in Rust
- [PyO3 Building & Distribution](https://pyo3.rs/v0.28.0/building-and-distribution.html) -- abi3, maturin, cross-platform concerns
- [PyO3/pyo3 Issue #5505](https://github.com/PyO3/pyo3/issues/5505) -- Python 3.14 forward compatibility with abi3

---
*Pitfalls research for: Rust/PyO3 Arrow-to-Pydantic conversion library*
*Researched: 2026-03-21*
