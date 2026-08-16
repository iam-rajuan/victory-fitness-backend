from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/admin/community/posts", response_model=CommunityPostListResponse)

async def admin_get_community_posts(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str = Query(default="", max_length=160),
    _: dict = Depends(_require_admin_user),
) -> CommunityPostListResponse:

    query: dict[str, Any] = {}
    if search.strip():
        query["$or"] = [
            {"content": {"$regex": search.strip(), "$options": "i"}},
            {"author_name": {"$regex": search.strip(), "$options": "i"}},
        ]
    total = await community_posts_collection.count_documents(query)
    records = await community_posts_collection.find(

        query,

        sort=[("created_at", -1), ("_id", -1)],

        skip=(page - 1) * limit,
        limit=limit,

    ).to_list(length=limit)

    posts = await _serialize_community_post_records(records, None, comment_limit_per_post=200, include_reactions=True)

    return CommunityPostListResponse(

        posts=[CommunityPostResponse(**post) for post in posts], page=page, limit=limit, total=total, has_more=page * limit < total

    )

@router.get("/admin/community/feed", response_model=CommunityPostListResponse)
async def admin_get_community_feed(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str = Query(default="", max_length=160),
    admin_user: dict = Depends(_require_admin_user),
) -> CommunityPostListResponse:
    """Feed section endpoint kept separate from broadcast and analytics sections."""
    return await admin_get_community_posts(page=page, limit=limit, search=search, _=admin_user)

@router.post("/admin/community/posts", response_model=CommunityPostResponse, status_code=status.HTTP_201_CREATED)

