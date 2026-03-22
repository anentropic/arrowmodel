use arrow_array::{
    cast::{as_boolean_array, as_largestring_array, as_primitive_array, as_string_array},
    types::{
        Float32Type, Float64Type, Int16Type, Int32Type, Int64Type, Int8Type, UInt16Type,
        UInt32Type, UInt64Type, UInt8Type,
    },
    Array, BooleanArray, LargeStringArray, StringArray,
};
use arrow_schema::DataType;
use pyo3::prelude::*;
use pyo3::types::PyString;

type PyObject = Py<PyAny>;

/// Column extractor enum -- one variant per supported Arrow primitive type.
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
}

/// Downcast an Arrow column to a concrete typed array once, before the row loop.
/// Returns a ColumnExtractor variant for efficient per-row value extraction.
pub fn prepare_extractor<'a>(
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
        }
    }
}
