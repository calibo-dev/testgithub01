# LangGraph Python Template

Configuration-driven LangGraph template with a FastAPI endpoint, reusable agent
runtime, deterministic nodes, conditional routing, model fallback, tool loading,
and optional LangSmith tracing.

## Runtime Contract

The template separates workflow configuration from stable runtime code:

- `config/agents.yaml` defines agent roles, prompts, concrete providers and model
  names, state access, outputs, and tool/MCP assignments.
- `config/tools.yaml` defines tool behavior, factory references and connection names.
- `config/connection.yml` defines named non-secret connector settings.
- `config/settings.py` resolves named connections without loading connector dependencies.
- The owning connector skill generates `tools/connection.py` only when required.
- `config/mcp.yaml` defines MCP server transports and connection metadata.
- `config/graph_config.yaml` defines nodes, entry/end nodes, direct edges,
  conditional routes, tracing, and the final output field.
- `graph/state.py` explicitly declares LangGraph `InputState`, `State`, and
  `OutputState` schemas, reducers, required inputs, and defaults.
- `nodes/agent_node_builder.py` builds every configured agent through one runtime
  path.
- `nodes/workflow_nodes.py` contains direct deterministic functions plus the
  allowlisted node and router registries.
- `graph/graph_builder.py` compiles the configuration into a `StateGraph`.
- `tools/tool_registry.py` resolves tools assigned to configured graph nodes.
- `tests/test_template.py` verifies the reusable contract without naming sample
  agents or requiring generated test rewrites.

See `approach.md` for the refactor rationale, ownership rules, and generated-file
targets.

## Tracing

When LangSmith tracing is enabled, workflow traces default to the public fields
exported as `INPUT_FIELDS` and `OUTPUT_FIELDS` in `graph/state.py`. This keeps
renamed request fields and full public responses visible without tracing arbitrary
internal state. Native LangGraph node, model and tool spans keep their hierarchy.

Workflow trace metadata records `execution_status` and, on exceptions,
`error_type` and `error_category`. These describe execution, not a returned
business outcome. Exceptions keep their original traceback and propagate normally;
a failed invocation does not fabricate returned state or an `error_count` of zero.
Configure `tracing.workflow` in `graph_config.yaml` to override field mappings,
names or tags. Input paths start with `inputs.`, for example `inputs.user_question`.

## Agent Configuration

Each agent in `agents.yaml` declares its role, model configuration, state access patterns, and tool assignments:

- `role`: Describes the agent's purpose
- `model`: Primary and optional fallback model definitions
- `reads_state`: List of state fields the agent reads as input
- `writes_state`: List of state fields the agent writes as output
- `output_mapping`: Map workflow response fields to state fields (for structured responses)
- `tools`: List of configured tool names (from `tools.yaml`)
- `mcp_servers`: List of MCP server names (from `mcp.yaml`)

Tool-backed agents list configured tool names in `tools`. Separate connection
settings from tool behavior in `config/connection.yml` and `config/tools.yaml`.

The registry resolves `connection_name` and passes the tool factory its exact
`tool_name` and resolved `tool_config` using the existing factory signature.
Multiple tools can reference the same connection while retaining their own
purpose and guidelines. Startup rejects missing references and mixed inline/named
settings. Existing tools without `connection_name` retain their factory behavior.
Migrate older entries containing both `connection_name` and inline settings by
moving `connector` and `configuration` to the named connection.

Generic named-connection resolution lives in `config/settings.py`. The base template
has no `tools/connection.py`. When an approved workflow assigns a connector, its
owning skill generates the connector-specific connection module and tool module
from assets, updates the named connection and factory mappings, and adds its
runtime dependencies, environment examples and documentation. Tool-free workflows
need no connection module. Credentials remain in environment variables or the
configured secrets manager, never in either YAML file.

MCP servers are declared separately in `config/mcp.yaml`:

```yaml
servers:
  catalog:
    transport: streamable_http
    url: https://mcp.example.com/mcp
    headers:
      Authorization: ${MCP_CATALOG_AUTHORIZATION}
```

