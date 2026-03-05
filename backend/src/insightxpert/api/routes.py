from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from insightxpert.agents.orchestrator import orchestrator_loop
from insightxpert.api.models import (
    ChatAnswerResponse,
    ChatChunk,
    ChatRequest,
    ConfigResponse,
    ConversationDetail,
    ConversationSummary,
    FeedbackRequest,
    MessageResponse,
    OllamaModelInfo,
    OllamaModelsResponse,
    OllamaPullRequest,
    ProviderModels,
    RagDeleteResponse,
    RenameRequest,
    SchemaResponse,
    SearchResultItem,
    SqlExecuteRequest,
    SqlExecuteResponse,
    StarRequest,
    SwitchModelRequest,
    SwitchModelResponse,
    TrainRequest,
    TrainResponse,
)
from sqlalchemy.exc import OperationalError, ProgrammingError

from insightxpert.admin.config_store import read_config
from insightxpert.admin.models import ClientConfig
from insightxpert.admin.models import FeatureToggles
from insightxpert.auth.conversation_store import PersistentConversationStore
from insightxpert.auth.dependencies import get_current_user
from insightxpert.auth.models import User
from insightxpert.db.connector import FORBIDDEN_SQL_RE
from insightxpert.db.schema import get_schema_ddl
from insightxpert.exceptions import (
    DatabaseConnectionError,
    DatabaseError,
    QuerySyntaxError,
    QueryTimeoutError,
    ServiceUnavailableError,
)
from insightxpert.llm.factory import create_llm
from insightxpert.memory.conversation_store import ConversationStore

logger = logging.getLogger("insightxpert.api")

router = APIRouter(prefix="/api")

# TTL cache for the admin config — avoids a DB read on every chat request.
# 60-second TTL means config changes propagate quickly.
_config_cache: dict[str, tuple[float, ClientConfig]] = {}
_CONFIG_TTL = 60.0
_CONFIG_CACHE_KEY = "__db__"


def _get_cached_config(engine) -> ClientConfig:
    cached = _config_cache.get(_CONFIG_CACHE_KEY)
    if cached is not None:
        cached_at, config = cached
        if time.time() - cached_at < _CONFIG_TTL:
            return config
    config = read_config(engine)
    _config_cache[_CONFIG_CACHE_KEY] = (time.time(), config)
    return config


class _TokenCountingLLM:
    """Thin wrapper around any LLMProvider that accumulates token usage."""

    def __init__(self, llm) -> None:
        self._llm = llm
        self.input_tokens: int = 0
        self.output_tokens: int = 0

    @property
    def model(self) -> str:
        return self._llm.model

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        force_tool_use: bool = False,
    ):
        resp = await self._llm.chat(messages, tools, force_tool_use=force_tool_use)
        self.input_tokens += resp.input_tokens
        self.output_tokens += resp.output_tokens
        return resp


def _resolve_user_features(request: Request, user: User) -> FeatureToggles:
    """Return the resolved FeatureToggles for the given user based on admin config."""
    config = _get_cached_config(request.app.state.auth_engine)
    # Everyone starts from defaults (including admins and admin-domain users).
    # Org-mapped users get their org-specific overrides on top.
    features = config.defaults.features
    if not user.is_admin:
        domain = user.email.split("@")[1].lower()
        if domain not in [d.lower() for d in config.admin_domains]:
            email_lower = user.email.lower()
            for mapping in config.user_org_mappings:
                if mapping.email.lower() == email_lower:
                    org = config.organizations.get(mapping.org_id)
                    if org:
                        features = org.features
                    break

    return features


def _get_deps(request: Request):
    return (
        request.app.state.llm,
        request.app.state.db,
        request.app.state.rag,
        request.app.state.settings,
        request.app.state.conversation_store,
        getattr(request.app.state, "dataset_service", None),
        getattr(request.app.state, "external_db_service", None),
    )


