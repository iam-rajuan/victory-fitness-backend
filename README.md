# Victory Fitness Backend

FastAPI backend with MongoDB auth, SMTP email verification, 10 minute access tokens, and 30 day session tokens.

## Setup

```powershell
cd C:\Miskat\victoria\victory-backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Update `.env` before running:

- `MONGODB_URI`: required MongoDB Atlas connection string. Auth, Coach Victor history, and nutrition plans all use this database.
- `JWT_SECRET_KEY`: replace with a long random secret.
- `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`: your SMTP account details.
- `OPENAI_API_KEY`: your OpenAI API key for Coach Victor and nutrition generation.
- `OPENAI_MODEL`: OpenAI model for Coach Victor and nutrition generation, defaults to `gpt-4o-mini`.
- `OPENAI_MEAL_ANALYSIS_MODEL`: OpenAI vision model for meal photo analysis, defaults to `gpt-4o-mini`.
- `ANTHROPIC_API_KEY`: optional Claude API key for Coach Victor.
- `ANTHROPIC_MODEL`: Claude model for Coach Victor and nutrition generation, defaults to `claude-haiku-4-5-20251001`.
- `VIMEO_ACCESS_TOKEN`: optional Vimeo token used to report dashboard overview integration status.
- `COACH_RECENT_MESSAGE_LIMIT`: how many recent Coach Victor messages stay in the live thread document.
- `COACH_ARCHIVE_BATCH_SIZE`: how many old messages are moved out of the live thread when retention is exceeded.
- `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET`: optional S3 archive settings for old Coach Victor messages.
- `AWS_S3_PREFIX`: S3 key prefix for archived Coach Victor message batches.
- `FRONTEND_ORIGIN`: Expo web origin, usually `http://localhost:8081`.
- `FRONTEND_ORIGIN_REGEX`: `.*` allows all origins for development. Use a strict regex or remove it in production.
- `COOKIE_SECURE`: use `false` for local HTTP, `true` for production HTTPS.
- `ADMIN_SEED_ENABLED`, `ADMIN_NAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`: startup seed settings for a verified admin account. On startup, if the admin email does not exist yet, the backend inserts it automatically.

## Run

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Run With Docker

```powershell
cd C:\Miskat\victoria\victory-backend
docker compose up --build
```

The compose file starts the FastAPI API and reads `MONGODB_URI` from `.env`, so it connects to MongoDB Atlas instead of a local Mongo service.

## Endpoints

- `GET /health`
- `POST /auth/register`
- `POST /auth/verify-email`
- `POST /auth/login`
- `POST /auth/refresh`

`/auth/login`, `/auth/verify-email`, and `/auth/refresh` set HttpOnly cookies and also return tokens in the response body for Expo native usage.

`POST /ai/coach-victor/chat` generates a response from Coach Victor using the configured cloud model. It expects an authenticated access token and a body with `message`.

Coach Victor chat history now keeps only recent messages in the `coach_victor_threads` collection. Older batches move into `coach_victor_archives`. If AWS S3 is configured, archive payloads are written to S3 and MongoDB stores the archive metadata. If S3 is not configured yet, archive payloads are still moved out of the live thread into the `coach_victor_archives` MongoDB collection so the active thread document stays small.

`POST /ai/nutrition/plan` builds a 7-day nutrition plan from the onboarding profile data. `POST /ai/nutrition/advice` returns short nutrition suggestions for the tracker tab.
