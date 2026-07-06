.. meta::
   :description: Use arrowmodel with pandera-validated Pydantic models to convert schema-checked Arrow data into typed model instances.

.. _how-to-use-with-pandera:

How to Use with Pandera
========================

`pandera <https://pandera.readthedocs.io/en/stable/pydantic_integration.html>`_
can validate DataFrames against Pydantic models. When your pipeline already uses
pandera for schema enforcement, arrowmodel handles the next step: converting
the validated Arrow data into Pydantic model instances.

**Prerequisites:** ``pandera`` with its Pydantic integration installed alongside
``arrowmodel`` and ``pyarrow``.

The workflow
------------

1. Define a Pydantic model that doubles as a pandera schema.
2. Validate your DataFrame with pandera.
3. Use arrowmodel to convert the validated data into model instances.

pandera ensures the data matches expectations *before* arrowmodel converts it,
so you can confidently use the fast path (``validate=False``) -- the data has
already been checked.

Define a pandera-compatible model
----------------------------------

pandera's Pydantic integration lets you annotate Pydantic fields with pandera
column metadata. The resulting model is still a standard ``BaseModel`` subclass
that arrowmodel can convert:

.. code-block:: python

   import pandera
   from pandera.typing import Series
   from pydantic import BaseModel

   from arrowmodel import model_convert


   class UserSchema(pandera.DataFrameModel):
       id: Series[int] = pandera.Field(ge=1)
       name: Series[str] = pandera.Field(str_length={"min_value": 1})
       score: Series[float] = pandera.Field(ge=0.0, le=10.0)


   class User(BaseModel):
       id: int
       name: str
       score: float

The ``UserSchema`` validates the DataFrame and the ``User`` model is used for
arrowmodel conversion.

Validate then convert
---------------------

Run pandera validation on the DataFrame, then convert the validated Arrow data
to Pydantic model instances:

.. code-block:: python

   import pandas as pd
   import pyarrow as pa

   # Raw data -- could come from a CSV, database, or API
   df = pd.DataFrame(
       {
           "id": [1, 2, 3],
           "name": ["Alice", "Bob", "Carol"],
           "score": [9.5, 8.0, 7.3],
       }
   )

   # Validate with pandera
   validated_df = UserSchema.validate(df)

   # Convert to Arrow, then to Pydantic models
   table = pa.Table.from_pandas(validated_df)
   users = model_convert(User, table)

   for user in users:
       print(f"{user.name}: {user.score}")

Since pandera already validated the data, you can skip arrowmodel's validated
mode. The fast path is safe here because the schema constraints have been
enforced upstream.

.. tip::

   If you are working with Polars instead of Pandas, pass the Polars DataFrame
   directly to :py:func:`~arrowmodel.model_convert` -- arrowmodel accepts any
   Arrow-PyCapsule-compatible input without converting through pyarrow first.

When to add arrowmodel validation
-----------------------------------

If the data passes through untrusted transformations *after* pandera validation,
consider enabling arrowmodel's validated mode as a defence-in-depth measure:

.. code-block:: python

   # Data was validated by pandera but then transformed by external code
   users = model_convert(User, table, validate=True)

See :ref:`how-to-use-validated-mode` for details on what the validated path
catches.
