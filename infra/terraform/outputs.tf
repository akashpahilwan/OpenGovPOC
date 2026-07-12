output "environments" {
  description = "Per-environment footprint (db, warehouses, service identities, governance objects)"
  value = {
    for env_key, m in module.env : env_key => {
      database       = m.database
      warehouses     = m.warehouses
      service_roles  = m.service_roles
      service_users  = m.service_users
      masking_policies = m.masking_policies
      pii_tags         = m.pii_tags
    }
  }
}

output "functional_roles" {
  value = [for name, r in snowflake_account_role.functional : name]
}
