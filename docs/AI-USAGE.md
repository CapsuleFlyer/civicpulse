# AI usage

Required disclosure. Written to be useful rather than defensive: what was
generated, what was changed afterwards, and what we would not have caught
without reading it line by line.

---

## Tools

| Tool | Used for |
| --- | --- |
| **Claude (Anthropic)** | The initial scaffold of most of this repository: file layout, FastAPI wiring, Compose and Kubernetes manifests, workflow YAML, first drafts of the docs. |
| **Ollama (`llama3.2:1b`), Groq (`llama-3.1-8b-instant`)** | Runtime components of the product, not authoring tools. Documented in [TRIAGE.md](TRIAGE.md). |

---

## What was generated, and what happened to it afterwards

### Backend

**Generated:** the four-layer package layout, FastAPI app factory, Pydantic v2
schemas, SQLAlchemy 2.0 async models, the repository class, Alembic migration,
middleware, and the first draft of every route.

**Changed by hand, and why:**

- **The state machine.** The generated version was a chain of `if`s inside the
  route handler. It was replaced with the `TRANSITIONS` table in
  `backend/app/domain.py` and moved out of the HTTP layer entirely. A table can
  be enumerated in a test and rendered to an operator; a chain of `if`s can be
  neither, and it had already grown an unreachable branch.
- **Cache invalidation.** The first draft cached `/api/stats` with a 30-second
  TTL and nothing else, which is what the spec's wording most obviously suggests.
  That means a citizen submits a complaint and does not see it in the aggregates
  for up to 30 seconds. `StatsService` now invalidates on every write *and* keeps
  the TTL, for the reasons in the README. This was our decision, not a
  suggestion.
- **The rate limiter.** Generated as a Lua script for atomicity — correct, and
  untestable against `fakeredis`, which does not evaluate Lua. Rewritten as a
  pipelined `INCR` + `TTL`. That is a real trade-off (a pipeline is not atomic,
  so a race at the window boundary can admit one extra request) and it is
  documented in a comment at the site rather than hidden. We took testability
  over a one-request edge case; the counter exists to protect a quota, not to be
  a billing system.
- **Retry classification.** The draft retried every exception. It now retries
  only timeouts, 429s and 5xx, because retrying a 400 spends quota to reach the
  same failure.
- **`SecretStr`.** The generated config held the API key as a plain `str`, which
  would print in any exception traceback that included `Settings`. Changed, along
  with the log formatter's redaction.
- **Graceful shutdown.** Not generated at all; we added the SIGTERM handler in
  `backend/app/main.py:35–53` after the first rollout test dropped in-flight
  requests. It chains the previous handler rather than replacing it, so uvicorn's
  own shutdown still runs.

### Frontend

**Generated:** the Vite + TypeScript setup, routing, component structure, the
typed API client, and the test harness.

**Changed by hand:**

- **Runtime configuration.** The generated client read `import.meta.env.VITE_API_URL`.
  Vite inlines that at build time, which makes the image environment-specific and
  quietly destroys build-once-deploy-many for half the system. Replaced with the
  `config.js` written by `docker-entrypoint.sh`, plus an ESLint rule that makes
  `import.meta.env` a build error so it cannot come back. See
  [ADR 0002](adr/0002-frontend-runtime-config.md).
- **The 409 handling.** The generated `StatusActions` component disabled buttons
  for transitions it believed were illegal — which requires the frontend to hold
  a copy of the transition table, and therefore guarantees two sources of truth
  and one that rots. It now offers every status and renders the server's 409
  message verbatim. This was the single most contested design decision in the
  project and it is deliberate.
- **The visual design.** The generated CSS was the default LLM house style:
  cream background, terracotta accent, oversized rounded cards, a lot of
  whitespace. Replaced with a dense municipal-register look — paper `#eef1ec`,
  ink `#16241f`, a brick signal colour for high priority, civic blue for links —
  because this is a tool an operator stares at for eight hours, not a landing
  page. Information density beat whitespace everywhere the two conflicted.
