from __future__ import annotations

import json
import logging
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sse_starlette.sse import EventSourceResponse

from insightxpert.agents.orchestrator import orchestrator_loop
from insightxpert.api.models import (
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
from insightxpert.admin.models import FeatureToggles
from insightxpert.auth.conversation_store import PersistentConversationStore
from insightxpert.auth.dependencies import get_current_user
from insightxpert.auth.models import User
from insightxpert.db.schema import get_schema_ddl
from insightxpert.exceptions import (
    DatabaseConnectionError,
    DatabaseError,
    QuerySyntaxError,
    QueryTimeoutError,
)
from insightxpert.llm.factory import create_llm
from insightxpert.memory.conversation_store import ConversationStore

logger = logging.getLogger("insightxpert.api")

router = APIRouter(prefix="/api")


class _TokenCountingLLM:
    """Thin wrapper around any LLMProvider that accumulates token usage."""

    def __init__(self, llm) -> None:
        self._llm = llm
        self.input_tokens: int = 0
        self.output_tokens: int = 0

    @property
    def model(self) -> str:
        return self._llm.model

    async def chat(self, messages: list[dict], tools: list[dict] | None = None):
        resp = await self._llm.chat(messages, tools)
        self.input_tokens += resp.input_tokens
        self.output_tokens += resp.output_tokens
        return resp


def _resolve_user_features(request: Request, user: User) -> FeatureToggles:
    """Return the resolved FeatureToggles for the given user based on admin config."""
    config = read_config(request.app.state.config_path)
    # Admins bypass all restrictions; return defaults (everything enabled except what's off by default)
    if user.is_admin:
        return FeatureToggles()
    domain = user.email.split("@")[1].lower()
    if domain in [d.lower() for d in config.admin_domains]:
        return FeatureToggles()
    email_lower = user.email.lower()
    for mapping in config.user_org_mappings:
        if mapping.email.lower() == email_lower:
            org = config.organizations.get(mapping.org_id)
            if org:
                return org.features
    return config.defaults.features


def _get_deps(request: Request):
    return (
        request.app.state.llm,
        request.app.state.db,
        request.app.state.rag,
        request.app.state.settings,
        request.app.state.conversation_store,
        getattr(request.app.state, "dataset_service", None),
    )


def _prepare_chat(request: Request, chat_req: ChatRequest, user: User):
    """Shared setup for both SSE and poll chat endpoints.

    Returns (llm, db, rag, settings, conv_store, dataset_service, persistent_store, cid, persistent_cid, history).
    """
    llm, db, rag, settings, conv_store, dataset_service = _get_deps(request)
    persistent_store = request.app.state.persistent_conv_store

    cid = chat_req.conversation_id or ""
    history = conv_store.get_history(cid)

    # If in-memory history is empty but the conversation exists in the
    # persistent store, hydrate from the database so the LLM has context
    # from prior turns (e.g. after server restart or TTL expiry).
    if not history and cid:
        try:
            convo_data = persistent_store.get_conversation(cid, user.id)
            if convo_data and convo_data.get("messages"):
                for m in convo_data["messages"]:
                    if m["role"] == "user":
                        conv_store.add_user_message(cid, m["content"])
                    elif m["role"] == "assistant":
                        conv_store.add_assistant_message(cid, m["content"])
                history = conv_store.get_history(cid)
                logger.info("Hydrated %d history messages from persistent store for %s", len(history), cid)
        except Exception as e:
            logger.warning("Failed to hydrate history from persistent store: %s", e, exc_info=True)

    if cid:
        conv_store.add_user_message(cid, chat_req.message)

    title = chat_req.message[:100]
    if cid:
        persistent_cid = cid
        try:
            persistent_store.get_or_create_conversation(cid, user.id, title)
        except Exception as e:
            logger.error("Failed to ensure persistent conversation: %s", e, exc_info=True)
            raise DatabaseError(f"Failed to create conversation: {e}")
    else:
        convo = persistent_store.create_conversation(user.id, title)
        persistent_cid = convo["id"]

    try:
        persistent_store.save_message(persistent_cid, user.id, "user", chat_req.message)
    except Exception as e:
        logger.error("Failed to persist user message: %s", e, exc_info=True)

    return llm, db, rag, settings, conv_store, dataset_service, persistent_store, cid, persistent_cid, history


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
) -> None:
    if store_cid and final_answer:
        history_content = final_answer
        if executed_sql:
            sql_ctx = "; ".join(executed_sql)
            history_content = f"[SQL: {sql_ctx}]\n\n{history_content}"
        conv_store.add_assistant_message(store_cid, history_content)

    if final_answer:
        try:
            persistent_store.save_message(
                persistent_cid, user_id, "assistant", final_answer, chunks_blob,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                generation_time_ms=generation_time_ms,
            )
        except Exception as e:
            logger.error("Failed to persist assistant message: %s", e, exc_info=True)


