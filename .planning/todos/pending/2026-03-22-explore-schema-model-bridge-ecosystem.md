---
created: 2026-03-22T22:35:00.000Z
title: Explore schema-model bridge ecosystem
area: general
files: []
---

## Problem

Arrow Tables and RecordBatches carry embedded schemas. Pydantic models also define schemas. There's an unexplored design space around bridging these two worlds — not just converting data (what arrowdantic does today), but deriving one schema from the other.

Existing projects in this space:
- **Patito** / **Poldantic** — Polars DataFrame <-> Pydantic model bridge
- **Pandera** — DataFrame schema validation (pandas/polars/pyspark), has Pydantic integration
- **pydantic-to-pyarrow** — Pydantic model -> Arrow schema generation

Questions to explore:
1. Can we define a Pydantic model that also serves as an Arrow schema definition? (e.g., annotate fields with Arrow type metadata)
2. Can we infer a Pydantic model from an Arrow schema at runtime? (e.g., from an ADBC query result)
3. How do we stay useful for pure Arrow (ADBC, Flight, IPC) while also being composable with Polars/Pandas ecosystems?
4. What would a "schema registry" look like — define once, use for validation + conversion + type checking?
5. Where does arrowdantic's value (fast Rust conversion) fit vs. schema definition (Python-level concern)?

## Solution

Research phase:
1. Study Patito, Poldantic, Pandera, pydantic-to-pyarrow APIs and design choices
2. Identify what's missing — the gap between "convert data" and "define schema"
3. Prototype: `ArrowModel(BaseModel)` subclass that carries Arrow type annotations alongside Pydantic field definitions
4. Consider: should this be part of arrowdantic or a separate complementary package?
