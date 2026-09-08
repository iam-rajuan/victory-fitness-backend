import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bson import ObjectId
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models import StrengthWorkoutSessionFeedbackRequest
from app.api.routers.ai_workout_plan import _adaptive_workout_adjustment
from app.api.routers import workout_logs as workout_logs_router


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


@pytest.mark.anyio
async def test_seven_day_workout_streak_awards_real_points_log(monkeypatch):
    fake_user_id = str(ObjectId())
    fake_user = {"_id": ObjectId(fake_user_id), "points": 100}
    now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    new_log_id = ObjectId()

    logs = [
        {
            "_id": ObjectId(),
            "user_id": fake_user_id,
            "status": "completed",
            "completed_at": now - timedelta(days=day),
        }
        for day in range(7)
    ]

    class AsyncListCursor:
        def __init__(self, data):
            self.data = data

        def sort(self, *args, **kwargs):
            return self

        async def to_list(self, length=None):
            return self.data

    class FakeWorkoutLogs:
        async def count_documents(self, query):
            return 0

        def find(self, query):
            return AsyncListCursor(logs)

    class FakePointsLog:
        def __init__(self):
            self.inserted = []

        async def count_documents(self, query):
            return 0

        async def insert_one(self, doc):
            self.inserted.append(doc)

    class FakeUsers:
        def __init__(self):
            self.updates = []

        async def update_one(self, query, update):
            self.updates.append((query, update))

    fake_points = FakePointsLog()
    fake_users = FakeUsers()
    monkeypatch.setattr(workout_logs_router, "workout_logs_collection", FakeWorkoutLogs())
    monkeypatch.setattr(workout_logs_router, "points_log_collection", fake_points)
    monkeypatch.setattr(workout_logs_router, "users_collection", fake_users)

    await workout_logs_router._award_streak_milestone_points(
        user_id=fake_user_id,
        user=fake_user,
        new_log_id=new_log_id,
        now=now,
    )

    assert len(fake_points.inserted) == 1
    assert fake_points.inserted[0]["points"] == 25
    assert fake_points.inserted[0]["event_type"] == "streak_milestone"
    assert fake_points.inserted[0]["streak_days"] == 7
    assert "7-day workout streak milestone" == fake_points.inserted[0]["reason"]
    assert fake_users.updates[0][1]["$inc"] == {"points": 25}
    assert fake_users.updates[0][1]["$set"]["streak_days"] == 7


@pytest.mark.anyio
async def test_streak_milestone_points_are_not_awarded_twice(monkeypatch):
    fake_user_id = str(ObjectId())
    now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    logs = [
        {
            "_id": ObjectId(),
            "user_id": fake_user_id,
            "status": "completed",
            "completed_at": now - timedelta(days=day),
        }
        for day in range(7)
    ]

    class AsyncListCursor:
        def __init__(self, data):
            self.data = data

        def sort(self, *args, **kwargs):
            return self

        async def to_list(self, length=None):
            return self.data

    class FakeWorkoutLogs:
        async def count_documents(self, query):
            return 0

        def find(self, query):
            return AsyncListCursor(logs)

    class FakePointsLog:
        async def count_documents(self, query):
            return 1

        async def insert_one(self, doc):
            raise AssertionError("duplicate streak awards must not be inserted")

    class FakeUsers:
        async def update_one(self, query, update):
            raise AssertionError("duplicate streak awards must not update points")

    monkeypatch.setattr(workout_logs_router, "workout_logs_collection", FakeWorkoutLogs())
    monkeypatch.setattr(workout_logs_router, "points_log_collection", FakePointsLog())
    monkeypatch.setattr(workout_logs_router, "users_collection", FakeUsers())

    await workout_logs_router._award_streak_milestone_points(
        user_id=fake_user_id,
        user={"_id": ObjectId(fake_user_id)},
        new_log_id=ObjectId(),
        now=now,
    )
