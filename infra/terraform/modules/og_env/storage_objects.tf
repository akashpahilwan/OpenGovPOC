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

# ── RAW telemetry tables — the brief's PAGE_VIEWS + _QUARANTINE + _LOAD_LOG ──
# Schema-on-read: contract keys promoted to typed columns (dedup/pruning),
# the full event lands in payload VARIANT. New upstream fields need no DDL.

resource "snowflake_table" "page_views" {
  name     = "PAGE_VIEWS"
  database = snowflake_database.db.name
  schema   = "PRODUCT_EVENTS_RAW_ADLS"
  comment  = "Telemetry landing - append-only; dedup on event_id happens in dbt staging"

  column {
    name = "EVENT_ID"
    type = "VARCHAR"
  }
  column {
    name = "ACCOUNT_ID"
    type = "VARCHAR"
  }
  column {
    name = "EVENT_TIMESTAMP"
    type = "TIMESTAMP_NTZ"
  }
  column {
    name = "PAYLOAD"
    type = "VARIANT"
  }
  column {
    name = "_FILENAME"
    type = "VARCHAR"
  }
  column {
    name = "_LOADED_AT"
    type = "TIMESTAMP_NTZ"
  }

  depends_on = [snowflake_schema.schema]
}

resource "snowflake_table" "quarantine" {
  name     = "PAGE_VIEWS_QUARANTINE"
  database = snowflake_database.db.name
  schema   = "PRODUCT_EVENTS_RAW_ADLS"
  comment  = "Records failing contract validation (missing event_id/account_id/event_timestamp)"

  column {
    name = "REASON"
    type = "VARCHAR"
  }
  column {
    name = "PAYLOAD"
    type = "VARIANT"
  }
  column {
    name = "_FILENAME"
    type = "VARCHAR"
  }
  column {
    name = "_QUARANTINED_AT"
    type = "TIMESTAMP_NTZ"
  }

  depends_on = [snowflake_schema.schema]
}

resource "snowflake_table" "load_log" {
  name     = "PAGE_VIEWS_LOAD_LOG"
  database = snowflake_database.db.name
  schema   = "PRODUCT_EVENTS_RAW_ADLS"
  comment  = "One summary row per ingestion run - the audit trail that outlives COPY_HISTORY retention"

  column {
    name = "FILE_NAME"
    type = "VARCHAR"
  }
  column {
    name = "RECORDS_PROCESSED"
    type = "NUMBER(18,0)"
  }
  column {
    name = "RECORDS_QUARANTINED"
    type = "NUMBER(18,0)"
  }
  column {
    name = "LOAD_TIMESTAMP"
    type = "TIMESTAMP_NTZ"
  }

  depends_on = [snowflake_schema.schema]
}
