# Runbook: add / resize a warehouse

Warehouses are **per role** for cost attribution, created in every active env as
`OG_<ENV>_<KEY>_WH` (the CSV `key`, uppercased). Each functional role is granted
`USAGE` on **every** warehouse whose `function` matches the role's `warehouse`
column — so one role can hold multiple warehouses (see below).

## Edit `config/warehouses.csv`

```
key,function,size,auto_suspend,is_default,comment,is_active
analyst,ANALYST,MEDIUM,60,true,RevOps analyst queries,true
reader,READER,XSMALL,60,true,Read-only / dev reads,true
developer,DEVELOPER,MEDIUM,60,true,dbt model builds,true
admin,ADMIN,XSMALL,60,true,Break-glass admin,true
ingest_adls,INGEST_ADLS,XSMALL,60,true,Python telemetry loader,true
ingest_fivetran,INGEST_FIVETRAN,XSMALL,60,true,Fivetran,true
```

- **`function`** — the group a warehouse belongs to; every role whose
  `warehouse` column equals this function gets `USAGE` on it. The warehouse name
  comes from `key`, not function: `OG_<ENV>_<KEY>_WH`.
- **`size`** — `XSMALL` / `MEDIUM` / `LARGE` … Resize = change this cell.
- **`auto_suspend`** — seconds of idle before suspend (keep low to control cost).
- **`is_default`** — exactly one row per function; it's the service users'
  default warehouse. Additional same-function rows must be `is_default=false`.

## Two warehouses for one role

There are two ways, depending on whether the second warehouse belongs to the
role's own function or a different one.

**Same function (e.g. an XS default + a LARGE backfill wh).** Add a second
`warehouses.csv` row sharing the `function`, with `is_default=false`. Every role
of that function automatically gets `USAGE` on both — no other change. Example:
```
developer,DEVELOPER,MEDIUM,60,true,dbt model builds,true
developer_l,DEVELOPER,LARGE,60,false,Opt-in LARGE for full-refresh/backfill,true
```
`REVOPS_DEVELOPER` lands on `OG_<ENV>_DEVELOPER_WH` by default and runs
`USE WAREHOUSE OG_<ENV>_DEVELOPER_L_WH;` to escalate for a heavy job.

**Different function (cross-function).** Grant a role `USAGE` on a warehouse
outside its own function via `config/warehouse_grants.csv`:
```
key,role,warehouse,is_active
admin_ingest_adls,REVOPS_ADMIN,ingest_adls,true   # role, then a warehouses.csv KEY
```
`warehouse` is a warehouses.csv **key**; the grant is expanded to
`OG_<ENV>_<KEY>_WH` in every active env. Use this only when a role genuinely
needs a warehouse from another function (e.g. an admin running a manual
ingestion). For same-function extras, prefer the row above — no grant needed.

> Note: default warehouse is a **user** property (one per user), so a role with
> two warehouses still lands on one by default; the second is reached with
> `USE WAREHOUSE`.

## Resize (e.g. bump backfills to LARGE)

Just change `size` and redeploy — Terraform issues `ALTER WAREHOUSE … SET
WAREHOUSE_SIZE=…`. Current sizing: `ANALYST`/`DEVELOPER` = MEDIUM, everything
else XSMALL.

## Deploy & verify

PR → merge → CI.
```sql
SHOW WAREHOUSES LIKE 'OG_DEV_%';
```

> A warehouse a role can't `USE` will surface as "no active warehouse" errors.
> The mapping is automatic, but if you reference a warehouse by name in a script
> (loader / seed), make sure it matches `OG_<ENV>_<FUNCTION>_WH`.
