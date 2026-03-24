# BriefBox Engineering Design

Reviewed on 2026-03-24 via `/plan-eng-review`
Inputs:
- `docs/briefbox-design-20260323.md`
- `docs/ai-assistant-prd.md`

Status: PROPOSED
Branch: `work`

## Goal

Turn the approved demo concept into an implementation-ready design that is:
- reliable in a live demo
- honest about what is demo-only versus product-grade
- small enough to ship without accidental architecture sprawl
- complete enough to include failure handling and full test scope up front

## Step 0: Scope Challenge

### What already exists

- The PRD already defines the long-term product shape: local processing, inbox triage, summaries, quick actions, pin tracking, and deterministic fallbacks.
- The branch design doc already makes the key demo decisions: seeded dataset, FastAPI backend, Chainlit frontend, Ollama + Qwen, visible multi-agent trace, and real unsubscribe.
- There is no implementation yet, so there is no legacy code to preserve. The main reuse opportunity is conceptual reuse:
  - Reuse the PRD's local-first and fallback principles.
  - Reuse the branch design doc's 3-lane board and agent-trace storytelling.
  - Do not prematurely implement the full PRD inbox/feed model for this demo.

### Minimum change set that achieves the goal

The minimum complete demo is:
1. Seeded mailbox fixture loader
2. Deterministic preprocessing and normalization
3. Single orchestration run per demo session
4. LLM-backed classification/extraction pipeline
5. 3-lane board output with rationale and confidence
6. Agent trace UI
7. One stateful local action flow plus real `List-Unsubscribe`
8. Timeout fallback to cached deterministic result

Anything beyond that is scope creep for this branch.

### Complexity check

The current concept can stay under the smell threshold if implemented as:
- 1 FastAPI app module
- 1 orchestration service
- 1 model client
- 1 rules/fallback module
- 1 fixture loader
- 1 unsubscribe executor
- 1 Chainlit app
- tests

That is still several files, but only 2 true service boundaries are necessary:
- `TriageOrchestrator`
- `OllamaClient`

Recommendation: keep explicit "agents" as prompt stages inside one orchestrator, not separate processes, queues, or microservices.

### Search check

Search unavailable under the current review flow, so this design uses in-distribution engineering judgment only.

### TODOS cross-reference

No `TODOS.md` exists. This design identifies deferred work explicitly in `Not in Scope` so it can later be promoted into TODOs if you want.

### Completeness check

The original design is mostly complete for a demo, but two shortcuts would become demo risks:
- no explicit fallback result contract on model timeout
- no clear persistence boundary for mutable actions after triage

Those are small additions with high payoff and should be included now.

### Distribution check

This branch does not introduce a shipped artifact yet. It introduces a runnable demo app only.
Distribution is intentionally deferred, but local startup scripts and a one-command demo run path should still be part of implementation.

## Opinionated Scope Decision

Keep the demo scope narrow:
- seeded inbox only
- single-user only
- local-only runtime
- no IMAP
- no background polling
- no chat-based configuration
- no learning loop
- no digest generation

This is the right tradeoff. The PRD is a product vision; this branch should build a credible vertical slice.

## Proposed Detailed Design

### System shape

```text
                   +-------------------+
                   |  Seeded Dataset   |
                   |  50-60 emails     |
                   +---------+---------+
                             |
                             v
                   +-------------------+
                   | Fixture Loader    |
                   | normalize email   |
                   +---------+---------+
                             |
                             v
                   +-------------------+
                   | TriageOrchestrator|
                   | run_id lifecycle  |
                   +----+----+----+----+
                        |    |    |
                        |    |    |
                        |    |    +------------------+
                        |    |                       |
                        v    v                       v
              +-------------+----+        +-------------------+
              | Rules/Fallback   |        | OllamaClient      |
              | deterministic    |        | Qwen structured   |
              | heuristics       |        | JSON inference    |
              +-------------+----+        +---------+---------+
                            |                       |
                            +-----------+-----------+
                                        |
                                        v
                              +---------------------+
                              | Run Store           |
                              | status/result/trace |
                              +----------+----------+
                                         |
                  +----------------------+----------------------+
                  |                                             |
                  v                                             v
       +-----------------------+                    +-----------------------+
       | FastAPI REST API      |                    | Unsubscribe Executor  |
       | run/status/result     |                    | mailto/http handler   |
       +-----------+-----------+                    +-----------+-----------+
                   |                                            |
                   +----------------------+---------------------+
                                          |
                                          v
                               +----------------------+
                               | Chainlit UI          |
                               | board + trace panel  |
                               +----------------------+
```

### Core engineering decision

Do not build four autonomous agents.

Build one orchestrator that executes four explicit stages:
1. classify
2. summarize
3. prioritize
4. extract_actions

