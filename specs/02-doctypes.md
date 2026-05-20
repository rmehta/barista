# 02 · DocTypes

All Barista state is in the `barista.localhost` site's database. Every
DocType below lives in module `Barista`. Conventions:

- Fieldnames use `snake_case`.
- `autoname` is given explicitly. Prefer human-readable names where the
  user picks them (Bench Host, Site), and `hash` for ephemeral records
  (Bench Action, Site Backup).
- `Link` fields are listed with the target DocType in parentheses.
- Where helpful, child tables are listed inline as `→ Child:`.
- Standard Frappe permission model: list view, form view, REST, all
  free.

---

## 1. Bench Spec

A reusable recipe for a bench. "ERPNext v15 with HRMS and India
Compliance, Python 3.11, Node 18." Many bench hosts can be built from
one spec; many builds can target one spec.

| Field | Type | Notes |
|---|---|---|
| spec_name        | Data, unique, required | `autoname: field:spec_name` |
| description      | Small Text |  |
| python_version   | Select: 3.10, 3.11, 3.12 | default 3.11 |
| node_version     | Select: 18, 20, 22       | default 20 |
| frappe_branch    | Data | default `version-15` |
| base_image       | Data | default `ghcr.io/frappe/bench-base:python3.11-node20` |
| apps             | Table → **Bench Spec App** |  |
| build_status     | Select: Never built, Built, Outdated | computed, read-only |
| latest_image     | Data | `barista/bench-<spec_name>:<short_sha>` |

### Bench Spec App (child)

| Field | Type | Notes |
|---|---|---|
| app_name   | Data, required          | `frappe`, `erpnext`, `hrms`, ... |
| source     | Link (Bench App)        |  |
| branch     | Data                    | overrides source's default |
| idx        | Int                     | install order (`frappe` is always first) |

---

## 2. Bench App

A *source* — i.e. "the thing you might `bench get-app` someday." Pre-seeded
with the common Frappe apps; users add more.

| Field | Type | Notes |
|---|---|---|
| app_name      | Data, required, unique | `autoname: field:app_name` |
| title         | Data | "ERPNext" |
| repository_url| Data, required | `https://github.com/frappe/erpnext` |
| default_branch| Data | `version-15` |
| is_private    | Check |  |
| ssh_key       | Link (Barista SSH Key) | optional, for private repos |
| icon_url      | Data |  |
| description   | Small Text |  |

---

## 3. Bench Host

A live Docker container running a bench. Created from a Bench Spec via
a Bench Build.

| Field | Type | Notes |
|---|---|---|
| bench_name     | Data, unique, required | `autoname: field:bench_name`, validated against `^[a-z][a-z0-9-]{1,30}$` |
| spec           | Link (Bench Spec), required |  |
| current_build  | Link (Bench Build) | image actually running |
| status         | Select: Pending, Building, Starting, Running, Stopped, Errored | computed from Docker |
| container_id   | Data | short SHA |
| http_port      | Int | host-side bound port; auto-allocated from 18000+ |
| ssh_port       | Int | for `docker exec`-equivalent terminal access via UI |
| created_on     | Datetime |  |
| started_at     | Datetime |  |
| cpu_quota      | Float | cores; 0 = no limit |
| mem_limit_mb   | Int   | 0 = no limit |
| host_path      | Data  | e.g. `~/.barista/data/benches/myproject` |

Hooks:
- `before_delete`: refuse if there are sites with `status != "Archived"`.
- On `status` change: `frappe.publish_realtime("bench:" + name + ":status", ...)`.

---

## 4. Bench Build

One image build event. Like Press's `Deploy Candidate`.

| Field | Type | Notes |
|---|---|---|
| name           | autoname `hash` |  |
| spec           | Link (Bench Spec), required |  |
| status         | Select: Pending, Running, Success, Failure, Cancelled |  |
| started_at     | Datetime |  |
| finished_at    | Datetime |  |
| duration_s     | Int |  |
| image_tag      | Data | `barista/bench-myproject:abc1234` |
| dockerfile     | Code, language=Dockerfile | rendered Dockerfile, kept for reproducibility |
| build_log      | Code, language=Shell | streamed log, capped at 5 MB |
| triggered_by   | Link (User) |  |

The build log streams via `publish_realtime("build:<name>:log", chunk)`
so the UI can tail it.

---

## 5. Site

A Frappe site on a Bench Host. The Barista site itself is one of these
rows (with `is_control_plane = 1`, hidden from default list filters).

| Field | Type | Notes |
|---|---|---|
| site_name        | Data, unique, required | e.g. `myshop.localhost` — `autoname: field:site_name` |
| bench            | Link (Bench Host), required |  |
| status           | Select: Pending, Active, Migrating, Broken, Archived |  |
| admin_password   | Password | encrypted via Frappe's standard `Password` field |
| db_name          | Data | derived: first 16 chars of sha256(site_name) |
| installed_apps   | Table → **Site App** |  |
| created_on       | Datetime |  |
| is_control_plane | Check, read-only |  |
| backup_schedule  | Select: None, Daily, Weekly | default Daily |
| domains          | Table → **Site Domain** | for non-`*.localhost` setups |

### Site App (child)

