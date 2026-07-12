# ============================================================================
# Provider — snowflakedb/snowflake v2, key-pair (JWT) auth as OG_DEPLOYER.
# All secrets arrive via environment variables (TF_VAR_*) — nothing hardcoded:
#   TF_VAR_SF_ORGANIZATION_NAME, TF_VAR_SF_ACCOUNT_NAME,
#   TF_VAR_SF_USERNAME, TF_VAR_SF_PRIVATE_KEY
# State: local backend — deliberate for this POC (single operator, no team
# concurrency; secrets never enter state because users carry no passwords).
# Production would use S3 + DynamoDB locking.
# ============================================================================

terraform {
  required_version = ">= 1.6"
  required_providers {
    snowflake = {
      source  = "snowflakedb/snowflake"
      version = "~> 2.18"
    }
  }
}

provider "snowflake" {
  organization_name = var.SF_ORGANIZATION_NAME
  account_name      = var.SF_ACCOUNT_NAME
  user              = var.SF_USERNAME
  authenticator     = "SNOWFLAKE_JWT"
  private_key       = var.SF_PRIVATE_KEY
  role              = "OG_DEPLOYER" # bootstrap_deployer.sql created this

  # Several v2 resources are still gated behind preview flags in ~> 2.18
  # (same pattern as the SnowOps stack).
  preview_features_enabled = [
    "snowflake_storage_integration_resource",
    "snowflake_stage_resource",
    "snowflake_file_format_resource",
    "snowflake_table_resource",
  ]
}
