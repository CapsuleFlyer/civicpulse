# Runbook

Written for the person who did not build this and is reading it at 3 a.m.
Commands are copy-pasteable. Every section starts with the cheapest diagnostic,
not the most likely cause.

**Namespace:** `civicpulse` · **Images:** `ghcr.io/your-org/civicpulse-{backend,frontend}`
· **Deploy unit:** a commit SHA, never `latest`.

---

## 0. Is it actually broken? — 60 seconds

```bash
# Compose
docker compose ps                     # every service should read (healthy)
curl -sS localhost:8000/health        # liveness: process alive, no DB touched
curl -sS localhost:8000/ready         # readiness: Postgres AND Redis answered
curl -sSI localhost:8000/api/stats | grep -i x-cache

# Kubernetes
kubectl -n civicpulse get pods -o wide
kubectl -n civicpulse get deploy,sts,hpa
kubectl -n civicpulse rollout status deployment/backend --timeout=30s
```

Read the two health endpoints as a pair, because they answer different questions:

| `/health` | `/ready` | Meaning |
| --- | --- | --- |
| 200 | 200 | Healthy. Look elsewhere — ingress, DNS, the client. |
| 200 | 503 | The app is fine; a **dependency** is not. `/ready`'s body names which. Go to §2 or §3. |
| 200 | 503 `"draining"` | The pod is shutting down on purpose. Expected during a rollout. |
| connection refused | — | The process is gone. §1. |

`/ready` returns the failing dependency by name, so read the body before guessing:

```bash
kubectl -n civicpulse exec deploy/backend -- curl -sS localhost:8000/ready
# {"status":"degraded","failed":"cache","checks":{"database":"ok","cache":"unreachable"}}
```

---

## 1. Deploy

### Normal path — automatic

Merge to `main`. `cd.yml` runs the full suite, builds both images, pushes them to
GHCR tagged with the commit SHA, generates an SBOM, signs with Cosign, and
deploys. Watch it in the Actions tab; the job summary prints the SHA-to-digest
mapping, which is the answer to "what is running?".

### Manual path — when you must

```bash
SHA=$(git rev-parse HEAD)            # the SHA you want, not necessarily HEAD
cd k8s/overlays/prod
kustomize edit set image \
  ghcr.io/your-org/civicpulse-backend=ghcr.io/your-org/civicpulse-backend:$SHA
kustomize edit set image \
  ghcr.io/your-org/civicpulse-frontend=ghcr.io/your-org/civicpulse-frontend:$SHA
cd -
kubectl apply -k k8s/overlays/prod
kubectl -n civicpulse rollout status deployment/backend --timeout=300s
```

Then **commit the kustomization change**. A cluster running something the
repository does not describe is how the next incident starts.

Never `kubectl set image ... :latest`. `scripts/check_submission.py` fails the
build if that string appears in a deploy path, and the reason is §3 of the
engineering notes.

### Migrations

Migrations run as a Kubernetes `Job` (`k8s/base/backend.yaml`) and as an
entrypoint step under Compose, gated by `RUN_MIGRATIONS`. They run *before* new
pods serve traffic. Alembic owns all DDL — the application never calls
`create_all`, and the submission lint fails if it starts to.

```bash
kubectl -n civicpulse logs job/migrate
kubectl -n civicpulse exec deploy/backend -- alembic current
kubectl -n civicpulse exec deploy/backend -- alembic history --verbose
```

If a migration fails, the Job fails and the rollout does not proceed. Fix
forward with a new migration. Do not hand-edit the schema; the next `alembic
upgrade` will disagree with you.

---

## 2. Rollback

**While users are affected, use the imperative one.** It is one command, needs no
repository, and is the reason Kubernetes keeps a ReplicaSet history.

```bash
kubectl -n civicpulse rollout undo deployment/backend
kubectl -n civicpulse rollout status deployment/backend --timeout=120s
```

