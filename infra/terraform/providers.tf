# ============================================================================
# Provider — snowflakedb/snowflake v2, key-pair (JWT) auth as OG_DEPLOYER.
# All secrets arrive via environment variables (TF_VAR_*) — nothing hardcoded:
#   TF_VAR_SF_ORGANIZATION_NAME, TF_VAR_SF_ACCOUNT_NAME,
#   TF_VAR_SF_USERNAME, TF_VAR_SF_PRIVATE_KEY
# State: remote azurerm backend — the state lives in the same ADLS storage
# account we already use for ingestion (snowopssa), in a dedicated POC container
# (og-tfstate). This lets GitHub Actions share state with local runs. Auth to
# the backend is the storage account access key via ARM_ACCESS_KEY (a GitHub
# secret / local env var), so no credentials are committed. Snowflake secrets
# still never enter state (users carry no passwords).
# ============================================================================

terraform {
  required_version = ">= 1.6"
  required_providers {
    snowflake = {
      source  = "snowflakedb/snowflake"
      version = "~> 2.18"
    }
  }

  backend "azurerm" {
    storage_account_name = "snowopssa"
    container_name       = "og-tfstate"
    key                  = "opengov-poc/terraform.tfstate"
    # access_key supplied out-of-band via ARM_ACCESS_KEY (never committed)
  }
}

provider "snowflake" {
  organization_name = var.SF_ORGANIZATION_NAME
  account_name      = var.SF_ACCOUNT_NAME
  user              = var.SF_USERNAME
  authenticator     = "SNOWFLAKE_JWT"
  private_key       = var.SF_PRIVATE_KEY
  role              = "OG_DEPLOYER"    # bootstrap_deployer.sql created this
  warehouse         = var.SF_WAREHOUSE # some resource reads (tags/policy refs) need compute

  # Several v2 resources are still gated behind preview flags in ~> 2.18
  # (same pattern as the SnowOps stack).
  preview_features_enabled = [
    "snowflake_storage_integration_resource",
    "snowflake_stage_resource",
    "snowflake_file_format_resource",
    "snowflake_table_resource",
    "snowflake_table_constraint_resource",
  ]
}
