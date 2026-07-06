.. meta::
   :description: Choose between the ArrowModel base class, ArrowModelConverter, and convenience functions for converting Arrow data to Pydantic models.

.. _how-to-choose-api-style:

How to Choose an API Style
==========================

arrowmodel offers three ways to convert Arrow data into Pydantic models.
They all call the same Rust conversion code under the hood -- the difference
is ergonomics. Pick the one that fits your situation and move on.

ArrowModel base class (recommended default)
--------------------------------------------

Subclass :py:class:`~arrowmodel.ArrowModel` instead of ``BaseModel`` and you
get :py:meth:`~arrowmodel.ArrowModel.convert` and
:py:meth:`~arrowmodel.ArrowModel.iter` as classmethods for free. The converter
is compiled at class definition time, so repeated calls reuse the same field
mapping.

.. code-block:: python

   import pyarrow as pa
   from arrowmodel import ArrowModel


   class User(ArrowModel):
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

   users = User.convert(batch)
   # [User(id=1, name='Alice', score=9.5), ...]

   for user in User.iter(batch):
       print(user.name)

This is the recommended default for most projects. Your model *is* the
converter -- no separate object to manage, no extra import.

.. tip::

   ``ArrowModel`` is a subclass of Pydantic's ``BaseModel``. Everything you
   know about ``BaseModel`` -- validators, serializers, ``model_config``,
   ``Field()`` -- still works.

ArrowModelConverter (when you cannot use the base class)
---------------------------------------------------------

Sometimes you cannot change the model's base class. The model might live in
another package, it might already inherit from a custom ``BaseModel`` subclass,
or you might want a converter with ``validate=True`` while keeping the model
class unchanged.

In those cases, create an :py:class:`~arrowmodel.ArrowModelConverter` explicitly:

.. code-block:: python

   from pydantic import BaseModel
   from arrowmodel import ArrowModelConverter


   # Model defined elsewhere -- you can't change its base class
   class User(BaseModel):
       id: int
       name: str
       score: float


   converter = ArrowModelConverter(User)
   users = converter.convert(batch)

   # Reuse the converter across batches -- the field mapping is compiled once
   more_users = converter.convert(another_batch)

Create the converter once and reuse it. The schema-to-field mapping is compiled
at ``__init__`` time, so there is no repeated work on each
:py:meth:`~arrowmodel.ArrowModelConverter.convert` call.

To iterate lazily instead of materialising the full list:

.. code-block:: python

   # Using converter from above
   for user in converter.iter(table):
       print(user.name)

model_convert and model_iter (quick one-shots)
-----------------------------------------------

The :py:func:`~arrowmodel.model_convert` and :py:func:`~arrowmodel.model_iter`
functions are convenience wrappers that create a temporary converter, call it
once, and throw it away. They are handy for REPL exploration, scripts, and
situations where you only convert a single batch with a given model.

.. code-block:: python

   from arrowmodel import model_convert, model_iter

   users = model_convert(User, batch)

   for user in model_iter(User, table):
       print(user.name)

.. warning::

   Every call to ``model_convert`` or ``model_iter`` creates a fresh converter
   internally. If you are converting many batches with the same model, create
   an :py:class:`~arrowmodel.ArrowModelConverter` or use
   :py:class:`~arrowmodel.ArrowModel` to avoid recompiling the field mapping
   each time.

When to use which
-----------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Style
     - Use when
   * - ``ArrowModel`` base class
     - You control the model definition and want the most concise API.
       This is the right choice for most new code.
   * - ``ArrowModelConverter``
     - You cannot change the model's base class, or you need separate
       converters with different ``validate`` settings for the same model.
   * - ``model_convert`` / ``model_iter``
     - One-off conversions in a REPL, notebook, or script where
       convenience outweighs converter reuse.
