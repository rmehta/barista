# 07 · Observability

This page covers the six observability features listed in the original
brief, with collector design for each.

| Feature             | Collector                                  | Storage                   | UI page          |
|---------------------|--------------------------------------------|---------------------------|------------------|
| System performance  | agent worker → `docker stats` / cgroups    | in-memory ring + chart    | Bench detail     |
| Background jobs     | proxied from managed site                  | none (live fetch)         | Site detail tab  |
| Error logs          | proxied + snapshot cache                   | `Error Log Snapshot`      | Site detail tab  |
| Web analytics       | JS shim → `/api/method/barista.analytics.collect` | `Web Analytics Event` | Site detail tab |
| Slow queries        | MariaDB slow log tail                      | `Slow Query Snapshot`     | Site detail tab  |
| Bin log browser     | `mysqlbinlog` parser on demand             | none (read-through)       | Top-level page   |

---

## 1. System performance

Every 5 seconds while at least one user has a relevant page open, the
agent worker calls `docker.containers.get(name).stats(stream=False)`
and computes:

```
cpu_pct  = (cpu_total - precpu_total) / (system_total - presystem_total)
            * online_cpus * 100
mem_mb   = memory_stats.usage / 1024 / 1024
io_r_mb  = blkio.read_bytes  / 1024 / 1024  (cumulative)
io_w_mb  = blkio.write_bytes / 1024 / 1024
```

Pushes `metrics:<bench>` realtime events.

In-memory ring buffer per bench (last 720 samples = 1 hour) lives in
Redis under `barista:metrics:<bench>` as a capped list. The agent
trims to length on every push. We do not persist to MariaDB — metrics
of older-than-1h granularity aren't a goal of Barista; if you need
that, point Prometheus at the same `docker stats` source (the spec
exposes a `/api/method/barista.metrics.prometheus` endpoint
returning OpenMetrics for exactly this reason).

**Host-level** metrics use `psutil` (already a Frappe dependency) and
publish on `metrics:__host__`.

## 2. Background jobs

We do not duplicate the queue. The Vue tab calls
`barista.api.observability.jobs(site, ...)` which proxies to the
target site's `frappe.utils.background_jobs.get_jobs`. Refresh
button + auto-refresh every 5s while tab is visible.

There is no "kill job" button. Killing RQ jobs requires write access
to the target site's Redis, which the agent has, but the UX for it is
gnarly (some jobs are uninterruptible). If users need this, the
escape hatch is "Open Terminal" on the bench → `bench --site <s>
delete-rq-job <id>`. We can add the button later when there's demand.

## 3. Error logs

Same proxy pattern. The snapshot table (`Error Log Snapshot`)
exists *only* to power the "Errors 24h" badge on the Sites list — we
don't want to make N proxy calls when rendering the list. A scheduler
event every 10 minutes calls `frappe.client.get_count` over
Bearer-auth on each site and writes one row.

The snapshot also records the top 5 method names by count, which
gives the Site Overview tab its little sparkline + "most common
errors" widget without proxy overhead.

Detail view (clicking a row) **does** make a proxy call to pull the
full traceback — that's fine because it's user-initiated and one row
at a time.

## 4. Web analytics

### Collector

A tiny JS shim, served from `/assets/barista/analytics.js`:

```js
(function() {
  if (navigator.doNotTrack === "1") return;
  if (window.__barista_analytics_loaded) return;
  window.__barista_analytics_loaded = true;

  function sid() {
    let s = sessionStorage.getItem('__barista_sid');
    if (!s) {
      s = crypto.randomUUID();
      sessionStorage.setItem('__barista_sid', s);
    }
    return s;
  }

  function send(extra) {
    navigator.sendBeacon('/api/method/barista.analytics.collect',
      JSON.stringify(Object.assign({
        path: location.pathname,
        referrer: document.referrer,
        sid: sid(),
      }, extra || {})));
  }

  send({ event: 'pageview' });
  window.addEventListener('hashchange', () => send({ event: 'hashchange' }));
})();
```

Injected by Barista into each managed site only when
`Site.web_analytics_enabled` is on. Injection mechanism: a small
`barista_agent` app inside the bench image registers a
`website_context` hook that appends a `<script src="...">` to the
base template. No edit to the user's templates.

### Endpoint

`barista.analytics.collect` is **whitelisted as `allow_guest=True`**
and lives *inside* the managed site (via the same `barista_agent`
app), where it writes to a local lightweight table. The control plane
pulls aggregated counts via the standard proxy path every 5 minutes,
*not* per request — so analytics don't depend on the control plane
being online.

