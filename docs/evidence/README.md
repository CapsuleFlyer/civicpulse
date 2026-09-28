# Evidence index

Artefacts that prove the claims made elsewhere in this repository. A screenshot
is not decoration here — several rubric items can only be demonstrated by one,
because the thing being demonstrated (a blocked merge, an HPA scaling out) does
not survive as a file.

Capture these yourself. Nothing in this folder can be generated from the source.

---

## 1. Process evidence

| File | What it must show | How |
| --- | --- | --- |
| `branch-protection.png` | `main` protected: PR required, CI status check required, no direct pushes | Settings → Branches → the rule, expanded |
| `blocked-merge.png` | A PR with the merge button **disabled** because a required check failed | Push a commit that fails `ruff` or a test, screenshot the PR, then fix it |
| `merge-conflict.png` | A real conflict and its resolution | Two branches editing the same lines; screenshot the conflict, then `git log --graph` after resolving |
| `pr-review.png` | A review with substantive comments, not "LGTM" | Any of your PRs where one of you asked for a change |
| `git-graph.txt` | Branch topology | `git log --all --graph --oneline --decorate > docs/evidence/git-graph.txt` |
| `contributions.txt` | Both members contributing (floor: 35% each) | `git shortlog -sn --all > docs/evidence/contributions.txt` |

## 2. Runtime evidence

| File | What it must show | How |
| --- | --- | --- |
| `screenshot-submit.png` | Submit view mid-triage, then the triage receipt with provider and latency | Submit a complaint with `TRIAGE_PROVIDER=llm` |
| `screenshot-dashboard.png` | Dashboard with filters applied, priority visibly encoded | Filter to `open` + `high` |
| `screenshot-409.png` | The server's 409 message rendered verbatim in the UI | Move a complaint to `resolved`, then try `in_progress` |
| `screenshot-stats.png` | Stats view showing its own cache state | Reload twice; the second is a HIT |
| `screenshot-fallback.png` | A complaint showing `rules:fallback` | Set `TRIAGE_PROVIDER=llm` with a deliberately invalid key |
| `compose-ps.txt` | All five services `(healthy)` | `docker compose ps > docs/evidence/compose-ps.txt` |
| `network-isolation.txt` | Frontend cannot resolve the database | `docker compose exec frontend getent hosts database; echo "exit: $?"` |
| `image-sizes.txt` | Both image sizes, and the build context size | `docker images \| grep civicpulse`, plus `du -sh backend frontend` before and after `.dockerignore` |

## 3. Kubernetes evidence

| File | What it must show | How |
| --- | --- | --- |
| `hpa-watch.txt` | REPLICAS rising under load | `make hpa-watch` in one terminal, `make load` in another |
| `hpa-scaleout.png` | The same, as a chart or annotated terminal | Screenshot of the above, or plot replicas over time |
| `vpa-recommendation.txt` | VPA `Target` / `Lower Bound` / `Upper Bound` | `kubectl describe vpa backend-vpa -n civicpulse > docs/evidence/vpa-recommendation.txt` |
| `rollout-undo.txt` | A rollback completing | `kubectl rollout undo deployment/backend -n civicpulse` and `rollout status` |
| `k6-summary.txt` | Zero-downtime: no failed requests during a rolling update | `make load` while `kubectl set image` triggers a rollout |
| `pods-wide.txt` | Pods across nodes, images by SHA | `kubectl -n civicpulse get pods -o wide` |

## 4. CI/CD evidence

| File | What it must show | How |
| --- | --- | --- |
| `ci-run.png` | A full green CI run with every job visible | Actions tab, a successful PR run |
| `cd-run.png` | Build → push → deploy → smoke, with `needs:` gating visible in the graph | Actions tab, a `main` run |
| `ghcr-tags.png` | Images tagged by SHA in the registry | GHCR package page |
| `trivy-report.txt` | The scan result you are standing behind | Artifact from the CI run |
| `sbom.json` | The generated SBOM | Artifact from the CD run |

## 5. Measurements to fill in

These replace the `MEASURE:` markers in [../TRIAGE.md](../TRIAGE.md) and the
`MEASURED:` markers in [../ENGINEERING-NOTES.md](../ENGINEERING-NOTES.md):

- Triage latency, mean and p95, per provider — SQL query is in TRIAGE.md
- Triage cache hit rate — `curl -sS localhost:8000/metrics | grep triage_cache`
- Category and priority agreement per provider against your own hand labels
- HPA lag: seconds from load step to first new pod `Ready`
- Final image sizes for both containers
- Build context size before and after `.dockerignore`

---

## Naming

Keep the filenames above. The README, the engineering notes and the evidence
tables all reference them by path, and a renamed file becomes a broken image in
the document a marker reads first.
