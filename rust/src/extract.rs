use arrow_array::{
    cast::{as_boolean_array, as_largestring_array, as_primitive_array, as_string_array},
    types::{
        Date32Type, DurationMicrosecondType, DurationMillisecondType, DurationNanosecondType,
        DurationSecondType, Float32Type, Float64Type, Int16Type, Int32Type, Int64Type, Int8Type,
        TimestampMicrosecondType, TimestampMillisecondType, TimestampNanosecondType,
        TimestampSecondType, UInt16Type, UInt32Type, UInt64Type, UInt8Type,
    },
    Array, BooleanArray, LargeStringArray, StringArray,
};
use arrow_schema::{DataType, TimeUnit};
use pyo3::prelude::*;
use pyo3::types::{PyDateTime, PyString, PyTzInfo};

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
    // Null type -- always returns None
    Null,
}

/// Downcast an Arrow column to a concrete typed array once, before the row loop.
/// Returns a ColumnExtractor variant for efficient per-row value extraction.
///
/// Dictionary columns should be pre-unpacked before calling this function.
/// See `unpack_dictionary_columns` in lib.rs.
pub fn prepare_extractor<'a>(
    py: Python<'_>,
    col: &'a dyn Array,
    data_type: &DataType,
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
            // Null type -- always returns None unconditionally.
            // Do NOT check is_null() -- NullArray has no physical null buffer
            // so is_null() returns false (Pitfall 1 from research).
            ColumnExtractor::Null => Ok(py.None()),
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
