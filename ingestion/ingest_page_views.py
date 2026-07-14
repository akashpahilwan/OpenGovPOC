#!/usr/bin/env python
"""
ingest_page_views.py — load product-telemetry JSON from ADLS into Snowflake.

APPROACH (see infra/README.md for the security rationale):
  The script authenticates to Snowflake ONLY (key-pair, as OG_INGEST_ADLS_SVC /
  REVOPS_INGESTION_ADLS). It reads records through the keyless EXTERNAL STAGE
  PAGE_VIEWS_STAGE (backed by the OG_ADLS_INT storage integration) — so there
  are NO Azure credentials anywhere in this script, and the ADLS->Snowflake
  bytes move server-side, not through this host.

PER-FILE PIPELINE (one Snowflake transaction per file — atomic):
  1. read     — SELECT the file's records through the stage (VARIANT per event)
  2. validate — in Python: contract fields must be present & non-null
  3. load     — the FULL SET of records APPENDs to PAGE_VIEWS (RAW is an
                immutable schema-on-read log — nothing is dropped; malformed
                rows land too, with NULL promoted columns), invalid rows ALSO
                get an audit row in PAGE_VIEWS_QUARANTINE (with a reason), and
                one summary row goes to PAGE_VIEWS_LOAD_LOG. INSERT, never
                MERGE/UPDATE.
  4. commit    — all three writes commit together; ANY exception rolls the whole
                file back (no half-loaded file, no orphan log row). Quarantining
                is normal operation, NOT an error: a file with some bad records
                still commits (partial load + quarantine append).

SCAN MODES (pick one; ALL of them skip files already in PAGE_VIEWS_LOAD_LOG, so
none create duplicate rows in RAW by default):
  default             only files whose dt=/hr= falls in the last --lookback-hours
                      (default 48) — the steady-state hourly run; the lookback is
                      tunable per source SLA. Reads only the window's day-folders.
  --prefill DATE      DATE..today — catch stragglers that arrived later than the
                      window; still skip-aware, so it loads only what's missing.
  --backfill          ALL files under the env prefix.
  --path PREFIX       one ADLS sub-prefix (a single day/hour folder).

  --force-insert      cross-cuts ALL four modes: force-append even files already
                      in the load log. RAW is append-only, so this ADDS duplicate
                      rows on purpose (a deliberate reprocess); dbt staging then
                      collapses them on event_id. Without it, every mode is a
                      no-op for files it has already loaded.

IDEMPOTENCY (RAW is append-only; current-state is a downstream concern):
  - File level: the PAGE_VIEWS_LOAD_LOG skip means no mode reloads a file it has
    already loaded (unless --force-insert). No RAW mutation, no duplicates.
  - Row level (event_id): dbt STAGING runs
    QUALIFY ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY _loaded_at DESC) —
    the deduplicated current view, which also catches the same event_id arriving
    in a DIFFERENT file (a producer resend). RAW keeps every landed row as history.

REUSABILITY:
  The engine is parameterized by EVENTS[<name>] (stage, tables, contract fields).
  A second event type = one EVENTS entry + its Terraform table — no code change.
  Run another type with:  python ingest_page_views.py --event <name>

ENV (secrets never hardcoded):
  SF_ORGANIZATION_NAME, SF_ACCOUNT_NAME, SF_USERNAME, SF_PRIVATE_KEY_PATH
  (optional) SF_ROLE, SF_WAREHOUSE — sensible per-env defaults below.
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


# ── Event configuration — the ONLY thing that differs per event type ────────

@dataclass(frozen=True)
class EventConfig:
    name: str
    schema: str                    # RAW schema holding the stage + tables
    stage: str                     # external stage (over the env-prefixed ADLS path)
    file_format: str               # JSON file format (strip_outer_array)
    target_table: str              # append-only RAW landing table
    quarantine_table: str
    load_log_table: str
    # Contract fields that must be present AND non-null, else the record is
    # quarantined. event_id/account_id/event_timestamp are the hard keys from
    # the brief; user_id is required for page-view attribution — this is what
    # sends the mock's intentional null-user_id record to quarantine.
    required_non_null: tuple = ("event_id", "account_id", "event_timestamp", "user_id")


EVENTS = {
    "page_views": EventConfig(
        name="page_views",
        schema="PRODUCT_EVENTS_RAW_ADLS",
        stage="PAGE_VIEWS_STAGE",
        file_format="FF_JSON",
        target_table="PAGE_VIEWS",
        quarantine_table="PAGE_VIEWS_QUARANTINE",
        load_log_table="PAGE_VIEWS_LOAD_LOG",
    ),
    # A second event type is just another entry here + its Terraform table:
    # "feature_clicks": EventConfig(name="feature_clicks", stage="FEATURE_CLICKS_STAGE", ...),
}


# ── Connection — Snowflake only, key-pair (no Azure creds) ──────────────────

def connect(env: str):
    import snowflake.connector
    from cryptography.hazmat.primitives import serialization

    # We bind with ? placeholders (qmark), not the connector's default %s.
    snowflake.connector.paramstyle = "qmark"

    need = ["SF_ORGANIZATION_NAME", "SF_ACCOUNT_NAME", "SF_USERNAME", "SF_PRIVATE_KEY_PATH"]
    missing = [v for v in need if not os.environ.get(v)]
    if missing:
        sys.exit(f"Missing env vars: {', '.join(missing)}")

    with open(os.environ["SF_PRIVATE_KEY_PATH"], "rb") as f:
        pkey = serialization.load_pem_private_key(f.read(), password=None)
    der = pkey.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    conn = snowflake.connector.connect(
        account=f"{os.environ['SF_ORGANIZATION_NAME']}-{os.environ['SF_ACCOUNT_NAME']}",
        user=os.environ["SF_USERNAME"],
        private_key=der,
        role=os.environ.get("SF_ROLE", "REVOPS_INGESTION_ADLS"),
        warehouse=os.environ.get("SF_WAREHOUSE", f"OG_{env}_INGEST_ADLS_WH"),
        database=f"OG_{env}_DB",
        schema=None,  # set per-event below
        autocommit=False,  # we manage per-file transactions explicitly
    )
    return conn


# ── Read records through the external stage ─────────────────────────────────

def read_staged(cur, cfg: EventConfig, path: str | None):
    """Return [(payload_json_str, filename)] for every record under the stage
    (optionally scoped to a sub-prefix). strip_outer_array => one row per event."""
    loc = f"@{cfg.schema}.{cfg.stage}" + (f"/{path.strip('/')}/" if path else "")
    cur.execute(
        f"SELECT $1, METADATA$FILENAME FROM {loc} "
        f"(FILE_FORMAT => '{cfg.schema}.{cfg.file_format}')"
    )
    return cur.fetchall()


def already_loaded(cur, cfg: EventConfig) -> set:
    cur.execute(f"SELECT DISTINCT file_name FROM {cfg.schema}.{cfg.load_log_table}")
    return {r[0] for r in cur.fetchall()}


_DT_RE = re.compile(r"dt=(\d{4}-\d{2}-\d{2})(?:/hr=(\d{2}))?")

def file_datetime(filename: str):
    """Parse dt=YYYY-MM-DD[/hr=HH] out of a staged path into an aware UTC datetime
    (or None if the path isn't partitioned that way). Used to apply the lookback /
    prefill lower bound with hourly precision."""
    m = _DT_RE.search(filename)
    if not m:
        return None
    d, h = m.group(1), m.group(2) or "00"
    return datetime.strptime(f"{d} {h}", "%Y-%m-%d %H").replace(tzinfo=timezone.utc)

def date_prefixes(start_dt, end_dt):
    """`dt=<date>` sub-prefixes covering [start_dt, end_dt] inclusive (one per day),
    so the DEFAULT window scan lists only the relevant day-folders, not the whole
    stage."""
    out, d = [], start_dt.date()
    while d <= end_dt.date():
        out.append(f"dt={d.isoformat()}")
        d += timedelta(days=1)
    return out


# ── Validation (Python) ─────────────────────────────────────────────────────

def validate(record: dict, cfg: EventConfig):
    """Return a reason string if the record fails the contract, else None."""
    missing = [k for k in cfg.required_non_null if record.get(k) in (None, "")]
    if missing:
        return "missing/null required field(s): " + ", ".join(missing)
    return None


# ── Per-file load (one transaction) ─────────────────────────────────────────

def append_records(cur, cfg: EventConfig, rows):
    """rows: [(event_id, account_id, event_ts, payload_str, filename)] for the
    FULL SET (valid AND invalid). APPEND-ONLY INSERT into RAW (no MERGE) — RAW
    is an immutable schema-on-read log that keeps every landed record; promoted
    columns are NULL for malformed rows. event_id dedup happens in dbt staging."""
    if not rows:
        return 0
    values = ",".join(["(?,?,?,?,?)"] * len(rows))
    params = [v for r in rows for v in r]
    cur.execute(
        f"INSERT INTO {cfg.schema}.{cfg.target_table} "
        f"(event_id, account_id, event_timestamp, payload, _filename) "
        f"SELECT column1, column2, column3::timestamp_ntz, PARSE_JSON(column4), column5 "
        f"FROM VALUES {values}",
        params,
    )
    return len(rows)


def append_quarantine(cur, cfg: EventConfig, rows):
    """rows: [(reason, payload_str, filename)]."""
    if not rows:
        return 0
    values = ",".join(["(?,?,?)"] * len(rows))
    params = [v for r in rows for v in r]
    cur.execute(
        f"INSERT INTO {cfg.schema}.{cfg.quarantine_table} (reason, payload, _filename) "
        f"SELECT column1, PARSE_JSON(column2), column3 FROM VALUES {values}",
        params,
    )
    return len(rows)


def process_file(conn, cfg: EventConfig, filename: str, records):
    """records: [payload_json_str]. APPEND-ONLY: write the full set to RAW +
    quarantine the invalid + one load-log row, all in ONE transaction (a file is
    all-or-nothing). RAW is never mutated here: re-running an already-loaded file
    is prevented upstream by the file-level skip; a --backfill simply re-appends
    and dbt staging dedups on event_id."""
    all_rows, quarantine = [], []
    for payload_str in records:
        rec = json.loads(payload_str)
        reason = validate(rec, cfg)
        # FULL SET lands in RAW — promoted keys are best-effort (None -> NULL).
        all_rows.append((rec.get("event_id"), rec.get("account_id"),
                         rec.get("event_timestamp"), payload_str, filename))
        if reason:  # invalid records ALSO get an audit row in quarantine
            quarantine.append((reason, payload_str, filename))

    cur = conn.cursor()
    try:
        loaded = append_records(cur, cfg, all_rows)   # full set -> RAW (append-only)
        quar = append_quarantine(cur, cfg, quarantine)  # bad ones -> quarantine audit
        cur.execute(
            f"INSERT INTO {cfg.schema}.{cfg.load_log_table} "
            f"(file_name, records_processed, records_quarantined) VALUES (?, ?, ?)",
            (filename, loaded, quar),
        )
        conn.commit()  # full-set load + quarantine + log, atomically
        return loaded, quar
    except Exception:
        conn.rollback()  # unexpected error => whole file back to clean state
        raise
    finally:
        cur.close()


# ── Orchestration ───────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--env", required=True, choices=["DEV", "QA", "PROD"])
    ap.add_argument("--event", default="page_views", choices=list(EVENTS))
    # ── scope: pick one; default is the trailing lookback window ─────────────
    ap.add_argument("--lookback-hours", type=int, default=48,
                    help="DEFAULT mode: only scan files whose dt=/hr= is within the last N "
                         "hours (default 48). Tune per source's late-arrival SLA.")
    ap.add_argument("--prefill", metavar="YYYY-MM-DD",
                    help="scan from this date through today (catch stragglers older than the window).")
    ap.add_argument("--backfill", action="store_true",
                    help="scan ALL files under the env prefix.")
    ap.add_argument("--path", metavar="dt=YYYY-MM-DD/hr=HH",
                    help="scan one ADLS sub-prefix (a single day/hour folder).")
    # ── force flag: cross-cuts every mode ────────────────────────────────────
    ap.add_argument("--force-insert", action="store_true",
                    help="force-append even files already in the load log. RAW is append-only, so this "
                         "creates duplicate rows on purpose (deliberate reprocess); dbt staging dedups "
                         "on event_id. Without it, every mode skips already-loaded files (no dups).")
    args = ap.parse_args()

    cfg = EVENTS[args.event]
    now = datetime.now(timezone.utc)

    # Resolve scan scope -> (stage sub-prefixes to read, lower-bound datetime | None).
    # Precedence: --path > --backfill > --prefill > default window.
    if args.path:
        prefixes, lower, mode = [args.path], None, f"path {args.path}"
    elif args.backfill:
        prefixes, lower, mode = [None], None, "backfill (all files under env prefix)"
    elif args.prefill:
        lower = datetime.strptime(args.prefill, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        prefixes, mode = [None], f"prefill from {args.prefill}"   # read all, filter by date below
    else:
        lower = now - timedelta(hours=args.lookback_hours)
        # Bound the read to the window's day-folders. For an unusually large
        # lookback, fall back to one whole-stage read + the date filter below,
        # rather than enumerating thousands of dt= prefixes.
        prefixes = date_prefixes(lower, now) if (now - lower).days <= 90 else [None]
        mode = f"default (last {args.lookback_hours}h lookback)"

    force = args.force_insert
    print(f"MODE: {mode}" + (
        "  [--force-insert: forcing re-insert; duplicates land in append-only RAW]"
        if force else "  [skips files already in _LOAD_LOG; no duplicates]"))

    conn = connect(args.env)
    conn.cursor().execute(f"USE SCHEMA OG_{args.env}_DB.{cfg.schema}")
    try:
        cur = conn.cursor()
        rows = []
        for pfx in prefixes:
            rows += read_staged(cur, cfg, pfx)

        # group by file; for window/prefill, drop files before the lower bound (hour-precise)
        by_file: dict[str, list] = {}
        for payload_str, filename in rows:
            if lower is not None:
                fdt = file_datetime(filename)
                if fdt is not None and fdt < lower:
                    continue
            by_file.setdefault(filename, []).append(payload_str)

        if not by_file:
            print(f"No files in scope for mode: {mode}")
            return

        # every mode is skip-aware unless --force-insert forces the re-insert
        skip = set() if force else already_loaded(cur, cfg)
        cur.close()

        total_loaded = total_quar = total_files = 0
        for filename, records in sorted(by_file.items()):
            if filename in skip:
                print(f"skip (already loaded) {filename}")
                continue
            loaded, quar = process_file(conn, cfg, filename, records)
            total_files += 1
            total_loaded += loaded
            total_quar += quar
            print(f"OK  {filename}  loaded={loaded} quarantined={quar}")

        print(f"\nDone: {total_files} file(s), {total_loaded} loaded, {total_quar} quarantined.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
