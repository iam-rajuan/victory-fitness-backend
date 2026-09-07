from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/admin/homepage/quotes", response_model=HomepageQuoteListResponse)
async def admin_list_homepage_quotes(_: dict = Depends(_require_admin_user)) -> HomepageQuoteListResponse:
    return HomepageQuoteListResponse(items=[HomepageQuote(**item) for item in await _load_homepage_quotes()])

@router.post("/admin/homepage/quotes", response_model=HomepageQuoteListResponse)
async def admin_add_homepage_quote(payload: HomepageQuoteRequest, _: dict = Depends(_require_admin_user)) -> HomepageQuoteListResponse:
    items = await _load_homepage_quotes()
    if payload.selected:
        for item in items:
            item["selected"] = False
    items.append({
        "id": str(uuid4()),
        "text": payload.text.strip(),
        "author": payload.author.strip(),
        "active": payload.active,
        "version": payload.version.strip() if payload.version else None,
        "selected": payload.selected,
    })
    await _save_homepage_quotes(items)
    return HomepageQuoteListResponse(items=[HomepageQuote(**item) for item in items])

@router.post("/admin/homepage/quotes/{quote_id}/select", response_model=HomepageQuoteListResponse)
async def admin_select_homepage_quote(quote_id: str, _: dict = Depends(_require_admin_user)) -> HomepageQuoteListResponse:
    items = await _load_homepage_quotes()
    for item in items:
        item["selected"] = (str(item.get("id")) == str(quote_id))
        if item["selected"]:
            item["active"] = True
    await _save_homepage_quotes(items)
    return HomepageQuoteListResponse(items=[HomepageQuote(**item) for item in items])

@router.delete("/admin/homepage/quotes/{quote_id}", response_model=HomepageQuoteListResponse)
async def admin_delete_homepage_quote(quote_id: str, _: dict = Depends(_require_admin_user)) -> HomepageQuoteListResponse:
    items = await _load_homepage_quotes()
    items = [item for item in items if str(item.get("id")) != str(quote_id)]
    if items and not any(item.get("selected") for item in items):
        items[0]["selected"] = True
    await _save_homepage_quotes(items)
    return HomepageQuoteListResponse(items=[HomepageQuote(**item) for item in items])

@router.put("/admin/homepage/quotes", response_model=HomepageQuoteListResponse)
async def admin_replace_homepage_quotes(payload: HomepageQuoteListResponse, _: dict = Depends(_require_admin_user)) -> HomepageQuoteListResponse:
    items = [item.model_dump() for item in payload.items]
    await _save_homepage_quotes(items)
    return HomepageQuoteListResponse(items=[HomepageQuote(**item) for item in items])