Supported configuration transports are `stdio`, `sse`, and `streamable_http`.
This POC validates MCP declarations and agent references. Until an MCP adapter is
added to the reusable runtime, startup validation rejects non-empty agent
`mcp_servers` assignments instead of silently ignoring them.

For structured agent responses, replace `output_field` with an `output_mapping`.
The runtime builds a Pydantic response schema from the mapping; keys are structured
response fields and values are workflow state fields:

```yaml
writes_state:
  - sentiment
  - confidence
output_mapping:
  classification: sentiment
  score: confidence
```

## Graph Configuration

Declare graph-wide state explicitly in `graph/state.py`. `Required` controls the
public API requirement, `Annotated` attaches reducers, and `state_defaults()`
provides isolated defaults for each run. Define `InputState`, `OutputState`, and
`State` (combining both) with exact field names and types.

Agent nodes reference an entry from `agents.yaml`:

Every deterministic node exposes its operation contract in configuration. Its
node ID selects the direct Python callable from `NODE_REGISTRY`. All deterministic
nodes declare `reads_state`, `writes_state`, and optional `metadata` describing
parameters and behavior.

`operation_type`, `description`, and `metadata.parameters` are descriptive,
requirement-derived metadata. They are available to validation and workflow UIs
but are not executed by the graph runtime. This keeps one consistent
implementation path for input validation, routing calculations, custom algorithms,
and every other deterministic node.

Configure nodes, edges, conditional routing, and output mappings in `graph_config.yaml`.

Configuration validation requires operation metadata and declared state fields
for every deterministic node, plus an exact callable under the same node ID in
`NODE_REGISTRY`. Each direct function returns a partial state update.

Use direct edges for unconditional execution in `graph_config.yaml`.

Use a state field and path map for ordinary conditional routing:

Conditional edges use a `decision_field` referencing a state field, or a
`ROUTER_REGISTRY` key when routing depends on multiple state fields.

A registered router is ordinary testable Python and may evaluate several state
fields.

Keep all destinations in YAML so topology remains visible to configuration
validation and workflow UIs. A node must not mix outgoing mechanisms.

Use `Command(update=..., goto=...)` when a node must atomically update state and
choose its next destination. The corresponding `NODE_REGISTRY` callable returns
the command with both update and destination. Declare all possible destinations in
`command_destinations` so graph visualization and validation know the topology.

Use `Send` only for dynamic fan-out, where the number of worker invocations is
known at runtime rather than design time. The registered router returns one `Send`
per work item; destinations declared in YAML are used for validation.

Per-request dependencies and configuration belong in LangGraph runtime context,
not persisted workflow state. Define default values under `runtime_context` and
override them through the API request's `context` object. A node that needs these
values accepts a second `runtime` argument and reads `runtime.context["values"]`:

```yaml
runtime_context:
  defaults:
    locale: en-US
```

```python
def node(state: State, runtime: Runtime[RuntimeContext]) -> dict[str, str]:
    locale = runtime.context["values"]["locale"]
    return {"draft_response": render(state, locale=locale)}
```

Ordinary nodes remain one-argument callables. These advanced features are
independent and opt-in; subgraphs are intentionally outside the current template
contract.

## API

Request:

```http
POST /ask
Content-Type: application/json

{"thread_id": "<thread-id>", "context": {"locale": "en-US"}}
```

Response:

```json
{
  "thread_id": "<thread-id>",
  "status": "completed",
  "final_response": "...",
  "interrupts": []
}
```

The FastAPI path awaits `graph.ainvoke()` and never blocks the event loop with a
synchronous graph call. Persistence is enabled through the configured checkpointer.
Fully automatic graphs expose only `/ask`. A graph that deliberately uses
LangGraph interrupts can set `execution.resume_enabled: true` (with persistence
enabled) to expose `/resume` and continue a saved thread.
FastAPI lifespan validates configuration and compiles one reusable workflow at
startup, then closes graph and registered tool resources during shutdown.

