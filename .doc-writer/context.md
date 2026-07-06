# Doc Writer Context

**Generated:** 2026-04-04
**Source:** /doc-writer:setup researcher
**Editable:** Yes -- manual edits are preserved until the next --refresh-context run. To make permanent changes, edit config.yaml and re-run setup.

## Project Summary

arrowmodel is a Python library with a Rust core (via PyO3/maturin) that converts Apache Arrow `RecordBatch` and `Table` objects directly into Pydantic v2 model instances. It eliminates the intermediate Python dict representation from `to_pylist()` + Pydantic construction, replacing it with a single tight Rust loop over Arrow buffers accessed via the Arrow C Data Interface. The library accepts any Arrow-PyCapsule-compatible input (pyarrow, polars, nanoarrow) and delivers roughly 2x speedup over pure-Python approaches. The public API surface is small and focused: `model_convert`, `model_iter`, `ArrowModelConverter`, and `ArrowModel` base class.

## User Persona: Python backend engineers

### Profile
- **Skill level:** Intermediate-advanced
- **What they know:**
  - Python: fluent in modern Python (3.11+), type hints, context managers, generators, decorators, and package management with pip/uv.
  - Arrow (RecordBatch/Table): understands columnar data layout, knows what a RecordBatch and Table are, has used `to_pylist()` or `to_pandas()` to extract row-oriented data. Familiar with schemas, column types, and zero-copy semantics.
  - Pydantic v2 models: can define models with `BaseModel`, use `Field()` with aliases, configure `model_config`, and understands the difference between `model_validate` and `model_construct`. Knows about validators and serializers.
  - Web frameworks (FastAPI): builds REST APIs with FastAPI, understands dependency injection, response models, and how Pydantic models serve as both request parsing and response serialization.
  - Data layer tools (ADBC, Flight SQL, Polars, Pandas): queries databases using ADBC or Flight SQL (which return Arrow-native results), transforms data with Polars or Pandas, and understands the impedance mismatch between columnar query results and row-oriented API responses.
- **What to always explain:**
  - arrowmodel's API surface: every function, class, and parameter must be introduced before use. Do not assume they have read other pages -- each page should be self-contained for the concepts it uses.
  - Installation steps: this is a PyO3/maturin-built binary wheel. Explain `pip install arrowmodel` and `uv add arrowmodel`. Note that no Rust toolchain is needed for end users (pre-built wheels).
  - Supported Arrow type mappings: always document which Arrow types map to which Python/Pydantic types. Do not assume they know that Arrow `Timestamp` becomes `datetime` or that `Struct` maps to nested models.
  - Edge case handling (nulls, nested types, aliases): explain how nulls map to `None` or defaults, how nested Arrow Structs become nested Pydantic models, and how alias resolution works (validation_alias > alias > field_name).
- **Their world:** These engineers sit at the boundary between the data layer and the web serving layer. Their daily work involves receiving query results from databases (often via ADBC, Flight SQL, or Polars), transforming that data, and serving it through FastAPI or similar frameworks as JSON API responses. The pain point is the serialization bottleneck: Arrow data must become Pydantic model instances before FastAPI can serialize them. The current approach (`to_pylist()` into dicts, then `Model(**row)` or `model_validate`) is slow and allocates heavily. They care about latency, memory pressure, and keeping their response models as the single source of truth for data shape.
- **How they found this library:** They hit the `to_pylist()` + Pydantic construction bottleneck in a production API endpoint. Either profiling showed serialization as a hot spot, or they searched PyPI/GitHub for "arrow to pydantic" or "fast arrow deserialization" and found arrowmodel. They may have considered writing their own Rust extension, using `model_construct` manually with dict unpacking, or switching to a non-Pydantic serialization path -- all of which arrowmodel replaces.

### Common Tasks
- **Convert Arrow query results to Pydantic models:** Use `model_convert(MyModel, batch)` for one-shot conversion or create an `ArrowModelConverter(MyModel)` for repeated use. Choose between the fast path (default, uses `model_construct`) and the validated path (`validate=True`, runs full Pydantic validation via `model_validate_json`).
- **Integrate with FastAPI response serialization:** Wire arrowmodel into a FastAPI endpoint where the database returns Arrow data and the response model is a Pydantic class. The converter output is a `list[Model]` that FastAPI serializes directly.
- **Connect ADBC/Flight SQL/Polars outputs to API endpoints:** ADBC and Flight SQL return `RecordBatch` or `Table` natively. Polars DataFrames export via Arrow PyCapsule. arrowmodel accepts all of these via the Arrow C Data Interface -- no pyarrow dependency required at runtime.

