import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.challenge_terminology import (
    is_canonical_challenge_title,
    canonicalize_challenge_title,
    EXCLUDED_CHALLENGE_UI_KEYS,
)


def test_challenge_terminology_canonical_titles():
    # Canonical challenge titles must be recognized and protected
    assert is_canonical_challenge_title("21-Day Gold Beta") is True
    assert is_canonical_challenge_title("21-day gold beta") is True
    assert is_canonical_challenge_title("Core Crusher") is True
    assert is_canonical_challenge_title("Morning Mobility Challenge") is True
    assert is_canonical_challenge_title("30-Day Summer Shred") is True
    assert is_canonical_challenge_title("14-Day Reset Challenge") is True

    # Proper casing restored
    assert canonicalize_challenge_title("21-day gold beta") == "21-Day Gold Beta"
    assert canonicalize_challenge_title("core crusher") == "Core Crusher"


def test_challenge_terminology_excluded_ui_keys():
    # Surrounding UI keys must NOT be classified as challenge titles
    assert is_canonical_challenge_title("Challenge") is False
    assert is_canonical_challenge_title("Challenges") is False
    assert is_canonical_challenge_title("Challenge Chat") is False
    assert is_canonical_challenge_title("Challenge Library") is False
    assert is_canonical_challenge_title("Active Challenges") is False
    assert is_canonical_challenge_title("What To Do") is False
    assert is_canonical_challenge_title("Why It Matters") is False
    assert is_canonical_challenge_title("Join Challenge") is False


@pytest.mark.anyio
async def test_translate_batch_preserves_challenge_title_in_english():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/i18n/translate-batch",
            json={
                "target_language": "de",
                "source_language": "en",
                "texts": [
                    "21-Day Gold Beta",
                    "Core Crusher",
                    "Challenges",
                    "What To Do",
                ],
            },
        )
        assert response.status_code == 200
        data = response.json()
        translations = data.get("translations", {})

        # Challenge titles must remain strictly in English
        assert translations.get("21-Day Gold Beta") == "21-Day Gold Beta"
        assert translations.get("Core Crusher") == "Core Crusher"

        # Surrounding UI text is not forced to canonical challenge title
        assert translations.get("What To Do") is not None
