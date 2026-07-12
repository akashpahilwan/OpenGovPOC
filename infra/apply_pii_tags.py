"""
apply_pii_tags.py — idempotently apply GOVERNANCE that Terraform can't, from
the same config manifests. Two steps per env:

  1. BIND each masking policy to its tag (ALTER TAG ... SET MASKING POLICY),
     from resources/infrastructure/masking_rules.json. The snowflakedb/snowflake
     ~> 2.18 provider has no tag->policy resource, so this lives here.
  2. CLASSIFY columns (ALTER TABLE ... MODIFY COLUMN ... SET TAG), from
     resources/infrastructure/pii_columns.json.

WHY A SCRIPT, NOT TERRAFORM: the tagged columns live on Fivetran-owned tables
that the connector may drop and recreate on a re-sync, which would silently
strip column tags and permanently drift Terraform state. This re-applies both
steps from config on every run — schedule it after each Fivetran sync (and run
it in CI after deploy/seed). Both operations are idempotent.

Auth: same key-pair identity as Terraform (OG_DEPLOYER_SVC). Env vars:
  SF_ORGANIZATION_NAME, SF_ACCOUNT_NAME, SF_USERNAME, SF_PRIVATE_KEY_PATH

Usage:
  python infra/apply_pii_tags.py --env DEV
  python infra/apply_pii_tags.py --env PROD --dry-run
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
INFRA = os.path.join(HERE, "resources", "infrastructure")
PII_MANIFEST = os.path.join(INFRA, "pii_columns.json")
RULES_MANIFEST = os.path.join(INFRA, "masking_rules.json")


def connect():
    import snowflake.connector
    from cryptography.hazmat.primitives import serialization

    required = ["SF_ORGANIZATION_NAME", "SF_ACCOUNT_NAME", "SF_USERNAME", "SF_PRIVATE_KEY_PATH"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        sys.exit(f"Missing env vars: {', '.join(missing)}")

    with open(os.environ["SF_PRIVATE_KEY_PATH"], "rb") as f:
        pkey = serialization.load_pem_private_key(f.read(), password=None)
    pkey_der = pkey.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    return snowflake.connector.connect(
        account=f"{os.environ['SF_ORGANIZATION_NAME']}-{os.environ['SF_ACCOUNT_NAME']}",
        user=os.environ["SF_USERNAME"],
        private_key=pkey_der,
        role="OG_DEPLOYER",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", required=True, choices=["DEV", "QA", "PROD"])
    parser.add_argument("--dry-run", action="store_true", help="Print SQL without executing")
    args = parser.parse_args()

    db = f"OG_{args.env}_DB"

    with open(RULES_MANIFEST, encoding="utf-8") as f:
        masking_rules = json.load(f)["masking_rules"]
    with open(PII_MANIFEST, encoding="utf-8") as f:
        pii_columns = json.load(f)["pii_columns"]

    # Step 1: bind each active policy to its tag.
    bind_stmts = [
        f'ALTER TAG "{db}"."GOVERNANCE"."{r["tag"]}" '
        f'SET MASKING POLICY "{db}"."GOVERNANCE"."{r["policy_name"]}"'
        for r in masking_rules.values()
        if r["is_active"]
    ]
    # Step 2: classify columns (idempotent SET TAG; restores tags after a
    # Fivetran table recreate).
    tag_stmts = [
        f'ALTER TABLE "{db}"."{p["schema"]}"."{p["table"]}" '
        f'MODIFY COLUMN "{p["column"]}" '
        f'SET TAG "{db}"."GOVERNANCE"."{p["tag"]}" = \'{p["tag_value"]}\''
        for p in pii_columns.values()
        if p["is_active"]
    ]

    if not bind_stmts and not tag_stmts:
        print("No active masking rules or pii_columns - nothing to do.")
        return

    if args.dry_run:
        print(f"-- {len(bind_stmts)} tag->policy binding(s), {len(tag_stmts)} column tag(s) for {db}:")
        print(";\n".join(bind_stmts + tag_stmts) + ";")
        return

    conn = connect()
    try:
        cur = conn.cursor()
        ok, failed, skipped = 0, 0, 0
        for stmt in bind_stmts + tag_stmts:
            try:
                cur.execute(stmt)
                ok += 1
                print(f"OK       {stmt}")
            except Exception as e:
                # "already has a masking policy" => binding already in place; idempotent no-op.
                if "already" in str(e).lower():
                    skipped += 1
                    print(f"SKIP     {stmt}  (already applied)")
                else:  # e.g. table not synced/seeded yet — report, don't abort the batch
                    failed += 1
                    print(f"FAILED   {stmt}\n         {e}")
        print(f"\n{ok} applied, {skipped} already-set, {failed} failed.")
        if failed:
            sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
