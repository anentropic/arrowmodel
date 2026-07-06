.. meta::
   :description: How arrowmodel's two conversion paths work, what each one skips or runs, and when to pick one over the other.

.. _explanation-fast-vs-validated:

Understanding Fast Path vs Validated Path
==========================================

arrowmodel offers two ways to build Pydantic model instances from Arrow data.
Picking the right one is the most impactful performance decision you will make
with this library, so it is worth understanding what each path does under the
hood.

The two paths at a glance
--------------------------

.. list-table::
   :header-rows: 1
   :widths: 20 40 40

   * -
     - Fast path (default)
     - Validated path
   * - Flag
     - ``validate=False``
     - ``validate=True``
   * - Pydantic method
     - ``model_construct``
     - ``model_validate_json``
   * - Type coercion
     - None
     - Full Pydantic coercion
   * - Custom validators
     - Skipped
     - Run
   * - Field constraints
     - Skipped
     - Enforced
   * - Speed
     - ~2x faster than ``to_pylist()`` + ``model_construct``
     - Slower (JSON round-trip + validation)

How the fast path works
------------------------

When ``validate=False`` (the default), arrowmodel:

1. Walks each Arrow column in Rust, extracting values directly from Arrow
   buffers.
2. For each row, collects the extracted values as Python objects.
3. Calls ``model_construct(**row_kwargs)`` on the model class.

``model_construct`` is Pydantic's "I know what I'm doing" constructor. It
bypasses all validation -- no ``@field_validator`` decorators fire, no
``Field(ge=0)`` constraints are checked, no type coercion is attempted. The
values go straight into the model's ``__dict__``.

This is fast because:

- No intermediate Python dicts from ``to_pylist()``.
- No JSON serialisation or parsing.
- No Pydantic validation overhead.
- The Rust loop over Arrow buffers is tight and cache-friendly.

The trade-off is trust. You are trusting that the Arrow data matches the model's
schema exactly. If a column contains a string where the model expects an int,
you get a model instance with a string in an int field -- no error, no coercion,
just a quietly wrong value.

How the validated path works
-----------------------------

When ``validate=True``, arrowmodel:

1. Walks each Arrow column in Rust, extracting values directly from Arrow
   buffers (same as the fast path so far).
2. For each row, serialises the extracted values to a JSON byte string in Rust.
3. Calls ``model_validate_json(json_bytes)`` on the model class.

``model_validate_json`` is Pydantic's full validation entry point. It parses
the JSON, runs type coercion, fires custom validators, and enforces field
constraints. If anything fails, it raises ``ValidationError``.

.. mermaid::

   flowchart LR
       A["Arrow buffers"] --> B["Rust extraction"]
       B --> C{validate?}
       C -->|"False"| D["model_construct"]
       C -->|"True"| E["JSON bytes"]
       E --> F["model_validate_json"]
       D --> G["Model instance"]
       F --> G

The JSON round-trip adds overhead, but it also gives you everything Pydantic
provides: coercion, validation, and custom logic.

When to use which
------------------

**Use the fast path when:**

- The data comes from a source you control (your own database, an internal
  service, a file your pipeline produced).
- You already validated the data upstream (pandera, Great Expectations, a
  schema-enforced database).
- You need maximum conversion speed and are willing to trust the data.

**Use the validated path when:**

- The data comes from an external or untrusted source (user uploads, third-party
  APIs, federated queries).
- Your model has custom validators that enforce business rules beyond type
  checking.
- You need Pydantic's type coercion (e.g., string ``"42"`` to int ``42``).
- Correctness matters more than speed for this particular code path.

Performance characteristics
----------------------------

From the project's benchmarks on flat primitive schemas (``RecordBatch`` input):

.. list-table::
   :header-rows: 1
   :widths: 25 25 25 25

   * - Rows
     - arrowmodel (fast)
     - ``to_pylist()`` + ``model_construct``
     - Speedup
   * - 100
     - 1.9 ms
     - 3.8 ms
     - ~2x
   * - 500
     - 8.1 ms
     - 16.2 ms
     - ~2x
   * - 1,000
     - 15.6 ms
     - 33.9 ms
     - ~2.2x

The fast path is roughly 2x faster than the pure-Python approach for flat
schemas. For deeply nested models (10 levels of struct-in-struct), the advantage
narrows to roughly parity -- the Rust loop's overhead is proportionally larger
when each row requires recursive struct conversion.

The validated path adds the cost of JSON serialisation and Pydantic's validation
pipeline on top of the extraction. It is slower than both the fast path and the
pure-Python approach, but it gives you the same guarantees as calling
``model_validate_json`` directly.

A note on float NaN and Infinity
---------------------------------

JSON does not have representations for ``NaN`` or ``Infinity``. In the validated
path, arrowmodel converts these to JSON ``null``, which Pydantic then maps to
``None`` (for ``Optional[float]`` fields) or raises ``ValidationError`` (for
required ``float`` fields).

In the fast path, ``NaN`` and ``Infinity`` are passed through as-is -- your
model field will contain ``float('nan')`` or ``float('inf')``.
