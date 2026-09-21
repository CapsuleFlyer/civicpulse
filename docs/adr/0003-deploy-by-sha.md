# ADR 0003 — Deploy by commit SHA; `latest` is pushed but never deployed

- **Status:** Accepted
- **Date:** 2026-02
- **Deciders:** both team members

## Context

Something has to name the thing being deployed. The available options are a
mutable tag (`latest`, `stable`, `v1`), an immutable tag (a commit SHA, a
semver release), or a content digest (`@sha256:...`).

Mutable tags are the default almost everywhere, and they break three things that
only matter during an incident — which is exactly when you cannot afford them
broken:

- *What is production running?* `latest` is not an answer. It is a pointer whose
  target changed at an unknown time.
- *Roll it back.* Re-deploying the previous mutable tag re-deploys whatever that
  tag currently points at, which may be the thing you are rolling back from.
- *Reproduce the bug.* A rebuild of the "same" commit can produce a different
  image as upstream base layers move underneath it.

## Decision

**Images are built exactly once, in `cd.yml`'s `build-push` job, tagged with the
commit SHA.** Every deployment references that SHA. Nothing downstream rebuilds.

```yaml
tags: |
  ${{ env.BACKEND_IMAGE }}:${{ github.sha }}
  ${{ env.BACKEND_IMAGE }}:latest      # convenience for humans, never deployed
```

The deploy job rewrites the manifests rather than templating them:

```bash
kustomize edit set image ghcr.io/your-org/civicpulse-backend=...:${{ github.sha }}
```

`k8s/overlays/prod/kustomization.yaml` ships with `newTag: REPLACED_BY_CI`, which
fails loudly if someone applies it by hand without substituting. `compose.prod.yaml`
uses `${IMAGE_TAG:?set IMAGE_TAG to a commit SHA}` and has no `build:` key at all,
so forgetting is a startup error and not a surprise.

The **digest** of each build is captured as a job output and written into the
workflow summary, so the SHA-to-digest mapping is recorded even though we deploy
by tag. Digests are the strongest reference; tags are what a human can read in
`kubectl get pods -o wide` at 3 a.m. We keep both and lose neither.

`scripts/check_submission.py` (`check_no_latest_deploy`, `check_pinned_images`)
fails the build if `:latest` appears in any deploy path or if any base image is
unpinned.

## Consequences

**Good**

- "What is production running?" is a SHA you can paste into `git show`.
- Rollback is `kubectl rollout undo`, or re-applying a previous SHA, and both
  name exactly one artefact.
- The image that passed CI is byte-for-byte the image that runs.
- Cosign signatures and the Syft SBOM attach to a specific digest, so a supply
  chain claim refers to something that cannot change.

**Bad, and accepted**

- Tag sprawl in GHCR: one tag per commit to `main`. Storage is cheap; a retention
  policy is the fix if it ever is not.
- SHAs are unreadable. Mitigated by `release.yml`, which adds semver tags on `v*`
  for humans, and by the job summary.
- A manual deploy needs two `kustomize edit` commands, which is friction. The
  friction is the point — and the runbook says to commit the result so the
  cluster and the repository do not drift.

## Alternatives considered

**Deploy by digest.** Strictly stronger, and what we would do at scale. Rejected
because a digest is unreadable in `kubectl` output and mapping it back to a
commit requires a lookup — during an incident, that lookup is a cost. We capture
the digest so the option stays open.

**Semver tags for every deploy.** Requires a version bump per merge, which is
either manual (forgotten) or automated (a second commit per merge). Semver is for
releases; `main` deploys on merge.

**Template the image tag with `envsubst` before `kubectl apply`.** Works, and
produces manifests that exist only in CI, so `kubectl diff` locally compares
against something that is not what is deployed. Kustomize keeps the manifests
real.
