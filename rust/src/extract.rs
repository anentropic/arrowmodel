use arrow_array::{
    cast::{
        as_boolean_array, as_largestring_array, as_primitive_array, as_string_array,
        as_list_array, as_large_list_array, as_struct_array,
    },
    types::{
        Date32Type, DurationMicrosecondType, DurationMillisecondType, DurationNanosecondType,
        DurationSecondType, Float32Type, Float64Type, Int16Type, Int32Type, Int64Type, Int8Type,
        TimestampMicrosecondType, TimestampMillisecondType, TimestampNanosecondType,
        TimestampSecondType, UInt16Type, UInt32Type, UInt64Type, UInt8Type,
    },
    Array, BooleanArray, LargeStringArray, ListArray, LargeListArray, StringArray, StructArray,
};
use arrow_schema::{DataType, TimeUnit};
use pyo3::prelude::*;
use pyo3::types::{PyDateTime, PyDict, PyList, PyString, PyTzInfo};
use serde_json::{Map, Number, Value};

type PyObject = Py<PyAny>;

/// Column extractor enum -- one variant per supported Arrow type.
/// Each variant holds a reference to the pre-downcast typed array,
/// avoiding dynamic dispatch inside the row loop.
pub enum ColumnExtractor<'a> {
    Int8(&'a arrow_array::Int8Array),
    Int16(&'a arrow_array::Int16Array),
    Int32(&'a arrow_array::Int32Array),
    Int64(&'a arrow_array::Int64Array),
    UInt8(&'a arrow_array::UInt8Array),
    UInt16(&'a arrow_array::UInt16Array),
    UInt32(&'a arrow_array::UInt32Array),
    UInt64(&'a arrow_array::UInt64Array),
    Float32(&'a arrow_array::Float32Array),
    Float64(&'a arrow_array::Float64Array),
    Boolean(&'a BooleanArray),
    Utf8(&'a StringArray),
    LargeUtf8(&'a LargeStringArray),
    // Temporal types
    Date32(&'a arrow_array::Date32Array),
    TimestampNaive(&'a dyn Array, TimeUnit),
    TimestampAware(&'a dyn Array, TimeUnit, PyObject),
    Duration(&'a dyn Array, TimeUnit),
    // Complex types
    /// List element extraction: stores child DataType to create temporary
    /// extractors per row's sub-array (ListArray.value(i) returns new ArrayRef).
    List(&'a ListArray, DataType),
    /// LargeList: identical to List but uses i64 offsets.
    LargeList(&'a LargeListArray, DataType),
    /// Struct: child extractors (pre-built), interned field names, nested model class.
    Struct(
        &'a StructArray,
        Vec<(Py<PyString>, ColumnExtractor<'a>)>,
        PyObject, // nested Pydantic model class
    ),
    // Null type -- always returns None
    Null,
}

/// Downcast an Arrow column to a concrete typed array once, before the row loop.
/// Returns a ColumnExtractor variant for efficient per-row value extraction.
///
/// Dictionary columns should be pre-unpacked before calling this function.
/// See `unpack_dictionary_columns` in lib.rs.
///
/// `nested_model` is `Some(model_cls)` when the column is a Struct that should
/// produce a nested Pydantic model instance. `None` for all other column types.
pub fn prepare_extractor<'a>(
    py: Python<'_>,
    col: &'a dyn Array,
    data_type: &DataType,
    nested_model: Option<&PyObject>,
) -> PyResult<ColumnExtractor<'a>> {
    match data_type {
        DataType::Int8 => Ok(ColumnExtractor::Int8(as_primitive_array::<Int8Type>(col))),
        DataType::Int16 => Ok(ColumnExtractor::Int16(as_primitive_array::<Int16Type>(col))),
        DataType::Int32 => Ok(ColumnExtractor::Int32(as_primitive_array::<Int32Type>(col))),
        DataType::Int64 => Ok(ColumnExtractor::Int64(as_primitive_array::<Int64Type>(col))),
        DataType::UInt8 => Ok(ColumnExtractor::UInt8(as_primitive_array::<UInt8Type>(col))),
        DataType::UInt16 => Ok(ColumnExtractor::UInt16(as_primitive_array::<UInt16Type>(col))),
        DataType::UInt32 => Ok(ColumnExtractor::UInt32(as_primitive_array::<UInt32Type>(col))),
        DataType::UInt64 => Ok(ColumnExtractor::UInt64(as_primitive_array::<UInt64Type>(col))),
        DataType::Float32 => Ok(ColumnExtractor::Float32(as_primitive_array::<Float32Type>(col))),
        DataType::Float64 => Ok(ColumnExtractor::Float64(as_primitive_array::<Float64Type>(col))),
        DataType::Boolean => Ok(ColumnExtractor::Boolean(as_boolean_array(col))),
        DataType::Utf8 => Ok(ColumnExtractor::Utf8(as_string_array(col))),
        DataType::LargeUtf8 => Ok(ColumnExtractor::LargeUtf8(as_largestring_array(col))),
        DataType::Date32 => Ok(ColumnExtractor::Date32(
            as_primitive_array::<Date32Type>(col),
        )),
        DataType::Timestamp(unit, None) => {
            Ok(ColumnExtractor::TimestampNaive(col, *unit))
        }
        DataType::Timestamp(unit, Some(tz_str)) => {
            let zoneinfo = py.import("zoneinfo")?;
            let zi_cls = zoneinfo.getattr("ZoneInfo")?;
            let tz_obj: PyObject = zi_cls.call1((tz_str.as_ref(),))?.unbind();
            Ok(ColumnExtractor::TimestampAware(col, *unit, tz_obj))
        }
        DataType::Duration(unit) => Ok(ColumnExtractor::Duration(col, *unit)),
        DataType::List(field) => {
            let arr = as_list_array(col);
            Ok(ColumnExtractor::List(arr, field.data_type().clone()))
        }
        DataType::LargeList(field) => {
            let arr = as_large_list_array(col);
            Ok(ColumnExtractor::LargeList(arr, field.data_type().clone()))
        }
        DataType::Struct(fields) => {
            let model_cls = nested_model
                .ok_or_else(|| {
                    PyErr::new::<pyo3::exceptions::PyTypeError, _>(
                        "Struct column requires a nested Pydantic model class",
                    )
                })?
                .clone_ref(py);
            let struct_arr = as_struct_array(col);
            let mut children: Vec<(Py<PyString>, ColumnExtractor<'a>)> =
                Vec::with_capacity(fields.len());

            // Introspect the nested model class to find child struct model classes.
            // Import the _get_nested_model helper from Python.
            let arrowdantic = py.import("arrowdantic")?;
            let get_nested_model_fn = arrowdantic.getattr("_get_nested_model")?;
            let model_fields = model_cls.bind(py).getattr("model_fields")?;

            for (i, field) in fields.iter().enumerate() {
                let child_col = struct_arr.column(i);
                let field_name_str = field.name();

                // Look up the child's nested model class from the Pydantic model
                let child_nested_model: Option<PyObject> =
                    if let Ok(field_info) = model_fields.get_item(field_name_str) {
                        let annotation = field_info.getattr("annotation")?;
                        let result = get_nested_model_fn.call1((annotation,))?;
                        if result.is_none() {
                            None
                        } else {
                            Some(result.unbind())
                        }
                    } else {
                        None
                    };

                let child_ext = prepare_extractor(
                    py,
                    child_col.as_ref(),
                    field.data_type(),
                    child_nested_model.as_ref(),
                )?;
                let field_name = PyString::intern(py, field_name_str).unbind();
                children.push((field_name, child_ext));
            }
            Ok(ColumnExtractor::Struct(struct_arr, children, model_cls))
        }
        DataType::Null => Ok(ColumnExtractor::Null),
        _ => Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(format!(
            "Unsupported Arrow type: {data_type:?}"
        ))),
    }
}

impl<'a> ColumnExtractor<'a> {
    /// Extract the value at `row` as a PyObject.
    /// Checks is_null(row) BEFORE accessing value(row) per NULL-01, NULL-03.
    /// Returns py.None() for null values per NULL-02.
    pub fn extract_value(&self, py: Python<'_>, row: usize) -> PyResult<PyObject> {
        match self {
            ColumnExtractor::Int8(arr) => {
                if arr.is_null(row) {
                    Ok(py.None())
                } else {
                    Ok(arr.value(row).into_pyobject(py)?.into_any().unbind())
                }
            }
            ColumnExtractor::Int16(arr) => {
                if arr.is_null(row) {
                    Ok(py.None())
                } else {
                    Ok(arr.value(row).into_pyobject(py)?.into_any().unbind())
                }
            }
            ColumnExtractor::Int32(arr) => {
                if arr.is_null(row) {
                    Ok(py.None())
                } else {
                    Ok(arr.value(row).into_pyobject(py)?.into_any().unbind())
                }
            }
            ColumnExtractor::Int64(arr) => {
                if arr.is_null(row) {
                    Ok(py.None())
                } else {
                    Ok(arr.value(row).into_pyobject(py)?.into_any().unbind())
                }
            }
            ColumnExtractor::UInt8(arr) => {
                if arr.is_null(row) {
                    Ok(py.None())
                } else {
                    Ok(arr.value(row).into_pyobject(py)?.into_any().unbind())
                }
            }
            ColumnExtractor::UInt16(arr) => {
                if arr.is_null(row) {
                    Ok(py.None())
                } else {
                    Ok(arr.value(row).into_pyobject(py)?.into_any().unbind())
                }
            }
            ColumnExtractor::UInt32(arr) => {
                if arr.is_null(row) {
                    Ok(py.None())
                } else {
                    Ok(arr.value(row).into_pyobject(py)?.into_any().unbind())
                }
            }
            ColumnExtractor::UInt64(arr) => {
                if arr.is_null(row) {
                    Ok(py.None())
                } else {
                    Ok(arr.value(row).into_pyobject(py)?.into_any().unbind())
                }
            }
            ColumnExtractor::Float32(arr) => {
                if arr.is_null(row) {
                    Ok(py.None())
                } else {
                    Ok(arr.value(row).into_pyobject(py)?.into_any().unbind())
                }
            }
            ColumnExtractor::Float64(arr) => {
                if arr.is_null(row) {
                    Ok(py.None())
                } else {
                    Ok(arr.value(row).into_pyobject(py)?.into_any().unbind())
                }
            }
            ColumnExtractor::Boolean(arr) => {
                if arr.is_null(row) {
                    Ok(py.None())
                } else {
                    let val = arr.value(row);
                    Ok(val.into_pyobject(py)?.to_owned().into_any().unbind())
                }
            }
            ColumnExtractor::Utf8(arr) => {
                if arr.is_null(row) {
                    Ok(py.None())
                } else {
                    Ok(PyString::new(py, arr.value(row)).into_any().unbind())
                }
            }
            ColumnExtractor::LargeUtf8(arr) => {
                if arr.is_null(row) {
                    Ok(py.None())
                } else {
                    Ok(PyString::new(py, arr.value(row)).into_any().unbind())
                }
            }
            // --- Temporal types ---
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
            ColumnExtractor::TimestampNaive(arr, unit) => {
                if arr.is_null(row) {
                    Ok(py.None())
                } else {
                    extract_naive_datetime(py, *arr, row, *unit)
                }
            }
            ColumnExtractor::TimestampAware(arr, unit, tz_obj) => {
                if arr.is_null(row) {
                    Ok(py.None())
                } else {
                    extract_aware_datetime(py, *arr, row, *unit, tz_obj)
                }
            }
            ColumnExtractor::Duration(arr, unit) => {
                if arr.is_null(row) {
                    Ok(py.None())
                } else {
                    extract_duration(py, *arr, row, *unit)
                }
            }
            // --- Complex types ---
            ColumnExtractor::List(arr, child_dt) => {
                if arr.is_null(row) {
                    Ok(py.None())
                } else {
                    let child_array = arr.value(row); // ArrayRef for this row's list
                    let len = child_array.len();
                    let child_ext =
                        prepare_extractor(py, child_array.as_ref(), child_dt, None)?;
                    let mut items: Vec<PyObject> = Vec::with_capacity(len);
                    for j in 0..len {
                        items.push(child_ext.extract_value(py, j)?);
                    }
                    Ok(PyList::new(py, &items)?.into_any().unbind())
                }
            }
            ColumnExtractor::LargeList(arr, child_dt) => {
                if arr.is_null(row) {
                    Ok(py.None())
                } else {
                    let child_array = arr.value(row);
                    let len = child_array.len();
                    let child_ext =
                        prepare_extractor(py, child_array.as_ref(), child_dt, None)?;
                    let mut items: Vec<PyObject> = Vec::with_capacity(len);
                    for j in 0..len {
                        items.push(child_ext.extract_value(py, j)?);
                    }
                    Ok(PyList::new(py, &items)?.into_any().unbind())
                }
            }
            ColumnExtractor::Struct(arr, children, model_cls) => {
                if arr.is_null(row) {
                    Ok(py.None()) // null struct -> None for entire nested model (Pitfall 4)
                } else {
                    let kwargs = PyDict::new(py);
                    for (field_name, extractor) in children.iter() {
                        let value = extractor.extract_value(py, row)?;
                        kwargs.set_item(field_name.bind(py), value)?;
                    }
                    Ok(model_cls
                        .bind(py)
                        .call_method("model_construct", (), Some(&kwargs))?
                        .unbind())
                }
            }
            // Null type -- always returns None unconditionally.
            // Do NOT check is_null() -- NullArray has no physical null buffer
            // so is_null() returns false (Pitfall 1 from research).
            ColumnExtractor::Null => Ok(py.None()),
        }
    }

    /// Extract the value at `row` as a serde_json::Value for JSON serialization.
    /// Used by the validated path (validate=True) to build JSON bytes per row.
    /// Checks is_null(row) BEFORE accessing value(row).
    /// Returns Value::Null for null values (key included, not omitted -- Pitfall 7).
    pub fn extract_json_value(&self, py: Python<'_>, row: usize) -> Result<Value, PyErr> {
        match self {
            ColumnExtractor::Int8(arr) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    Ok(Value::Number(Number::from(arr.value(row))))
                }
            }
            ColumnExtractor::Int16(arr) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    Ok(Value::Number(Number::from(arr.value(row))))
                }
            }
            ColumnExtractor::Int32(arr) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    Ok(Value::Number(Number::from(arr.value(row))))
                }
            }
            ColumnExtractor::Int64(arr) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    Ok(Value::Number(Number::from(arr.value(row))))
                }
            }
            ColumnExtractor::UInt8(arr) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    Ok(Value::Number(Number::from(arr.value(row))))
                }
            }
            ColumnExtractor::UInt16(arr) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    Ok(Value::Number(Number::from(arr.value(row))))
                }
            }
            ColumnExtractor::UInt32(arr) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    Ok(Value::Number(Number::from(arr.value(row))))
                }
            }
            ColumnExtractor::UInt64(arr) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    Ok(Value::Number(Number::from(arr.value(row))))
                }
            }
            // Pitfall 5: Float NaN/Infinity -> Value::Null (not serde_json error)
            ColumnExtractor::Float32(arr) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    let v = arr.value(row);
                    if v.is_nan() || v.is_infinite() {
                        Ok(Value::Null)
                    } else {
                        Ok(Number::from_f64(v as f64)
                            .map(Value::Number)
                            .unwrap_or(Value::Null))
                    }
                }
            }
            ColumnExtractor::Float64(arr) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    let v = arr.value(row);
                    if v.is_nan() || v.is_infinite() {
                        Ok(Value::Null)
                    } else {
                        Ok(Number::from_f64(v)
                            .map(Value::Number)
                            .unwrap_or(Value::Null))
                    }
                }
            }
            ColumnExtractor::Boolean(arr) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    Ok(Value::Bool(arr.value(row)))
                }
            }
            ColumnExtractor::Utf8(arr) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    Ok(Value::String(arr.value(row).to_owned()))
                }
            }
            ColumnExtractor::LargeUtf8(arr) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    Ok(Value::String(arr.value(row).to_owned()))
                }
            }
            // --- Temporal types: format as ISO 8601 strings for Pydantic ---
            ColumnExtractor::Date32(arr) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    match arr.value_as_date(row) {
                        Some(d) => {
                            Ok(Value::String(d.format("%Y-%m-%d").to_string()))
                        }
                        None => Ok(Value::Null),
                    }
                }
            }
            ColumnExtractor::TimestampNaive(arr, unit) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    match extract_naive_dt_value(*arr, row, *unit) {
                        Some(dt) => {
                            Ok(Value::String(
                                dt.format("%Y-%m-%dT%H:%M:%S%.f").to_string(),
                            ))
                        }
                        None => Ok(Value::Null),
                    }
                }
            }
            ColumnExtractor::TimestampAware(arr, unit, _tz_obj) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    // Arrow timestamps with tz are stored in UTC.
                    // Append +00:00 so Pydantic produces tz-aware datetime.
                    match extract_naive_dt_value(*arr, row, *unit) {
                        Some(dt) => {
                            let s = dt.format("%Y-%m-%dT%H:%M:%S%.f").to_string();
                            Ok(Value::String(format!("{s}+00:00")))
                        }
                        None => Ok(Value::Null),
                    }
                }
            }
            ColumnExtractor::Duration(arr, unit) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    match extract_duration_value(*arr, row, *unit) {
                        Some(td) => Ok(Value::String(timedelta_to_iso8601(&td))),
                        None => Ok(Value::Null),
                    }
                }
            }
            // --- Complex types ---
            ColumnExtractor::List(arr, child_dt) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    let child_array = arr.value(row);
                    let len = child_array.len();
                    let child_ext =
                        prepare_extractor(py, child_array.as_ref(), child_dt, None)?;
                    let mut items: Vec<Value> = Vec::with_capacity(len);
                    for j in 0..len {
                        items.push(child_ext.extract_json_value(py, j)?);
                    }
                    Ok(Value::Array(items))
                }
            }
            ColumnExtractor::LargeList(arr, child_dt) => {
                if arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    let child_array = arr.value(row);
                    let len = child_array.len();
                    let child_ext =
                        prepare_extractor(py, child_array.as_ref(), child_dt, None)?;
                    let mut items: Vec<Value> = Vec::with_capacity(len);
                    for j in 0..len {
                        items.push(child_ext.extract_json_value(py, j)?);
                    }
                    Ok(Value::Array(items))
                }
            }
            ColumnExtractor::Struct(_arr, children, _model_cls) => {
                if _arr.is_null(row) {
                    Ok(Value::Null)
                } else {
                    let mut map = Map::new();
                    for (field_name, extractor) in children.iter() {
                        let key = field_name.bind(py).to_str()?.to_owned();
                        let value = extractor.extract_json_value(py, row)?;
                        map.insert(key, value);
                    }
                    Ok(Value::Object(map))
                }
            }
            ColumnExtractor::Null => Ok(Value::Null),
        }
    }
}

