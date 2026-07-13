# Runbook: assign a user role

`user_roles.csv` grants a **functional role** to a user (human or pre-existing).
It's how analysts/admins get their access. Developers are the exception —
their composite `DEV_<NAME>` role is granted automatically from the
`environments.csv` developers list, so they need **no** row here.

## Edit `config/user_roles.csv`

```
key,username,role_name,is_active
jane_analyst,JANE_DOE,REVOPS_ANALYST,true
```

- **`role_name`** — must be `human_assignable=true` (`sync_config.py` rejects
  service-only roles like `REVOPS_DEVELOPER` / the ingestion roles).
- Soft-delete with `is_active=false` to revoke on the next apply.

## Deploy & verify

PR → merge → CI.
```sql
SHOW GRANTS TO USER JANE_DOE;   -- should list REVOPS_ANALYST
```

> Don't add a `REVOPS_READER` row for a developer — the composite `DEV_<NAME>`
> already inherits `REVOPS_READER`. (Redundant direct grants were removed for
> `AKASHPAHILWAN`/`SOURABH_SHINDE` for exactly this reason.)
