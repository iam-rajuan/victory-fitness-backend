from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

UNSUPPORTED_SOCKET_IO_REASON = "Unsupported Socket.IO client. Use /ws/... endpoints."


@router.websocket("/socket.io")
@router.websocket("/socket.io/")
async def unsupported_socket_io_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.close(code=1008, reason=UNSUPPORTED_SOCKET_IO_REASON)


@router.websocket("/ws/challenges/{challenge_id}/chat")
async def challenge_chat_socket(websocket: WebSocket, challenge_id: str) -> None:
    token = websocket.query_params.get("token", "").strip()

    if not token:
        await websocket.close(code=4401, reason="Missing access token")
        return

    try:
        user = await dependency_get_verified_user_from_access_token(token)
        _ensure_subscription_feature_access(
            user,
            "challenge",
            "Your current plan does not include challenge access",
        )
        membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))
        challenge = await _get_challenge_or_404(challenge_id)
        _ensure_challenge_read_access(membership, challenge)
    except HTTPException as exc:
        await websocket.close(code=4403 if exc.status_code == 403 else 4401, reason=str(exc.detail))
        return

    await challenge_chat_socket_manager.connect(challenge_id, websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        challenge_chat_socket_manager.disconnect(challenge_id, websocket)


@router.websocket("/ws/notifications")
async def notification_socket(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token", "").strip()

    if not token:
        await websocket.close(code=4401, reason="Missing access token")
        return

    try:
        user = await dependency_get_verified_user_from_access_token(token)
    except HTTPException as exc:
        await websocket.close(code=4403 if exc.status_code == 403 else 4401, reason=str(exc.detail))
        return

    user_id = str(user["_id"])
    await notification_socket_manager.connect(user_id, websocket)

    try:
        await websocket.send_json({"type": "connected"})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        notification_socket_manager.disconnect(user_id, websocket)
    except Exception:
        notification_socket_manager.disconnect(user_id, websocket)
