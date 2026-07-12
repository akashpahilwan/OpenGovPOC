# ============================================================================
# og_env — database, schemas, warehouses for one environment.
#
# Layout decision (owner): ONE database per environment (OG_DEV_DB / OG_QA_DB
# / OG_PROD_DB), with layer separation done at SCHEMA level. RAW schemas are
# named <SOURCE>_RAW_<INGESTION_TYPE> so that write/DDL grants can be scoped
# to exactly one loader per schema:
#   SALESFORCE_RAW_FIVETRAN  -> only the Fivetran identity can write/alter
#   PRODUCT_EVENTS_RAW_S3    -> only the Python ingestion identity can
# dbt owns STAGING (hub project) and MARTS_REVOPS (RevOps spoke project).
# ============================================================================

terraform {
  required_providers {
    snowflake = {
      source  = "snowflakedb/snowflake"
      version = "~> 2.18"
    }
  }
}

locals {
  db_name = "OG_${var.env}_DB"

  # Individual dbt sandboxes — dbt-recommended schema-per-developer dev pattern.
  sandbox_schemas = {
    for d in var.developers :
    "REVOPS_DEV_${upper(d)}" => { comment = "Personal dbt sandbox for ${upper(d)} - namespace isolation, shared REVOPS_DEVELOPER access" }
  }

  # Config-driven schemas (config/schemas.csv) + generated sandboxes.
  schemas = merge(
    { for s, cfg in var.schemas : s => { comment = cfg.comment } },
    local.sandbox_schemas,
  )

  # Only DATA-kind schemas get R/W access-role pairs; GOVERNANCE and DBT are
  # special-cased (governance is policy-only, DBT holds project objects).
  data_schemas = concat(
    [for s, cfg in var.schemas : s if cfg.kind == "DATA"],
    keys(local.sandbox_schemas),
  )
}

resource "snowflake_database" "db" {
  name    = local.db_name
  comment = "OpenGov POC - ${var.env} environment (all layers as schemas)"
}

resource "snowflake_schema" "schema" {
  for_each = local.schemas
  database = snowflake_database.db.name
  name     = each.key
  comment  = each.value.comment
}

resource "snowflake_warehouse" "wh" {
  for_each       = { for k, v in var.warehouses : k => v if v.is_active }
  name           = "OG_${var.env}_${upper(each.key)}_WH"
  warehouse_size = each.value.size
  auto_suspend   = each.value.auto_suspend
  auto_resume    = true
  comment        = "OpenGov POC ${var.env} - ${each.value.comment}"
}

locals {
  # function => every warehouse name of that function (roles get USAGE on all)
  wh_by_function = {
    for fn in distinct([for k, v in var.warehouses : v.function if v.is_active]) :
    fn => [for k, v in var.warehouses : snowflake_warehouse.wh[k].name if v.is_active && v.function == fn]
  }
  # function => the default (XSMALL) warehouse — service users' default
  wh_default = {
    for k, v in var.warehouses : v.function => snowflake_warehouse.wh[k].name
    if v.is_active && v.is_default
  }
}
