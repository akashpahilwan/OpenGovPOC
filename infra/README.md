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
config/environments.csv       envs + warehouse sizing + developer sandboxes
config/schemas.csv            schemas + kind (DATA / GOVERNANCE / DBT)
config/service_roles.csv      pipeline identities + schema R/W sets + dbt flag
config/functional_roles.csv   human roles + hierarchy (inherits_from/granted_to)
config/functional_grants.csv  role × env × schema-pattern × R/W rules
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
├── SALESFORCE_RAW_FIVETRAN   raw — written ONLY by OG_FIVETRAN_<ENV> (owns its DDL)
├── PRODUCT_EVENTS_RAW_ADLS   raw — DML ONLY by OG_INGEST_<ENV> (Python/ADLS);
│                             tables/stage/file format are deployer-owned contract objects
├── STAGING                   dbt HUB project output (platform team)
├── MARTS_REVOPS              dbt RevOps SPOKE project output
├── REVOPS_DEV                shared dev target (CI/integration runs, DEV only)
├── REVOPS_DEV_<NAME>         personal dbt sandbox per developer (DEV only)
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
  tables (promoted keys + `payload VARIANT`), in `modules/og_env/storage_objects.tf`

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

**Tier 2a — human functional roles** (account-wide, one set, per the brief):

| Role | Access |
|---|---|
| `REVOPS_ANALYST` | read `MARTS_REVOPS` (DEV + PROD) |
| `REVOPS_DEVELOPER` | analyst + read `STAGING` (DEV + PROD) + write `REVOPS_DEV` (DEV only — PROD writes go through CI/CD, never humans) |
| `REVOPS_ADMIN` | full domain access; the only human role that sees unmasked ARR |

Hierarchy: `REVOPS_ANALYST → REVOPS_DEVELOPER → REVOPS_ADMIN → SYSADMIN`
(each tier declares only its increment; inheritance supplies the rest).

**Tier 2b — service roles** (env-suffixed — a pipeline identity never spans envs):

| Role | Access | User |
|---|---|---|
| `OG_FIVETRAN_<ENV>` | W on `SALESFORCE_RAW_FIVETRAN` only | `OG_FIVETRAN_SVC_<ENV>` |
| `OG_INGEST_<ENV>` | W on `PRODUCT_EVENTS_RAW_S3` only | `OG_INGEST_SVC_<ENV>` |
| `OG_DBT_HUB_<ENV>` | R on both RAW, W on `STAGING` | `OG_DBT_HUB_SVC_<ENV>` |
| `OG_DBT_REVOPS_<ENV>` | R on `STAGING`, W on `MARTS_REVOPS` + `REVOPS_DEV` | `OG_DBT_REVOPS_SVC_<ENV>` |

The dbt Mesh boundary is enforced by RBAC: the RevOps spoke **cannot read
RAW** — it can only build on the hub's published STAGING models. All service
users are `TYPE = SERVICE` (key-pair JWT only; passwords are impossible).

## ARR masking (tag-based)

`GOVERNANCE.MASK_ARR_NUMBER` returns the real value only when
`IS_ROLE_IN_SESSION('REVOPS_ADMIN')` (hierarchy-aware — survives role
inheritance and secondary roles) or for the two dbt ETL roles (so dbt never
*persists* masked NULLs into staging/marts); everyone else gets NULL.
The policy is attached to the `GOVERNANCE.PII_FINANCIAL` **tag**, and the tag
is set on `ACCOUNT.ARR` (seed SQL) and re-applied by dbt post-hooks on every
downstream `arr` column — classifying a column IS protecting it, at every
layer, in all 10 future domains, with zero per-table policy wiring.

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

## Developer sandboxes (dbt-recommended)

Each developer gets a personal `REVOPS_DEV_<NAME>` schema — **DEV only,
never PROD** — as their dbt profile's `schema` target, so parallel `dbt run`s
never collide. This is namespace isolation, not security isolation: every
sandbox is granted to the shared `REVOPS_DEVELOPER` role, preserving the
users-hold-only-functional-roles invariant. Onboard a developer workspace:
add the name to the `developers` column of the `dev` row in
`config/environments.csv`, sync, apply. Remove the name to tear it down.

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

## Onboard a new DEVELOPER (e.g. SOURABH_SHINDE) — three CSV edits

1. `config/human_users.csv` — creates the Snowflake user:
   `sourabh,SOURABH_SHINDE,sourabh.shinde@opengov.com,...,REVOPS_DEVELOPER,...,true`
2. `config/environments.csv` — append to the DEV row's `developers` column:
   `dev,DEV,AKASH_PAHILWAN|SOURABH_SHINDE,true`
   → creates his personal dbt sandbox `OG_DEV_DB.REVOPS_DEV_SOURABH_SHINDE`
   (+ its `AR_DEV_REVOPS_DEV_SOURABH_SHINDE_R/W` access roles, auto-wired to
   `REVOPS_DEVELOPER` by the `REVOPS_DEV*` grant rule). DEV only — the PROD
   row's developers column stays empty by design.
3. `config/user_roles.csv` — one role does both envs:
   `sourabh_developer,SOURABH_SHINDE,REVOPS_DEVELOPER,true`
   → developer in DEV (writes his sandbox) **and** reader in PROD (STAGING +
   MARTS read-only; the sandbox-write grant is scoped `env=DEV`, so he has
   zero write paths in PROD — PROD writes belong to CI/CD).

After apply, verify:
`SHOW GRANTS TO USER SOURABH_SHINDE;` and
`SHOW SCHEMAS LIKE 'REVOPS_DEV%' IN DATABASE OG_DEV_DB;`

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
`SELECT * FROM TABLE(og_prod_db.information_schema.policy_references(policy_name => 'OG_PROD_DB.GOVERNANCE.MASK_ARR_NUMBER'));`

## How this scales to 10 domains

Everything above is domain-shaped: a new domain = one more spoke dbt project +
`MARTS_<DOMAIN>` schema + three functional roles + env-suffixed service roles,
all generated by the same module pattern. Masking scales through tags, not
policies: classify the column, protection follows.
