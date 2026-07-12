# ============================================================================
# Load JSON manifests (generated from infra/config/*.csv by sync_config.py).
# Terraform never contains hand-written object lists — config is the single
# source of truth, and is_active=false soft-deletes on the next apply.
# ============================================================================

locals {
  environments = jsondecode(file("${path.module}/../resources/infrastructure/environments.json"))["environments"]
  env_map      = { for k, v in local.environments : v.env => v if v.is_active }

  schemas    = jsondecode(file("${path.module}/../resources/infrastructure/schemas.json"))["schemas"]
  schema_map = { for k, v in local.schemas : v.schema => v if v.is_active }

  warehouses    = jsondecode(file("${path.module}/../resources/infrastructure/warehouses.json"))["warehouses"]
  warehouse_map = { for k, v in local.warehouses : k => v if v.is_active }

  storage_integrations    = jsondecode(file("${path.module}/../resources/infrastructure/storage_integrations.json"))["storage_integrations"]
  storage_integration_map = { for k, v in local.storage_integrations : k => v if v.is_active }

  stages    = jsondecode(file("${path.module}/../resources/infrastructure/stages.json"))["stages"]
  stage_map = { for k, v in local.stages : k => v if v.is_active }

  file_formats    = jsondecode(file("${path.module}/../resources/infrastructure/file_formats.json"))["file_formats"]
  file_format_map = { for k, v in local.file_formats : k => v if v.is_active }

  tables    = jsondecode(file("${path.module}/../resources/infrastructure/tables.json"))["tables"]
  table_map = { for k, v in local.tables : k => v if v.is_active }

  service_roles    = jsondecode(file("${path.module}/../resources/infrastructure/service_roles.json"))["service_roles"]
  service_role_map = { for k, v in local.service_roles : v.name => v if v.is_active }

  functional_roles    = jsondecode(file("${path.module}/../resources/infrastructure/functional_roles.json"))["functional_roles"]
  functional_role_map = { for k, v in local.functional_roles : v.name => v if v.is_active }

  functional_grants    = jsondecode(file("${path.module}/../resources/infrastructure/functional_grants.json"))["functional_grants"]
  functional_grant_map = { for k, v in local.functional_grants : k => v if v.is_active }

  human_users    = jsondecode(file("${path.module}/../resources/infrastructure/human_users.json"))["human_users"]
  human_user_map = { for k, v in local.human_users : k => v if v.is_active }

  user_roles    = jsondecode(file("${path.module}/../resources/infrastructure/user_roles.json"))["user_roles"]
  user_role_map = { for k, v in local.user_roles : k => v if v.is_active }
}
