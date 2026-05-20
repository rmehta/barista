# 04 · API & Realtime

Barista exposes its work surface through three layers, in order of
preference:

1. **Standard Frappe REST** for everything that's just a DocType:
   `GET /api/resource/Bench%20Host`, `POST /api/resource/Bench%20Spec`,
   etc. The Vue app uses `createListResource` / `createDocumentResource`
   from `frappe-ui` directly against these endpoints. No custom API.
2. **Whitelisted methods** (`@frappe.whitelist()`) for actions that
   can't be a CRUD on a DocType — these enqueue work and return the
   `Bench Action` name so the UI can subscribe to it.
3. **Realtime events** (`frappe.publish_realtime` / `socket.io`) for
   live status, build/log tails, and metric tickers.

The rule: **anything that the user "owns" is a DocType; anything they
"do" is a method that creates a `Bench Action`.**

---

## Module layout

```
barista/
├── api/
│   ├── __init__.py
│   ├── bench.py          # bench actions
│   ├── site.py           # site actions
│   ├── apps.py           # marketplace-ish operations
│   ├── observability.py  # proxied logs, slow queries, analytics
│   └── terminal.py       # websocket endpoint for `docker exec`
└── tasks/
    ├── bench.py          # the privileged worker code (Docker SDK calls)
    ├── site.py
    ├── builds.py
    ├── backup.py
    └── observability.py
```

The split is deliberate: `api/` is **stateless**, runs in the web
worker, and never touches Docker. `tasks/` runs only on the
`barista-agent` queue and holds every privileged call.

---

## Whitelisted methods

### Bench

```python
barista.api.bench.create(spec: str, bench_name: str,
                         cpu_quota: float = 0, mem_limit_mb: int = 0)
    -> { "bench_action": "<name>", "bench": "<name>" }

barista.api.bench.start(bench: str)    -> { "bench_action": "<name>" }
barista.api.bench.stop(bench: str)     -> { "bench_action": "<name>" }
barista.api.bench.restart(bench: str)  -> { "bench_action": "<name>" }
barista.api.bench.rebuild(bench: str)  -> { "bench_action": "<name>" }   # triggers new build
barista.api.bench.destroy(bench: str)  -> { "bench_action": "<name>" }
barista.api.bench.exec_token(bench: str)
    -> { "token": "<one-shot>", "url": "wss://.../terminal/<token>" }
```

### Site

```python
barista.api.site.create(bench: str, site_name: str, admin_password: str,
                        apps: list[str], install_demo_data: bool = False)
    -> { "bench_action": "<name>", "site": "<name>" }

barista.api.site.archive(site: str)          # equivalent to bench drop-site
barista.api.site.unarchive(site: str)
barista.api.site.migrate(site: str)
barista.api.site.install_app(site: str, app: str)
barista.api.site.uninstall_app(site: str, app: str)
barista.api.site.set_admin_password(site: str, new_password: str)
barista.api.site.backup(site: str, with_files: bool = True)
barista.api.site.restore(site: str, backup: str)        # backup = Site Backup name
barista.api.site.clone(site: str, new_site_name: str, target_bench: str = None)
```

### Apps

```python
barista.api.apps.add_source(repository_url: str, branch: str = None,
                            is_private: bool = False)
    -> { "bench_app": "<name>" }

barista.api.apps.detect_version(repository_url: str, branch: str)
    -> { "python_min": "3.10", "node_min": "18", "frappe_branch": "version-15" }
```

### Observability (proxied)

```python
barista.api.observability.error_logs(site: str, since: str = None,
                                      limit: int = 50, search: str = None)
    -> [ { "name": "...", "method": "...", "error": "...", "creation": "..." }, ... ]

barista.api.observability.jobs(site: str, status: str = None, queue: str = None,
                                limit: int = 50)
    -> [ { "id": "...", "method": "...", "status": "...", "started": "..." }, ... ]

barista.api.observability.system_metrics(bench: str, range: str = "1h")
    -> {
         "cpu":     [ [ts, pct], ... ],
         "mem":     [ [ts, mb],  ... ],
         "io_read": [ [ts, mb],  ... ],
         "io_write":[ [ts, mb],  ... ]
       }

barista.api.observability.slow_queries(site: str, since: str = None, limit: int = 100)
barista.api.observability.binlog_events(since: str = None, limit: int = 200,
                                         db: str = None, op: str = None)
barista.api.observability.analytics_summary(site: str, range: str = "7d")
    -> {
         "pageviews":     [ [date, n], ... ],
         "unique_visitors":[ [date, n], ... ],
         "top_paths":     [ { "path": "/", "n": 123 }, ... ],
         "by_country":    [ { "country": "IN", "n": 87 }, ... ],
         "by_device":     { "Mobile": 41, "Desktop": 57, "Tablet": 2 }
       }
```

