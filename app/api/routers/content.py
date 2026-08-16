from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/content/privacy-policy", response_model=PrivacyPolicyResponse)

async def get_privacy_policy() -> PrivacyPolicyResponse:

    record = await _ensure_privacy_policy_record()

    return _serialize_privacy_policy_record(record)

@router.get("/content/about-us", response_model=AboutUsResponse)

async def get_about_us() -> AboutUsResponse:

    record = await _ensure_about_us_record()

    return _serialize_about_us_record(record)

@router.get("/content/onboarding", response_model=OnboardingContentResponse)

async def get_onboarding_content() -> OnboardingContentResponse:

    items = await _get_dashboard_onboarding_items()

    slides = [

        OnboardingSlideResponse(

            id=str(item.get("id") or uuid4().hex),

            badge=str(item.get("badge") or "").strip(),

            title_lines=[

                str(line).strip()

                for line in item.get("title_lines") or []

                if str(line).strip()

            ],

            title_accent_index=item.get("title_accent_index") if isinstance(item.get("title_accent_index"), int) else None,

            description=str(item.get("description") or "").strip(),

            show_skip=bool(item.get("show_skip", False)),

            button_label=str(item.get("button_label") or "").strip(),

            button_arrow=str(item.get("button_arrow") or "").strip(),

            has_secondary=bool(item.get("has_secondary", False)),

            secondary_label=str(item.get("secondary_label") or "").strip(),

            has_footer=bool(item.get("has_footer", False)),

            footer_text=str(item.get("footer_text") or "").strip(),

        )

        for item in items

    ]

    return OnboardingContentResponse(slides=slides)

@router.get("/content/homepage/quote", response_model=HomepageQuote | None)
async def get_homepage_quote() -> HomepageQuote | None:
    active_items = [item for item in await _load_homepage_quotes() if item.get("active")]
    if not active_items:
        return None
    return HomepageQuote(**active_items[datetime.now(timezone.utc).date().toordinal() % len(active_items)])
