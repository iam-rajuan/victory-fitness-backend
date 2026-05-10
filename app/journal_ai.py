import json
from dataclasses import dataclass
from urllib import error, request

from .config import settings


JOURNAL_ANALYSIS_SYSTEM_PROMPT = (
    "You are the reflective journaling guide inside the Victory Fitness app. "
    "Analyze the user's journal entry in a clear, supportive, emotionally intelligent way. "
    "Do not sound clinical or robotic. "
    "Keep the response concise, practical, and grounded in the user's words. "
    "Return plain text only. "
    "Use short sections with labels when useful, such as Reflection, Pattern, Reframe, and Next Step. "
    "Do not use markdown tables, code blocks, or long disclaimers. "
    "Avoid therapy claims, diagnosis, or unsafe mental health advice."
)

REQUEST_TIMEOUT_SECONDS = 90


@dataclass
class JournalAnalysisResult:
    analysis: str


def generate_journal_analysis(payload: dict) -> JournalAnalysisResult:
    prompt = (
        "Analyze this journal entry and return a clearer reflective version that the user can keep in the journal text box.\n"
        "Preserve the meaning, but improve clarity and add concise insight.\n"
        f"Current mood: {payload.get('mood', '')}\n"
        f"Journal entry: {payload.get('content', '')}"
    )

    if settings.openai_api_key:
        return JournalAnalysisResult(analysis=_openai_journal_analysis(prompt))

    if settings.anthropic_api_key:
        return JournalAnalysisResult(analysis=_anthropic_journal_analysis(prompt))

    raise RuntimeError("No AI provider is configured for journal analysis")


def _openai_journal_analysis(prompt: str) -> str:
    request_payload = {
        "model": settings.openai_model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": JOURNAL_ANALYSIS_SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            },
        ],
        "max_output_tokens": 500,
    }

    data = _openai_responses_json(request_payload)
    text = _extract_response_text(data).strip()
    if not text:
        raise RuntimeError("OpenAI journal analysis response was empty")
    return text


def _anthropic_journal_analysis(prompt: str) -> str:
    payload = {
        "model": settings.anthropic_model,
        "system": JOURNAL_ANALYSIS_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 600,
        "temperature": 0.4,
    }

    req = request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except TimeoutError as exc:
        raise RuntimeError("Anthropic journal analysis request timed out") from exc
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Anthropic journal analysis request failed: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Anthropic journal analysis request failed: {exc.reason}") from exc

    try:
        text = "".join(
            part["text"]
            for part in data["content"]
            if isinstance(part, dict) and part.get("type") == "text" and part.get("text")
        ).strip()
    except (KeyError, TypeError) as exc:
        raise RuntimeError("Anthropic journal analysis response was missing text") from exc

    if not text:
        raise RuntimeError("Anthropic journal analysis response was empty")
    return text


def _openai_responses_json(payload: dict) -> dict:
    req = request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except TimeoutError as exc:
        raise RuntimeError("OpenAI journal analysis request timed out") from exc
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI journal analysis request failed: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenAI journal analysis request failed: {exc.reason}") from exc


def _extract_response_text(data: dict) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = data.get("output", [])
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue

            content = item.get("content", [])
            if not isinstance(content, list):
                continue

            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "output_text":
                    text = part.get("text", "")
                    if text:
                        parts.append(text)
                elif isinstance(part.get("text"), str) and part.get("text"):
                    parts.append(part["text"])

        if parts:
            return "".join(parts)

    raise RuntimeError("OpenAI journal analysis response was missing text")
