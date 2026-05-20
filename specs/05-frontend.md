# 05 · Frontend (Frappe-UI SPA)

A single Vue 3 SPA, mounted at `/barista`, built with Vite, using only
components from the public **frappe-ui** package. No custom UI kit.

## Tech choices

- **Vue 3 + Composition API**, `<script setup>`
- **frappe-ui** (`Button`, `ListView`, `Dialog`, `TabButtons`, `Tabs`,
  `Charts`, `FormControl`, `Autocomplete`, `Switch`, `Badge`,
  `Breadcrumbs`, `CommandPalette`, `Tree`, `LoadingIndicator`,
  `ListFilter`, `Toast`, `Tooltip`, `Dropdown`, `Avatar`,
  `Resource`)
- **Pinia** for cross-page state (current bench filter, theme).
- **vue-router** in history mode, base = `/barista`.
- **createResource / createListResource** from frappe-ui for every
  data call. No fetch-by-hand.
- **Tailwind** via frappe-ui's preset, plus a thin
  `tailwind.config.js` for the brand color.
- **Charts** via frappe-ui's wrapping of Frappe Charts; no Chart.js.

The hosting strategy: Vite builds into `barista/public/dist/`,
`hooks.py` declares `app_include_js = "/assets/barista/dist/index.js"`,
and `barista/www/barista.html` mounts the app under `/barista`. The
`/barista` path is registered as an SPA fallback in `hooks.py`'s
`website_route_rules`.

## Brand

- Logo: a stylised coffee cup (Barista, get it). One SVG; lives in
  `barista/public/icons/barista.svg`.
- Primary accent: `#7c3aed` (violet). Everything else is the default
  frappe-ui neutral.
- Dark mode honoured via frappe-ui's `<Provider :theme="...">`.

## Routes

```
/barista/                          Dashboard (overview)
/barista/benches                   ListView of Bench Hosts
/barista/benches/new               Wizard
/barista/benches/:name             Bench detail (tabs)
/barista/benches/:name/terminal    xterm.js over websocket
/barista/specs                     Bench Specs
/barista/specs/:name               Bench Spec detail (with build history)
/barista/apps                      Bench App sources (marketplace-ish)
/barista/sites                     All sites across benches
/barista/sites/:name               Site detail (tabs)
/barista/sites/:name/backups       Backups list + restore
/barista/sites/:name/analytics     Web analytics
/barista/sites/:name/errors        Error Log proxy
/barista/sites/:name/jobs          Background jobs proxy
/barista/sites/:name/slow-queries  Slow queries
/barista/binlog                    Bin log browser (site-wide)
/barista/audit                     Bench Action audit trail
/barista/settings                  Single doc form
```

Every route uses `<Breadcrumbs>` at the top and `<CommandPalette>`
(bound to `cmd+k` / `ctrl+k`) for global navigation: type "site shop"
and jump.

## Wireframes

ASCII because they survive copy/paste, render anywhere, and are easy
to diff. A designer will redo these in Figma; engineering can build
from these.

