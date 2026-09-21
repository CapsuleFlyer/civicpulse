# ADR 0001 — Triage behind a provider interface

- **Status:** Accepted
- **Date:** 2026-02
- **Deciders:** both team members
- **Supersedes:** none

## Context

CivicPulse needs free-text complaints classified into a category, a priority and
a short summary. The obvious implementation is to call a hosted language model
from the route handler that accepts the complaint.

Three facts make that obvious implementation wrong:

1. **The reader will change.** Today the sensible default is a keyword table
   (no key, no quota, works offline). Tomorrow it is a hosted model. In a year it
   plausibly becomes a fine-tuned classifier or a local model that got good
   enough. The system will outlive at least two of these.
2. **The reader fails in ways the citizen must never see.** Free tiers rate-limit.
   Providers have outages. Models return prose where JSON was requested. A citizen
   reporting a burst main cannot be shown a 500 because a third party had a bad
   afternoon.
3. **The reader is non-deterministic**, and a test suite that asserts against a
   live model is a test suite that goes red for no reason — which trains a team
   to ignore red, which is worse than having no CI.

## Decision

Triage is defined by a `Protocol` with a single method, and every implementation
satisfies it:

```python
class TriageProvider(Protocol):
    name: str
    async def triage(self, text: str, location: str) -> TriageResult: ...
```

Four implementations — `RuleBasedTriage`, `LLMTriage`, `OllamaTriage`,
`SimulatedTriage` — are selected at startup by the `TRIAGE_PROVIDER` environment
variable in `backend/app/providers/triage/factory.py` and injected once in
`backend/app/deps.py`.

All policy lives *above* the interface, in `backend/app/services/triage.py`, and
is therefore identical for every provider: 10-second timeout, one jittered retry
on timeout/429/5xx only, re-validation into `TriageResult`, content-hash cache,
and fallback to `RuleBasedTriage` recording `triaged_by = "rules:fallback"`.

`RuleBasedTriage` is both a first-class choice and the universal fallback. It is
pure Python and cannot fail, which is what lets `POST /api/complaints` promise
`201`.

## Consequences

**Good**

- Switching providers is a config change, not a deploy: `kubectl set env
  deployment/backend TRIAGE_PROVIDER=rules` is a valid incident response.
- CI is deterministic by construction — `SimulatedTriage` is seeded and offline,
  and failure modes are injected as providers rather than mocked at the HTTP layer.
- Failure handling is written once. A fifth provider inherits timeout, retry,
  validation, caching and fallback for free.
- The offline path (`ollama`) is a genuine alternative rather than a demo, which
  matters for any deployment that will not send citizen text to a third party.

**Bad, and accepted**

- Indirection. Following a complaint from route to model crosses four files. For
  a component with one implementation this would be over-engineering; the whole
  premise is that there are four.
- The interface is the narrowest thing all four can do. A provider offering
  token-level confidence or batch classification cannot express it without
  changing the Protocol — and batching in particular is something we want later
  (see TRIAGE.md).
- `triaged_by` leaks the provider into the data model. Deliberate: without it,
  "was this classified by the model or by the fallback?" is unanswerable after
  the fact, and that question turned out to be the most important one we asked
  during the incident in question 8 of the engineering notes.

## Alternatives considered

**Call the model directly from the route handler.** Fewer files, and the first
version was written this way. Rejected on the first provider outage: the failure
handling has to exist somewhere, and putting it in the route means writing it
again for every provider and mixing HTTP concerns with retry policy.

**A plugin system with dynamic loading.** Rejected. Four implementations in one
repository do not need discovery; a dict in a factory is legible and typed, and
`mypy` checks it.

**LangChain or a similar framework.** It provides the abstraction we want plus
several hundred we do not, has its own release cadence, and would make the
timeout and retry policy — the actual subject of this assignment — someone else's
configuration rather than our code.

**An abstract base class instead of a Protocol.** `Protocol` gives structural
typing: a test double satisfies it without importing anything from us, so
`backend/tests/conftest.py` defines `AlwaysRaisingProvider` as a plain class with
one method. An ABC would force test doubles to inherit from production code.
