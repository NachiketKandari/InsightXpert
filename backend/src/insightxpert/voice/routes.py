from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlencode

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from insightxpert.auth.security import decode_access_token

logger = logging.getLogger("insightxpert.voice")

router = APIRouter(prefix="/api")

DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"


def _authenticate_ws(websocket: WebSocket) -> str | None:
    """Extract and validate JWT from WebSocket cookie or query param."""
    token = websocket.cookies.get("__session")
    if not token:
        token = websocket.query_params.get("token")
    if not token:
        logger.debug("WS auth: no token found in cookie or query param")
        return None

    settings = websocket.app.state.settings
    payload = decode_access_token(token, settings.secret_key)
    if payload is None:
        logger.debug("WS auth: token decode failed")
        return None
    user_id = payload.get("sub")
    logger.debug("WS auth: authenticated user_id=%s", user_id)
    return user_id


@router.websocket("/transcribe")
async def transcribe(websocket: WebSocket):
    """Proxy browser audio to Deepgram Nova-3 and stream transcripts back."""
    import websockets

    await websocket.accept()
    logger.debug("Voice WS accepted")

    user_id = _authenticate_ws(websocket)
    if not user_id:
        logger.warning("Voice WS rejected: not authenticated")
        await websocket.close(code=4001, reason="Not authenticated")
        return

    settings = websocket.app.state.settings
    if not settings.deepgram_api_key:
        logger.warning("Voice WS rejected: deepgram_api_key not configured")
        await websocket.close(code=4002, reason="Speech-to-text is not configured")
        return

    # Let Deepgram auto-detect encoding from WebM container headers.
    # Do NOT pass encoding/sample_rate — browser sends WebM/opus containers,
    # not raw opus frames.
    params = urlencode({
        "model": "nova-3",
        "language": "en",
        "punctuate": "true",
        "interim_results": "true",
        "utterance_end_ms": "1000",
        "smart_format": "true",
    })
    dg_url = f"{DEEPGRAM_WS_URL}?{params}"
    dg_headers = {"Authorization": f"Token {settings.deepgram_api_key}"}

    try:
        async with websockets.connect(dg_url, additional_headers=dg_headers) as dg_ws:
            logger.debug("Deepgram WS connected")

            async def browser_to_deepgram():
                try:
                    while True:
                        data = await websocket.receive_bytes()
                        await dg_ws.send(data)
                except WebSocketDisconnect:
                    logger.debug("Browser disconnected")
                except Exception as exc:
                    logger.warning("browser_to_deepgram error: %s", exc)

            async def deepgram_to_browser():
                try:
                    async for message in dg_ws:
                        await websocket.send_text(
                            message if isinstance(message, str) else message.decode()
                        )
                except Exception as exc:
                    logger.warning("deepgram_to_browser error: %s", exc)

            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(browser_to_deepgram()),
                    asyncio.create_task(deepgram_to_browser()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            logger.debug("Voice session ended for user_id=%s", user_id)

    except Exception as e:
        logger.warning("Deepgram connection failed: %s", e)
        try:
            await websocket.send_json({"error": "Voice connection failed"})
            await websocket.close(code=1011)
        except Exception:
            pass
