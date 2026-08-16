from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/admin/homepage/quotes", response_model=HomepageQuoteListResponse)
async def admin_list_homepage_quotes(_: dict = Depends(_require_admin_user)) -> HomepageQuoteListResponse:
    return HomepageQuoteListResponse(items=[HomepageQuote(**item) for item in await _load_homepage_quotes()])

@router.post("/admin/homepage/quotes", response_model=HomepageQuoteListResponse)
async def admin_add_homepage_quote(payload: HomepageQuoteRequest, _: dict = Depends(_require_admin_user)) -> HomepageQuoteListResponse:
    items = await _load_homepage_quotes()
    items.append({"id": str(uuid4()), "text": payload.text.strip(), "author": payload.author.strip(), "active": payload.active})
    await _save_homepage_quotes(items)
    return HomepageQuoteListResponse(items=[HomepageQuote(**item) for item in items])

@router.put("/admin/homepage/quotes", response_model=HomepageQuoteListResponse)
async def admin_replace_homepage_quotes(payload: HomepageQuoteListResponse, _: dict = Depends(_require_admin_user)) -> HomepageQuoteListResponse:
    items = [item.model_dump() for item in payload.items]
    await _save_homepage_quotes(items)
    return HomepageQuoteListResponse(items=[HomepageQuote(**item) for item in items])
