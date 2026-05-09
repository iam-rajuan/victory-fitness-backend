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

- `MONGODB_URI`: your MongoDB Atlas connection string.
- `JWT_SECRET_KEY`: replace with a long random secret.
- `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`: your SMTP account details.
- `ANTHROPIC_API_KEY`: your Anthropic API key for Coach Victor.
- `ANTHROPIC_MODEL`: Anthropic model for Coach Victor, defaults to `claude-3-5-haiku-20241022`.
- `FRONTEND_ORIGIN`: Expo web origin, usually `http://localhost:8081`.
- `FRONTEND_ORIGIN_REGEX`: `.*` allows all origins for development. Use a strict regex or remove it in production.
- `COOKIE_SECURE`: use `false` for local HTTP, `true` for production HTTPS.

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

`POST /ai/coach-victor/chat` generates a response from Coach Victor using Anthropic. It expects an authenticated access token and a body with `message` plus optional prior `history`.
