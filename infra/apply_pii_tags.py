"""
apply_pii_tags.py — idempotently apply PII classification tags to columns,
from resources/infrastructure/pii_columns.json (generated from
config/pii_columns.csv by sync_config.py).

WHY A SCRIPT, NOT TERRAFORM: the tagged columns live on Fivetran-owned tables
that the connector may drop and recreate on a re-sync, which would silently
strip column tags and permanently drift Terraform state. This script re-applies
the classification from config on every run — schedule it after each Fivetran
sync (or run it in CI after deploy/seed). Because the masking policy is
attached to the TAG (Terraform-managed, GOVERNANCE schema), re-tagging a
column re-protects it: classifying IS protecting.

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
MANIFEST = os.path.join(HERE, "resources", "infrastructure", "pii_columns.json")


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

    with open(MANIFEST, encoding="utf-8") as f:
        pii_columns = json.load(f)["pii_columns"]

    db = f"OG_{args.env}_DB"
    statements = [
        # ALTER ... SET TAG is idempotent: re-setting the same tag/value is a no-op,
        # and re-setting after Fivetran recreated the table restores protection.
        f'ALTER TABLE "{db}"."{p["schema"]}"."{p["table"]}" '
        f'MODIFY COLUMN "{p["column"]}" '
        f'SET TAG "{db}"."GOVERNANCE"."{p["tag"]}" = \'{p["tag_value"]}\''
        for p in pii_columns.values()
        if p["is_active"]
    ]

    if not statements:
        print("No active pii_columns rows - nothing to do.")
        return

    if args.dry_run:
        print(f"-- {len(statements)} statement(s) for {db}:")
        print(";\n".join(statements) + ";")
        return

    conn = connect()
    try:
        cur = conn.cursor()
        ok, failed = 0, 0
        for stmt in statements:
            try:
                cur.execute(stmt)
                ok += 1
                print(f"OK      {stmt}")
            except Exception as e:  # e.g. table not synced/seeded yet — report, don't abort
                failed += 1
                print(f"FAILED  {stmt}\n        {e}")
        print(f"\n{ok} applied, {failed} failed.")
        if failed:
            sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
