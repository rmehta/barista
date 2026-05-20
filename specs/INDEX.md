# Specs

Design documents for Barista. The top-level [README](../README.md) has
the pitch and quick-start; this folder has the long-form internals.

Read order: 01 → 09. Each doc is self-contained but assumes you've
read the ones with lower numbers.

| # | Doc | What's in it |
|---|---|---|
| 01 | [01-architecture.md](01-architecture.md) | Three-plane system diagram, processes, request flow |
| 02 | [02-doctypes.md](02-doctypes.md) | Every DocType, fields, relationships, naming |
| 03 | [03-docker-design.md](03-docker-design.md) | Bench image, volumes, networking, MariaDB/Redis topology |
| 04 | [04-api-and-realtime.md](04-api-and-realtime.md) | Whitelisted endpoints, realtime events, job patterns |
| 05 | [05-frontend.md](05-frontend.md) | Routes, Frappe-UI components used, ASCII wireframes |
| 06 | [06-install-and-bootstrap.md](06-install-and-bootstrap.md) | `install.py`, first-run wizard, idempotency |
| 07 | [07-observability.md](07-observability.md) | Web analytics, slow queries, binlog browser, jobs, errors, system perf |
| 08 | [08-security-and-permissions.md](08-security-and-permissions.md) | Roles, container isolation, secrets, audit |
| 09 | [09-docker-manager.md](09-docker-manager.md) | The privileged Flask microservice that owns Docker |

Reference implementations:
- [../install.py](../install.py) — Python installer
- [../docker-manager/](../docker-manager/) — Flask microservice
- [../barista/](../barista/) — the Frappe app
- [../dashboard/](../dashboard/) — Vue + frappe-ui SPA

The specs lead implementation; if you see a mismatch, prefer fixing
the code unless the spec is clearly wrong.
