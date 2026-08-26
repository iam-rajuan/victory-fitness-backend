from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()


def _challenge_message_mentions_coach(content: str) -> bool:
    normalized = " ".join(str(content or "").strip().lower().split())
    if not normalized:
        return False
    coach_triggers = (
        "@coach",
        "@victor",
        "coach victor",
        "victor coach",
    )
    return any(trigger in normalized for trigger in coach_triggers)


async def _safe_notify_challenge_chat_participants(
    challenge_id: str,
    author_id: str,
    challenge_title: str,
    content: str,
) -> None:
    try:
        await _notify_challenge_chat_participants(challenge_id, author_id, challenge_title, content)
    except Exception as exc:
        logger.warning("challenge_chat_notification_task_failed challenge_id=%s error=%s", challenge_id, exc)


def _get_report_font(size: int, bold: bool = False) -> Any:
    _require_pillow()
    try:
        font_name = "arialbd.ttf" if bold else "arial.ttf"
        return ImageFont.truetype(font_name, size)
    except Exception:
        return ImageFont.load_default()


def _wrap_report_text_lines(draw: Any, text: str, font: Any, max_width: int, max_lines: int) -> list[str]:
    normalized = " ".join(str(text or "").split()).strip()
    if not normalized:
        return []
    words = normalized.split(" ")
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}".strip()
        box = draw.textbbox((0, 0), candidate, font=font)
        if box[2] - box[0] <= max_width:
            current = candidate
            continue
        lines.append(current)
        current = word
        if len(lines) >= max_lines - 1:
            break
    if len(lines) < max_lines:
        lines.append(current)
    remaining_words = words[len(" ".join(lines).split(" ")):]
    if remaining_words and lines:
        lines[-1] = lines[-1].rstrip(" .") + "..."
    return lines[:max_lines]


