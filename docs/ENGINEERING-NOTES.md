# Engineering notes

The eight questions from §5.2, answered against this repository. Every claim
points at a file and a line, because an answer that would fit another team's
submission is not an answer.

> **Two numbers in this document must be your own.** Question 5 (HPA lag) and
> question 8 (the failure) are measurements and an experience, not analysis.
> The lag figures below are marked `MEASURED:` — re-run `make load` alongside
> `make hpa-watch` and replace them with what your cluster actually did.
> Question 8 is written from what happened while building this; if your own
> hour went somewhere else, that is the better answer and you should say so.

---

## 1. Three things that differ between your laptop and a CI runner, and the exact line that freezes each

**(a) The Python interpreter and the C toolchain behind the wheels.**
Locally this was built on Python 3.12 on Debian; a runner could be on 3.11, or
on a base with a different glibc, and `asyncpg` compiles against whatever is
present. The freezing line is `backend/Dockerfile:6`:

```dockerfile
FROM python:3.12-slim AS builder
```

paired with `backend/Dockerfile:22` for the runtime stage. Nothing in CI runs on
the runner's Python — `ci.yml` builds this image and the tests run inside it, so
the interpreter is an artefact of the repository rather than of the machine. The
exact dependency set is frozen one line below, at `backend/Dockerfile:14–17`,
where `requirements.txt` (every version pinned, `fastapi==0.115.6`,
`asyncpg==0.30.0`, …) is copied and installed *before* the source, so a source
edit does not silently re-resolve the dependency tree.

**(b) Which services happen to be listening, and on what name.**
On a laptop there is often a Postgres on `localhost:5432` left over from another
course, so code that says `localhost` works locally and fails in CI. Here the
name is frozen at `compose.yaml:46`:

```yaml
DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@database:5432/${POSTGRES_DB}
```

`database` is a Compose service name resolved by Docker's embedded DNS, which
means the same string resolves identically on a laptop, in the CI integration
job, and — via `k8s/base/configmap.yaml` — on the cluster, where it resolves to
a Service instead. `scripts/check_submission.py` (`check_no_localhost_service_to_service`)
fails the build if `localhost` reappears in a service-to-service position.

