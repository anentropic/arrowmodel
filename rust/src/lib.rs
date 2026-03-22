use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyString};
use pyo3_arrow::PyRecordBatch;

type PyObject = Py<PyAny>;

mod extract;

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

        // Pattern 2: Downcast columns once before the row loop
        let schema = rb.schema();
        let extractors: Vec<extract::ColumnExtractor<'_>> = col_indices
            .iter()
            .map(|&idx| {
                let col = rb.column(idx);
                let dt = schema.field(idx).data_type();
                extract::prepare_extractor(col.as_ref(), dt)
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
}
