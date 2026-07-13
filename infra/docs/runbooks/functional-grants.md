# Runbook: change functional grants

`functional_grants.csv` wires **functional roles** (account-wide) to **access
roles** (`AR_<ENV>_<SCHEMA>`) — i.e. which role can read/write which schema, in
which env. This is where the env dimension enters: `env=ALL` composes the role
across DEV *and* PROD.

## Edit `config/functional_grants.csv`

```
key,role,env,schema,level,is_active
analyst_marts,REVOPS_ANALYST,ALL,MARTS_*,R,true
reader_all,REVOPS_READER,ALL,*,R,true
developer_staging,REVOPS_DEVELOPER,ALL,STAGING,W,true
developer_marts,REVOPS_DEVELOPER,ALL,MARTS_REVOPS,W,true
ingestion_adls,REVOPS_INGESTION_ADLS,ALL,PRODUCT_EVENTS_RAW_ADLS,W,true
```

- **`role`** — a functional role (must exist in `functional_roles.csv`).
- **`env`** — `ALL` (both envs) or `DEV` / `PROD`. Prefer `ALL` — one grant,
  both databases.
- **`schema`** — exact (`STAGING`), prefix (`MARTS_*`), or `*` (all DATA schemas).
- **`level`** — `R` (read: usage + select) or `W` (write: DML + more).

## Rules enforced by `sync_config.py`

- Referenced roles/schemas must exist.
- A pattern that matches no schema is fine (future-proof), but a typo'd exact
  schema fails at sync time.

## Deploy & verify

PR → merge → CI. Verify the access role landed under the functional role:
```sql
SHOW GRANTS TO ROLE REVOPS_ANALYST;   -- should list AR_<ENV>_MARTS_REVOPS_R
```

> Never grant an `AR_*` access role (or a raw object privilege) directly to a
> **user**. Users hold functional/composite roles only — that's the invariant
> that makes offboarding a single revoke.