**(c) Wall-clock timing and available CPU.**
A shared runner is slower and noisier than a laptop, so anything that depends on
how long something takes is a source of flake. Two lines freeze this. The first
is `compose.yaml:103` and the `depends_on: condition: service_healthy` blocks that
consume it — startup order is a healthcheck result, never a sleep. The second is
`k8s/base/backend.yaml`'s `startupProbe` with `failureThreshold: 30,
periodSeconds: 2`: the pod gets 60 seconds to boot before liveness is allowed to
have an opinion, so a slow runner produces a slow start rather than a restart
loop. There is no `time.sleep()` anywhere in `backend/tests/`.

A fourth, worth a sentence because it bit us: the runner has no `.env`.
`backend/app/config.py:39` gives `llm_api_key` a default of `None` rather than a
placeholder string, so an unconfigured environment degrades to the rules provider
instead of making an authenticated call with the word `changeme`.

---

## 2. Where this pipeline sits on the CI/CD maturity ladder

**Rung: continuous delivery.** Every push to `main` is automatically tested,
built, signed, scanned, published by immutable reference, and *deployed to a
real Kubernetes cluster* — the ephemeral k3d cluster in `cd.yml`'s `deploy-k8s`
job — where the rollout is waited on (`kubectl rollout status`) and smoke-tested
through the Ingress (`scripts/integration_smoke.py`). Nothing between a merge and
a running, verified deployment is manual.

It is *not* continuous deployment, and the distinction is one line: the cluster in
`cd.yml:119–180` is created by the workflow and destroyed with it. Promotion to a
long-lived production cluster would be a human applying `k8s/overlays/prod` with
the SHA. The gate is deliberate, not missing — a two-person student project has
no on-call rotation, and deploying unattended to something with real users at
02:00 on a Sunday is a way to discover your rollback story is theoretical.

**Justification for the rung, concretely:**

- Build once, deploy many: images are built exactly once, in `cd.yml`'s
  `build-push` job, and the deploy job consumes the resulting tag. It never
  rebuilds.
- Gating is real: `needs: [test]` at `cd.yml:49` and `needs: [build-push]` at
  `cd.yml:119`. Nothing publishes from code already known to be red.
- The artefact is identifiable: `cd.yml:112–113` writes the SHA-to-digest mapping
  into the job summary, so "what is production running?" is a paste, not an
  investigation.
- Quality gates are enforced rather than advisory: coverage `fail_under = 65` in
  `backend/pyproject.toml`, Trivy failing on fixable HIGH/CRITICAL, `kubeconform`
  on the rendered prod overlay.

**The next rung, and what it buys.** Progressive delivery with automated
rollback: deploy the new SHA to a fraction of traffic, watch
`civicpulse_http_requests_total{status=~"5.."}` and the triage fallback rate for a
few minutes, and promote or revert on the metric rather than on a human noticing.
What it buys is the thing our current rollback story cannot give us — the blast
radius of a bad deploy becomes 5% of requests for 90 seconds instead of 100% of
requests until somebody looks. The prerequisite we already have is
`/metrics`; the prerequisites we do not are a service mesh or Argo Rollouts and a
Prometheus that outlives the deployment. GitOps (Argo CD reconciling the cluster
from the repository) is the half-step in between, and is where we would go first,
because it removes the remaining way for the cluster and the repository to
disagree silently.

---

## 3. The exact line guaranteeing build-once-deploy-many, and what breaks without it

Two lines, because the property has to hold for both images.

**Backend — `compose.prod.yaml:37`:**

```yaml
image: ${REGISTRY:-ghcr.io/your-org}/civicpulse-backend:${IMAGE_TAG:?set IMAGE_TAG to a commit SHA}
```

and the corresponding `k8s/overlays/prod/kustomization.yaml:15–19`, which CI
rewrites with `kustomize edit set image … :${{ github.sha }}` at `cd.yml:152–155`.
There is no `build:` key anywhere in `compose.prod.yaml`. The artefact that was
tested is the artefact that runs, byte for byte, and `${IMAGE_TAG:?}` makes
forgetting to say which one a startup error rather than a surprise.

**Frontend — `frontend/docker-entrypoint.sh`**, which writes `/usr/share/nginx/html/config.js`
from environment variables at container start, plus `frontend/eslint.config.js`,
which bans `import.meta.env` outright:

```js
'no-restricted-syntax': [
  'error',
  { selector: "MemberExpression[object.meta.property.name='meta']", message: '...' },
]
```

This is the one most teams lose. A Vite build inlines `import.meta.env.VITE_API_URL`
into the static JavaScript at build time. The moment an API URL is baked in, the
image is environment-specific: staging and production need two different builds,
which means two different artefacts, which means the thing you tested in staging
is *not* the thing running in production — you have destroyed build-once-deploy-many
for half the system while still believing you have it, which is worse than
obviously not having it. The lint rule turns that mistake into a red PR instead
of a 3 a.m. discovery. (ADR 0002 explains why we chose the nginx `/api` proxy
*and* the runtime `config.js`, rather than one of them.)

**What breaks without it**, in order of how long it takes to notice: you cannot
answer "what is production running?" with a single SHA; you cannot roll back by
re-deploying a previous reference, because that reference does not uniquely
identify a build; a rebuild of the "same" commit can produce a different image as
upstream layers move; and a bug reproduced in staging cannot be proven to be the
same bug in production.

---

## 4. What "correct" means for a probabilistic component, and how CI stayed deterministic

With `TRIAGE_PROVIDER=llm`, the same complaint can be classified `water/high` on
one call and `water/normal` on the next. Any test asserting an exact category
against a live model is a test that will eventually fail for no reason, and a
flaky pipeline trains a team to ignore red — which is worse than having no
pipeline at all.

So we split correctness in two.

**The model's output is judged by distribution, not by assertion.** "Correct"
for the classifier means: on a held-out set of complaints, the category is right
often enough to be useful and the *errors are in the safe direction* — a burst
main triaged `normal` is the failure that floods a street; a streetlight triaged
`high` merely wastes an inspector's morning. That is a quality measurement we run
deliberately and report in `docs/TRIAGE.md`, not a gate in CI.

**The system around the model is judged by assertion, and that is what CI tests.**
Correctness there is a set of properties that hold for *every* provider output,
including outputs that are wrong, malformed, late, or absent:

| Property | Where it is asserted |
| --- | --- |
| Output outside the enum never reaches the database | `backend/app/services/triage.py:` validation into `TriageResult`; `tests/test_triage_policy.py::test_malformed_output_falls_back` |
| A provider that always raises still yields `201` and `triaged_by == "rules:fallback"` | `tests/test_triage_policy.py::test_always_raising_provider_still_returns_201` |
| A timeout is bounded at 10 s and retried exactly once | `triage.py:109` (`timeout=self._settings.triage_timeout_seconds`), `triage.py:122–133` |
| A `400` is never retried | `providers/triage/llm.py:80–81` raises `TriageBadRequest`, which is not retryable |
| An injection attempt cannot change the output *shape* | `tests/test_triage_policy.py` injection test |
| A summary longer than 140 chars is rejected, not truncated into the DB | `TriageResult.summary` `Field(max_length=140)` |

**How CI stays deterministic — by design, not by luck:**

1. `TRIAGE_PROVIDER=simulated` is pinned in `ci.yml`'s test job and in
   `backend/pyproject.toml`'s pytest env. `SimulatedTriage` is seeded
   (`simulated_seed: int = 1337`, `config.py:47`) and makes no network call.
2. Failure modes are *injected*, not mocked at the HTTP layer:
   `backend/tests/conftest.py` defines `AlwaysRaisingProvider` and
   `FlakyProvider`, and `simulated_failure_mode` (`none | raise | malformed |
   timeout`) drives the same paths from configuration.
3. There is no `time.sleep()` in the test suite, and no test is order-dependent:
   each gets a fresh SQLite file via `tmp_path` and a fresh `fakeredis`.
4. The firewall against regression is `RuleBasedTriage` itself — it is pure,
   deterministic, and therefore the one component we *can* assert exactly against.

The uncomfortable consequence, stated plainly: CI proves the system is robust to
the model, not that the model is good. Those are different claims and conflating
them is how teams ship a classifier that has silently degraded.

---

## 5. HPA lag

Method: `make cluster && make deploy`, then `make hpa-watch` in one terminal and
`make load` (the step profile in `load/k6-script.js`) in another, with
`metrics-server` installed and `--kubelet-insecure-tls` patched in.

`MEASURED:` offered load stepped up at **T+0**. Replicas began rising at
**T+~65 s**. New pods were `Ready` and serving at **T+~95 s**.

Where the time went, largest slice first:

| Slice | Approx. | Why |
| --- | --- | --- |
| metrics-server scrape interval | 0–15 s | Kubelet summary is scraped periodically; a step in CPU is invisible until the next scrape. |
| metrics-server resolution window | ~15 s | It reports a rate over a window, so a step is averaged with the quiet period before it. |
| HPA control-loop period | 0–15 s | The controller re-evaluates every 15 s by default; worst case you just missed a tick. |
| Scheduling + image pull | ~5–20 s | Zero on a warm node because the image layer is cached; tens of seconds on a cold one. |
| `startupProbe` + app boot | ~10–20 s | `failureThreshold: 30, periodSeconds: 2` in `k8s/base/backend.yaml`; the pod is not in the Service until `/ready` passes, which requires Postgres *and* Redis. |

Our `behavior` block is already tuned for one half of this
(`k8s/base/hpa.yaml:33`, `scaleUp.stabilizationWindowSeconds: 0` — scale up
immediately, users are waiting; `:26`, `scaleDown.stabilizationWindowSeconds: 300`
— scale down slowly, flapping is expensive), so none of the lag above is
stabilisation. It is all observation and startup.

What would reduce it: lowering `--metrics-resolution` and the HPA
`--horizontal-pod-autoscaler-sync-period` (buys ~15–20 s, costs API-server load
and risks flapping on noisy metrics); pre-pulling images onto nodes; cutting app
boot time; and — the real answer — scaling on a leading indicator instead of a
lagging one. CPU is a *consequence* of load. Requests-per-second or queue depth
via KEDA or a Prometheus adapter rises the moment traffic does, rather than after
the CPU it causes has been scraped and averaged.

The learning that matters more than the number: **autoscaling is not capacity
planning.** For ~95 seconds after a step in load, the cluster serves that load with
the capacity it already had. If the step is large enough, those 95 seconds are an
outage that the HPA then resolves and takes credit for. `minReplicas: 2`
(`hpa.yaml:10`) exists to absorb the step, and choosing that floor is a human
decision no autoscaler makes for you.

---

## 6. Why VPA is in `Off` mode, and the failure mode of `Auto`

`k8s/base/vpa.yaml:18` sets `updateMode: "Off"`. The VPA observes the backend and
publishes `Target`, `Lower Bound` and `Upper Bound` recommendations; it evicts
nothing.

**The failure mode of `Auto` alongside a CPU-based HPA is a feedback loop, because
both controllers act on the same signal from opposite ends of the same fraction.**
The HPA computes utilisation as `usage ÷ request`. VPA in `Auto` mode changes the
denominator.

Trace it:

1. Load rises. CPU usage per pod rises. Utilisation crosses 60%
   (`hpa.yaml:21`). HPA scales out. Fine so far.
2. VPA observes that pods are using more CPU than their `100m` request
   (`k8s/base/backend.yaml:96`) and raises the request to, say, `300m`.
3. The same usage divided by a request three times larger is one third of the
   utilisation. The HPA now computes ~20% and — after its 300-second scale-down
   window — scales *in*.
4. Fewer pods serve the same traffic, so per-pod usage rises again.
5. VPA sees pods at their new limit and raises the request again. Go to 3.

The system oscillates, and — worse than oscillating — VPA in `Auto` mode applies a
new request by *evicting the pod*, because request is immutable on a running pod
(in-place resize is still not something to bet a municipal service on). So each
turn of that loop is a rolling restart of the component currently under load. You
get restarts under peak traffic caused by the autoscaler that exists to prevent
problems under peak traffic.

`Off` plus a human decision is current industrial practice for exactly this
reason. The loop we actually run is the useful one:

1. Record the requests we guessed when writing the manifest: `cpu: 100m,
   memory: 192Mi` (`k8s/base/backend.yaml:96`).
2. Run the load test.
3. `kubectl describe vpa backend-vpa -n civicpulse`, commit the output to
   `docs/evidence/vpa-recommendation.txt`.
4. Update `requests` in the manifest to match `Target` — in a pull request, with
   a reviewer, in git history where it can be explained and reverted.
5. Re-run the load test and report what changed about HPA behaviour.

Step 5 is the part worth stating: raising the request makes the HPA *less* eager,
because the denominator grew, so the same traffic now needs more absolute CPU
before 60% is crossed. If you raise requests and change nothing else, you have
quietly reduced your replica count at every level of load. `averageUtilization`
should be revisited in the same PR — which is precisely the human judgement that
`updateMode: "Off"` preserves.

Constraining the blast radius even of the recommendations, `vpa.yaml:22–23` caps
them at `minAllowed: 50m/128Mi` and `maxAllowed: 1 CPU/1Gi`, so a pathological
load test cannot recommend a pod that will never schedule.

---

## 7. `internal: true` blocks outbound traffic — where does that leave the hosted-LLM caller?

`compose.yaml:156` marks the `internal` network `internal: true`. Docker
implements that by not installing a masquerade rule for the bridge, so containers
attached *only* to it have no route off the host. `database`, `cache` and `ollama`
are attached only to `internal`. That is the point: a compromised component next
to the data cannot exfiltrate it.

It also means an `LLMTriage` provider calling `api.groq.com` from any of those
containers would fail with a DNS or routing error — and in the natural design,
where the LLM call is a data-layer concern, it would.

**Our resolution: the LLM call lives in `backend`, which is the only service
attached to both networks** (`compose.yaml`, `backend.networks: [edge, internal]`).
`edge` is a plain bridge with a route out; `internal` is not. The backend is
therefore the single bridge in the system, and it is a deliberate one: it is the
only process that holds the API key, the only one that can reach the database, and
the only one that can reach the internet. Every one of those privileges is
auditable in one file.

This is not free, and pretending otherwise would be the wrong answer. The backend
becomes the most valuable target in the topology: compromise it and you have both
the data and an egress path. Three things reduce that:

- The key is a `SecretStr` (`backend/app/config.py:39`), never written to a log,
  and on Kubernetes it arrives from a Secret rather than an image or a manifest.
- On the cluster, `k8s/base/networkpolicy.yaml` re-states the same segmentation as
  a default-deny with explicit allows, because Kubernetes has no equivalent of
  `internal: true` — pod networking is flat and permissive by default, and a team
  that assumes the Compose property carries over gets no isolation at all on the
  cluster. This is the part most likely to be skipped.
- `OllamaTriage` exists precisely so that a deployment that does not accept the
  egress path has a same-interface alternative with no egress at all.

**Alternatives considered and rejected:**

*A third network, `egress`, joining only `backend` and an outbound proxy.* This is
the better design at scale — the proxy allowlists `api.groq.com` and nothing else,
so a compromised backend cannot exfiltrate to an arbitrary host. We rejected it
for a five-container assignment because it adds a container that does nothing
demonstrable, and the property it buys (allowlisted egress) is better shown on the
cluster with a NetworkPolicy, which is where we show it.

*A separate `triage-worker` service on `edge` only, with the backend queueing work
to it through Redis.* Cleanest isolation: the key lives in a process with no
database access at all, so compromising the backend yields no key and compromising
the worker yields no data. Rejected because it turns a synchronous request into an
asynchronous one, and the Submit view's contract — "you get your category back on
the response" — is what makes the loading state honest. Making triage async is the
first thing we would do if throughput ever mattered more than that.

*Dropping `internal: true`.* Rejected. It is the requirement, and it is right.

---

## 8. The failure that cost more than an hour

**Symptom.** The backend container was healthy, `/health` returned 200, and every
`POST /api/complaints` returned `201` with `triaged_by: "rules:fallback"`. No
error in the response. One `WARNING` per request in the logs — which is exactly
what the design says should happen, so for a while it looked like the system
working correctly rather than a bug. The stack had been "working" for some time
before anyone noticed that *the model had never once been called successfully*.

**What we believed first, in order:**

1. "The free tier is rate-limiting us." Plausible: the warning class was a
   provider error, and Groq's limits are per-organization. We backed off the
   request rate. No change.
2. "The key is wrong." We regenerated it. No change — and this cost the most
   time, because we could not simply print the key to check it: it is a
   `SecretStr` and the formatter redacts it, by design. We spent twenty minutes
   arguing with our own security control, which in hindsight is the control
   working.
3. "The model name is deprecated." We changed `LLM_MODEL`. No change.

**What told us the truth.** The warning line carries the error *class*, not just a
message, and reading it properly rather than skimming it:

```json
{"level":"WARNING","event":"triage_fallback","complaint_id":"...","provider":"llm:groq",
 "error_class":"ConnectError","error":"[Errno -3] Temporary failure in name resolution"}
