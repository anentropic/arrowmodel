# arrowmodel

Dict-free, single-step conversion from Apache Arrow buffers to Pydantic v2 model instances.

arrowmodel uses a Rust core (via PyO3) to convert `RecordBatch` and `Table` objects directly into Pydantic models, skipping the intermediate Python dict representation that `to_pylist()` + Pydantic construction requires.

## Installation

```bash
pip install arrowmodel
```

## Quick start

```python
import pyarrow as pa
from pydantic import BaseModel

from arrowmodel import from_arrow


class User(BaseModel):
    id: int
    name: str
    score: float


batch = pa.record_batch(
    {
        "id": [1, 2, 3],
        "name": ["Alice", "Bob", "Carol"],
        "score": [9.5, 8.0, 7.3],
    }
)

users = from_arrow(User, batch)
# [User(id=1, name='Alice', score=9.5), ...]
```

## Usage

### Converter object (recommended for repeated use)

When converting multiple batches with the same model, create a converter once and reuse it. The schema-to-field mapping is compiled at init and cached.

```python
from arrowmodel import ArrowModelConverter

converter = ArrowModelConverter(User)

# Works with RecordBatch
users = converter.convert(batch)

# Works with Table (multiple batches handled internally)
table = pa.table({"id": [1, 2], "name": ["a", "b"], "score": [1.0, 2.0]})
users = converter.convert(table)
```

### Lazy iteration

For large datasets, iterate one batch at a time to limit memory usage:

```python
from arrowmodel import iter_arrow

for user in iter_arrow(User, table):
    process(user)

# Or with the converter object:
for user in converter.iter(table):
    process(user)
```

### Validated mode

By default arrowmodel uses `model_construct` (no validation, maximum speed). Pass `validate=True` to run full Pydantic validation on each row:

```python
users = from_arrow(User, batch, validate=True)

# Or:
converter = ArrowModelConverter(User, validate=True)
users = converter.convert(batch)
```

### Alias support

arrowmodel resolves Arrow column names against Pydantic aliases. Resolution priority: `validation_alias` > `alias` > field name.

```python
from pydantic import Field


class Record(BaseModel):
    user_id: int = Field(alias="userId")
    display_name: str = Field(alias="displayName")


batch = pa.record_batch(
    {
        "userId": [1, 2],
        "displayName": ["Alice", "Bob"],
    }
)
records = from_arrow(Record, batch)
# [Record(user_id=1, display_name='Alice'), ...]
```

### Schema handling

- **Missing required columns** raise `ValueError` with details about which columns are missing and what is available.
- **Extra Arrow columns** are silently ignored.
- **Optional fields** missing from the Arrow schema are set to their default value.

### Supported types

arrowmodel handles the full range of Arrow primitive, temporal, binary, and nested types including: integers, floats, strings, booleans, dates, timestamps, durations, times, decimals, binary, lists, structs, maps, dictionaries, and more.

## Input compatibility

arrowmodel accepts any Arrow-PyCapsule-compatible input (pyarrow, polars, nanoarrow) via the Arrow C Data Interface.

## Development

```bash
# Install dependencies
uv sync --dev

# Install git hooks
prek install

# Run all checks
prek run --all-files
```

## License

Apache-2.0