/// Extract a naive datetime from a timestamp column at the given row.
/// Handles all TimeUnit variants (Second, Millisecond, Microsecond, Nanosecond).
/// Nanosecond precision truncates to microsecond automatically via chrono.
fn extract_naive_datetime(
    py: Python<'_>,
    arr: &dyn Array,
    row: usize,
    unit: TimeUnit,
) -> PyResult<PyObject> {
    let naive_dt = match unit {
        TimeUnit::Second => {
            as_primitive_array::<TimestampSecondType>(arr).value_as_datetime(row)
        }
        TimeUnit::Millisecond => {
            as_primitive_array::<TimestampMillisecondType>(arr).value_as_datetime(row)
        }
        TimeUnit::Microsecond => {
            as_primitive_array::<TimestampMicrosecondType>(arr).value_as_datetime(row)
        }
        TimeUnit::Nanosecond => {
            as_primitive_array::<TimestampNanosecondType>(arr).value_as_datetime(row)
        }
    };
    match naive_dt {
        Some(dt) => Ok(dt.into_pyobject(py)?.into_any().unbind()),
        None => Ok(py.None()),
    }
}

/// Extract a timezone-aware datetime from a timestamp column at the given row.
/// Constructs a PyDateTime with the cached ZoneInfo tzinfo object.
fn extract_aware_datetime(
    py: Python<'_>,
    arr: &dyn Array,
    row: usize,
    unit: TimeUnit,
    tz_obj: &PyObject,
) -> PyResult<PyObject> {
    let naive_dt = match unit {
        TimeUnit::Second => {
            as_primitive_array::<TimestampSecondType>(arr).value_as_datetime(row)
        }
        TimeUnit::Millisecond => {
            as_primitive_array::<TimestampMillisecondType>(arr).value_as_datetime(row)
        }
        TimeUnit::Microsecond => {
            as_primitive_array::<TimestampMicrosecondType>(arr).value_as_datetime(row)
        }
        TimeUnit::Nanosecond => {
            as_primitive_array::<TimestampNanosecondType>(arr).value_as_datetime(row)
        }
    };
    match naive_dt {
        Some(dt) => {
            use chrono::Datelike;
            use chrono::Timelike;
            let tz_bound = tz_obj.bind(py);
            let tz_info: &Bound<'_, PyTzInfo> = tz_bound.cast::<PyTzInfo>()?;
            let py_dt = PyDateTime::new(
                py,
                dt.year(),
                dt.month() as u8,
                dt.day() as u8,
                dt.hour() as u8,
                dt.minute() as u8,
                dt.second() as u8,
                (dt.nanosecond() / 1000) as u32, // TEMP-05: truncate ns to us
                Some(tz_info),
            )?;
            Ok(py_dt.into_any().unbind())
        }
        None => Ok(py.None()),
    }
}

