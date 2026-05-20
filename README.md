# Barista

A Frappe app to create, run, and observe **local Frappe benches and sites**
from a single, modern Frappe-UI dashboard.

Barista is to a self-hosted developer / small-team what
[frappe/press](https://github.com/frappe/press) is to Frappe Cloud — but
shrunk down to a single host, using **Docker containers** instead of
provisioned VMs, and shipped as a self-contained Frappe app you can install
on a laptop or a self-hosted VPS.

---

## Goals

1. **One-command install** on macOS or Linux: `curl ... | bash` and you have
   a running Barista with one bench and one site.
2. **Bench-as-a-container**: every Barista-managed bench is a Docker
   container (or set of containers via `docker compose`) so benches are
   isolated, reproducible, and disposable.
3. **Frappe-native**: everything Barista does is modelled as **DocTypes**,
   exposed through standard `frappe.client` / whitelisted methods, and
   surfaced through realtime via `frappe.publish_realtime`. No bespoke
   protocol.
4. **Frappe-UI front-end**: a single SPA mounted at `/barista` using the
   public Frappe-UI component library (`Button`, `ListView`, `Dialog`,
   `Charts`, `TabButtons`, `CommandPalette`, etc.) and the
   `createResource` / `createListResource` data layer.
5. **Observability built in**: web analytics, background jobs, error logs,
   slow queries, binary log browsing, and system metrics — all surfaced
   through the same UI you create benches with.

## Non-goals

- Multi-host orchestration. Barista is a **single-host** tool. (One Docker
  daemon. If you outgrow it, use Press.)
- Replacing `bench` CLI. Barista *wraps* `bench` inside containers; power
  users can still `docker exec` and run `bench` by hand.
- Payment, subscription, plan management. (Press territory.)

## What you get on first run

```
your host
└── docker
    └── bench: barista-bench-01      ← created automatically
        ├── apps: frappe, barista
        └── sites
            └── barista.localhost    ← the Barista control-plane site
```

The control-plane site `barista.localhost` runs the Barista app itself.
**All Barista state lives in this site's database** — there is no
sidecar config store, no `barista.yaml`, no second SQLite. If you can
back up that one site, you can rebuild your entire local fleet.

## Spec index

| # | Doc | What's in it |
|---|---|---|
| 01 | [01-architecture.md](01-architecture.md) | System diagram, processes, control vs data plane |
| 02 | [02-doctypes.md](02-doctypes.md) | Every DocType, fields, relationships, naming |
| 03 | [03-docker-design.md](03-docker-design.md) | Bench image, volumes, networking, MariaDB/Redis topology |
| 04 | [04-api-and-realtime.md](04-api-and-realtime.md) | Whitelisted endpoints, realtime events, job patterns |
| 05 | [05-frontend.md](05-frontend.md) | Routes, Frappe-UI components used, ASCII wireframes |
| 06 | [06-install-and-bootstrap.md](06-install-and-bootstrap.md) | `install.sh`, first-run wizard, idempotency |
| 07 | [07-observability.md](07-observability.md) | Web analytics, slow queries, binlog browser, jobs, errors, system perf |
| 08 | [08-security-and-permissions.md](08-security-and-permissions.md) | Roles, container isolation, secrets, audit |

The companion install script lives at [install.sh](install.sh).

## Status

This folder contains **specs only** — no Python or Vue code yet. The
intent is that an engineer (or Claude) can read this folder end to end
and implement Barista without further design decisions.