To a specific revision:

```bash
kubectl -n civicpulse rollout history deployment/backend
kubectl -n civicpulse rollout undo deployment/backend --to-revision=7
```

**Once the fire is out, use the declarative one**, so the cluster and the
repository agree again:

```bash
cd k8s/overlays/prod
kustomize edit set image ghcr.io/your-org/civicpulse-backend=ghcr.io/your-org/civicpulse-backend:$GOOD_SHA
cd - && kubectl apply -k k8s/overlays/prod
git commit -am "revert: pin backend to $GOOD_SHA after incident" && git push
```

The trade-off, stated plainly: `rollout undo` is fast and leaves no trace in git,
so the cluster silently drifts from the repository and the *next* `apply` — from
anyone, including CI — re-deploys the bad SHA. It buys minutes at the cost of
truth. Use it, then repay the debt within the hour.

**Rolling back a migration** is a different and harder problem. `alembic
downgrade` exists, but a downgrade that drops a column destroys data the old code
cannot recreate. Prefer expand-and-contract: deploy the schema change first in a
backwards-compatible form, deploy the code, drop the old column in a later
release. If you must downgrade, snapshot first:

```bash
kubectl -n civicpulse exec postgres-0 -- pg_dump -U civic civicpulse > /tmp/pre-downgrade.sql
```

---

## 3. Triage is failing (the most likely incident)

Symptom: complaints still return `201` — by design — but `triaged_by` reads
`rules:fallback` and categories are obviously coarse. **The system is degraded,
not down,** and it will stay quietly degraded until someone looks. Check:

```bash
curl -sS localhost:8000/api/meta/providers | python -m json.tool
```

A `fallback: true` on most of the last 20 outcomes confirms it.

Work the list in this order. It is ordered by how often each has actually been
the cause, not by how clever it sounds.

**1. Is it DNS?** It usually is, and it is the cheapest check.

```bash
docker compose exec backend getent hosts api.groq.com   # exit 2 = cannot resolve
kubectl -n civicpulse exec deploy/backend -- getent hosts api.groq.com
```

Exit code 2 on Compose almost always means the backend lost its `edge` network
and is attached only to `internal`, which is `internal: true` and has no route
out. Check `compose.yaml`: `backend` must list **both** networks. On Kubernetes,
check that `k8s/base/networkpolicy.yaml` still has an egress allow for DNS
(port 53 to `kube-system`) and for HTTPS — a default-deny policy with no DNS
allow produces exactly this symptom.

**2. Read the error class, not the message.** Every fallback logs one line:

```bash
kubectl -n civicpulse logs -l app.kubernetes.io/name=backend --tail=200 \
  | grep triage_fallback | tail -5
```

| `error_class` | Means | Do |
| --- | --- | --- |
| `ConnectError` / name resolution | Network or DNS | Step 1 |
| `TriageTimeout` | Provider slower than 10 s | Check the provider's status page; consider `TRIAGE_PROVIDER=ollama` |
| `TriageRateLimited` (429) | Quota exhausted | §3a |
| `TriageBadRequest` (4xx) | Bad key, or a model name that no longer exists | §3b |
| `TriageUpstreamError` (5xx) | Their problem | Wait; the fallback is holding |
| `ValidationError` | Model returned JSON we reject | §3c |

**3a. Rate limited.** The free tier is measured in tens of requests per minute.
Confirm the limiter is actually distributed — if Redis is down, every pod is
limiting independently and you are sending N× the traffic you think:

```bash
kubectl -n civicpulse exec deploy/backend -- curl -sS localhost:8000/ready
kubectl -n civicpulse exec -it redis-0 -- redis-cli --scan --pattern 'civicpulse:ratelimit:*' | head
```

Reduce `RATE_LIMIT_REQUESTS` in the ConfigMap, or switch to `ollama` until quota
resets. Do **not** raise the timeout to compensate; you will convert a fast
failure into a slow one and the whole queue backs up behind it.

