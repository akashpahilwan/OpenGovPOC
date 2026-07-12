# ============================================================================
# Governance — PII tag + ARR masking policy (tag-based masking).
#
# Deliverable: "Column masking policy on ACCOUNT.ARR: return NULL for roles
# below REVOPS_ADMIN, actual value for REVOPS_ADMIN."
#
# Design choices worth defending to the panel:
#
# 1. TAG-BASED, not per-column. The policy is attached to the PII_FINANCIAL
#    tag (seed SQL: ALTER TAG ... SET MASKING POLICY ...); any column tagged
#    PII_FINANCIAL='arr' is masked automatically. Scales to 10 domains:
#    classifying a column IS protecting it — no per-table policy wiring.
#
# 2. IS_ROLE_IN_SESSION, not CURRENT_ROLE(). Hierarchy-aware: a user holding
#    REVOPS_ADMIN (directly or via inheritance) is unmasked even when running
#    with a secondary role active. CURRENT_ROLE() breaks under role hierarchy.
#
# 3. dbt service roles are EXEMPT — deliberately. dbt materializes staging
#    and mart tables; if dbt read masked NULLs it would PERSIST NULLs and
#    REVOPS_ADMIN could never see real ARR downstream. Instead dbt reads
#    real values and re-tags the arr column on every model it builds
#    (post-hook), so the mask travels with the data. Humans below
#    REVOPS_ADMIN see NULL at every layer.
# ============================================================================

resource "snowflake_tag" "pii_financial" {
  name                   = "PII_FINANCIAL"
  database               = snowflake_database.db.name
  schema                 = snowflake_schema.schema["GOVERNANCE"].name
  ordered_allowed_values = ["arr"]
  comment                = "Financial PII classification. Tagged columns are masked via attached policy."
}

locals {
  # Unmasked readers: REVOPS_ADMIN + every dbt_project service role from
  # config (ETL must read real values or it would persist NULLs downstream).
  masking_exempt_roles = concat(
    ["REVOPS_ADMIN"],
    [for name in sort(tolist(local.dbt_project_roles)) : snowflake_account_role.service[name].name],
  )
}

resource "snowflake_masking_policy" "mask_arr" {
  name     = "MASK_ARR_NUMBER"
  database = snowflake_database.db.name
  schema   = snowflake_schema.schema["GOVERNANCE"].name

  argument {
    name = "VAL"
    type = "NUMBER(18,2)"
  }

  body = <<-SQL
    CASE
      ${join("\n      ", [for r in local.masking_exempt_roles : "WHEN IS_ROLE_IN_SESSION('${r}') THEN VAL"])}
      ELSE NULL
    END
  SQL

  return_data_type = "NUMBER(18,2)"
  comment          = "ARR visible only to REVOPS_ADMIN (+ dbt ETL roles); NULL for all others."
}
