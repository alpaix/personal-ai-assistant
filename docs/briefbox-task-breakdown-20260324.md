# BriefBox Task Breakdown

Derived from:
- `docs/briefbox-engineering-design-20260324.md`
- `docs/briefbox-design-20260323.md`
- `docs/ai-assistant-prd.md`

Status: READY FOR IMPLEMENTATION
Branch: `work`

## Delivery Strategy

Build the demo in thin vertical slices, but lock in the risky foundations first:
1. fixture schema
2. fallback rules
3. model contract
4. orchestrator
5. API
6. UI
7. actions
8. demo hardening

This keeps the branch small while still boiling the lake on reliability and tests.

## Milestone Plan

### Milestone 0: Project Skeleton

Goal: create a runnable local app skeleton without implementing triage logic yet.

#### Task 0.1: Scaffold backend and frontend entrypoints

Scope:
- create `briefbox/app/`
- create `briefbox/chainlit_app.py`
- create package init files as needed

Done means:
- FastAPI app starts locally
- Chainlit app starts locally
- health endpoint returns 200
- placeholder UI renders a header and "Triage Inbox" control

Depends on:
- none

#### Task 0.2: Add local developer run path

Scope:
- add one command or short script to run backend + Chainlit locally
- document required local services: Ollama, model name, ports

Done means:
- a new contributor can start the demo stack without guessing commands
- startup instructions live in repo docs

Depends on:
- Task 0.1

#### Task 0.3: Add test harness and baseline CI command

Scope:
- choose Python test framework
- add unit test command
- add one smoke test for app startup

Done means:
- `pytest` or equivalent runs locally
- CI/test command is documented
- at least one backend smoke test passes

Depends on:
- Task 0.1

### Milestone 1: Data Contracts and Fixture Loader

Goal: define the message schema and make the seeded dataset safe and deterministic.

#### Task 1.1: Define canonical message models

Scope:
- define Pydantic models for raw fixture message, normalized message, run status, result payload, trace step, action response
- define lane/category enums

Done means:
- every API payload has an explicit model
- no free-form dicts are required across module boundaries

Depends on:
- Task 0.1

#### Task 1.2: Create `monday-chaos-v1` fixture schema

Scope:
- define required fields for each message:
  - `message_id`
  - sender fields
  - timestamp
  - subject
  - body
  - optional headers including `List-Unsubscribe`
- document fixture file format

Done means:
- schema supports all planned triage outputs
- fixture format is stable enough for tests and cached results

Depends on:
- Task 1.1

#### Task 1.3: Build fixture loader and validator

Scope:
- load fixture by id
- validate file exists
- validate schema
- reject duplicate `message_id`
- normalize missing optional fields

Done means:
- happy-path fixture load works
- malformed fixture yields clear error
- duplicate ids are rejected deterministically

Depends on:
- Task 1.2

#### Task 1.4: Author seed dataset

Scope:
- create 50-60 realistic emails
- ensure coverage across:
  - urgent asks
  - shipments
  - travel
  - events
  - promotions
  - newsletters
  - unsubscribe-supported messages
  - malformed/noisy edge cases

Done means:
- dataset drives all three lanes
- at least 3 strong deadline/follow-up examples exist
- dataset includes both supported and unsupported unsubscribe cases

Depends on:
- Task 1.2

### Milestone 2: Deterministic Rules and Fallback

Goal: ensure the app remains useful even when the model is slow, wrong, or unavailable.

#### Task 2.1: Implement fallback classification heuristics

Scope:
- sender/domain allowlists
- keyword matching for shipments, deadlines, travel, events, promotions
- lane suggestion logic

Done means:
- fallback can classify every fixture email into a usable lane
- heuristic results are deterministic

Depends on:
- Task 1.3
- Task 1.4

#### Task 2.2: Implement fallback extraction heuristics

Scope:
- lightweight extraction for deadlines, events, shipment cues, unsubscribe candidate
- `needs_review` marker for total parse failure cases

