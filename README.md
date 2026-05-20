# Barista ☕

A Frappe app to create, run, and observe **local Frappe benches and
sites** from a single, modern Frappe-UI dashboard.

Barista is to a self-hosted developer / small-team what
[frappe/press](https://github.com/frappe/press) is to Frappe Cloud — but
shrunk to a single host, using **Docker containers** instead of
provisioned VMs, and shipped as a self-contained Frappe app you can
install on a laptop or a small VPS.

[![CI](https://github.com/rmehta/barista/actions/workflows/ci.yml/badge.svg)](https://github.com/rmehta/barista/actions/workflows/ci.yml)

---

## Quick start

> Requires **Docker** (or Docker Desktop on macOS) and **Python ≥ 3.9**.
> ~5 GB of disk in `$HOME` for the data dir.

One command:

```bash
curl -fsSL https://raw.githubusercontent.com/rmehta/barista/main/install.py | python3 -
```

That installs Docker (on Linux, with confirmation) if missing, then
starts:

- `barista-mariadb`, `barista-redis`, `barista-traefik` — shared infra
- `barista-docker-manager` — the privileged microservice (on the
  internal `barista-net` network only)
- `barista-bench-default` — your first bench container, with the
  `barista.localhost` control-plane site inside it

Open the URL the script prints (typically `http://barista.localhost/barista`),
sign in as `Administrator` with the password it just generated, and
you'll see your bench + control-plane site already listed.

Re-running the installer is safe; each step writes a marker under
`~/.barista/.state/` and is skipped on the next run.

### Common flags

```bash
./install.py --domain shop.example.com --email ops@example.com   # real domain + LE TLS
./install.py --no-traefik                                         # use your own proxy
./install.py --dry-run                                            # print, don't change
./install.py --uninstall                                          # stop containers, keep data
./install.py --purge                                              # nuke everything in ~/.barista
```

Full reference: [`./install.py --help`](install.py) and
[specs/06-install-and-bootstrap.md](specs/06-install-and-bootstrap.md).

### After install: try the workflow

1. **Browse the catalog** at `/barista/apps` — 12 first-party Frappe
   apps are pre-seeded (frappe, erpnext, hrms, crm, insights, builder,
   lms, helpdesk, wiki, gameplan, drive, print_designer).
2. **Add a custom app** by Git URL: same page, `+ Add Custom App`.
3. **Create a bench** at `/barista/benches` → `+ New Bench`.
4. **Create a site** with apps pre-selected at `/barista/sites` →
   `+ New Site`.

---

## What's in this repo

```
barista/
├── install.py          ← stdlib-only Python installer; the entrypoint
├── barista/            ← the Frappe app (DocTypes, API, hooks)
│   ├── api/            ← whitelisted methods (bench, site, apps, …)
│   ├── tasks/          ← OO task layer that calls docker-manager
│   ├── barista/        ← Frappe DocType definitions
│   ├── catalog.py      ← first-party app catalog
│   └── tests/          ← unit + Frappe-runner tests
├── docker-manager/     ← Flask microservice that owns /var/run/docker.sock
│   └── src/            ← auth, policy, builds, exec, routes
├── dashboard/          ← Vue 3 + frappe-ui SPA, served at /barista
│   ├── src/pages/      ← BenchList, BenchDetail, SiteList, SiteDetail, AppList
│   └── tests/          ← Vitest
├── specs/              ← design docs — read these to understand internals
├── TEST_PLAN.md        ← layered test strategy
└── .github/workflows/  ← CI: python-unit, docker-manager, frontend, lint
```

The split is deliberate: `install.py` is one file (so
`curl ... | python3 -` works), the Frappe app is one Python package,
the docker-manager is one Flask service, the dashboard is one Vue
app. Four independent components, four sets of tests.

## How it fits together

```
┌────────────── host machine ──────────────┐
│                                          │
│  barista-bench-default                   │
│    └─ Frappe + Barista app               │
│       (your dashboard, all state)        │
│                                          │
│              ↓ HTTP + token              │
│         (on barista-net only)            │
│                                          │
│  barista-docker-manager                  │
│    └─ Flask + /var/run/docker.sock       │
│                                          │
│              ↓                           │
│         Docker daemon                    │
│              ↓                           │
│  any number of other bench containers    │
│                                          │
└──────────────────────────────────────────┘
```

The control plane (Frappe) has **no** Docker access. Only the
Flask microservice does. See
[specs/01-architecture.md](specs/01-architecture.md) and
[specs/09-docker-manager.md](specs/09-docker-manager.md) for the why.

## Developing

```bash
git clone https://github.com/rmehta/barista
cd barista

# Python tests (stdlib-only — no Frappe needed)
pip install pytest requests
PYTHONPATH=. pytest barista/tests/unit -q

# docker-manager tests
pip install -r docker-manager/requirements.txt pytest
pytest docker-manager/tests -q

# Frontend tests + build
cd dashboard
yarn install
yarn test
yarn build      # output: ../barista/public/dist
```

CI runs all of the above on every push: see
[.github/workflows/ci.yml](.github/workflows/ci.yml). The full test
strategy is in [TEST_PLAN.md](TEST_PLAN.md).

### Running the dev SPA against a real bench

The Vue dev server proxies API + assets to a running Frappe bench:

```bash
# in dashboard/
yarn dev   # http://localhost:8080 → http://127.0.0.1:8000 (bench)
```

## Goals & non-goals

**Goals.** One-command install. Bench-as-a-container. Frappe-native
(DocTypes + realtime, no bespoke protocol). Frappe-UI front-end.
Observability built in.

**Non-goals.** Multi-host orchestration (single Docker daemon — if you
outgrow it, use [Press](https://github.com/frappe/press)). Replacing
the `bench` CLI (we wrap it). Payment / plan management.

## Where to look next

- [specs/INDEX.md](specs/INDEX.md) — the spec index
- [specs/01-architecture.md](specs/01-architecture.md) — system shape
- [specs/05-frontend.md](specs/05-frontend.md) — UI wireframes
- [TEST_PLAN.md](TEST_PLAN.md) — testing strategy

## License

AGPL-3.0. See [license.txt](license.txt).