/// Extract a duration from a duration column at the given row.
/// Handles all TimeUnit variants via chrono::TimeDelta.
fn extract_duration(
    py: Python<'_>,
    arr: &dyn Array,
    row: usize,
    unit: TimeUnit,
) -> PyResult<PyObject> {
    let td = match unit {
        TimeUnit::Second => {
            as_primitive_array::<DurationSecondType>(arr).value_as_duration(row)
        }
        TimeUnit::Millisecond => {
            as_primitive_array::<DurationMillisecondType>(arr).value_as_duration(row)
        }
        TimeUnit::Microsecond => {
            as_primitive_array::<DurationMicrosecondType>(arr).value_as_duration(row)
        }
        TimeUnit::Nanosecond => {
            as_primitive_array::<DurationNanosecondType>(arr).value_as_duration(row)
        }
    };
    match td {
        Some(delta) => Ok(delta.into_pyobject(py)?.into_any().unbind()),
        None => Ok(py.None()),
    }
}

/// Convert a chrono::TimeDelta to ISO 8601 duration string (PxDTxHxMxS).
/// Pydantic's model_validate_json expects this format for timedelta fields.
fn timedelta_to_iso8601(td: &chrono::TimeDelta) -> String {
    let total_secs = td.num_seconds();
    let is_negative = total_secs < 0;
    let total_secs = total_secs.unsigned_abs();

    let days = total_secs / 86400;
    let remaining = total_secs % 86400;
    let hours = remaining / 3600;
    let remaining = remaining % 3600;
    let minutes = remaining / 60;
    let seconds = remaining % 60;

    // Include subsecond microseconds from the TimeDelta
    let subsec_nanos = td.subsec_nanos().unsigned_abs();
    let micros = subsec_nanos / 1000;

    let mut result = String::new();
    if is_negative {
        result.push('-');
    }
    result.push('P');
    if days > 0 {
        result.push_str(&format!("{days}D"));
    }
    // Always include T section if there are time components
    if hours > 0 || minutes > 0 || seconds > 0 || micros > 0 || days == 0 {
        result.push('T');
        if hours > 0 {
            result.push_str(&format!("{hours}H"));
        }
        if minutes > 0 {
            result.push_str(&format!("{minutes}M"));
        }
        if micros > 0 {
            result.push_str(&format!("{seconds}.{micros:06}S"));
        } else if seconds > 0 || (hours == 0 && minutes == 0 && days == 0) {
            result.push_str(&format!("{seconds}S"));
        }
    }
    result
}

