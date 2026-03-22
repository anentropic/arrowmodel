use arrow_array::ArrayRef;
use arrow_schema::DataType;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyString};
use pyo3_arrow::{PyRecordBatch, PyTable};

type PyObject = Py<PyAny>;

mod extract;

/// Unpack dictionary-encoded columns to their value type arrays.
/// Non-dictionary columns are returned as-is (cloned Arc reference).
/// This resolves the lifetime issue: owned unpacked arrays live in the
/// returned Vec, and extractors borrow from them.
fn unpack_columns(
    columns: &[ArrayRef],
    schema: &arrow_schema::SchemaRef,
    col_indices: &[usize],
) -> Result<Vec<ArrayRef>, PyErr> {
    col_indices
        .iter()
        .map(|&idx| {
            let col = &columns[idx];
            let dt = schema.field(idx).data_type();
            match dt {
                DataType::Dictionary(_, value_type) => {
                    arrow_cast::cast(col.as_ref(), value_type.as_ref()).map_err(|e| {
                        PyErr::new::<pyo3::exceptions::PyTypeError, _>(format!(
                            "Failed to unpack dictionary array: {e}"
                        ))
                    })
                }
                _ => Ok(col.clone()),
            }
        })
        .collect()
}

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

    /// Convert an Arrow RecordBatch to a list of Pydantic model instances.
    ///
    /// For each row, builds a kwargs PyDict from extracted column values
    /// and calls model_cls.model_construct(**kwargs) -- no Pydantic validation.
    ///
    /// Arguments:
    ///   - batch: Arrow RecordBatch (via PyCapsule / C Data Interface)
    ///   - model_cls: Pydantic model class (e.g. MyModel)
    ///   - col_indices: column indices in the RecordBatch to extract
    ///   - field_names: Pydantic field names corresponding to each column index
    #[pyfunction]
    fn convert_record_batch(
        py: Python<'_>,
        batch: PyRecordBatch,
        model_cls: Bound<'_, PyAny>,
        col_indices: Vec<usize>,
        field_names: Vec<String>,
    ) -> PyResult<PyObject> {
        let rb = batch.into_inner();
        let num_rows = rb.num_rows();

        // FAST-03: Intern field names once, reuse across all rows (Pattern 5)
        let interned_names: Vec<Bound<'_, PyString>> = field_names
            .iter()
            .map(|name| PyString::intern(py, name))
            .collect();

        // Pre-unpack dictionary columns before building extractors
        let schema = rb.schema();
        let unpacked = unpack_columns(rb.columns(), &schema, &col_indices)?;

        // Pattern 2: Downcast columns once before the row loop
        // Use unpacked columns (dictionary columns are already decoded)
        let extractors: Vec<extract::ColumnExtractor<'_>> = unpacked
            .iter()
            .enumerate()
            .map(|(i, col)| {
                let orig_idx = col_indices[i];
                let dt = schema.field(orig_idx).data_type();
                // For dictionary columns, use the value type for the extractor
                let effective_dt = match dt {
                    DataType::Dictionary(_, value_type) => value_type.as_ref(),
                    other => other,
                };
                extract::prepare_extractor(py, col.as_ref(), effective_dt)
            })
            .collect::<Result<_, _>>()?;

        // Pitfall 5: Pre-allocate result Vec
        let mut results: Vec<PyObject> = Vec::with_capacity(num_rows);

        // Row loop: build kwargs, call model_construct
        for row in 0..num_rows {
            let kwargs = PyDict::new(py);
            for (extractor, interned_name) in extractors.iter().zip(interned_names.iter()) {
                let value = extractor.extract_value(py, row)?;
                kwargs.set_item(interned_name, value)?;
            }
            // FAST-01, Pitfall 3: call_method with kwargs (not call_method1)
            let instance = model_cls.call_method("model_construct", (), Some(&kwargs))?;
            results.push(instance.unbind());
        }

        // Convert Vec to PyList and return
        let py_list = PyList::new(py, &results)?;
        Ok(py_list.into_any().unbind())
    }

    /// Convert an Arrow Table to a list of Pydantic model instances.
    ///
    /// Iterates over all RecordBatches in the Table, using the shared
    /// Table schema to resolve column indices once. Field name strings
    /// are interned once and reused across all batches (FAST-02).
    #[pyfunction]
    fn convert_table(
        py: Python<'_>,
        table: PyTable,
        model_cls: Bound<'_, PyAny>,
        col_indices: Vec<usize>,
        field_names: Vec<String>,
    ) -> PyResult<PyObject> {
        let (batches, _schema) = table.into_inner();

        // FAST-02: Intern field names once, reuse across ALL batches
        let interned_names: Vec<Bound<'_, PyString>> = field_names
            .iter()
            .map(|name| PyString::intern(py, name))
            .collect();

        // Pre-allocate for total rows across all batches
        let total_rows: usize = batches.iter().map(|b| b.num_rows()).sum();
        let mut results: Vec<PyObject> = Vec::with_capacity(total_rows);

        for rb in &batches {
            let schema = rb.schema();

            // Pre-unpack dictionary columns for this batch
            let unpacked = unpack_columns(rb.columns(), &schema, &col_indices)?;

            let extractors: Vec<extract::ColumnExtractor<'_>> = unpacked
                .iter()
                .enumerate()
                .map(|(i, col)| {
                    let orig_idx = col_indices[i];
                    let dt = schema.field(orig_idx).data_type();
                    let effective_dt = match dt {
                        DataType::Dictionary(_, value_type) => value_type.as_ref(),
                        other => other,
                    };
                    extract::prepare_extractor(py, col.as_ref(), effective_dt)
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
}
