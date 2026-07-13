# Runbook: onboard / offboard a developer

A developer reads every layer and writes **only their own sandbox** — via a
per-person composite role `DEV_<NAME>` (`REVOPS_READER` + their sandbox write),
set as their default role with secondary roles off. Humans never get
`REVOPS_DEVELOPER` (that's the dbt CI service role; prod writes go through CI).

## Onboard — two CSV edits

1. **`config/environments.csv`** — add the username to the DEV `developers`
   list (pipe-separated). This creates the sandbox `REVOPS_DEV_<NAME>`, its
   access roles, and the composite role `DEV_<NAME>`:
   ```
   dev,DEV,AKASHPAHILWAN|SOURABH_SHINDE|ANUJKUMAR,true
   ```
2. **`config/human_users.csv`** — create the Snowflake user (no password here;
   set out-of-band). `default_role` = the composite role, `login_name` = the
   email they'll authenticate with:
   ```
   anuj,ANUJKUMAR,anujkumar@opengov.com,anujkumar@opengov.com,DEV_ANUJKUMAR,RevOps developer,true
   ```
   > The developer must be a real Snowflake user — either created here
   > (`human_users`) or a pre-existing account user (e.g. the account owner).

## Deploy

PR → merge to `main` → infra CI runs `sync_config` + `terraform apply` +
`apply_pii_tags`. (Locally: `python infra/sync_config.py`, `terraform apply`.)

## Set their password (out-of-band — never in config/state)

As an admin, or the user themselves in Snowsight:
```sql
ALTER USER ANUJKUMAR SET PASSWORD='<policy-compliant>' MUST_CHANGE_PASSWORD=FALSE;
```
The account has a password policy (no reuse / `PRIOR_USE`). They then log in and
develop locally — see the dbt repo's
[local-development guide](https://github.com/akashpahilwan/opengov-dbt-hub/blob/main/docs/local-development.md).

## Verify

```sql
SHOW GRANTS OF ROLE DEV_ANUJKUMAR;          -- granted to USER ANUJKUMAR
SHOW GRANTS TO ROLE DEV_ANUJKUMAR;           -- REVOPS_READER + AR_DEV_REVOPS_DEV_ANUJKUMAR_W
DESC USER ANUJKUMAR;                         -- DEFAULT_ROLE=DEV_ANUJKUMAR, DEFAULT_SECONDARY_ROLES=[]
```
A clean login should show `CURRENT_ROLE() = DEV_ANUJKUMAR`, empty secondary roles,
can read shared `STAGING` (financials masked), can build into `REVOPS_DEV_ANUJKUMAR`.

## Offboard — full revocation

1. `human_users.csv`: flip the user's row to `is_active=false` (drops the user
   and every grant on the next apply).
2. Remove the username from `environments.csv` `developers` (drops the composite
   role + sandbox).
3. Immediately, out-of-band: `ALTER USER ANUJKUMAR SET DISABLED=TRUE;` (kills
   live sessions while the PR merges).
4. Verify `SHOW GRANTS TO USER ANUJKUMAR;` returns nothing.

Because object grants live only in access roles and the user holds only the
composite role, revoking it removes everything — no per-object cleanup.
