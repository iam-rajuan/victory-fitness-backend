from ..database import workouts_collection


PUBLIC_WORKOUT_PROJECTION = {
    "_id": 1,
    "title": 1,
    "vimeo_id": 1,
    "video_url": 1,
    "video_source": 1,
    "tag": 1,
    "thumbnail": 1,
    "created_at": 1,
}


async def list_public_workout_records(filter_doc: dict) -> list[dict]:
    return await workouts_collection.find(
        filter_doc,
        projection=PUBLIC_WORKOUT_PROJECTION,
        sort=[("created_at", -1), ("_id", -1)],
    ).to_list(length=None)
