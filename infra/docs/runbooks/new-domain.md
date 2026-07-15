# Runbook: onboard a whole new spoke domain

A spoke "domain" (Finance, Revenue, Budget, HR…) is the same set of config rows
every time. Everything is domain-shaped, so onboarding one is **additive config,
no new HCL** — the paved path for federated self-serve. Finance is the first
built example; Revenue/Budget/HR are the same recipe.

A spoke **consumes upstream PUBLIC marts** (e.g. `MARTS_REVOPS`) and **produces
its own** `MARTS_<DOMAIN>`. The RBAC boundary — the spoke can read the upstream
mart but **not** its `RAW`/`STAGING` or dev sandboxes — is what enforces the
Mesh contract (no cross-project `ref()` needed; the spoke's dbt project reads
the upstream schema as a `source()`).

## 1. Schemas — `config/schemas.csv`
```
marts_finance,MARTS_FINANCE,DATA,true,Finance domain marts (dbt),true
```
(Just the output marts schema if the spoke reads an existing upstream mart. Add
a RAW schema only if the domain ingests its own source.)

## 2. Functional roles — `config/functional_roles.csv`
Three roles per spoke. **Do NOT inherit any other domain's role** — that's the
isolation. `granted_to = SYSADMIN`; `developer` inherits `reader`.
```
finance_analyst,FINANCE_ANALYST,Reads MARTS_FINANCE only,,SYSADMIN,FINANCE_ANALYST,true,true
finance_reader,FINANCE_READER,Reads upstream MARTS_REVOPS + MARTS_FINANCE; no cross-domain reads,,SYSADMIN,FINANCE_READER,true,true
finance_developer,FINANCE_DEVELOPER,Inherits FINANCE_READER + writes MARTS_FINANCE; SERVICE-ONLY (dbt CI),FINANCE_READER,SYSADMIN,FINANCE_DEVELOPER,false,true
```

## 3. Grants — `config/functional_grants.csv`
Reader gets the upstream + own marts; developer only needs the extra WRITE
(reads come via inheriting the reader):
```
finance_reader_revops,FINANCE_READER,ALL,MARTS_REVOPS,R,true
finance_reader_finance,FINANCE_READER,ALL,MARTS_FINANCE,R,true
finance_developer_marts,FINANCE_DEVELOPER,ALL,MARTS_FINANCE,W,true
```

## 4. Warehouses — `config/warehouses.csv`
Dedicated per-role functions so the domain never borrows another's compute
(cost attribution + isolation):
```
finance_analyst,FINANCE_ANALYST,MEDIUM,60,true,...,true
finance_reader,FINANCE_READER,XSMALL,60,true,...,true
finance_developer,FINANCE_DEVELOPER,MEDIUM,60,true,...,true
```

## 5. Service user — `config/service_users.csv`
The spoke's dbt-CI identity, holding the developer role:
```
finance_dbt,OG_FINANCE_DBT_SVC,FINANCE_DEVELOPER,FINANCE_DEVELOPER,,Finance-hub dbt CI,true
```

## 6. Users — `config/human_users.csv` (+ `config/sandboxes.csv` for developers)

Two kinds of users, configured differently. Terraform creates the user shell
(no passwords — initial auth is out-of-band / SSO); the `default_role` is what
they land on at login, and secondary roles are off, so it must be a role they
actually hold.

