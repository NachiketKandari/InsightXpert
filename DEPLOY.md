# Deployment Guide

InsightXpert deploys as two services:

- **Frontend** (Next.js static export) → Firebase Hosting
- **Backend** (FastAPI container) → Cloud Run

## Architecture

```
GitHub push to main
        │
        ├── deploy-backend
        │     ├── Docker build (backend/)
        │     ├── Push image to GCR
        │     └── Deploy to Cloud Run
        │
        └── deploy-frontend (after backend)
              ├── npm build (static export)
              └── Deploy to Firebase Hosting
```

Firebase Hosting rewrites `/api/**` requests to the Cloud Run backend, so the frontend calls relative API paths and routing is handled at the infrastructure level.

## Prerequisites

- [Firebase CLI](https://firebase.google.com/docs/cli) (`npm install -g firebase-tools`)
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (`gcloud`)
- [GitHub CLI](https://cli.github.com/) (`gh`)

## GCP Project

| Resource | Value |
|----------|-------|
| Project ID | `insightx-487005` |
| Project number | `413119399385` |
| Firebase Hosting URL | https://insightx-487005.web.app |
| Cloud Run service | `insightxpert-api` |
| Cloud Run region | `us-central1` |

## Authentication (Workload Identity Federation)

CI/CD uses **keyless authentication** via Workload Identity Federation — no service account JSON keys are stored in GitHub.

| Resource | Value |
|----------|-------|
| Service account | `github-actions@insightx-487005.iam.gserviceaccount.com` |
| WIF pool | `github-pool` |
| WIF provider | `github-provider` |
| WIF provider full path | `projects/413119399385/locations/global/workloadIdentityPools/github-pool/providers/github-provider` |
| Attribute condition | `assertion.repository == 'NachiketKandari/InsightXpert'` |

### Service account roles

- `roles/run.admin` — deploy Cloud Run services
- `roles/storage.admin` — push Docker images to GCR
- `roles/cloudbuild.builds.builder` — build containers
- `roles/iam.serviceAccountUser` — act as service account during deploy
- `roles/firebasehosting.admin` — deploy to Firebase Hosting

## GitHub Secrets & Variables

### Secrets (Settings → Secrets and variables → Actions → Secrets)

| Secret | Description |
|--------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key for the LLM |
| `SECRET_KEY` | Random hex string for JWT signing |

`GITHUB_TOKEN` is provided automatically by GitHub Actions.

### Variables (Settings → Secrets and variables → Actions → Variables)

These are optional overrides — defaults are set in the workflow files.

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name |
| `CORS_ORIGINS` | `https://insightx-487005.web.app` | Comma-separated allowed origins |

## CI/CD Workflows

### `deploy.yml` — Production deploy

**Trigger:** Push to `main` or manual dispatch.

1. **deploy-backend** — builds Docker image, pushes to GCR, deploys to Cloud Run
2. **deploy-frontend** — builds Next.js static export, deploys to Firebase Hosting (live channel)

### `preview.yml` — PR preview

**Trigger:** Pull request targeting `main`.

1. **test-backend** — installs deps with `uv`, runs `pytest`
2. **test-frontend** — installs deps with `npm`, runs lint + build
3. **preview-hosting** — deploys a temporary Firebase Hosting preview channel and posts the URL as a PR comment

## Key Files

| File | Purpose |
|------|---------|
| `firebase.json` | Firebase Hosting config — serves `frontend/out/`, rewrites `/api/**` to Cloud Run |
| `.firebaserc` | Firebase project ID |
| `backend/Dockerfile` | Containerizes FastAPI backend for Cloud Run |
| `backend/.dockerignore` | Excludes dev files from Docker build |
| `.github/workflows/deploy.yml` | Production deploy workflow |
| `.github/workflows/preview.yml` | PR preview workflow |

## Local Development

Local dev doesn't use Firebase at all. The Next.js dev server proxies `/api/**` to the backend via `rewrites()` in `next.config.ts`.

```bash
# Terminal 1: Backend
cd backend
uv run python -m insightxpert.main

# Terminal 2: Frontend
cd frontend
npm run dev
```

## Manual Deploy

### Backend

```bash
export CLOUDSDK_PYTHON=/opt/homebrew/opt/python@3.12/bin/python3

# Build and push
IMAGE="gcr.io/insightx-487005/insightxpert-api:latest"
docker build -t "$IMAGE" ./backend
docker push "$IMAGE"

# Deploy
gcloud run deploy insightxpert-api \
  --image "$IMAGE" \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated
```

### Frontend

```bash
cd frontend
NEXT_OUTPUT=export npm run build
firebase deploy --only hosting
```

## Troubleshooting

**Docker build fails on `COPY insightxpert.db`**
The Dockerfile generates the database at build time via `generate_data.py`. Make sure `generate_data.py` exists in `backend/`.

**Next.js build fails with "rewrites not supported"**
The `NEXT_OUTPUT=export` env var must be set during the build. This switches to static export mode and disables rewrites (which are dev-only).

**CORS errors in production**
Set the `CORS_ORIGINS` env var on the Cloud Run service to include your Firebase Hosting URL. The workflow defaults to `https://insightx-487005.web.app`.

**Workload Identity Federation auth fails**
Verify the attribute condition matches the repo: `assertion.repository == 'NachiketKandari/InsightXpert'`. The pool only accepts tokens from this exact repository.
