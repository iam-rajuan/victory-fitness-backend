from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/admin/masterclasses", response_model=AdminMasterclassListResponse)

async def admin_list_masterclasses(

    _: dict = Depends(_require_admin_user),

) -> AdminMasterclassListResponse:

    items = [_serialize_admin_masterclass_item(item) for item in await _get_dashboard_masterclass_items()]

    return AdminMasterclassListResponse(items=[AdminMasterclassItem(**item) for item in items])

@router.post("/admin/masterclasses", response_model=AdminMasterclassItem, status_code=status.HTTP_201_CREATED)

async def admin_create_masterclass(

    payload: AdminMasterclassRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> AdminMasterclassItem:

    items = [_serialize_admin_masterclass_item(item) for item in await _get_dashboard_masterclass_items()]

    payload_data = payload.model_dump()

    try:

        payload_data["videoUrl"] = await _prepare_masterclass_video_payload(payload, str(admin_user["_id"]))

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if payload.audio_base64:

        try:

            payload_data["audioUrl"] = _upload_masterclass_audio_to_s3(

                str(admin_user["_id"]),

                payload.audio_base64,

                payload.audio_mime_type,

                payload.audio_file_name,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Masterclass audio upload failed: {exc}") from exc

    elif str(payload.audioUrl or "").strip():

        audio_value = str(payload.audioUrl or "").strip()

        if _looks_like_remote_media_url(audio_value):

            try:

                payload_data["audioUrl"] = _download_remote_media_to_storage(

                    "masterclass-audio",

                    str(admin_user["_id"]),

                    audio_value,

                    upload_log_label="audio",

                )

            except ValueError as exc:

                raise HTTPException(status_code=400, detail=str(exc)) from exc

            except Exception as exc:

                raise HTTPException(status_code=500, detail=f"Masterclass audio download failed: {exc}") from exc

        else:

            payload_data["audioUrl"] = audio_value

    masterclass = _serialize_admin_masterclass_item(

        {

            "id": uuid4().hex,

            **payload_data,

        }

    )

    items.insert(0, masterclass)

    await _replace_items_record(DASHBOARD_MASTERCLASSES_KEY, items)

    return AdminMasterclassItem(**masterclass)

@router.patch("/admin/masterclasses/{masterclass_id}", response_model=AdminMasterclassItem)

async def admin_update_masterclass(

    masterclass_id: str,

    payload: AdminMasterclassRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> AdminMasterclassItem:

    items = [_serialize_admin_masterclass_item(item) for item in await _get_dashboard_masterclass_items()]

    updated_masterclass: dict | None = None

    payload_data = payload.model_dump()

    try:

        payload_data["videoUrl"] = await _prepare_masterclass_video_payload(payload, str(admin_user["_id"]))

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if payload.clear_audio:

        payload_data["audioUrl"] = ""

    elif payload.audio_base64:

        try:

            payload_data["audioUrl"] = _upload_masterclass_audio_to_s3(

                str(admin_user["_id"]),

                payload.audio_base64,

                payload.audio_mime_type,

                payload.audio_file_name,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Masterclass audio upload failed: {exc}") from exc

    elif str(payload.audioUrl or "").strip():

        audio_value = str(payload.audioUrl or "").strip()

        if _looks_like_remote_media_url(audio_value):

            try:

                payload_data["audioUrl"] = _download_remote_media_to_storage(

                    "masterclass-audio",

                    str(admin_user["_id"]),

                    audio_value,

                    upload_log_label="audio",

                )

            except ValueError as exc:

                raise HTTPException(status_code=400, detail=str(exc)) from exc

            except Exception as exc:

                raise HTTPException(status_code=500, detail=f"Masterclass audio download failed: {exc}") from exc

        else:

            payload_data["audioUrl"] = audio_value

    for index, item in enumerate(items):

        if item["id"] == masterclass_id:

            items[index] = _serialize_admin_masterclass_item({"id": masterclass_id, **payload_data})

            updated_masterclass = items[index]

            break

    if not updated_masterclass:

        raise HTTPException(status_code=404, detail="Masterclass not found")

    await _replace_items_record(DASHBOARD_MASTERCLASSES_KEY, items)

    return AdminMasterclassItem(**updated_masterclass)

@router.delete("/admin/masterclasses/{masterclass_id}")

async def admin_delete_masterclass(

    masterclass_id: str,

    _: dict = Depends(_require_admin_user),

) -> dict[str, str]:

    items = [_serialize_admin_masterclass_item(item) for item in await _get_dashboard_masterclass_items()]

    next_items = [item for item in items if item["id"] != masterclass_id]

    if len(next_items) == len(items):

        raise HTTPException(status_code=404, detail="Masterclass not found")

    await _replace_items_record(DASHBOARD_MASTERCLASSES_KEY, next_items)

    return {"status": "success", "message": "Masterclass deleted"}
