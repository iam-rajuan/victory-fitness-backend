from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/favicon.ico")

async def get_favicon_ico() -> Response:

    content = _build_favicon_ico_bytes()

    if not content:

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return Response(content=content, media_type="image/x-icon")

@router.get("/favicon.png")

async def get_favicon_png() -> Response:

    content = _build_favicon_png_bytes()

    if not content:

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return Response(content=content, media_type="image/png")

@router.get("/")

async def root() -> dict[str, str]:

    return {

        "status": "success",

        "message": "Victory Fitness API is running",

    }

@router.get("/health")

async def health() -> dict[str, str]:

    return {"status": "ok"}
