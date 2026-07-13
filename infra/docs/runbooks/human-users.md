# Runbook: add / change a human user

Terraform creates the **user shell** only — **no passwords in config or state**.
Initial auth is set out-of-band (SSO/SCIM in real life; `ALTER USER … SET
PASSWORD` here). Humans hold functional/composite roles, never access roles.

## Edit `config/human_users.csv`

```
key,username,login_name,email,default_role,comment,is_active
jane,JANE_DOE,jane.doe@opengov.com,jane.doe@opengov.com,REVOPS_ANALYST,GTM analyst,true
```

- **`login_name`** — what they authenticate with. **Important:** for
  username+password auth, the connector matches the `LOGIN_NAME`, so tools must
  use this (the email), **not** the object `username`.
- **`default_role`** — a functional role, or a developer's composite `DEV_<NAME>`.
  `sync_config.py` rejects a service-only role (`human_assignable=false`) here.
- Humans are created with **secondary roles disabled**
  (`default_secondary_roles_option = "NONE"`) — one active role per session.

## Set the password (out-of-band)

```sql
ALTER USER JANE_DOE SET PASSWORD='<policy-compliant>' MUST_CHANGE_PASSWORD=FALSE;
```
Password policy rejects reused values (`PRIOR_USE`).

## Assign roles

`human_users.csv` creates the user + sets its default role; role **grants** come
from `user_roles.csv` (see [user-roles runbook](user-roles.md)) — except
developers, whose composite role is granted automatically from the
`environments.csv` developers list.

## Deploy & verify

PR → merge → CI. `DESC USER JANE_DOE;` → check `DEFAULT_ROLE`,
`DEFAULT_SECONDARY_ROLES=[]`, `DISABLED=false`.

## Offboard

Flip `is_active=false` (drops the user + all grants next apply); immediately
`ALTER USER JANE_DOE SET DISABLED=TRUE;` to kill live sessions.