@router.post("/chat")
async def chat_sse(
    chat_req: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    logger.info("POST /chat (SSE) message=%r conv=%s user=%s", chat_req.message[:80], chat_req.conversation_id, user.email)
    llm, db, rag, settings, conv_store, dataset_service, persistent_store, cid, persistent_cid, history = _prepare_chat(request, chat_req, user)
    features = _resolve_user_features(request, user)
    effective_skip_clarification = chat_req.skip_clarification or not features.clarification_enabled

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
            skip_clarification=effective_skip_clarification,
        ):
            actual_cid = chunk.conversation_id
            chunk_json = chunk.model_dump_json()
            all_chunks.append(chunk_json)
            if chunk.type == "sql" and chunk.sql:
                executed_sql.append(chunk.sql)
            if chunk.type == "answer" and chunk.content:
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

        # Persist BEFORE yielding [DONE] so that data is saved even if the
        # client disconnects immediately after receiving the sentinel.
        store_cid = cid or actual_cid
        _persist_response(
            conv_store, persistent_store, store_cid, persistent_cid, user.id,
            final_answer[-1] if final_answer else "",
            executed_sql,
            "[" + ",".join(all_chunks) + "]",
            input_tokens=counting_llm.input_tokens or None,
            output_tokens=counting_llm.output_tokens or None,
            generation_time_ms=generation_time_ms,
        )

        yield {"data": "[DONE]"}

    return EventSourceResponse(event_generator())


@router.post("/chat/poll")
async def chat_poll(
    chat_req: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    logger.info("POST /chat/poll message=%r conv=%s user=%s", chat_req.message[:80], chat_req.conversation_id, user.email)
    llm, db, rag, settings, conv_store, dataset_service, persistent_store, cid, persistent_cid, history = _prepare_chat(request, chat_req, user)
    features = _resolve_user_features(request, user)
    effective_skip_clarification = chat_req.skip_clarification or not features.clarification_enabled

    chunks: list[dict] = []
    final_answer = ""
    poll_executed_sql: list[str] = []
    poll_counting_llm = _TokenCountingLLM(llm)
    start_time = time.time()
    async for chunk in orchestrator_loop(
        question=chat_req.message,
        llm=poll_counting_llm,
        db=db,
        rag=rag,
        config=settings,
        conversation_id=cid or persistent_cid,
        history=history,
        agent_mode=chat_req.agent_mode,
        dataset_service=dataset_service,
        skip_clarification=effective_skip_clarification,
    ):
        chunks.append(chunk.model_dump())
        if chunk.type == "sql" and chunk.sql:
            poll_executed_sql.append(chunk.sql)
        if chunk.type == "answer" and chunk.content:
            final_answer = chunk.content

    generation_time_ms = int((time.time() - start_time) * 1000)
    store_cid = cid or (chunks[0]["conversation_id"] if chunks else "")
    _persist_response(
        conv_store, persistent_store, store_cid, persistent_cid, user.id,
        final_answer, poll_executed_sql, json.dumps(chunks),
        input_tokens=poll_counting_llm.input_tokens or None,
        output_tokens=poll_counting_llm.output_tokens or None,
        generation_time_ms=generation_time_ms,
    )

    logger.info("POST /chat/poll done: %d chunks", len(chunks))
    return {"chunks": chunks}


@router.post("/train", response_model=TrainResponse)
async def train(
    req: TrainRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    logger.info("POST /train type=%s", req.type)
    _, _, rag, _, _, _ = _get_deps(request)

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
    _, _, rag, _, _, _ = _get_deps(request)
    counts = rag.delete_all()
    logger.info("RAG embeddings deleted: %s", counts)
    return RagDeleteResponse(status="ok", deleted=counts)


@router.get("/schema", response_model=SchemaResponse)
async def schema(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
):
    _, db, _, _, _, _ = _get_deps(request)
    ddl = get_schema_ddl(db.engine)
    tables = db.get_tables()
    response.headers["Cache-Control"] = "private, max-age=3600"
    return SchemaResponse(ddl=ddl, tables=tables)


GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
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

    # Only advertise Ollama if it's actually reachable
    try:
        import ollama as ollama_sdk
        client = ollama_sdk.Client(host=settings.ollama_base_url)
        ollama_resp = client.list()
        ollama_models = [m.model.replace(":latest", "") for m in ollama_resp.models]
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
            client = ollama_sdk.Client(host=settings.ollama_base_url)
            client.show(req.model)
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

    if req.provider == "gemini":
        settings.llm_provider = LLMProviderEnum.GEMINI
        settings.gemini_model = req.model
    elif req.provider == "ollama":
        settings.llm_provider = LLMProviderEnum.OLLAMA
        settings.ollama_model = req.model

    try:
        new_llm = create_llm(req.provider, settings)
    except ValueError as e:
        # Roll back settings on failure
        settings.llm_provider = prev_provider
        settings.gemini_model = prev_gemini_model
        settings.ollama_model = prev_ollama_model
        raise HTTPException(status_code=400, detail=str(e))

    request.app.state.llm = new_llm
    logger.info("Switched LLM: provider=%s model=%s", req.provider, req.model)

    return SwitchModelResponse(provider=req.provider, model=req.model)


_FORBIDDEN_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|MERGE|GRANT|REVOKE|ATTACH|DETACH|PRAGMA\s+\w+\s*=)\b",
    re.IGNORECASE,
)


