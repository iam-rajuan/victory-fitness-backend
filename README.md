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

- `MONGODB_URI`: your local MongoDB or MongoDB Atlas connection string.
- `JWT_SECRET_KEY`: replace with a long random secret.
- `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`: your SMTP account details.
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

The compose file starts both the FastAPI API and MongoDB. It reads `.env`, but overrides `MONGODB_URI` to use the compose Mongo service.

## Endpoints

- `GET /health`
- `POST /auth/register`
- `POST /auth/verify-email`
- `POST /auth/login`
- `POST /auth/refresh`

`/auth/login`, `/auth/verify-email`, and `/auth/refresh` set HttpOnly cookies and also return tokens in the response body for Expo native usage.
