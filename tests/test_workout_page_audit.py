import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bson import ObjectId
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models import StrengthWorkoutSessionFeedbackRequest
from app.api.routers.ai_workout_plan import _adaptive_workout_adjustment


def test_adaptive_workout_adjustment_rubric():
    # 1. Too Easy / Easy
    req_easy = StrengthWorkoutSessionFeedbackRequest(
        day="Day 1",
        perceived_difficulty="too_easy",
        energy="high",
        soreness="low",
        notes="Felt light",
    )
    adj_pct, direction, summary, what_went_well, cautions, next_steps = _adaptive_workout_adjustment(req_easy)
    assert adj_pct == 5
    assert direction == "increase"
    assert "motor unit recruitment" in what_went_well
    assert "tempo control" in cautions

    # 2. Too Hard with Pain Flag
    req_hard_pain = StrengthWorkoutSessionFeedbackRequest(
        day="Day 1",
        perceived_difficulty="too_hard",
        energy="low",
        soreness="high",
        pain_flag=True,
    )
    adj_pct, direction, summary, what_went_well, cautions, next_steps = _adaptive_workout_adjustment(req_hard_pain)
    assert adj_pct == -10
    assert direction == "decrease"
    assert "Pain / discomfort noted" in cautions

    # 3. Just Right with Sweet Spot Flag
    req_just_right = StrengthWorkoutSessionFeedbackRequest(
        day="Day 2",
        perceived_difficulty="just_right",
        energy="medium",
        soreness="medium",
        sweet_spot_flag=True,
    )
    adj_pct, direction, summary, what_went_well, cautions, next_steps = _adaptive_workout_adjustment(req_just_right)
    assert adj_pct == 0
    assert direction == "maintain"
    assert "Sweet spot achieved" in what_went_well


@pytest.mark.anyio
async def test_workout_logs_pagination():
    fake_user_id = str(ObjectId())
    fake_user = {
        "_id": ObjectId(fake_user_id),
        "email": "test@victory.fit",
        "subscription_tier": "GOLD",
        "is_active": True,
    }

    # Mock 55 workout log documents
    mock_logs = []
    now = datetime.now(timezone.utc)
    for i in range(55):
        mock_logs.append({
            "_id": ObjectId(),
            "user_id": fake_user_id,
            "workout_id": f"workout-{i+1}",
            "title": f"Workout #{i+1}",
            "duration_seconds": 1800,
            "status": "completed",
            "market": "GB",
            "started_at": now,
            "completed_at": now,
        })

    class AsyncMockCursor:
        def __init__(self, data):
            self.data = data
            self.index = 0

        def sort(self, *args, **kwargs):
            return self

        def skip(self, count):
            self.data = self.data[count:]
            return self

        def limit(self, count):
            self.data = self.data[:count]
            return self

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.index < len(self.data):
                item = self.data[self.index]
                self.index += 1
                return item
            raise StopAsyncIteration

    mock_collection = MagicMock()
    mock_collection.count_documents = AsyncMock(return_value=55)
    mock_collection.find = MagicMock(side_effect=lambda query: AsyncMockCursor(list(mock_logs)))

    from app.core.legacy import dependency_require_access_user
    app.dependency_overrides[dependency_require_access_user] = lambda: fake_user

    try:
        with patch("app.api.routers.workout_logs.workout_logs_collection", mock_collection):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Page 1: Default 20 items
                res1 = await client.get("/workout-logs?page=1&limit=20")
                assert res1.status_code == 200
                data1 = res1.json()
                assert len(data1["items"]) == 20
                assert data1["total"] == 55
                assert data1["total_pages"] == 3
                assert data1["page"] == 1
                assert data1["limit"] == 20

                # Page 2: 20 items
                res2 = await client.get("/workout-logs?page=2&limit=20")
                assert res2.status_code == 200
                data2 = res2.json()
                assert len(data2["items"]) == 20
                assert data2["page"] == 2

                # Page 3: Remaining 15 items
                res3 = await client.get("/workout-logs?page=3&limit=20")
                assert res3.status_code == 200
                data3 = res3.json()
                assert len(data3["items"]) == 15
                assert data3["page"] == 3
    finally:
        app.dependency_overrides.pop(dependency_require_access_user, None)
