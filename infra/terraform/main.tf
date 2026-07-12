# ============================================================================
# Root stack — one og_env module instance per active environment (from
# config/environments.csv) + the human functional-role layer (from
# config/functional_roles.csv + functional_grants.csv).
#
# Adding QA = one CSV row. Onboarding a developer sandbox = one cell edit.
# ============================================================================

module "env" {
  source   = "./modules/og_env"
  for_each = local.env_map

  env          = each.value.env
  developers   = each.value.developers
  schemas      = local.schema_map
  warehouses   = local.warehouse_map
  stages       = local.stage_map
  file_formats = local.file_format_map
  tables       = local.table_map

  masking_rules      = local.masking_rule_map
  masking_exemptions = local.masking_exemption_map

  # stages reference the account-level ADLS integration by name
  depends_on = [snowflake_storage_integration.integration]
}

# ============================================================================
# Functional roles (tier 2) — HUMAN roles, config-driven.
#
# One account-wide set spanning all environments (humans hold one role; env
# separation lives in functional_grants.csv rows):
#   REVOPS_ANALYST     read MARTS only (all envs)
#   REVOPS_DEVELOPER   + read STAGING (all envs) + write DEV sandboxes only —
#                        humans never get write in PROD; that path is CI/CD
#   REVOPS_ADMIN       full domain access
# Hierarchy (inherits_from): ANALYST -> DEVELOPER -> ADMIN -> SYSADMIN.
# ============================================================================

resource "snowflake_account_role" "functional" {
  for_each = local.functional_role_map
  name     = each.key
  comment  = each.value.comment
}

# ── Hierarchy: inherits_from = GRANT <that role> TO ROLE <this role> ─────────

resource "snowflake_grant_account_role" "functional_inheritance" {
  for_each = merge([
    for name, cfg in local.functional_role_map : {
      for parent in cfg.inherits_from :
      "${name}__inherits__${parent}" => { child = parent, holder = name }
    }
  ]...)
  role_name        = each.value.child
  parent_role_name = each.value.holder
  depends_on       = [snowflake_account_role.functional]
}

# ── Tree top: granted_to (e.g. REVOPS_ADMIN -> SYSADMIN) ─────────────────────

resource "snowflake_grant_account_role" "functional_granted_to" {
  for_each = {
    for name, cfg in local.functional_role_map : name => cfg.granted_to
    if cfg.granted_to != ""
  }
  role_name        = each.key
  parent_role_name = each.value
  depends_on       = [snowflake_account_role.functional]
}

# ── Access-role wiring from functional_grants.csv ────────────────────────────
# Each grant row: role + env (or ALL) + schema (exact, PREFIX*, or *) + R/W.
# Expanded here against every active env module's access-role outputs.

locals {
  functional_grant_expanded = merge([
    for gk, g in local.functional_grant_map : {
      for pair in flatten([
        for env_key, env_mod in module.env : [
          for schema, ar in(g.level == "R" ? env_mod.access_roles_read : env_mod.access_roles_write) : {
            key         = "${gk}__${env_key}__${schema}"
            access_role = ar
            func_role   = g.role
          }
          if(g.env == "ALL" || g.env == env_key) && (
            g.schema == "*" ||
            g.schema == schema ||
            (endswith(g.schema, "*") && startswith(schema, trimsuffix(g.schema, "*")))
          )
        ]
      ]) : pair.key => pair
    }
  ]...)
}

resource "snowflake_grant_account_role" "functional_access" {
  for_each         = local.functional_grant_expanded
  role_name        = each.value.access_role
  parent_role_name = each.value.func_role
  depends_on       = [snowflake_account_role.functional]
}

# ── Warehouse usage: every size of the role's function, per env ──────────────

