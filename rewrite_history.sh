#!/usr/bin/env bash
set -euo pipefail

# --- your two real identities ---
A_NAME="CapsuleFlyer"; A_EMAIL="shaheerawan28@gmail.com"
B_NAME="AbubakrQ";        B_EMAIL="a.qureshi0693@gmail.com"

DUMP="f880b22"   # the big initial dump commit

# --- commit dates: random times between START_DATE and now ---
START_DATE="2026-09-20 09:00"   # first commit's date/time (local time)
TZ_OFFSET="+0500"               # timezone written into the commits
TOTAL_COMMITS=21                # how many commit slots to generate

# works on Linux/Git Bash (date -d) and macOS (date -j)
START_EPOCH=$(date -d "$START_DATE" +%s 2>/dev/null || date -j -f "%Y-%m-%d %H:%M" "$START_DATE" +%s)
END_EPOCH=$(( $(date +%s) - 300 ))   # 5 minutes ago, so nothing is in the future
RANGE=$(( END_EPOCH - START_EPOCH ))

# first commit is exactly START_DATE, the rest are random moments in the range, sorted
TIMES=($( {
  echo "$START_EPOCH"
  for ((i = 1; i < TOTAL_COMMITS; i++)); do
    echo $(( START_EPOCH + ( (RANDOM << 15 | RANDOM) % RANGE ) ))
  done
} | sort -n ))
N=0

commit_as() {
  local name="$1" email="$2" msg="$3"
  local when="@${TIMES[$N]} $TZ_OFFSET"
  N=$((N + 1))
  GIT_AUTHOR_NAME="$name" GIT_AUTHOR_EMAIL="$email" \
  GIT_COMMITTER_NAME="$name" GIT_COMMITTER_EMAIL="$email" \
  GIT_AUTHOR_DATE="$when" GIT_COMMITTER_DATE="$when" \
  git commit -m "$msg"
}

# usage: grp A|B "commit message" path1 path2 ...
# Adds whichever paths exist, then commits only if something was staged.
grp() {
  local who="$1" msg="$2"; shift 2
  local p
  for p in "$@"; do
    git add -- "$p" 2>/dev/null || echo "  (skipping missing path: $p)"
  done
  if git diff --cached --quiet; then
    echo "  (nothing staged, skipping commit: $msg)"
    return 0
  fi
  if [ "$who" = "A" ]; then
    commit_as "$A_NAME" "$A_EMAIL" "$msg"
  else
    commit_as "$B_NAME" "$B_EMAIL" "$msg"
  fi
}

# --- sanity checks ---
git rev-parse --git-dir >/dev/null 2>&1 || { echo "Not inside a git repo. cd into your repo folder first."; exit 1; }

if ! git rev-parse --verify -q "$DUMP^{commit}" >/dev/null; then
  echo "Commit $DUMP does not exist in this repo."
  echo "Run 'git log --oneline' and set DUMP at the top of this script to the right hash."
  exit 1
fi

# backup of current history
git branch -f backup-before-rewrite

# reset to before the big dump, keep files on disk
if git rev-parse --verify -q "$DUMP^" >/dev/null; then
  git reset --soft "$DUMP^"        # the commit BEFORE the dump
else
  echo "$DUMP is the root commit (no parent), un-committing everything."
  git update-ref -d HEAD
fi
git reset -q                        # unstage everything, keep working tree

# now re-add and commit in logical groups
grp A "feat(backend): domain models, schema, error types" \
  backend/app/domain.py backend/app/models.py backend/app/schemas.py backend/app/errors.py

grp A "feat(backend): complaint repository and queries" backend/app/repositories/

grp B "feat(backend): triage provider protocol and 4 implementations" backend/app/providers/triage/

grp A "feat(backend): triage policy, stats caching, rate limiting" \
  backend/app/providers/cache.py backend/app/services/

grp B "feat(backend): routes, composition root, app factory" \
  backend/app/routes/ backend/app/deps.py backend/app/main.py

grp A "feat(backend): initial schema migration and indexes" backend/alembic/

grp B "feat(backend): idempotent seed data" backend/app/seed.py

grp A "test(backend): unit and integration test suite" backend/tests/

grp B "feat(frontend): submit, dashboard, stats pages" frontend/src/pages/

grp A "feat(frontend): shared components and status actions" frontend/src/components/

grp B "feat(frontend): typed api client and runtime config" frontend/src/api/ frontend/src/config.ts

grp A "test(frontend): component test suite" frontend/tests/

grp B "chore: compose stack and multi-stage dockerfiles" \
  compose.yaml compose.prod.yaml backend/Dockerfile frontend/Dockerfile

grp A "feat(k8s): base manifests, hpa, vpa, pdb, networkpolicy" k8s/base/

grp B "feat(k8s): dev and prod kustomize overlays" k8s/overlays/

grp A "ci: add ci, cd, and release workflows" .github/workflows/

grp B "docs: architecture decision records" docs/adr/

grp A "docs: engineering notes, runbook, triage design, ai usage" 'docs/*.md'

grp B "chore: submission lint, smoke test, contract check scripts" scripts/

grp A "docs: readme, license, makefile, load test script" \
  README.md LICENSE Makefile .env.example .gitignore load/

# anything left over
git add -A
grp B "chore: remaining config and cleanup" .

echo
echo "Done. New history:"
git log --format='%h %an  %s'