@router.post("/sql/execute", response_model=SqlExecuteResponse)
async def execute_sql(req: SqlExecuteRequest, request: Request):
    sql_text = req.sql.strip()
    if not sql_text:
        raise HTTPException(status_code=400, detail="SQL query cannot be empty")

    if _FORBIDDEN_SQL.search(sql_text):
        raise HTTPException(
            status_code=403,
            detail="Only read-only queries (SELECT, WITH, EXPLAIN) are allowed. "
                   "INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, and other write operations are blocked.",
        )

    _, db, _, settings, _, _ = _get_deps(request)

    start = time.time()
    try:
        rows = db.execute(sql_text, row_limit=settings.sql_row_limit, timeout=settings.sql_timeout_seconds, read_only=True)
        ms = (time.time() - start) * 1000
    except ProgrammingError as e:
        raise QuerySyntaxError(f"SQL syntax error: {e}")
    except OperationalError as e:
        msg = str(e).lower()
        if "timeout" in msg or "timed out" in msg:
            raise QueryTimeoutError(f"Query timed out: {e}")
        if "connect" in msg or "connection" in msg:
            raise DatabaseConnectionError(f"Database connection error: {e}")
        raise DatabaseError(f"Database operational error: {e}")
    except Exception as e:
        raise DatabaseError(f"Database error: {e}")

    columns = list(rows[0].keys()) if rows else []
    return SqlExecuteResponse(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        execution_time_ms=round(ms, 2),
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
    convos = persistent_store.get_conversations(user.id)
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
    results = persistent_store.search_conversations(user.id, q)
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
                    if isinstance(result_obj, dict) and isinstance(result_obj.get("rows"), list):
                        original_count = len(result_obj["rows"])
                        if original_count > _HISTORY_ROW_LIMIT:
                            result_obj["rows"] = result_obj["rows"][:_HISTORY_ROW_LIMIT]
                            result_obj["truncated"] = True
                            result_obj["original_row_count"] = original_count
                            data = {**data, "result": json.dumps(result_obj)}
                            chunk = {**chunk, "data": data}
                except (json.JSONDecodeError, TypeError):
                    logger.debug("Could not parse tool_result for truncation, skipping chunk")
        out.append(chunk)
    return out


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    persistent_store = request.app.state.persistent_conv_store
    convo = persistent_store.get_conversation(conversation_id, user.id)
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
        messages.append(MessageResponse(
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
        ))

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
    deleted = persistent_store.delete_conversation(conversation_id, user.id)
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
    renamed = persistent_store.rename_conversation(conversation_id, user.id, body.title)
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
    ok = store.star_conversation(conversation_id, user.id, body.starred)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "ok", "starred": body.starred}


# --- Ollama model management --------------------------------------------


def _get_ollama_client(request: Request):
    """Return an async Ollama client or raise 503 if Ollama is unreachable."""
    try:
        import ollama as ollama_sdk
    except ImportError:
        raise HTTPException(status_code=503, detail="ollama Python package is not installed")
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
                status = progress.get("status", "") if isinstance(progress, dict) else getattr(progress, "status", "")
                completed = progress.get("completed") if isinstance(progress, dict) else getattr(progress, "completed", None)
                total = progress.get("total") if isinstance(progress, dict) else getattr(progress, "total", None)
                digest = progress.get("digest") if isinstance(progress, dict) else getattr(progress, "digest", None)

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
        raise HTTPException(status_code=503, detail=f"Cannot reach Ollama: {e}")

    models = []
    for m in response.models:
        size_bytes = m.size if isinstance(m.size, (int, float)) else getattr(m.size, "real", None)
        details = m.details
        models.append(OllamaModelInfo(
            model=(m.model or "").replace(":latest", ""),
            size_mb=round(size_bytes / 1_048_576, 1) if size_bytes else None,
            parameter_size=details.parameter_size if details else None,
            quantization=details.quantization_level if details else None,
            family=details.family if details else None,
        ))

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
        status = result.get("status", "success") if isinstance(result, dict) else getattr(result, "status", "success")
        return {"status": status, "model": model_name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to delete model '{model_name}': {e}")


# --- Feedback -----------------------------------------------------------


@router.post("/feedback")
async def submit_feedback(
    body: FeedbackRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    store = request.app.state.persistent_conv_store
    ok = store.update_message_feedback(
        message_id=body.message_id,
        user_id=user.id,
        feedback=body.feedback,
        comment=body.comment,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "ok"}