### 1. Dashboard (`/barista/`)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ☕ Barista        ⌘K Search …                          🌙   rmehta@…  ▾    │
├──────────────┬──────────────────────────────────────────────────────────────┤
│              │  Home / Dashboard                                            │
│  ⌂ Dashboard │                                                              │
│  ◧ Benches   │  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐      │
│  ▤ Sites     │  │ Benches       │ │ Sites         │ │ Running jobs  │      │
│  ◇ Specs     │  │ 3   running   │ │ 7   active    │ │ 2             │      │
│  ⌂ Apps      │  │ 1   stopped   │ │ 1   broken    │ │ 19  last hour │      │
│  📈 Analytics│  └───────────────┘ └───────────────┘ └───────────────┘      │
│  ⚠ Errors    │                                                              │
│  ⛁ Bin Log   │  Host load (last hour)                                       │
│  ☷ Audit     │  ┌──────────────────────────────────────────────────────┐  │
│  ⚙ Settings  │  │ CPU  ▁▂▃▅▆▇▇▆▅▃▂▁▁▂▃▄▅▆▆▅▄▃▂▁▁▂  47%               │  │
│              │  │ MEM  ▃▃▄▄▄▅▅▅▅▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆  3.2 / 8 GB         │  │
│              │  │ DISK ████░░░░░░░░░░░░░░░░░░░░░░░  18 / 100 GB        │  │
│              │  └──────────────────────────────────────────────────────┘  │
│              │                                                              │
│              │  Recent activity                                             │
│              │  ┌──────────────────────────────────────────────────────┐  │
│              │  │ ✓  Restart    bench-myproject       Rushabh   12s    │  │
│              │  │ ✓  Backup     myshop.localhost      system    2m     │  │
│              │  │ ●  Build      erpnext-v15 #ab12c34  Rushabh   5m     │  │
│              │  │ ✗  Install    erpnext on dev.local  Rushabh   12m    │  │
│              │  └──────────────────────────────────────────────────────┘  │
│              │                                                              │
└──────────────┴──────────────────────────────────────────────────────────────┘
```

Implementation notes:
- Top stat cards = three `<Card>` components, data via three
  `createResource` calls.
- Host load chart = frappe-ui `<LineChart>` from `system_metrics(bench='__host__')`.
- Recent activity = `<ListView>` over `Bench Action` filtered to
  `triggered_at >= now - 1h`. Subscribes to `action:*` realtime.

### 2. Benches list (`/barista/benches`)

```
┌─ Benches ──────────────────────────────────────────────────  + New Bench ──┐
│ [ filter: status ▾ ] [ filter: spec ▾ ]                                    │
├───────────────────────────────────────────────────────────────────────────┤
│ Name              Spec               Sites  Status      CPU   Mem   ⋯     │
├───────────────────────────────────────────────────────────────────────────┤
│ default           barista-cp          1      ● Running   3%   412M  ⋯     │
│ myproject         erpnext-v15         3      ● Running   12%  1.4G  ⋯     │
│ erpnext-v15-test  erpnext-v15         2      ● Running   8%   980M  ⋯     │
│ scratch           framework-v15       0      ○ Stopped   —    —     ⋯     │
└───────────────────────────────────────────────────────────────────────────┘
```

Implementation:
- `<ListView>` bound to `createListResource({ doctype: 'Bench Host', ...})`.
- `Status`, `CPU`, `Mem` are live via `bench:<name>:status` realtime
  events: the row component subscribes for the names it can see.
- `⋯` opens a `<Dropdown>` with Start / Stop / Restart / Rebuild /
  Open Terminal / Destroy. Destructive items are red and behind a
  `<ConfirmDialog>`.

### 3. New Bench wizard (`/barista/benches/new`)

```
┌─ New Bench ───────────────────────────────────────────────────────────────┐
│  Step 1 of 3 — Pick a spec                                                │
│                                                                           │
│  ◉ erpnext-v15      Frappe, ERPNext, HRMS · Py 3.11 · Node 20             │
│  ○ framework-v15    Frappe only · Py 3.11 · Node 20                       │
│  ○ builder          Frappe, Builder · Py 3.11 · Node 20                   │
│  ○ ── New spec ──   Create a new spec from scratch                        │
│                                                                           │
│                                                            [Cancel] [Next]│
└───────────────────────────────────────────────────────────────────────────┘
```

Step 2 collects `bench_name` (validated live against the same regex
the server uses) and limits (CPU/Mem sliders).

Step 3 is a confirm screen showing the rendered Dockerfile (collapsed
by default) and the action plan: "Will build image, create container,
start nginx, write nginx routes."

On submit:
- `barista.api.bench.create(...)` returns a `bench_action`.
- We push to `/barista/benches/<name>` and show a banner subscribed to
  `action:<name>` until it's `Success` or `Failure`.

### 4. Bench detail (`/barista/benches/myproject`)

```
┌─ myproject  ● Running                              [Stop] [Restart] [⋯] ──┐
│ Breadcrumbs:  Benches / myproject                                          │
│                                                                            │
│ Tabs: [ Overview ] [ Sites ] [ Apps ] [ Builds ] [ Logs ] [ Resources ]   │
│                                                                            │
│  Overview                                                                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                       │
│  │ CPU  12%     │ │ Mem  1.4 GB  │ │ Sites  3     │                       │
│  └──────────────┘ └──────────────┘ └──────────────┘                       │
│                                                                            │
│  Live CPU / Mem (60s)                                                      │
│  ┌──────────────────────────────────────────────────────────────┐         │
│  │ ▁▂▃▅▆▇▇▆▅▃▂▁▁▂▃▄▅▆▆▅▄▃▂▁▁▂▃▅▆▇▇▆▅▃▂▁▁▂▃▄▅▆▆▅▄▃▂▁▁▂          │         │
│  └──────────────────────────────────────────────────────────────┘         │
│                                                                            │
│  Container                                                                 │
│   image:   barista/bench-erpnext-v15:ab12c34                              │
│   id:      d3f8e1c9...                                                    │
│   host:    127.0.0.1:18004    →   open in browser ↗                       │
│   created: 2 days ago                                                     │
│   limits:  CPU 4 cores · Mem 4 GB                       [Edit limits …]   │
└────────────────────────────────────────────────────────────────────────────┘
```

`Logs` tab is a tail of `docker logs --since=<n>` plus a live stream
via `bench:<name>:log`. Search box filters lines client-side.

### 5. Sites list (`/barista/sites`)

```
┌─ Sites ──────────────────────────────────────────────────  + New Site ─────┐
│ filters: [ bench: any ▾ ] [ status: any ▾ ]   search: ____________________ │
├────────────────────────────────────────────────────────────────────────────┤
│ Name                  Bench         Apps              Backups   Errors 24h │
├────────────────────────────────────────────────────────────────────────────┤
│ barista.localhost     default       frappe, barista   42        0          │
│ myshop.localhost      myproject     frappe, erpnext   12        3 ⚠        │
│ dev.local             myproject     frappe, hrms      0         11 ⚠⚠     │
│ analytics.test        myproject     frappe            5         0          │
└────────────────────────────────────────────────────────────────────────────┘
```

The `Errors 24h` column uses `Error Log Snapshot` for the count (no
per-row proxy call). Click → site detail.

### 6. Site detail tabs

```
┌─ myshop.localhost  ● Active                              [Backup] [⋯] ────┐
│ Tabs: [Overview] [Apps] [Backups] [Analytics] [Errors] [Jobs] [Slow Q] [Domains]│
│                                                                            │
│  Overview                                                                  │
│  - bench       : myproject                                                 │
│  - created     : 12 Mar 2026                                              │
│  - admin user  : Administrator             [Reset password]               │
│  - DB size     : 412 MB                                                   │
│  - files       : 87 MB                                                    │
│                                                                            │
│  Last 7 days                                                              │
│   pageviews ▆▅▄▃▄▅▇    errors ▁▁▂▁▁▃▁    slow queries ▁▂▃▂▁▄▂            │
│                                                                            │
│  Open ↗   https://myshop.localhost                                        │
└────────────────────────────────────────────────────────────────────────────┘
```

### 7. Analytics tab

```
┌─ Analytics — myshop.localhost ────────────────────────────────────────────┐
│ range: [ 24h ] [ 7d ●] [ 30d ] [ custom… ]                                 │
│                                                                            │
│  Pageviews                            Unique visitors                      │
│  ┌──────────────────────────┐         ┌──────────────────────────┐        │
│  │ ▂▃▄▅▆▇▇▆▅▄▃▂▃▄▅▆▇▆▅▄▃▂  │         │ ▁▂▂▃▃▄▄▄▃▃▂▂▃▃▄▄▅▅▄▄▃▃▂ │        │
│  │ 12,403                   │         │ 2,711                    │        │
│  └──────────────────────────┘         └──────────────────────────┘        │
│                                                                            │
│  Top paths                   By device                  By country         │
│  /                  4 102    Mobile   ▇▇▇▇▇▇▇▇  41%    IN     1,820 ▇▇   │
│  /products          1 873    Desktop  ▇▇▇▇▇▇▇▇▇▇ 57%   US       412 ▇    │
│  /products/widget     902    Tablet   ▇          2%    DE        88 ▏    │
│  /cart                641                                                  │
│  /login               503                                                  │
└────────────────────────────────────────────────────────────────────────────┘
```

Charts: frappe-ui `<LineChart>` and `<BarChart>`. Data from
`barista.api.observability.analytics_summary`. Tables are plain
`<ListView>` in "compact" mode (no checkboxes).

### 8. Errors tab — proxied Error Log

```
┌─ Errors — myshop.localhost ───────────────────────────────────────────────┐
│ search: ___________________   filter: [ last 24h ▾ ]                       │
├────────────────────────────────────────────────────────────────────────────┤
│ Time      Method                                       Snippet             │
├────────────────────────────────────────────────────────────────────────────┤
│ 14:21:09  erpnext.controllers.taxes.calculate          TypeError: 'NoneType│
│ 13:55:03  frappe.email.queue.send                      smtplib.SMTPAuthErr│
│ 13:22:51  myshop.api.checkout.charge                   stripe.error.Card…│
│ …                                                                          │
└────────────────────────────────────────────────────────────────────────────┘
```

Click a row → full traceback in a side `<Dialog>` (frappe-ui `Drawer`
style). No editing; this is a viewer.

### 9. Jobs tab — proxied background jobs

```
┌─ Background Jobs — myshop.localhost ──────────────────────────────────────┐
│ queue: [ all ▾ ]  status: [ any ▾ ]                            [Refresh] │
├────────────────────────────────────────────────────────────────────────────┤
│ ID        Method                          Queue    Status    Took    Started│
├────────────────────────────────────────────────────────────────────────────┤
│ a3f0…     frappe.email.queue.flush         default   running   —      14:21 │
│ d211…     erpnext.stock.utils.update_bin   long      queued    —      14:21 │
│ 7c8e…     frappe.utils.background_jobs.…   default   finished  0.4s   14:20 │
└────────────────────────────────────────────────────────────────────────────┘
```

### 10. Slow Queries tab

```
┌─ Slow queries — myshop.localhost ─────────────────────────────────────────┐
│ threshold: 500ms     range: 24h        [ refresh ]                         │
├────────────────────────────────────────────────────────────────────────────┤
│ ✕ 24    1.8s avg    SELECT … FROM `tabSales Invoice` WHERE … `customer` = ?│
│ ✕ 11    1.2s avg    SELECT … FROM `tabItem` JOIN `tabBin` …               │
│ ✕  6    910ms avg   UPDATE `tabStock Ledger Entry` SET …                  │
└────────────────────────────────────────────────────────────────────────────┘

