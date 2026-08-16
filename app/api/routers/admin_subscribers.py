from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/admin/subscribers", response_model=AdminSubscriberListResponse)

async def admin_list_subscribers(

    page: int = 1,

    limit: int = 100,

    query: str | None = None,

    _: dict = Depends(_require_admin_user),

) -> AdminSubscriberListResponse:

    records = await users_collection.find({"is_admin": {"$ne": True}}).to_list(length=None)

    subscribers = [

        _serialize_admin_subscriber_record(record)

        for record in records

        if _build_subscription_summary(record)["tier"] != "NONE"

    ]

    normalized_query = str(query or "").strip().lower()

    if normalized_query:

        subscribers = [

            item

            for item in subscribers

            if normalized_query in str(item["fullName"]).lower()

            or normalized_query in str(item["email"]).lower()

            or normalized_query in str(item["contactNumber"]).lower()

            or normalized_query in str(item["country"]).lower()

            or normalized_query in str(item["subscriptionTier"]).lower()

        ]

    subscribers.sort(key=lambda item: item["joinedDate"], reverse=True)

    safe_page = max(page, 1)

    safe_limit = max(limit, 1)

    start = (safe_page - 1) * safe_limit

    paged = subscribers[start:start + safe_limit]

    return AdminSubscriberListResponse(

        total=len(subscribers),

        page=safe_page,

        limit=safe_limit,

        users=[AdminSubscriberItem(**item) for item in paged],

    )
