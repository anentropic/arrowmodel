"""Build verification tests for Phase 1 requirements."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa

PROJECT_ROOT = Path(__file__).parent.parent


class TestBuildConfig:
    """Verify build configuration files are correct (BUILD-02, BUILD-03)."""

    def test_pyproject_uses_maturin_backend(self) -> None:
        """BUILD-02: pyproject.toml uses maturin as build backend."""
        content = (PROJECT_ROOT / "pyproject.toml").read_text()
        assert 'build-backend = "maturin"' in content
        assert '"maturin>=' in content

    def test_cargo_has_required_dependencies(self) -> None:
        """BUILD-03: Cargo.toml contains all required Rust dependencies."""
        content = (PROJECT_ROOT / "rust" / "Cargo.toml").read_text()
        required_deps = [
            "pyo3",
            "pyo3-arrow",
            "arrow-array",
            "arrow-schema",
            "serde_json",
            "chrono",
            "thiserror",
        ]
        for dep in required_deps:
            assert dep in content, f"Missing dependency: {dep}"

    def test_cargo_has_cdylib_crate_type(self) -> None:
        """BUILD-03: Cargo.toml produces a cdylib for Python extension."""
        content = (PROJECT_ROOT / "rust" / "Cargo.toml").read_text()
        assert "cdylib" in content


class TestModuleImport:
    """Verify the Rust extension module is importable (BUILD-01)."""

    def test_import_core_module(self) -> None:
        """BUILD-01: import arrowmodel._core succeeds."""
        from arrowmodel import _core

        assert hasattr(_core, "record_batch_info")

    def test_import_record_batch_info(self) -> None:
        """BUILD-01: record_batch_info function is callable."""
        from arrowmodel._core import record_batch_info

        assert callable(record_batch_info)


class TestPyCapsuleRoundTrip:
    """Verify Arrow C Data Interface works via pyo3-arrow (INPUT-03)."""

    def test_record_batch_info_returns_shape(self, sample_record_batch: pa.RecordBatch) -> None:
        """INPUT-03: record_batch_info accepts pyarrow RecordBatch via PyCapsule."""
        from arrowmodel._core import record_batch_info

        rows, cols = record_batch_info(sample_record_batch)
        assert rows == 3
        assert cols == 2

    def test_empty_record_batch(self) -> None:
        """INPUT-03: handles empty RecordBatch."""
        from arrowmodel._core import record_batch_info

        batch = pa.record_batch({"x": pa.array([], type=pa.int64())})
        rows, cols = record_batch_info(batch)
        assert rows == 0
        assert cols == 1

    def test_many_columns(self) -> None:
        """INPUT-03: handles RecordBatch with many columns."""
        from arrowmodel._core import record_batch_info

        data = {f"col_{i}": [1, 2, 3] for i in range(20)}
        batch = pa.record_batch(data)
        rows, cols = record_batch_info(batch)
        assert rows == 3
        assert cols == 20