Each stage can still be narrated as an "agent" in the UI and trace payload. This preserves the storytelling value without introducing coordination bugs, queueing, or state duplication.

### Processing model

Use batch execution with per-message outputs.

```text
load fixture
  -> normalize messages
  -> split into batches of N
  -> run stage pipeline per batch
  -> validate structured outputs
  -> merge with deterministic fallback fields
  -> persist per-message trace
  -> compute final board lanes
  -> expose result snapshot
```

Suggested defaults:
- batch size: `8`
- maximum model timeout per batch: `10s`
- maximum full run budget: `60s`
- if a batch fails: mark fallback_used and continue

### State model

Use an in-memory run store plus a local JSON snapshot file for demo resilience.

Reason:
- in-memory keeps implementation simple
- snapshot file lets you recover from server restart and precompute fallback results
- full database is unnecessary for this branch

```text
Run
├── run_id
├── status: queued | running | completed | failed | partial
├── created_at
├── started_at
├── completed_at
├── source_fixture_id
├── total_messages
├── processed_messages
├── fallback_used: bool
├── board
├── trace
└── errors[]

MessageResult
├── message_id
├── sender
├── subject
├── summary
├── entities { deadlines[], events[], shipments[] }
├── category
├── final_lane
├── confidence
├── priority_score
├── score_rationale
├── action
├── action_deadline
├── unsubscribe
└── trace_steps[]
```

### API design

#### `POST /triage/run`

Starts a run against a named fixture.

Request:

```json
{
  "fixture_id": "monday-chaos-v1",
  "use_cached_on_timeout": true
}
```

Response:

```json
{
  "run_id": "run_123",
  "status": "queued"
}
```

#### `GET /triage/status/{run_id}`

Returns coarse progress for polling.

```json
{
  "run_id": "run_123",
  "status": "running",
  "processed_messages": 24,
  "total_messages": 54,
  "current_stage": "prioritize",
  "fallback_used": false,
  "errors": []
}
```

#### `GET /triage/result/{run_id}`

Returns final board plus trace snapshot.

```json
{
  "run_id": "run_123",
  "status": "completed",
  "fallback_used": false,
  "board": {
    "do_now": [],
    "track": [],
    "ignore": []
  },
  "trace": [],
  "summary_stats": {
    "messages": 54,
    "lanes": {
      "do_now": 7,
      "track": 16,
      "ignore": 31
    }
  }
}
```

#### `POST /actions/message`

Use one general action endpoint for local state mutations.

Request:

```json
{
  "run_id": "run_123",
  "message_id": "msg_018",
  "action": "pin"
}
```

Supported actions:
- `archive`
- `pin`
- `snooze`

Rationale: keep the REST surface smaller. Do not create a separate endpoint for each local UI action.

#### `POST /actions/unsubscribe`

Execute a real unsubscribe only when the message has a supported `List-Unsubscribe` target.

Response contract must include:
- `performed`: boolean
- `method`: `mailto` | `http` | `none`
- `status`: `succeeded` | `failed` | `unsupported`
- `user_message`: human-readable result

### UI design

Chainlit should show three coordinated regions:

```text
+---------------------------------------------------------------+
| Header: BriefBox | fixture selector | Triage Inbox button     |
+---------------------------+-----------------------------------+
| Board                      | Agent Trace                      |
|                            |                                  |
| Do Now     Track  Ignore   | [collapsed by default]           |
| cards      cards  cards    | message -> stages -> outputs     |
|                            | confidence, score, latency       |
+---------------------------+-----------------------------------+
| Details / Action Drawer                                        |
| summary | rationale | deadline | actions | unsubscribe state   |
+---------------------------------------------------------------+
```

UI rules:
- poll `status` every `750ms`
- switch to `result` once run is terminal
- default Agent Trace to collapsed cards
- never block the board on trace expansion
- show fallback badge if any part of the run used deterministic fallback

### Prompt and output contract

All LLM calls must request strict JSON only. Do not parse prose.

Per-message stage output contract:

```json
{
  "category": "action_required",
  "confidence": 0.84,
  "summary": "Vendor needs approval by Wednesday for contract renewal.",
  "entities": {
    "deadlines": ["2026-03-26"],
    "events": [],
    "shipments": []
  },
  "priority_score": 91,
  "score_rationale": "Direct ask with time-bound follow-up from a known contact.",
  "suggested_lane": "do_now",
  "action": "reply_with_approval",
  "unsubscribe_candidate": false
}
```

Validation rules:
- reject missing required keys
- clamp confidence to `0..1`
- clamp priority score to `0..100`
- if parse fails, record error and apply deterministic fallback

### Deterministic fallback

This is mandatory for demo reliability.

Fallback heuristics:
- sender/domain allowlist for known important senders
- keyword rules for shipments, events, invoices, deadlines
- subject/body signals for promotions and newsletters
- low-confidence default to `do_now` only for ambiguous action-like content, not every parsing failure

