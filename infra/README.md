# OpenGov POC — Snowflake RBAC & Security (Task 1)

Terraform-managed access control for the RevOps domain: two environments
(`OG_DEV_DB`, `OG_PROD_DB`), two-tier role hierarchy, scoped ingestion
identities, dbt Mesh (hub + spoke) service roles, and tag-based masking of
`ACCOUNT.ARR`.

## Config-driven RBAC (CSV/Excel → JSON → Terraform)

No object lists live in HCL. The human interface is `infra/config/*.csv`
(or one Excel workbook `og_config.xlsx` with matching sheets);
`sync_config.py` converts them into JSON manifests under
`infra/resources/infrastructure/`, which Terraform `for_each`es over:

```
config/environments.csv       active environments (DEV / PROD)
config/warehouses.csv         warehouses per function (XS default + L)
config/schemas.csv            schemas + kind (DATA / GOVERNANCE / DBT)
config/service_users.csv      service identities (TYPE=SERVICE) → role
config/functional_roles.csv   the 5 roles + hierarchy (inherits_from/granted_to)
config/functional_grants.csv  role × env × schema-pattern × R/W rules
config/masking_rules.csv      masking VOCABULARY: tag x data_type x mask expr
config/pii_columns.csv        column PII classifications (applied by apply_pii_tags.py)
config/masking_exemptions.csv WHO sees unmasked PII (roles only, never users)
config/human_users.csv        human users Terraform creates (no passwords)
config/user_roles.csv         user → functional role assignments
```

```bash
python infra/sync_config.py            # regenerate manifests (validates refs)
python infra/sync_config.py --dry-run  # preview without writing
```

Every RBAC change is a CSV edit in a PR: `is_active=false` soft-deletes on
the next apply; a new domain, schema, role, or developer sandbox is a row.
`sync_config.py` cross-validates references (unknown schemas, roles, envs)
so mistakes fail at sync time, not at `terraform apply` time.

## Layout

```
OG_<ENV>_DB
├── SALESFORCE_RAW_FIVETRAN   raw — all privileges to REVOPS_INGESTION_FIVETRAN (owns its DDL)
├── PRODUCT_EVENTS_RAW_ADLS   raw — write to REVOPS_INGESTION_ADLS (Python/ADLS);
│                             tables/stage/file format are deployer-owned contract objects
├── STAGING                   dbt staging models (built by REVOPS_DEVELOPER)
├── MARTS_REVOPS              dbt RevOps marts (built by REVOPS_DEVELOPER)
├── GOVERNANCE                masking policy + PII_FINANCIAL tag (no data)
└── DBT                       native "dbt Projects on Snowflake" objects

Warehouses (two sizes per pipeline function; XSMALL is the default, LARGE is
opt-in via USE WAREHOUSE for backfills / full refreshes):
  OG_<ENV>_INGEST_XS_WH  / OG_<ENV>_INGEST_L_WH
  OG_<ENV>_TRANSFORM_XS_WH / OG_<ENV>_TRANSFORM_L_WH
  OG_<ENV>_ANALYTICS_XS_WH
```

RAW schemas are named `<SOURCE>_RAW_<INGESTION_TYPE>` so each loader's
rights are scoped to exactly its own landing schema.
The brief's `RAW.SALESFORCE.ACCOUNT` ⇒ `OG_<ENV>_DB.SALESFORCE_RAW_FIVETRAN.ACCOUNT`;
`RAW.PRODUCT_EVENTS.PAGE_VIEWS` ⇒ `OG_<ENV>_DB.PRODUCT_EVENTS_RAW_ADLS.PAGE_VIEWS`.
(Owner decision: telemetry files land in **ADLS**, not S3 — the brief's
boto3 pattern is implemented 1:1 with the Azure Blob SDK instead.)

## ADLS telemetry landing (storage integration + contract objects)

Files land in a new `og-telemetry` container in the existing `snowopssa`
storage account, env-prefixed:
`azure://snowopssa.blob.core.windows.net/og-telemetry/<env>/product_events/page_views/dt=YYYY-MM-DD/hr=HH/...`

Terraform (as OG_DEPLOYER) deploys the full ingestion contract:
- `OG_ADLS_INT` — account-level **storage integration** (config/storage_integrations.csv)
- `PAGE_VIEWS_STAGE` — external stage per env over the env's path prefix (config/stages.csv)
- `FF_JSON` — JSON file format, `strip_outer_array` (config/file_formats.csv)
- `PAGE_VIEWS`, `PAGE_VIEWS_QUARANTINE`, `PAGE_VIEWS_LOAD_LOG` — stable-DDL raw
  tables (promoted keys + `payload VARIANT`), config-driven SnowOps-style:
  manifest in `config/tables.csv`, column definitions in
  `resources/tables/<key>.json`, deployed per env by Terraform via CI/CD.
  **Custom-ingestion schemas only** — Fivetran-owned schemas never appear in
  tables.csv (the connector manages that DDL; sync_config.py enforces this).
  Adding a raw table for a new event type = one CSV row + one JSON file in a PR.

