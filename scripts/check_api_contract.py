#!/usr/bin/env python3
"""Check the frontend's declared API contract against the backend's OpenAPI schema.

The frontend is typed by hand in `frontend/src/api/types.ts`, and the set of
operations and enums it depends on is declared in
`frontend/src/api/contract.json`. That declaration is worthless unless something
proves it still matches the server, so CI runs this script against the live
`/openapi.json` of a freshly built backend.

This is the cheap half of "a typed API client checked against the backend's
OpenAPI schema": if a backend author renames a path, changes a success code or
adds an enum member, the frontend build goes red in CI rather than the feature
going quietly broken in a browser.

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "frontend/src/api/contract.json"


def fetch_schema(url: str, attempts: int = 30) -> dict[str, Any]:
    last: Exception | None = None
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
            last = exc
            time.sleep(2)
    raise SystemExit(f"could not fetch the OpenAPI schema from {url}: {last}")


def collect_enum(schema: dict[str, Any], name: str) -> list[str] | None:
    component = schema.get("components", {}).get("schemas", {}).get(name)
    if not component:
        return None
    if "enum" in component:
        return [str(value) for value in component["enum"]]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="e.g. http://localhost:8000")
    parser.add_argument(
        "--schema-path",
        default="/openapi.json",
        help="path to the OpenAPI document (default: /openapi.json)",
    )
    args = parser.parse_args()

    if not CONTRACT.exists():
        raise SystemExit(f"contract file not found: {CONTRACT}")
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    schema = fetch_schema(f"{args.base_url.rstrip('/')}{args.schema_path}")
    paths: dict[str, Any] = schema.get("paths", {})

    problems: list[str] = []
    checked = 0

    for operation in contract["operations"]:
        method = operation["method"].lower()
        path = operation["path"]
        label = f"{method.upper()} {path}"

        entry = paths.get(path)
        if entry is None:
            # FastAPI may name the parameter differently; try a shape match.
            candidates = [
                known
                for known in paths
                if _shape(known) == _shape(path)
            ]
            if candidates:
                problems.append(
                    f"{label}: not found, but the server exposes {candidates[0]} — "
                    "the path parameter was renamed"
                )
                continue
            problems.append(f"{label}: the server does not expose this path")
            continue

        if method not in entry:
            problems.append(
                f"{label}: path exists but not for this method "
                f"(server has: {', '.join(sorted(entry)).upper()})"
            )
            continue

        responses = entry[method].get("responses", {})
        expected = [str(operation["success"]), *[str(c) for c in operation.get("errors", [])]]
        for code in expected:
            if code not in responses:
                problems.append(
                    f"{label}: the frontend handles {code} but the schema does not "
                    f"document it (documented: {', '.join(sorted(responses))})"
                )
        checked += 1

    for name, members in contract.get("enums", {}).items():
        server = collect_enum(schema, name)
        if server is None:
            problems.append(f"enum {name}: not present in components.schemas")
            continue
        missing = [m for m in members if m not in server]
        extra = [m for m in server if m not in members]
        if missing:
            problems.append(
                f"enum {name}: the frontend renders {missing} which the server no longer accepts"
            )
        if extra:
            problems.append(
                f"enum {name}: the server added {extra} — the frontend has no label or colour "
                "for these and will render them raw"
            )

    print(f"checked {checked} operation(s) and {len(contract.get('enums', {}))} enum(s)")
    if problems:
        print("\nContract drift detected:\n")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\nFix the backend, or update frontend/src/api/{contract.json,types.ts} "
            "in the same pull request."
        )
        return 1
    print("Frontend contract matches the backend's OpenAPI schema.")
    return 0


def _shape(path: str) -> str:
    """Normalise /api/complaints/{anything} so a renamed parameter is detectable."""
    out: list[str] = []
    depth = 0
    for char in path:
        if char == "{":
            depth += 1
            out.append("{")
        elif char == "}":
            depth -= 1
            out.append("}")
        elif depth == 0:
            out.append(char)
    return "".join(out)


if __name__ == "__main__":
    sys.exit(main())
