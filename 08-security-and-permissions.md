# 08 · Security & Permissions

Barista has root-equivalent power on the host (it can launch
arbitrary containers via the Docker socket). That makes its
authorization model the single most important spec to get right.

## Threat model

| Actor                  | Capability before Barista          | Capability via Barista (intended) |
|------------------------|------------------------------------|-----------------------------------|
| Local OS user (you)    | Full root via `sudo`               | Same — Barista doesn't add power, just convenience |
| Barista admin user     | None                               | Create/destroy benches, read all data, run `docker exec` |
| Barista editor user    | None                               | Manage sites within already-existing benches |
| Barista viewer user    | None                               | Read-only: see dashboards, audit, logs |
| Anonymous internet     | None                               | Login screen; nothing else without auth |
| Compromised managed site | Code exec in that container      | **Must NOT escalate to other containers or host** ← real risk |

The fourth row is the live one. The other rows are easy.

## Roles

Three custom roles (Frappe-native `Role` doctype):

### `Barista Admin`

- All DocTypes: full perms.
- Privileged actions: yes (Create/Destroy Bench, Rebuild, toggle
  binlog, edit Barista Settings, view bin log events).
- Can read all sites' data.

### `Barista Editor`

- DocTypes: read on `Bench Host`, `Bench Spec`, `Bench Build`,
  `Bench App`. CRUD on `Site`, `Site Backup`.
- Privileged actions: limited to site-level (create site, install app
  on site, backup/restore site, archive site).
- **Cannot** create/destroy benches, change settings, or read bin log.

### `Barista Viewer`

- Read on everything in their permitted sites/benches.
- No actions.

User Permissions filter `Site` rows: by default an editor sees all
sites; an admin can restrict via standard Frappe User Permissions on
`Site` or `Bench Host`.

The default `Administrator` user gets `Barista Admin`. The first user
created by `install.sh` gets it too. Subsequent users default to no
Barista roles — explicitly granted.

## Action authorization at the API layer

Every whitelisted method does **three** checks before enqueueing
anything:

```python
def restart(bench: str):
    # 1. session must be logged in (Frappe default)
    # 2. user must have write perm on the target DocType
    frappe.has_permission("Bench Host", "write", bench, throw=True)
    # 3. user must have the right role for THIS action
    require_barista_role("Barista Admin")          # restart of a bench
    ...
```

The role requirement table:

| Action                                  | Min role        |
|-----------------------------------------|-----------------|
| Bench create / destroy / rebuild        | Barista Admin   |
| Bench start / stop / restart            | Barista Admin   |
| Bench Spec edit                         | Barista Admin   |
| Bench Action read                       | Barista Admin (for bench-targeted), Editor (site-targeted) |
| Site create / archive / migrate / restore | Barista Editor |
| Install/Uninstall app on a site         | Barista Editor  |
| Backup site                             | Barista Editor  |
| Slow query / Error log / Analytics view | Barista Editor  |
| Bin log view                            | Barista Admin   |
| Settings edit                           | Barista Admin   |
| Open Terminal (`docker exec`)           | Barista Admin   |

`require_barista_role(role)` raises `frappe.PermissionError` with a
clear message; the UI turns that into a toast.

## Container isolation

The control plane container **does not have `/var/run/docker.sock`**.
Only the `barista-docker-manager` container does. This is Barista's
single most important security decision: any process inside the
Barista bench (including arbitrary user-installed Frappe apps and
server scripts) is one network hop away from `docker-manager`, and
must clear:

- the **token** check (`X-Auth-Token`), and
- the **CIDR** check (source IP must be inside `barista-net`), and
- the **policy** check (image allowlist, mount allowlist, capability
  allowlist — see [09-docker-manager.md](09-docker-manager.md))

before it can do anything. There is no path from "Frappe Python code"
to "raw `dockerd` API call" — that's the whole point of the split.

Other isolations still apply:

- The agent worker is the *only* process in the control plane with
  `BARISTA_DOCKER_MANAGER_URL`/`_TOKEN` env vars set. The web worker
  and other queue workers don't have them, so the client raises on
  init if called from the wrong place. Enforced at supervisord
  program-env scope.