Because the platform owns this DDL, `AR_<ENV>_PRODUCT_EVENTS_RAW_ADLS_W` is
**DML-only** (`writer_owns_future=false` in schemas.csv): the loader can
INSERT/COPY but can never ALTER or DROP the contract. Contrast with the
Fivetran schema (`writer_owns_future=true`), where the connector owns its DDL.

One-time Azure setup (after the first `terraform apply`):
```bash
az storage container create --name og-telemetry --account-name snowopssa
```
```sql
DESC STORAGE INTEGRATION OG_ADLS_INT;
-- open AZURE_CONSENT_URL in a browser, grant consent, then in the Azure
-- portal give the Snowflake service principal (AZURE_MULTI_TENANT_APP_NAME)
-- "Storage Blob Data Contributor" on the og-telemetry container.
```

## Role model (Snowflake-recommended two tiers)

**Tier 1 — access roles** (never granted to users): `AR_<ENV>_<SCHEMA>_R`
(usage + select, current & future) and `AR_<ENV>_<SCHEMA>_W` (all schema
privileges + DML + future ownership, so writers can ALTER/DROP what they create).

**Tier 2 — functional roles** (account-wide; the privileges live here, so a
role spans both envs). Five roles, kept deliberately simple:

| Role | Access |
|---|---|
| `REVOPS_ANALYST` | read `MARTS_REVOPS` (DEV + PROD) |
| `REVOPS_DEVELOPER` | analyst + **read/write `RAW` + `STAGING` + `MARTS`** (DEV + PROD) — this is the role dbt jobs run as to build models, including in PROD |
| `REVOPS_ADMIN` | full domain access; the only role that sees unmasked ARR |
| `REVOPS_INGESTION_ADLS` | write `PRODUCT_EVENTS_RAW_ADLS` (Python/ADLS telemetry loader) |
| `REVOPS_INGESTION_FIVETRAN` | all privileges on tables + views in `SALESFORCE_RAW_FIVETRAN` (Fivetran connector) |

Hierarchy: `REVOPS_ANALYST → REVOPS_DEVELOPER → REVOPS_ADMIN → SYSADMIN`; the
two ingestion roles hang off `SYSADMIN` directly (each tier declares only its
increment; inheritance supplies the rest).

**Service users** (`config/service_users.csv`) — `TYPE = SERVICE`, key-pair
JWT only (passwords impossible). Each holds exactly one functional role:

| User | Holds | Purpose |
|---|---|---|
| `OG_DBT_SVC` | `REVOPS_DEVELOPER` | dbt model builds, DEV **and** PROD |
| `OG_INGEST_ADLS_SVC` | `REVOPS_INGESTION_ADLS` | Python telemetry loader |
| `OG_FIVETRAN_SVC` | `REVOPS_INGESTION_FIVETRAN` | Fivetran connector |

## ARR masking (tag-based)

`GOVERNANCE.MASK_PII_FINANCIAL_NUMBER` returns the real value only when
`IS_ROLE_IN_SESSION('REVOPS_ADMIN')` (hierarchy-aware — survives role
inheritance and secondary roles); **everyone else, including `REVOPS_DEVELOPER`
and the dbt job, gets NULL** — exactly the brief. Because dbt is not exempt,
`ARR` is deliberately **kept out of staging/marts models** so nothing ever
persists a masked NULL; the real value lives only in RAW, visible only to
`REVOPS_ADMIN`. The policy attaches to the `GOVERNANCE.PII_FINANCIAL` **tag**
(config `masking_rules.csv`), and the tag is set on `ACCOUNT.ARR` by
`apply_pii_tags.py` from `pii_columns.csv` — classifying a column IS protecting
it, across all future domains, with zero per-table policy wiring.

## PII masking — fully config-driven & extensible

Three CSVs, three questions, zero HCL to add a rule:

- **What masking rules exist** — `config/masking_rules.csv`: one row per
  `(tag, data_type)` → Terraform generates a tag (deduped across rows) and a
  masking policy whose non-exempt branch is `mask_expression` (references
  `VAL`). `NULL`, a partial reveal (`REGEXP_REPLACE(VAL,'^[^@]+','****')`), a
  hash — anything valid for that data type. Adding `PII_CONTACT` masking
  VARCHAR emails, or a second data type on an existing tag, is a CSV row.
  `sync_config.py` rejects a duplicate `(tag, data_type)` (Snowflake allows
  multiple policies on a tag only if their argument types differ) and any
  `mask_expression` that doesn't reference `VAL`.
- **What is classified** — `config/pii_columns.csv` (schema/table/column → tag).
- **Who sees it unmasked** — `config/masking_exemptions.csv`, per tag (a
  functional role name). Current PII_FINANCIAL: **REVOPS_ADMIN only**; everyone
  else (including REVOPS_DEVELOPER and the dbt job) reads the mask. Users are
  never exempted directly — grant an exempt role via user_roles.csv, so
  offboarding stays a single role revoke.

