import asyncio
import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ...config import settings
from ...database import app_content_collection
from ...models import TranslationBatchRequest, TranslationBatchResponse

router = APIRouter()

_LANGUAGE_RE = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})?$")
_MAX_TEXT_LENGTH = 500


def _normalize_language(value: str) -> str:
    language = str(value or "").strip().lower()
    if not _LANGUAGE_RE.fullmatch(language):
        raise HTTPException(status_code=400, detail="Unsupported language")
    return language


def _normalize_texts(texts: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for text in texts:
        value = re.sub(r"\s+", " ", str(text or "")).strip()
        if not value or value in seen:
            continue
        if len(value) > _MAX_TEXT_LENGTH:
            value = value[:_MAX_TEXT_LENGTH].strip()
        seen.add(value)
        normalized.append(value)
    return normalized[:80]


def _cache_key(target_language: str, text: str) -> str:
    digest = hashlib.sha256(f"{target_language}\n{text}".encode("utf-8")).hexdigest()
    return f"i18n:{target_language}:{digest}"


async def _read_cached_translations(target_language: str, texts: list[str]) -> dict[str, str]:
    keys = [_cache_key(target_language, text) for text in texts]
    records = await app_content_collection.find({"_id": {"$in": keys}}).to_list(length=len(keys))
    by_key = {str(record.get("_id")): str(record.get("translated_text") or "") for record in records}
    return {
        text: by_key.get(_cache_key(target_language, text), "")
        for text in texts
        if by_key.get(_cache_key(target_language, text), "")
    }


async def _write_cached_translations(target_language: str, translations: dict[str, str]) -> None:
    now = datetime.now(timezone.utc)
    for source_text, translated_text in translations.items():
        if not translated_text:
            continue
        await app_content_collection.update_one(
            {"_id": _cache_key(target_language, source_text)},
            {
                "$set": {
                    "type": "i18n_translation",
                    "target_language": target_language,
                    "source_text": source_text,
                    "translated_text": translated_text,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )


def _openai_translate(target_language: str, texts: list[str]) -> dict[str, str]:
    if not settings.openai_api_key:
        return {}

    payload = {
        "model": settings.openai_model,
        "input": [
            {
                "role": "system",
                "content": (
                    "Translate Victory Fitness app UI copy from English into the requested target language. "
                    "Return only compact JSON mapping each exact source string to its translation. "
                    "Preserve placeholders like {name}, numbers, punctuation intent, product names, and short button tone."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"target_language": target_language, "texts": texts}, ensure_ascii=False),
            },
        ],
        "text": {"format": {"type": "json_object"}},
    }

    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=18) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return {}

    output_text = str(data.get("output_text") or "").strip()
    if not output_text:
        chunks: list[str] = []
        for item in data.get("output") or []:
            for content in item.get("content") or []:
                if content.get("type") in {"output_text", "text"}:
                    chunks.append(str(content.get("text") or ""))
        output_text = "\n".join(chunks).strip()

    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError:
        return {}

    if not isinstance(parsed, dict):
        return {}

    return {
        source: str(parsed.get(source) or "").strip()
        for source in texts
        if str(parsed.get(source) or "").strip()
    }


@router.post("/i18n/translate-batch", response_model=TranslationBatchResponse)
async def translate_batch(payload: TranslationBatchRequest) -> TranslationBatchResponse:
    target_language = _normalize_language(payload.target_language)
    source_language = _normalize_language(payload.source_language)
    texts = _normalize_texts(payload.texts)

    if not texts or target_language == source_language:
        return TranslationBatchResponse(target_language=target_language, translations={text: text for text in texts})

    cached = await _read_cached_translations(target_language, texts)
    missing = [text for text in texts if text not in cached]
    translated = await asyncio.to_thread(_openai_translate, target_language, missing) if missing else {}
    if translated:
        await _write_cached_translations(target_language, translated)

    return TranslationBatchResponse(
        target_language=target_language,
        translations={text: cached.get(text) or translated.get(text) or text for text in texts},
    )