**3b. Bad key.** You cannot print it — it is a `SecretStr` and the log formatter
redacts it. That is the control working. Verify presence and shape only:

```bash
kubectl -n civicpulse get secret backend-secrets -o jsonpath='{.data.LLM_API_KEY}' | base64 -d | wc -c
```

If that is 0, the Secret key is missing or misnamed. Rotate at the provider,
update the Secret, restart:

```bash
kubectl -n civicpulse create secret generic backend-secrets \
  --from-literal=LLM_API_KEY="$NEW_KEY" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n civicpulse rollout restart deployment/backend
```

Never paste the key into a manifest, a commit, a ticket, or this file.

**3c. Model returning JSON we reject.** Usually a model change on their side
(code fences, a wrapper object, a category outside our enum). Reproduce against
the provider directly, then either tighten the prompt in
`backend/app/providers/triage/prompt.py` or pin a different `LLM_MODEL`. Ship a
test in `backend/tests/test_triage_policy.py` with the exact malformed shape
before you ship the fix.

**Escape hatch at any point.** Triage provider is configuration, not code:

```bash
kubectl -n civicpulse set env deployment/backend TRIAGE_PROVIDER=rules
```

Complaints keep flowing, categories get coarser, nobody sees an error. That is
the whole point of ADR 0001.

---

## 4. Database

```bash
kubectl -n civicpulse get sts postgres
kubectl -n civicpulse exec -it postgres-0 -- psql -U civic -d civicpulse
```

Useful once you are in:

```sql
-- what is the queue actually like right now
SELECT status, priority, count(*) FROM complaints GROUP BY 1,2 ORDER BY 1,2;

-- is the fallback rate rising over time
SELECT date_trunc('hour', created_at) AS hour,
       count(*) FILTER (WHERE triaged_by = 'rules:fallback') AS fell_back,
       count(*) AS total
FROM complaints GROUP BY 1 ORDER BY 1 DESC LIMIT 12;

-- confirm the dashboard query uses the composite index
EXPLAIN ANALYZE SELECT * FROM complaints
WHERE status = 'open' AND priority = 'high'
ORDER BY created_at DESC LIMIT 20;

-- connections, if the pool looks exhausted
SELECT state, count(*) FROM pg_stat_activity WHERE datname='civicpulse' GROUP BY 1;
```

Backup and restore:

```bash
kubectl -n civicpulse exec postgres-0 -- pg_dump -U civic -Fc civicpulse > backup-$(date +%F).dump
kubectl -n civicpulse exec -i postgres-0 -- pg_restore -U civic -d civicpulse --clean < backup.dump
```

**Disk full on the PVC** is the failure that takes a StatefulSet down hard.
Check early:

```bash
kubectl -n civicpulse exec postgres-0 -- df -h /var/lib/postgresql/data
```

Expanding a PVC requires a StorageClass with `allowVolumeExpansion: true`; edit
the PVC's `spec.resources.requests.storage` and restart the pod. If the class
does not allow it, you are restoring into a new volume from a dump. Find out
which you have *before* the incident.

---

## 5. Cache and rate limiting

```bash
kubectl -n civicpulse exec -it redis-0 -- redis-cli INFO stats | grep keyspace
kubectl -n civicpulse exec -it redis-0 -- redis-cli --scan --pattern 'civicpulse:*' | head -20
```

**If Redis is down**, `/ready` returns 503 naming `cache` and pods leave the
Service. Two consequences worth knowing: `/api/stats` cannot be served from
cache, and the rate limiter is not enforcing globally — which means the LLM quota
it protects is exposed. Restarting Redis is safe for the cache and *not* free for
the other two tenants: counters reset and the 24 h triage cache is cold, so the
next hour of inference is re-paid. This is why `redisdata` is a named volume with
AOF; see the appendix of the engineering notes.