### Writing Guidance for This Persona
- When explaining the API, assume they already know Pydantic model definition and Arrow data structures, but spell out every arrowmodel function signature, parameter, and return type.
- Use professional but accessible terminology. They know what "zero-copy" and "columnar" mean -- do not define those. Do define arrowmodel-specific concepts like "field map," "fast path vs validated path," and "column resolution."
- Examples should show real-world scenarios: ADBC query result into a FastAPI response model, Polars DataFrame into typed models, handling optional fields and aliases in production schemas.

## Use Cases

### Serialize Arrow data to JSON API responses

**Problem:** In backend API services, data often arrives in Arrow columnar format from modern database connectors (ADBC, Flight SQL) or analytical engines (Polars). To serve this data as a JSON API response through FastAPI or similar frameworks, it must be converted to Pydantic model instances. The standard approach -- `batch.to_pylist()` to get a list of dicts, then `Model(**row)` for each row -- creates an intermediate Python dict for every row, doubling memory allocation and adding significant latency on high-throughput endpoints.
**What's possible:** arrowmodel's `model_convert` and `ArrowModelConverter.convert` take a `RecordBatch` or `Table` and a Pydantic model class, then walk the Arrow buffers in Rust to produce `model_construct`-built instances directly. The converter resolves Arrow column names against Pydantic aliases at init time, handles nested Struct columns as nested models, and supports both a fast path (no validation, maximum speed) and a validated path (`model_validate_json` for full Pydantic validation). The `ArrowModel` base class provides `MyModel.convert(batch)` for the most concise API.
**Outcome:** Arrow query results are materialized as typed Pydantic model instances with roughly 2x less latency and significantly reduced allocation pressure compared to the dict-based approach. FastAPI endpoints can return these models directly for JSON serialization. Schema mismatches (missing required columns) are caught with clear `ValueError` messages at conversion time rather than silently producing broken data.
**Relevant persona(s):** Python backend engineers
**Source:** user-provided

### Lazy iteration over large Arrow datasets

**Problem:** When processing large Arrow Tables with millions of rows, materializing the entire list of Pydantic models at once consumes excessive memory. Batch-processing patterns (e.g., streaming results to a client, writing to a file row-by-row, or applying per-row business logic) need to process one model at a time without holding all of them in memory.
**What's possible:** arrowmodel's `model_iter` function and `ArrowModelConverter.iter` method yield individual model instances lazily. For Tables with multiple RecordBatches, only one batch's worth of instances is materialized at a time. The `ArrowModel.iter` classmethod provides the same capability with the most concise syntax.
**Outcome:** Memory usage stays proportional to a single RecordBatch rather than the full Table. Engineers can stream-process arbitrarily large Arrow datasets through Pydantic models without memory pressure spikes.
**Relevant persona(s):** Python backend engineers
**Source:** inferred

### Use ArrowModel base class for concise model definitions

**Problem:** Creating and managing `ArrowModelConverter` instances alongside Pydantic model definitions adds boilerplate. Engineers who define many models want the conversion capability built into the model class itself, similar to how Django models have `objects.all()`.
**What's possible:** The `ArrowModel` base class (subclass of `BaseModel`) auto-generates an `ArrowModelConverter` at class definition time via `__pydantic_init_subclass__`. Subclasses gain `convert()` and `iter()` classmethods with no additional setup. The validated path is available via `validate=True` on either method.
**Outcome:** Model definitions are self-contained -- `User.convert(batch)` works immediately after class definition. No converter management, no imports beyond `ArrowModel`. The converter is cached as a class variable, so repeated calls reuse the same compiled field map.
**Relevant persona(s):** Python backend engineers
**Source:** inferred

> The last two use cases were inferred from persona context and codebase analysis. To promote use cases to a documentation section, run `/doc-writer:setup` and provide explicit use cases.

## Tone: personality

### Writing Rules
- Same depth and structure as warm-businesslike: brief (1-2 sentence) introduction explaining what the page covers, multiple examples per concept (basic then variations), troubleshooting sections where relevant.
- Occasional light humor in admonitions or transitions is welcome, but never in code examples, API signatures, or critical instructions. If the joke obscures the point, cut it.
- Can use first person sparingly ("We'll start by...", "Let's see what happens when...") to create a conversational feel.
- Personality belongs in analogies and explanations, not in API descriptions. The reference docs stay precise; the tutorials and how-to guides can be warmer.
- Never sacrifice clarity for humor. A confused reader who chuckled is worse off than a clear reader who did not.
- Admonitions can have personality in their titles or framing ("Don't skip this -- your future self will thank you") but the content inside must be accurate and actionable.

