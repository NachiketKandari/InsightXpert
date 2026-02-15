from __future__ import annotations

import json
import logging
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from insightxpert.agents.orchestrator import orchestrator_loop
from insightxpert.api.models import (
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
    SwitchModelRequest,
    SwitchModelResponse,
    TrainRequest,
    TrainResponse,
)
from insightxpert.auth.dependencies import get_current_user
from insightxpert.auth.models import User
from insightxpert.llm.factory import create_llm
from insightxpert.db.schema import get_schema_ddl

logger = logging.getLogger("insightxpert.api")

router = APIRouter(prefix="/api")


def _get_deps(request: Request):
    return (
        request.app.state.llm,
        request.app.state.db,
        request.app.state.rag,
        request.app.state.settings,
        request.app.state.conversation_store,
    )


def _prepare_chat(request: Request, chat_req: ChatRequest, user: User):
    """Shared setup for both SSE and poll chat endpoints.

    Returns (llm, db, rag, settings, conv_store, persistent_store, cid, persistent_cid, history).
    """
    llm, db, rag, settings, conv_store = _get_deps(request)
    persistent_store = request.app.state.persistent_conv_store

    cid = chat_req.conversation_id or ""
    history = conv_store.get_history(cid)

    if cid:
        conv_store.add_user_message(cid, chat_req.message)

    title = chat_req.message[:100]
    if cid:
        persistent_cid = cid
        try:
            persistent_store.get_or_create_conversation(cid, user.id, title)
        except Exception as e:
            logger.warning("Failed to ensure persistent conversation: %s", e)
    else:
        convo = persistent_store.create_conversation(user.id, title)
        persistent_cid = convo["id"]

    try:
        persistent_store.save_message(persistent_cid, user.id, "user", chat_req.message)
    except Exception as e:
        logger.warning("Failed to persist user message: %s", e)

    return llm, db, rag, settings, conv_store, persistent_store, cid, persistent_cid, history


