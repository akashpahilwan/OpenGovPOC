-- ============================================================================
-- bootstrap_deployer.sql — ONE-TIME setup, run as ACCOUNTADMIN.
--
-- Creates the OG_DEPLOYER role + service user that Terraform authenticates as.
-- Everything else (databases, schemas, warehouses, roles, grants, policies)
-- is created BY Terraform running as OG_DEPLOYER — so the entire OpenGov POC
-- footprint is owned by one role and can be torn down cleanly.
--
-- WHY a dedicated deployer instead of SYSADMIN: blast-radius isolation. This
-- account also hosts SnowOps objects; OG_DEPLOYER can only manage what it
-- creates, and revoking one role kills the whole pipeline's write path.
--
-- Before running: generate a key pair and paste the public key below.
--   openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out og_deployer_rsa_key.p8 -nocrypt
--   openssl rsa -in og_deployer_rsa_key.p8 -pubout -out og_deployer_rsa_key.pub
-- ============================================================================

USE ROLE ACCOUNTADMIN;

-- Deployer role: account-level create rights, granted up to SYSADMIN so the
-- platform team keeps visibility over everything the deployer owns.
CREATE ROLE IF NOT EXISTS OG_DEPLOYER
  COMMENT = 'OpenGov POC - Terraform deployer. Owns all OG_* objects.';

GRANT CREATE DATABASE    ON ACCOUNT TO ROLE OG_DEPLOYER;
GRANT CREATE WAREHOUSE   ON ACCOUNT TO ROLE OG_DEPLOYER;
GRANT CREATE ROLE        ON ACCOUNT TO ROLE OG_DEPLOYER;
GRANT CREATE USER        ON ACCOUNT TO ROLE OG_DEPLOYER;
-- Storage integrations (ADLS) are account-level objects deployed by Terraform.
GRANT CREATE INTEGRATION ON ACCOUNT TO ROLE OG_DEPLOYER;
-- MANAGE GRANTS lets Terraform grant roles/privileges it does not own
-- (e.g. wiring access roles into functional roles).
GRANT MANAGE GRANTS    ON ACCOUNT TO ROLE OG_DEPLOYER;

GRANT ROLE OG_DEPLOYER TO ROLE SYSADMIN;

-- Service user for Terraform / CI. TYPE = SERVICE: no password, no MFA —
-- key-pair (JWT) auth only, which is what the GitHub Actions pipeline uses.
CREATE USER IF NOT EXISTS OG_DEPLOYER_SVC
  TYPE              = SERVICE
  DEFAULT_ROLE      = OG_DEPLOYER
  RSA_PUBLIC_KEY    = '<PASTE_PUBLIC_KEY_BODY_HERE>'   -- key body only, no header/footer lines
  COMMENT           = 'OpenGov POC - Terraform/CI service identity (key-pair auth only)';

GRANT ROLE OG_DEPLOYER TO USER OG_DEPLOYER_SVC;
