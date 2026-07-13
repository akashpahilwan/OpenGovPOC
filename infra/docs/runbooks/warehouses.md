# Runbook: add / resize a warehouse

Warehouses are **per role** for cost attribution, created in every active env as
`OG_<ENV>_<ROLE>_WH`. Each functional role is granted `USAGE` on its own
warehouse(s) automatically.

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

- **`function`** — maps to a role; the warehouse becomes `OG_<ENV>_<FUNCTION>_WH`
  and USAGE is granted to the matching functional role.
- **`size`** — `XSMALL` / `MEDIUM` / `LARGE` … Resize = change this cell.
- **`auto_suspend`** — seconds of idle before suspend (keep low to control cost).

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
