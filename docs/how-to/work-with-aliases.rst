.. meta::
   :description: Map Arrow column names to Pydantic field names using aliases, validation_alias, and populate_by_name.

.. _how-to-work-with-aliases:

How to Work with Aliases
========================

When Arrow column names do not match Pydantic field names -- camelCase columns
versus snake_case fields, for example -- arrowmodel resolves the mapping using
Pydantic's alias system. This guide covers the alias types that work, the ones
that do not, and how to configure ``populate_by_name`` for maximum flexibility.

Alias resolution priority
-------------------------

arrowmodel looks up each model field's expected Arrow column name in this order:

1. ``validation_alias`` (if set)
2. ``alias`` (if set and no ``validation_alias``)
3. Field name (if neither alias is set)

The first match wins. This matches Pydantic's own priority when validating
input data.

Use validation_alias
--------------------

``validation_alias`` is the strongest alias. When set, arrowmodel looks for an
Arrow column with that name:

.. code-block:: python

   import pyarrow as pa
   from pydantic import BaseModel, Field
   from arrowmodel import model_convert


   class Record(BaseModel):
       user_id: int = Field(validation_alias="userId")
       display_name: str = Field(validation_alias="displayName")


   batch = pa.record_batch(
       {
           "userId": [1, 2],
           "displayName": ["Alice", "Bob"],
       }
   )

   records = model_convert(Record, batch)
   print(records[0].user_id)  # 1
   print(records[0].display_name)  # Alice

Use alias
---------

If ``validation_alias`` is not set, arrowmodel falls back to ``alias``:

.. code-block:: python

   class Record(BaseModel):
       user_id: int = Field(alias="userId")
       display_name: str = Field(alias="displayName")


   # Same batch as above -- "userId" and "displayName" columns
   records = model_convert(Record, batch)
   print(records[0].user_id)  # 1

Mix alias types in one model
-----------------------------

You can use ``validation_alias``, ``alias``, and bare field names together.
Each field resolves independently:

.. code-block:: python

   class MixedRecord(BaseModel):
       user_id: int = Field(validation_alias="userId")
       display_name: str = Field(alias="displayName")
       email: str  # no alias -- looks for "email" column


   batch = pa.record_batch(
       {
           "userId": [1],
           "displayName": ["Alice"],
           "email": ["alice@example.com"],
       }
   )

   records = model_convert(MixedRecord, batch)
   print(records[0].email)  # alice@example.com

Accept both alias and field name with populate_by_name
------------------------------------------------------

By default, arrowmodel only looks for the alias (or ``validation_alias``) when
one is set. If your Arrow data sometimes uses the alias and sometimes uses the
Python field name, enable ``populate_by_name`` (or ``validate_by_name``) in the
model config:

.. code-block:: python

   from pydantic import ConfigDict


   class FlexibleRecord(BaseModel):
       model_config = ConfigDict(populate_by_name=True)
       user_id: int = Field(alias="userId")


   # Works with the alias column name
   batch_alias = pa.record_batch({"userId": [1, 2]})
   records = model_convert(FlexibleRecord, batch_alias)
   print(records[0].user_id)  # 1

   # Also works with the Python field name
   batch_field = pa.record_batch({"user_id": [3, 4]})
   records = model_convert(FlexibleRecord, batch_field)
   print(records[0].user_id)  # 3

``validate_by_name=True`` has the same effect. When either is enabled,
arrowmodel registers both the alias and the field name as valid column lookups.
If both columns are present, the alias takes priority.

Unsupported alias types
-----------------------

arrowmodel does not support the following Pydantic alias features. Using them
will raise ``NotImplementedError`` when the converter is created:

- **AliasPath** -- e.g., ``Field(validation_alias=AliasPath("data", "value"))``
- **AliasChoices** -- e.g., ``Field(validation_alias=AliasChoices("val", "value"))``
- **AliasGenerator** -- e.g., ``model_config = ConfigDict(alias_generator=...)``

These alias types resolve to nested or multi-option lookups that do not map
cleanly to flat Arrow column names.

.. code-block:: python

   from pydantic import AliasPath


   class Unsupported(BaseModel):
       nested_val: str = Field(validation_alias=AliasPath("data", "value"))


   # Raises NotImplementedError at converter creation time:
   # "Field 'nested_val' uses AliasPath as validation_alias, which is not supported."
   model_convert(Unsupported, batch)

If you need these alias types, extract the relevant columns manually before
passing data to arrowmodel.
