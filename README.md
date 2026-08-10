# Victory Fitness Backend

FastAPI backend for the Victory Fitness mobile app and admin dashboard. The API provides authentication, email verification, user profiles, workout content, challenges, community features, analytics, AI-generated coaching and nutrition plans, push notifications, wearable integrations, and admin management endpoints.

## Tech Stack

- Python 3.12
- FastAPI
- Uvicorn
- MongoDB Atlas through Motor
- JWT authentication with access and session tokens
- SMTP email delivery
- OpenAI and Anthropic integrations for AI features
- Docker and Docker Compose
- Vercel Python serverless deployment

## Project Structure

```text
victory-fitness-backend/
├── api/
│   └── index.py              # Vercel entry point
├── app/
│   ├── main.py               # FastAPI application and routes
│   ├── config.py             # Environment-driven settings
│   ├── database.py           # MongoDB connection and collections
│   ├── models.py             # Pydantic request/response models
│   ├── dependencies.py       # Auth and role dependencies
│   ├── security.py           # Password hashing and JWT helpers
│   ├── wearables/            # Wearable provider integration layer
│   ├── repositories/         # Data access helpers
│   ├── serializers/          # API serialization helpers
│   └── utils/                # Shared utility functions
├── public/                   # Static assets
├── tests/                    # Test suite
├── .env.example              # Environment variable template
├── requirements.txt          # Python dependencies
├── Dockerfile
├── docker-compose.yml
└── vercel.json
```

## Prerequisites

Install these before running the project:

- Python 3.12
- Git
- MongoDB Atlas database, or another MongoDB instance reachable from your machine
- Docker Desktop, only if you want to run the backend with Docker
- Vercel CLI, only if you want to deploy or test the Vercel build locally

## Installation

From the repository root:

```powershell
cd D:\RAJUAN-PERSONAL\VSCODE\victora\victory-fitness-backend
```

Create and activate a virtual environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
```

The version check should print `Python 3.12.x`. Do not use Python 3.14 for this project because `Pillow==11.2.1` does not provide compatible Windows wheels for that runtime.

Install the Python dependencies:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks virtual environment activation, run this once for the current terminal session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Environment Setup

Create your local environment file from the example:

```powershell
Copy-Item .env.example .env
```

Update `.env` with real values before starting the server. At minimum, configure:

```env
APP_NAME=Victory Fitness API
ENVIRONMENT=development
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster>/<database>?retryWrites=true&w=majority
MONGODB_DB=victory_fitness
JWT_SECRET_KEY=<use-a-long-random-secret>
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:8081
COOKIE_SECURE=false
COOKIE_SAMESITE=lax
```

Important environment variables:

| Variable | Required | Purpose |
| --- | --- | --- |
| `APP_NAME` | No | FastAPI application title. |
| `ENVIRONMENT` | No | Runtime environment, usually `development` or `production`. |
| `MONGODB_URI` | Yes | MongoDB connection string. |
| `MONGODB_DB` | Yes | MongoDB database name. |
| `JWT_SECRET_KEY` | Yes | Secret used to sign application JWTs. Use a strong random value. |
| `JWT_ALGORITHM` | No | JWT signing algorithm. Defaults to `HS256`. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Access token lifetime. Defaults to `10`. |
| `SESSION_TOKEN_EXPIRE_DAYS` | No | Session token lifetime. Defaults to `30`. |
| `CORS_ORIGINS` or `CORS_ORIGIN` | Yes | Comma-separated frontend origins allowed to call the API. |
| `CORS_ALLOW_ALL` | No | Allows all origins when set to `true`; avoid in production. |
| `COOKIE_SECURE` | Yes | Use `false` locally and `true` in HTTPS production. |
| `COOKIE_SAMESITE` | Yes | Use `lax` locally. Use `none` for cross-site HTTPS cookies in production. |
| `SMTP_HOST`, `SMTP_PORT` | Required for email | SMTP server settings for verification and password reset emails. |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Required for email | SMTP credentials. |
| `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME` | Required for email | Sender identity for outbound emails. |
| `OPENAI_API_KEY` | Required for OpenAI features | Enables Coach Victor, meal analysis, workout plans, and nutrition generation where OpenAI is used. |
| `OPENAI_MODEL` | No | Main OpenAI model. |
| `OPENAI_MEAL_ANALYSIS_MODEL` | No | Vision model for meal image analysis. |
| `ANTHROPIC_API_KEY` | Optional | Enables Anthropic-backed AI generation where configured. |
| `ANTHROPIC_MODEL` | Optional | Anthropic model name. |
| `VIMEO_ACCESS_TOKEN` | Optional | Enables Vimeo workout sync and integration status. |
| `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET` | Optional | Enables S3 archive and media upload behavior. |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_PROJECT_ID` | Optional | Google OAuth settings. |
| `FIREBASE_PROJECT_ID`, `FIREBASE_CLIENT_EMAIL`, `FIREBASE_PRIVATE_KEY` | Optional | Firebase auth and push notification credentials. |
| `ADMIN_SEED_ENABLED` | No | Seeds an admin user on startup when enabled. |
| `ADMIN_NAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Required when admin seed is enabled | Initial admin account details. |
| `ADMIN_SEED_SYNC_PASSWORD` | No | Keeps the seeded admin password synchronized with `ADMIN_PASSWORD`. |

Do not commit `.env`. It contains secrets and is ignored by Git.

## Run Locally

Start the API in development mode:

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at:

```text
http://localhost:8000
```

Useful local URLs:

- API root: `http://localhost:8000/`
- Health check: `http://localhost:8000/health`
- Swagger docs: `http://localhost:8000/docs`
- ReDoc docs: `http://localhost:8000/redoc`

