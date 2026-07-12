output "environments" {
  description = "Per-environment footprint (db, warehouses, service identities, governance objects)"
  value = {
    for env_key, m in module.env : env_key => {
      database         = m.database
      warehouses       = m.warehouses
      masking_policies = m.masking_policies
      pii_tags         = m.pii_tags
    }
  }
}

output "functional_roles" {
  value = [for name, r in snowflake_account_role.functional : name]
}

output "service_users" {
  description = "service user => role it holds"
  value       = { for k, u in snowflake_service_user.svc : u.name => local.service_user_map[k].role }
}