**Stale stats.** `X-Cache: HIT` when you expect fresh data:

```bash
curl -sSI localhost:8000/api/stats | grep -i x-cache   # MISS after any write
kubectl -n civicpulse exec -it redis-0 -- redis-cli DEL civicpulse:stats:v1
```

Writes invalidate the key explicitly, so a stale value after a write is a bug —
file it with the request id from the response header.

---

## 6. Scaling and load

```bash
kubectl -n civicpulse get hpa -w
kubectl -n civicpulse describe hpa backend-hpa
kubectl -n civicpulse top pods
```

`unknown/60%` in the HPA's TARGETS column means metrics-server is not reporting;
the HPA is not scaling and will not tell you so loudly.

```bash
kubectl -n kube-system get deploy metrics-server
kubectl -n kube-system logs deploy/metrics-server --tail=50
```

On k3d, this is usually the kubelet TLS issue; `make cluster` patches
`--kubelet-insecure-tls` for exactly that reason. Never do that on a real cluster.

Expect roughly **95 seconds** between a step in load and new pods serving —
scrape interval, resolution window, controller period, scheduling and startup.
The breakdown is question 5 of the engineering notes. During those 95 seconds the
existing replicas absorb everything, which is what `minReplicas: 2` is for.

Load test:

```bash
make load                              # k6, against the ingress
kubectl -n civicpulse get hpa -w | tee docs/evidence/hpa-watch.txt
```

---

## 7. Logs and tracing a single request

Logs are structured JSON on stdout. Every line carries `request_id`, which is
echoed to the client in `X-Request-ID` and accepted from the client if supplied —
so a user reporting "it failed at 14:32" can hand you the header and you get the
exact request.

```bash
kubectl -n civicpulse logs -l app.kubernetes.io/name=backend --tail=500 \
  | jq 'select(.request_id=="6f1c...")'

kubectl -n civicpulse logs -l app.kubernetes.io/name=backend --since=15m \
  | jq 'select(.level=="ERROR")'

kubectl -n civicpulse logs deploy/backend --previous     # the crashed container
```

The API key never appears here. If you ever see one, that is a P1 of its own:
rotate it, then fix the formatter.

---

## 8. Common failures, shortest path first

| Symptom | Most likely | Command |
| --- | --- | --- |
| Frontend loads, API calls 502 | Backend not ready; nginx has nothing to proxy to | `kubectl -n civicpulse get pods` |
| `CrashLoopBackOff` on backend | Migration failed, or a required env var missing | `kubectl logs deploy/backend --previous` |
| Pods `Pending` forever | No node has the requested CPU/memory, or no PV | `kubectl describe pod <name>` |
| Every complaint `rules:fallback` | DNS / egress | §3, step 1 |
| `PATCH` returns 409 unexpectedly | Correct behaviour — the state machine | Read the body; it names the transition |
| 429 on submit | Rate limiter doing its job | `Retry-After` header; raise the limit only deliberately |
| Stats never update | Redis unreachable, or invalidation bug | §5 |
| Rollout hangs at `1 of 2 updated` | New pod failing readiness | `kubectl describe pod` on the new one |
| `ImagePullBackOff` | SHA never pushed, or GHCR auth | Check the `cd.yml` job summary for the digest |

---

## 9. Escalation

1. **Degraded but serving** (fallback triage, stats stale, one replica down):
   working hours. Open an issue, link the request id.
2. **Serving errors** (5xx rate above a percent, rollout stuck): roll back first
   (§2), investigate second. Rollback is not an admission of anything.
3. **Data at risk** (disk full, migration half-applied, restore in progress):
   stop writes, snapshot, get a second person. Nothing in this runbook is worth
   doing alone at that point.

Before you close anything: add the symptom to §8 and the command that actually
found it to the right section. A runbook that does not grow after an incident is
a runbook nobody will trust during the next one.
