from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.post("/journal/entries", response_model=JournalEntryResponse, status_code=status.HTTP_201_CREATED)

async def create_journal_entry(

    payload: JournalEntryCreateRequest,

    user: dict = Depends(_require_access_user),

) -> JournalEntryResponse:

    user_id = str(user["_id"])

    logger.info("journal_create_attempt user_id=%s", user_id)

    now = datetime.now(timezone.utc)

    document = {

        "user_id": user_id,

        "mood": payload.mood.strip(),

        "content": payload.content.strip(),

        "created_at": now,

        "updated_at": now,

    }

    insert_result = await journal_entries_collection.insert_one(document)

    logger.info("journal_create_success user_id=%s entry_id=%s", user_id, str(insert_result.inserted_id))

    return JournalEntryResponse(

        id=str(insert_result.inserted_id),

        user_id=user_id,

        mood=document["mood"],

        content=document["content"],

        created_at=now,

        updated_at=now,

    )

@router.get("/journal/entries", response_model=JournalEntryListResponse)

async def list_journal_entries(

    user: dict = Depends(_require_access_user),

) -> JournalEntryListResponse:

    user_id = str(user["_id"])

    logger.info("journal_list_attempt user_id=%s", user_id)

    records = await journal_entries_collection.find(

        {"user_id": user_id},

        sort=[("created_at", -1)],

    ).to_list(length=None)

    entries = [

        JournalEntryResponse(

            id=str(record["_id"]),

            user_id=record["user_id"],

            mood=record["mood"],

            content=record["content"],

            created_at=record["created_at"],

            updated_at=record["updated_at"],

        )

        for record in records

    ]

    logger.info("journal_list_success user_id=%s count=%s", user_id, len(entries))

    return JournalEntryListResponse(entries=entries)

@router.get("/journal/entries/{entry_id}", response_model=JournalEntryResponse)

async def get_journal_entry(

    entry_id: str,

    user: dict = Depends(_require_access_user),

) -> JournalEntryResponse:

    user_id = str(user["_id"])

    logger.info("journal_get_attempt user_id=%s entry_id=%s", user_id, entry_id)

    try:

        object_id = ObjectId(entry_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid journal entry id") from exc

    record = await journal_entries_collection.find_one({"_id": object_id, "user_id": user_id})

    if not record:

        raise HTTPException(status_code=404, detail="Journal entry not found")

    logger.info("journal_get_success user_id=%s entry_id=%s", user_id, entry_id)

    return JournalEntryResponse(

        id=str(record["_id"]),

        user_id=record["user_id"],

        mood=record["mood"],

        content=record["content"],

        created_at=record["created_at"],

        updated_at=record["updated_at"],

    )

@router.delete("/journal/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)

async def delete_journal_entry(

    entry_id: str,

    user: dict = Depends(_require_access_user),

) -> Response:

    user_id = str(user["_id"])

    logger.info("journal_delete_attempt user_id=%s entry_id=%s", user_id, entry_id)

    try:

        object_id = ObjectId(entry_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid journal entry id") from exc

    delete_result = await journal_entries_collection.delete_one({"_id": object_id, "user_id": user_id})

    if delete_result.deleted_count == 0:

        raise HTTPException(status_code=404, detail="Journal entry not found")

    logger.info("journal_delete_success user_id=%s entry_id=%s", user_id, entry_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.patch("/journal/entries/{entry_id}", response_model=JournalEntryResponse)

async def update_journal_entry(

    entry_id: str,

    payload: JournalEntryUpdateRequest,

    user: dict = Depends(_require_access_user),

) -> JournalEntryResponse:

    user_id = str(user["_id"])

    logger.info("journal_update_attempt user_id=%s entry_id=%s", user_id, entry_id)

    try:

        object_id = ObjectId(entry_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid journal entry id") from exc

    existing_record = await journal_entries_collection.find_one({"_id": object_id, "user_id": user_id})

    if not existing_record:

        raise HTTPException(status_code=404, detail="Journal entry not found")

    now = datetime.now(timezone.utc)

    update_document = {

        "mood": payload.mood.strip(),

        "content": payload.content.strip(),

        "updated_at": now,

    }

    await journal_entries_collection.update_one(

        {"_id": object_id, "user_id": user_id},

        {"$set": update_document},

    )

    logger.info("journal_update_success user_id=%s entry_id=%s", user_id, entry_id)

    return JournalEntryResponse(

        id=str(existing_record["_id"]),

        user_id=existing_record["user_id"],

        mood=update_document["mood"],

        content=update_document["content"],

        created_at=existing_record["created_at"],

        updated_at=now,

    )

@router.post("/journal/analyze", response_model=JournalAnalysisResponse)

async def analyze_journal_entry(

    payload: JournalAnalysisRequest,

    user: dict = Depends(_require_access_user),

) -> JournalAnalysisResponse:

    user_id = str(user["_id"])

    logger.info("journal_analyze_attempt user_id=%s", user_id)

    try:

        result = generate_journal_analysis(payload.model_dump())

    except RuntimeError as exc:

        raise HTTPException(status_code=502, detail=f"Journal analysis unavailable: {exc}") from exc

    logger.info("journal_analyze_success user_id=%s", user_id)

    return JournalAnalysisResponse(analysis=result.analysis)

@router.post("/journal/analyze/latest", response_model=JournalLatestAnalysisResponse)

async def analyze_latest_journal_entry(

    user: dict = Depends(_require_access_user),

) -> JournalLatestAnalysisResponse:

    user_id = str(user["_id"])

    logger.info("journal_analyze_latest_attempt user_id=%s", user_id)

    record = await journal_entries_collection.find_one(

        {"user_id": user_id},

        sort=[("created_at", -1)],

    )

    if not record:

        raise HTTPException(status_code=404, detail="No journal entries found")

    entry = JournalEntryResponse(

        id=str(record["_id"]),

        user_id=record["user_id"],

        mood=record["mood"],

        content=record["content"],

        created_at=record["created_at"],

        updated_at=record["updated_at"],

    )

    try:

        result = generate_journal_analysis(

            {

                "mood": entry.mood,

                "content": entry.content,

            }

        )

    except RuntimeError as exc:

        raise HTTPException(status_code=502, detail=f"Journal analysis unavailable: {exc}") from exc

    logger.info("journal_analyze_latest_success user_id=%s entry_id=%s", user_id, entry.id)

    return JournalLatestAnalysisResponse(entry=entry, analysis=result.analysis)
