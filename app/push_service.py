import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4
from urllib.request import Request, urlopen

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


async def notify_user(users_collection, user: dict, title: str, message: str, notification_type: str, data: dict) -> None:
    notification = {"id": str(uuid4()), "type": notification_type, "title": title, "message": message, "data": data, "created_at": datetime.now(timezone.utc), "read": False}
    await users_collection.update_one({"_id": user["_id"]}, {"$push": {"app_notifications": {"$each": [notification], "$slice": -50}}})
    tokens = [str(item.get("token")) for item in (user.get("push_tokens") or []) if isinstance(item, dict) and str(item.get("platform") or "").lower() != "web" and str(item.get("token") or "").startswith("ExponentPushToken[")]
    if tokens:
        await asyncio.to_thread(_send_expo_push, list(dict.fromkeys(tokens)), title, message, data)


def _send_expo_push(tokens: list[str], title: str, body: str, data: dict) -> None:
    if not tokens:
        return
    messages = [{"to": token, "sound": "default", "title": title, "body": body, "data": data} for token in tokens]
    request = Request(EXPO_PUSH_URL, data=json.dumps(messages).encode("utf-8"), headers={"Accept": "application/json", "Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=15) as response:
        response.read()


async def notify_users_of_published_workout(users_collection, workout: dict) -> None:
    records = await users_collection.find({"is_admin": {"$ne": True}}).to_list(length=None)
    tokens = []
    notification = {
        "id": str(uuid4()),
        "type": "workout_published",
        "title": "New workout available",
        "message": f"{str(workout.get('title') or 'A new workout')} is now available in Victory Fitness.",
        "data": {"type": "workout", "workoutId": str(workout.get("_id") or "")},
        "created_at": datetime.now(timezone.utc),
        "read": False,
    }
    for user in records:
        await users_collection.update_one(
            {"_id": user["_id"]},
            {"$push": {"app_notifications": {"$each": [notification], "$slice": -50}}},
        )
        for item in user.get("push_tokens") or []:
            if isinstance(item, dict) and str(item.get("platform") or "").lower() != "web":
                token = str(item.get("token") or "").strip()
                if token.startswith("ExponentPushToken["):
                    tokens.append(token)
    await asyncio.to_thread(
        _send_expo_push,
        list(dict.fromkeys(tokens)),
        "New workout available",
        notification["message"],
        notification["data"],
    )