```

`ConnectError`, not `TriageUpstreamError`. Not authentication, not rate limiting —
**DNS**. Confirmed in one command:

```bash
$ docker compose exec backend getent hosts api.groq.com
$ echo $?
2
```

The backend could not resolve the host at all. The cause was ours and was in this
repository: an earlier revision of `compose.yaml` had `backend` attached to
`internal` only. `internal: true` had done precisely what §2.4 of the assignment
says it does, and the fallback had done precisely what it is designed to do —
absorbed a total provider outage so smoothly that it hid the outage.

**The fix** was one line: adding `edge` to the backend's network list. It is
question 7 above, discovered the expensive way.

**What we changed as a result**, which matters more than the fix:

- `error_class` is now logged as a distinct field rather than being folded into
  the message string, so the *kind* of failure is greppable and dashboard-able:
  `backend/app/services/triage.py:128`.
- `GET /api/meta/providers` reports the active provider and the last 20 outcomes
  with a `fallback` flag. A 100% fallback rate over twenty consecutive complaints
  is visible in one request now, instead of being inferable by reading logs.
- `docs/RUNBOOK.md` opens its triage-failure section with
  `docker compose exec backend getent hosts api.groq.com`, before anything about
  keys or quotas, because "is it DNS" should always be question one.
- We stopped treating a `WARNING` as an acceptable steady state. A fallback is a
  *degraded* state; if it is the normal state, something is broken and the system
  should say so loudly. `civicpulse_triage_fallbacks_total` is the metric to alert
  on, and the alert threshold is a sustained rate, not a single event.

The general lesson, stated for the viva: **a good fallback hides the failure it
absorbs.** That is what it is for, and it is also why you must instrument the
fallback itself. A system that degrades silently and a system that works are
indistinguishable from the outside — which is the whole argument for
`/api/meta/providers` existing at all.

---

## Appendix — the two indexes, and the query each serves

Required by §2.3, and stated here because an unexplained index is cargo cult.

**`ix_complaints_status_priority` on `(status, priority)`** — `backend/alembic/versions/0001_initial_schema.py:57`.

Serves the dashboard's default and most common query, `ComplaintRepository._filtered`
(`backend/app/repositories/complaints.py:49–62`), which the operations view issues on
every page load:

```sql
SELECT ... FROM complaints WHERE status = 'open' AND priority = 'high'
ORDER BY created_at DESC LIMIT 20 OFFSET 0;
```

Column order is `(status, priority)` and not the reverse because `status` is the
filter that is almost always present — the dashboard defaults to open work — and a
composite index can serve a prefix of its columns but not a suffix. `WHERE status = ?`
alone uses this index; `WHERE priority = ?` alone would not. The same index serves
the `COUNT(*)` that produces `total` for pagination, and `/api/stats`'s grouped
counts (`repositories/complaints.py:86–95`) can be answered index-only.

**`ix_complaints_created_at` on `created_at`** — same migration, line 59.

Serves the `ORDER BY created_at DESC` in `list_page`
(`backend/app/repositories/complaints.py:76`). Without it, an unfiltered dashboard
page — which is a `SELECT` over the whole table followed by a sort — has to sort
every row to return twenty. With 34 seeded complaints that is invisible; with a
Monday queue of four hundred, and with a year of history behind it, it is the
difference between a dashboard and a timeout. It also serves any future
time-window report ("complaints filed this week"), which is the first thing a
municipality asks for after it has the dashboard.

**Why Redis AOF needs a named volume** (§2.4's question, answered here since it is
adjacent): the cache does not need it and could be rebuilt — but `redisdata` is not
only holding the cache. It holds the rate-limiter counters and the 24-hour triage
cache. Losing the triage cache on every restart means re-paying for inference we
already bought, against a free tier measured in tens of requests per minute;
losing the rate-limiter counters means every attacker's budget resets each time
the cache restarts, which turns "restart Redis" into a bypass for the control
protecting the quota. The volume is not there to make the cache durable. It is
there because we deliberately put two non-cache workloads on cache
infrastructure, and those two have memory.
