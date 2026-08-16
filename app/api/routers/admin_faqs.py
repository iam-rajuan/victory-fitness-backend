from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/admin/faqs", response_model=FAQListResponse)

async def admin_list_faqs(

    _: dict = Depends(_require_admin_user),

) -> FAQListResponse:

    items = [_serialize_faq_item(item) for item in await _get_dashboard_faq_items()]

    return FAQListResponse(items=[FAQItemResponse(**item) for item in items])

@router.post("/admin/faqs", response_model=FAQItemResponse, status_code=status.HTTP_201_CREATED)

async def admin_create_faq(

    payload: FAQRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> FAQItemResponse:

    items = [_serialize_faq_item(item) for item in await _get_dashboard_faq_items()]

    faq = {

        "id": uuid4().hex,

        "question": payload.question.strip(),

        "answer": payload.answer.strip(),

    }

    items.insert(0, faq)

    await _replace_items_record(DASHBOARD_FAQS_KEY, items)

    await _record_admin_audit(

        admin_user,

        "faq_created",

        "faq",

        faq["id"],

        {"question": faq["question"][:120]},

    )

    return FAQItemResponse(**faq)

@router.patch("/admin/faqs/{faq_id}", response_model=FAQItemResponse)

async def admin_update_faq(

    faq_id: str,

    payload: FAQRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> FAQItemResponse:

    items = [_serialize_faq_item(item) for item in await _get_dashboard_faq_items()]

    updated_faq: dict | None = None

    for item in items:

        if item["id"] == faq_id:

            item["question"] = payload.question.strip()

            item["answer"] = payload.answer.strip()

            updated_faq = item

            break

    if not updated_faq:

        raise HTTPException(status_code=404, detail="FAQ not found")

    await _replace_items_record(DASHBOARD_FAQS_KEY, items)

    await _record_admin_audit(

        admin_user,

        "faq_updated",

        "faq",

        faq_id,

        {"question": updated_faq["question"][:120]},

    )

    return FAQItemResponse(**updated_faq)

@router.delete("/admin/faqs/{faq_id}")

async def admin_delete_faq(

    faq_id: str,

    admin_user: dict = Depends(_require_admin_user),

) -> dict[str, str]:

    items = [_serialize_faq_item(item) for item in await _get_dashboard_faq_items()]

    next_items = [item for item in items if item["id"] != faq_id]

    if len(next_items) == len(items):

        raise HTTPException(status_code=404, detail="FAQ not found")

    await _replace_items_record(DASHBOARD_FAQS_KEY, next_items)

    await _record_admin_audit(admin_user, "faq_deleted", "faq", faq_id)

    return {"status": "success", "message": "FAQ deleted"}
