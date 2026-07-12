output "environments" {
  description = "Per-environment footprint (db, warehouses, service identities, governance objects)"
  value = {
    for env_key, m in module.env : env_key => {
      database       = m.database
      warehouses     = m.warehouses
      service_roles  = m.service_roles
      service_users  = m.service_users
      masking_policy = m.masking_policy_fqn
      pii_tag        = m.pii_tag_fqn
    }
  }
}

output "functional_roles" {
  value = [for name, r in snowflake_account_role.functional : name]
}
