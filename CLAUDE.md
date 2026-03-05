# Rules

- Never include "Generated with Claude Code" or similar attribution lines in PR descriptions, commit messages, or any generated content.

# InsightXpert

AI data analyst for the Techfest IIT Bombay Leadership Analytics Challenge.
Queries 250K synthetic Indian digital payment transactions via natural language using Vanna 2.0 + Gemini + SQLite.

## Project Structure

- `app/main.py` — FastAPI entry point, creates Agent and runs VannaFastAPIServer
- `app/agent.py` — Agent factory: wires LLM, tools, memory, system prompt
- `app/config.py` — Pydantic Settings (env vars / .env.local)
- `app/training/schema.py` — DDL for the `transactions` table
- `app/training/documentation.py` — Business context & column descriptions
- `app/training/queries.py` — Example question→SQL pairs
- `app/db/loader.py` — CSV→SQLite loader utility
- `data/` — CSV data files
- `prd/` — Problem statement & question bank

## Running

```bash
# Load data
python -m app.db.loader data/transactions.csv

# Start server
python -m app.main
```

## Key Config (env vars)

- `GOOGLE_API_KEY` — Gemini API key
- `GEMINI_MODEL` — model name (default: gemini-2.5-flash)
- `DATABASE_PATH` — SQLite DB path (default: ./insightxpert.db)
- `CHROMA_PERSIST_DIR` — ChromaDB persistence (default: ./chroma_data)

---

# Vanna 2.0 Reference

This project uses Vanna >= 2.0 (agent-based architecture). Below is a reference for the key APIs.

## Core Architecture

Vanna 2.0 is an agent framework for text-to-SQL. The main components are:

1. **Agent** — Main orchestrator for LLM interactions, tool execution, and conversation management
2. **ToolRegistry** — Manages and executes tools with permission validation
3. **LLM Service** — Interface to LLM providers (Anthropic, OpenAI, Google Gemini, Ollama, etc.)
4. **SQL Runner** — Executes SQL queries against databases
5. **Agent Memory** — Stores and retrieves tool usage patterns (ChromaDB, in-memory, etc.)
6. **UserResolver** — Extracts user identity from requests
7. **SystemPromptBuilder** — Builds the system prompt injected into every LLM call

## Key Imports Used in This Project

```python
from vanna import Agent, AgentConfig
from vanna.core.registry import ToolRegistry
from vanna.core.system_prompt import DefaultSystemPromptBuilder
from vanna.core.user import RequestContext, User, UserResolver
from vanna.integrations.chromadb import ChromaAgentMemory
from vanna.integrations.google.gemini import GeminiLlmService
from vanna.integrations.sqlite import SqliteRunner
from vanna.tools import LocalFileSystem, RunSqlTool, VisualizeDataTool
from vanna.servers.fastapi import VannaFastAPIServer
```

## Agent Class

`vanna.Agent` — Main agent that orchestrates LLM interactions, tool execution, and conversation management.

```python
class Agent:
    def __init__(
        self,
        llm_service: LlmService,
        tool_registry: ToolRegistry,
        user_resolver: UserResolver,
        agent_memory: AgentMemory,
        conversation_store: Optional[ConversationStore] = None,
        config: AgentConfig = AgentConfig(),
        system_prompt_builder: SystemPromptBuilder = DefaultSystemPromptBuilder(),
        lifecycle_hooks: List[LifecycleHook] = [],
        llm_middlewares: List[LlmMiddleware] = [],
        workflow_handler: Optional[WorkflowHandler] = None,
        error_recovery_strategy: Optional[ErrorRecoveryStrategy] = None,
        context_enrichers: List[ToolContextEnricher] = [],
        llm_context_enhancer: Optional[LlmContextEnhancer] = None,
        conversation_filters: List[ConversationFilter] = [],
        observability_provider: Optional[ObservabilityProvider] = None,
        audit_logger: Optional[AuditLogger] = None,
    )

    async def send_message(
        self,
        request_context: RequestContext,
        message: str,
        *,
        conversation_id: Optional[str] = None,
    ) -> AsyncGenerator[UiComponent, None]:
        """Process a user message and yield UI components."""
```

Seven extensibility points: `lifecycle_hooks`, `llm_middlewares`, `error_recovery_strategy`, `context_enrichers`, `llm_context_enhancer`, `conversation_filters`, `observability_provider`.

## AgentConfig

```python
class AgentConfig(BaseModel):
    max_tool_iterations: int = 10
    stream_responses: bool = True
    auto_save_conversations: bool = True
    include_thinking_indicators: bool = True
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    ui_features: UiFeatures = UiFeatures()
    audit_config: AuditConfig = AuditConfig()
```

## ToolRegistry

```python
class ToolRegistry:
    def register_local_tool(self, tool: Tool[Any], access_groups: List[str]) -> None: ...
    async def get_tool(self, name: str) -> Optional[Tool[Any]]: ...
    async def get_schemas(self, user: Optional[User] = None) -> List[ToolSchema]: ...
    async def execute(self, tool_call: ToolCall, context: ToolContext) -> ToolResult: ...
    async def transform_args(self, tool, args, user, context) -> Union[T, ToolRejection]: ...
```

