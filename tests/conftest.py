"""Shared pytest fixtures for arrowdantic test suite."""

from __future__ import annotations

import pyarrow as pa
import pytest


@pytest.fixture
def sample_record_batch() -> pa.RecordBatch:
    """A simple RecordBatch with int and string columns."""
    return pa.record_batch({"x": [1, 2, 3], "y": ["a", "b", "c"]})