`error_logs` and `jobs` *proxy* the managed site rather than caching
its data locally. Implementation:

```python
def error_logs(site, since=None, limit=50, search=None):
    frappe.has_permission("Site", "read", site, throw=True)
    return _proxy_call(
        site,
        "frappe.client.get_list",
        doctype="Error Log",
        fields=["name", "method", "error", "creation"],
        filters=_build_filters(since, search),
        order_by="creation desc",
        limit_page_length=limit,
    )
```

`_proxy_call` runs **inside the agent worker** via
`docker exec barista-bench-<bench> bench --site <site> execute frappe.handler.execute_cmd ...`
or, faster, over the bench's nginx using a service-to-service token
stored in `Site.admin_password`'s sibling field `service_token`. The
spec leaves the implementation choice open; both are easy.

---

## Realtime channels

Subscribed by the Vue app via the same socket connection
`frappe-ui`'s `socket` helper already opens.

| Event                                | Payload                              | Emitted by |
|--------------------------------------|--------------------------------------|------------|
| `bench:<name>:status`                | `{ status, cpu_pct, mem_mb }`        | agent worker, every 15s + on change |
| `bench:<name>:log`                   | `{ stream: 'stdout', line: '...' }`  | agent worker tailing container logs |
| `build:<build_name>:log`             | `{ chunk: '...' }`                   | build job |
| `build:<build_name>:status`          | `{ status, duration_s }`             | build job |
| `site:<name>:status`                 | `{ status, message }`                | site jobs |
| `action:<bench_action>`              | `{ status, log_tail, error }`        | every privileged task |
| `metrics:<bench>`                    | `{ ts, cpu, mem, io_r, io_w }`       | sampler, every 5s while page is open |

The frontend convention: a list view subscribes to
`*:<name>:status` for all visible rows, a detail page also subscribes to
`*:<name>:log`. Disconnect on unmount.

---

## Job pattern

Every privileged task follows the same template:

```python
@frappe.whitelist()
def restart(bench: str):
    frappe.has_permission("Bench Host", "write", bench, throw=True)

    action = frappe.get_doc({
        "doctype": "Bench Action",
        "target_type": "Bench Host",
        "target": bench,
        "action": "Restart",
        "status": "Queued",
    }).insert()

    frappe.enqueue(
        "barista.tasks.bench.restart",
        queue="barista-agent",
        job_name=f"restart-{bench}",
        bench_action=action.name,
    )
    return {"bench_action": action.name}
```

```python
# barista/tasks/bench.py
def restart(bench_action: str):
    action = frappe.get_doc("Bench Action", bench_action)
    action.status = "Running"
    action.save()
    try:
        client = docker.from_env()
        container = client.containers.get(f"barista-bench-{action.target}")
        container.restart()
        action.status = "Success"
    except Exception as e:
        action.status = "Failure"
        action.error = str(e)
        frappe.log_error(title="bench.restart", message=str(e))
    finally:
        action.save()
        frappe.publish_realtime(f"action:{action.name}", action.as_dict())
```

This template is identical for `start`, `stop`, `destroy`, etc., so the
codebase converges on ~10 short functions rather than 10 bespoke
flows.

---

## Authentication for the proxied calls

The control plane has to call managed sites' APIs without storing user
passwords. Approach:

1. At site creation, Barista generates a long random string and stores
   it on `Site.service_token`.
2. Inside the site, Barista installs (via a tiny `barista_agent` app
   that the bench image always carries — separate from the user-visible
   Barista app) an `API Key` rule that accepts this token as a Bearer
   header for a fixed allowlist of methods:
   `frappe.client.get_list` (read-only), `frappe.utils.background_jobs.get_jobs`,
   `frappe.client.get_count` on `Error Log`, and that's it.
3. Outbound calls use this token. **Never** the admin password.

Token rotation is a `Site` form action that regenerates and re-pushes
the agent config.

---

## Backwards compatibility

Barista does not promise API stability across major versions. The Vue
app pins to a server version (read at boot from
`/api/method/barista.api.version`) and refuses to load against a
mismatched server.
