# Smart Factory Digital Twin Optimizer

Multi-agent factory-floor optimization on top of an open-source digital twin.

This portfolio project reads plant twin state, detects workstation bottlenecks, and proposes rerouting actions through a LangGraph agent pipeline — exposed as a FastAPI service and deployable to Google Cloud Run.

**Live demo:** [smart-factory-optimizer on Cloud Run](https://smart-factory-optimizer-dczdrdacca-uc.a.run.app/)

---

## What it does

Manufacturing plants face shifting demand, uneven station load, and material waits that are hard to diagnose from static dashboards alone. This system:

1. **Ingests** digital-twin floor state (utilization, assembly sequence, inventory context)
2. **Predicts** bottlenecks above a configurable utilization threshold
3. **Proposes** concrete actions (load balancing, material staging, sequence tweaks)
4. **Serves** results via REST + a lightweight browser demo

Default scenario: OFacT **Bicycle World** (`bicycle_factory.xlsx`) — a multi-station assembly plant (body kit → gear/brakes → lighting/pedals/saddle → wheels → painting).

---

## Architecture

```text
┌─────────────────┐     ┌──────────────────────────────────────┐
│  Digital Twin   │────▶│  LangGraph agents                    │
│  (OFacT Excel / │     │  ofact_reader → bottleneck_predictor │
│   stub connector)│     │  → rerouting_agent                   │
└─────────────────┘     └──────────────────┬───────────────────┘
                                           │
                                           ▼
                                    ┌──────────────┐
                                    │   FastAPI    │
                                    │  /optimize   │
                                    │  / (demo UI) │
                                    └──────┬───────┘
                                           │
                                           ▼
                                    Google Cloud Run
```

| Layer | Location | Role |
|-------|----------|------|
| Twin framework | `ofact/` | Open Factory Twin (upstream) — state model, projects, simulation |
| Optimizer | `optimizer/` | LangGraph orchestration, connector, API, demo UI |
| Deploy | `Dockerfile`, `.gcloudignore` | Multi-stage image → Cloud Run |

The optimizer sits **beside** OFacT; it does not replace SPADE shop-floor agents or the Flask analytics API.

---

## Stack

- **Python 3.12** · **LangGraph** · **FastAPI** · **Uvicorn**
- **OFacT** digital twin (Apache 2.0) — [OpenFactoryTwin/ofact](https://github.com/OpenFactoryTwin/ofact)
- **Docker** · **Google Cloud Run** · **Cloud Build** / Artifact Registry

---

## Quick start (local)

```bash
# from repo root
python3 -m venv .venv && source .venv/bin/activate
pip install -r optimizer/requirements.txt

export PYTHONPATH=.
export OFACT_MODE=stub
export OFACT_PROJECT=bicycle_world

uvicorn optimizer.api.app:app --host 0.0.0.0 --port 8080
```

Then open:

- Demo UI — http://127.0.0.1:8080/
- OpenAPI — http://127.0.0.1:8080/docs
- Health — http://127.0.0.1:8080/health

```bash
curl -s -X POST http://127.0.0.1:8080/optimize \
  -H 'Content-Type: application/json' \
  -d '{"project_name":"bicycle_world"}' | python3 -m json.tool
```

---

## Agent pipeline

Shared state: `FactoryState` (`optimizer/models/factory_state.py`)

| Node | Responsibility |
|------|----------------|
| `ofact_reader` | Load utilization + assembly sequence from twin/stub |
| `bottleneck_predictor` | Flag stations above `BOTTLENECK_THRESHOLD` (default 0.80) |
| `rerouting_agent` | Propose balance / staging / sequence actions |

```bash
PYTHONPATH=. python3 -c "
from optimizer.agents import run_optimize
r = run_optimize(project_name='bicycle_world')
print(r['identified_bottlenecks'])
print(r['proposed_actions'])
"
```

---

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `OFACT_MODE` | `stub` | `stub` = Excel light-parse (no SPADE); `live` reserved |
| `OFACT_PROJECT` | `bicycle_world` | Twin project under `projects/` |
| `OFACT_STATE_MODEL_FILE` | `bicycle_factory.xlsx` | Static twin workbook |
| `OFACT_TWIN_DIR` | `scenarios/current/models/twin` | Relative twin folder |
| `BOTTLENECK_THRESHOLD` | `0.80` | Utilization cutoff for bottlenecks |
| `PORT` | `8080` | Cloud Run / local listen port |

Secrets (e.g. `OPENAI_API_KEY` if you later add LLM nodes) must come from the environment — never commit them.

---

## Deploy to Cloud Run

See [`optimizer/CLOUD_RUN.md`](optimizer/CLOUD_RUN.md) for full steps.

```bash
gcloud run deploy smart-factory-optimizer \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8080 \
  --memory 2Gi \
  --set-env-vars "OFACT_MODE=stub,OFACT_PROJECT=bicycle_world,OFACT_STATE_MODEL_FILE=bicycle_factory.xlsx,OFACT_TWIN_DIR=scenarios/current/models/twin"
```

---

## Repository layout

```text
.
├── optimizer/           # Portfolio application (agents, API, UI, config)
│   ├── agents/          # LangGraph nodes + compiled graph
│   ├── api/             # FastAPI app + static demo
│   ├── infrastructure/  # Config + OFacT connector
│   ├── models/          # FactoryState schema
│   ├── CLOUD_RUN.md
│   └── README.md        # Deeper package notes
├── ofact/               # Upstream Open Factory Twin framework
├── projects/            # Twin Excel models (bicycle_world, tutorial, …)
├── Dockerfile
└── requirements via optimizer/requirements.txt
```

---

## Attribution

Built on **[Open Factory Twin (OFacT)](https://github.com/OpenFactoryTwin/ofact)** by Fraunhofer ISST / OpenFactoryTwin contributors, licensed under Apache 2.0. This repository adds the `optimizer/` orchestration layer for portfolio demonstration; OFacT remains the digital-twin foundation.

---

## Author

**Shubh Vaishnav** — Data Engineering / AI systems portfolio project.