## Framework Preferences: sphinx-shibuya

The project is transitioning from mkdocs-material to sphinx-shibuya. The existing `mkdocs.yml` and `docs/` directory reflect the old system. New documentation should be authored in RST for Sphinx with the Shibuya theme.

### Navigation Strategy
- **Strategy:** Sidebar only
- No `nav_links` key in `html_theme_options` (or the key is absent entirely).
- The sidebar shows the full toctree from root `index.rst`.
- Sections are rendered as expandable groups in the sidebar.
- The root `index.rst` should have a hidden toctree listing all section index files so the sidebar populates without rendering a visible list on the landing page.
- The front page (`index.rst`) is linked as "Overview" in the sidebar at the same level as the section headings. Use "Overview" not "Home".
- Keep left nav to 3 levels maximum (section heading, page, sub-page). Avoid level 4 nesting.
- Section index pages list child pages with 1-sentence abstracts written inline (Sphinx does not auto-render child page descriptions).

### API Documentation: sphinx-autoapi
- autoapi output REPLACES the Reference section entirely. The doc-author MUST NOT write manual reference pages. Docstrings are the source of truth.
- Google docstring style is the convention (Napoleon extension parses them).
- Place autoapi output under `reference/api/` using `autoapi_root = "reference/api"` in conf.py.
- Set `autoapi_add_toctree_entry = False` and manually include `api/index` in the reference section toctree.
- Set `autoapi_python_class_content = "both"` to show both class-level and `__init__` docstrings.
- Include `sphinx.ext.napoleon` alongside `autoapi.extension` in conf.py extensions.

### Features to Use
- **Admonitions:** Use specific types (`.. tip::`, `.. warning::`, `.. danger::`, `.. note::`, `.. versionadded::`, `.. deprecated::`). Do not stack multiple admonitions back-to-back -- consolidate into one with a list.
- **Code blocks:** Always use `.. code-block:: {language}`. Use `:emphasize-lines:` for key lines, `:caption:` for file paths. Never use bare `::`.
- **Grids and cards** (`.. grid::`, `.. grid-item-card::`): Use for landing pages, feature overviews, and section index pages. Grid values `1 2 3 3` for responsive layout. Use `:link:` on cards for clickable navigation.
- **Tab sets** (`.. tab-set::`, `.. tab-item::`): Use for installation methods (pip/uv/conda), sync/async alternatives, or showing the same concept with different API styles (functional vs class-based). Use `:sync-group:` for cross-page tab synchronization.
- **Dropdowns** (`.. dropdown::`): Use for optional or advanced content most readers can skip. Use `:color:` and `:icon:` to distinguish informational from warning dropdowns.
- **Badges** (`:bdg-success:`, `:bdg-warning:`, `:bdg-info:`): Use for version markers, stability status, and deprecation notices. Keep badge text to one or two words.
- **Buttons** (`.. button-ref::`): Use on landing pages for prominent calls-to-action ("Get Started"). Maximum two per page.
- **Mermaid diagrams** (`.. mermaid::`): Available via sphinxcontrib-mermaid. Use the RST directive, never fenced code blocks. Shibuya handles dark/light mode automatically.
- **Cross-references:** Use `:ref:\`label\`` for ALL internal links. Place labels above headings. AVOID `:doc:\`path\``. Use `:py:func:`, `:py:class:`, `:py:meth:` for API mentions -- these auto-link to autoapi pages.
- **Intersphinx:** Link to Python stdlib and Pydantic docs via intersphinx roles (`:py:class:\`pydantic.BaseModel\``).

### Features NOT to Use
- **pymdownx extensions** (tabbed, superfences, details, highlight, snippets, emoji): These are MkDocs/Python-Markdown extensions. Not available in Sphinx. Use the Sphinx/sphinx-design equivalents listed above.
- **Markdown syntax in RST files:** Do not use fenced code blocks (triple backtick), Markdown-style links, or YAML frontmatter. Sphinx uses RST directives and roles.
- **`:doc:` cross-references:** Strongly discouraged. They couple links to file paths and break when pages move. Use `:ref:` with labels instead.
- **nav_links in theme options:** Not used with sidebar-only navigation. Do not add them.
