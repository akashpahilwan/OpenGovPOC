-- ============================================================================
-- setup_native_dbt.sql — wire the HUB dbt repo into Snowflake's NATIVE dbt.
--
-- The dbt code lives in its own isolated repo (github.com/akashpahilwan/
-- opengov-dbt-hub, public — no secrets in dbt code). Snowflake pulls it via a
-- Git API integration and runs it in-account as a DBT PROJECT object. No
-- dbt-core CI runner; the warehouse does the work.
--
-- Run as OG_DEPLOYER (has CREATE INTEGRATION). The DBT PROJECT executes as
-- REVOPS_DEVELOPER (per the project's profiles.yml target) — the service-only
-- role that owns STAGING + MARTS_REVOPS writes; OG_DBT_SVC holds it in prod.
-- Repeat per env (OG_DEV_DB / OG_PROD_DB); DEV shown.
-- ============================================================================

USE ROLE OG_DEPLOYER;

-- 1) Git API integration (public repo -> no secret/PAT needed).
CREATE API INTEGRATION IF NOT EXISTS OG_GIT_API
  API_PROVIDER = git_https_api
  API_ALLOWED_PREFIXES = ('https://github.com/akashpahilwan')
  ENABLED = TRUE;

-- Branch-per-env model (1 repo, 2 long-lived branches):
--   dev  branch -> OG_DEV_DB  project, built with --target preprod (integration/QA)
--   main branch -> OG_PROD_DB project, built with --target prod
-- Developers cut feature branches off dev and work in their sandbox (--target dev).

-- 2) Git repository object (per env DBT schema) + fetch.  [DEV shown; for PROD
--    swap OG_DEV_DB -> OG_PROD_DB]
CREATE OR REPLACE GIT REPOSITORY OG_DEV_DB.DBT.OG_DBT_HUB_REPO
  API_INTEGRATION = OG_GIT_API
  ORIGIN = 'https://github.com/akashpahilwan/opengov-dbt-hub.git';
ALTER GIT REPOSITORY OG_DEV_DB.DBT.OG_DBT_HUB_REPO FETCH;

-- 3) DBT PROJECT pinned to this env's branch (DEV<-dev, PROD<-main).
CREATE OR REPLACE DBT PROJECT OG_DEV_DB.DBT.OG_HUB
  FROM '@OG_DEV_DB.DBT.OG_DBT_HUB_REPO/branches/dev';

-- 4) Integration build (DEV=preprod target -> OG_DEV_DB.STAGING/MARTS_REVOPS).
--    Verified: PASS=20 WARN=0 ERROR=0.  PROD would be: ... branches/main / --target prod.
EXECUTE DBT PROJECT OG_DEV_DB.DBT.OG_HUB ARGS = 'build --target preprod';

-- ── HOW THIS RUNS (CI, not scheduled TASK) ──────────────────────────────────
-- opengov-dbt-hub/.github/workflows/deploy.yml runs ci/deploy_dbt.py on push:
--   push dev  -> FETCH + CREATE OR REPLACE DBT PROJECT (branches/dev)  + EXECUTE build --target preprod
--   push main -> same against OG_PROD_DB (branches/main)               + EXECUTE build --target prod
-- CI identity = OG_DBT_SVC (holds REVOPS_DEVELOPER), key-pair via GitHub secrets.

-- ── DEVELOPER / AD-HOC COMMANDS (interactive, --target dev -> own sandbox) ───
-- In a Snowflake Workspace on a feature branch developers run dbt directly; the
-- same commands are available via EXECUTE DBT PROJECT with ARGS (from a personal
-- DBT PROJECT pinned to their branch, or the dev project):
--   install packages :  EXECUTE DBT PROJECT OG_DEV_DB.DBT.OG_HUB ARGS='deps';
--   one model        :  EXECUTE DBT PROJECT OG_DEV_DB.DBT.OG_HUB ARGS='run --select mart_revops__pipeline --target dev';
--   model + upstream :  ... ARGS='run --select +mart_revops__pipeline --target dev';
--   a layer          :  ... ARGS='build --select staging --target dev';
--   only what changed:  ... ARGS='build --select state:modified+ --target dev';   -- needs --state
--   test one model   :  ... ARGS='test --select stg_salesforce__opportunities --target dev';
--   full refresh incr:  ... ARGS='build --select stg_salesforce__accounts --full-refresh --target dev';
--   whole project    :  ... ARGS='build --target dev';
-- --target dev -> models land in the developer's sandbox (REVOPS_DEV_<NAME>) as
-- <schema>__<model>; reads use REVOPS_READER (financials are masked in dev).

-- Re-sync after a push: ALTER GIT REPOSITORY ... FETCH; CREATE OR REPLACE DBT
-- PROJECT ...; EXECUTE ...  (this is exactly what the CI does).