async def _prepare_chat(request: Request, chat_req: ChatRequest, user: User):
    """Shared setup for both SSE and poll chat endpoints.

    DB calls are offloaded to a thread to avoid blocking the event loop.
    Returns (llm, db, rag, settings, conv_store, dataset_service, external_db_service, persistent_store, cid, persistent_cid, history).
    """
    llm, db, rag, settings, conv_store, dataset_service, external_db_service = (
        _get_deps(request)
    )
    persistent_store = request.app.state.persistent_conv_store

    cid = chat_req.conversation_id or ""
    history = conv_store.get_history(cid)

    # If in-memory history is empty but the conversation exists in the
    # persistent store, hydrate from the database so the LLM has context
    # from prior turns (e.g. after server restart or TTL expiry).
    if not history and cid:
        try:
            convo_data = await asyncio.to_thread(
                persistent_store.get_conversation, cid, user.id
            )
            if convo_data and convo_data.get("messages"):
                for m in convo_data["messages"]:
                    if m["role"] == "user":
                        conv_store.add_user_message(cid, m["content"])
                    elif m["role"] == "assistant":
                        conv_store.add_assistant_message(cid, m["content"])
                history = conv_store.get_history(cid)
                logger.info(
                    "Hydrated %d history messages from persistent store for %s",
                    len(history),
                    cid,
                )
        except Exception as e:
            logger.warning(
                "Failed to hydrate history from persistent store: %s", e, exc_info=True
            )

    if cid:
        conv_store.add_user_message(cid, chat_req.message)

    title = chat_req.message[:100]
    if cid:
        persistent_cid = cid
        try:
            await asyncio.to_thread(
                persistent_store.get_or_create_conversation,
                cid,
                user.id,
                title,
                user.org_id,
            )
        except Exception as e:
            logger.error(
                "Failed to ensure persistent conversation: %s", e, exc_info=True
            )
            raise DatabaseError("Failed to create conversation")
    else:
        convo = await asyncio.to_thread(
            persistent_store.create_conversation, user.id, title, user.org_id
        )
        persistent_cid = convo["id"]

    try:
        await asyncio.to_thread(
            persistent_store.save_message,
            persistent_cid,
            user.id,
            "user",
            chat_req.message,
        )
    except Exception as e:
        logger.error("Failed to persist user message: %s", e, exc_info=True)

    return (
        llm,
        db,
        rag,
        settings,
        conv_store,
        dataset_service,
        external_db_service,
        persistent_store,
        cid,
        persistent_cid,
        history,
    )


def _persist_response(
    conv_store: ConversationStore,
    persistent_store: PersistentConversationStore,
    store_cid: str,
    persistent_cid: str,
    user_id: str,
    final_answer: str,
    executed_sql: list[str],
    chunks_blob: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    generation_time_ms: int | None = None,
    org_id: str | None = None,
    question: str | None = None,
) -> None:
    if store_cid and final_answer:
        history_content = final_answer
        if executed_sql:
            sql_ctx = "; ".join(executed_sql)
            history_content = f"[SQL: {sql_ctx}]\n\n{history_content}"
        conv_store.add_assistant_message(store_cid, history_content)

    if final_answer:
        try:
            message_id = persistent_store.save_message(
                persistent_cid,
                user_id,
                "assistant",
                final_answer,
                chunks_blob,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                generation_time_ms=generation_time_ms,
            )
        except Exception as e:
            logger.error("Failed to persist assistant message: %s", e, exc_info=True)
            message_id = None

        # Persist enrichment traces if present (legacy conversations)
        if message_id and chunks_blob:
            try:
                chunks = (
                    json.loads(chunks_blob)
                    if isinstance(chunks_blob, str)
                    else chunks_blob
                )
                trace_chunks = [
                    c
                    for c in chunks
                    if isinstance(c, dict) and c.get("type") == "enrichment_trace"
                ]
                if trace_chunks:
                    traces = [c.get("data", {}) for c in trace_chunks if c.get("data")]
                    if traces:
                        persistent_store.save_enrichment_traces(message_id, traces)
            except Exception as e:
                logger.error(
                    "Failed to persist enrichment traces: %s", e, exc_info=True
                )

        # Persist orchestrator plan and agent executions
        if message_id and chunks_blob:
            try:
                chunks = (
                    json.loads(chunks_blob)
                    if isinstance(chunks_blob, str)
                    else chunks_blob
                )
                plan_chunks = [
                    c
                    for c in chunks
                    if isinstance(c, dict) and c.get("type") == "orchestrator_plan"
                ]
                if plan_chunks:
                    plan_data = plan_chunks[0].get("data", {})
                    plan_id = persistent_store.save_orchestrator_plan(
                        message_id, plan_data
                    )

                    agent_trace_chunks = [
                        c
                        for c in chunks
                        if isinstance(c, dict) and c.get("type") == "agent_trace"
                    ]
                    if agent_trace_chunks and plan_id:
                        executions = [
                            c.get("data", {})
                            for c in agent_trace_chunks
                            if c.get("data")
                        ]
                        if executions:
                            persistent_store.save_agent_executions(
                                plan_id, message_id, executions
                            )
            except Exception as e:
                logger.error(
                    "Failed to persist orchestrator plan/executions: %s",
                    e,
                    exc_info=True,
                )

        # Persist insight only if quality evaluator deemed it a genuine insight
        if message_id and chunks_blob and question:
            try:
                chunks = (
                    json.loads(chunks_blob)
                    if isinstance(chunks_blob, str)
                    else chunks_blob
                )
                insight_chunks = [
                    c
                    for c in chunks
                    if isinstance(c, dict) and c.get("type") == "insight"
                ]
                if insight_chunks:
                    # Use the last insight chunk (investigation re-synthesis overrides initial)
                    last_insight = insight_chunks[-1]
                    insight_data = last_insight.get("data", {})

                    # Only save if the quality evaluator approved it
                    if not insight_data.get("save_as_insight", False):
                        logger.info(
                            "Insight quality gate: not saving (not deemed insightful)"
                        )
                    else:
                        insight_content = last_insight.get("content", "")
                        insight_summary = insight_data.get("insight_summary", "")
                        plan_chunks = [
                            c
                            for c in chunks
                            if isinstance(c, dict)
                            and c.get("type") == "orchestrator_plan"
                        ]
                        plan_data = (
                            plan_chunks[0].get("data", {}) if plan_chunks else {}
                        )
                        tasks = plan_data.get("tasks", [])
                        categories = list(
                            {t.get("category", "") for t in tasks if t.get("category")}
                        )
                        # Fall back to plan reasoning if evaluator didn't provide a summary
                        if not insight_summary:
                            insight_summary = plan_data.get("reasoning", "")
                        persistent_store.save_insight(
                            user_id=user_id,
                            org_id=org_id,
                            conversation_id=persistent_cid,
                            message_id=message_id,
                            title=question,
                            summary=insight_summary,
                            content=insight_content,
                            categories=categories,
                            enrichment_task_count=len(tasks),
                        )
            except Exception as e:
                logger.error("Failed to persist insight: %s", e, exc_info=True)