/// Extract the naive datetime for a given timestamp row, returning a chrono::NaiveDateTime.
fn extract_naive_dt_value(
    arr: &dyn Array,
    row: usize,
    unit: TimeUnit,
) -> Option<chrono::NaiveDateTime> {
    match unit {
        TimeUnit::Second => {
            as_primitive_array::<TimestampSecondType>(arr).value_as_datetime(row)
        }
        TimeUnit::Millisecond => {
            as_primitive_array::<TimestampMillisecondType>(arr).value_as_datetime(row)
        }
        TimeUnit::Microsecond => {
            as_primitive_array::<TimestampMicrosecondType>(arr).value_as_datetime(row)
        }
        TimeUnit::Nanosecond => {
            as_primitive_array::<TimestampNanosecondType>(arr).value_as_datetime(row)
        }
    }
}

/// Extract a duration value as chrono::TimeDelta for a given row.
fn extract_duration_value(
    arr: &dyn Array,
    row: usize,
    unit: TimeUnit,
) -> Option<chrono::TimeDelta> {
    match unit {
        TimeUnit::Second => {
            as_primitive_array::<DurationSecondType>(arr).value_as_duration(row)
        }
        TimeUnit::Millisecond => {
            as_primitive_array::<DurationMillisecondType>(arr).value_as_duration(row)
        }
        TimeUnit::Microsecond => {
            as_primitive_array::<DurationMicrosecondType>(arr).value_as_duration(row)
        }
        TimeUnit::Nanosecond => {
            as_primitive_array::<DurationNanosecondType>(arr).value_as_duration(row)
        }
    }
}