- The `docker-manager` container runs as a non-root user (`manager`,
  uid 1001). On Linux we strongly recommend Docker **rootless** —
  `install.sh` detects rootless and prefers it.
- Managed-bench containers run with `--security-opt no-new-privileges`,
  `--cap-drop ALL` plus only the caps a bench needs (`CHOWN, SETUID,
  SETGID, DAC_OVERRIDE`), and a tmpfs for `/tmp`. `docker-manager`'s
  `policy.py` rejects any caller-supplied request that tries to relax
  these.
- Managed benches **do not** have access to `docker.sock`, the
  manager's token, or the manager's IP allowlist (they're on
  `barista-net` but the manager refuses requests from non-Barista
  containers via an extra label check: requests must originate from a
  container labelled `barista.role=control-plane` or
  `barista.role=docker-manager-client`). A compromised user site
  cannot launch sibling containers.

## Secret management

Things Barista must store:

- MariaDB root password (in `~/.barista/.env`, mode 600).
- Docker-manager token (in `~/.barista/.env`, mode 600; mirrored
  into both containers' env at compose time).
- Per-site admin passwords (encrypted via Frappe's standard
  `frappe.utils.password.set_encrypted_password`).
- Per-site `service_token` (same).
- SSH private keys for private repos (same).
- TLS certs (managed entirely by Traefik; on disk under
  `~/.barista/data/traefik`, root-owned).

The docker-manager token can be rotated without downtime: write the
new value to `.env`, `docker compose up -d` the manager (picks up new
token), then `bench --site barista.localhost set-config
barista_docker_manager_token <new>` on the control plane and restart
the agent worker. Old token stops working as soon as the manager
restarts.

Things Barista must **not** store:

- User OS passwords.
- Backup contents (live on disk, not in the DB).
- Bin log contents (read-through only).

When a `Site` row is exported (REST export), the encrypted fields are
stripped — same as Frappe's default behaviour for `Password` fields.

## Audit

The `Bench Action` DocType *is* the audit log. Every privileged
operation creates one row, immutable from the UI. For tamper-evident
audit, the `creation`, `triggered_by`, `triggered_at` fields are
indexed and a daily scheduler task signs the day's rows into a single
HMAC stored in `Barista Settings.audit_chain_<YYYYMMDD>` — chained so
deleting old rows is detectable. (Optional: off by default; on for
serious self-hosted deployments via `--audit-chain` install flag.)

## Network exposure

- By default, **only Traefik's :80/:443** is reachable from the
  network. MariaDB is on `127.0.0.1:13306` only; Redis is on the
  Docker network only; bench HTTP ports are on `127.0.0.1:18xxx`
  only.
- This is enforced by docker-compose port bindings (`127.0.0.1:`
  prefix). The user can choose to publish `:13306` more widely; the
  spec doesn't.

## Login

Standard Frappe login on the `barista.localhost` site. Two-factor
auth is available because Barista relies entirely on Frappe's auth
(`frappe.auth`), so anything Frappe supports — LDAP, OAuth, OTP — is
available without extra code. The only Barista-specific addition is a
"first run, set the admin password" wizard described in
[06-install-and-bootstrap.md](06-install-and-bootstrap.md).

## Sensitive UI affordances

Two UI surfaces deserve extra friction:

1. **Open Terminal**: clicking it asks "Open root shell inside
   `bench-myproject`?" with a typed-confirmation if the bench has a
   production-flagged site on it. The websocket token expires in
   60 seconds and is single-use.
2. **Destroy bench**: requires typing the bench name (à la
   GitHub repo deletion).

## What this spec does *not* solve

- Multi-tenant isolation between Barista users sharing one host.
  Barista is a power-tool, not a SaaS platform. If you need that,
  you want Press.
- Hardware-level protection against a compromised root user on the
  host. Out of scope.
- Defending against the local OS user themselves; if you have a shell
  on the host you can already do everything Barista can. Barista's
  security model is about *protecting the host from managed sites*,
  not protecting the host user from themselves.
