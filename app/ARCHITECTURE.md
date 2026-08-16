# Backend Architecture

This FastAPI backend is organized so the application entrypoint stays small and
feature code is easy to find.

## Entry Points

- `app/main.py` exports `app` for Uvicorn, Vercel, tests, and older imports.
- `app/application.py` owns application construction: middleware, static files,
  exception handlers, startup/shutdown hooks, and router inclusion.

Keep deployment commands pointed at `app.main:app`.

## Route Modules

HTTP and websocket endpoints live in `app/api/routers/`.

Examples:

- `auth.py`: login, register, token refresh, logout.
- `me.py`: current user profile, onboarding, subscription, body metrics.
- `community.py`: app community feed endpoints.
- `admin_community.py`: dashboard/admin community endpoints.
- `challenges.py`: app challenge endpoints and challenge chat.
- `admin_challenges.py`: dashboard/admin challenge management.
- `ai_nutrition.py`, `ai_workout_plan.py`, `ai_coach_victor.py`: AI features.

When adding a new router module:

1. Create `app/api/routers/<feature>.py`.
2. Define `router = APIRouter()`.
3. Register the module in `app/api/routers/__init__.py`.

Routers should stay thin: validate request data, apply dependencies, and call a
service function for business logic.

## Services

Feature business logic lives in `app/services/` when it is large enough to make
a router hard to scan.

Example:

- `services/admin_dashboard.py` builds the dashboard overview response.

## Shared Legacy Core

`app/core/legacy.py` contains shared helpers, constants, serializers, and
service-like functions that were previously mixed into the old monolithic
`app/main.py`.

This file is intentionally still large. Move code out of it gradually when you
are already touching a feature:

- Feature-specific helper functions should move beside their router or into a
  feature service module.
- Cross-feature helpers should move to `app/utils/`, `app/repositories/`, or a
  new focused module under `app/core/`.
- Keep behavior unchanged when moving code; route tests should pass before and
  after each extraction.

## Compatibility

`app/main.py` still re-exports legacy symbols because existing tests and older
code import internals from `app.main`. Do not remove that compatibility layer
until callers have been migrated to import from the newer modules directly.
