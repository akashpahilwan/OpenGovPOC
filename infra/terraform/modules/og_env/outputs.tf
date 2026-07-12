output "database" {
  value = snowflake_database.db.name
}

output "access_roles_read" {
  description = "schema => AR_<ENV>_<schema>_R role name"
  value       = { for s, r in snowflake_account_role.ar_read : s => r.name }
}

output "access_roles_write" {
  description = "schema => AR_<ENV>_<schema>_W role name"
  value       = { for s, r in snowflake_account_role.ar_write : s => r.name }
}

output "service_roles" {
  value = { for k, r in snowflake_account_role.service : k => r.name }
}

output "service_users" {
  value = { for k, u in snowflake_service_user.svc : k => u.name }
}

output "warehouses" {
  description = "warehouse key => name (e.g. ingest_xs => OG_DEV_INGEST_XS_WH)"
  value       = { for k, w in snowflake_warehouse.wh : k => w.name }
}

output "warehouses_by_function" {
  description = "function => all warehouse names of that function"
  value       = local.wh_by_function
}

output "default_warehouse_by_function" {
  description = "function => the is_default (XSMALL) warehouse name"
  value       = local.wh_default
}

output "masking_policies" {
  description = "rule key => masking policy FQN"
  value       = { for k, p in snowflake_masking_policy.policy : k => p.fully_qualified_name }
}

output "pii_tags" {
  description = "tag name => tag FQN"
  value       = { for t, tag in snowflake_tag.tag : t => tag.fully_qualified_name }
}
