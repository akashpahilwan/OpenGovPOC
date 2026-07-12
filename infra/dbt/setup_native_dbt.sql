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

-- 2) Git repository object (in the DBT schema) + fetch the latest.
CREATE OR REPLACE GIT REPOSITORY OG_DEV_DB.DBT.OG_DBT_HUB_REPO
  API_INTEGRATION = OG_GIT_API
  ORIGIN = 'https://github.com/akashpahilwan/opengov-dbt-hub.git';
ALTER GIT REPOSITORY OG_DEV_DB.DBT.OG_DBT_HUB_REPO FETCH;

-- 3) Native DBT PROJECT object from the repo's main branch.
CREATE OR REPLACE DBT PROJECT OG_DEV_DB.DBT.OG_HUB
  FROM '@OG_DEV_DB.DBT.OG_DBT_HUB_REPO/branches/main';

-- 4) Run it (build = run models + tests). Verified: PASS=19 WARN=0 ERROR=0.
--    staging -> OG_DEV_DB.STAGING (views), marts -> OG_DEV_DB.MARTS_REVOPS.
EXECUTE DBT PROJECT OG_DEV_DB.DBT.OG_HUB ARGS = 'build --target dev';

-- Re-sync after a repo push: ALTER GIT REPOSITORY ... FETCH; then EXECUTE again
-- (or CREATE OR REPLACE DBT PROJECT to pick up structural changes).
-- CI/CD (Task 4) triggers steps 2-4 on merge to main.
