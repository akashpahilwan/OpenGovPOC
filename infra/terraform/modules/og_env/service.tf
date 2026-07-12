# ============================================================================
# Service roles + service users — env-suffixed, one identity per pipeline.
#
# Unlike the human REVOPS_* functional roles (account-wide, one set), every
# automated identity is bound to exactly one environment: a DEV pipeline
# credential must never be able to touch PROD. Each service role composes
# access roles — it holds no direct object grants.
#
#   OG_FIVETRAN_<ENV>    W on SALESFORCE_RAW_FIVETRAN only   (connector DDL)
#   OG_INGEST_<ENV>      W on PRODUCT_EVENTS_RAW_S3 only     (Python loader)
#   OG_DBT_HUB_<ENV>     R on both RAW schemas, W on STAGING (hub project)
#   OG_DBT_REVOPS_<ENV>  R on STAGING, W on MARTS_REVOPS + REVOPS_DEV (spoke)
#
# dbt Mesh boundary enforced by RBAC: the RevOps spoke CANNOT read RAW —
# it can only build from the hub's published STAGING models.
# ============================================================================

locals {
  # From config/service_roles.csv (via root). Keyed by base name; personal
  # sandboxes are appended to the spoke's write set so developers' dbt runs
  # (executed under the spoke project pattern) can build there too.
  service_roles = {
    for name, cfg in var.service_roles : name => {
      comment   = cfg.comment
      read_ars  = cfg.read_schemas
      write_ars = name == "DBT_REVOPS" ? concat(cfg.write_schemas, keys(local.sandbox_schemas)) : cfg.write_schemas
      warehouse = cfg.warehouse
    }
  }

  dbt_project_roles = toset([for name, cfg in var.service_roles : name if cfg.dbt_project])

  role_read_pairs = merge([
    for r, cfg in local.service_roles : {
      for s in cfg.read_ars : "${r}.${s}" => { role = r, schema = s }
    }
  ]...)

  role_write_pairs = merge([
    for r, cfg in local.service_roles : {
      for s in cfg.write_ars : "${r}.${s}" => { role = r, schema = s }
    }
  ]...)
}

resource "snowflake_account_role" "service" {
  for_each = local.service_roles
  name     = "OG_${each.key}_${var.env}"
  comment  = each.value.comment
}

# ── Compose: access roles -> service roles ───────────────────────────────────

resource "snowflake_grant_account_role" "service_read" {
  for_each         = local.role_read_pairs
  role_name        = snowflake_account_role.ar_read[each.value.schema].name
  parent_role_name = snowflake_account_role.service[each.value.role].name
}

resource "snowflake_grant_account_role" "service_write" {
  for_each         = local.role_write_pairs
  role_name        = snowflake_account_role.ar_write[each.value.schema].name
  parent_role_name = snowflake_account_role.service[each.value.role].name
}

# Service roles roll up to SYSADMIN (Snowflake-recommended: no orphan branches).
resource "snowflake_grant_account_role" "service_to_sysadmin" {
  for_each         = local.service_roles
  role_name        = snowflake_account_role.service[each.key].name
  parent_role_name = "SYSADMIN"
}

# ── Warehouse usage — every size of the role's function ─────────────────────
# Jobs run on the XSMALL default; backfills/full refreshes opt into LARGE
# with USE WAREHOUSE. Same role, explicit escalation, per-second billing.

resource "snowflake_grant_privileges_to_account_role" "service_wh" {
  for_each = merge([
    for r, cfg in local.service_roles : {
      for wh in local.wh_by_function[cfg.warehouse] : "${r}.${wh}" => { role = r, wh = wh }
    }
  ]...)
  account_role_name = snowflake_account_role.service[each.value.role].name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = each.value.wh
  }
}

# ── dbt Projects on Snowflake ────────────────────────────────────────────────
# Both dbt service roles can create/execute native DBT PROJECT objects in the
# DBT schema. (The project object needs USAGE on the schemas it builds into —
# already covered by the access roles above.)

resource "snowflake_grant_privileges_to_account_role" "dbt_project_schema" {
  for_each          = local.dbt_project_roles
  account_role_name = snowflake_account_role.service[each.key].name
  privileges        = ["USAGE", "CREATE DBT PROJECT"]
  on_schema {
    schema_name = "\"${local.db_name}\".\"DBT\""
  }
  depends_on = [snowflake_schema.schema]
}

# ── Governance access for dbt ────────────────────────────────────────────────
# dbt re-applies the PII tag to arr columns it materializes (post-hook), so it
# needs USAGE on GOVERNANCE and APPLY on the tag. The masking policy follows
# the tag automatically — dbt never touches the policy itself.

resource "snowflake_grant_privileges_to_account_role" "dbt_governance_usage" {
  for_each          = local.dbt_project_roles
  account_role_name = snowflake_account_role.service[each.key].name
  privileges        = ["USAGE"]
  on_schema {
    schema_name = "\"${local.db_name}\".\"GOVERNANCE\""
  }
  depends_on = [snowflake_schema.schema]
}

# APPLY on every governance tag — dbt re-tags derived columns of any
# classification (PII_FINANCIAL, PII_CONTACT, ...) as it materializes models.
resource "snowflake_grant_privileges_to_account_role" "dbt_apply_tag" {
  for_each = merge([
    for role in local.dbt_project_roles : {
      for tag in keys(snowflake_tag.tag) : "${role}.${tag}" => { role = role, tag = tag }
    }
  ]...)
  account_role_name = snowflake_account_role.service[each.value.role].name
  privileges        = ["APPLY"]
  on_schema_object {
    object_type = "TAG"
    object_name = "\"${local.db_name}\".\"GOVERNANCE\".\"${each.value.tag}\""
  }
}

# ── Service users — TYPE=SERVICE, key-pair only, no passwords ────────────────
# RSA public keys are attached later, one per pipeline, via ALTER USER (kept
# out of Terraform so key rotation never requires a terraform apply).

resource "snowflake_service_user" "svc" {
  for_each          = local.service_roles
  name              = "OG_${each.key}_SVC_${var.env}"
  default_role      = snowflake_account_role.service[each.key].name
  default_warehouse = local.wh_default[each.value.warehouse]
  comment           = "OpenGov POC ${var.env} - ${each.value.comment}"
}

resource "snowflake_grant_account_role" "svc_user_role" {
  for_each  = local.service_roles
  role_name = snowflake_account_role.service[each.key].name
  user_name = snowflake_service_user.svc[each.key].name
}
