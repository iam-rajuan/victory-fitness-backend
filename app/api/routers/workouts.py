from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/workouts/library", response_model=WorkoutLibraryResponse)

async def workout_library(query: str | None = None) -> WorkoutLibraryResponse:

    filter_doc: dict = {"visibility": "Published"}

    search = (query or "").strip()

    if search:

        escaped = re.escape(search)

        filter_doc["$or"] = [

            {"title": {"$regex": escaped, "$options": "i"}},

            {"tag": {"$regex": escaped, "$options": "i"}},

        ]

    records = await list_public_workout_records(filter_doc)

    workouts = [WorkoutLibraryItem(**shared_serialize_public_workout_record(record)) for record in records]

    category_map: dict[str, dict[str, object]] = {}

    for workout in workouts:

        key = workout.tag.strip() or "Workout"

        if key not in category_map:

            category_map[key] = {

                "id": key.lower().replace(" ", "-"),

                "name": key,

                "count": 0,

                "image": workout.thumbnail,

            }

        category_map[key]["count"] = int(category_map[key]["count"]) + 1

    categories = [

        WorkoutLibraryCategory(

            id=str(item["id"]),

            name=str(item["name"]),

            count=int(item["count"]),

            image=str(item["image"] or ""),

        )

        for item in sorted(category_map.values(), key=lambda item: (-int(item["count"]), str(item["name"])))

    ]

    return WorkoutLibraryResponse(

        featuredWorkout=workouts[0] if workouts else None,

        workouts=workouts,

        categories=categories,

    )