- **Loading states.** The drafts used skeleton shimmer. Triage takes an
  unpredictable 0–10 seconds, so a shimmer that implies "nearly there" is a lie
  after second four. Replaced with explicit text about what is happening.

### Infrastructure

**Generated:** Compose files, all Kubernetes manifests, all three workflows.

**Changed by hand:**

- **Backend network membership.** The generated `compose.yaml` attached the
  backend to `internal` only — which is the natural reading of "the data services
  live on the internal network" and is wrong, because `internal: true` means no
  egress and the hosted LLM call then cannot resolve DNS. This cost us over an
  hour and is question 8 of the engineering notes. It is the best example in this
  project of why generated infrastructure must be *run*, not reviewed.
- **NetworkPolicy.** Not generated. Kubernetes pod networking is flat and
  permissive by default, so the Compose segmentation does not carry over; without
  `k8s/base/networkpolicy.yaml` the cluster deployment has none of the isolation
  the Compose one demonstrates.
- **HPA behaviour.** The generated HPA had no `behavior` block, which means
  default stabilisation in both directions — slow to scale up when users are
  waiting. Tuned to `scaleUp.stabilizationWindowSeconds: 0` and
  `scaleDown: 300`.
- **Probe wiring.** The draft pointed `livenessProbe` at `/ready`. That turns a
  slow database into a cluster-wide restart loop: every pod fails liveness, every
  pod restarts, none of them fix the database. `scripts/check_submission.py` now
  fails the build if that pattern reappears.
- **Workflow permissions.** The generated workflows had no top-level
  `permissions:` block, defaulting to a broad token. Added least-privilege blocks
  to all three.

### Documentation

First drafts of the README, this runbook and the ADRs were generated. Every
number, file path and line reference in them was then checked against the
repository, and the generic passages were cut. Where a claim could not be
verified — measured latency, HPA lag, cache hit rate — it is marked `MEASURE:`
rather than invented, because a plausible fabricated number is the most damaging
thing an AI tool produces in a document like this.

`scripts/check_submission.py`, `scripts/integration_smoke.py` and
`scripts/check_api_contract.py` were written to make the claims in these
documents mechanically checkable, so that a future edit that makes a doc untrue
also turns CI red.

---

## Where AI assistance was least useful

Worth recording, because it is where the time actually went.

1. **Anything whose correctness depends on running it.** The `internal: true`
   mistake reads perfectly. So did the `livenessProbe` → `/ready` wiring. Both
   are subtly wrong in a way that only shows up under `docker compose up` and a
   rollout respectively. Generated infrastructure is a hypothesis.
2. **Trade-offs with no single right answer.** TTL versus invalidation, atomic
   Lua versus testable pipeline, disabling buttons versus surfacing the 409 —
   generated code picks one and presents it as settled. The decision, and the
   reason, has to be ours; that is what the ADRs are for.
3. **Version drift.** Suggestions mixed Pydantic v1 and v2 idioms, and
   SQLAlchemy 1.x `Query` with 2.0 `select()`. Everything is pinned in
   `requirements.txt` and `mypy` is clean, which is how this got caught rather
   than by reading.
4. **Knowing what to leave out.** The instinct is to add. The `egress` proxy
   network, the separate triage worker, a Grafana container — all plausible, all
   rejected in ADRs, and the rejection is worth more marks than the addition
   would have been.

---

## Statement

AI tooling wrote a large share of the first draft of this repository. Every
design decision in it — layer boundaries, the cache strategy, the state machine
representation, network topology, probe wiring, what to reject — was made,
argued and verified by us. Every test result quoted in the README was produced by
running the suite: 60 backend tests at 86.85% coverage, 15 frontend tests, clean
`ruff`, `mypy`, `eslint` and `tsc`, green `vite build`. Every number not produced
that way is marked `MEASURE:` and is not claimed.

We can explain, extend, debug and defend any file in this repository, which is
the standard that actually matters at the viva.
