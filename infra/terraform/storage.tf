# ============================================================================
# ADLS storage integration — ACCOUNT-level, so it lives in the root stack
# (one integration serves both envs; env separation is path-prefixing inside
# the og-telemetry container: /dev/... and /prod/...).
#
# After the FIRST apply, a one-time Azure consent is required:
#   DESC STORAGE INTEGRATION OG_ADLS_INT;
#   -> open AZURE_CONSENT_URL, grant consent, then give the Snowflake service
#      principal "Storage Blob Data Contributor" on the og-telemetry container.
# Steps are in infra/README.md.
# ============================================================================

resource "snowflake_storage_integration" "integration" {
  for_each                  = local.storage_integration_map
  name                      = each.value.name
  type                      = "EXTERNAL_STAGE"
  storage_provider          = each.value.provider
  azure_tenant_id           = try(each.value.azure_tenant_id, null)
  storage_allowed_locations = each.value.allowed_locations
  enabled                   = true
  comment                   = each.value.comment
}

# USAGE for the configured service roles, expanded per active environment
# (granted_to_service_roles holds base names like INGEST -> OG_INGEST_DEV/PROD).
# Needed only by roles that CREATE stages against the integration ad hoc;
# using a Terraform-created stage needs stage privileges only.

# USAGE on the account-level integration for each configured functional role
# (granted_to_service_roles now holds functional role names, e.g.
# REVOPS_INGESTION_ADLS). Account-wide — the role spans both envs.
resource "snowflake_grant_privileges_to_account_role" "storage_integration_usage" {
  for_each = merge([
    for ik, integ in local.storage_integration_map : {
      for role in integ.granted_to_service_roles :
      "${ik}__${role}" => { integration = integ.name, role = role }
    }
  ]...)
  account_role_name = each.value.role
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "INTEGRATION"
    object_name = each.value.integration
  }
  depends_on = [snowflake_storage_integration.integration, snowflake_account_role.functional]
}