def _build_challenge_progress_report_png(
    challenge: dict,
    membership: dict,
    viewer_name: str,
    selected_day_number: int | None = None,
) -> tuple[bytes, str]:
    _require_pillow()

    plan_days = _get_normalized_plan_days(challenge)
    total_days = max(len(plan_days), int(challenge.get("duration_days") or 0), 1)
    viewer_plan_progress = _build_viewer_plan_progress(plan_days, membership or {})
    progress_by_day = {item.day_number: item for item in viewer_plan_progress}
    completed_days = _count_completed_plan_days_from_start(plan_days, membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {})
    challenge_points = max(int(challenge.get("points") or 0), 0)
    points_earned = _calculate_challenge_points_earned(plan_days, membership or {}, challenge_points)

    selected_day = None
    if selected_day_number is not None:
      selected_day = next((day for day in plan_days if int(day.get("day_number") or 0) == selected_day_number), None)
    if selected_day is None:
      selected_day = next((day for day in reversed(plan_days) if progress_by_day.get(int(day.get("day_number") or 0)) and progress_by_day[int(day.get("day_number") or 0)].completed), None)
    if selected_day is None and plan_days:
      selected_day = plan_days[0]

    selected_progress = progress_by_day.get(int(selected_day.get("day_number") or 0)) if selected_day else None
    completed_section_ids = set(selected_progress.completed_section_ids if selected_progress else [])
    completed_exercise_ids = set(selected_progress.completed_exercise_ids if selected_progress else [])

    exercise_entries: list[str] = []
    for section in (selected_day or {}).get("sections") or []:
        section_exercises = section.get("exercises") or []
        if completed_section_ids and str(section.get("id") or "") in completed_section_ids:
            exercise_entries.extend(str(exercise.get("name") or "Exercise") for exercise in section_exercises)
            continue
        for exercise in section_exercises:
            if not completed_exercise_ids or str(exercise.get("id") or "") in completed_exercise_ids:
                exercise_entries.append(str(exercise.get("name") or "Exercise"))
    exercise_entries = exercise_entries[:5]
    if not exercise_entries:
        exercise_entries = ["Keep going. Your progress is building day by day."]

    width, height = 1080, 1350
    image = Image.new("RGB", (width, height), "#06111D")
    draw = ImageDraw.Draw(image)

    cyan = "#21D4FD"
    cyan_soft = "#0E7490"
    white = "#F8FAFC"
    muted = "#94A3B8"
    muted_soft = "#CBD5E1"
    gold = "#F59E0B"
    pink = "#FF5C8A"
    navy_panel = "#0D1726"
    navy_card = "#121D30"
    outline = "#23344D"
    progress_track = "#1E293B"

    title_font = _get_report_font(60, bold=True)
    challenge_font = _get_report_font(40, bold=True)
    heading_font = _get_report_font(34, bold=True)
    section_font = _get_report_font(24, bold=True)
    body_font = _get_report_font(22, bold=False)
    small_font = _get_report_font(18, bold=False)
    micro_font = _get_report_font(16, bold=False)

    def center_text(y: int, text: str, font: Any, fill: str) -> None:
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(((width - (box[2] - box[0])) / 2, y), text, font=font, fill=fill)

    for dot_x in range(44, width - 44, 56):
        for dot_y in range(34, height - 34, 56):
            draw.ellipse((dot_x, dot_y, dot_x + 4, dot_y + 4), fill="#0C3A55")

    header_top = 88
    draw.rounded_rectangle((100, header_top, width - 100, 184), radius=28, fill=navy_panel, outline=outline, width=2)
    draw.rounded_rectangle((126, 108, 208, 160), radius=18, fill=cyan)
    draw.text((148, 118), "VF", font=_get_report_font(28, bold=True), fill="#04141D")
    draw.text((238, 110), "VICTORY FITNESS", font=section_font, fill=white)
    draw.text((238, 142), "Challenge Progress Card", font=small_font, fill=muted)

    center_text(228, "YOUR VICTORY", title_font, white)
    center_text(298, "CHALLENGE COMPLETED", section_font, cyan)

    challenge_title = str(challenge.get("title") or "Challenge").strip() or "Challenge"
    title_lines = _wrap_report_text_lines(draw, challenge_title.upper(), challenge_font, 760, 2)
    title_y = 360
    for line in title_lines:
        center_text(title_y, line, challenge_font, white)
        title_y += 48

    day_number = int(selected_day.get("day_number") or selected_day_number or 1) if selected_day else 1
    day_title = str(selected_day.get("title") or f"Day {day_number}").strip() if selected_day else f"Day {day_number}"
    day_focus = str(selected_day.get("focus") or "").strip() if selected_day else ""
    center_text(title_y + 8, f"DAY {day_number}", heading_font, gold)
    if day_title:
        day_title_lines = _wrap_report_text_lines(draw, day_title, body_font, 760, 2)
        line_y = title_y + 62
        for line in day_title_lines:
            center_text(line_y, line, body_font, muted_soft)
            line_y += 30
    if day_focus:
        focus_lines = _wrap_report_text_lines(draw, day_focus, small_font, 760, 2)
        line_y += 6
        for line in focus_lines:
            center_text(line_y, line, small_font, muted)
            line_y += 24

    content_top = 570
    draw.rounded_rectangle((84, content_top, width - 84, 980), radius=36, fill=navy_panel, outline=outline, width=2)

    progress_left = 132
    progress_top = content_top + 34
    draw.text((progress_left, progress_top), "PROGRAM PROGRESS", font=small_font, fill=cyan)
    progress_ratio = min(max(completed_days / max(total_days, 1), 0), 1)
    draw.rounded_rectangle((progress_left, progress_top + 36, width - 132, progress_top + 58), radius=11, fill=progress_track)
    draw.rounded_rectangle(
        (progress_left, progress_top + 36, progress_left + int((width - 264) * progress_ratio), progress_top + 58),
        radius=11,
        fill=cyan,
    )
    progress_summary = f"{completed_days}/{total_days} DAYS COMPLETE  •  {points_earned}/{max(challenge_points, 1)} PTS"
    draw.text((progress_left, progress_top + 74), progress_summary, font=micro_font, fill=muted_soft)

    exercise_block_top = progress_top + 136
    draw.text((progress_left, exercise_block_top), "HIGHLIGHTED COMPLETIONS", font=section_font, fill=white)
    row_y = exercise_block_top + 46
    for entry in exercise_entries[:4]:
        draw.rounded_rectangle((progress_left, row_y - 6, width - 132, row_y + 38), radius=16, fill=navy_card, outline="#1E2F49")
        draw.ellipse((progress_left + 16, row_y + 7, progress_left + 30, row_y + 21), fill=cyan)
        entry_lines = _wrap_report_text_lines(draw, entry, body_font, width - 264 - 60, 1)
        draw.text((progress_left + 48, row_y), entry_lines[0] if entry_lines else entry, font=body_font, fill=white)
        row_y += 60

    stat_top = 1018
    stat_width = 272
    stat_gap = 24
    stat_x_positions = [84, 84 + stat_width + stat_gap, 84 + (stat_width + stat_gap) * 2]

    streak_value = str(max(completed_days, int(selected_day.get("day_number") or 0) if selected_progress and selected_progress.completed else 0, 0))
    exercise_total = sum(len(section.get("exercises") or []) for section in (selected_day or {}).get("sections") or [])
    exercise_done = len(completed_exercise_ids) if completed_exercise_ids else exercise_total if selected_progress and selected_progress.completed else 0
    stat_cards = [
        ("STREAK", f"{streak_value} DAY", cyan),
        ("INTENSITY", str(challenge.get("difficulty") or "INTERMEDIATE").upper(), pink),
        ("EXERCISES", f"{exercise_done}/{max(exercise_total, 1)}", gold),
    ]

    for index, (label, value, color) in enumerate(stat_cards):
        x = stat_x_positions[index]
        draw.rounded_rectangle((x, stat_top, x + stat_width, stat_top + 132), radius=26, fill=navy_panel, outline=outline, width=2)
        draw.text((x + 24, stat_top + 24), label, font=small_font, fill=muted)
        value_lines = _wrap_report_text_lines(draw, value, heading_font, stat_width - 48, 2)
        value_y = stat_top + 58
        for line in value_lines:
            draw.text((x + 24, value_y), line, font=heading_font, fill=color)
            value_y += 34

    draw.rounded_rectangle((240, 1196, width - 240, 1278), radius=40, fill=cyan)
    member_name = str(viewer_name or "Victory Member").upper()
    member_lines = _wrap_report_text_lines(draw, member_name, section_font, width - 560, 1)
    member_label = member_lines[0] if member_lines else member_name
    member_box = draw.textbbox((0, 0), member_label, font=section_font)
    draw.text(((width - (member_box[2] - member_box[0])) / 2, 1222), member_label, font=section_font, fill="#04141D")
    center_text(1300, "VICTORY-FITNESS.APP", section_font, muted_soft)

    summary_title = str(challenge.get("title") or "Challenge").strip() or "Challenge"
    share_message = "\n".join(
        [
            "Victory Fitness",
            f"{summary_title} progress update by {viewer_name or 'Victory Member'}",
            f"Completed {completed_days}/{total_days} days · {points_earned}/{challenge_points} pts",
            f"Highlighted day: Day {day_number}",
        ]
    )

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue(), share_message

