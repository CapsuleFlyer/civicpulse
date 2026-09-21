# ADR 0002 — Frontend configuration at runtime, not build time

- **Status:** Accepted
- **Date:** 2026-02
- **Deciders:** both team members

## Context

The frontend must reach the backend. The default Vite idiom is:

```ts
const API = import.meta.env.VITE_API_URL;
```

Vite **inlines that value into the JavaScript bundle at build time**. The string
is baked into a static asset inside the image.

The consequence is not stylistic. If the API URL is baked in, the image is
environment-specific: staging needs one build, production needs another. Two
builds means two artefacts, which means the thing tested in staging is not the
thing running in production. Build-once-deploy-many is destroyed for half the
system — while the team still believes they have it, because the backend does.
That is worse than obviously not having it.

## Decision

Two mechanisms, together.

**1. nginx proxies `/api` to the backend** (`frontend/nginx.conf.template`). The
browser only ever talks to the origin it loaded from, so in the common case there
is no cross-origin API URL to configure at all, no CORS preflight, and one fewer
thing to get wrong per environment.

**2. Anything genuinely per-environment is written at container start.**
`frontend/docker-entrypoint.sh` runs `envsubst` over a template and writes
`/usr/share/nginx/html/config.js`:

```js
window.__CIVICPULSE_CONFIG__ = { apiBaseUrl: "/api", environment: "production" };
```

`index.html` loads it before the bundle; `frontend/src/config.ts` reads it with a
typed accessor and a development default.

**3. The mistake is made unrepresentable.** `frontend/eslint.config.js` bans
`import.meta.env` outright:

```js
'no-restricted-syntax': [
  'error',
  { selector: "MemberExpression[object.meta.property.name='meta']", message: '...' },
]
```

A reviewer will not catch this reliably — it looks like idiomatic Vite. A linter
catches it every time, in the pull request, before the image exists.

## Consequences

**Good**

- One image per commit, promotable from dev to staging to production unchanged.
- The Kubernetes ConfigMap can change `apiBaseUrl` without a rebuild.
- No CORS configuration in the common path; the backend's `cors_origins`
  defaults to empty.
- The ban makes the decision durable past the people who made it.

**Bad, and accepted**

- One extra network round trip for `config.js` before the app boots. It is a
  sub-kilobyte same-origin file and, unlike the bundle, deliberately uncached.
- `window.__CIVICPULSE_CONFIG__` is a global, which TypeScript cannot verify at
  compile time. Contained by making `config.ts` the only file that reads it.
- The entrypoint is shell. It is fifteen lines, `set -eu`, and runs before nginx.
- Anything in `config.js` is visible to any visitor. Correct — nothing secret may
  ever go there, and the runtime-config pattern makes that easy to forget. The
  file has a comment saying so.

## Alternatives considered

**Build one image per environment.** Rejected — it is the problem, not the fix.

**Fetch configuration from the backend at boot** (`GET /api/config`). Cleaner,
and it makes the frontend unable to start when the backend is down, which turns a
partial outage into a total one. Rejected for that reason.

**Absolute backend URL in `config.js`, no proxy.** Requires CORS, exposes the
backend directly to the internet, and adds a preflight to every request. The
proxy keeps the backend reachable only through the frontend on the `edge`
network, which is the topology we want anyway.