**Applying it:** Terraform creates the tags + policies. `apply_pii_tags.py`
does the two things this provider version can't express as resources —
binds each policy to its tag (`ALTER TAG ... SET MASKING POLICY`) and
classifies columns (`ALTER TABLE ... SET TAG`) — both idempotent, from the
same manifests. Run it after apply/seed and after every Fivetran re-sync
(Fivetran recreating a table would strip column tags; TF state would drift,
which is why this is a script):

```bash
python infra/apply_pii_tags.py --env DEV            # bind + classify
python infra/apply_pii_tags.py --env PROD --dry-run # preview the SQL
```

`masking_rules.csv` ships two inactive examples (PII_CONTACT email, PII_PHONE)
— flip `is_active` to see new tags+policies appear with no code change.

## Deploy

```bash
# 0. One-time: generate the deployer key pair, paste public key into
#    infra/bootstrap/bootstrap_deployer.sql, run it as ACCOUNTADMIN.
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out og_deployer_rsa_key.p8 -nocrypt
openssl rsa -in og_deployer_rsa_key.p8 -pubout -out og_deployer_rsa_key.pub

# 1. Secrets — environment only, nothing on disk or in code:
export TF_VAR_SF_ORGANIZATION_NAME="IVUTLPR"
export TF_VAR_SF_ACCOUNT_NAME="JZ06632"
export TF_VAR_SF_USERNAME="OG_DEPLOYER_SVC"
export TF_VAR_SF_PRIVATE_KEY="$(cat og_deployer_rsa_key.p8)"

# 2. Provision both environments:
cd infra/terraform && terraform init && terraform plan && terraform apply

# 3. Seed the mock Fivetran tables + wire tag-based masking (per env):
snow sql -f infra/seed/seed_salesforce_mock.sql -D "env=DEV"
snow sql -f infra/seed/seed_salesforce_mock.sql -D "env=PROD"
```

## Onboard a new analyst

1. Add one row to `config/human_users.csv` (creates the user; initial
   password/SSO is set out-of-band — no secrets in config):
   `jane,JANE_DOE,jane.doe@opengov.com,jane.doe@opengov.com,REVOPS_ANALYST,GTM analyst,true`
2. Add one row to `config/user_roles.csv`:
   `jane_analyst,JANE_DOE,REVOPS_ANALYST,true`
3. PR → merge → `python infra/sync_config.py && terraform apply` (CI does this).
   The functional role already carries warehouse usage and marts read.
   Never grant `AR_*` access roles or object privileges directly to users —
   that is the invariant that makes offboarding total.

## Onboard a new developer (e.g. SOURABH_SHINDE) — two CSV edits

1. `config/human_users.csv` — creates the Snowflake user:
   `sourabh,SOURABH_SHINDE,sourabh.shinde@opengov.com,...,REVOPS_DEVELOPER,...,true`
2. `config/user_roles.csv`:
   `sourabh_developer,SOURABH_SHINDE,REVOPS_DEVELOPER,true`

`REVOPS_DEVELOPER` gives read/write on RAW + STAGING + MARTS in both envs. For
personal dev work, developers point their dbt profile `schema` at a namespaced
target (e.g. `STAGING_SOURABH`) within the schemas they already can write —
no separate sandbox schema is provisioned. Verify: `SHOW GRANTS TO USER SOURABH_SHINDE;`

## Offboard someone — full revocation

1. Flip the user's rows in `config/user_roles.csv` to `is_active=false`
   (sync + apply revokes the roles) — a single-cell change, auditable in git.
2. Immediately, out-of-band: `ALTER USER JANE_DOE SET DISABLED = TRUE;`
   (kills live sessions and the login while the PR merges).
3. Verify: `SHOW GRANTS TO USER JANE_DOE;` must return zero rows.
4. After the retention window: `DROP USER JANE_DOE;`

Because object grants live only in access roles, and users hold only
functional roles, revoking the functional role removes **everything** — there
is no per-object cleanup and nothing to forget.

## Audit: who saw ACCOUNT.ARR, and when?

Enterprise edition `ACCESS_HISTORY` records column-level reads:

```sql
SELECT ah.query_start_time, ah.user_name, q.role_name,
       f.value:objectName::string  AS table_fqn
FROM snowflake.account_usage.access_history ah
JOIN snowflake.account_usage.query_history q USING (query_id),
     LATERAL FLATTEN(ah.base_objects_accessed) f,
     LATERAL FLATTEN(f.value:columns) c
WHERE f.value:objectName::string ILIKE '%SALESFORCE_RAW_FIVETRAN.ACCOUNT'
  AND c.value:columnName::string = 'ARR'
ORDER BY ah.query_start_time DESC;
```

Pair with `POLICY_REFERENCES` to prove the policy was attached at read time:
`SELECT * FROM TABLE(og_prod_db.information_schema.policy_references(policy_name => 'OG_PROD_DB.GOVERNANCE.MASK_PII_FINANCIAL_NUMBER'));`

## How this scales to N domains

Everything is domain-shaped: a new domain = a `MARTS_<DOMAIN>` schema + its
functional roles + service users, all generated from the same CSV config and
module. Masking scales through tags, not policies: classify the column,
protection follows.