@router.get("/challenges/overview", response_model=ChallengeOverviewResponse)

async def get_challenge_overview(

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengeOverviewResponse:

    return await _build_challenge_overview_response(user)

@router.get("/challenges/{challenge_id}", response_model=ChallengeDetailResponse)

async def get_challenge_detail(

    challenge_id: str,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengeDetailResponse:

    challenge = await _get_challenge_or_404(challenge_id)

    membership = await challenge_memberships_collection.find_one(

        {"challenge_id": challenge_id, "user_id": str(user["_id"])}

    )

    if membership and str(membership.get("status") or "").upper() == "ACTIVE":

        total_days = max(int(challenge.get("duration_days") or 0), 1)

        started_at_raw = membership.get("started_at")

        if started_at_raw:

            try:

                started_at = datetime.fromisoformat(str(started_at_raw).replace("Z", "+00:00"))

                if started_at.tzinfo is None:

                    started_at = started_at.replace(tzinfo=timezone.utc)

                else:

                    started_at = started_at.astimezone(timezone.utc)

                today = datetime.now(timezone.utc).date()

                started_day = started_at.date()

                elapsed_days = max((today - started_day).days, 0)

                if elapsed_days >= total_days:

                    now = datetime.now(timezone.utc)

                    await challenge_memberships_collection.update_one(

                        {"_id": membership["_id"]},

                        {"$set": {"status": "COMPLETED", "completed_at": now, "updated_at": now}}

                    )

                    membership = dict(membership)

                    membership["status"] = "COMPLETED"

                    membership["completed_at"] = now

            except ValueError:

                pass

    challenge_status = str(challenge.get("status") or "ACTIVE").upper()

    membership_status = str((membership or {}).get("status") or "NOT_JOINED").upper()

    normalized_plan_days = _normalize_challenge_plan_days(

        challenge.get("plan_days") if isinstance(challenge.get("plan_days"), list) else [],

        duration_days=max(int(challenge.get("duration_days") or 0), 1)

    )

    challenge_points = max(int(challenge.get("points") or 0), 0)

    participants = await _load_challenge_participants(challenge_id)

    participant_count = await challenge_memberships_collection.count_documents(

        {"challenge_id": challenge_id, "status": {"$in": ["ACTIVE", "COMPLETED"]}}

    )

    messages = await _load_challenge_chat_messages(challenge_id, str(user["_id"]), limit=50)

    has_joined = membership_status in {"ACTIVE", "COMPLETED"}

    viewer_plan_progress = _build_viewer_plan_progress(normalized_plan_days, membership or {}) if membership else []

    viewer_progress_days_completed = _count_completed_plan_days_from_start(

        normalized_plan_days,

        membership.get("plan_progress") if membership and isinstance(membership.get("plan_progress"), dict) else {},

    )

    current_day_number = _get_current_challenge_day_number(

        membership or {},

        normalized_plan_days,

        max(int(challenge.get("duration_days") or 0), 1),

    ) if membership and has_joined and challenge_status == "ACTIVE" else None

    viewer_points_earned = _calculate_challenge_points_earned(

        normalized_plan_days,

        {**(membership or {}), "challenge_points": challenge_points},

        challenge_points,

    ) if membership else 0

    unread_count = 0

    if membership and has_joined:

        unread_count = await _count_unread_challenge_messages(challenge_id, str(user["_id"]), membership)

    completed_today = _has_completed_challenge_day_today(membership or {}) if membership and has_joined else False

    can_start = False

    if challenge_status == "ACTIVE" and membership_status not in {"ACTIVE", "COMPLETED"}:

        active_challenge_limit = _get_user_active_challenge_limit(user)

        if active_challenge_limit is None:

            can_start = True

        else:

            active_membership_count = await challenge_memberships_collection.count_documents(

                {

                    "user_id": str(user["_id"]),

                    "status": "ACTIVE",

                    **({"challenge_id": {"$ne": challenge_id}} if membership_status == "LEFT" else {}),

                }

            )

            can_start = active_membership_count < active_challenge_limit

    can_post = has_joined and challenge_status == "ACTIVE"

    return ChallengeDetailResponse(

        challenge_id=challenge_id,

        title=str(challenge.get("title") or ""),

        description=str(challenge.get("description") or ""),

        why_it_matters=str(challenge.get("why_it_matters") or ""),

        plan_text=str(challenge.get("plan_text") or ""),

        plan_days=[ChallengePlanDay(**day) for day in normalized_plan_days],

        category=str(challenge.get("category") or "Challenge"),

        duration_days=max(int(challenge.get("duration_days") or 0), 0),

        points=challenge_points,

        difficulty=str(challenge.get("difficulty") or "BEGINNER"),

        status=str(challenge.get("status") or "ACTIVE"),

        thumbnail=_normalize_challenge_thumbnail(challenge.get("thumbnail")),

        participant_count=participant_count,

        participants=participants,

        viewer_membership_status=membership_status,

        viewer_progress_days_completed=viewer_progress_days_completed,

        viewer_points_earned=viewer_points_earned,

        viewer_plan_progress=viewer_plan_progress,

        unread_count=unread_count,

        can_start=can_start,

        can_post=can_post,

        has_joined=has_joined,

        current_day_number=current_day_number,

        can_complete_today=bool(has_joined and membership_status == "ACTIVE" and challenge_status == "ACTIVE" and current_day_number and not completed_today),

        completed_today=completed_today,

        messages=[ChallengeChatMessageResponse(**message) for message in messages],

        started_at=membership.get("started_at") if membership else None,

    )

@router.get("/challenges/{challenge_id}/chat", response_model=ChallengeChatThreadResponse)

async def get_challenge_chat_thread(

    challenge_id: str,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengeChatThreadResponse:

    challenge = await _get_challenge_or_404(challenge_id)

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    if membership and str(membership.get("status") or "").upper() == "ACTIVE":

        total_days = max(int(challenge.get("duration_days") or 0), 1)

        started_at_raw = membership.get("started_at")

        if started_at_raw:

            try:

                started_at = datetime.fromisoformat(str(started_at_raw).replace("Z", "+00:00"))

                if started_at.tzinfo is None:

                    started_at = started_at.replace(tzinfo=timezone.utc)

                else:

                    started_at = started_at.astimezone(timezone.utc)

                today = datetime.now(timezone.utc).date()

                started_day = started_at.date()

                elapsed_days = max((today - started_day).days, 0)

                if elapsed_days >= total_days:

                    now = datetime.now(timezone.utc)

                    await challenge_memberships_collection.update_one(

                        {"_id": membership["_id"]},

                        {"$set": {"status": "COMPLETED", "completed_at": now, "updated_at": now}}

                    )

                    membership = dict(membership)

                    membership["status"] = "COMPLETED"

                    membership["completed_at"] = now

            except ValueError:

                pass

    _ensure_challenge_read_access(membership, challenge)

    messages = await _load_challenge_chat_messages(challenge_id, str(user["_id"]), limit=50)

    participants = await _load_challenge_participants(challenge_id)

    participant_count = await challenge_memberships_collection.count_documents(

        {"challenge_id": challenge_id, "status": {"$in": ["ACTIVE", "COMPLETED"]}}

    )

    unread_count = await _count_unread_challenge_messages(challenge_id, str(user["_id"]), membership)

    now = datetime.now(timezone.utc)

    await challenge_memberships_collection.update_one(

        {"_id": membership["_id"]},

        {"$set": {"last_read_message_at": now, "updated_at": now}},

    )

    challenge_points = max(int(challenge.get("points") or 0), 0)

    membership_with_points = dict(membership)

    membership_with_points["challenge_points"] = challenge_points

    normalized_plan_days = _normalize_challenge_plan_days(

        challenge.get("plan_days") if isinstance(challenge.get("plan_days"), list) else [],

        duration_days=max(int(challenge.get("duration_days") or 0), 1)

    )

    viewer_plan_progress = _build_viewer_plan_progress(normalized_plan_days, membership)

    viewer_progress_days_completed = _count_completed_plan_days_from_start(

        normalized_plan_days,

        membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {},

    )

    return ChallengeChatThreadResponse(

        challenge_id=challenge_id,

        title=str(challenge.get("title") or ""),

        description=str(challenge.get("description") or ""),

        why_it_matters=str(challenge.get("why_it_matters") or ""),

        plan_text=str(challenge.get("plan_text") or ""),

        plan_days=[ChallengePlanDay(**day) for day in normalized_plan_days],

        category=str(challenge.get("category") or "Challenge"),

        duration_days=max(int(challenge.get("duration_days") or 0), 0),

        points=challenge_points,

        difficulty=str(challenge.get("difficulty") or "BEGINNER"),

        status=str(challenge.get("status") or "ACTIVE"),

        thumbnail=_normalize_challenge_thumbnail(challenge.get("thumbnail")),

        participant_count=participant_count,

        participants=participants,

        viewer_membership_status=str(membership.get("status") or "ACTIVE"),

        viewer_progress_days_completed=viewer_progress_days_completed,

        viewer_points_earned=_calculate_challenge_points_earned(

            normalized_plan_days,

            membership_with_points,

            challenge_points,

        ),

        viewer_plan_progress=viewer_plan_progress,

        unread_count=unread_count,

        messages=[ChallengeChatMessageResponse(**message) for message in messages],

        started_at=membership.get("started_at"),

    )

@router.post("/challenges/{challenge_id}/chat/messages", response_model=ChallengeChatMessageResponse, status_code=status.HTTP_201_CREATED)

async def create_challenge_chat_message(

    challenge_id: str,

    payload: ChallengeChatMessageCreateRequest,

    background_tasks: BackgroundTasks,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengeChatMessageResponse:

    challenge = await _get_challenge_or_404(challenge_id)

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    _ensure_challenge_chat_write_access(membership, challenge)

    content = str(payload.content or "").strip()

    if not content and not payload.image_base64:

        raise HTTPException(status_code=400, detail="Message content or image is required")

    image_url = ""

    if payload.image_base64:

        try:

            image_url = _upload_challenge_chat_image_to_s3(

                str(user["_id"]),

                payload.image_base64,

                payload.mime_type,

                payload.file_name,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Challenge chat image upload failed: {exc}") from exc

    reply_to_message_id = str(payload.reply_to_message_id or "").strip() or None

    if reply_to_message_id and not ObjectId.is_valid(reply_to_message_id):

        raise HTTPException(status_code=400, detail="Invalid reply_to_message_id")

    if reply_to_message_id:

        await _get_challenge_message_or_404(challenge_id, reply_to_message_id)

    now = datetime.now(timezone.utc)

    document = {

        "_id": ObjectId(),

        "challenge_id": challenge_id,

        "author_id": str(user["_id"]),

        "message_type": "message",

        "content": content,

        "image_url": image_url,

        "reply_to_message_id": reply_to_message_id,

        "progress_payload": None,

        "created_at": now,

        "updated_at": now,

    }

    await challenge_chat_messages_collection.insert_one(document)

    await challenge_memberships_collection.update_one(

        {"_id": membership["_id"]},

        {"$set": {"updated_at": now}},

    )

    try:
        await _broadcast_challenge_chat_event("message_created", challenge_id, document)
    except Exception as exc:
        logger.warning("challenge_chat_broadcast_failed challenge_id=%s error=%s", challenge_id, exc)

    background_tasks.add_task(
        _safe_notify_challenge_chat_participants,
        challenge_id,
        str(user["_id"]),
        str(challenge.get("title") or "Your challenge"),
        content or "Sent an image in the challenge chat.",
    )

    coach_reply_handler = globals().get("_create_challenge_coach_reply")
    if _challenge_message_mentions_coach(content) and callable(coach_reply_handler):
        try:
            await coach_reply_handler(
                challenge=challenge,
                membership=membership,
                user=user,
                trigger_message=document,
            )
        except Exception as exc:
            logger.warning("challenge_chat_coach_reply_failed challenge_id=%s message_id=%s error=%s", challenge_id, str(document["_id"]), exc)
    elif _challenge_message_mentions_coach(content):
        logger.warning("challenge_chat_coach_reply_unavailable challenge_id=%s message_id=%s", challenge_id, str(document["_id"]))

    serialized_message = await _serialize_single_challenge_chat_message(document, str(user["_id"]))
    return ChallengeChatMessageResponse(**serialized_message)

@router.patch("/challenges/{challenge_id}/chat/messages/{message_id}", response_model=ChallengeChatMessageResponse)

async def update_challenge_chat_message(

    challenge_id: str,

    message_id: str,

    payload: ChallengeChatMessageUpdateRequest,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengeChatMessageResponse:

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    challenge = await _get_challenge_or_404(challenge_id)

    _ensure_challenge_chat_write_access(membership, challenge)

    message_record = await _get_challenge_message_or_404(challenge_id, message_id)

    if str(message_record.get("author_id") or "") != str(user["_id"]):

        raise HTTPException(status_code=403, detail="You can only edit your own messages")

    if str(message_record.get("author_id") or "") in {"coach_bot", "system"}:

        raise HTTPException(status_code=400, detail="This message cannot be edited")

    if message_record.get("deleted_at"):

        raise HTTPException(status_code=400, detail="Deleted messages cannot be edited")

    now = datetime.now(timezone.utc)

    await challenge_chat_messages_collection.update_one(

        {"_id": message_record["_id"]},

        {

            "$set": {

                "content": payload.content.strip(),

                "updated_at": now,

                "edited_at": now,

            }

        },

    )

    updated = await challenge_chat_messages_collection.find_one({"_id": message_record["_id"]})

    if not updated:

        raise HTTPException(status_code=404, detail="Challenge chat message not found")

    await _broadcast_challenge_chat_event("message_updated", challenge_id, updated)

    return ChallengeChatMessageResponse(**(await _serialize_single_challenge_chat_message(updated, str(user["_id"]))))

@router.delete("/challenges/{challenge_id}/chat/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)

async def delete_challenge_chat_message(

    challenge_id: str,

    message_id: str,

    user: dict = Depends(_require_challenge_access_user),

) -> Response:

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    challenge = await _get_challenge_or_404(challenge_id)

    _ensure_challenge_read_access(membership, challenge)

    message_record = await _get_challenge_message_or_404(challenge_id, message_id)

    if str(message_record.get("author_id") or "") != str(user["_id"]):

        raise HTTPException(status_code=403, detail="You can only delete your own messages")

    if str(message_record.get("author_id") or "") in {"coach_bot", "system"}:

        raise HTTPException(status_code=400, detail="This message cannot be deleted")

    now = datetime.now(timezone.utc)

    await challenge_chat_messages_collection.update_one(

        {"_id": message_record["_id"]},

        {

            "$set": {

                "content": "",

                "image_url": "",

                "updated_at": now,

                "deleted_at": now,

            }

        },

    )

    updated = await challenge_chat_messages_collection.find_one({"_id": message_record["_id"]})

    if updated:

        await _broadcast_challenge_chat_event("message_deleted", challenge_id, updated, message_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/challenges/{challenge_id}/chat/messages/{message_id}/reactions/toggle", response_model=ChallengeChatMessageResponse)

async def toggle_challenge_chat_reaction(

    challenge_id: str,

    message_id: str,

    payload: ChallengeChatReactionToggleRequest,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengeChatMessageResponse:

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    challenge = await _get_challenge_or_404(challenge_id)

    _ensure_challenge_read_access(membership, challenge)

    message_record = await _get_challenge_message_or_404(challenge_id, message_id)

    emoji = payload.emoji.strip()

    reaction_filter = {

        "message_id": message_id,

        "challenge_id": challenge_id,

        "user_id": str(user["_id"]),

        "emoji": emoji,

    }

    existing = await challenge_message_reactions_collection.find_one(reaction_filter)

    now = datetime.now(timezone.utc)

    if existing:

        await challenge_message_reactions_collection.delete_one({"_id": existing["_id"]})

    else:

        await challenge_message_reactions_collection.insert_one(

            {

                "_id": ObjectId(),

                "message_id": message_id,

                "challenge_id": challenge_id,

                "user_id": str(user["_id"]),

                "emoji": emoji,

                "created_at": now,

            }

        )

    updated = await challenge_chat_messages_collection.find_one({"_id": message_record["_id"]})

    if not updated:

        raise HTTPException(status_code=404, detail="Challenge chat message not found")

    await _broadcast_challenge_chat_event("reaction_toggled", challenge_id, updated)

    return ChallengeChatMessageResponse(**(await _serialize_single_challenge_chat_message(updated, str(user["_id"]))))

@router.post("/challenges/{challenge_id}/plan/days/{day_number}/complete", response_model=ChallengePlanProgressResponse)

async def complete_challenge_plan_day(

    challenge_id: str,

    day_number: int,

    payload: ChallengePlanCompletionRequest,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengePlanProgressResponse:

    challenge = await _get_challenge_or_404(challenge_id)

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    _ensure_challenge_write_access(membership, challenge)

    plan_days = _get_normalized_plan_days(challenge)

    plan_day = _get_plan_day_or_404(plan_days, day_number)

    existing_day_progress = _get_membership_day_progress(membership, day_number)

    valid_section_ids, valid_exercise_ids = _get_plan_day_ids(plan_day)

    completed_section_ids, completed_exercise_ids = _normalize_completed_progress_ids(

        existing_day_progress,

        valid_section_ids,

        valid_exercise_ids,

    )

    if payload.completed and valid_exercise_ids and len(completed_exercise_ids) < len(valid_exercise_ids):

        raise HTTPException(status_code=400, detail="Complete every exercise before marking the day done")

    if payload.completed and not valid_exercise_ids and valid_section_ids and len(completed_section_ids) < len(valid_section_ids):

        raise HTTPException(status_code=400, detail="Complete every section before marking the day done")

    if payload.completed and not valid_section_ids:

        completed_section_ids = []

    if payload.completed and not valid_exercise_ids:

        completed_exercise_ids = []

    if not payload.completed:

        completed_section_ids = []

        completed_exercise_ids = []

    return await _store_membership_plan_progress(

        challenge=challenge,

        membership=membership,

        user=user,

        day_number=day_number,

        completed_section_ids=completed_section_ids,

        completed_exercise_ids=completed_exercise_ids,

        completed=payload.completed,

        emit_progress_message=payload.completed,

    )

@router.post("/challenges/{challenge_id}/complete-today", response_model=ChallengePlanProgressResponse)

async def complete_challenge_today(

    challenge_id: str,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengePlanProgressResponse:

    return await _complete_current_challenge_day(challenge_id, user)

@router.post("/challenges/{challenge_id}/current-day/complete", response_model=ChallengePlanProgressResponse)

async def complete_current_challenge_day(

    challenge_id: str,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengePlanProgressResponse:

    return await _complete_current_challenge_day(challenge_id, user)

@router.post(

    "/challenges/{challenge_id}/plan/days/{day_number}/sections/{section_id}/complete",

    response_model=ChallengePlanProgressResponse,

)

async def complete_challenge_plan_section(

    challenge_id: str,

    day_number: int,

    section_id: str,

    payload: ChallengePlanCompletionRequest,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengePlanProgressResponse:

    challenge = await _get_challenge_or_404(challenge_id)

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    _ensure_challenge_write_access(membership, challenge)

    plan_days = _get_normalized_plan_days(challenge)

    plan_day = _get_plan_day_or_404(plan_days, day_number)

    valid_section_ids, valid_exercise_ids = _get_plan_day_ids(plan_day)

    if section_id not in valid_section_ids:

        raise HTTPException(status_code=404, detail="Challenge plan section not found")

    existing_day_progress = _get_membership_day_progress(membership, day_number)

    prior_completed = bool(isinstance(existing_day_progress, dict) and existing_day_progress.get("completed"))

    if payload.completed:
        completed_section_ids, completed_exercise_ids = _normalize_completed_progress_ids(

            existing_day_progress,

            valid_section_ids,

            valid_exercise_ids,

        )

        section_record = _get_plan_section_or_404(plan_day, section_id)

        section_exercise_ids = _get_section_exercise_ids(section_record)

        if section_exercise_ids:

            completed_section_exercise_ids = {
                exercise_id for exercise_id in completed_exercise_ids if exercise_id in section_exercise_ids
            }

            if len(completed_section_exercise_ids) < len(section_exercise_ids):

                raise HTTPException(
                    status_code=400,
                    detail="Complete every exercise in this section before marking the section complete",
                )

        if section_id not in completed_section_ids:

            completed_section_ids.append(section_id)

        will_complete_day = False

    else:

        completed_section_ids, completed_exercise_ids = _normalize_completed_progress_ids(

            existing_day_progress,

            valid_section_ids,

            valid_exercise_ids,

        )

        section_record = _get_plan_section_or_404(plan_day, section_id)

        section_exercise_ids = _get_section_exercise_ids(section_record)

        completed_section_ids = [value for value in completed_section_ids if value != section_id]

        if section_exercise_ids:

            completed_exercise_ids = [value for value in completed_exercise_ids if value not in section_exercise_ids]

        will_complete_day = False

    return await _store_membership_plan_progress(

        challenge=challenge,

        membership=membership,

        user=user,

        day_number=day_number,

        completed_section_ids=completed_section_ids,

        completed_exercise_ids=completed_exercise_ids,

        completed=will_complete_day,

        emit_progress_message=will_complete_day and not prior_completed,

    )

@router.post(

    "/challenges/{challenge_id}/plan/days/{day_number}/exercises/{exercise_id}/complete",

    response_model=ChallengePlanProgressResponse,

)

async def complete_challenge_plan_exercise_direct(

    challenge_id: str,

    day_number: int,

    exercise_id: str,

    payload: ChallengePlanCompletionRequest,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengePlanProgressResponse:

    challenge = await _get_challenge_or_404(challenge_id)

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    _ensure_challenge_write_access(membership, challenge)

    return await _complete_challenge_plan_exercise_internal(

        challenge=challenge,

        membership=membership,

        user=user,

        day_number=day_number,

        exercise_id=exercise_id,

        payload=payload,

    )

@router.post(

    "/challenges/{challenge_id}/plan/days/{day_number}/sections/{section_id}/exercises/{exercise_id}/complete",

    response_model=ChallengePlanProgressResponse,

)

async def complete_challenge_plan_exercise(

    challenge_id: str,

    day_number: int,

    section_id: str,

    exercise_id: str,

    payload: ChallengePlanCompletionRequest,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengePlanProgressResponse:

    challenge = await _get_challenge_or_404(challenge_id)

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    _ensure_challenge_write_access(membership, challenge)

    return await _complete_challenge_plan_exercise_internal(

        challenge=challenge,

        membership=membership,

        user=user,

        day_number=day_number,

        exercise_id=exercise_id,

        payload=payload,

        section_id=section_id,

    )

@router.post("/challenges/{challenge_id}/progress", response_model=ChallengeChatMessageResponse, status_code=status.HTTP_201_CREATED)

async def post_challenge_progress_update(

    challenge_id: str,

    payload: ChallengeProgressUpdateRequest,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengeChatMessageResponse:

    challenge = await _get_challenge_or_404(challenge_id)

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    _ensure_challenge_write_access(membership, challenge)

    total_days = max(int(challenge.get("duration_days") or 0), 1)

    completed_day = min(payload.completed_day, total_days)

    plan_days = _normalize_challenge_plan_days(

        challenge.get("plan_days") if isinstance(challenge.get("plan_days"), list) else [],

        duration_days=total_days

    )

    existing_plan_progress = membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {}

    next_plan_progress = dict(existing_plan_progress)

    plan_day = next((day for day in plan_days if int(day.get("day_number") or 0) == completed_day), None)

    if plan_day:

        completed_section_ids = [

            str(section.get("id") or "")

            for section in plan_day.get("sections") or []

            if str(section.get("id") or "")

        ]

        next_plan_progress[str(completed_day)] = {

            "completed": True,

            "completed_section_ids": completed_section_ids,

            "updated_at": datetime.now(timezone.utc).isoformat(),

        }

    next_progress = _count_completed_plan_days_from_start(plan_days, next_plan_progress)

    next_status = "COMPLETED" if next_progress >= total_days else "ACTIVE"

    image_url = ""

    if payload.image_base64:

        try:

            image_url = _upload_challenge_chat_image_to_s3(

                str(user["_id"]),

                payload.image_base64,

                payload.mime_type,

                payload.file_name,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Challenge progress image upload failed: {exc}") from exc

    note = str(payload.note or "").strip()

    content = note or f"Completed day {completed_day}."

    now = datetime.now(timezone.utc)

    progress_payload = {

        "completed_day": completed_day,

        "total_days": total_days,

        "membership_status": next_status,

    }

    document = {

        "_id": ObjectId(),

        "challenge_id": challenge_id,

        "author_id": str(user["_id"]),

        "message_type": "progress_update",

        "content": content,

        "image_url": image_url,

        "reply_to_message_id": None,

        "progress_payload": progress_payload,

        "created_at": now,

        "updated_at": now,

    }

    await challenge_chat_messages_collection.insert_one(document)

    membership_update = {

        "progress_days_completed": next_progress,

        "plan_progress": next_plan_progress,

        "status": next_status,

        "updated_at": now,

    }

    if next_status == "COMPLETED":

        membership_update["completed_at"] = now

    await challenge_memberships_collection.update_one(

        {"_id": membership["_id"]},

        {"$set": membership_update},

    )

    await _broadcast_challenge_chat_event("message_created", challenge_id, document)

    return ChallengeChatMessageResponse(**_serialize_challenge_chat_message(document, user, str(user["_id"])))

@router.get("/challenges/{challenge_id}/progress/report", response_model=ChallengeProgressReportResponse)

async def get_challenge_progress_report(

    challenge_id: str,
    day: int | None = None,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengeProgressReportResponse:

    challenge = await _get_challenge_or_404(challenge_id)

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    if membership and str(membership.get("status") or "").upper() == "ACTIVE":

        total_days = max(int(challenge.get("duration_days") or 0), 1)

        started_at_raw = membership.get("started_at")

        if started_at_raw:

            try:

                started_at = datetime.fromisoformat(str(started_at_raw).replace("Z", "+00:00"))

                if started_at.tzinfo is None:

                    started_at = started_at.replace(tzinfo=timezone.utc)

                else:

                    started_at = started_at.astimezone(timezone.utc)

                today = datetime.now(timezone.utc).date()

                started_day = started_at.date()

                elapsed_days = max((today - started_day).days, 0)

                if elapsed_days >= total_days:

                    now = datetime.now(timezone.utc)

                    await challenge_memberships_collection.update_one(

                        {"_id": membership["_id"]},

                        {"$set": {"status": "COMPLETED", "completed_at": now, "updated_at": now}}

                    )

                    membership = dict(membership)

                    membership["status"] = "COMPLETED"

                    membership["completed_at"] = now

            except ValueError:

                pass

    _ensure_challenge_read_access(membership, challenge)

    viewer_name = str(user.get("name") or "Victory Member").strip() or "Victory Member"

    png_bytes, share_message = _build_challenge_progress_report_png(challenge, membership, viewer_name, day)

    return ChallengeProgressReportResponse(

        file_name="victory-fitness-progress-report.png",

        mime_type="image/png",

        image_base64=base64.b64encode(png_bytes).decode("ascii"),

        share_message=share_message,

    )

@router.post("/challenges/{challenge_id}/start", response_model=StartChallengeResponse, status_code=status.HTTP_201_CREATED)

async def start_challenge(

    challenge_id: str,

    user: dict = Depends(_require_challenge_access_user),

) -> StartChallengeResponse:

    try:

        object_id = ObjectId(challenge_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid challenge id") from exc

    challenge = await challenges_collection.find_one({"_id": object_id})

    if not challenge:

        raise HTTPException(status_code=404, detail="Challenge not found")

    challenge_status = str(challenge.get("status") or "").upper()

    if challenge_status == "UPCOMING":

        raise HTTPException(status_code=400, detail="This challenge is coming soon and cannot be started yet")

    if challenge_status != "ACTIVE":

        raise HTTPException(status_code=400, detail="This challenge cannot be started")

    user_id = str(user["_id"])

    active_challenge_limit = _get_user_active_challenge_limit(user)

    if active_challenge_limit is not None:

        active_membership_count = await challenge_memberships_collection.count_documents(

            {"user_id": user_id, "status": "ACTIVE"}

        )

        if active_membership_count >= active_challenge_limit:

            raise HTTPException(

                status_code=403,

                detail=f"Your current plan allows up to {active_challenge_limit} active challenges",

            )

    existing_membership = await challenge_memberships_collection.find_one(

        {"user_id": user_id, "challenge_id": challenge_id}

    )

    if existing_membership:

        existing_status = str(existing_membership.get("status") or "").upper()

        if existing_status == "ACTIVE":

            return StartChallengeResponse(membership_id=str(existing_membership["_id"]))

        if existing_status == "COMPLETED":

            raise HTTPException(status_code=409, detail="You already completed this challenge")

        if existing_status == "LEFT":

            now = datetime.now(timezone.utc)

            await challenge_memberships_collection.update_one(

                {"_id": existing_membership["_id"]},

                {

                    "$set": {

                        "status": "ACTIVE",

                        "plan_progress": existing_membership.get("plan_progress") if isinstance(existing_membership.get("plan_progress"), dict) else {},

                        "updated_at": now,

                        "started_at": existing_membership.get("started_at") or now,

                    }

                },

            )

            await challenge_chat_messages_collection.insert_one(

                {

                    "_id": ObjectId(),

                    "challenge_id": challenge_id,

                    "author_id": "system",

                    "author_name": "Coach",

                    "author_role": "system",

                    "message_type": "system_event",

                    "content": f"{user.get('name') or 'A member'} joined the challenge.",

                    "image_url": "",

                    "reply_to_message_id": None,

                    "progress_payload": None,

                    "created_at": now,

                    "updated_at": now,

                }

            )

            return StartChallengeResponse(membership_id=str(existing_membership["_id"]))

    now = datetime.now(timezone.utc)

    document = {

        "user_id": user_id,

        "challenge_id": challenge_id,

        "status": "ACTIVE",

        "progress_days_completed": 0,

        "plan_progress": {},

        "joined_at": now,

        "started_at": now,

        "updated_at": now,

    }

    insert_result = await challenge_memberships_collection.insert_one(document)

    await challenge_chat_messages_collection.insert_one(

        {

            "_id": ObjectId(),

            "challenge_id": challenge_id,

            "author_id": "system",

            "author_name": "Coach",

            "author_role": "system",

            "message_type": "system_event",

            "content": f"{user.get('name') or 'A member'} joined the challenge.",

            "image_url": "",

            "reply_to_message_id": None,

            "progress_payload": None,

            "created_at": now,

            "updated_at": now,

        }

    )

    await notify_user(
        users_collection,
        user,
        "Challenge started",
        f"You are ready for {str(challenge.get('title') or 'your challenge')}. Complete day 1 today to build your streak.",
        "challenge_started",
        {"type": "challenge", "challengeId": challenge_id, "route": f"/challenges/progress/{challenge_id}"},
    )
    return StartChallengeResponse(membership_id=str(insert_result.inserted_id))