Done means:
- every message can produce a minimum viable summary/result even without model output
- fallback output conforms to the same result contract as model-backed output

Depends on:
- Task 2.1

#### Task 2.3: Add cached-result fallback artifact

Scope:
- define cached result file format
- allow one fixture-specific precomputed result snapshot

Done means:
- app can serve a complete demo result if live inference times out
- cached result is clearly labeled as fallback-derived

Depends on:
- Task 1.4
- Task 2.2

### Milestone 3: Ollama Client and Structured Model Contract

Goal: make model calls boring, validated, and replaceable.

#### Task 3.1: Implement Ollama client wrapper

Scope:
- local HTTP client for Ollama
- model name/config centralization
- timeout handling
- latency measurement

Done means:
- one wrapper owns all model I/O
- timeouts raise typed errors, not raw transport exceptions

Depends on:
- Task 1.1

#### Task 3.2: Define strict JSON prompt/output contract

Scope:
- prompts for classify, summarize, prioritize, extract_actions stages
- strict JSON-only instruction
- schema validation for every stage output

Done means:
- prose output is treated as failure
- invalid or incomplete JSON cannot leak into the API response shape

Depends on:
- Task 3.1
- Task 1.1

#### Task 3.3: Implement model result validation and clamping

Scope:
- confidence range clamping
- priority score range clamping
- required-key enforcement
- invalid field fallback routing

Done means:
- semantically invalid model output degrades safely
- trace records validation failures explicitly

Depends on:
- Task 3.2
- Task 2.2

### Milestone 4: Orchestrator and Run Store

Goal: create the core triage engine with explicit stage execution and durable run state.

#### Task 4.1: Build in-memory run store

Scope:
- create/update/read run records
- statuses: `queued`, `running`, `completed`, `failed`, `partial`
- store board, trace, errors, action state

Done means:
- API can poll a run independently of orchestration internals
- one source of truth exists for UI state

Depends on:
- Task 1.1

#### Task 4.2: Add JSON snapshot persistence

Scope:
- save terminal run snapshots to disk
- optionally load cached/precomputed result snapshots

Done means:
- server restart does not destroy prepared demo artifacts
- terminal results can be inspected offline

Depends on:
- Task 4.1

#### Task 4.3: Implement `TriageOrchestrator`

Scope:
- batch messages
- run four named stages
- merge model and fallback outputs
- record per-message trace
- compute final lanes and aggregate stats

Done means:
- one run can process the full fixture end to end
- stage trace is attached to each message
- board output is deterministic for fallback-only mode

Depends on:
- Task 2.2
- Task 3.3
- Task 4.1

#### Task 4.4: Handle timeout, partial, and dedupe behavior

Scope:
- full-run deadline
- batch timeout handling
- partial completion rules
- duplicate run trigger protection

Done means:
- double-clicking "Triage Inbox" does not create duplicate concurrent runs
- a single bad batch does not blank the whole board
- run status clearly reflects `partial` vs `failed`

Depends on:
- Task 4.3

### Milestone 5: FastAPI Surface

Goal: expose a stable backend contract for the UI.

#### Task 5.1: Implement `POST /triage/run`

Scope:
- fixture selection
- run creation
- async or background launch

Done means:
- valid fixture returns `run_id`
- invalid fixture returns structured 4xx error

Depends on:
- Task 4.3

#### Task 5.2: Implement `GET /triage/status/{run_id}`

Scope:
- lightweight polling payload
- no full trace payload here

Done means:
- polling remains small and fast
- unknown run id returns clear non-500 error

Depends on:
- Task 4.1
- Task 5.1

#### Task 5.3: Implement `GET /triage/result/{run_id}`

Scope:
- final board
- trace payload
- summary stats
- fallback badge data

Done means:
- completed and partial runs are renderable by the UI
- board, trace, and summary stats are top-level stable sections