@router.post("/chat")
async def chat_sse(
    chat_req: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    logger.info("POST /chat (SSE) message=%r conv=%s user=%s", chat_req.message[:80], chat_req.conversation_id, user.email)
    llm, db, rag, settings, conv_store, persistent_store, cid, persistent_cid, history = _prepare_chat(request, chat_req, user)

    final_answer: list[str] = []
    all_chunks: list[str] = []
    executed_sql: list[str] = []

    async def event_generator():
        actual_cid = ""
        async for chunk in orchestrator_loop(
            question=chat_req.message,
            llm=llm,
            db=db,
            rag=rag,
            config=settings,
            conversation_id=cid or persistent_cid,
            history=history,
            agent_mode=chat_req.agent_mode,
        ):
            actual_cid = chunk.conversation_id
            chunk_json = chunk.model_dump_json()
            all_chunks.append(chunk_json)
            if chunk.type == "sql" and chunk.sql:
                executed_sql.append(chunk.sql)
            if chunk.type == "answer" and chunk.content:
                final_answer.append(chunk.content)
            yield {"data": chunk_json}
        yield {"data": "[DONE]"}

        # Save assistant answer to in-memory conversation memory
        store_cid = cid or actual_cid
        if store_cid and final_answer:
            history_content = final_answer[-1]
            if executed_sql:
                sql_ctx = "; ".join(executed_sql)
                history_content = f"[SQL: {sql_ctx}]\n\n{history_content}"
            conv_store.add_assistant_message(store_cid, history_content)

        # Persist assistant message to SQLite
        if final_answer:
            try:
                chunks_blob = "[" + ",".join(all_chunks) + "]"
                persistent_store.save_message(
                    persistent_cid, user.id, "assistant", final_answer[-1], chunks_blob,
                )
            except Exception as e:
                logger.warning("Failed to persist assistant message: %s", e)

    return EventSourceResponse(event_generator())


@router.post("/chat/poll")
async def chat_poll(
    chat_req: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    logger.info("POST /chat/poll message=%r conv=%s user=%s", chat_req.message[:80], chat_req.conversation_id, user.email)
    llm, db, rag, settings, conv_store, persistent_store, cid, persistent_cid, history = _prepare_chat(request, chat_req, user)

    chunks: list[dict] = []
    final_answer = ""
    poll_executed_sql: list[str] = []
    async for chunk in orchestrator_loop(
        question=chat_req.message,
        llm=llm,
        db=db,
        rag=rag,
        config=settings,
        conversation_id=cid or persistent_cid,
        history=history,
        agent_mode=chat_req.agent_mode,
    ):
        chunks.append(chunk.model_dump())
        if chunk.type == "sql" and chunk.sql:
            poll_executed_sql.append(chunk.sql)
        if chunk.type == "answer" and chunk.content:
            final_answer = chunk.content

    store_cid = cid or (chunks[0]["conversation_id"] if chunks else "")
    if store_cid and final_answer:
        history_content = final_answer
        if poll_executed_sql:
            sql_ctx = "; ".join(poll_executed_sql)
            history_content = f"[SQL: {sql_ctx}]\n\n{history_content}"
        conv_store.add_assistant_message(store_cid, history_content)

    # Persist assistant message to SQLite
    if final_answer:
        try:
            chunks_blob = json.dumps(chunks)
            persistent_store.save_message(
                persistent_cid, user.id, "assistant", final_answer, chunks_blob,
            )
        except Exception as e:
            logger.warning("Failed to persist assistant message: %s", e)

    logger.info("POST /chat/poll done: %d chunks", len(chunks))
    return {"chunks": chunks}


@router.post("/train", response_model=TrainResponse)
async def train(
    req: TrainRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    logger.info("POST /train type=%s", req.type)
    _, _, rag, _, _ = _get_deps(request)

    if req.type == "qa_pair":
        sql = req.metadata.get("sql", "")
        doc_id = rag.add_qa_pair(req.content, sql, req.metadata)
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
    _, _, rag, _, _ = _get_deps(request)
    counts = rag.delete_all()
    logger.info("RAG embeddings deleted: %s", counts)
    return RagDeleteResponse(status="ok", deleted=counts)


@router.get("/schema", response_model=SchemaResponse)
async def schema(
    request: Request,
    user: User = Depends(get_current_user),
):
    _, db, _, _, _ = _get_deps(request)
    ddl = get_schema_ddl(db.engine)
    tables = db.get_tables()
    return SchemaResponse(ddl=ddl, tables=tables)


GEMINI_MODELS = [
    # Gemini 3 (Preview)
    "gemini-3-pro-preview",
    "gemini-3-flash-preview",
    # Gemini 2.5 (Stable)
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]

OLLAMA_MODELS = [
    "llama3.1",
    "llama3.2",
    "qwen2.5",
    "mistral",
    "phi3",
    "deepseek-r1",
    "codellama",
]


@router.get("/config", response_model=ConfigResponse)
async def get_config(
    request: Request,
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
        response = client.list()
        ollama_models = [m.model.replace(":latest", "") for m in response.models]
        if ollama_models:
            providers.append(ProviderModels(provider="ollama", models=ollama_models))
    except Exception:
        pass

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

    _, db, _, settings, _ = _get_deps(request)

    start = time.time()
    try:
        rows = db.execute(sql_text, row_limit=settings.sql_row_limit, timeout=settings.sql_timeout_seconds, read_only=True)
        ms = (time.time() - start) * 1000
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

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
    user: User = Depends(get_current_user),
):
    persistent_store = request.app.state.persistent_conv_store
    convos = persistent_store.get_conversations(user.id)
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

    messages = [
        MessageResponse(
            id=m["id"],
            role=m["role"],
            content=m["content"],
            chunks=json.loads(m["chunks_json"]) if m.get("chunks_json") else None,
            created_at=m["created_at"],
        )
        for m in convo["messages"]
    ]
    return ConversationDetail(
        id=convo["id"],
        title=convo["title"],
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
    from sqlalchemy.orm import Session
    from insightxpert.auth.models import FeedbackRecord

    engine = request.app.state.persistent_conv_store.engine
    try:
        with Session(engine) as session:
            record = FeedbackRecord(
                user_id=user.id,
                conversation_id=body.conversation_id,
                message_id=body.message_id,
                rating=body.rating,
                comment=body.comment or None,
            )
            session.add(record)
            session.commit()
    except Exception as e:
        logger.warning("Failed to save feedback: %s", e)
        raise HTTPException(status_code=500, detail="Failed to save feedback")
    return {"status": "ok"}
