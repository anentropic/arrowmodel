use pyo3::prelude::*;
use pyo3_arrow::PyRecordBatch;

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
}
