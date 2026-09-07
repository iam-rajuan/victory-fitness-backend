import mimetypes
from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/community/posts", response_model=CommunityPostListResponse)
async def get_community_posts(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    audience: str | None = Query(default=None),
    user: dict = Depends(_require_community_access_user),
) -> CommunityPostListResponse:
    query: dict[str, Any] = {}
    if audience and str(audience).strip().upper() != "ALL":
        query["audience"] = str(audience).strip().upper()
    total = await community_posts_collection.count_documents(query)
    records = await community_posts_collection.find(
        query,
        sort=[("created_at", -1), ("_id", -1)],
        skip=(page - 1) * limit,
        limit=limit,
    ).to_list(length=limit)

    posts = await _serialize_community_post_records(records, user, include_reactions=False)

    return CommunityPostListResponse(
        posts=[CommunityPostResponse(**post) for post in posts], page=page, limit=limit, total=total, has_more=page * limit < total
    )

@router.post("/community/posts", response_model=CommunityPostResponse, status_code=status.HTTP_201_CREATED)

async def create_community_post(

    request: Request,

    user: dict = Depends(_require_community_access_user),

) -> CommunityPostResponse:

    content = ""

    image_base64 = ""

    video_base64 = ""

    external_video_url_raw = ""

    mime_type = "image/jpeg"

    file_name: str | None = None

    image_url = ""

    video_url = ""

    audio_url = ""

    content_type = request.headers.get("content-type", "").lower()

    if "multipart/form-data" in content_type:

        form = await request.form()

        content = str(form.get("content") or "").strip()

        external_video_url_raw = str(form.get("external_video_url") or "").strip()

        mime_type = str(form.get("mime_type") or mime_type).strip() or mime_type

        file_name = str(form.get("file_name") or "").strip() or None

        media_file = form.get("media_file") or form.get("media")

        if media_file is not None and hasattr(media_file, "read") and hasattr(media_file, "filename"):

            try:

                payload = await media_file.read()

                if payload:

                    file_name = media_file.filename or file_name

                    raw_content_type = str(getattr(media_file, "content_type", "") or "").strip().lower()
                    detected_mime = raw_content_type
                    if not detected_mime or detected_mime in ("application/octet-stream", "binary/octet-stream"):
                        if file_name:
                            guessed_mime, _ = mimetypes.guess_type(file_name)
                            if guessed_mime:
                                detected_mime = guessed_mime.lower()
                        if (not detected_mime or detected_mime in ("application/octet-stream", "binary/octet-stream")) and mime_type and mime_type not in ("application/octet-stream", "binary/octet-stream"):
                            detected_mime = mime_type.lower()
                        if not detected_mime or detected_mime in ("application/octet-stream", "binary/octet-stream"):
                            lower_name = (file_name or "").lower()
                            if lower_name.endswith((".jpg", ".jpeg")):
                                detected_mime = "image/jpeg"
                            elif lower_name.endswith(".png"):
                                detected_mime = "image/png"
                            elif lower_name.endswith(".webp"):
                                detected_mime = "image/webp"
                            elif lower_name.endswith(".gif"):
                                detected_mime = "image/gif"
                            elif lower_name.endswith((".heic", ".heif")):
                                detected_mime = "image/heic"
                            elif lower_name.endswith(".mp4"):
                                detected_mime = "video/mp4"
                            elif lower_name.endswith(".mov"):
                                detected_mime = "video/quicktime"
                            elif lower_name.endswith(".webm"):
                                detected_mime = "video/webm"
                            elif lower_name.endswith(".m4v"):
                                detected_mime = "video/mp4"
                            elif lower_name.endswith((".ogg", ".ogv")):
                                detected_mime = "video/ogg"

                    mime_type = detected_mime or mime_type or "image/jpeg"

                    if mime_type.startswith("image/"):

                        if len(payload) > COMMUNITY_IMAGE_MAX_SIZE_BYTES:

                            raise HTTPException(

                                status_code=400,

                                detail=f"Image must be {COMMUNITY_IMAGE_MAX_SIZE_BYTES // (1024 * 1024)}MB or smaller",

                            )

                        try:

                            image_url = _upload_binary_bytes_to_s3(

                                "community-images",

                                str(user["_id"]),

                                payload,

                                mime_type,

                                file_name,

                                allowed_types={

                                    "image/jpeg": ".jpg",

                                    "image/jpg": ".jpg",

                                    "image/png": ".png",

                                    "image/webp": ".webp",

                                    "image/gif": ".gif",

                                    "image/heic": ".heic",

                                    "image/heif": ".heif",

                                },

                                invalid_type_message="Only JPEG, PNG, WEBP, GIF, and HEIC images are supported",

                                max_size_bytes=COMMUNITY_IMAGE_MAX_SIZE_BYTES,

                                upload_log_label="image",

                            )

                        except ValueError as exc:

                            raise HTTPException(status_code=400, detail=str(exc)) from exc

                        except Exception as exc:

                            raise HTTPException(status_code=500, detail=f"Community image upload failed: {exc}") from exc

                    elif mime_type.startswith("video/"):

                        if len(payload) > COMMUNITY_VIDEO_MAX_SIZE_BYTES:

                            raise HTTPException(

                                status_code=400,

                                detail=f"Video must be {COMMUNITY_VIDEO_MAX_SIZE_BYTES // (1024 * 1024)}MB or smaller",

                            )

                        try:

                            video_url = _upload_binary_bytes_to_s3(

                                "community-videos",

                                str(user["_id"]),

                                payload,

                                mime_type,

                                file_name,

                                allowed_types={

                                    "video/mp4": ".mp4",

                                    "video/quicktime": ".mov",

                                    "video/webm": ".webm",

                                    "video/x-m4v": ".m4v",

                                    "video/m4v": ".m4v",

                                    "video/ogg": ".ogv",

                                },

                                invalid_type_message="Only MP4, MOV, WEBM, and M4V videos are supported",

                                max_size_bytes=COMMUNITY_VIDEO_MAX_SIZE_BYTES,

                                upload_log_label="video",

                            )

                        except ValueError as exc:

                            raise HTTPException(status_code=400, detail=str(exc)) from exc

                        except Exception as exc:

                            raise HTTPException(status_code=500, detail=f"Community video upload failed: {exc}") from exc

                    else:

                        raise HTTPException(status_code=400, detail="Only image or video files are supported")

            finally:

                close_method = getattr(media_file, "close", None)

                if callable(close_method):

                    close_result = close_method()

                    if inspect.isawaitable(close_result):

                        await close_result

        image_base64 = str(form.get("image_base64") or "").strip()

        video_base64 = str(form.get("video_base64") or "").strip()

    else:

        try:

            raw_payload = await request.json()

        except Exception:

            raw_payload = {}

        payload = CommunityPostCreateRequest.model_validate(raw_payload)

        content = str(payload.content or "").strip()

        image_base64 = str(payload.image_base64 or "").strip()

        video_base64 = str(payload.video_base64 or "").strip()

        external_video_url_raw = str(payload.external_video_url or "").strip()

        mime_type = str(payload.mime_type or mime_type).strip() or mime_type

        file_name = str(payload.file_name or "").strip() or None

    external_video_url = ""

    if external_video_url_raw:

        try:

            external_video_url = _resolve_media_url_to_storage(

                external_video_url_raw,

                folder_name="community-videos",

                user_id=str(user["_id"]),

                upload_log_label="video",

                allow_embed_urls=True,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not content and not image_url and not video_url and not image_base64 and not video_base64 and not external_video_url:

        raise HTTPException(status_code=400, detail="Post content, image, video, or supported video link is required.")

    now = datetime.now(timezone.utc)

    if image_base64 and not image_url:

        try:

            image_url = _upload_community_image_to_s3(

                str(user["_id"]),

                image_base64,

                mime_type,

                file_name,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Community image upload failed: {exc}") from exc

    elif video_base64 and not video_url:

        try:

            video_url = _upload_community_video_to_s3(

                str(user["_id"]),

                video_base64,

                mime_type,

                file_name,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Community video upload failed: {exc}") from exc

    elif external_video_url:

        video_url = external_video_url

    document = {

        "_id": ObjectId(),

        "author_id": str(user["_id"]),

        "audience": _get_community_post_audience_for_user(user),

        "content": content,

        "image_url": image_url,

        "video_url": video_url,

        "like_count": 0,

        "comment_count": 0,
        "created_at": now,
        "updated_at": now,
    }

    is_workout_share = False
    if "form" in locals():
        is_workout_share = bool(form.get("is_workout_share")) or str(form.get("prefill_source") or "").strip().lower() in {"workout_completion", "workout_card"}
    elif "raw_payload" in locals() and isinstance(raw_payload, dict):
        is_workout_share = bool(raw_payload.get("is_workout_share")) or str(raw_payload.get("prefill_source") or "").strip().lower() in {"workout_completion", "workout_card"}

    if not is_workout_share and ("workout completed" in content.lower() or "#workoutcompleted" in content.lower() or ("streak" in content.lower() and "kcal" in content.lower())):
        is_workout_share = True

    if is_workout_share:
        document["is_workout_share"] = True
        try:
            if points_log_collection is not None:
                await points_log_collection.insert_one({
                    "user_id": str(user["_id"]),
                    "points": 30,
                    "reason": "Shared workout completion card to Community",
                    "created_at": now,
                })
            await users_collection.update_one({"_id": user["_id"]}, {"$inc": {"points": 30}})
        except Exception:
            pass

    await community_posts_collection.insert_one(document)

    serialized = await _serialize_community_post_records([document], user, include_reactions=False)

    return CommunityPostResponse(**serialized[0])

@router.delete("/community/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)

async def delete_own_community_post(

    post_id: str,

    user: dict = Depends(_require_community_access_user),

) -> Response:

    record = await _get_community_post_or_404(post_id)

    _ensure_community_post_access(record, user)

    if not _can_delete_community_post(record, user):

        raise HTTPException(status_code=403, detail="You can only delete your own post")

    await community_posts_collection.delete_one({"_id": record["_id"]})

    _delete_community_post_media(record)

    await community_comments_collection.delete_many({"post_id": str(record["_id"])})

    await community_reactions_collection.delete_many({"post_id": str(record["_id"])})

    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/community/posts/{post_id}/comments", response_model=list[CommunityCommentResponse])

async def get_community_post_comments(

    post_id: str,

    user: dict = Depends(_require_community_access_user),

) -> list[CommunityCommentResponse]:

    record = await _get_community_post_or_404(post_id)

    _ensure_community_post_access(record, user)

    comments = await _load_community_comments([record], limit_per_post=200)

    return [CommunityCommentResponse(**comment) for comment in comments.get(str(record["_id"]), [])]

@router.post("/community/posts/{post_id}/comments", response_model=CommunityCommentResponse, status_code=status.HTTP_201_CREATED)

async def create_community_post_comment(

    post_id: str,

    payload: CommunityCommentCreateRequest,

    user: dict = Depends(_require_community_access_user),

) -> CommunityCommentResponse:

    record = await _get_community_post_or_404(post_id)

    _ensure_community_post_access(record, user)

    now = datetime.now(timezone.utc)

    comment_document = {

        "_id": ObjectId(),

        "post_id": str(record["_id"]),

        "author_id": str(user["_id"]),

        "content": payload.content.strip(),

        "created_at": now,

    }

    await community_comments_collection.insert_one(comment_document)

    await community_posts_collection.update_one(

        {"_id": record["_id"]},

        {

            "$inc": {"comment_count": 1},

            "$set": {"updated_at": now},

        },

    )

    return CommunityCommentResponse(**_serialize_community_comment_record(comment_document, user))

@router.post("/community/posts/{post_id}/reactions/toggle", response_model=CommunityReactionToggleResponse)

async def toggle_community_post_reaction(

    post_id: str,

    user: dict = Depends(_require_community_access_user),

) -> CommunityReactionToggleResponse:

    record = await _get_community_post_or_404(post_id)

    _ensure_community_post_access(record, user)

    reaction_filter = {"post_id": str(record["_id"]), "user_id": str(user["_id"])}

    existing = await community_reactions_collection.find_one(reaction_filter)

    now = datetime.now(timezone.utc)

    if existing:

        await community_reactions_collection.delete_one({"_id": existing["_id"]})

        await community_posts_collection.update_one(

            {"_id": record["_id"]},

            {

                "$inc": {"like_count": -1},

                "$set": {"updated_at": now},

            },

        )

        viewer_has_liked = False

    else:

        await community_reactions_collection.insert_one(

            {

                "_id": ObjectId(),

                "post_id": str(record["_id"]),

                "user_id": str(user["_id"]),

                "created_at": now,

            }

        )

        await community_posts_collection.update_one(

            {"_id": record["_id"]},

            {

                "$inc": {"like_count": 1},

                "$set": {"updated_at": now},

            },

        )

        viewer_has_liked = True

    updated_record = await community_posts_collection.find_one({"_id": record["_id"]})

    like_count = int((updated_record or {}).get("like_count") or 0)

    if like_count < 0:

        like_count = 0

        await community_posts_collection.update_one({"_id": record["_id"]}, {"$set": {"like_count": 0}})

    return CommunityReactionToggleResponse(

        post_id=str(record["_id"]),

        like_count=like_count,

        viewer_has_liked=viewer_has_liked,

    )
