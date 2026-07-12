-- ============================================================================
-- seed_salesforce_mock.sql — simulate what Fivetran has "already loaded".
--
-- The brief provides RAW.SALESFORCE.OPPORTUNITY / ACCOUNT as pre-existing
-- Fivetran output. In our layout that maps to:
--     OG_<ENV>_DB.SALESFORCE_RAW_FIVETRAN.{OPPORTUNITY, ACCOUNT}
--
-- Run per environment with Snowflake CLI templating (no hardcoded env):
--     snow sql -f infra/seed/seed_salesforce_mock.sql -D "env=DEV"
--     snow sql -f infra/seed/seed_salesforce_mock.sql -D "env=PROD"
--
-- Runs as OG_DEPLOYER: it owns SALESFORCE_RAW_FIVETRAN's Terraform-created
-- schema and the GOVERNANCE objects, so it can both create the mock tables
-- and wire the tag-based masking. (In real life Fivetran creates these
-- tables itself under OG_FIVETRAN_<ENV>.)
--
-- Idempotent: CREATE OR REPLACE + deterministic seed rows — safe to re-run.
-- ============================================================================

USE ROLE OG_DEPLOYER;
USE DATABASE OG_<% env %>_DB;
USE SCHEMA SALESFORCE_RAW_FIVETRAN;
USE WAREHOUSE OG_<% env %>_INGEST_XS_WH;

-- ── Mock Fivetran tables (schema exactly as provided in the brief) ──────────

CREATE OR REPLACE TABLE ACCOUNT (
    account_id        VARCHAR        COMMENT 'PK',
    account_name      VARCHAR,
    industry          VARCHAR        COMMENT 'e.g. Government, Education, Utilities',
    arr               NUMBER(18,2)   COMMENT 'Annual Recurring Revenue - PII-sensitive, masked via GOVERNANCE.PII_FINANCIAL tag',
    billing_state     VARCHAR        COMMENT 'US state code',
    customer_tier     VARCHAR        COMMENT 'Enterprise / Mid-Market / SMB',
    created_date      TIMESTAMP_NTZ,
    _fivetran_synced  TIMESTAMP_NTZ  COMMENT 'Fivetran metadata'
);

CREATE OR REPLACE TABLE OPPORTUNITY (
    opportunity_id      VARCHAR        COMMENT 'PK, Salesforce 18-char ID',
    account_id          VARCHAR        COMMENT 'FK to ACCOUNT',
    owner_id            VARCHAR        COMMENT 'Salesforce user ID',
    stage_name          VARCHAR        COMMENT 'Prospecting / Negotiation / Closed Won / ...',
    amount              NUMBER(18,2)   COMMENT 'USD deal value',
    close_date          DATE,
    created_date        TIMESTAMP_NTZ,
    last_modified_date  TIMESTAMP_NTZ,
    is_deleted          BOOLEAN        COMMENT 'soft-delete flag from Fivetran',
    _fivetran_synced    TIMESTAMP_NTZ  COMMENT 'Fivetran metadata'
);

-- ── Seed data (covers every dbt-test path: soft-deletes, all stage values,
--    messy stage_name casing/whitespace for the clean_string macro) ──────────

INSERT INTO ACCOUNT VALUES
  ('0011g00001AbCdEf', 'City of Springfield',  'Government', 480000.00, 'IL', 'Enterprise', '2024-03-11 09:15:00', CURRENT_TIMESTAMP()),
  ('0011g00001XyZabc', 'Lakeview School District', 'Education', 120000.00, 'MI', 'Mid-Market', '2024-07-02 14:40:00', CURRENT_TIMESTAMP()),
  ('0011g00001QqQqQq', 'Granite County',       'Government',  36000.00, 'MT', 'SMB',        '2025-01-20 11:05:00', CURRENT_TIMESTAMP()),
  ('0011g00001ZzZzZz', 'Harbor Utilities Co',  'Utilities',  245000.00, 'WA', 'Mid-Market', '2025-05-09 16:22:00', CURRENT_TIMESTAMP());

INSERT INTO OPPORTUNITY VALUES
  ('0061g000004AAAAA', '0011g00001AbCdEf', 'usr_owner_01', 'Prospecting',   50000.00, '2026-09-30', '2026-04-01 10:00:00', '2026-06-20 12:00:00', FALSE, CURRENT_TIMESTAMP()),
  ('0061g000004BBBBB', '0011g00001AbCdEf', 'usr_owner_01', '  negotiation ', 145000.00, '2026-08-15', '2026-02-15 09:30:00', '2026-07-01 15:45:00', FALSE, CURRENT_TIMESTAMP()),
  ('0061g000004CCCCC', '0011g00001XyZabc', 'usr_owner_02', 'Closed Won',    120000.00, '2026-05-31', '2025-11-10 08:20:00', '2026-06-01 10:10:00', FALSE, CURRENT_TIMESTAMP()),
  ('0061g000004DDDDD', '0011g00001QqQqQq', 'usr_owner_02', 'Qualification',  18000.00, '2026-12-31', '2026-05-05 13:00:00', '2026-07-08 09:00:00', FALSE, CURRENT_TIMESTAMP()),
  ('0061g000004EEEEE', '0011g00001ZzZzZz', 'usr_owner_03', 'Closed Lost',    90000.00, '2026-03-31', '2025-12-01 10:45:00', '2026-04-02 11:30:00', FALSE, CURRENT_TIMESTAMP()),
  ('0061g000004FFFFF', '0011g00001ZzZzZz', 'usr_owner_03', 'Prospecting',    60000.00, '2026-10-15', '2026-06-25 14:10:00', '2026-07-05 16:00:00', TRUE,  CURRENT_TIMESTAMP());

-- ── Wire tag-based masking ───────────────────────────────────────────────────
-- 1) Attach the masking policy to the tag (once per env; idempotent).
--    From here on, ANY column tagged PII_FINANCIAL with a NUMBER type is
--    masked automatically — this is the "scales to 10 domains" answer.
ALTER TAG GOVERNANCE.PII_FINANCIAL
  SET MASKING POLICY GOVERNANCE.MASK_ARR_NUMBER;

-- 2) Classify the column. Tagging IS protecting.
ALTER TABLE ACCOUNT MODIFY COLUMN arr
  SET TAG OG_<% env %>_DB.GOVERNANCE.PII_FINANCIAL = 'arr';

-- ── Hand the schema to its rightful owner ────────────────────────────────────
-- Future objects in this schema are owned by the Fivetran access role
-- (Terraform future-ownership grant), but these two seeded tables were
-- created by OG_DEPLOYER — transfer them so the grant model stays honest.
GRANT OWNERSHIP ON TABLE ACCOUNT     TO ROLE AR_<% env %>_SALESFORCE_RAW_FIVETRAN_W COPY CURRENT GRANTS;
GRANT OWNERSHIP ON TABLE OPPORTUNITY TO ROLE AR_<% env %>_SALESFORCE_RAW_FIVETRAN_W COPY CURRENT GRANTS;

-- ── Verification ─────────────────────────────────────────────────────────────
-- Masked path  (any role below REVOPS_ADMIN):  arr IS NULL
--   USE ROLE REVOPS_ANALYST;  SELECT account_name, arr FROM ...MARTS after dbt
-- Unmasked path:
--   USE ROLE REVOPS_ADMIN;    SELECT account_name, arr FROM ACCOUNT;
SELECT 'seeded ' || COUNT(*) || ' accounts into OG_<% env %>_DB.SALESFORCE_RAW_FIVETRAN.ACCOUNT' AS result
FROM ACCOUNT;