async def admin_create_community_post(

    payload: AdminCommunityPostCreateRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> CommunityPostResponse:

    external_video_url = ""

    if payload.external_video_url:

        try:

            external_video_url = _resolve_media_url_to_storage(

                payload.external_video_url,

                folder_name="community-videos",

                user_id=str(admin_user["_id"]),

                upload_log_label="video",

                allow_embed_urls=True,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

    now = datetime.now(timezone.utc)

    image_url = ""

    video_url = ""

    if payload.image_base64:

        try:

            image_url = _upload_community_image_to_s3(

                str(admin_user["_id"]),

                payload.image_base64,

                payload.mime_type,

                payload.file_name,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Community image upload failed: {exc}") from exc

    elif payload.video_base64:

        try:

            video_url = _upload_community_video_to_s3(

                str(admin_user["_id"]),

                payload.video_base64,

                payload.mime_type,

                payload.file_name,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Community video upload failed: {exc}") from exc

    elif payload.audio_base64:
        try:
            audio_url = _upload_community_audio_to_s3(
                str(admin_user["_id"]), payload.audio_base64, payload.mime_type, payload.file_name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Community audio upload failed: {exc}") from exc

    elif external_video_url:

        video_url = external_video_url

    document = {

        "_id": ObjectId(),

        "author_id": str(admin_user["_id"]),

        "audience": payload.audience.strip(),

        "content": payload.content.strip(),

        "image_url": image_url,

        "video_url": video_url,

        "audio_url": audio_url,

        "like_count": 0,

        "comment_count": 0,

        "created_at": now,

        "updated_at": now,

    }

    await community_posts_collection.insert_one(document)

    serialized = await _serialize_community_post_records([document], admin_user, comment_limit_per_post=200, include_reactions=True)

    return CommunityPostResponse(**serialized[0])

@router.post("/admin/community/broadcast", response_model=CommunityPostResponse, status_code=status.HTTP_201_CREATED)
async def admin_send_community_broadcast(
    payload: AdminCommunityPostCreateRequest,
    admin_user: dict = Depends(_require_admin_user),
) -> CommunityPostResponse:
    """Broadcast section endpoint for publishing a tier-targeted community post."""
    result = await admin_create_community_post(payload, admin_user)
    await _record_admin_audit(admin_user, "broadcast_created", "community_post", result.id, {"audience": payload.audience})
    return result

@router.patch("/admin/community/posts/{post_id}", response_model=CommunityPostResponse)

async def admin_update_community_post(

    post_id: str,

    payload: AdminCommunityPostUpdateRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> CommunityPostResponse:

    try:

        object_id = ObjectId(post_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid community post id") from exc

    existing_record = await community_posts_collection.find_one({"_id": object_id})

    if not existing_record:

        raise HTTPException(status_code=404, detail="Community post not found")

    update_doc: dict = {"updated_at": datetime.now(timezone.utc)}

    external_video_url = None

    if payload.external_video_url is not None:

        external_raw = str(payload.external_video_url or "").strip()

        if external_raw:

            try:

                external_video_url = _resolve_media_url_to_storage(

                    external_raw,

                    folder_name="community-videos",

                    user_id=str(existing_record.get("author_id") or ""),

                    upload_log_label="video",

                    allow_embed_urls=True,

                )

            except ValueError as exc:

                raise HTTPException(status_code=400, detail=str(exc)) from exc

        else:

            external_video_url = ""

    if payload.content is not None:

        update_doc["content"] = payload.content.strip()

    if payload.audience is not None:

        update_doc["audience"] = payload.audience.strip()

    if payload.flagged is not None:
        update_doc["flagged"] = payload.flagged
        update_doc["flag_reason"] = payload.flag_reason.strip() if payload.flag_reason else ""

    if payload.moderation_status is not None:
        update_doc["moderation_status"] = payload.moderation_status
    if payload.moderator_notes is not None:
        update_doc["moderator_notes"] = payload.moderator_notes.strip()

    if payload.clear_image or payload.clear_media:

        update_doc["image_url"] = ""

        update_doc["video_url"] = ""

    elif payload.image_base64:

        try:

            update_doc["image_url"] = _upload_community_image_to_s3(

                str(existing_record.get("author_id") or ""),

                payload.image_base64,

                payload.mime_type,

                payload.file_name,

            )

            update_doc["video_url"] = ""

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Community image upload failed: {exc}") from exc

    elif payload.video_base64:

        try:

            update_doc["video_url"] = _upload_community_video_to_s3(

                str(existing_record.get("author_id") or ""),

                payload.video_base64,

                payload.mime_type,

                payload.file_name,

            )

            update_doc["image_url"] = ""

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Community video upload failed: {exc}") from exc

    elif external_video_url is not None:

        update_doc["video_url"] = external_video_url

        if external_video_url:

            update_doc["image_url"] = ""

    await community_posts_collection.update_one({"_id": object_id}, {"$set": update_doc})

    updated_record = await community_posts_collection.find_one({"_id": object_id})

    if not updated_record:

        raise HTTPException(status_code=500, detail="Community post could not be updated")

    serialized = await _serialize_community_post_records([updated_record], None, comment_limit_per_post=200, include_reactions=True)
    await _record_admin_audit(admin_user, "community_post_updated", "community_post", post_id, {"flagged": payload.flagged, "flag_reason": payload.flag_reason})

    return CommunityPostResponse(**serialized[0])

@router.delete("/admin/community/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)

async def admin_delete_community_post(

    post_id: str,

    _: dict = Depends(_require_admin_user),

) -> Response:

    try:

        object_id = ObjectId(post_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid community post id") from exc

    record = await community_posts_collection.find_one({"_id": object_id})

    if not record:

        raise HTTPException(status_code=404, detail="Community post not found")

    delete_result = await community_posts_collection.delete_one({"_id": object_id})

    if delete_result.deleted_count == 0:

        raise HTTPException(status_code=404, detail="Community post not found")

    _delete_community_post_media(record)

    await community_comments_collection.delete_many({"post_id": str(object_id)})

    await community_reactions_collection.delete_many({"post_id": str(object_id)})

    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/admin/community/top-contributors")
async def admin_get_community_top_contributors(_: dict = Depends(_require_admin_user)) -> dict[str, Any]:
    records = await community_posts_collection.find({}, sort=[("created_at", -1)]).to_list(length=500)
    posts = await _serialize_community_post_records(records, None, comment_limit_per_post=0, include_reactions=False)
    contributors: dict[str, dict[str, Any]] = {}
    for post in posts:
        author_id = str(post.get("author_id") or "")
        if not author_id:
            continue
        item = contributors.setdefault(author_id, {"userId": author_id, "name": str(post.get("author_name") or "Community member"), "profileImage": str(post.get("author_profile_image") or ""), "postCount": 0, "likeCount": 0})
        item["postCount"] += 1
        item["likeCount"] += max(int(post.get("like_count") or 0), 0)
    return {"contributors": sorted(contributors.values(), key=lambda item: (item["likeCount"], item["postCount"]), reverse=True)[:10]}

@router.get("/admin/community/trending")
async def admin_get_community_trending(_: dict = Depends(_require_admin_user)) -> dict[str, Any]:
    records = await community_posts_collection.find({}, {"content": 1}).to_list(length=500)
    counts: dict[str, int] = {}
    for record in records:
        for tag in re.findall(r"#[A-Za-z0-9_]+", str(record.get("content") or "").lower()):
            counts[tag] = counts.get(tag, 0) + 1
    return {"hashtags": [{"tag": tag, "postCount": count} for tag, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:20]]}

@router.get("/admin/community/flags")
async def admin_get_community_flags(_: dict = Depends(_require_admin_user)) -> dict[str, Any]:
    records = await community_posts_collection.find({"flagged": True}, sort=[("updated_at", -1)]).to_list(length=200)
    posts = await _serialize_community_post_records(records, None, comment_limit_per_post=0, include_reactions=False)
    return {"total": len(posts), "posts": posts}

@router.get("/admin/community/shortcuts")
async def admin_get_community_shortcuts(_: dict = Depends(_require_admin_user)) -> dict[str, Any]:
    flagged_count = await community_posts_collection.count_documents({"flagged": True})
    return {"items": [
        {"key": "flagged_posts", "label": "Review Flagged Posts", "route": "/community", "count": flagged_count},
        {"key": "pinned_announcements", "label": "Pinned Announcements", "route": "/community/announcements"},
        {"key": "community_guidelines", "label": "Community Guidelines", "route": "/community/guidelines"},
    ]}
