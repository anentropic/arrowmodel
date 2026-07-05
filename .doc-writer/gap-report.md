# Gap Report

**Generated:** 2026-04-04
**Source root:** src/
**Language:** Python
**Total undocumented symbols:** 8
**Potentially stale pages:** 0

## Undocumented Symbols

### src/arrowmodel/__init__.py
- `ArrowModel` (class) -- BaseModel subclass with Arrow conversion classmethods
- `ArrowModelConverter` (class) -- converter that maps Arrow schema to Pydantic fields
- `model_convert` (function) -- one-shot Arrow-to-Pydantic conversion
- `model_iter` (function) -- lazy iterator Arrow-to-Pydantic conversion
- `_build_field_map` (function) -- internal: builds alias-aware column-to-field mapping
- `_get_nested_model` (function) -- internal: extracts nested BaseModel from annotation

### src/arrowmodel/_core.pyi (Rust extension)
- `convert_record_batch` (function) -- fast-path batch conversion via model_construct
- `convert_table` (function) -- fast-path table conversion via model_construct
- `convert_record_batch_validated` (function) -- validated batch conversion via model_validate_json
- `convert_table_validated` (function) -- validated table conversion via model_validate_json
- `record_batch_info` (function) -- returns batch metadata (nrows, ncols)
