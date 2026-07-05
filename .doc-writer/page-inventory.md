# Page Inventory

**Generated:** 2026-04-04
**Doc system:** sphinx-shibuya (RST)
**Navigation:** Sidebar only
**API Reference:** sphinx-autoapi (replaces Reference section -- no manual reference pages)

## Proposed Documentation

| # | Type | Title | Key Sections | File Path |
|---|------|-------|--------------|-----------|
| 1 | (landing) | Overview | Project intro, feature highlights (grid/cards), quick install, quick example, section navigation | docs/index.rst |
| 2 | tutorial | Getting Started | Prerequisites, installation (pip/uv tabs), define a model, create Arrow data, convert to models, what you learned | docs/tutorials/getting-started.rst |
| 3 | tutorial | Tutorials (index) | Section intro, child page links with abstracts, hidden toctree | docs/tutorials/index.rst |
| 4 | how-to | How to Choose an API Style | Problem context, three styles (functional, converter, ArrowModel base class), when to use each, comparison table | docs/how-to/choose-api-style.rst |
| 5 | how-to | How to Use Validated Mode | When to validate, enabling validate=True, what validation catches, performance trade-off, error handling | docs/how-to/use-validated-mode.rst |
| 6 | how-to | How to Work with Aliases | Pydantic alias resolution, validation_alias vs alias vs field_name, populate_by_name, unsupported alias types | docs/how-to/work-with-aliases.rst |
| 7 | how-to | How to Convert Nested Models | Arrow Struct columns, defining nested Pydantic models, Optional nested models, null struct handling | docs/how-to/convert-nested-models.rst |
| 8 | how-to | How to Iterate over Large Datasets | Memory problem, model_iter / converter.iter / ArrowModel.iter, batch-at-a-time semantics, streaming patterns | docs/how-to/iterate-large-datasets.rst |
| 9 | how-to | How to Integrate with FastAPI | ADBC/Flight SQL query, convert to Pydantic, return from endpoint, reusing converters, validated mode for untrusted data | docs/how-to/integrate-fastapi.rst |
| 10 | how-to | How-To Guides (index) | Section intro, child page links with abstracts, hidden toctree | docs/how-to/index.rst |
| 11 | explanation | Understanding Fast Path vs Validated Path | What each path does, how model_construct works, how model_validate_json works, when to use which, performance characteristics, diagram | docs/explanation/fast-vs-validated.rst |
| 12 | explanation | Arrow Type Mappings | Full type mapping table (Arrow type -> Python type), temporal types, nested types, binary types, interval types, unsupported types | docs/explanation/type-mappings.rst |
| 13 | explanation | Explanation (index) | Section intro, child page links with abstracts, hidden toctree | docs/explanation/index.rst |
| 14 | (section-index) | Reference (index) | Section intro, link to autoapi-generated API docs, hidden toctree including api/index | docs/reference/index.rst |
| 15 | (readme) | README.md | Title, badges, description, quick start, key features, input compatibility, license | README.md |
| 16 | (maintainer) | MAINTAINER.md | Dev setup, common tasks, architecture overview, CI/CD, release process, decision log | MAINTAINER.md |

## API Reference Status

**Detected:** sphinx-autoapi is configured in the project. Autoapi output will be placed under `reference/api/` via `autoapi_root = "reference/api"` in conf.py. The doc-author will NOT write manual reference pages -- docstrings in `src/arrowmodel/__init__.py` and `src/arrowmodel/_core.pyi` are the source of truth. Inline code mentions of public symbols will use `:py:func:`, `:py:class:`, and `:py:meth:` roles to auto-link to autoapi pages.

## Audience Targeting

All pages target the single configured persona: **Python backend engineers** (intermediate-advanced).

- **Tutorials (#2):** Targets engineers new to arrowmodel specifically. Assumes Python, Arrow, and Pydantic knowledge but explains every arrowmodel API call.
- **How-To Guides (#4-9):** Targets engineers actively integrating arrowmodel into a project. Task-oriented, assumes they have completed or could complete the tutorial.
- **Explanation (#11-12):** Targets engineers who want to understand the "why" behind design decisions (fast path vs validated, type mapping rules). Useful for making informed choices about validation mode and debugging type conversion issues.
- **README (#15):** Targets first-time visitors evaluating whether to adopt the library.
- **MAINTAINER (#16):** Targets the project maintainer (future self reference).

## Coverage Gaps

- **Polars/nanoarrow integration:** The library accepts any PyCapsule-compatible input but all examples and tests use pyarrow. A dedicated how-to for Polars DataFrame conversion could be added once real-world usage patterns emerge. The "Getting Started" tutorial and "Integrate with FastAPI" how-to will mention PyCapsule compatibility.
- **Error handling reference:** The library raises `ValueError` (missing columns), `NotImplementedError` (unsupported alias types), and `ValidationError` (validated path). These are covered within the relevant how-to guides rather than a separate page, which is appropriate for the current API size.
- **Performance tuning:** Benchmarks exist in `benchmarks/` but there is no dedicated "How to optimize performance" page. The fast-vs-validated explanation page covers the main performance decision. A dedicated page could be added if the API grows performance-relevant knobs.
- **Rust internals:** The Rust core (`_core` module, `extract.rs`) is internal implementation. It is not documented in user-facing pages, as intended.
