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

-- Central-governance rights for apply_pii_tags.py (runs as OG_DEPLOYER):
--   APPLY MASKING POLICY -> ALTER TAG ... SET MASKING POLICY (tag<->policy bind)
--   APPLY TAG            -> ALTER TABLE ... SET TAG on any object, even ones
--                          whose ownership the seed transfers to the AR_*_W role.
GRANT APPLY MASKING POLICY ON ACCOUNT TO ROLE OG_DEPLOYER;
GRANT APPLY TAG            ON ACCOUNT TO ROLE OG_DEPLOYER;

GRANT ROLE OG_DEPLOYER TO ROLE SYSADMIN;

-- Deployer's own tiny warehouse. Terraform needs an active warehouse in the
-- session for a few resource reads (e.g. tag policy references), and this must
-- exist BEFORE the first apply — so it lives here, not in Terraform. Owned by
-- OG_DEPLOYER (ownership implies USAGE).
CREATE WAREHOUSE IF NOT EXISTS OG_DEPLOYER_WH
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND   = 60
  AUTO_RESUME    = TRUE
  INITIALLY_SUSPENDED = TRUE
  COMMENT = 'OpenGov POC - Terraform/CI deployer session compute';
GRANT USAGE ON WAREHOUSE OG_DEPLOYER_WH TO ROLE OG_DEPLOYER;

-- Service user for Terraform / CI. TYPE = SERVICE: no password, no MFA —
-- key-pair (JWT) auth only, which is what the GitHub Actions pipeline uses.
CREATE USER IF NOT EXISTS OG_DEPLOYER_SVC
  TYPE              = SERVICE
  DEFAULT_ROLE      = OG_DEPLOYER
  RSA_PUBLIC_KEY    = 'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAtCvx6sQbTllp4KCB6vH9leLT3kN/dc0o/yRpIiGxNZOncR2URFUkYmMWxmVaTD15HN3XDf9zhcDCGElyldZRl/GkcILCNENKlJCI0BvKWMYBsPKGy6228d17e81KTnRex+7r5y+de9XYGJObrrQQxTHGDEQuaiCwcYXnBso1w6JrSxFzJbUVQkMwUTYRPgz2y8AWKFbM7iWOZf81k3NPxa9/eyDcW4LtQ1zfRDBWHeoBM4Mg9sqXvKmXqjf3hKT9bgSwIAXtm9XEoYgjn6zHDmw6O5K2EynA3N9DdJBh/teDKT8ASeM5YtWsZBWpk88ig0Yz3IOV8UnjwLLlWFZVRQIDAQAB'
  COMMENT           = 'OpenGov POC - Terraform/CI service identity (key-pair auth only)';

GRANT ROLE OG_DEPLOYER TO USER OG_DEPLOYER_SVC;
