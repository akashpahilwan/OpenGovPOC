# Product-telemetry ingestion (Task 2)

`ingest_page_views.py` loads product-telemetry JSON from ADLS into Snowflake
RAW, validating and quarantining per record.

## Security: keyless, Snowflake-only auth

The script authenticates to **Snowflake only** (key-pair, as `OG_INGEST_ADLS_SVC`
/ `REVOPS_INGESTION_ADLS`). It reads records through the **external stage**
`PAGE_VIEWS_STAGE`, backed by the `OG_ADLS_INT` storage integration — so there
are **no Azure credentials anywhere** in the script, and ADLS→Snowflake bytes
move server-side, not through this host.

## Per-file pipeline (one transaction, atomic)

1. **read** – `SELECT $1 FROM @PAGE_VIEWS_STAGE (FILE_FORMAT => FF_JSON)` →
   one VARIANT per event.
2. **validate** (Python) – contract fields must be present & non-null:
   `event_id`, `account_id`, `event_timestamp` (the brief's keys) + `user_id`
   (required for attribution — this is what quarantines the mock's null-user row).
3. **load** – the **full set** of records **appends** to `PAGE_VIEWS` (RAW is an
   immutable schema-on-read log — `INSERT`, never `MERGE`; malformed rows land
   too, with NULL promoted columns, so nothing is ever dropped). Invalid rows
   **also** get an audit row in `PAGE_VIEWS_QUARANTINE` with a reason. One
   summary row goes to `PAGE_VIEWS_LOAD_LOG`.
4. **commit** – all three commit together. Any **exception → rollback** the whole
   file (clean state to retry). Quarantining is normal, not an error: a file with
   some bad rows still commits (partial load + quarantine).

## Scan modes & idempotency

Pick one scan scope. **Every mode skips files already in `PAGE_VIEWS_LOAD_LOG`, so
none create duplicate rows** — RAW stays append-only, nothing is deleted:

| Mode | Scans | Use for |
|------|-------|---------|
| *default* | files in the last `--lookback-hours` (default **48**) | the steady-state hourly run |
| `--prefill YYYY-MM-DD` | that date → today | a straggler that arrived after the window |
| `--backfill` | every file under the env prefix | a full (re)load |
| `--path dt=…/hr=…` | one day/hour folder | one specific folder |

- **File-level idempotency** — the `_LOAD_LOG` skip means no mode reloads a file it
  has already loaded, so re-runs never duplicate rows and RAW is never mutated.
- **`--force-insert`** cross-cuts all four modes: it forces the append **even for
  already-loaded files**. Because RAW is append-only, that intentionally adds
  duplicate rows (a deliberate reprocess), which dbt staging then dedups on
  `event_id`. Reach for it only when you *mean* to re-load.
- **Row-level `event_id` dedup is NOT done here** — RAW keeps every landed row as
  auditable history; the deduplicated current view is built in **dbt staging**
  (Task 3) via `QUALIFY ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY _loaded_at DESC)`,
  which also catches the same event arriving in a **different** file (a resend).

> **Late-arriving files:** anything within the lookback window is picked up
> automatically; something older is a `--prefill <date>` (skip-aware, no dups).
> In production, Snowpipe auto-ingest removes the window entirely by loading each
> file the moment it arrives.

## Run

```bash
export SF_ORGANIZATION_NAME=IVUTLPR SF_ACCOUNT_NAME=JZ06632
export SF_USERNAME=OG_INGEST_ADLS_SVC          # needs its RSA key attached (ALTER USER)
export SF_PRIVATE_KEY_PATH=/path/to/ingest_key.p8
# role/warehouse default to REVOPS_INGESTION_ADLS / OG_<ENV>_INGEST_ADLS_WH

python ingest_page_views.py --env DEV                             # default: last 48h window
python ingest_page_views.py --env DEV --lookback-hours 6          # tighter window
python ingest_page_views.py --env DEV --prefill 2026-05-01        # catch stragglers from a date
python ingest_page_views.py --env DEV --backfill                  # scan every file (skip-aware)
python ingest_page_views.py --env DEV --path dt=2026-05-01/hr=09  # one folder
python ingest_page_views.py --env DEV --backfill --force-insert   # deliberately re-load all (dups -> staging dedups)
```

> **Loading the seeded sample data:** the sample files are dated in the past, so
> the *default* 48h window won't see them — use `--backfill` (or
> `--prefill <their date>`) for the initial historical load.

Path layout: `og-telemetry/<env>/product_events/page_views/dt=YYYY-MM-DD/hr=HH/`
(`hr` is 24-hour, `00`–`23`).

## Panel probes

- **Partial batch failure mid-load** — per-file transaction: everything commits
  or the whole file rolls back; `event_id` dedup in staging makes retries safe.
- **Files on arrival (Lambda/S3 → here ADLS)** — the unit of work is one file,
  so it's the same function behind an **Event Grid `BlobCreated` → Function**
  trigger, or **Snowpipe auto-ingest** for the fully-managed path. Only the
  trigger changes.
- **Reusable for a second event type** — the engine is parameterized by
  `EVENTS[<name>]` (stage, tables, contract fields); a new type is one config
  entry + its Terraform table, run with `--event <name>`. No copy-paste.

## Reusability / production notes

- Attach an RSA key to `OG_INGEST_ADLS_SVC` (`ALTER USER … SET RSA_PUBLIC_KEY`)
  so runs use the dedicated ingestion identity (key-pair, no password).
- `mock/` holds sample payloads (incl. the brief's, plus a validation set with
  every quarantine case and a duplicate `event_id`) for uploading to ADLS.
