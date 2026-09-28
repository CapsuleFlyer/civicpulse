#!/usr/bin/env python3
"""Submission lint for CivicPulse.

This is a lint, not a grader. It mechanically checks the failures listed in
the assignment's "automatic deductions" section, because every one of them is
detectable from the repository alone and none of them should ever reach a
marker. Run it from the repository root before you submit:

    python scripts/check_submission.py

Exit code 0 means clean. Exit code 1 means at least one FAIL. WARN findings do
not fail the run but are worth reading.

Deliberately zero third-party dependencies: it must run on a fresh clone with
nothing installed but CPython.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Files we never want to read as text (binary, vendored or generated).
SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "coverage",
    "htmlcov",
    ".idea",
    ".vscode",
}
TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".yaml",
    ".yml",
    ".md",
    ".sh",
    ".env",
    ".example",
    ".conf",
    ".template",
    ".toml",
    ".ini",
    ".cfg",
    ".txt",
    ".html",
    ".css",
    "",
}

# Secret-looking literals. Kept deliberately narrow: a scanner that cries wolf
# gets muted, and a muted scanner catches nothing.
SECRET_PATTERNS: list[tuple[str, str]] = [
    (r"\bgsk_[A-Za-z0-9]{20,}", "Groq API key"),
    (r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}", "OpenAI-style API key"),
    (r"\bAIza[0-9A-Za-z_-]{30,}", "Google API key"),
    (r"\bghp_[A-Za-z0-9]{30,}", "GitHub personal access token"),
    (r"\bxox[abprs]-[A-Za-z0-9-]{10,}", "Slack token"),
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS access key id"),
    (r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", "private key"),
]

# Placeholder values that are allowed to look like credentials.
PLACEHOLDER_HINTS = (
    "changeme",
    "replace",
    "placeholder",
    "example",
    "your-",
    "xxx",
    "<",
    "dummy",
    "notreal",
    "fake",
)


@dataclass
class Report:
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    passes: list[str] = field(default_factory=list)

    def fail(self, check: str, detail: str) -> None:
        self.failures.append(f"{check}: {detail}")

    def warn(self, check: str, detail: str) -> None:
        self.warnings.append(f"{check}: {detail}")

    def ok(self, check: str) -> None:
        self.passes.append(check)


def repo_files() -> list[Path]:
    out: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        out.append(path)
    return out


def read_text(path: Path) -> str:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def looks_like_placeholder(line: str) -> bool:
    lowered = line.lower()
    return any(hint in lowered for hint in PLACEHOLDER_HINTS)


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------


def check_env_not_tracked(report: Report) -> None:
    """-20: a .env, key, token or password anywhere in git history."""
    check = "env-not-tracked"
    tracked = git("ls-files")
    if tracked is None:
        report.warn(check, "not a git repository (or git unavailable) — skipped")
        return

    offenders = [
        name
        for name in tracked.splitlines()
        if Path(name).name == ".env" or Path(name).name.startswith(".env.")
        if not Path(name).name.endswith((".example", ".sample", ".template"))
    ]
    if offenders:
        report.fail(check, f"tracked env file(s): {', '.join(offenders)}")
        return

    history = git("log", "--all", "--pretty=format:", "--name-only", "--diff-filter=A")
    if history:
        ever = sorted(
            {
                name
                for name in history.splitlines()
                if name
                and (Path(name).name == ".env" or Path(name).name.startswith(".env."))
                and not Path(name).name.endswith((".example", ".sample", ".template"))
            }
        )
        if ever:
            report.fail(
                check,
                "a .env file exists in git history (rotate the credential and write "
                f"an incident note): {', '.join(ever)}",
            )
            return
    report.ok(check)


def check_gitignore(report: Report) -> None:
    check = "gitignore"
    path = ROOT / ".gitignore"
    if not path.exists():
        report.fail(check, ".gitignore is missing")
        return
    body = path.read_text(encoding="utf-8")
    required = [".env", "node_modules", "__pycache__"]
    missing = [item for item in required if item not in body]
    if missing:
        report.fail(check, f".gitignore does not cover: {', '.join(missing)}")
        return
    report.ok(check)


def check_no_secrets(report: Report) -> None:
    """-20 / -15: credential literals in the working tree."""
    check = "no-secret-literals"
    hits: list[str] = []
    for path in repo_files():
        if rel(path) == "scripts/check_submission.py":
            continue  # this file contains the patterns themselves
        text = read_text(path)
        if not text:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern, label in SECRET_PATTERNS:
                if re.search(pattern, line) and not looks_like_placeholder(line):
                    hits.append(f"{rel(path)}:{lineno} looks like a {label}")
    if hits:
        for hit in hits:
            report.fail(check, hit)
        return
    report.ok(check)


def check_k8s_secret_placeholders(report: Report) -> None:
    """-15: an LLM API key in a committed manifest, even base64-encoded."""
    check = "k8s-secret-placeholders"
    suspicious: list[str] = []
    for path in (ROOT / "k8s").rglob("*.yaml"):
        text = read_text(path)
        if "kind: Secret" not in text:
            continue
        if re.search(r"^\s*data:", text, re.MULTILINE):
            # base64 is encoding, not encryption. Decode and inspect.
            import base64

            for lineno, line in enumerate(text.splitlines(), start=1):
                match = re.match(r"\s*([\w.\-]+):\s*([A-Za-z0-9+/=]{16,})\s*$", line)
                if not match:
                    continue
                try:
                    decoded = base64.b64decode(match.group(2), validate=True).decode(
                        "utf-8", "replace"
                    )
                except Exception:  # noqa: BLE001 - not base64, not our problem
                    continue
                if any(re.search(p, decoded) for p, _ in SECRET_PATTERNS):
                    suspicious.append(
                        f"{rel(path)}:{lineno} base64 value decodes to a credential"
                    )
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern, label in SECRET_PATTERNS:
                if re.search(pattern, line) and not looks_like_placeholder(line):
                    suspicious.append(f"{rel(path)}:{lineno} contains a {label}")
    if suspicious:
        for item in suspicious:
            report.fail(check, item)
        return
    report.ok(check)


def check_pinned_images(report: Report) -> None:
    """-8: unpinned base image, or postgres/redis/node without a tag."""
    check = "pinned-images"
    problems: list[str] = []

    for dockerfile in ROOT.rglob("Dockerfile*"):
        if any(part in SKIP_DIRS for part in dockerfile.relative_to(ROOT).parts):
            continue
        for lineno, line in enumerate(
            read_text(dockerfile).splitlines(), start=1
        ):
            match = re.match(r"\s*FROM\s+(\S+)", line, re.IGNORECASE)
            if not match:
                continue
            image = match.group(1)
            if image.startswith("$"):
                continue
            base = image.split(" AS ")[0].strip()
            if "@sha256:" in base:
                continue
            name, _, tag = base.partition(":")
            if not tag:
                problems.append(f"{rel(dockerfile)}:{lineno} FROM {base} has no tag")
            elif tag == "latest":
                problems.append(f"{rel(dockerfile)}:{lineno} FROM {base} uses :latest")
            elif "/" in name and name.count("/") > 1 and not tag:
                problems.append(f"{rel(dockerfile)}:{lineno} FROM {base} has no tag")

    for compose in ROOT.glob("compose*.y*ml"):
        for lineno, line in enumerate(read_text(compose).splitlines(), start=1):
            match = re.match(r"\s*image:\s*['\"]?([^'\"\s]+)", line)
            if not match:
                continue
            image = match.group(1)
            if image.startswith("$") or "${" in image:
                continue
            if "@sha256:" in image:
                continue
            _, sep, tag = image.rpartition(":")
            if not sep or "/" in tag:
                problems.append(f"{rel(compose)}:{lineno} image {image} has no tag")
            elif tag == "latest":
                problems.append(f"{rel(compose)}:{lineno} image {image} uses :latest")

    for manifest in (ROOT / "k8s").rglob("*.yaml"):
        for lineno, line in enumerate(read_text(manifest).splitlines(), start=1):
            match = re.match(r"\s*-?\s*image:\s*['\"]?([^'\"\s]+)", line)
            if not match:
                continue
            image = match.group(1)
            if "@sha256:" in image or "${" in image:
                continue
            _, sep, tag = image.rpartition(":")
            if not sep or "/" in tag:
                problems.append(f"{rel(manifest)}:{lineno} image {image} has no tag")
            elif tag == "latest":
                problems.append(f"{rel(manifest)}:{lineno} image {image} uses :latest")

    if problems:
        for item in problems:
            report.fail(check, item)
        return
    report.ok(check)


def check_no_latest_deploy(report: Report) -> None:
    """-8: deploying :latest anywhere."""
    check = "no-latest-deploy"
    problems: list[str] = []
    cd = ROOT / ".github/workflows/cd.yml"
    if not cd.exists():
        report.fail(check, ".github/workflows/cd.yml is missing")
        return
    text = read_text(cd)
    deploy_section = text.split("deploy-k8s:", 1)[-1]
    for lineno, line in enumerate(deploy_section.splitlines(), start=1):
        if re.search(r":latest\b", line) and "set image" in line.lower():
            problems.append(f"cd.yml deploy job sets an image to :latest ({line.strip()})")
        if "kubectl set image" in line and ":latest" in line:
            problems.append(f"cd.yml deploy job sets an image to :latest ({line.strip()})")
    for manifest in (ROOT / "k8s").rglob("*.yaml"):
        for lineno, line in enumerate(read_text(manifest).splitlines(), start=1):
            if re.search(r"image:.*:latest\s*$", line):
                problems.append(f"{rel(manifest)}:{lineno} deploys :latest")
    if problems:
        for item in problems:
            report.fail(check, item)
        return
    report.ok(check)


def check_needs_gating(report: Report) -> None:
    """-8: a publishing or deploying job not gated by needs:."""
    check = "needs-gating"
    problems: list[str] = []
    for workflow in (ROOT / ".github/workflows").glob("*.yml"):
        text = read_text(workflow)
        # Crude job splitter: top-level 2-space keys under jobs:.
        jobs_blob = text.split("\njobs:", 1)
        if len(jobs_blob) < 2:
            continue
        body = jobs_blob[1]
        chunks = re.split(r"\n  (?=[a-zA-Z0-9_-]+:\s*$)", body)
        for chunk in chunks:
            name_match = re.match(r"\s*([a-zA-Z0-9_-]+):", chunk)
            if not name_match:
                continue
            name = name_match.group(1)
            publishes = (
                re.search(r"push:\s*true", chunk) is not None
                or "kubectl apply" in chunk
                or "kubectl rollout" in chunk
                or "softprops/action-gh-release" in chunk
            )
            if not publishes:
                continue
            if not re.search(r"\n\s+needs:", chunk):
                problems.append(
                    f"{rel(workflow)} job '{name}' publishes or deploys without needs:"
                )
    if problems:
        for item in problems:
            report.fail(check, item)
        return
    report.ok(check)


def check_least_privilege_permissions(report: Report) -> None:
    check = "workflow-permissions"
    missing: list[str] = []
    workflows = list((ROOT / ".github/workflows").glob("*.yml"))
    if not workflows:
        report.fail(check, "no workflows found in .github/workflows")
        return
    for workflow in workflows:
        text = read_text(workflow)
        if not re.search(r"^permissions:", text, re.MULTILINE):
            missing.append(rel(workflow))
    if missing:
        for item in missing:
            report.fail(check, f"{item} has no top-level permissions: block")
        return
    report.ok(check)


def check_no_localhost_service_to_service(report: Report) -> None:
    """-8: localhost used for service-to-service communication."""
    check = "no-localhost-service-to-service"
    problems: list[str] = []
    targets = [
        *(ROOT / "backend/app").rglob("*.py"),
        *(ROOT / "frontend/src").rglob("*.ts"),
        *(ROOT / "frontend/src").rglob("*.tsx"),
        *(ROOT / "k8s").rglob("*.yaml"),
        ROOT / "compose.yaml",
        ROOT / "compose.prod.yaml",
        ROOT / "frontend/nginx.conf.template",
        ROOT / ".env.example",
    ]
    pattern = re.compile(r"(localhost|127\.0\.0\.1)")
    for path in targets:
        if not path.exists() or not path.is_file():
            continue
        for lineno, line in enumerate(read_text(path).splitlines(), start=1):
            if not pattern.search(line):
                continue
            lowered = line.lower()
            # Healthchecks, probes and dev-only tooling legitimately talk to
            # the loopback address inside their own container.
            allowed = any(
                token in lowered
                for token in (
                    "healthcheck",
                    "health",
                    "ready",
                    "metrics",
                    "127.0.0.1:8000/health",
                    "cors",
                    "allow_origin",
                    "#",
                    "test:",
                    "pg_isready",
                    "redis-cli",
                    "vite",
                    "dev only",
                    "listen",
                    "host:",   # Ingress hostnames are browser-facing, not service-to-service
                )
            )
            if allowed:
                continue
            problems.append(f"{rel(path)}:{lineno} {line.strip()[:90]}")
    if problems:
        for item in problems:
            report.warn(check, item)
        return
    report.ok(check)


def check_prod_compose(report: Report) -> None:
    """-8 / -1: prod compose must not build, nor publish DB or cache ports."""
    check = "compose-prod-hygiene"
    path = ROOT / "compose.prod.yaml"
    if not path.exists():
        report.fail(check, "compose.prod.yaml is missing")
        return
    text = read_text(path)
    problems: list[str] = []
    if re.search(r"^\s+build:", text, re.MULTILINE):
        problems.append("compose.prod.yaml contains a build: key")
    if "${IMAGE_TAG" not in text:
        problems.append("compose.prod.yaml does not pin images via ${IMAGE_TAG}")

    # Walk the service blocks looking for ports: on database/cache.
    for service in ("database", "cache", "postgres", "redis"):
        block = re.search(
            rf"\n  {service}:\n(.*?)(?=\n  [a-z0-9_-]+:\n|\nnetworks:|\nvolumes:|\Z)",
            text,
            re.DOTALL,
        )
        if block and re.search(r"^\s+ports:", block.group(1), re.MULTILINE):
            problems.append(f"compose.prod.yaml publishes a port on '{service}'")
    if problems:
        for item in problems:
            report.fail(check, item)
        return
    report.ok(check)


def check_network_segmentation(report: Report) -> None:
    """-8: frontend able to reach the database."""
    check = "network-segmentation"
    problems: list[str] = []
    for name in ("compose.yaml", "compose.prod.yaml"):
        path = ROOT / name
        if not path.exists():
            problems.append(f"{name} is missing")
            continue
        text = read_text(path)
        if "internal: true" not in text:
            problems.append(f"{name} has no network with internal: true")
        fe = re.search(
            r"\n  frontend:\n(.*?)(?=\n  [a-z0-9_-]+:\n|\nnetworks:|\nvolumes:|\Z)",
            text,
            re.DOTALL,
        )
        if fe and re.search(r"^\s+-\s+internal\s*$", fe.group(1), re.MULTILINE):
            problems.append(f"{name}: frontend is attached to the internal network")
    if problems:
        for item in problems:
            report.fail(check, item)
        return
    report.ok(check)


def check_postgres_statefulset(report: Report) -> None:
    """-8: PostgreSQL as a Deployment with no PVC."""
    check = "postgres-statefulset"
    path = ROOT / "k8s/base/postgres.yaml"
    if not path.exists():
        report.fail(check, "k8s/base/postgres.yaml is missing")
        return
    text = read_text(path)
    if "kind: StatefulSet" not in text:
        report.fail(check, "postgres is not a StatefulSet")
        return
    if "volumeClaimTemplates" not in text:
        report.fail(check, "postgres StatefulSet has no volumeClaimTemplates")
        return
    if re.search(r"type:\s*(NodePort|LoadBalancer)", text):
        report.fail(check, "the database Service is not ClusterIP")
        return
    report.ok(check)


def check_resource_requests(report: Report) -> None:
    check = "resource-requests"
    problems: list[str] = []
    for manifest in (ROOT / "k8s/base").glob("*.yaml"):
        text = read_text(manifest)
        # Only real workloads. `kind: Deployment` also appears indented inside
        # an HPA scaleTargetRef and a VPA targetRef, which own no containers.
        if not re.search(r"^kind:\s*(Deployment|StatefulSet)", text, re.MULTILINE):
            continue
        if "requests:" not in text:
            problems.append(f"{rel(manifest)} sets no resources.requests (HPA needs it)")
    if problems:
        for item in problems:
            report.fail(check, item)
        return
    report.ok(check)


def check_probes(report: Report) -> None:
    check = "probes"
    path = ROOT / "k8s/base/backend.yaml"
    if not path.exists():
        report.fail(check, "k8s/base/backend.yaml is missing")
        return
    text = read_text(path)
    missing = [
        probe
        for probe in ("startupProbe", "livenessProbe", "readinessProbe")
        if probe not in text
    ]
    if missing:
        report.fail(check, f"backend is missing: {', '.join(missing)}")
        return
    # Liveness must not depend on the database.
    liveness = re.search(r"livenessProbe:(.*?)(?=readinessProbe:|startupProbe:|\n\s{10}\w)", text, re.DOTALL)
    if liveness and "/ready" in liveness.group(1):
        report.fail(check, "livenessProbe points at /ready — a slow DB will restart-loop your pods")
        return
    report.ok(check)


def check_required_files(report: Report) -> None:
    check = "required-files"
    required = [
        "README.md",
        "LICENSE",
        ".env.example",
        ".gitignore",
        "compose.yaml",
        "compose.prod.yaml",
        "docs/ENGINEERING-NOTES.md",
        "docs/RUNBOOK.md",
        "docs/AI-USAGE.md",
        "docs/TRIAGE.md",
        "docs/adr/0001-provider-interface.md",
        "docs/adr/0002-frontend-runtime-config.md",
        "docs/adr/0003-deploy-by-sha.md",
        "docs/adr/0004-pii-and-data-governance.md",
        "load/k6-script.js",
        ".github/workflows/ci.yml",
        ".github/workflows/cd.yml",
        ".github/workflows/release.yml",
        "backend/Dockerfile",
        "backend/.dockerignore",
        "frontend/Dockerfile",
        "frontend/.dockerignore",
        "k8s/base/kustomization.yaml",
        "k8s/overlays/prod/kustomization.yaml",
    ]
    missing = [name for name in required if not (ROOT / name).exists()]
    if missing:
        for name in missing:
            report.fail(check, f"missing {name}")
        return
    report.ok(check)


def check_no_ddl_in_startup(report: Report) -> None:
    check = "migrations-only-ddl"
    problems: list[str] = []
    for path in (ROOT / "backend/app").rglob("*.py"):
        text = read_text(path)
        for lineno, line in enumerate(text.splitlines(), start=1):
            if re.search(r"create_all\s*\(", line) or re.search(
                r"CREATE\s+TABLE", line, re.IGNORECASE
            ):
                problems.append(f"{rel(path)}:{lineno} creates schema outside Alembic")
    if problems:
        for item in problems:
            report.fail(check, item)
        return
    report.ok(check)


def check_sql_only_in_repositories(report: Report) -> None:
    check = "layering"
    problems: list[str] = []
    for path in (ROOT / "backend/app/routes").rglob("*.py"):
        text = read_text(path)
        if re.search(r"\b(select|insert|update|delete)\s*\(", text) or "AsyncSession" in text:
            problems.append(f"{rel(path)} looks like it touches the database directly")
    for directory in ("services", "routes"):
        for path in (ROOT / "backend/app" / directory).rglob("*.py"):
            text = read_text(path)
            if re.search(r"^\s*from sqlalchemy import", text, re.MULTILINE) and directory == "routes":
                problems.append(f"{rel(path)} imports sqlalchemy — SQL belongs in repositories/")
    if problems:
        for item in problems:
            report.fail(check, item)
        return
    report.ok(check)


def check_git_hygiene(report: Report) -> None:
    check = "git-hygiene"
    log = git("log", "--pretty=format:%s")
    if log is None:
        report.warn(check, "no git history available — skipped")
        return
    subjects = [line for line in log.splitlines() if line.strip()]
    if len(subjects) < 35:
        report.warn(check, f"{len(subjects)} commits — the rubric asks for at least 35")
    conventional = re.compile(
        r"^(feat|fix|docs|chore|refactor|test|ci|build|perf|style|revert)(\([^)]+\))?!?:"
    )
    unconventional = [s for s in subjects if not conventional.match(s)]
    if subjects and len(unconventional) > len(subjects) * 0.2:
        report.warn(
            check,
            f"{len(unconventional)}/{len(subjects)} commit subjects are not conventional",
        )
    shortlog = git("shortlog", "-sn", "--all")
    if shortlog:
        counts = []
        for line in shortlog.splitlines():
            parts = line.strip().split("\t")
            if len(parts) == 2 and parts[0].strip().isdigit():
                counts.append(int(parts[0].strip()))
        if len(counts) == 1:
            report.warn(check, "only one contributor in git shortlog -sn")
        elif counts:
            total = sum(counts)
            low = min(counts)
            if total and low / total < 0.35:
                report.warn(
                    check,
                    f"lowest contributor is at {low / total:.0%} of commits (floor is 35%)",
                )
    if not report.warnings or all(not w.startswith(check) for w in report.warnings):
        report.ok(check)


def check_evidence(report: Report) -> None:
    check = "evidence"
    evidence = ROOT / "docs/evidence"
    if not evidence.exists():
        report.fail(check, "docs/evidence/ is missing")
        return
    artefacts = [p for p in evidence.rglob("*") if p.is_file() and p.name != "README.md"]
    if not artefacts:
        report.warn(
            check,
            "docs/evidence/ holds no screenshots yet (branch protection, blocked merge, "
            "merge conflict, hpa -w, scaling chart)",
        )
        return
    report.ok(check)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable output"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat warnings as failures (used by the pre-submission gate)",
    )
    args = parser.parse_args()

    report = Report()
    for check in (
        check_required_files,
        check_env_not_tracked,
        check_gitignore,
        check_no_secrets,
        check_k8s_secret_placeholders,
        check_pinned_images,
        check_no_latest_deploy,
        check_needs_gating,
        check_least_privilege_permissions,
        check_no_localhost_service_to_service,
        check_prod_compose,
        check_network_segmentation,
        check_postgres_statefulset,
        check_resource_requests,
        check_probes,
        check_no_ddl_in_startup,
        check_sql_only_in_repositories,
        check_git_hygiene,
        check_evidence,
    ):
        check(report)

    if args.json:
        print(
            json.dumps(
                {
                    "passes": report.passes,
                    "warnings": report.warnings,
                    "failures": report.failures,
                },
                indent=2,
            )
        )
    else:
        for name in report.passes:
            print(f"PASS  {name}")
        for item in report.warnings:
            print(f"WARN  {item}")
        for item in report.failures:
            print(f"FAIL  {item}")
        print()
        print(
            f"{len(report.passes)} passed, {len(report.warnings)} warning(s), "
            f"{len(report.failures)} failure(s)"
        )
        if not report.failures:
            print("Clean run. This is a lint, not a grader — it does not mean the work is good.")

    if report.failures:
        return 1
    if args.strict and report.warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