@router.post("/chat")
async def chat_sse(
    chat_req: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    logger.info(
        "POST /chat (SSE) message=%r conv=%s user=%s mode=%s",
        chat_req.message[:80],
        chat_req.conversation_id,
        user.email,
        chat_req.agent_mode,
    )
    (
        llm,
        db,
        rag,
        settings,
        conv_store,
        dataset_service,
        external_db_service,
        persistent_store,
        cid,
        persistent_cid,
        history,
    ) = await _prepare_chat(request, chat_req, user)
    features = _resolve_user_features(request, user)

    final_answer: list[str] = []
    all_chunks: list[str] = []
    executed_sql: list[str] = []
    counting_llm = _TokenCountingLLM(llm)

    async def event_generator():
        actual_cid = ""
        start_time = time.time()
        async for chunk in orchestrator_loop(
            question=chat_req.message,
            llm=counting_llm,
            db=db,
            rag=rag,
            config=settings,
            conversation_id=cid or persistent_cid,
            history=history,
            agent_mode=chat_req.agent_mode,
            dataset_service=dataset_service,
            skip_clarification=chat_req.skip_clarification,
            stats_context_injection=features.stats_context_injection,
            clarification_enabled=features.clarification_enabled,
            rag_retrieval=features.rag_retrieval,
            external_db_service=external_db_service,
            user_org_id=user.org_id,
            user_db_service=getattr(request.app.state, "user_db_service", None),
            user_id=user.id,
        ):
            actual_cid = chunk.conversation_id
            chunk_json = chunk.model_dump_json()
            all_chunks.append(chunk_json)
            if chunk.type == "sql" and chunk.sql:
                executed_sql.append(chunk.sql)
            if chunk.type in ("answer", "insight") and chunk.content:
                final_answer.append(chunk.content)
            yield {"data": chunk_json}

        generation_time_ms = int((time.time() - start_time) * 1000)

        # Emit observability metrics as a final chunk before [DONE]
        metrics_chunk = ChatChunk(
            type="metrics",
            data={
                "input_tokens": counting_llm.input_tokens,
                "output_tokens": counting_llm.output_tokens,
                "generation_time_ms": generation_time_ms,
            },
            conversation_id=cid or persistent_cid,
        )
        yield {"data": metrics_chunk.model_dump_json()}

        # Yield [DONE] immediately so the client stops spinning — the
        # persist is fire-and-forget in a background thread.
        yield {"data": "[DONE]"}

        store_cid = cid or actual_cid
        asyncio.ensure_future(
            asyncio.to_thread(
                _persist_response,
                conv_store,
                persistent_store,
                store_cid,
                persistent_cid,
                user.id,
                final_answer[-1] if final_answer else "",
                executed_sql,
                "[" + ",".join(all_chunks) + "]",
                counting_llm.input_tokens or None,
                counting_llm.output_tokens or None,
                generation_time_ms,
                org_id=user.org_id,
                question=chat_req.message,
            )
        )

    return EventSourceResponse(event_generator())


async def _run_orchestrator_to_completion(
    request: Request,
    body: ChatRequest,
    user: User,
) -> dict:
    """Run the orchestrator loop to completion and persist the response.

    Returns dict with keys: chunks, final_answer, sql, conversation_id
    """
    (
        llm,
        db,
        rag,
        settings,
        conv_store,
        dataset_service,
        external_db_service,
        persistent_store,
        cid,
        persistent_cid,
        history,
    ) = await _prepare_chat(request, body, user)
    features = _resolve_user_features(request, user)

    all_chunks: list[dict] = []
    final_answer = ""
    executed_sql: list[str] = []
    counting_llm = _TokenCountingLLM(llm)
    start_time = time.time()
    async for chunk in orchestrator_loop(
        question=body.message,
        llm=counting_llm,
        db=db,
        rag=rag,
        config=settings,
        conversation_id=cid or persistent_cid,
        history=history,
        agent_mode=body.agent_mode,
        dataset_service=dataset_service,
        skip_clarification=body.skip_clarification,
        stats_context_injection=features.stats_context_injection,
        clarification_enabled=features.clarification_enabled,
        rag_retrieval=features.rag_retrieval,
        external_db_service=external_db_service,
        user_org_id=user.org_id,
        user_db_service=getattr(request.app.state, "user_db_service", None),
        user_id=user.id,
    ):
        all_chunks.append(chunk.model_dump())
        if chunk.type == "sql" and chunk.sql:
            executed_sql.append(chunk.sql)
        if chunk.type in ("answer", "insight") and chunk.content:
            final_answer = chunk.content

    generation_time_ms = int((time.time() - start_time) * 1000)
    store_cid = cid or (all_chunks[0]["conversation_id"] if all_chunks else "")
    await asyncio.to_thread(
        _persist_response,
        conv_store,
        persistent_store,
        store_cid,
        persistent_cid,
        user.id,
        final_answer,
        executed_sql,
        json.dumps(all_chunks),
        counting_llm.input_tokens or None,
        counting_llm.output_tokens or None,
        generation_time_ms,
        org_id=user.org_id,
        question=body.message,
    )

    return {
        "chunks": all_chunks,
        "final_answer": final_answer,
        "sql": executed_sql,
        "conversation_id": persistent_cid,
    }


@router.post("/chat/poll")
async def chat_poll(
    chat_req: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    logger.info(
        "POST /chat/poll message=%r conv=%s user=%s",
        chat_req.message[:80],
        chat_req.conversation_id,
        user.email,
    )
    result = await _run_orchestrator_to_completion(request, chat_req, user)
    logger.info("POST /chat/poll done: %d chunks", len(result["chunks"]))
    return {"chunks": result["chunks"]}


@router.post("/chat/answer", response_model=ChatAnswerResponse)
async def chat_answer(
    chat_req: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Run the full pipeline and return only the final answer, conversation ID, and SQL."""
    logger.info(
        "POST /chat/answer message=%r conv=%s user=%s",
        chat_req.message[:80],
        chat_req.conversation_id,
        user.email,
    )
    result = await _run_orchestrator_to_completion(request, chat_req, user)
    logger.info("POST /chat/answer done: answer_len=%d", len(result["final_answer"]))
    return ChatAnswerResponse(
        answer=result["final_answer"],
        conversation_id=result["conversation_id"],
        sql=result["sql"],
    )


@router.post("/train", response_model=TrainResponse)
async def train(
    req: TrainRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    logger.info("POST /train type=%s", req.type)
    _, _, rag, _, _, _, _ = _get_deps(request)

    if req.type == "qa_pair":
        sql = req.metadata.get("sql", "")
        meta = {**req.metadata, "sql_valid": req.metadata.get("sql_valid", True)}
        doc_id = rag.add_qa_pair(req.content, sql, meta)
    elif req.type == "ddl":
        table_name = req.metadata.get("table_name", "")
        doc_id = rag.add_ddl(req.content, table_name)
    elif req.type == "documentation":
        doc_id = rag.add_documentation(req.content, req.metadata)
    else:
        logger.warning("Unknown train type: %s", req.type)
        return TrainResponse(status="error", id="")

    logger.info("Trained %s: id=%s", req.type, doc_id)
    return TrainResponse(status="ok", id=doc_id)


@router.delete("/rag", response_model=RagDeleteResponse)
async def delete_rag(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Delete all RAG embeddings from all collections (qa_pairs, ddl, docs, findings)."""
    logger.info("DELETE /rag requested by user=%s", user.email)
    _, _, rag, _, _, _, _ = _get_deps(request)
    counts = rag.delete_all()
    logger.info("RAG embeddings deleted: %s", counts)
    return RagDeleteResponse(status="ok", deleted=counts)


@router.get("/schema", response_model=SchemaResponse)
async def schema(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
):
    _, db, _, _, _, _, _ = _get_deps(request)
    ddl = get_schema_ddl(db.engine)
    tables = db.get_tables()
    response.headers["Cache-Control"] = "private, max-age=3600"
    return SchemaResponse(ddl=ddl, tables=tables)


GEMINI_MODELS = [
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]

VERTEX_AI_MODELS = [
    "zai-org/glm-5-maas",
]


@router.get("/config", response_model=ConfigResponse)
async def get_config(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
):
    settings = request.app.state.settings
    llm = request.app.state.llm

    current_provider = settings.llm_provider.value
    current_model = llm.model

    providers = [
        ProviderModels(provider="gemini", models=GEMINI_MODELS),
    ]

    # Advertise Vertex AI if GCP project is configured
    if settings.gcp_project_id:
        providers.append(ProviderModels(provider="vertex_ai", models=VERTEX_AI_MODELS))

    # Only advertise Ollama if it's actually reachable
    try:
        import ollama as ollama_sdk

        def _list_ollama():
            client = ollama_sdk.Client(host=settings.ollama_base_url)
            resp = client.list()
            return [m.model.replace(":latest", "") for m in resp.models]

        ollama_models = await asyncio.to_thread(_list_ollama)
        if ollama_models:
            providers.append(ProviderModels(provider="ollama", models=ollama_models))
    except Exception:
        logger.debug("Ollama not available for model listing", exc_info=True)

    response.headers["Cache-Control"] = "private, max-age=60"
    return ConfigResponse(
        current_provider=current_provider,
        current_model=current_model,
        providers=providers,
    )


@router.post("/config/switch", response_model=SwitchModelResponse)
async def switch_model(
    req: SwitchModelRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    settings = request.app.state.settings
    from insightxpert.config import LLMProvider as LLMProviderEnum

    # Validate Ollama model exists before creating the provider
    if req.provider == "ollama":
        try:
            import ollama as ollama_sdk

            def _check_ollama():
                client = ollama_sdk.Client(host=settings.ollama_base_url)
                client.show(req.model)

            await asyncio.to_thread(_check_ollama)
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail=f"Cannot reach Ollama or model '{req.model}' not found. "
                f"Ensure Ollama is running and the model is pulled. Error: {e}",
            )

    # Save original settings so we can roll back on failure
    prev_provider = settings.llm_provider
    prev_gemini_model = settings.gemini_model
    prev_ollama_model = settings.ollama_model
    prev_vertex_model = settings.vertex_ai_model

    if req.provider == "gemini":
        settings.llm_provider = LLMProviderEnum.GEMINI
        settings.gemini_model = req.model
    elif req.provider == "ollama":
        settings.llm_provider = LLMProviderEnum.OLLAMA
        settings.ollama_model = req.model
    elif req.provider == "vertex_ai":
        settings.llm_provider = LLMProviderEnum.VERTEX_AI
        settings.vertex_ai_model = req.model

    try:
        new_llm = create_llm(req.provider, settings)
    except ValueError as e:
        logger.warning("Model switch failed: %s", e)
        # Roll back settings on failure
        settings.llm_provider = prev_provider
        settings.gemini_model = prev_gemini_model
        settings.ollama_model = prev_ollama_model
        settings.vertex_ai_model = prev_vertex_model
        raise HTTPException(status_code=400, detail="Invalid model configuration")

    request.app.state.llm = new_llm
    logger.info("Switched LLM: provider=%s model=%s", req.provider, req.model)

    return SwitchModelResponse(provider=req.provider, model=req.model)


@router.post("/sql/execute", response_model=SqlExecuteResponse)
async def execute_sql(req: SqlExecuteRequest, request: Request):
    sql_text = req.sql.strip()
    if not sql_text:
        raise HTTPException(status_code=400, detail="SQL query cannot be empty")

    if FORBIDDEN_SQL_RE.search(sql_text):
        raise HTTPException(
            status_code=403,
            detail="Only read-only queries (SELECT, WITH, EXPLAIN) are allowed. "
            "INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, and other write operations are blocked.",
        )

    _, db, _, settings, _, _, _ = _get_deps(request)

    start = time.time()
    try:
        rows = db.execute(
            sql_text,
            row_limit=settings.sql_row_limit,
            timeout=settings.sql_timeout_seconds,
            read_only=True,
        )
        ms = (time.time() - start) * 1000
    except ProgrammingError as e:
        logger.warning("SQL syntax error: %s", e)
        raise QuerySyntaxError()
    except OperationalError as e:
        msg = str(e).lower()
        logger.warning("SQL operational error: %s", e)
        if "timeout" in msg or "timed out" in msg:
            raise QueryTimeoutError()
        if "connect" in msg or "connection" in msg:
            raise DatabaseConnectionError()
        raise DatabaseError()
    except Exception as e:
        logger.error("Unexpected DB error: %s", e, exc_info=True)
        raise DatabaseError()

    columns = list(rows[0].keys()) if rows else []
    return SqlExecuteResponse(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        execution_time_ms=round(ms, 2),
    )


@router.get("/sql/export-csv")
async def export_csv(request: Request, table: str = "transactions"):
    """Export an entire table as a CSV file download."""
    _, db, _, _, _, _, _ = _get_deps(request)

    # Validate table name against known tables to prevent SQL injection
    known_tables = db.get_tables()
    if table not in known_tables:
        raise HTTPException(status_code=400, detail=f"Unknown table: {table}")

    def generate():
        from sqlalchemy import text as sa_text

        with db.engine.connect() as conn:
            result = conn.execute(sa_text(f"SELECT * FROM {table}"))
            columns = list(result.keys())

            # Write header
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(columns)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

            # Stream rows in batches
            while True:
                rows = result.fetchmany(5000)
                if not rows:
                    break
                for row in rows:
                    output.seek(0)
                    output.truncate(0)
                    writer.writerow(row)
                    yield output.getvalue()

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="insightxpert-{table}.csv"'
        },
    )


@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": time.time()}


# --- Conversation CRUD ---------------------------------------------------


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
):
    persistent_store = request.app.state.persistent_conv_store
    convos = await asyncio.to_thread(
        persistent_store.get_conversations, user.id, user.org_id
    )
    response.headers["Cache-Control"] = "private, max-age=5"
    return [ConversationSummary(**c) for c in convos]


