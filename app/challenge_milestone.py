import json
import logging
from urllib.request import Request, urlopen

from .config import settings

logger = logging.getLogger(__name__)


def fallback_challenge_milestone_message(name: str, title: str, day: int, total_days: int, status: str) -> str:
    member = name.strip() or "there"
    if status == "COMPLETED":
        return f"Amazing work, {member}! You completed all {total_days} days of {title}. You finished what you started."
    if day == 1:
        return f"Great first step, {member}! You completed day 1 of {title}. Come back tomorrow and keep the streak alive."
    if day * 2 >= total_days:
        return f"You are past the halfway point, {member}! Day {day} of {title} is complete. Keep your momentum going."
    return f"Well done, {member}! Day {day} of {title} is complete. One more milestone added to your progress."


def generate_challenge_milestone_message(name: str, title: str, day: int, total_days: int, status: str) -> str:
    fallback = fallback_challenge_milestone_message(name, title, day, total_days, status)
    if not settings.openai_api_key:
        return fallback
    prompt = (
        "Write one short, warm fitness-app notification (maximum 22 words) celebrating a user's completed challenge milestone. "
        "Do not mention AI, avoid guilt, and do not use emojis. "
        f"Name: {name or 'there'}; challenge: {title}; completed day: {day} of {total_days}; status: {status}."
    )
    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": "You write concise, encouraging milestone notifications."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 80,
    }
    try:
        request = Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
        message = str(data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        return message[:240] or fallback
    except Exception:
        logger.exception("challenge_milestone_ai_failed")
        return fallback
