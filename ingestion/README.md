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

## Idempotency

- **Per-file** — before writing, the file's prior rows are cleared from all
  three tables, then re-inserted; and files already in `PAGE_VIEWS_LOAD_LOG` are
  skipped by default. So re-running a file never duplicates its rows, and a
  **new** file dropped into an already-processed `dt=/hr=` folder is still picked
  up (new filename).
- **Row-level `event_id` dedup is NOT done here** — RAW keeps every landed row
  (in-file and cross-file duplicates included, as auditable history). The
  deduplicated current view is built in **dbt staging** (Task 3) via
  `QUALIFY ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY _loaded_at DESC)`.

## Run

```bash
export SF_ORGANIZATION_NAME=IVUTLPR SF_ACCOUNT_NAME=JZ06632
export SF_USERNAME=OG_INGEST_ADLS_SVC          # needs its RSA key attached (ALTER USER)
export SF_PRIVATE_KEY_PATH=/path/to/ingest_key.p8
# role/warehouse default to REVOPS_INGESTION_ADLS / OG_<ENV>_INGEST_XS_WH

python ingest_page_views.py --env DEV                              # incremental (skip loaded files)
python ingest_page_views.py --env DEV --path dt=2026-05-01/hr=09   # scope to a day/hour folder
python ingest_page_views.py --env DEV --path dt=2026-05-01/hr=09 --backfill   # reprocess that folder
python ingest_page_views.py --env DEV --backfill                   # FULL-SET backfill (every file)
```

Backfill/reprocess is idempotent per file: a file's prior rows are cleared from
all three tables and re-inserted, so reprocessing (a folder or the full set)
never duplicates rows — including quarantine.

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
