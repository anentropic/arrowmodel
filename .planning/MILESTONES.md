# Milestones

## v1.0.0 Core Library (Shipped: 2026-07-05)

**Phases completed:** 7 phases, 16 plans, 29 tasks

**Known deferred items at close:** 1 (see STATE.md Deferred Items — the schema-model bridge research idea, parked for a future milestone)

**Key accomplishments:**

- Maturin + PyO3 build pipeline with pyo3-arrow PyCapsule smoke test accepting pyarrow RecordBatch input
- 8 pytest build verification tests covering import, config, and PyCapsule round-trip plus CI workflows with Rust toolchain and Cargo caching
- Rust ColumnExtractor with null-safe extraction for 13 Arrow primitive types, convert_record_batch pyfunction, and Python ArrowModelConverter class producing Pydantic instances via model_construct
- 18 correctness tests covering all 15 requirement IDs plus pytest-benchmark comparison showing ~1.7x speedup over to_pylist+model_construct at 100k rows
- Alias-aware ArrowModelConverter with validation_alias > alias > field_name priority, schema validation for missing required columns, and NotImplementedError for unsupported alias types
- Rust convert_table with PyTable multi-batch iteration, duck-type Table dispatch, from_arrow convenience function, and FAST-02 cross-batch string interning
- Temporal extractors (Date32, Timestamp naive/aware, Duration), dictionary pre-unpacking via arrow-cast, and null type support added to ColumnExtractor
- List/LargeList/Struct ColumnExtractor variants with recursive nested model construction via field_specs API
- Dual-path architecture complete: serde_json row serialization to model_validate_json for full Pydantic validation on all Arrow types
- Lazy iterator/generator API (iter, iter_arrow) for memory-constrained scenarios plus _core.pyi stubs for IDE autocompletion with clean basedpyright strict mode
- 14 new ColumnExtractor variants (Float16, Decimal128/256/32/64, Date64, Time32/64, Binary/LargeBinary/FixedSizeBinary, Utf8View/BinaryView) with dual-path extraction and base64 binary JSON serialization
- 6 new ColumnExtractor variants (3 intervals, FixedSizeList, Map, Union) with REE pre-unpacking completing full Arrow type coverage
- Fixed REE Table-input bug and added Decimal32/Decimal64 test coverage for full gap closure
- IntervalYearMonth/DayTime test coverage via C Data Interface reinterpretation, plus validated path tests for 7 previously untested extended types
- Added validate parameter to from_arrow() and test coverage for both from_arrow(validate=True) and iter_arrow(validate=True)

---
