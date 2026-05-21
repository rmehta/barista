# 06 · Install & Bootstrap

## Goal

Two friendly entry points, each idempotent:

1. `curl -fsSL https://raw.githubusercontent.com/rmehta/barista/main/install.py | python3 -`
   on a fresh laptop or VPS — see [install.py](../install.py).
2. From an existing bench: `bench get-app barista && bench --site … install-app barista`
   for power users.

Both arrive at the same end state: one running `barista-bench-default`
container with the `barista.localhost` site initialised.

## Why Python (not bash)

The installer was originally a 600-line bash script. It got hard to
read and impossible to test. The Python version is:

- **Stdlib-only.** No `pip install` step; `curl ... | python3 -`
  works on any host with Python 3.9+. We shell out to the `docker`
  CLI instead of using the Docker SDK.
- **OO with small methods.** Each step is one method on `Installer`.
  Methods take no positional args (config lives on `self`) so tests
  can call any step in any order.
- **Pure where possible.** Every config file is rendered by a
  `Templates.<thing>(…)` function returning a string. The only
  impure bit is the one method that writes it. Same for command
  lines — `Docker.run(argv)` is the only seam, easy to mock.

## What `install.py` does

In order — but every step is **a function** gated by a "skip if
already done" marker, so re-running is safe.

```
 1.  preflight              — OS check, Docker presence, ports free, disk space
 2.  ensure_dirs            — ~/.barista/{data,config,backups,src,.state}
 3.  write_env              — generate ~/.barista/.env (passwords, tokens, ports), once
 4.  write_mariadb_conf     — slow-log enabled my.cnf
 5.  write_traefik_conf     — static + empty dynamic config
 6.  stage_docker_manager   — copy docker-manager/ source to ~/.barista/src
                              (or git clone the repo when running via curl|python3)
 7.  write_compose          — render ~/.barista/docker-compose.yml
 8.  compose_up             — build docker-manager image, pull mariadb/redis/traefik,
                              `up -d`, wait for MariaDB and docker-manager health
 9.  bootstrap_cp           — create the control-plane bench container (NO docker.sock!),
                              create barista.localhost site, install barista app,
                              register-control-plane (writes Bench Host & Site rows)
10.  print_summary          — print URL + admin password.
```

## Code shape

```python
# install.py — top-level classes
class Logger:      # pretty terminal output; falls back to plain on non-tty
class Config:      # CLI args + computed paths; built once
class Docker:      # thin wrapper around `docker` CLI; one mockable seam
class Templates:   # static methods returning config-file strings (testable)
class StepRunner:  # ordered steps + state-marker idempotency
class Installer:   # one method per step
```

`main()` builds a `Config` from `sys.argv`, constructs `Installer`,
hands its steps to a `StepRunner`, runs.

### `Config`

```python
@dataclass
class Config:
    mode: str = "install"          # install | uninstall | purge
    barista_home: Path = …          # ~/.barista by default
    repo: str = "https://github.com/rmehta/barista"
    branch: str = "main"
    domain: str = "<public-ip>.nip.io"  # falls back to barista.localhost
    email: str = ""
    port_start: int = 18000
    no_traefik: bool = False
    interactive: bool = False
    dry_run: bool = False
```

Derived paths (`env_file`, `compose_file`, `src_dir`, `state_dir`,
`data_dirs`) are properties — never strings hard-coded in two places.

### Generated `~/.barista/.env`

Written **once**, never overwritten. Contents:

```
BARISTA_VERSION=0.1.0
BARISTA_MARIADB_ROOT_PASSWORD=<32-byte hex>
BARISTA_ADMIN_PASSWORD=<24-byte hex>        # initial Barista admin
BARISTA_DOCKER_MANAGER_TOKEN=<32-byte hex>  # internal auth
BARISTA_TIMEZONE=Asia/Kolkata
BARISTA_HTTP_PORT_RANGE_START=18000
BARISTA_DOMAIN=<public-ip>.nip.io
BARISTA_LETSENCRYPT_EMAIL=
BARISTA_DOCKER_NETWORK=barista-net
```

`Templates.env_file(...)` returns this as a string. The installer
writes it with `chmod 600`.

### Generated `docker-compose.yml`

`Templates.compose_yml(home, network, no_traefik)` returns the YAML
text. Services: `mariadb`, `redis`, `docker-manager`, and `traefik`
(unless `--no-traefik`). `docker-manager` is explicitly published on
no host ports — it's reachable only via the `barista-net` Docker
network.

### Bootstrapping the control-plane bench

This is the only step that's a little magic — it has to create the
"first bench" without Barista being available yet to do it for us. So
the installer shells out to `docker run` directly, **once**:

```python
def bootstrap_cp(self):
    bench_dir = self.cfg.barista_home / "data" / "benches" / "default"
    if not (bench_dir / "sites").exists():
        self._init_bench(bench_dir)              # `bench init` in a throw-away container
        self._write_common_site_config(bench_dir / "sites")
    if not self.docker.container_running("barista-bench-default"):
        self._run_control_plane(bench_dir)       # the long-lived container
    if not self._app_present_in_bench():
        self._get_app()                          # `bench get-app barista`
    if not self._site_present():
        self._new_site()                         # `bench new-site barista.localhost`
        self._register_control_plane()           # writes Bench Host + Site rows
```

Note the per-step checks — each can be re-run after a failure and
will skip what's already been done.

The control-plane container is started with `--label
barista.role=control-plane` and Traefik labels for routing. **It does
NOT have `/var/run/docker.sock` bind-mounted** — that's the whole
point of the `barista-docker-manager` split (see
[09-docker-manager.md](09-docker-manager.md)).

## Default domain

If `--domain` is not passed the installer looks up the host's public
IPv4 (api.ipify.org and friends, 2-second timeout, fail-closed) and
defaults the domain to `<ip>.nip.io`. nip.io is a wildcard DNS
service that resolves any `<ip>.nip.io` back to `<ip>` — so the
install is reachable from the open web with zero DNS configuration.
If detection fails (offline, blocked egress, RFC 1918 behind NAT) we
fall back to `barista.localhost` and the install only works from the
host itself.

Override with `--domain shop.example.com` for a real DNS name. Add
`--email ops@example.com` to also enable Let's Encrypt — Traefik
will request a cert (works for both real domains and nip.io
subdomains).

## Flags `install.py` accepts

```
--domain <hostname>    override the auto-detected `<ip>.nip.io` default
--email  <addr>        Let's Encrypt contact email (enables HTTPS)
--port-start <n>       start of HTTP port range; default 18000
--no-traefik           skip traefik; you'll proxy in your own nginx/caddy
--interactive          prompt before destructive actions
--dry-run              print what would happen, do nothing
--repo <url>           override the source repo (for forks)
--branch <name>        override the source branch
--uninstall            stop containers, delete networks, leave data alone
--purge                ⚠ delete EVERYTHING under ~/.barista
```

`--uninstall` is the "I'm done playing" button; `--purge` requires a
typed `PURGE` confirmation when `--interactive` is on.

## First-run wizard (in the UI)

When the user opens `http://<public-ip>.nip.io/barista` (or whatever
`--domain` was set to) for the first
time, they hit a wizard backed by `Onboarding Status (Single)`:

```
┌─ Welcome to Barista ☕ ────────────────────────────────────────────────────┐
│                                                                            │
│  Step 1 — Sign in as your admin                                            │
│    email:    rmehta@…                                                      │
│    full name: Rushabh                                                      │
│    password: ●●●●●●●●●●                                                    │
│                                                                            │
│  Step 2 — Tell us about this host (optional)                               │
│    [x] Enable web analytics on new sites                                   │
│    [ ] Enable MariaDB binary logs (uses more disk)                         │
│                                                                            │
│  Step 3 — All set!                                                         │
│    You can now create more benches, add app sources, or just play          │
│    around in the existing default bench.                                   │
│                                                                            │
│                                                              [Get started] │
└────────────────────────────────────────────────────────────────────────────┘
```

The wizard never blocks — every step is skippable. Onboarding state is
on the single DocType so power-users can flip `completed = 1` from the
console without seeing the modal.

## Idempotency contract

- Running `install.py` again on a healthy machine prints "already
  done" for every step and exits 0.
- Running it after a failed install resumes at the first incomplete
  step. Each step writes a marker file in `~/.barista/.state/` on
  success.
- `bench --site barista.localhost migrate` works the standard way for
  Barista app upgrades; no special command needed.

## Testability

Because every step is a method on `Installer`, tests in
[`barista/tests/unit/test_install.py`](../barista/tests/unit/test_install.py)
can:

- Construct `Config` directly with a `tmp_path` as `barista_home`.
- Mock `Docker` so no daemon is needed.
- Monkeypatch `random_hex` for deterministic password generation.
- Call any single step and assert on the resulting files.
- Verify the step **order** as a stability test.

The test suite covers: argv parsing, every template's output shape,
every step's effects on disk, `StepRunner` semantics (order, markers,
skip-on-done, stop-on-failure), and `_parse_env_file`.

## Upgrading

```
python3 install.py    # convenience wrapper, idempotent
```

The control-plane bench is rebuilt the same way any other bench is —
via a `Bench Build` — so the upgrade path is exercised by everyday
use. No separate code path for "upgrading Barista itself."

## What if Docker isn't available?

`install.py` will offer to install it (with explicit confirmation) on
Linux via the official `get.docker.com` script. On macOS it points
the user at the Docker Desktop installer URL (we don't auto-install
Desktop because of licensing). If the user declines, the script exits
with a clear message.