Depends on:
- Task 4.4
- Task 5.1

### Milestone 6: Local Actions and Unsubscribe

Goal: make the demo interactive after triage completes.

#### Task 6.1: Implement `POST /actions/message`

Scope:
- support `archive`, `pin`, `snooze`
- mutate run-store-owned message state
- enforce idempotency

Done means:
- repeated clicks do not corrupt card state
- action responses are immediately renderable by the UI

Depends on:
- Task 4.1
- Task 5.3

#### Task 6.2: Implement `List-Unsubscribe` parser

Scope:
- parse `mailto:` and `http(s):` targets
- reject unsupported/malformed values safely

Done means:
- parser clearly distinguishes supported, unsupported, and invalid headers

Depends on:
- Task 1.4

#### Task 6.3: Implement `POST /actions/unsubscribe`

Scope:
- execute mailto/http unsubscribe
- record result status and user-facing message
- keep unsupported flows explicit

Done means:
- supported unsubscribe attempts run for real
- network/transport failure is recoverable and visible
- unsupported flows say "Manual unsubscribe required"

Depends on:
- Task 6.2
- Task 4.1

### Milestone 7: Chainlit UI

Goal: render the demo clearly and keep trace visibility high without making the interface noisy.

#### Task 7.1: Build shell layout

Scope:
- header
- fixture selector
- triage button
- three-lane board container
- trace panel container
- details/action drawer

Done means:
- layout works before live data wiring
- board and trace regions are visually distinct

Depends on:
- Task 0.1

#### Task 7.2: Wire run trigger and status polling

Scope:
- call `POST /triage/run`
- poll `GET /triage/status/{run_id}` every `750ms`
- transition to result fetch on terminal state

Done means:
- user can start a run from the UI
- progress is visible without full trace payload churn

Depends on:
- Task 5.1
- Task 5.2
- Task 7.1

#### Task 7.3: Render board and trace result view

Scope:
- render `Do Now`, `Track`, `Ignore`
- render collapsed trace cards by default
- show confidence, priority, rationale, latency
- add fallback badge

Done means:
- final result is legible in a live demo
- trace expands per message without blocking the board

Depends on:
- Task 5.3
- Task 7.2

#### Task 7.4: Wire local actions and unsubscribe UX

Scope:
- action buttons on message cards
- inline unsubscribe result state
- optimistic or immediate refresh from backend state

Done means:
- pin/archive/snooze visibly update the card
- unsubscribe success/failure/unsupported states are obvious

Depends on:
- Task 6.1
- Task 6.3
- Task 7.3

### Milestone 8: Demo Hardening

Goal: remove live-demo fragility.

#### Task 8.1: Add prewarm path for Ollama/model

Scope:
- simple command or startup hook to warm the model

Done means:
- cold-start latency is reduced before presenting

Depends on:
- Task 3.1

#### Task 8.2: Add cached result fallback toggle and badge

Scope:
- use cached result when timeout policy triggers
- make fallback visible in backend and UI

Done means:
- timeout path never presents a blank board
- demo operator can explain degraded mode honestly

Depends on:
- Task 2.3
- Task 5.3
- Task 7.3

#### Task 8.3: Add demo rehearsal checklist

Scope:
- fixture selected
- Ollama running
- model warmed
- ports verified
- fallback result present
- known action demo message identified
- known unsubscribe demo message identified

Done means:
- demo can be rehearsed repeatably by following a short checklist

Depends on:
- Milestones 1-8 implementation

## Test Breakdown

### Backend unit tests

#### Task T1: Fixture loader tests

Cover:
- valid fixture load
- missing fixture
- duplicate `message_id`
- malformed schema

Maps to:
- `tests/test_fixtures.py`

#### Task T2: Rules/fallback tests

Cover:
- urgent action classification
- shipment detection
- event/travel detection
- promo/newsletter detection
- parse-failure fallback output