| Field | Type |
|---|---|
| app_name | Link (Bench App) |
| installed_on | Datetime |
| version | Data |

### Site Domain (child)

| Field | Type | Notes |
|---|---|---|
| domain | Data | e.g. `crm.example.com` |
| tls    | Check | Barista will request a Let's Encrypt cert |
| status | Select: Pending, Active, Failed |  |

---

## 6. Site Backup

| Field | Type | Notes |
|---|---|---|
| name        | autoname `hash` |  |
| site        | Link (Site), required |  |
| type        | Select: Manual, Scheduled, Pre-migration |  |
| with_files  | Check | files & private files included |
| status      | Select: Running, Success, Failure |  |
| size_mb     | Float |  |
| path        | Data | `~/.barista/backups/<site>/<ts>.tar.gz` |
| started_at  | Datetime |  |
| finished_at | Datetime |  |

---

## 7. Bench Action

The audit trail. Every container-touching operation creates one row.

| Field | Type | Notes |
|---|---|---|
| name         | autoname `hash` |  |
| target_type  | Select: Bench Host, Site, Bench Build |  |
| target       | Dynamic Link (target_type) |  |
| action       | Select: Create, Start, Stop, Restart, Destroy, Install App, Migrate, Backup, Restore, Update |  |
| status       | Select: Queued, Running, Success, Failure, Cancelled |  |
| triggered_by | Link (User) | defaults to `frappe.session.user` |
| triggered_at | Datetime | auto |
| duration_s   | Int |  |
| log          | Code | command output |
| error        | Text | only set on Failure |

`Bench Action` is read-only via the UI — created and updated only by
the queue worker. It is the "did this really run?" log every admin
reaches for first.

---

## 8. Background Job (proxied)

We do **not** create a separate DocType for jobs of remote benches.
Instead, Barista uses the existing **`RQ Job`** DocType (Frappe core)
for jobs on the *control-plane* site, and renders jobs of *managed*
sites by calling that site's `/api/method/frappe.utils.background_jobs.get_jobs`
through a thin proxy. See [04-api-and-realtime.md](04-api-and-realtime.md).

---

## 9. Error Log Snapshot

We also proxy **`Error Log`** from managed sites rather than duplicating
the rows. To keep things fast we cache a 24h rolling count per site in:

| Field | Type | Notes |
|---|---|---|
| site            | Link (Site) |  |
| date            | Date |  |
| error_count     | Int |  |
| top_methods     | JSON | `[{"method": "...", "count": 12}, ...]` |

Refreshed by a scheduler entry every 10 minutes.

---

## 10. Slow Query Snapshot

| Field | Type | Notes |
|---|---|---|
| site            | Link (Site) |  |
| captured_at     | Datetime |  |
| duration_ms     | Float |  |
| rows_examined   | Int |  |
| query_digest    | Data | normalised MD5 (à la `pt-query-digest`) |
| query           | Long Text | first occurrence, truncated to 4 KB |
| user            | Data |  |
| sample_count    | Int | how many times this digest fired in window |

Source: MariaDB's slow log; read by the agent worker once a minute,
deduplicated by digest. Auto-purge after 7 days.

---

## 11. Web Analytics Event

A lightweight pageview store, populated by a small JS shim that
Barista injects into managed sites' web pages (opt-in per site).

| Field | Type |
|---|---|
| site            | Link (Site) |
| path            | Data |
| referrer        | Data |
| user_agent_kind | Select: Mobile, Tablet, Desktop, Bot |
| country         | Data |
| occurred_at     | Datetime |
| session_id      | Data | rotating, hashed, no PII |

Aggregations are computed on the fly (see [07-observability.md](07-observability.md)).

---

## 12. Barista Settings (Single)

Site-wide config.

| Field | Type | Default | Notes |
|---|---|---|---|
| docker_host           | Data | `unix:///var/run/docker.sock` |  |
| default_python        | Select | 3.11 |  |
| default_node          | Select | 20 |  |
| http_port_range_start | Int | 18000 |  |
| backup_retention_days | Int | 14 |  |
| enable_web_analytics  | Check | 1 | adds the JS shim to managed sites |
| slow_query_threshold_ms | Int | 500 |  |
| binlog_enabled        | Check | 0 | turning on enables MariaDB `--log-bin` and the bin log browser |
| max_concurrent_builds | Int | 2 |  |

---

## 13. Barista SSH Key

For pulling private app repos. Stored encrypted using `frappe.utils.password`.

| Field | Type |
|---|---|
| key_name      | Data, unique |
| private_key   | Password |
| public_key    | Code |
| created_on    | Datetime |

---

## Relationships at a glance

```
Bench Spec ───┐
              ├──< Bench Build >── Bench Host ──< Site ──< Site Backup
Bench App ────┘                        │
                                       └──< Bench Action

                Site ──< Slow Query Snapshot
                Site ──< Error Log Snapshot
                Site ──< Web Analytics Event
```

All `Link` deletions use `ondelete=Restrict` except `Bench Action`,
`Site Backup`, `Slow Query Snapshot`, `Error Log Snapshot`, and `Web
Analytics Event`, which `Cascade` so destroying a site cleans its
observability data.