**a) Analyst / reader users** — they only *query* marts, so they just need the
functional role as their default. No sandbox. This is how the two finance
analysts are set up:
```
# human_users.csv
priya,PRIYA_SHARMA,priya.sharma@opengov.com,priya.sharma@opengov.com,FINANCE_ANALYST,Finance analyst - reads MARTS_FINANCE,true
```
`default_role` **does not grant** a role — so also grant it in `user_roles.csv`
(a user's default must be a role they hold):
```
# user_roles.csv
priya_finance,PRIYA_SHARMA,FINANCE_ANALYST,true
```

**b) Developer users** — they *build* dbt models, so they need a writable dev
schema. One `sandboxes.csv` row generates a `<DOMAIN>_DEV_<NAME>` schema (with
R/W access roles) **and** a composite login role `DEV_<DOMAIN>_<NAME>` that
carries the domain `reader_role` + write on that one sandbox — nothing else:
```
# sandboxes.csv
key,env,domain,developer,reader_role,is_active
meera_finance,DEV,FINANCE,MEERA_IYER,FINANCE_READER,true
```
Then the `human_users.csv` row uses that composite as the default role — and
because the composite is granted to the user *by* the sandbox mechanism, no
`user_roles.csv` row is needed for a developer:
```
# human_users.csv
meera,MEERA_IYER,meera.iyer@opengov.com,meera.iyer@opengov.com,DEV_FINANCE_MEERA_IYER,Finance developer: composite (read MARTS_REVOPS + own sandbox); no secondary roles,true
```
(RevOps developers predate `sandboxes.csv` and stay on the `developers` column
of `environments.csv`; every new spoke uses `sandboxes.csv`.)

## 7. Masking — `config/masking_exemptions.csv`
Who on the domain sees real financials. The dev/CI role must be exempt to build
real numbers from the upstream mart; the analyst usually should see the domain's
own marts unmasked:
```
finance_dev_reads_financial,PII_FINANCIAL,FUNCTIONAL,FINANCE_DEVELOPER,true
finance_analyst_sees_financial,PII_FINANCIAL,FUNCTIONAL,FINANCE_ANALYST,true
```
Classification of the domain's own PII (if any) is `masking_rules.csv` +
`pii_columns.csv` — tags, not new policy code.

## 8. dbt (separate step)
A spoke repo with its own native `DBT PROJECT`, running as the domain's service
user, reading the upstream mart via `source()` and writing `MARTS_<DOMAIN>`.

## What the Finance rows above produce

The user → role → grant chains that come out of the config (all verified live):

```
PRIYA_SHARMA (analyst)
  └─ FINANCE_ANALYST            → reads MARTS_FINANCE only (own wh: OG_<ENV>_FINANCE_ANALYST_WH)

MEERA_IYER (developer)
  └─ DEV_FINANCE_MEERA_IYER (composite, her default; no secondary roles)
       ├─ FINANCE_READER                    → reads MARTS_REVOPS + MARTS_FINANCE
       └─ AR_DEV_FINANCE_DEV_MEERA_IYER_W    → writes ONLY her FINANCE_DEV_MEERA_IYER sandbox

OG_FINANCE_DBT_SVC (finance-hub dbt CI)
  └─ FINANCE_DEVELOPER          → inherits FINANCE_READER (read MARTS_REVOPS) + writes MARTS_FINANCE
```

Isolation check that must hold: `FINANCE_*` can read `MARTS_REVOPS` (the upstream
source) but is **denied** on the hub's `RAW` / `STAGING` and on any
`REVOPS_DEV_*` sandbox — finance never inherits a RevOps role. Masking: the
build role (`FINANCE_DEVELOPER`) and `FINANCE_ANALYST` are exempt so they see
real financials; `FINANCE_READER` (and a developer's dev build, which runs under
the composite → `FINANCE_READER`) sees them masked.

## Deploy
```
python infra/sync_config.py    # validates the whole graph
```
→ PR → CI runs `terraform apply` + `apply_pii_tags`. Schemas, roles, service
user, warehouses, sandboxes, and masking all come up together.

**Why it scales:** roles are account-wide and env-composed via access roles;
sandboxes/composites are generated by `for_each` over `sandboxes.csv`; masking
scales through tags not policies. Every artifact is `for_each` over a CSV — so
spoke #10 is the same effort as Finance. Verified for Finance: `FINANCE_DEVELOPER`
reads `MARTS_REVOPS` (real values) via inherited `FINANCE_READER` but is denied
on `STAGING`/`RAW`.