Click a row →
┌─ Slow query a3c1… ───────────────────────────────────────────────────────┐
│ Digest: a3c1f...                                                          │
│ Occurrences (24h): 24    avg: 1.8s    p95: 3.1s    rows examined: 41,902 │
│                                                                           │
│ SELECT `name`, `customer`, `grand_total`                                  │
│ FROM `tabSales Invoice`                                                   │
│ WHERE `customer` = ?  AND `docstatus` = 1                                 │
│ ORDER BY `posting_date` DESC                                              │
│                                                                           │
│ Sample plan (EXPLAIN):                                                    │
│ id  select_type  type   key                rows                           │
│ 1   SIMPLE       ALL    NULL               41 902                         │
│                                                                           │
│ Suggested:  CREATE INDEX `tabSales Invoice` (`customer`, `posting_date`)  │
└───────────────────────────────────────────────────────────────────────────┘
```

The "Suggested index" is best-effort static heuristics on the query
plan; explicitly flagged "experimental".

### 11. Bin Log Browser (`/barista/binlog`)

Available only when `Barista Settings.binlog_enabled` is on. Streams
events using `mysqlbinlog --read-from-remote-server`-style parsing
done in the worker, returning structured rows.

```
┌─ Bin log browser ─────────────────────────────────────────────────────────┐
│ db: [ any ▾ ]  op: [ any ▾ ]  range: [ last 1h ]   search: _______________│
├────────────────────────────────────────────────────────────────────────────┤
│ Time           DB              Op      Table             Rows  Statement   │
├────────────────────────────────────────────────────────────────────────────┤
│ 14:21:09.412   myshop          UPDATE  tabSalesInvoice    1    UPDATE `tab│
│ 14:21:09.401   myshop          INSERT  tabGLEntry         3    INSERT INTO│
│ 14:21:08.997   dev_local       UPDATE  tabUser            1    UPDATE `tab│
└────────────────────────────────────────────────────────────────────────────┘
```

Click → expanded panel with the full statement and, for row events,
before/after column values rendered as a diff.

> ⚠ Bin logs are large. The UI fetches paginated chunks via cursor;
> the worker uses `--start-position` / `--stop-position` to avoid
> reading the whole log. Streaming pause/resume in the UI.

### 12. Audit trail (`/barista/audit`)

```
┌─ Audit ───────────────────────────────────────────────────────────────────┐
│ filters: action ▾   target type ▾   user ▾   status ▾    range: 24h ▾    │
├────────────────────────────────────────────────────────────────────────────┤
│ 14:21:09  ✓ Backup       Site         myshop.localhost   system   2.4s    │
│ 14:18:33  ✓ Restart      Bench Host   myproject          rmehta@…  1.2s   │
│ 14:17:01  ✗ Install App  Site         dev.local          rmehta@…  —     │
│ …                                                                          │
└────────────────────────────────────────────────────────────────────────────┘
```

Plain `<ListView>` on `Bench Action`. Detail dialog shows log + error.

### 13. Command palette (`cmd+k`)

```
┌─ ⌘K ──────────────────────────────────────────────────────────────────────┐
│ ❯ shop                                                                    │
│                                                                           │
│ Sites      myshop.localhost                                               │
│ Sites      shop-demo.localhost                                            │
│ Action     ▸ Backup site myshop.localhost                                 │
│ Action     ▸ Open myshop.localhost in browser                             │
│ Page       Analytics for myshop.localhost                                 │
└───────────────────────────────────────────────────────────────────────────┘
```

`<CommandPalette>` is fed by a small registry that combines: every
`Site` and `Bench Host` name, plus a fixed list of actions per kind.

## File layout

```
barista/public/
├── icons/barista.svg
└── dist/                ← Vite output
barista/barista_ui/      ← Vue source
├── src/
│   ├── main.js
│   ├── router.js
│   ├── App.vue
│   ├── pages/
│   │   ├── Dashboard.vue
│   │   ├── BenchList.vue
│   │   ├── BenchNew.vue
│   │   ├── BenchDetail.vue
│   │   ├── BenchTerminal.vue
│   │   ├── SiteList.vue
│   │   ├── SiteDetail/
│   │   │   ├── index.vue
│   │   │   ├── Overview.vue
│   │   │   ├── Apps.vue
│   │   │   ├── Backups.vue
│   │   │   ├── Analytics.vue
│   │   │   ├── Errors.vue
│   │   │   ├── Jobs.vue
│   │   │   ├── SlowQueries.vue
│   │   │   └── Domains.vue
│   │   ├── BinLog.vue
│   │   ├── Audit.vue
│   │   └── Settings.vue
│   ├── composables/
│   │   ├── useBenchStatus.js     ← realtime subscribe per bench
│   │   ├── useMetrics.js
│   │   └── useCommandPalette.js
│   └── components/
│       ├── ActionDropdown.vue
│       ├── StatusBadge.vue
│       └── ResourceMeter.vue
├── vite.config.js
└── package.json
```

`useBenchStatus(name)` returns a reactive `{ status, cpu, mem }` and
internally calls `socket.on('bench:'+name+':status', ...)` plus
`socket.off` on unmount. This composable is the only place the
realtime channel naming lives.
