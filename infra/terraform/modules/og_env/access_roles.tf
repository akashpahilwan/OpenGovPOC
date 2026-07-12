# ============================================================================
# Access roles — tier 1 of the Snowflake-recommended two-tier hierarchy.
#
# One R (read) and one W (write) role per data schema per environment:
#   AR_<ENV>_<SCHEMA>_R   USAGE + SELECT on all current/future tables & views
#   AR_<ENV>_<SCHEMA>_W   two flavors, by schemas.csv writer_owns_future:
#
#   writer_owns_future = true  (Fivetran schema, dbt schemas, sandboxes)
#     all schema privileges (every CREATE) + FUTURE OWNERSHIP of what it
#     creates — Fivetran manages its own DDL; dbt needs CREATE OR REPLACE.
#
#   writer_owns_future = false (ADLS telemetry landing)
#     DML ONLY on the deployer-owned contract objects: the platform (this
#     Terraform) owns tables/stages/file formats; the loader can SELECT/
#     INSERT/DELETE and use stages/formats but can never ALTER or DROP the
#     contract. (SnowOps "SVC" pattern.)
#
# Access roles are never granted to users — only to functional/service roles.
# ============================================================================

locals {
  # schema => does the writer own future objects? (sandboxes: always true)
  writer_owns = merge(
    { for s, cfg in var.schemas : s => cfg.writer_owns_future if cfg.kind == "DATA" },
    { for s in keys(local.sandbox_schemas) : s => true },
  )

  owner_schemas = [for s in local.data_schemas : s if local.writer_owns[s]]
  dml_schemas   = [for s in local.data_schemas : s if !local.writer_owns[s]]

  ar_read  = { for s in local.data_schemas : s => "AR_${var.env}_${s}_R" }
  ar_write = { for s in local.data_schemas : s => "AR_${var.env}_${s}_W" }

  # (schema, object-type) helper maps for for_each fan-outs
  rw_tables_views = merge([
    for s in local.data_schemas : {
      "${s}.TABLES" = { schema = s, plural = "TABLES" }
      "${s}.VIEWS"  = { schema = s, plural = "VIEWS" }
    }
  ]...)

  owner_futures = merge([
    for s in local.owner_schemas : {
      "${s}.TABLES" = { schema = s, plural = "TABLES" }
      "${s}.VIEWS"  = { schema = s, plural = "VIEWS" }
      "${s}.STAGES" = { schema = s, plural = "STAGES" }
    }
  ]...)
}

resource "snowflake_account_role" "ar_read" {
  for_each = local.ar_read
  name     = each.value
  comment  = "Access role - read ${local.db_name}.${each.key}"
}

resource "snowflake_account_role" "ar_write" {
  for_each = local.ar_write
  name     = each.value
  comment  = "Access role - write ${local.db_name}.${each.key} (${local.writer_owns[each.key] ? "owns what it creates" : "DML only - platform owns DDL"})"
}

# ── Database USAGE — every access role can see the database ──────────────────

resource "snowflake_grant_privileges_to_account_role" "db_usage_r" {
  for_each          = local.ar_read
  account_role_name = snowflake_account_role.ar_read[each.key].name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.db.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "db_usage_w" {
  for_each          = local.ar_write
  account_role_name = snowflake_account_role.ar_write[each.key].name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.db.name
  }
}

# ── R: schema USAGE + SELECT on existing and future tables/views ─────────────

resource "snowflake_grant_privileges_to_account_role" "r_schema_usage" {
  for_each          = local.ar_read
  account_role_name = snowflake_account_role.ar_read[each.key].name
  privileges        = ["USAGE"]
  on_schema {
    schema_name = "\"${local.db_name}\".\"${each.key}\""
  }
  depends_on = [snowflake_schema.schema]
}

resource "snowflake_grant_privileges_to_account_role" "r_existing" {
  for_each          = local.rw_tables_views
  account_role_name = snowflake_account_role.ar_read[each.value.schema].name
  privileges        = ["SELECT"]
  on_schema_object {
    all {
      object_type_plural = each.value.plural
      in_schema          = "\"${local.db_name}\".\"${each.value.schema}\""
    }
  }
  depends_on = [snowflake_schema.schema]
}

resource "snowflake_grant_privileges_to_account_role" "r_future" {
  for_each          = local.rw_tables_views
  account_role_name = snowflake_account_role.ar_read[each.value.schema].name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = each.value.plural
      in_schema          = "\"${local.db_name}\".\"${each.value.schema}\""
    }
  }
  depends_on = [snowflake_schema.schema]
}

# ═══════════════════ W flavor 1 — writer OWNS its objects ════════════════════

