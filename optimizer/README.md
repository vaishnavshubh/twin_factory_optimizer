# Smart Factory Digital Twin Optimizer

LangGraph + FastAPI orchestration layer for factory-floor optimization on top of
OFacT. Deploy target: **Google Cloud Run**.

## Why this package exists

OFacT (`ofact/`) already provides:

- Excel static twin models under `projects/*/models/twin/`
- SPADE multi-agent shop-floor control
- A Flask scenario-analytics API

This `optimizer/` package sits **beside** that framework. It ingests twin state,
predicts bottlenecks, and proposes rerouting actions via LangGraph — without
forking OFacT's agent runtime.

## Layout

| Path | Role |
|------|------|
| `infrastructure/` | OFacT connector stubs, env config |
| `models/` | `FactoryState` LangGraph schema (Step 2) |
| `agents/` | LangGraph nodes and compiled graph (Step 3) |
| `api/` | FastAPI `/optimize` endpoint (Step 4) |

## Twin path convention

OFacT resolves static models as:

```text
projects/{project_name}/models/twin/{state_model_file}
```

Defaults match the OFacT **Bicycle World** factory:

- Project: `bicycle_world`
- File: `bicycle_factory.xlsx`
- Path: `projects/bicycle_world/scenarios/current/models/twin/bicycle_factory.xlsx`
- Stations: `body_kit_ws` → `gear_shift_brakes_ws` → `lightning_pedal_saddle_ws` → `wheel_ws` → `painting_ws`

Tutorial twin still works: set project to `tutorial` (resolves `models/twin/mini_model.xlsx`).

## FactoryState (Step 2)

LangGraph shared state lives in `optimizer.models.factory_state.FactoryState`:

| Field | Role |
|-------|------|
| `current_utilization` | `resource_id → float` from twin/stub |
| `assembly_sequence` | Ordered tutorial processes |
| `identified_bottlenecks` | Filled by predictor (Step 3) |
| `proposed_actions` | Filled by rerouting agent (Step 3) |

Bridge from connector: `factory_state_from_floor_snapshot(read_factory_floor_state(...))`.

```bash
PYTHONPATH=. python3 -c "
from optimizer.infrastructure.ofact_connector import read_factory_floor_state
from optimizer.models import factory_state_from_floor_snapshot
state = factory_state_from_floor_snapshot(read_factory_floor_state('tutorial'))
print(state['current_utilization'].keys())
print(state['identified_bottlenecks'], state['proposed_actions'])
"
```

## LangGraph workflow (Step 3)

```text
START → ofact_reader → bottleneck_predictor → rerouting_agent → END
```

```bash
PYTHONPATH=. python3 -c "
from optimizer.agents import run_optimize
result = run_optimize(project_name='tutorial')
print(result['identified_bottlenecks'])
print(result['proposed_actions'])
"
```

Compiled export: ``optimizer.agents.optimize_graph``.

## Stub vs live mode

Set `OFACT_MODE` (default `stub`):

- `stub` — Bicycle World / tutorial Excel light-parse (no SPADE/XMPP)
- `live` — reserved for `deserialize_state_model` integration (scaffolded in Step 1)

Secrets such as `OPENAI_API_KEY` must come from environment variables; never hardcode them.

## Quick smoke test (Step 1)

```bash
cd /path/to/ofact
PYTHONPATH=. python3 -c "
from optimizer.infrastructure.ofact_connector import read_factory_floor_state
state = read_factory_floor_state('tutorial')
print(state['current_utilization'])
print(state['assembly_sequence'])
"
```

## Portfolio demo UI

Open the interactive demo (same process as the API):

[http://127.0.0.1:8080/](http://127.0.0.1:8080/)

Click **Run optimization** to invoke the LangGraph agents and render bottlenecks
plus proposed actions. API reference remains at `/docs`.

## FastAPI (Step 4)

```bash
pip install -r optimizer/requirements.txt
PYTHONPATH=. uvicorn optimizer.api.app:app --host 0.0.0.0 --port 8080
```

```bash
curl -s -X POST http://127.0.0.1:8080/optimize \
  -H 'Content-Type: application/json' \
  -d '{"project_name":"tutorial"}' | python3 -m json.tool
```

OpenAPI docs: `http://127.0.0.1:8080/docs`

## Docker / Cloud Run (Step 5)

See [`CLOUD_RUN.md`](CLOUD_RUN.md) for full deploy commands.

```bash
docker build -t smart-factory-optimizer:local .
docker run --rm -p 8080:8080 smart-factory-optimizer:local
```

**You do not need to share GCP credentials with the agent.** Run `gcloud auth login` on your machine, then:

```bash
gcloud run deploy smart-factory-optimizer \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8080 \
  --set-env-vars "OFACT_MODE=stub,OFACT_PROJECT=tutorial" \
  --memory 1Gi
```

## Roadmap

1. Project setup & OFacT stubbing
2. LangGraph `FactoryState` schema
3. Multi-agent LangGraph nodes
4. FastAPI orchestrator
5. Docker multi-stage build → `gcloud run deploy`
6. Demo UI (portfolio click-through) ← current
