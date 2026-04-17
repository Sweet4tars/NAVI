# Qunar And Fliggy Roadmap

## Current Facts

### Qunar

- Agent login state is valid.
- The agent profile can open the Qunar account order page as a logged-in user.
- The current `global` search page still builds a domestic result URL under `/cn/{cityUrl}`.
- That domestic route currently redirects to the Qunar homepage.
- Therefore the blocker is route availability, not login.

### Fliggy

- Agent login state is valid after manual Taobao or Fliggy login.
- Agent can build a real result URL via `CitySuggest.do -> cityCode -> hotel_list3.htm`.
- Agent can parse first-screen recommended hotels from the result page.
- The remaining blocker is not login, but richer result parsing and slider recurrence.

## Qunar Roadmap

### Goal

Upgrade Qunar from `region_hint` source to a true hotel list source.

### Current code touch points

- `travel_planner/connectors/hotels.py`
- `travel_planner/connectors/browser.py`
- `travel_planner/service.py`
- `tests/test_parsers.py`

### Track A: Replace the dead domestic route

Objective:
- Find the current live hotel list entry point that replaced `/cn/{cityUrl}`.

Method:
- Continue reverse-engineering the frontend bundle around the search button flow.
- Capture every request after city selection and before popup navigation.
- Search for new H5 or app-style result routes rather than desktop routes.

Acceptance:
- A URL or API that returns a real hotel list for a domestic city while logged in.

Implementation target:
- Add a dedicated `fetch_qunar_list()` path in `HotelConnector`.
- Keep the existing `region_hint` path as fallback only.

### Track B: Move from route guessing to request replay

Objective:
- If no stable web URL exists, use the live request chain instead of public routes.

Method:
- Capture browser network requests while selecting a city and submitting search.
- Identify authenticated JSON or HTML list payloads.
- Replay only the minimum required requests with browser cookies or in-page fetch.

Implementation target:
- Add a helper in `browser.py` or a site-specific adapter that can run `page.evaluate(fetch(...))` inside the logged-in context.
- Persist the discovered endpoint shape and required parameters in source checkpoint state.

Acceptance:
- A reproducible function that returns hotel cards for a domestic city without opening a popup to the homepage.

### Qunar fallback contract

If the list route is still unavailable:
- `candidate_kind` must stay `region_hint`
- `price_confidence` must stay `estimated`
- UI and summary must explicitly say Qunar is providing location guidance, not real hotel inventory

## Fliggy Roadmap

### Goal

Upgrade Fliggy from first-screen recommendation parsing to real result card parsing.

### Current code touch points

- `travel_planner/connectors/hotels.py`
- `travel_planner/connectors/browser.py`
- `travel_planner/service.py`
- `tests/test_parsers.py`

### Track A: Result page DOM parsing

Objective:
- Parse more than the current top recommendation text block.

Method:
- Inspect the logged-in `hotel_list3.htm` DOM after slider completion.
- Identify stable card wrappers, detail links, tags, and visible prices.
- Prefer real card nodes over the current text slicing fallback.

Acceptance:
- Extract at least:
  - hotel name
  - visible price when present
  - district or area label when present
  - 2-4 visible feature tags

### Track B: Slider-aware workflow

Objective:
- Make repeated slider interruptions survivable without losing job progress.

Method:
- Keep current manual verification flow.
- Treat slider pages as `awaiting_login` or `awaiting_verification` style states at the source level.
- Resume from source checkpoint, not from the top of the job.

Acceptance:
- A job that was blocked only on Fliggy should resume just the Fliggy source after verification.

## Cross-Cutting Changes

### Candidate typing

Use these meanings consistently:
- `hotel`: real candidate from a hotel result source
- `strategy`: policy or price-band suggestion
- `region_hint`: area or landmark guidance

### Price confidence

Use these meanings consistently:
- `observed`: seen on page or in payload
- `hidden`: page confirms a hidden or login-only price
- `estimated`: not a real observed booking price

### Checkpoint shape

Persist per-source artifacts under checkpoint state:
- source status
- source warnings
- serialized candidates
- serialized source evidence
- route health metadata when relevant

## Validation Scenario

Use this scenario for end-to-end regression:

- Four travelers:
  - Chengdu Xiaomao
  - Chongqing Xiaotang
  - Chongqing Xiaozhang
  - Yibin Xiaoxiong
- April 30 evening: gather in Yibin
- May 5 evening: return to Yibin and disband
- Mode: Yunnan self-drive trip

What to validate:
- Partial job can stop on one source verification and resume only that source.
- Qunar result should clearly say whether it is a real hotel list or region fallback.
- Fliggy result should survive manual slider verification and re-enter the same job.
- Ctrip login state should remain reusable and not regress to anonymous parsing.

## Recommended Next Implementation Order

1. Qunar live list endpoint discovery or replay path
2. Fliggy real card parsing on `hotel_list3.htm`
3. UI badges and warnings for `candidate_kind` and `price_confidence`
4. Full UI-level manual-verification recovery regression for the Yunnan roadtrip case
