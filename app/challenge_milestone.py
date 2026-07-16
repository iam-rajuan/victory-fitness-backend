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


def fallback_challenge_reminder_message(name: str, title: str, day: int, task_context: str) -> str:
    member = name.strip() or "there"
    task = task_context.strip() or "today's planned tasks"
    return f"Hi {member}, day {day} of {title} is waiting. Start with {task} to keep your progress moving."


def generate_challenge_reminder_message(name: str, title: str, day: int, task_context: str) -> str:
    fallback = fallback_challenge_reminder_message(name, title, day, task_context)
    if not settings.openai_api_key:
        return fallback
    task_label = task_context or "today's planned tasks"
    prompt = (
        "Write one concise, supportive fitness reminder (maximum 28 words) for a user who has not completed today's challenge tasks. "
        "Mention the relevant task, give one practical next step, avoid guilt, and do not mention AI or emojis. "
        f"Name: {name or 'there'}; challenge: {title}; day: {day}; tasks: {task_label}."
    )
    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": "You write specific, kind, actionable challenge reminders."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 100,
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
        return message[:280] or fallback
    except Exception:
        logger.exception("challenge_reminder_ai_failed")
        return fallback
