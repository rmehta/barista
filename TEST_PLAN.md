# Test Plan

## Goals & scope

Cover the load-bearing behaviour:

- DocType validation (names, refs, cascades).
- API authorization (roles + DocType perms).
- Task scaffolding (Bench Action lifecycle, error capture).
- DockerManagerClient HTTP behaviour (with the real network mocked).
- Frontend mount + interaction smoke (Vitest + happy-dom).

Out of scope for v0.1:
- End-to-end with a real Docker daemon (covered manually + nightly job
  later).
- Observability collectors (placeholders in v0.1).
- Frontend visual regression.

## Test layers

### 1. Pure-Python unit tests (`barista/tests/unit/`)

Run as `pytest` against the package directly — no Frappe site needed.
Fast (< 2s), no I/O, no DB.

Cover:
- `dm_client.DockerManagerClient`
  - missing env → raises DockerManagerError
  - 4xx → raises with status + body
  - 5xx → raises
  - network error → raises
  - success → returns parsed JSON
- `permissions.require_admin / require_editor` with mocked
  `frappe.get_roles`.

### 2. Frappe unit tests (`barista/tests/test_*.py`)

Run as `bench --site test_site run-tests --app barista`. The Frappe
test runner spins up a real test site, runs migrations, then each
test class in a transaction it rolls back.

Cover:
- DocType validation:
  - Bench Spec without `frappe` → raises InvalidBenchSpec
  - Bench Spec duplicate apps → raises
  - Bench Host with invalid name → raises
  - Site invalid name → raises
  - Site control-plane deletion → blocked
  - Bench Host destroy with active sites → BenchInUseError
- Task base class:
  - enqueue_task creates a Bench Action row with the right fields
  - BaristaTask.execute marks Running → Success on happy path
  - BaristaTask.execute marks Failure on exception, captures error
- API:
  - bench.restart enqueues a job + returns bench_action name
  - bench.restart requires Barista Admin role
  - site.create creates Site row in Pending, returns action name
  - site.archive enqueues, requires Editor

### 3. Docker-manager tests (`docker-manager/tests/`)

Pytest against the Flask app via test client. Docker SDK is mocked.
Cover:
- `/v1/health` requires token
- Wrong token → 401
- IP outside allowlist → 403
- `POST /v1/benches` rejects images outside allowlist (policy.py)
- `POST /v1/benches` rejects mount paths outside `BARISTA_DATA_ROOT`
- `POST /v1/benches` rewrites 0.0.0.0 → 127.0.0.1 (port policy)
- `PUT /v1/routes` writes a YAML file atomically

### 4. Frontend tests (`dashboard/tests/`)

Vitest + @vue/test-utils + happy-dom. No browser.

Cover:
- BenchList renders empty state when no data
- BenchList renders rows when data is present
- NewBenchDialog: submit disabled until name and spec set
- StatusBadge: maps status → CSS classes for the obvious states

## CI matrix

GitHub Actions:

| Job | Trigger | Steps |
|---|---|---|
| `python-unit` | push, PR | setup-python 3.11 → `pip install -e .` + pytest → run `barista/tests/unit/` |
| `python-frappe`* | push, PR, scheduled | spin up Frappe, install barista, run `bench run-tests --app barista` |
| `docker-manager` | push, PR | setup-python 3.11 → `pip install -r docker-manager/requirements.txt` + pytest |
| `frontend` | push, PR | setup-node 20 → `yarn install` → `yarn build` → `yarn test` |
| `lint` | push, PR | ruff for Python, eslint optional |

`python-frappe` requires a MariaDB + Redis service and ~3 min of
boot. Initially scheduled only on `main` to keep PR cycles fast; we
can move it to every push once we trust it.

## How to run locally

```
# Pure unit tests
pip install -e ".[dev]"
pytest barista/tests/unit/

# Frappe site tests (assumes bench at $BENCH)
cd $BENCH
bench --site test_site run-tests --app barista

# Docker-manager
pytest docker-manager/tests/

# Frontend
cd dashboard
yarn install
yarn test
```

## Adding a new test

1. Decide which layer it belongs to (above).
2. Add the file in the matching folder.
3. CI picks it up automatically — no workflow edit needed.
