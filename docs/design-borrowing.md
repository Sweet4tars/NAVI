# Travel Agent Design Borrowing

## Purpose

This note records which public travel-agent projects are worth borrowing from, and exactly where their ideas should land in the current codebase.

## Borrow First

### `akka-samples/travel-agent`

What to borrow:
- Stateful workflow orchestration
- Durable task state instead of fire-and-forget background work
- Idempotent resume semantics

Why it fits:
- The current project already has `jobs`, `source_status`, and `checkpoint` concepts.
- The main gap is not feature breadth. It is workflow rigor.

Where to land it:
- `travel_planner/service.py`
- `travel_planner/database.py`
- `travel_planner/schemas.py`

Concrete changes:
- Split one big `run_sync()` into named workflow phases with explicit phase ownership.
- Persist phase completion and per-source artifacts in checkpoint state.
- Add a lightweight lease or run token so the same job cannot be resumed concurrently from multiple browser rechecks.
- Make resume idempotent: resuming a completed phase should only reuse persisted artifacts.

What not to copy:
- Do not copy backend framework choices or Akka-specific patterns.
- Copy the workflow discipline, not the stack.

### `OSU-NLP-Group/TravelPlanner`

What to borrow:
- Clear hard constraints vs. soft preferences separation
- Explicit infeasibility reasoning

Why it fits:
- The current planner mixes user preferences, placeholder prices, and route heuristics in one score.
- For multi-person, multi-city self-drive trips, hard constraints matter more than polish.

Where to land it:
- `travel_planner/schemas.py`
- `travel_planner/planner/engine.py`

Concrete changes:
- Add explicit route constraints: latest return time, max daily drive hours, max days per base city, driver rotation hints.
- Add lodging constraints: required parking, required real hotel vs. strategy suggestion, minimum room count.
- Make planner output say when a request is feasible only with tradeoffs.
- Add a distinct explanation block for why a city or hotel was rejected.

What not to copy:
- Do not overfit to benchmark datasets.
- Keep the current China-roadtrip use case as the primary target.

### `CrewAI / LangGraph travel planner demos`

What to borrow:
- Role decomposition
- Artifact handoff contracts between research, lodging, transport, and itinerary stages

Why it fits:
- The current service already behaves like a multi-role pipeline, but the roles are implicit.
- Making them explicit will reduce connector coupling and make source-specific retries safer.

Where to land it:
- `travel_planner/service.py`
- `travel_planner/connectors/*`
- `travel_planner/planner/engine.py`

Concrete changes:
- Define stable intermediate artifacts:
  - guide artifact
  - hotel artifact
  - transport artifact
  - POI artifact
- Make each source write one artifact payload into checkpoint state.
- Rebuild final itinerary only from artifacts, not from direct scraper side effects.

What not to copy:
- Do not introduce orchestration libraries unless they replace real pain.
- The current project is still small enough to keep orchestration in Python code.

### `OpenTripPlanner`

What to borrow:
- Unified route-leg abstraction
- Travel-time matrix thinking

Why it fits:
- The current roadtrip logic still treats transport as one label plus one number.
- Multi-stop Yunnan self-drive plans need route legs and transfer costs.

Where to land it:
- `travel_planner/schemas.py`
- `travel_planner/connectors/map.py`
- `travel_planner/connectors/rail.py`
- `travel_planner/planner/engine.py`

Concrete changes:
- Add a route-leg model with start, end, duration, distance, and confidence.
- Precompute travel-time penalties between hotel areas and POIs.
- Penalize itineraries that require cross-district moves after long drive days.

What not to copy:
- Do not bring in OTP itself for this project.
- Borrow the modeling pattern only.

### General scraper-engineering repos

What to borrow:
- Site adapter boundaries
- Per-site parser tests and fixture discipline
- Route health checks

Why it fits:
- The current hotel connector still carries too much multi-site logic in one file.
- Qunar and Fliggy are already specialized enough to justify stronger boundaries.

Where to land it:
- `travel_planner/connectors/browser.py`
- `travel_planner/connectors/hotels.py`
- `tests/fixtures/*`
- `tests/test_parsers.py`

Concrete changes:
- Split hotel adapters by site once one file becomes the bottleneck.
- Add route availability checks as first-class source capability probes.
- Persist source-level route health in checkpoint or source-state metadata.
- Add parser confidence metrics per source.

## Borrow Second

### Use external projects for patterns, not code

For Qunar and Fliggy specifically:
- Public GitHub repos rarely contain a current and reliable crawler for the live consumer hotel flows.
- What is worth borrowing is the reverse-engineering method:
  - inspect frontend bundle
  - capture active request chain
  - classify login vs. slider vs. dead route
  - checkpoint and resume after human verification

## Immediate Adoption Order

1. Workflow rigor from `akka-samples/travel-agent`
2. Constraint modeling from `OSU-NLP-Group/TravelPlanner`
3. Role and artifact separation from CrewAI/LangGraph demos
4. Route-leg abstraction from `OpenTripPlanner`
5. Scraper adapter hardening from generic crawler repos