resource "snowflake_grant_privileges_to_account_role" "functional_wh" {
  for_each = merge([
    for env_key, env_mod in module.env : merge([
      for name, cfg in local.functional_role_map : {
        for wh in env_mod.warehouses_by_function[cfg.warehouse] :
        "${name}__${env_key}__${wh}" => { role = name, wh = wh }
      }
      if cfg.warehouse != ""
    ]...)
  ]...)
  account_role_name = each.value.role
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = each.value.wh
  }
  depends_on = [snowflake_account_role.functional]
}

# ── Human users (config/human_users.csv) ─────────────────────────────────────
# Terraform creates the user shell only — NO passwords in config or state;
# initial authentication is set out-of-band (in real life: SSO/SCIM).
# Offboard: is_active=false drops the user (and with it every session).

resource "snowflake_user" "human" {
  for_each     = local.human_user_map
  name         = each.value.username
  login_name   = each.value.login_name
  email        = each.value.email
  default_role = each.value.default_role
  comment      = each.value.comment
  depends_on   = [snowflake_account_role.functional]
}

# ── Human user -> functional role assignments (config/user_roles.csv) ────────
# Onboard: add a row (is_active=true). Offboard: flip is_active=false — the
# next apply revokes it. Username may be a human_users entry (created above)
# or a pre-existing account user.

resource "snowflake_grant_account_role" "user_role" {
  for_each   = local.user_role_map
  role_name  = each.value.role_name
  user_name  = each.value.username
  depends_on = [snowflake_account_role.functional, snowflake_user.human]
}

# ── Service users (config/service_users.csv) ─────────────────────────────────
# TYPE=SERVICE, key-pair only. Each holds ONE functional role (account-wide),
# so the role carries the privileges and spans both envs — e.g. OG_DBT_SVC
# holds REVOPS_DEVELOPER and builds models in DEV and PROD. RSA public keys are
# attached out-of-band via ALTER USER, so key rotation needs no terraform apply.

resource "snowflake_service_user" "svc" {
  for_each = local.service_user_map
  name     = each.value.name
  comment  = each.value.comment
  # default_role must be set by name; the role is granted below.
  default_role = each.value.role
  depends_on   = [snowflake_account_role.functional]
}

resource "snowflake_grant_account_role" "svc_user_role" {
  for_each   = local.service_user_map
  role_name  = each.value.role
  user_name  = snowflake_service_user.svc[each.key].name
  depends_on = [snowflake_account_role.functional]
}

# ── Personal dev sandboxes — write to OWN schema only (DEV) ──────────────────
# A developer reads all layers via REVOPS_READER but writes nothing shared.
# Their personal sandbox (OG_DEV_DB.REVOPS_DEV_<NAME>) write role is granted
# straight to their user — so they can build/iterate dbt models in their own
# schema without touching STAGING/MARTS/PROD (that path is the dbt CI job as
# REVOPS_DEVELOPER). Guarded to active human_users.

locals {
  dev_developers  = contains(keys(local.env_map), "DEV") ? local.env_map["DEV"].developers : []
  human_usernames = toset([for k, v in local.human_user_map : v.username])
  sandbox_owner_grants = {
    for name in local.dev_developers : name => name
    if contains(local.human_usernames, name)
  }
}

resource "snowflake_grant_account_role" "personal_sandbox_owner" {
  for_each   = local.sandbox_owner_grants
  role_name  = module.env["DEV"].access_roles_write["REVOPS_DEV_${each.key}"]
  user_name  = each.key
  depends_on = [snowflake_user.human]
}

# ── dbt Projects on Snowflake — REVOPS_DEVELOPER runs them (DEV + PROD) ──────
# The role that builds models needs CREATE DBT PROJECT + USAGE on each env's
# DBT schema. (Native "dbt Projects on Snowflake" objects live in OG_<ENV>_DB.DBT.)

resource "snowflake_grant_privileges_to_account_role" "developer_dbt_project" {
  for_each          = module.env
  account_role_name = "REVOPS_DEVELOPER"
  privileges        = ["USAGE", "CREATE DBT PROJECT"]
  on_schema {
    schema_name = "\"${each.value.database}\".\"DBT\""
  }
  depends_on = [snowflake_account_role.functional]
}
