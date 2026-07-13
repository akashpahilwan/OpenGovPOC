# Runbook: add a service user

Service users are `TYPE=SERVICE`, **key-pair (JWT) only** — passwords are
impossible. Each holds exactly one functional role. Used by dbt CI, the Python
loader, Fivetran, etc.

## Generate a key pair (private key never committed)

```bash
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -nocrypt -out og_new_svc.p8
openssl rsa -in og_new_svc.p8 -pubout -out og_new_svc.pub
# strip header/footer/newlines to get the one-line public key body
```

## Edit `config/service_users.csv`

```
key,name,role,warehouse,rsa_public_key,comment,is_active
og_dbt_svc,OG_DBT_SVC,REVOPS_DEVELOPER,DEVELOPER,MIIBIjANBg... ,dbt CI builds DEV+PROD,true
```

- **`role`** — the single functional role it holds.
- **`warehouse`** — warehouse *function* for its default (e.g. `DEVELOPER`,
  `INGEST_ADLS`).
- **`rsa_public_key`** — the public key **body** (one line). The public key is
  **safe to commit**; the private key lives only with the CI/owner. Managing it
  in TF means an `apply` never wipes the key (an out-of-band `ALTER USER` would
  be clobbered).

## Deploy & wire secrets

PR → merge → CI creates the user with the key + role. Put the **private** key
where its consumer reads it:
- dbt CI → GitHub secret `SF_PRIVATE_KEY` (+ `SF_USERNAME`).
- Local loader → `SF_PRIVATE_KEY_PATH` env var.

## Verify

```sql
DESC USER OG_DBT_SVC;                    -- TYPE=SERVICE, RSA_PUBLIC_KEY_FP set
SHOW GRANTS TO USER OG_DBT_SVC;          -- its one functional role
```

## Rotate

Generate a new pair, replace `rsa_public_key` in the CSV (or use
`RSA_PUBLIC_KEY_2` for zero-downtime rotation), redeploy, update the consumer's
private key, then retire the old key.
