# ============================================================================
# Deployer-owned ingestion contract objects: file formats, stages, RAW tables.
#
# These are the platform's side of the schema-on-read contract for the ADLS
# telemetry path. The tables have STABLE DDL (promoted keys + payload VARIANT)
# and change only via a reviewed PR to this repo — the ingestion service role
# gets DML on them but never ownership, so a compromised or buggy loader
# cannot ALTER or DROP the contract.
# ============================================================================

# ── File formats ─────────────────────────────────────────────────────────────

resource "snowflake_file_format" "ff" {
  for_each    = { for k, v in var.file_formats : k => v if v.is_active }
  name        = each.value.name
  database    = snowflake_database.db.name
  schema      = each.value.schema
  format_type = each.value.format_type

  # telemetry files are JSON arrays — one row per event
  strip_outer_array = each.value.format_type == "JSON" ? true : null

  comment    = each.value.comment
  depends_on = [snowflake_schema.schema]
}

# ── Stages ({env} in the URL -> this env's path prefix) ──────────────────────

resource "snowflake_stage" "stage" {
  for_each            = { for k, v in var.stages : k => v if v.is_active }
  name                = each.value.name
  database            = snowflake_database.db.name
  schema              = each.value.schema
  url                 = each.value.stage_type == "EXTERNAL" ? replace(each.value.url, "{env}", lower(var.env)) : null
  storage_integration = each.value.stage_type == "EXTERNAL" ? each.value.storage_integration : null
  comment             = each.value.comment
  depends_on          = [snowflake_schema.schema]
}

# ── RAW tables for CUSTOM ingestion schemas — SnowOps-style manifests ────────
# config/tables.csv is the manifest; resources/tables/<key>.json holds each
# table's column definitions (hand-authored). Only for schemas the platform
# owns (ADLS landing) — Fivetran-owned schemas never appear here, the
# connector manages that DDL. Schema-on-read: contract keys are promoted
# typed columns, the full event lands in payload VARIANT.

resource "snowflake_table" "table" {
  for_each        = { for k, v in var.tables : k => v if v.is_active }
  name            = each.value.name
  database        = snowflake_database.db.name
  schema          = each.value.schema
  comment         = each.value.comment
  change_tracking = each.value.change_tracking

  dynamic "column" {
    for_each = jsondecode(file("${path.root}/../resources/tables/${each.key}.json")).columns
    content {
      name     = column.value["name"]
      type     = column.value["type"]
      nullable = lookup(column.value, "nullable", true)
      comment  = lookup(column.value, "comment", null)

      dynamic "default" {
        for_each = contains(keys(column.value), "default") ? [column.value.default] : []
        content {
          expression = lookup(default.value, "expression", null)
          constant   = lookup(default.value, "constant", null)
        }
      }
    }
  }

  depends_on = [snowflake_schema.schema]
}

# Optional primary keys (resources/tables/<key>.json: table_config.primary_key).
# RAW landing tables deliberately have none — append-only; dedup is downstream.
resource "snowflake_table_constraint" "primary_key" {
  for_each = {
    for k, v in var.tables : k => v
    if v.is_active && contains(keys(jsondecode(file("${path.root}/../resources/tables/${k}.json")).table_config), "primary_key")
  }
  name       = "${each.value.name}_PK"
  table_id   = "\"${snowflake_database.db.name}\".\"${each.value.schema}\".\"${each.value.name}\""
  type       = "PRIMARY KEY"
  columns    = jsondecode(file("${path.root}/../resources/tables/${each.key}.json")).table_config.primary_key
  enable     = false
  deferrable = false
  depends_on = [snowflake_table.table]
}
