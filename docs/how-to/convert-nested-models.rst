.. meta::
   :description: Convert Arrow Struct columns into nested Pydantic models, including Optional nested types and deeply nested hierarchies.

.. _how-to-convert-nested-models:

How to Convert Nested Models
=============================

Arrow ``Struct`` columns map to nested Pydantic models. arrowmodel detects
``BaseModel`` subclass annotations on your fields and recursively converts
the struct's child arrays into nested model instances.

Define nested models
--------------------

Define a parent model with a field typed as another ``BaseModel`` subclass.
The nested model's field names must match the struct's child field names.

.. code-block:: python

   import pyarrow as pa
   from pydantic import BaseModel
   from arrowmodel import model_convert


   class Address(BaseModel):
       city: str
       zip_code: int


   class Person(BaseModel):
       name: str
       address: Address


   struct_arr = pa.StructArray.from_arrays(
       [pa.array(["NYC", "LA"]), pa.array([10001, 90001], type=pa.int32())],
       names=["city", "zip_code"],
   )
   batch = pa.record_batch(
       {
           "name": pa.array(["Alice", "Bob"]),
           "address": struct_arr,
       }
   )

   people = model_convert(Person, batch)
   print(people[0].name)  # Alice
   print(people[0].address.city)  # NYC
   print(people[0].address.zip_code)  # 10001

The nested ``Address`` instances are built with ``model_construct`` (or
``model_validate_json`` in validated mode) just like top-level models.

Handle optional nested models
-----------------------------

When a struct value can be null, type the field as ``Optional``:

.. code-block:: python

   class Person(BaseModel):
       name: str
       address: Address | None = None


   # Build a struct array with a null at row index 1
   cities = pa.array(["NYC", None, "LA"])
   zips = pa.array([10001, 0, 90001], type=pa.int32())
   struct_arr = pa.StructArray.from_arrays(
       [cities, zips],
       names=["city", "zip_code"],
       mask=pa.array([False, True, False]),  # row 1 is a null struct
   )
   batch = pa.record_batch(
       {
           "name": pa.array(["Alice", "Bob", "Charlie"]),
           "address": struct_arr,
       }
   )

   people = model_convert(Person, batch)
   print(people[0].address.city)  # NYC
   print(people[1].address)  # None  (the entire struct was null)
   print(people[2].address.city)  # LA

A null *struct* produces ``None`` for the nested model. A non-null struct with a
null *child field* produces a model instance where that field is ``None``:

.. code-block:: python

   # Struct is not null, but the city child is null
   cities = pa.array(["NYC", None])
   zips = pa.array([10001, 90001], type=pa.int32())
   struct_arr = pa.StructArray.from_arrays(
       [cities, zips],
       names=["city", "zip_code"],
   )
   batch = pa.record_batch(
       {
           "name": pa.array(["Alice", "Bob"]),
           "address": struct_arr,
       }
   )

   people = model_convert(Person, batch)
   print(people[1].address)  # Address(city=None, zip_code=90001)
   print(people[1].address.city)  # None
   print(people[1].address.zip_code)  # 90001

.. tip::

   There is a difference between a null struct (the whole address is missing)
   and a struct with null children (the address exists but some fields are
   missing). arrowmodel preserves this distinction.

Deeply nested structs
---------------------

Struct-in-struct works to arbitrary depth. Define matching nested models:

.. code-block:: python

   class Inner(BaseModel):
       x: int


   class Outer(BaseModel):
       inner: Inner | None = None


   class Wrapper(BaseModel):
       outer: Outer | None = None


   inner_struct = pa.StructArray.from_arrays(
       [pa.array([10, 20], type=pa.int32())],
       names=["x"],
   )
   outer_struct = pa.StructArray.from_arrays(
       [inner_struct],
       names=["inner"],
   )
   batch = pa.record_batch({"outer": outer_struct})

   results = model_convert(Wrapper, batch)
   print(results[0].outer.inner.x)  # 10
   print(results[1].outer.inner.x)  # 20
