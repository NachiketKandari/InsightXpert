from __future__ import annotations

import json
import logging
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from insightxpert.agents.analyst import analyst_loop
from insightxpert.api.models import (
    ChatRequest,
    ConfigResponse,
    ConversationDetail,
    ConversationSummary,
    FeedbackRequest,
    MessageResponse,
    ProviderModels,
    RenameRequest,
    SchemaResponse,
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

    async def event_generator():
        actual_cid = ""
        async for chunk in analyst_loop(
            question=chat_req.message,
            llm=llm,
            db=db,
            rag=rag,
            config=settings,
            conversation_id=cid or persistent_cid,
            history=history,
        ):
            actual_cid = chunk.conversation_id
            chunk_json = chunk.model_dump_json()
            all_chunks.append(chunk_json)
            if chunk.type == "answer" and chunk.content:
                final_answer.append(chunk.content)
            yield {"data": chunk_json}
        yield {"data": "[DONE]"}

        # Save assistant answer to in-memory conversation memory
        store_cid = cid or actual_cid
        if store_cid and final_answer:
            conv_store.add_assistant_message(store_cid, final_answer[-1])

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
    async for chunk in analyst_loop(
        question=chat_req.message,
        llm=llm,
        db=db,
        rag=rag,
        config=settings,
        conversation_id=cid or persistent_cid,
        history=history,
    ):
        chunks.append(chunk.model_dump())
        if chunk.type == "answer" and chunk.content:
            final_answer = chunk.content

    store_cid = cid or (chunks[0]["conversation_id"] if chunks else "")
    if store_cid and final_answer:
        conv_store.add_assistant_message(store_cid, final_answer)

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
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
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

    ollama_models = list(OLLAMA_MODELS)
    try:
        import ollama as ollama_sdk
        client = ollama_sdk.Client(host=settings.ollama_base_url)
        response = client.list()
        local_models = [m.model.replace(":latest", "") for m in response.models]
        if local_models:
            ollama_models = local_models
    except Exception:
        pass

    providers = [
        ProviderModels(provider="gemini", models=GEMINI_MODELS),
        ProviderModels(provider="ollama", models=ollama_models),
    ]

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
