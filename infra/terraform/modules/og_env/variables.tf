# ── og_env module inputs ─────────────────────────────────────────────────────
# One instance of this module = one fully-provisioned environment:
# OG_<ENV>_DB + schemas + warehouses + access roles + service roles/users
# + governance objects (masking policy, PII tag).

variable "env" {
  type        = string
  description = "Environment name — DEV / QA / PROD. Drives every object name."
  validation {
    condition     = contains(["DEV", "QA", "PROD"], var.env)
    error_message = "env must be one of DEV, QA, PROD."
  }
}

variable "warehouses" {
  type = map(object({
    function     = string # INGEST | TRANSFORM | ANALYTICS — what roles bind to
    size         = string
    auto_suspend = number
    is_default   = bool # exactly one per function; becomes service users' default warehouse
    comment      = string
    is_active    = bool
  }))
  description = <<-EOT
    Warehouses for this env, keyed by short name (ingest_xs, ingest_l, ...) —
    from config/warehouses.csv. Each becomes OG_<ENV>_<KEY>_WH. Two sizes per
    pipeline function: roles get USAGE on every warehouse of their function;
    jobs run on the default (XSMALL) and opt into LARGE explicitly for
    backfills / full refreshes via USE WAREHOUSE.
  EOT
}

variable "developers" {
  type        = list(string)
  default     = []
  description = <<-EOT
    Developer names that get an individual dbt sandbox schema
    (REVOPS_DEV_<NAME>) — the dbt-recommended one-schema-per-developer dev
    pattern, so parallel `dbt run`s never collide. Namespace isolation only:
    every sandbox is granted to the shared REVOPS_DEVELOPER role; each
    developer's dbt profile targets their own schema. Comes from the
    `developers` column of config/environments.csv (normally DEV only).
  EOT
}

variable "schemas" {
  type = map(object({
    kind               = string # DATA (gets R/W access roles) | GOVERNANCE | DBT
    writer_owns_future = bool   # true: W role owns what it creates (Fivetran/dbt); false: platform owns DDL, W role gets DML only (ADLS landing)
    comment            = string
    is_active          = bool
  }))
  description = "Schemas for this env DB, keyed by schema name — from config/schemas.csv."
}

variable "stages" {
  type = map(object({
    name                = string
    schema              = string
    stage_type          = string # EXTERNAL | INTERNAL
    url                 = string # {env} placeholder -> lowercase env prefix
    storage_integration = string
    comment             = string
    is_active           = bool
  }))
  default     = {}
  description = "Stages to create in this env — from config/stages.csv."
}

variable "tables" {
  type = map(object({
    name            = string
    schema          = string
    change_tracking = bool
    comment         = string
    is_active       = bool
  }))
  default     = {}
  description = <<-EOT
    Deployer-owned RAW tables for custom-ingestion schemas — from
    config/tables.csv; column definitions in resources/tables/<key>.json
    (SnowOps pattern). Never used for Fivetran-owned schemas.
  EOT
}

variable "masking_rules" {
  type = map(object({
    tag             = string
    allowed_values  = list(string)
    data_type       = string
    mask_expression = string # ELSE branch — references VAL, returns data_type
    policy_name     = string # derived in sync_config.py (MASK_<tag>_<basetype>)
    comment         = string
    is_active       = bool
  }))
  default     = {}
  description = <<-EOT
    The masking VOCABULARY — from config/masking_rules.csv. One row per
    (tag, data_type): generates a tag (deduped across rows) and a masking
    policy whose non-exempt branch is mask_expression. Adding a rule is a
    CSV row; no HCL changes.
  EOT
}

variable "masking_exemptions" {
  type = map(object({
    tag       = string
    role_type = string # FUNCTIONAL (literal role name) | SERVICE (base name, env-expanded)
    role      = string
    is_active = bool
  }))
  default     = {}
  description = <<-EOT
    WHO SEES UNMASKED PII — from config/masking_exemptions.csv. Each active row
    exempts a role from the masking policy attached to that tag. FUNCTIONAL
    roles are account-wide names (REVOPS_ADMIN); SERVICE roles are base names
    expanded to this env (DBT_HUB -> OG_DBT_HUB_<ENV>). Everyone else gets NULL.
    Users are never exempted directly — grant them an exempt role instead
    (user_roles.csv), so offboarding stays a single role revoke.
  EOT
}

variable "file_formats" {
  type = map(object({
    name        = string
    schema      = string
    format_type = string
    comment     = string
    is_active   = bool
  }))
  default     = {}
  description = "File formats to create in this env — from config/file_formats.csv."
}

