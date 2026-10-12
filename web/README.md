# applyloop's dashboard

A React + TypeScript + [shadcn/ui](https://ui.shadcn.com) frontend for applyloop, talking to the existing
Python backend's JSON API (`applyloop/ui.py`) — no backend rewrite, just a proper UI in front of it.

## Develop

```bash
# terminal 1: the backend, with a password so you can use the login screen
cd ..
APPLYLOOP_PASSWORD=devpass python -m applyloop ui --port 8765 --no-open

# terminal 2: the frontend, with hot reload
cd web
npm install
npm run dev        # opens on :5173, proxies /api, /screens and /ghosted to :8765
```

Without `$APPLYLOOP_PASSWORD` set, `/api/login` is disabled and `applyloop ui` prints a one-time link with
`?t=<token>` instead — opening that link signs you in automatically (the token is read from the URL and
stored), so the plain local `applyloop ui` workflow keeps working with no password to manage.

## Build

```bash
npm run build
```

Outputs straight into `../applyloop/web_dist/` — **inside the Python package**, not a sibling directory —
so it's picked up by `applyloop ui` under any install method (`pip install -e .`, a plain `pip install .`,
a wheel), not only when running from a source checkout. `applyloop/ui.py` serves `web_dist/` when present
and falls back to the old single-file `ui.html` when it isn't (e.g. a fresh `pip install` before anyone has
run this build).

Commit `web_dist/` is **not** required — it's gitignored, same as `node_modules/` and `web/dist/` (Vite's
own default output location, unused here since `build.outDir` points elsewhere). Run `npm run build` as
part of your deploy step.

## Deploying

One process serves everything: the Python HTTP server (`applyloop ui`) answers both the API and the built
static files, on one port. There's no separate Node server or build step needed at runtime — only at build
time, once, before you start the Python process.

```bash
pip install -e .
cd web && npm install && npm run build && cd ..
APPLYLOOP_PASSWORD=<a real password> python -m applyloop ui --port 8765
```

Put it behind a reverse proxy (Caddy, nginx) for TLS if it's reachable from outside your own machine.
Auth is a single shared password (`$APPLYLOOP_PASSWORD`, timing-safe compared, with a short lockout after 5
wrong attempts) — this is a personal tool for one person's job search, not a multi-user product, so there
are no user accounts to manage.

## Stack

Vite, React 19, TypeScript, Tailwind v4, shadcn/ui (`new-york` style), React Router (`HashRouter` — no
server-side route handling needed beyond the SPA-shell fallback `ui.py` already does), Sonner for toasts.
