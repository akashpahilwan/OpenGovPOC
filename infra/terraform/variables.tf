# ── Connection (from environment: TF_VAR_<name>) ────────────────────────────
# Everything else — environments, schemas, roles, grants, users — comes from
# infra/config/*.csv via sync_config.py. No object lists live in HCL.

variable "SF_ORGANIZATION_NAME" {
  type        = string
  description = "Snowflake organization name (env: TF_VAR_SF_ORGANIZATION_NAME)"
}

variable "SF_ACCOUNT_NAME" {
  type        = string
  description = "Snowflake account name (env: TF_VAR_SF_ACCOUNT_NAME)"
}

variable "SF_USERNAME" {
  type        = string
  description = "Deployer service user (env: TF_VAR_SF_USERNAME)"
  default     = "OG_DEPLOYER_SVC"
}

variable "SF_PRIVATE_KEY" {
  type        = string
  sensitive   = true
  description = "PEM private key for key-pair auth (env: TF_VAR_SF_PRIVATE_KEY)"
}