## Run With Docker

Make sure `.env` exists first, then run:

```powershell
docker compose up --build
```

The Docker service exposes the API on:

```text
http://localhost:8000
```

Stop the container:

```powershell
docker compose down
```

## Run Tests

Install the test runner if it is not already available:

```powershell
pip install pytest httpx
```

Run the test suite:

```powershell
pytest
```

Run a specific test file:

```powershell
pytest tests/test_integrations.py
```

## Core API Areas

The backend includes endpoints for:

- `GET /health` for service health
- `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`
- `GET /me` and profile update routes
- Workout library and admin workout management
- Challenge participation, challenge chat, and admin challenge management
- Community posts, comments, reactions, and moderation
- Journal entries and AI analysis
- Coach Victor chat and chat history
- Nutrition plan generation, progressive nutrition jobs, and meal analysis
- Longevity OS dashboard, habits, circles, and wearable integrations
- Admin dashboard analytics, users, subscribers, content, FAQs, notifications, and audit logs

Use `/docs` while the server is running for the complete request and response schema.

## Deployment

This project includes `vercel.json` for Vercel deployment. The Vercel entry point is:

```text
api/index.py
```

Before deploying, configure the same environment variables in the Vercel project settings. For production, use:

```env
ENVIRONMENT=production
COOKIE_SECURE=true
COOKIE_SAMESITE=none
CORS_ORIGINS=https://your-app-domain.com,https://your-dashboard-domain.com
```

The Vercel configuration also defines scheduled jobs:

- `POST /jobs/trial-campaign` every hour
- `POST /jobs/nutrition` once per day

## Troubleshooting

If the server cannot connect to MongoDB, verify `MONGODB_URI`, `MONGODB_DB`, Atlas network access, and database user permissions.

If browser requests fail because of CORS, add the frontend URL to `CORS_ORIGINS` and restart the backend.

If login works locally but cookies do not persist in production, verify `COOKIE_SECURE=true`, `COOKIE_SAMESITE=none`, HTTPS, and the frontend API base URL.

If email verification does not send, check the SMTP variables and confirm that the provider allows app passwords or SMTP authentication.

If AI routes fail, verify that the required model provider API key is present and valid.

If `py -3.12 -m venv .venv` prints `No suitable Python runtime found`, install Python 3.12 first, then create the virtual environment again. On Windows, you can install it from the official Python installer or with:

```powershell
winget install Python.Python.3.12
```

Close and reopen PowerShell after installation, then verify:

```powershell
py -0
py -3.12 --version
```

If `pip install -r requirements.txt` fails while building `Pillow` and the output mentions `cpython-314` or `Python 3.14`, delete `.venv`, recreate it with Python 3.12, and reinstall the dependencies.

## Development Notes

- Keep dependencies in `requirements.txt`.
- Keep secrets in `.env` locally and in deployment environment variables for hosted environments.
- Use `/health` after each deployment to confirm the API started successfully.
- Use `/docs` to inspect current route contracts before integrating frontend changes.