Important refinement:
The PRD says low confidence should route to Action Required. For this demo, that rule should be narrowed.
Otherwise, noisy parse failures will make the board look worse during the demo.

Recommended demo rule:
- low confidence + explicit action signal -> `Do Now`
- low confidence + tracking signal -> `Track`
- low confidence + promo/newsletter signal -> `Ignore`
- total parse failure -> fallback classifier result plus `needs_review=true`

### Unsubscribe design

Support only these paths:
1. `mailto:` unsubscribe target
2. `http(s):` unsubscribe target

Do not attempt:
- login-required unsubscribe pages
- complex form submissions
- JS-heavy confirmation flows

Mark unsupported flows clearly in UI as "Manual unsubscribe required".

### File layout

Proposed minimal implementation layout:

```text
briefbox/
├── app/
│   ├── api.py
│   ├── models.py
│   ├── orchestrator.py
│   ├── ollama_client.py
│   ├── rules.py
│   ├── fixtures.py
│   ├── actions.py
│   └── store.py
├── chainlit_app.py
├── data/
│   ├── fixtures/monday-chaos-v1.json
│   └── cached-results/monday-chaos-v1.json
└── tests/
    ├── test_api.py
    ├── test_orchestrator.py
    ├── test_rules.py
    ├── test_actions.py
    └── test_chainlit_flow.py
```

Files that should contain inline ASCII diagrams:
- `app/orchestrator.py`
- `app/store.py`
- `app/actions.py`
- `tests/test_chainlit_flow.py`

## Architecture Review

### Issue 1: Four-agent framing should stay logical, not infrastructural

Finding:
The design doc presents four explicit agents. If implemented literally as separate agent runtimes, the branch will over-spend complexity on orchestration rather than demo quality.

Recommendation:
Keep four named stages but one orchestrator and one model client.

Tradeoff:
- Pro: lower blast radius, easier testing, easier timeout handling
- Con: less "pure" multi-agent architecture story

Assessment:
This is the right boring-by-default choice.

### Issue 2: Mutable actions need a state owner

Finding:
The original design includes archive/snooze/pin/unsubscribe but does not define where local post-triage state lives.

Recommendation:
Use the run store as the single owner of mutable action state for the demo.

Tradeoff:
- Pro: one source of truth for UI refresh after actions
- Con: state resets unless snapshot persistence is enabled

### Issue 3: Result contract must separate board data from trace data

Finding:
If board cards and verbose trace live in one loosely shaped blob, UI rendering and tests will become brittle.

Recommendation:
Expose `board`, `trace`, and `summary_stats` as separate top-level result sections.

## Code Quality Review

### Main recommendations

- Keep prompt templates close to the orchestrator instead of inventing a separate prompt framework.
- Use explicit Pydantic models for every API payload and model response.
- Keep lane names canonical at one boundary only:
  - internal enum: `DO_NOW`, `TRACK`, `IGNORE`
  - external API strings: `do_now`, `track`, `ignore`
- Do not duplicate classification logic between rules and LLM post-processing. Rules should be fallback-only or override-only.

### Edge cases to handle explicitly

- duplicate `message_id` in fixture input
- malformed `List-Unsubscribe` headers
- model returns syntactically valid JSON with semantically invalid fields
- partial batch completion followed by timeout
- user triggers triage twice quickly
- user clicks unsubscribe twice
- stale UI polling after run completion

## Test Review

No code exists yet, so all paths are currently gaps by definition. The design below is the required coverage target.

```text
CODE PATH COVERAGE
===========================
[+] app/fixtures.py
    │
    ├── load_fixture()
    │   ├── [GAP] valid fixture load
    │   ├── [GAP] missing fixture id
    │   └── [GAP] duplicate message ids rejected
    │
[+] app/orchestrator.py
    │
    ├── run_triage()
    │   ├── [GAP] happy path, all batches succeed
    │   ├── [GAP] one batch times out -> deterministic fallback
    │   ├── [GAP] model returns invalid schema -> fallback + trace error
    │   ├── [GAP] run started twice -> second request rejected or deduped
    │   └── [GAP] partial completion -> status=partial with usable board
    │
    ├── classify_stage()
    │   ├── [GAP] valid structured output
    │   └── [GAP] ambiguous message routes through fallback heuristics
    │
    └── merge_results()
        ├── [GAP] confidence/score clamped to valid ranges
        └── [GAP] board lane totals remain consistent
    │
[+] app/actions.py
    │
    ├── apply_message_action()
    │   ├── [GAP] archive happy path
    │   ├── [GAP] pin happy path
    │   ├── [GAP] snooze happy path
    │   └── [GAP] duplicate action request is idempotent
    │
    └── unsubscribe()
        ├── [GAP] mailto unsubscribe succeeds
        ├── [GAP] http unsubscribe succeeds
        ├── [GAP] unsupported header returns clear message
        └── [GAP] transport failure returns recoverable error

USER FLOW COVERAGE
===========================
[+] Demo run flow
    │
    ├── [GAP] [->E2E] user starts triage and sees board populate
    ├── [GAP] [->E2E] trace panel expands for one message
    ├── [GAP] [->E2E] timeout path shows fallback badge, not blank UI
    └── [GAP] [->E2E] double-click on Triage Inbox does not create duplicate runs

[+] Board interaction flow
    │
    ├── [GAP] pin/archive/snooze updates visible state
    ├── [GAP] unsupported unsubscribe shows manual message
    └── [GAP] successful unsubscribe updates card state live

[+] Error states
    │
    ├── [GAP] run fails before first batch -> clear error banner
    ├── [GAP] partial result still renders usable board
    └── [GAP] polling stale run id returns non-crashing UI state

─────────────────────────────────
COVERAGE: 0/24 paths tested (0%)
  Code paths: 0/16
  User flows: 0/8
QUALITY:  ★★★: 0  ★★: 0  ★: 0
GAPS: 24 paths need tests (4 need E2E)
─────────────────────────────────
```