## Tool Base Class

```python
class Tool(ABC, Generic[T]):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    def access_groups(self) -> List[str]:
        return []

    @abstractmethod
    def get_args_schema(self) -> Type[T]: ...

    @abstractmethod
    async def execute(self, context: ToolContext, args: T) -> ToolResult: ...
```

Built-in tools: `RunSqlTool`, `VisualizeDataTool`, `RunPythonFileTool`, `PipInstallTool`, `SearchFilesTool`, `ListFilesTool`, `ReadFileTool`, `WriteFileTool`.

## User & UserResolver

```python
class User(BaseModel):
    id: str
    username: Optional[str] = None
    email: Optional[str] = None
    metadata: Dict[str, Any] = {}
    group_memberships: List[str] = []

class UserResolver(ABC):
    @abstractmethod
    async def resolve_user(self, request_context: RequestContext) -> User: ...
```

## SystemPromptBuilder

```python
from vanna.core.system_prompt import DefaultSystemPromptBuilder

# Pass a custom base prompt:
builder = DefaultSystemPromptBuilder(base_prompt="Your system prompt here")
```

## LLM Services

```python
# Google Gemini (used in this project)
from vanna.integrations.google.gemini import GeminiLlmService
llm = GeminiLlmService(model="gemini-2.5-flash", api_key="...")

# Other providers:
from vanna.integrations.anthropic import AnthropicLlmService
from vanna.integrations.openai import OpenAILlmService
from vanna.integrations.azureopenai import AzureOpenAILlmService
from vanna.integrations.ollama import OllamaLlmService
```

## SQL Runners

```python
from vanna.integrations.sqlite import SqliteRunner       # used in this project
from vanna.integrations.postgres import PostgresRunner
from vanna.integrations.mysql import MysqlRunner
from vanna.integrations.snowflake import SnowflakeRunner
from vanna.integrations.bigquery import BigQueryRunner
from vanna.integrations.clickhouse import ClickHouseRunner
from vanna.integrations.duckdb import DuckDBRunner
```

## Agent Memory

```python
from vanna.integrations.chromadb import ChromaAgentMemory  # used in this project

memory = ChromaAgentMemory(
    persist_directory="./chroma_data",
    collection_name="insightxpert_memory",
)

# Other backends:
from vanna.integrations.local import MemoryAgentMemory     # in-memory
from vanna.integrations.faiss import FaissAgentMemory
from vanna.integrations.milvus import MilvusAgentMemory
```

Memory is automatic — when the agent successfully generates SQL, the question-SQL pair is saved. On new questions, similar past queries are retrieved and added to LLM context.

## FastAPI Server

```python
from vanna.servers.fastapi import VannaFastAPIServer

server = VannaFastAPIServer(agent)
server.run(host="0.0.0.0", port=8000)

# Provides:
# - POST /api/vanna/v2/chat_sse  (streaming chat endpoint)
# - GET /  (built-in web UI)
```

## Streaming UI Components

`agent.send_message()` yields UI components:
- `StatusBarUpdateComponent` — progress indicator
- `DataFrameComponent` — table results
- `PlotlyChartComponent` — visualizations
- `CodeBlockComponent` — SQL code
- `RichTextComponent` — AI summary
- `NotificationComponent` — success/error messages

## Custom Tool Example

```python
from vanna.core.tool import Tool, ToolContext, ToolResult
from pydantic import BaseModel, Field

class MyArgs(BaseModel):
    query: str = Field(description="The search query")

class MyTool(Tool[MyArgs]):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "Does something useful"

    def get_args_schema(self) -> Type[MyArgs]:
        return MyArgs

    async def execute(self, context: ToolContext, args: MyArgs) -> ToolResult:
        result = do_something(args.query)
        return ToolResult(
            success=True,
            result_for_llm=f"Result: {result}",
            ui_component=NotificationComponent(level="success", message="Done")
        )

# Register:
tool_registry.register_local_tool(MyTool(), access_groups=[])
```

## Row-Level Security

Override `transform_args` on `ToolRegistry` to modify SQL based on user identity:

```python
class RLSToolRegistry(ToolRegistry):
    async def transform_args(self, tool, args, user, context):
        if tool.name == "run_sql":
            # Add WHERE clause based on user.metadata
            ...
        return args
```

## Lifecycle Hooks

```python
from vanna.core.lifecycle import LifecycleHook

class MyHook(LifecycleHook):
    async def before_message(self, user, message, context): ...
    async def after_tool_execution(self, user, tool_name, result, context): ...
```

## Frontend Web Component

```html
<script src="https://img.vanna.ai/vanna-components.js"></script>
<vanna-chat
  sse-endpoint="https://your-api.com/api/vanna/v2/chat_sse"
  theme="dark">
</vanna-chat>
```

## Installation

```bash
pip install 'vanna[google,chromadb,fastapi]'  # what this project uses
pip install 'vanna[anthropic,postgres,visualization,chromadb]'  # full stack example
```
