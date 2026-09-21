# ADR 0004 — PII and data governance

- **Status:** Accepted
- **Date:** 2026-02
- **Deciders:** both team members

## Context

A complaint carries more personal data than it looks like it does:

- `reporter_contact` — a phone number or email. Unambiguously PII.
- `location` — a street address, often the reporter's own home.
- `text` — free-form, so it contains whatever the citizen typed: names,
  neighbours' names, health details ("my mother is on oxygen and the power has
  been out for six hours"), and grievances against identifiable people.

`text` and `location` are sent to a third-party language model in the default
production configuration. That is a data export to another jurisdiction, and it
happens on every complaint. Treating it as an implementation detail would be the
single most serious governance failure available to this project.

## Decision

**1. Minimise what leaves the deployment.** `reporter_contact` is *never* sent to
any triage provider. The provider interface takes `text` and `location` only:

```python
async def triage(self, text: str, location: str) -> TriageResult: ...
```

This is enforced by the type signature rather than by discipline — there is no
parameter to pass a phone number through. The classifier does not need it, so it
does not get it.

**2. `location` is sent, deliberately.** It carries real classification signal
("Sector G-9 main road" distinguishes a road complaint from a household one) and
removing it measurably degrades categories. We send it and document that we do,
rather than pretending the system is more private than it is.

**3. An offline path is first-class, not a demo.** `TRIAGE_PROVIDER=ollama` runs
a model inside the deployment with no egress — the `ollama` container is attached
only to the `internal` network, which is `internal: true`. Any deployment that
cannot accept third-party processing has a same-interface alternative that
requires no code change. `TRIAGE_PROVIDER=rules` sends nothing anywhere at all.

**4. Credentials never enter the repository, the image, or a log.**
`llm_api_key` is a Pydantic `SecretStr` (`backend/app/config.py:39`) defaulting
to `None`, so an unconfigured environment degrades to rules rather than
authenticating with a placeholder. The log formatter redacts it. Kubernetes
manifests carry placeholder Secrets only, and `scripts/check_submission.py`
base64-decodes every committed Secret value and fails the build if one decodes to
something credential-shaped.

**5. The AI summary is treated as untrusted output.** `ai_summary` is capped at
140 characters by schema validation, is never interpolated into SQL, and is
rendered as text by React, which escapes it. A model that emits a `<script>` tag
produces a visible string, not an execution.

**6. Retention is named, not implemented.** Complaints are kept indefinitely,
because a municipality needs the history. The triage cache holds
`sha256(text + location)` as the key and the classification as the value — the
complaint text itself is not stored in Redis — and expires in 24 hours. Logs
carry complaint *ids*, never complaint text or contact details.

## Consequences

**Good**

- The most sensitive field cannot reach a third party, by construction.
- Two configurations (`rules`, `ollama`) involve no external processing at all.
- What is exported is stated precisely, so the trade-off is reviewable rather
  than hidden.
- Redis holding hashes rather than text means a compromised cache yields
  classifications, not complaints.

**Bad, and accepted**

- Sending `location` means sending an address that is frequently the reporter's
  home. This is a real privacy cost, accepted for classification quality, and it
  is the decision most likely to be challenged. If a deployment cannot accept it,
  `ollama` exists.
- Indefinite retention is a policy decision we have deferred rather than made.
  A real deployment needs a retention period, a deletion path, and a
  subject-access process. None exists here.
- We have no audit log of who viewed or changed a complaint. The operator
  dashboard has no authentication at all — out of scope for this assignment, and
  a genuine gap that must be named rather than glossed. Any real municipal
  deployment needs authn, authz and an audit trail before it sees one real
  complaint.
- The provider's own retention is outside our control. We rely on their terms;
  we do not verify them.

## Alternatives considered

**Redact PII from `text` before sending it.** Attractive and rejected as
currently unachievable. Reliable PII detection in Urdu-influenced English is
harder than the classification task itself, and a redactor that is 90% effective
produces false confidence — the 10% it misses now leaves the deployment with
everyone believing it cannot. We chose an honest export over an unreliable
filter, and made the no-export option genuinely usable instead.

**Send nothing, use `rules` only.** Perfect privacy, materially worse
classification, and it makes the entire provider abstraction pointless. Rejected,
but it is the default in `.env.example` precisely so nobody exports data by
accident on first run.

**Hash `location` before sending.** Destroys the signal it was sent for. A hash
is not a location to a classifier.

**Encrypt `reporter_contact` at rest.** Worth doing in a real deployment and not
done here: it requires key management that would be theatre at this scale. Named
as a gap rather than claimed as a feature.