### Required test plan

- `tests/test_fixtures.py`
  - fixture exists, missing fixture, duplicate ids, schema validation
- `tests/test_rules.py`
  - shipment/event/deadline/promotion heuristics
- `tests/test_orchestrator.py`
  - success, timeout fallback, invalid JSON fallback, partial completion, dedupe
- `tests/test_api.py`
  - run, status, result, bad run id, invalid action, unsubscribe result contract
- `tests/test_actions.py`
  - idempotent local actions, supported/unsupported unsubscribe, transport failure
- `tests/test_chainlit_flow.py`
  - run flow, trace expand, fallback badge, action refresh

## Failure Modes

| Codepath | Production failure | Test needed | Error handling | User experience | Gap |
|---|---|---:|---:|---|---|
| Fixture load | bad fixture shape | yes | yes | clear startup error | no |
| Model batch inference | timeout | yes | yes | fallback badge + partial trace | no |
| Model parsing | invalid JSON/schema | yes | yes | degraded but usable result | no |
| Merge results | impossible score values | yes | yes | invisible after clamping | no |
| Local actions | duplicate clicks | yes | yes | idempotent success | no |
| Unsubscribe http | 500/network error | yes | yes | recoverable inline error | no |
| Unsubscribe unsupported | complex page/manual flow | yes | yes | explicit manual step | no |
| UI polling | stale run id | yes | yes | non-fatal empty/error state | no |

Critical gap rule:
If implementation ships without fallback badge + partial result rendering, a model failure would look like a blank board. That would be a critical gap.

## Performance Review

### Main risks

1. Serial per-message inference will miss the 60-90 second demo budget.
2. Returning full verbose trace for 50+ messages on every poll will waste time and UI bandwidth.
3. Re-running inference after every local action would be needless and fragile.

### Recommendations

- Batch inference; do not call the model once per message.
- Keep `GET /triage/status` light and trace-free.
- Return full trace only from `GET /triage/result/{run_id}`.
- Mutate local action state without re-triaging the full mailbox.
- Pre-warm Ollama before demo start.

## NOT in Scope

- IMAP ingestion: deferred because seeded fixtures are the correct demo reliability tradeoff.
- encrypted local storage: product requirement, but unnecessary for a seeded local demo branch with no real user mailbox.
- background polling: not needed for a one-shot demo run.
- feed-style inbox UI: deferred in favor of 3-lane board, which better serves the demo story.
- user-authored rules UI: useful later, but not required to prove core triage value.
- learning/adaptation loop: high complexity, low demo value.
- digests: outside the vertical slice.
- Telegram integration: unrelated to the core demo.
- plugin system: premature.
- packaged distribution: defer until there is runnable software worth packaging.

## Recommended Implementation Sequence

1. Build fixture schema and one gold fixture.
2. Build deterministic rules and fallback classifier first.
3. Build Ollama client with strict JSON validation.
4. Build orchestrator and run store.
5. Expose FastAPI run/status/result endpoints.
6. Add local action endpoint and unsubscribe executor.
7. Build Chainlit board and trace UI.
8. Add cached-result fallback and prewarm command.
9. Write tests alongside each step.

## Review Verdict

The approved design is directionally right, but it needs tighter implementation boundaries.

Most important adjustments:
1. One orchestrator, not real multi-agent infrastructure
2. Mandatory deterministic fallback with explicit UI signaling
3. One local action endpoint plus one unsubscribe endpoint
4. Snapshot-backed run store for demo resilience
5. Full test plan defined before implementation starts

If you want the most reliable impressive demo, build exactly this vertical slice and resist the PRD temptation to expand into a real email client on this branch.