@router.get("/conversations/search", response_model=list[SearchResultItem])
async def search_conversations(
    request: Request,
    q: str = "",
    user: User = Depends(get_current_user),
):
    q = q.strip()
    if len(q) < 2:
        return []
    persistent_store = request.app.state.persistent_conv_store
    results = await asyncio.to_thread(
        persistent_store.search_conversations, user.id, q, org_id=user.org_id
    )
    return [SearchResultItem(**r) for r in results]


_HISTORY_ROW_LIMIT = 50


def _truncate_chunks(chunks: list[dict]) -> list[dict]:
    """Truncate large tool_result rows in historical chunks to reduce payload size."""
    out = []
    for chunk in chunks:
        if chunk.get("type") == "tool_result" and isinstance(chunk.get("data"), dict):
            data = chunk["data"]
            result_str = data.get("result")
            if isinstance(result_str, str):
                try:
                    result_obj = json.loads(result_str)
                    if isinstance(result_obj, dict) and isinstance(
                        result_obj.get("rows"), list
                    ):
                        original_count = len(result_obj["rows"])
                        if original_count > _HISTORY_ROW_LIMIT:
                            result_obj["rows"] = result_obj["rows"][:_HISTORY_ROW_LIMIT]
                            result_obj["truncated"] = True
                            result_obj["original_row_count"] = original_count
                            data = {**data, "result": json.dumps(result_obj)}
                            chunk = {**chunk, "data": data}
                except (json.JSONDecodeError, TypeError):
                    logger.debug(
                        "Could not parse tool_result for truncation, skipping chunk"
                    )
        elif chunk.get("type") == "enrichment_trace" and isinstance(
            chunk.get("data"), dict
        ):
            steps = chunk["data"].get("steps")
            if steps and isinstance(steps, list):
                for step in steps:
                    if step.get("type") == "tool_result" and step.get("result_data"):
                        rd = step["result_data"]
                        if isinstance(rd, str) and len(rd) > 2000:
                            # Truncate rows inside the JSON to keep it valid
                            try:
                                rd_obj = json.loads(rd)
                                if (
                                    isinstance(rd_obj.get("rows"), list)
                                    and len(rd_obj["rows"]) > 10
                                ):
                                    rd_obj["rows"] = rd_obj["rows"][:10]
                                    rd_obj["truncated"] = True
                                    step["result_data"] = json.dumps(rd_obj)
                                else:
                                    step["result_data"] = rd[:2000] + "…(truncated)"
                            except (json.JSONDecodeError, TypeError):
                                step["result_data"] = rd[:2000] + "…(truncated)"
        elif chunk.get("type") == "agent_trace" and isinstance(chunk.get("data"), dict):
            steps = chunk["data"].get("steps")
            if steps and isinstance(steps, list):
                for step in steps:
                    if step.get("result_preview"):
                        rp = step["result_preview"]
                        if isinstance(rp, str) and len(rp) > 2000:
                            step["result_preview"] = rp[:2000] + "…(truncated)"
        out.append(chunk)
    return out


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    persistent_store = request.app.state.persistent_conv_store
    convo = await asyncio.to_thread(
        persistent_store.get_conversation, conversation_id, user.id
    )
    if convo is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = []
    for m in convo["messages"]:
        chunks = None
        if m.get("chunks_json"):
            try:
                chunks = _truncate_chunks(json.loads(m["chunks_json"]))
            except (json.JSONDecodeError, TypeError):
                chunks = None
        messages.append(
            MessageResponse(
                id=m["id"],
                role=m["role"],
                content=m["content"],
                chunks=chunks,
                feedback=m.get("feedback"),
                feedback_comment=m.get("feedback_comment"),
                input_tokens=m.get("input_tokens"),
                output_tokens=m.get("output_tokens"),
                generation_time_ms=m.get("generation_time_ms"),
                created_at=m["created_at"],
            )
        )

    return ConversationDetail(
        id=convo["id"],
        title=convo["title"],
        is_starred=convo.get("is_starred", False),
        messages=messages,
        created_at=convo["created_at"],
        updated_at=convo["updated_at"],
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    persistent_store = request.app.state.persistent_conv_store
    deleted = await asyncio.to_thread(
        persistent_store.delete_conversation, conversation_id, user.id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "ok"}


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: str,
    body: RenameRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    persistent_store = request.app.state.persistent_conv_store
    renamed = await asyncio.to_thread(
        persistent_store.rename_conversation, conversation_id, user.id, body.title
    )
    if not renamed:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "ok"}


