# Runbook: add a schema

Adding a schema creates it in **every active environment**, plus its access
roles `AR_<ENV>_<SCHEMA>_R` / `_W` (with current + future grants). Functional
roles then compose those access roles via `functional_grants.csv`.

## Edit `config/schemas.csv`

```
key,schema,kind,writer_owns_future,comment,is_active
marts_finance,MARTS_FINANCE,DATA,false,Finance domain marts,true
```

- **`kind`**: `DATA` (gets R/W access roles) · `GOVERNANCE` (tags/policies, no
  access roles) · `DBT` (native dbt objects).
- **`writer_owns_future`**: `true` → the `_W` role **owns** future objects it
  creates (Fivetran-style, connector manages its own DDL). `false` → DML-only:
  the writer can INSERT/COPY but the platform (deployer) owns the DDL contract
  (use for platform-owned RAW tables and dbt-built schemas).

## Grant access to it

The schema alone grants nothing to functional roles. Add rows to
`functional_grants.csv` so roles can read/write it — see the
[functional-grants runbook](functional-grants.md). E.g. to let readers read it:
```
reader_all,REVOPS_READER,ALL,*,R,true      # already covers all DATA schemas via '*'
```
`*` and `PREFIX*` patterns mean new `DATA` schemas are often covered automatically
(readers read `*`; analysts read `MARTS_*`).

## Non-DATA schemas (GOVERNANCE / DBT)

These have no access roles, so `*` grants don't reach them. Grant `USAGE`
explicitly if a role needs to see them (as done for `REVOPS_READER` on
`GOVERNANCE` + `DBT` in `main.tf`).

## Deploy & verify

PR → merge → CI (`sync_config` + `terraform apply` + `apply_pii_tags`).
```sql
SHOW SCHEMAS LIKE 'MARTS_FINANCE' IN DATABASE OG_DEV_DB;
SHOW ROLES LIKE 'AR_DEV_MARTS_FINANCE_%';
```
