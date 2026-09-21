# Submission checklist

**Delete this file before you submit.** It is a handover note, not a deliverable.

What is in the repository is the code, the infrastructure, the pipeline and the
documentation. What is not in it is everything that can only be produced by
running, measuring, or collaborating — which is a substantial share of the marks
and is deliberately not fakeable.

---

## Verified before handover

| Check | Result |
| --- | --- |
| `cd backend && pytest` | 60 passed · **86.85%** coverage (gate 65%) |
| `cd backend && ruff check .` | clean |
| `cd backend && mypy app` | clean, 36 files |
| `cd frontend && npm run test` | 15 tests, 4 files |
| `cd frontend && npx tsc --noEmit` | clean |
| `cd frontend && npm run lint` | clean |
| `cd frontend && npx vite build` | green — 181.92 kB JS / 58.73 kB gzip, 5.94 kB CSS |
| `python scripts/check_submission.py` | **16 passed, 0 failures** (3 warnings, all expected before git init) |
| YAML parse of all 24 manifests and workflows | clean |

Not verified here, because this container has no Docker daemon and no cluster:
`docker compose up`, image builds, `kustomize build`, `kubeconform`, the k3d
deploy. Run those first — see step 1.

---

## 1. Run it before you read it

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps                 # all five healthy
python scripts/integration_smoke.py --base-url http://localhost:8000
```

The smoke script asserts the whole request path including the 409 and the
`X-Cache` MISS→HIT transition. If it passes, the stack is genuinely working.

Then the cluster:

```bash
make cluster
kubectl apply -k k8s/overlays/dev
kubectl -n civicpulse rollout status deployment/backend
```

Expect to fix something here. Manifests that parse are not manifests that run.

## 2. Initialise git properly — this is graded

The rubric wants ≥35 commits, conventional commit messages, a real branching
model, and both members at ≥35% of contributions. **A single "initial commit"
of this whole tree scores near zero on that section**, regardless of the code.

Build the history incrementally and split it between both of you: scaffold,
domain, repository, services, routes, tests, frontend shell, each page,
Dockerfiles, compose, k8s, each workflow, each doc. Use feature branches and
merge them via PRs on GitHub.

```bash
git init && git add .gitignore .env.example LICENSE
git commit -m "chore: repository scaffold"
# ... and so on
python scripts/check_submission.py     # re-run once history exists
```

Enable branch protection on `main` (PR required, CI required) **before** you
open the PRs, so the evidence screenshots are real.

## 3. Capture the evidence

`docs/evidence/README.md` is a complete list with the command for each. The ones
that cannot be reconstructed later:

- a **blocked merge** — push a deliberately failing commit, screenshot the PR
  with the merge button disabled, then fix it
- a **merge conflict** and its resolution
- **branch protection** settings
- `kubectl get hpa -w` while `make load` runs

## 4. Fill in the measurements

Search the repository for `MEASURE:` and `MEASURED:`. Every one is a number that
has to be yours:

- triage latency mean/p95 per provider — SQL in `docs/TRIAGE.md`
- triage cache hit rate — `curl -sS localhost:8000/metrics | grep triage_cache`
- category and priority agreement per provider, against your own hand labels
- HPA lag from load step to first new pod `Ready` — `docs/ENGINEERING-NOTES.md` §5
- both image sizes, and build context before/after `.dockerignore`

The placeholders in §5 of the engineering notes are estimates from the mechanism,
not observations. Replace them.

## 5. Make question 8 yours

`docs/ENGINEERING-NOTES.md` question 8 describes a real failure from this build:
the backend attached only to the `internal` network, `internal: true` killing
DNS, and the fallback hiding it so well that nothing looked broken. It is
accurate.

If your own expensive hour went somewhere else, **write that instead.** The viva
will ask you to walk through it, and the answer you lived is the one you can
defend under follow-up questions.

## 6. Replace the placeholders

```bash
grep -rn "your-org" --include="*.yml" --include="*.yaml" --include="*.md" .
```

`ghcr.io/your-org/...` appears in the compose prod file, the k8s overlays, all
three workflows and the README badges. Point them at your actual repository.

## 7. Screenshots in the README

The README references four images in `docs/evidence/`. Until they exist, those
are broken images on the first page a marker sees.

## 8. The video

Not producible here. The rubric wants the stack running, a complaint submitted
and triaged, the fallback demonstrated (invalid key → `rules:fallback`), the HPA
scaling, and a rollback. `docs/RUNBOOK.md` §2 and §3 are effectively the script.

## 9. Last pass

```bash
python scripts/check_submission.py     # must be 0 failures
rm SUBMISSION-CHECKLIST.md
git status                             # .env must not appear
```

---

## Where the deliberate arguments are

The viva rewards knowing which decisions were contested. In this repository:

| Decision | Where it is argued |
| --- | --- |
| TTL *and* invalidation for the stats cache, not one or the other | README § Redis does two jobs |
| Rate limiter in Redis, not in process | README, same section |
| Pipelined INCR over a Lua script — testability beat atomicity | `backend/app/providers/cache.py` comment, `docs/AI-USAGE.md` |
| Frontend shows every status and lets the server 409 | `docs/AI-USAGE.md`, ADR 0001 |
| `import.meta.env` banned by ESLint | ADR 0002 |
| `latest` pushed, never deployed | ADR 0003 |
| `reporter_contact` never reaches a model; `location` deliberately does | ADR 0004 |
| No PII redaction, because an unreliable redactor is worse than none | ADR 0004 |
| VPA `Off`, and the HPA feedback loop that `Auto` would create | Engineering notes §6 |
| LLM caller in the backend, and the two topologies rejected | Engineering notes §7 |

Know the ones you would defend differently. "We chose X, and here is what it
costs us" scores better than "X is best practice."