@router.patch("/conversations/{conversation_id}/star")
async def star_conversation(
    conversation_id: str,
    body: StarRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    store = request.app.state.persistent_conv_store
    ok = await asyncio.to_thread(
        store.star_conversation, conversation_id, user.id, body.starred
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "ok", "starred": body.starred}


# --- Ollama model management --------------------------------------------


def _get_ollama_client(request: Request):
    """Return an async Ollama client or raise 503 if Ollama is unreachable."""
    try:
        import ollama as ollama_sdk
    except ImportError:
        raise HTTPException(
            status_code=503, detail="ollama Python package is not installed"
        )
    settings = request.app.state.settings
    return ollama_sdk.AsyncClient(host=settings.ollama_base_url)


@router.post("/ollama/pull")
async def ollama_pull(
    body: OllamaPullRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Pull (download) an Ollama model. Streams progress via SSE."""
    client = _get_ollama_client(request)
    model_name = body.model
    logger.info("POST /ollama/pull model=%s user=%s", model_name, user.email)

    async def event_generator():
        try:
            stream = await client.pull(model=model_name, stream=True)
            async for progress in stream:
                status = (
                    progress.get("status", "")
                    if isinstance(progress, dict)
                    else getattr(progress, "status", "")
                )
                completed = (
                    progress.get("completed")
                    if isinstance(progress, dict)
                    else getattr(progress, "completed", None)
                )
                total = (
                    progress.get("total")
                    if isinstance(progress, dict)
                    else getattr(progress, "total", None)
                )
                digest = (
                    progress.get("digest")
                    if isinstance(progress, dict)
                    else getattr(progress, "digest", None)
                )

                event = {"status": status}
                if completed is not None and total is not None and total > 0:
                    event["completed"] = completed
                    event["total"] = total
                    event["percent"] = round(completed / total * 100, 1)
                if digest:
                    event["digest"] = digest

                yield {"data": json.dumps(event)}

            yield {"data": json.dumps({"status": "success", "model": model_name})}
        except Exception as e:
            logger.error("Ollama pull failed for %s: %s", model_name, e)
            yield {"data": json.dumps({"status": "error", "detail": str(e)})}

        yield {"data": "[DONE]"}

    return EventSourceResponse(event_generator())


@router.get("/ollama/models", response_model=OllamaModelsResponse)
async def ollama_list_models(
    request: Request,
    user: User = Depends(get_current_user),
):
    """List all locally available Ollama models."""
    client = _get_ollama_client(request)
    try:
        response = await client.list()
    except Exception as e:
        logger.warning("Cannot reach Ollama: %s", e)
        raise ServiceUnavailableError("Cannot reach Ollama")

    models = []
    for m in response.models:
        size_bytes = (
            m.size
            if isinstance(m.size, (int, float))
            else getattr(m.size, "real", None)
        )
        details = m.details
        models.append(
            OllamaModelInfo(
                model=(m.model or "").replace(":latest", ""),
                size_mb=round(size_bytes / 1_048_576, 1) if size_bytes else None,
                parameter_size=details.parameter_size if details else None,
                quantization=details.quantization_level if details else None,
                family=details.family if details else None,
            )
        )

    return OllamaModelsResponse(models=models)


@router.delete("/ollama/models/{model_name:path}")
async def ollama_delete_model(
    model_name: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Delete a locally downloaded Ollama model."""
    client = _get_ollama_client(request)
    logger.info("DELETE /ollama/models/%s user=%s", model_name, user.email)
    try:
        result = await client.delete(model_name)
        status = (
            result.get("status", "success")
            if isinstance(result, dict)
            else getattr(result, "status", "success")
        )
        return {"status": status, "model": model_name}
    except Exception as e:
        logger.warning("Failed to delete Ollama model '%s': %s", model_name, e)
        raise HTTPException(
            status_code=400, detail=f"Failed to delete model '{model_name}'"
        )


# --- Dataset Stats -------------------------------------------------------


@router.get("/stats")
async def get_dataset_stats(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Return all pre-computed dataset statistics grouped by stat_group and dimension."""
    auth_engine = request.app.state.auth_engine

    def _fetch_stats():
        from sqlalchemy import text as sa_text

        with auth_engine.connect() as conn:
            result = conn.execute(
                sa_text(
                    "SELECT stat_group, dimension, metric, value, string_value, updated_at "
                    "FROM dataset_stats ORDER BY stat_group, dimension, metric"
                )
            )
            return [dict(zip(result.keys(), row)) for row in result.fetchall()]

    try:
        rows = await asyncio.to_thread(_fetch_stats)
    except Exception as e:
        logger.error("Failed to fetch dataset stats: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch dataset stats")

    # Nest into groups -> dimensions -> metrics
    groups: dict[str, dict[str, dict]] = {}
    computed_at: str | None = None
    for row in rows:
        grp = row["stat_group"]
        dim = row["dimension"] or ""
        metric = row["metric"]
        val = row["string_value"] if row["string_value"] is not None else row["value"]
        if row.get("updated_at") and computed_at is None:
            computed_at = str(row["updated_at"])

        groups.setdefault(grp, {}).setdefault(dim, {})[metric] = val

    return {"groups": groups, "computed_at": computed_at}


# --- Feedback -----------------------------------------------------------


@router.post("/feedback")
async def submit_feedback(
    body: FeedbackRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    store = request.app.state.persistent_conv_store
    ok = await asyncio.to_thread(
        store.update_message_feedback,
        body.message_id,
        user.id,
        body.feedback,
        body.comment,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "ok"}