Privacy:
- No IP storage. Country is derived from request IP at write time via
  a bundled GeoLite2-Country DB, then the IP is discarded.
- Session id is per browser tab session (`sessionStorage`), so it
  resets on tab close. We never set cookies.
- Honors `DNT`.
- A site admin can disable it from the Site detail form; the shim
  short-circuits on next page load.

### Aggregations

Computed at query time over the last N days (small data; this is a
single-host tool). For high-traffic sites the agent rolls daily
aggregates into a `Web Analytics Daily` child table to keep dashboards
snappy.

## 5. Slow queries

### Collector

MariaDB writes to `/var/log/mysql/slow.log`. The agent tails this
file (bind-mounted into the control-plane container at `/slow.log`):

```python
def slow_query_loop():
    for entry in tail_slow_log("/slow.log"):
        digest = normalise(entry.query)
        key = f"slowq:{entry.db}:{digest}:{today}"
        n = redis.incr(key)
        redis.expire(key, 24*3600)
        if n == 1:                # first occurrence today
            insert_snapshot(entry, digest)
        else:
            update_snapshot_count(entry.db, digest, today, n)
```

Normalisation strips literals and whitespace so
`SELECT * FROM t WHERE id = 7` and `SELECT  *  FROM t WHERE id=42`
share a digest. We hash that string with MD5 (cheap, collision-safe
for this use).

### EXPLAIN

The "Sample plan" panel runs `EXPLAIN` against the live database
**lazily**, only when the user opens the detail. We refuse to run it
on queries we can't safely re-parameterise (e.g. `INSERT ... SELECT`).

### Retention

Snapshots auto-purge after 7 days (DocType `Slow Query Snapshot` has a
scheduler cleanup). The raw slow log rotates via `logrotate` defined
in `docker-compose.yml` for the mariadb service.

## 6. Bin log browser

Enabled by `Barista Settings.binlog_enabled`. Toggling on:

1. Rewrites `my.cnf` to include `log_bin = /var/lib/mysql/binlog` and
   `binlog_format = ROW` (we need ROW for column-level diffs).
2. Restarts `barista-mariadb` (one container, ~5s downtime — clearly
   warned in the UI).

Reading:

```python
def list_binlog_events(start_pos=None, end_pos=None, db=None, limit=200):
    args = ["mysqlbinlog",
            "--read-from-remote-server",
            "--host=barista-mariadb",
            "--user=root", "--password=" + root_pw,
            "--base64-output=DECODE-ROWS", "--verbose",
            "--start-position=" + str(start_pos),
            "--stop-position=" + str(end_pos or "")]
    out = subprocess.run(args, capture_output=True, text=True, check=True)
    return parse_mysqlbinlog(out.stdout, db=db, limit=limit)
```

`parse_mysqlbinlog` returns structured rows:

```
{ "ts": "2026-05-20T14:21:09.412",
  "db": "myshop",
  "op": "UPDATE",
  "table": "tabSalesInvoice",
  "rows": 1,
  "statement": "UPDATE `tabSalesInvoice` SET ...",
  "before": { "grand_total": "100.00", ... },
  "after":  { "grand_total": "120.00", ... } }
```

The UI pages by `start_position` cursor — each row knows its position,
"Load more" sends the last one as the new start. No SQL `LIMIT`, no
risk of timeouts on huge logs.

### Safety

- Bin log access is restricted to users with the `Barista Admin`
  role (see [08-security-and-permissions.md](08-security-and-permissions.md)),
  because it can reveal *any* data ever written, including data the
  reader has no business with.
- The API never returns row values from databases the requesting user
  has no `Site` access to.
- Bin logs are auto-rotated; max age and max size are settings in
  `Barista Settings`. Default: 7 days, 5 GB.

## Per-feature flags

Every observability feature has an opt-out switch in `Barista
Settings`, and per-site enables for the data-plane ones:

| Setting                            | Default | Cost           |
|------------------------------------|---------|----------------|
| `enable_web_analytics`             | on      | small JS + table writes |
| `slow_query_threshold_ms`          | 500     | log volume     |
| `binlog_enabled`                   | off     | disk: ~10% of write volume |
| `metrics_polling_interval_s`       | 5       | CPU on host    |
| `error_log_snapshot_interval_min`  | 10      | proxy traffic  |