Maps to:
- `tests/test_rules.py`

#### Task T3: Ollama client and validation tests

Cover:
- timeout handling
- JSON parse failure
- schema validation failure
- confidence/score clamping

Maps to:
- `tests/test_ollama_client.py`
- `tests/test_orchestrator.py`

#### Task T4: Orchestrator tests

Cover:
- happy path end-to-end run
- one batch timeout -> partial/fallback
- all batches fail -> failed or cached result path
- duplicate run trigger behavior
- board totals consistency

Maps to:
- `tests/test_orchestrator.py`

#### Task T5: API tests

Cover:
- run endpoint
- status endpoint
- result endpoint
- invalid run id
- invalid action
- structured error responses

Maps to:
- `tests/test_api.py`

#### Task T6: Action tests

Cover:
- archive/pin/snooze idempotency
- supported `mailto` unsubscribe
- supported `http` unsubscribe
- unsupported header
- transport failure path

Maps to:
- `tests/test_actions.py`

### UI and integration tests

#### Task T7: Chainlit integration flow

Cover:
- start triage
- polling progression
- terminal result render
- trace expansion
- local action state update
- fallback badge path

Maps to:
- `tests/test_chainlit_flow.py`

#### Task T8: Critical demo E2E flow

Cover:
- user starts demo
- board populates
- one message gets pinned or snoozed
- one unsubscribe succeeds or shows explicit unsupported state
- no duplicate run from double-click

Maps to:
- E2E harness of choice if added, otherwise a high-value integration test

## Critical Path

If you want the fastest path to a credible demo, build in this order:

1. Task 0.1
2. Task 1.1
3. Task 1.2
4. Task 1.3
5. Task 1.4
6. Task 2.1
7. Task 2.2
8. Task 3.1
9. Task 3.2
10. Task 3.3
11. Task 4.1
12. Task 4.3
13. Task 4.4
14. Task 5.1
15. Task 5.2
16. Task 5.3
17. Task 7.1
18. Task 7.2
19. Task 7.3
20. Task 6.1
21. Task 6.2
22. Task 6.3
23. Task 7.4
24. Task 2.3
25. Task 8.2
26. Task 8.1
27. Task 8.3

## Suggested PR Slices

### PR 1: Skeleton + models + fixture loader

Includes:
- Milestone 0
- Tasks 1.1 to 1.3
- tests T1

### PR 2: Dataset + rules + fallback

Includes:
- Task 1.4
- Milestone 2
- tests T2

### PR 3: Ollama client + orchestrator + run store

Includes:
- Milestone 3
- Milestone 4
- tests T3 and T4

### PR 4: FastAPI endpoints

Includes:
- Milestone 5
- tests T5

### PR 5: Actions + unsubscribe

Includes:
- Milestone 6
- tests T6

### PR 6: Chainlit UI

Includes:
- Milestone 7
- tests T7

### PR 7: Hardening + rehearsal

Includes:
- Milestone 8
- test T8

## Risks To Watch During Execution

- Dataset quality risk: weak fixture variety will make the model seem worse than it is.
- Prompt drift risk: if each stage prompt evolves independently without contract tests, outputs will become brittle.
- UI overwork risk: trace presentation can easily consume more time than triage correctness.
- Demo honesty risk: cached fallback must always be labeled so the demo stays defensible.
- Scope drift risk: adding IMAP or feed-style inbox now will delay the demo without improving the proof point.

## Definition of Done For The Branch

The branch is done when all of the following are true:
- seeded fixture triage runs locally end to end
- board shows `Do Now`, `Track`, and `Ignore`
- every card includes confidence, score, and rationale
- trace panel shows named agent stages
- at least one local action updates state live
- unsubscribe executes for supported targets and reports unsupported ones clearly
- model timeout still yields a usable demo state
- automated tests cover backend contracts, fallback behavior, actions, and at least one integration flow
- a short rehearsal checklist exists and can be followed successfully
