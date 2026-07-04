# Victory Fitness Backend

FastAPI backend with MongoDB auth, SMTP email verification, 10 minute access tokens, and 30 day session tokens.

## Setup

```powershell
cd C:\Miskat\victora\victory-fitness-backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Update `.env` before running:

- `APP_NAME`, `ENVIRONMENT`: API display name and runtime environment.
- `MONGODB_URI`, `MONGODB_DB`: required MongoDB Atlas connection string and database name. Auth, Coach Victor history, and nutrition plans all use this database.
- `JWT_SECRET_KEY`: replace with a long random secret.
- `ACCESS_TOKEN_EXPIRE_MINUTES`, `SESSION_TOKEN_EXPIRE_DAYS`: auth token lifetimes.
- `CORS_ORIGIN`: set `*` to allow all frontend origins, or set one or more comma-separated frontend origins.
- `COOKIE_SECURE`, `COOKIE_SAMESITE`: use `COOKIE_SECURE=true` and `COOKIE_SAMESITE=none` for cross-site HTTPS auth cookies in production.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME`, `SMTP_USE_TLS`: email verification SMTP settings.
- `OPENAI_API_KEY`: your OpenAI API key for Coach Victor and nutrition generation.
- `OPENAI_MODEL`: OpenAI model for Coach Victor and nutrition generation, defaults to `gpt-5.5`.
- `OPENAI_MEAL_ANALYSIS_MODEL`: OpenAI vision model for meal photo analysis, defaults to `gpt-4o-mini`.
- `ANTHROPIC_API_KEY`: optional Claude API key for Coach Victor.
- `ANTHROPIC_MODEL`: Claude model for Coach Victor and nutrition generation, defaults to `claude-haiku-4-5-20251001`.
- `VIMEO_ACCESS_TOKEN`: optional Vimeo token used to report dashboard overview integration status and power `/admin/workouts/sync`, which imports Vimeo folders/showcases/videos into the workout library.
- `COACH_RECENT_MESSAGE_LIMIT`: how many recent Coach Victor messages stay in the live thread document.
- `COACH_ARCHIVE_BATCH_SIZE`: how many old messages are moved out of the live thread when retention is exceeded.
- `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET`: optional S3 archive settings for old Coach Victor messages.
- `AWS_S3_PREFIX`: S3 key prefix for archived Coach Victor message batches.
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_PROJECT_ID`, `FIREBASE_PROJECT_ID`, `FIREBASE_AUTH_PROVIDER_CERT_URL`: Google OAuth and Firebase auth settings.
- `ADMIN_SEED_ENABLED`, `ADMIN_NAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`: startup seed settings for a verified admin account. On startup, if the admin email does not exist yet, the backend inserts it automatically.
- `ADMIN_SEED_SYNC_PASSWORD`: optional boolean, defaults to `true`. Startup resets the existing seeded admin account password to `ADMIN_PASSWORD`, which guarantees dashboard login after deploy if the stored hash was stale. Set it to `false` only if you want validation-only behavior.

## Run

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Run With Docker

```powershell
cd C:\Miskat\victora\victory-fitness-backend
docker compose up --build
```

The compose file starts the FastAPI API and reads `MONGODB_URI` from `.env`, so it connects to MongoDB Atlas instead of a local Mongo service.

## Endpoints

- `GET /health`
- `POST /auth/register`
- `POST /auth/verify-email`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`

`/auth/login`, `/auth/verify-email`, and `/auth/refresh` set HttpOnly cookies and also return tokens in the response body for Expo native usage. `POST /auth/logout` clears the auth cookies.

`POST /ai/coach-victor/chat` generates a response from Coach Victor using the configured cloud model. It expects an authenticated access token and a body with `message`.

Coach Victor chat history now keeps only recent messages in the `coach_victor_threads` collection. Older batches move into `coach_victor_archives`. If AWS S3 is configured, archive payloads are written to S3 and MongoDB stores the archive metadata. If S3 is not configured yet, archive payloads are still moved out of the live thread into the `coach_victor_archives` MongoDB collection so the active thread document stays small.

`POST /ai/nutrition/plan` builds a 7-day nutrition plan from the onboarding profile data. `POST /ai/nutrition/advice` returns short nutrition suggestions for the tracker tab.
