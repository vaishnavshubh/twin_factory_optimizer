# Google Cloud Run deploy (Step 5)

## Credentials — do you need to give them to the agent?

**No.** Do not paste service-account keys or passwords into chat.

Deploy from **your** machine (or CI) where you are already logged in:

```bash
gcloud auth login
gcloud config set project ofact-504514
```

Enable APIs once per project:

```bash
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
```

## Local image smoke test (before deploy)

From the repo root (`ofact/`):

```bash
docker build -t smart-factory-optimizer:local .
docker run --rm -p 8080:8080 -e PORT=8080 smart-factory-optimizer:local
```

Then:

```bash
curl -s http://127.0.0.1:8080/health
curl -s -X POST http://127.0.0.1:8080/optimize \
  -H 'Content-Type: application/json' \
  -d '{"project_name":"bicycle_world"}'
```

## Redeploy after a code fix

**Important:** root ``.gitignore`` previously had a bare ``main.py`` rule, which
made ``gcloud run deploy --source`` omit the ASGI module from the image
(``Could not import module optimizer.api.main``). The app module is now
``optimizer/api/app.py``, and ``.gcloudignore`` controls the upload set.

```bash
gcloud run deploy smart-factory-optimizer \
  --source . \
  --region us-central1 \
  --project ofact-504514 \
  --allow-unauthenticated \
  --port 8080 \
  --memory 2Gi \
  --cpu 2 \
  --cpu-boost \
  --set-env-vars "OFACT_MODE=stub,OFACT_PROJECT=bicycle_world,OFACT_STATE_MODEL_FILE=bicycle_factory.xlsx,OFACT_TWIN_DIR=scenarios/current/models/twin" \
  --max-instances 3
```

The container entrypoint is ``python -m optimizer.api.entrypoint`` (binds ``$PORT`` and ensures ``/app`` is on ``sys.path``).

Notes:

- `--source .` uses Cloud Build + this `Dockerfile` (no local Docker required).
- `--allow-unauthenticated` makes the URL clickable for portfolio demos. Tighten later if needed.
- Put secrets (e.g. `OPENAI_API_KEY`) via Secret Manager / `--set-secrets`, never in the image.
- After deploy, `gcloud run services describe smart-factory-optimizer --region us-central1 --format='value(status.url)'` prints the public URL.

## Alternative: build locally and push to Artifact Registry

```bash
PROJECT_ID=ofact-504514
REGION=us-central1
REPO=optimizer
IMAGE=${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/smart-factory-optimizer:latest

gcloud artifacts repositories create ${REPO} \
  --repository-format=docker --location=${REGION} --project=${PROJECT_ID} || true

gcloud auth configure-docker ${REGION}-docker.pkg.dev
docker build -t ${IMAGE} .
docker push ${IMAGE}

gcloud run deploy smart-factory-optimizer \
  --image ${IMAGE} \
  --region ${REGION} \
  --project ${PROJECT_ID} \
  --allow-unauthenticated \
  --port 8080 \
  --set-env-vars "OFACT_MODE=stub,OFACT_PROJECT=bicycle_world,OFACT_STATE_MODEL_FILE=bicycle_factory.xlsx,OFACT_TWIN_DIR=scenarios/current/models/twin" \
  --memory 2Gi
```
