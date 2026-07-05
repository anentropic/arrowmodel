.. meta::
   :description: Background concepts and design explanations for arrowmodel.

.. _explanation:

Explanation
===========

Deeper understanding of how arrowmodel works, why it makes the design choices
it does, and what happens under the hood.

- :ref:`explanation-fast-vs-validated` -- How the two conversion paths work internally, what each one skips or runs, and when to pick one over the other.
- :ref:`explanation-type-mappings` -- Complete mapping of every supported Arrow data type to the Python type it produces in your Pydantic model.

.. toctree::
   :hidden:

   fast-vs-validated
   type-mappings
