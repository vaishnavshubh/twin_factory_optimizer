# Smart Factory Digital Twin Optimizer

Factories don’t fail because nobody has a dashboard.  
They fail because the dashboard doesn’t tell you **what to do next**.

This project takes a plant digital twin, finds overloaded stations, and turns that into concrete moves — shift work, stage kits, reallocate mobile resources — through a small multi-agent pipeline you can hit as an API.

**Try it:** [live demo on Cloud Run](https://smart-factory-optimizer-xmdsqty7zq-uc.a.run.app/)

---

## The problem I cared about

A twin can describe the floor: stations, warehouses, process order.  
Utilization tells you who’s drowning. What’s missing is the decision layer:

> Painting is at 94%. Body kit is at 91%. Lighting/pedals has slack at 72%.  
> So… move what, from where, to where — and why?

I built that layer.

---

## How it works

Three LangGraph agents share one typed `FactoryState`:

```text
ofact_reader → bottleneck_predictor → rerouting_agent
```

| Agent | Job |
|-------|-----|
| **Reader** | Pull twin structure + floor snapshot into shared state |
| **Predictor** | Flag resources over a utilization threshold (default 80%) |
| **Rerouter** | Emit actions: load balance, material staging, AMR reallocation |

FastAPI wraps the graph (`POST /optimize`). A lightweight UI sits on `/`. Same service ships to Cloud Run.

**Deliberate choice:** rule-based agents first. Deterministic, explainable, demo-stable. LLM hooks exist in config for later — not required to run.

---

## Tech stack

**Python 3.12 · LangGraph · FastAPI · Uvicorn · pandas/openpyxl · Docker · Google Cloud Run**  
Twin foundation: [OFacT](https://github.com/OpenFactoryTwin/ofact) (Apache 2.0). Default plant: Bicycle World assembly line.

---

## Design decisions that matter

1. **Optimizer beside the twin, not inside it** — OFacT owns the model; `optimizer/` owns decisions + API. Clean swap path from stub → live twin without rewriting agents.
2. **Stub utilization on real topology** — Excel gives real station labels; synthetic util makes bottleneck logic testable without SPADE/sensors. Honest boundary, working product.
3. **Productized end-to-end** — not a notebook. API, UI, Docker, Cloud Run. If it doesn’t deploy, it doesn’t count.

---

## Run it

```bash
pip install -r optimizer/requirements.txt
export PYTHONPATH=. OFACT_MODE=stub OFACT_PROJECT=bicycle_world
uvicorn optimizer.api.app:app --host 0.0.0.0 --port 8080
```

Open http://127.0.0.1:8080/ or hit `/docs`.

---

## What’s next when this grows up

- Live twin / MES utilization instead of stubs  
- Validator node for “graph succeeded but action is nonsense”  
- Optional sim feedback before recommendations go to operators  

The architecture already assumes those upgrades.

---

## Author

**Shubh Vaishnav** · [twin_factory_optimizer](https://github.com/vaishnavshubh/twin_factory_optimizer)
