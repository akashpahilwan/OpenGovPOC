# Runbook: add a masking rule / classify a PII column

Masking is tag-based and fully config-driven — three CSVs, no HCL. A tag carries
a masking policy; classifying a column with the tag protects it everywhere,
across all current and future domains.

## The three CSVs

**1. `masking_rules.csv` — what rules exist** (`tag × data_type → policy`):
```
key,tag,allowed_values,data_type,mask_expression,comment,is_active
pii_financial_number,PII_FINANCIAL,arr|amount,NUMBER(18,2),NULL,Financial figures,true
pii_contact_email,PII_CONTACT,email,VARCHAR,REGEXP_REPLACE(VAL,'^[^@]+','****'),Emails,false
```
- `mask_expression` must reference `VAL` (the column value); can be `NULL`, a
  partial reveal, a hash — anything valid for `data_type`.
- `sync_config.py` rejects a duplicate `(tag, data_type)` and a `mask_expression`
  that doesn't reference `VAL`. Terraform generates the tag (deduped) + policy.

**2. `pii_columns.csv` — what is classified**:
```
key,schema,table,column,tag,tag_value,is_active
account_arr,SALESFORCE_RAW_FIVETRAN,ACCOUNT,ARR,PII_FINANCIAL,arr,true
opp_amount,SALESFORCE_RAW_FIVETRAN,OPPORTUNITY,AMOUNT,PII_FINANCIAL,amount,true
```

**3. `masking_exemptions.csv` — who sees it unmasked** (by ROLE, never user):
```
key,tag,role_type,role,is_active
fin_admin,PII_FINANCIAL,FUNCTIONAL,REVOPS_ADMIN,true
fin_developer,PII_FINANCIAL,FUNCTIONAL,REVOPS_DEVELOPER,true
fin_analyst,PII_FINANCIAL,FUNCTIONAL,REVOPS_ANALYST,true
```
Current `PII_FINANCIAL` exempt = ADMIN + DEVELOPER + ANALYST (**not** READER),
so analysts see financials in the mart; readers/dev-sandbox see `NULL`.

## Deploy — the critical two-step

Terraform creates tags + policies, but the **tag→policy binding is NOT a TF
resource** and is dropped by every apply. So after apply you MUST run:
```bash
python infra/apply_pii_tags.py --env DEV     # ALTER TAG SET MASKING POLICY + classify columns
python infra/apply_pii_tags.py --env PROD
```
The infra CI does this automatically after `terraform apply`. It skips columns
whose table doesn't exist yet in an env (e.g. a Fivetran table not synced to
PROD) rather than failing.

## Verify

```sql
-- as a non-exempt role (e.g. REVOPS_READER): should be NULL
SELECT arr FROM OG_DEV_DB.SALESFORCE_RAW_FIVETRAN.ACCOUNT LIMIT 3;
-- tag→policy bound?
SELECT * FROM TABLE(OG_DEV_DB.INFORMATION_SCHEMA.POLICY_REFERENCES(
  REF_ENTITY_NAME=>'OG_DEV_DB.GOVERNANCE.PII_FINANCIAL', REF_ENTITY_DOMAIN=>'TAG'));
```
Empty `POLICY_REFERENCES` = binding dropped → re-run `apply_pii_tags.py`.