Health endpoint: `GET /health`.

## Configuration

Provider defaults live in `config/models.yaml`. Each agent uses `model.primary`
and optional `model.fallback` sections in `config/agents.yaml`, matching the
LangChain stage model structure. Each supplied section requires `modelId` and
accepts optional `provider` and `generationDefaults`.

An omitted primary provider uses `models.yaml.default_provider`; a fallback
inherits the primary provider unless it supplies its own. Generation overrides
support `temperature`, `topP`, and `maxOutputTokens`, plus `presencePenalty` and
`frequencyPenalty` for OpenAI. Other profile fields are accepted as metadata;
they do not configure runtime safety or structured output.

Omitting `model.fallback` keeps the configured provider fallback. Set
`model.fallback: null` to disable it for one agent. Legacy scalar `provider` and
`model` entries remain supported.

Common environment variables:

- `OPENAI_API_KEY`, `ANTHROPICAI_API_KEY`, `GEMINIAI_API_KEY`, or
  `BEDROCK_AI_API_KEY`.
- `CLOUD_PROVIDER`: empty for local mode, `AWS`, or `AZURE`.
- `AZURE_KEY_VAULT_URL` and `AWS_REGION`.
- `AWS_REGION_NAME`: Amazon Bedrock model region.
- `TRACING_BACKEND`: `NONE` or `LANGSMITH`.
- `LANGSMITH_API_KEY` and `LANGSMITH_PROJECT`.
- `API_HOST`, `PORT`, and `API_ROOT_PATH`.
- `OUTPUT_DIR` and `REPORT_OUTPUT_FILE`.

## Running

```bash
uv sync --all-extras
uv run latest_ai_development
```

## Validation

```bash
uv sync --all-extras
uv run pytest -q
uv run ruff check src tests
uv run mypy src
uv run python -m compileall -q src tests
git diff --check
```

Startup validation rejects undefined agents or tools, invalid references,
undefined state reads/writes, unreachable nodes, paths without `END`, duplicate
edges, invalid route targets, and nodes that mix direct and conditional outgoing
routing.

## Extension Rules

For an ordinary agent addition, update only:

1. `config/agents.yaml`.
2. `config/graph_config.yaml`.
3. `graph/state.py` with the explicit typed workflow state.
4. A prompt file only when legacy file-based prompts are intentionally used;
   generated workflows normally keep prompts inline in `agents.yaml`.

The generated workflow should pass `tests/test_template.py` unchanged. The suite
derives its contract checks from configuration instead of hard-coding workflow
agent names.

Do not edit `graph/graph_builder.py`, `nodes/agent_node_builder.py`,
`tools/tool_registry.py`, `workflow.py`, `main.py`, model fallback, or tracking for
ordinary generated workflows.

<!-- BEGIN LANGGRAPH WORKFLOW -->
# Feedback Analyzer Workflow

This workflow consists of a single agent node named `feedback_analyzer` which analyzes customer feedback text to:

- Classify sentiment as one of Positive, Negative, Neutral, or Mixed.
- Generate a concise summary explanation clarifying the sentiment classification.
- Extract up to three key points explicitly mentioned in the feedback.

If the input feedback text is empty or insufficient for analysis, the workflow returns a Neutral sentiment, an explanatory summary, and an empty list of key points.

## Configuration

- Requires environment variables for OpenAI API access as specified in the `agents.yaml` model provider configuration.

## Usage

The workflow starts and ends at the `feedback_analyzer` node with no external tools or additional nodes.

## Input

- `feedback_text` (string): Customer feedback text to analyze.

## Output

- `sentiment` (string): Sentiment classification of the feedback.
- `summary` (string): Concise summary explanation clarifying the sentiment classification.
- `key_points` (array of strings): Up to three key points explicitly mentioned in the feedback.

---

This README is auto-generated and maintained by the LangGraph platform.
<!-- END LANGGRAPH WORKFLOW -->