# Full schema privileges (every CREATE type)
resource "snowflake_grant_privileges_to_account_role" "w_schema_all" {
  for_each          = toset(local.owner_schemas)
  account_role_name = snowflake_account_role.ar_write[each.key].name
  all_privileges    = true
  on_schema {
    schema_name = "\"${local.db_name}\".\"${each.key}\""
  }
  depends_on = [snowflake_schema.schema]
}

# DML + SELECT on objects that existed before the role (e.g. seeded tables)
resource "snowflake_grant_privileges_to_account_role" "w_existing_tables" {
  for_each          = toset(local.owner_schemas)
  account_role_name = snowflake_account_role.ar_write[each.key].name
  all_privileges    = true
  on_schema_object {
    all {
      object_type_plural = "TABLES"
      in_schema          = "\"${local.db_name}\".\"${each.key}\""
    }
  }
  depends_on = [snowflake_schema.schema]
}

# Future ownership — writers own (so can ALTER/DROP) what they create.
resource "snowflake_grant_ownership" "w_future" {
  for_each          = local.owner_futures
  account_role_name = snowflake_account_role.ar_write[each.value.schema].name
  on {
    future {
      object_type_plural = each.value.plural
      in_schema          = "\"${local.db_name}\".\"${each.value.schema}\""
    }
  }
  depends_on = [snowflake_schema.schema]
}

# ═════════════ W flavor 2 — DML only, platform owns the contract ═════════════

resource "snowflake_grant_privileges_to_account_role" "w_dml_schema_usage" {
  for_each          = toset(local.dml_schemas)
  account_role_name = snowflake_account_role.ar_write[each.key].name
  privileges        = ["USAGE"]
  on_schema {
    schema_name = "\"${local.db_name}\".\"${each.key}\""
  }
  depends_on = [snowflake_schema.schema]
}

resource "snowflake_grant_privileges_to_account_role" "w_dml_existing_tables" {
  for_each          = toset(local.dml_schemas)
  account_role_name = snowflake_account_role.ar_write[each.key].name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  on_schema_object {
    all {
      object_type_plural = "TABLES"
      in_schema          = "\"${local.db_name}\".\"${each.key}\""
    }
  }
  depends_on = [snowflake_schema.schema, snowflake_table.page_views, snowflake_table.quarantine, snowflake_table.load_log]
}

resource "snowflake_grant_privileges_to_account_role" "w_dml_future_tables" {
  for_each          = toset(local.dml_schemas)
  account_role_name = snowflake_account_role.ar_write[each.key].name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_schema          = "\"${local.db_name}\".\"${each.key}\""
    }
  }
  depends_on = [snowflake_schema.schema]
}

# Stages: use, list, read files (+ WRITE for PUT to internal stages)
resource "snowflake_grant_privileges_to_account_role" "w_dml_stages" {
  for_each = merge([
    for s in local.dml_schemas : {
      "${s}.all"    = { schema = s, scope = "all" }
      "${s}.future" = { schema = s, scope = "future" }
    }
  ]...)
  account_role_name = snowflake_account_role.ar_write[each.value.schema].name
  privileges        = ["USAGE"]
  on_schema_object {
    dynamic "all" {
      for_each = each.value.scope == "all" ? [1] : []
      content {
        object_type_plural = "STAGES"
        in_schema          = "\"${local.db_name}\".\"${each.value.schema}\""
      }
    }
    dynamic "future" {
      for_each = each.value.scope == "future" ? [1] : []
      content {
        object_type_plural = "STAGES"
        in_schema          = "\"${local.db_name}\".\"${each.value.schema}\""
      }
    }
  }
  depends_on = [snowflake_schema.schema, snowflake_stage.stage]
}

# File formats: reference in COPY INTO
resource "snowflake_grant_privileges_to_account_role" "w_dml_file_formats" {
  for_each = merge([
    for s in local.dml_schemas : {
      "${s}.all"    = { schema = s, scope = "all" }
      "${s}.future" = { schema = s, scope = "future" }
    }
  ]...)
  account_role_name = snowflake_account_role.ar_write[each.value.schema].name
  privileges        = ["USAGE"]
  on_schema_object {
    dynamic "all" {
      for_each = each.value.scope == "all" ? [1] : []
      content {
        object_type_plural = "FILE FORMATS"
        in_schema          = "\"${local.db_name}\".\"${each.value.schema}\""
      }
    }
    dynamic "future" {
      for_each = each.value.scope == "future" ? [1] : []
      content {
        object_type_plural = "FILE FORMATS"
        in_schema          = "\"${local.db_name}\".\"${each.value.schema}\""
      }
    }
  }
  depends_on = [snowflake_schema.schema, snowflake_file_format.ff]
}
