"""
sync_config.py — Convert infra/config/ CSV or Excel files into
infra/resources/infrastructure/ JSON manifests consumed by Terraform.

Same pattern as the SnowOps repo: config is the human interface (CSV or one
Excel workbook), JSON manifests are the machine interface, Terraform for_eachs
over the manifests. RBAC changes are config edits reviewed in a PR — never
hand-written HCL.

Supported input formats:
  CSV  (stdlib, no dependencies):  infra/config/*.csv
  Excel (requires openpyxl):       infra/config/og_config.xlsx
                                   Sheets: Environments, Schemas, ServiceRoles,
                                           FunctionalRoles, FunctionalGrants,
                                           UserRoles

Column reference
  environments.csv      : key | env | developers (pipe-separated personal
                          dbt sandboxes) | is_active
  warehouses.csv        : key | function (INGEST/TRANSFORM/ANALYTICS) | size
                          | auto_suspend | is_default (exactly one per function;
                          becomes service users' default) | comment | is_active
  schemas.csv           : key | schema | kind (DATA/GOVERNANCE/DBT)
                          | writer_owns_future (true: the W access role owns what
                          it creates, e.g. Fivetran/dbt schemas; false: platform/
                          Terraform owns the DDL and writers get DML only, e.g.
                          the ADLS telemetry landing) | comment | is_active
  storage_integrations.csv : key | name | provider | azure_tenant_id
                          | allowed_locations (pipe) | granted_to_service_roles
                          (pipe of service-role base names, expanded per env)
                          | comment | is_active
  stages.csv            : key | name | schema | stage_type (EXTERNAL/INTERNAL)
                          | url ({env} placeholder -> lowercase env prefix)
                          | storage_integration | comment | is_active
  file_formats.csv      : key | name | schema | format_type | comment | is_active
  tables.csv            : key | name | schema | change_tracking | comment | is_active
                          (deployer-owned tables for CUSTOM ingestion schemas
                          only — Fivetran creates its own tables. Column
                          definitions live in resources/tables/<key>.json,
                          hand-authored, SnowOps style.)
  service_users.csv     : key | name | role (functional role it holds) |
                          warehouse (function: INGEST/TRANSFORM/ANALYTICS, for
                          the user's default wh) | comment | is_active
  functional_roles.csv  : key | name | comment | inherits_from (pipe)
                          | granted_to (parent role, e.g. SYSADMIN for tree top)
                          | warehouse | is_active
  functional_grants.csv : key | role | env (DEV/QA/PROD/ALL)
                          | schema (exact, PREFIX* or *) | level (R/W) | is_active
  masking_rules.csv     : key | tag | allowed_values (pipe) | data_type
                          | mask_expression (ELSE branch; references VAL or NULL)
                          | comment | is_active   — the masking VOCABULARY;
                          one policy per (tag, data_type). New rule = new row.
  pii_columns.csv       : key | schema | table | column | tag | tag_value | is_active
  masking_exemptions.csv: key | tag | role_type (FUNCTIONAL/SERVICE) | role | is_active
  human_users.csv       : key | username | login_name | email | default_role
                          | comment | is_active  (human users Terraform CREATES;
                          no passwords here — initial auth is set out-of-band /
                          SSO. Service users come from service_roles.csv.)
  user_roles.csv        : key | username | role_name | is_active  (role
                          assignments; username may be a human_users entry or a
                          pre-existing user)

Usage:
  python infra/sync_config.py            # auto-detect CSV or Excel
  python infra/sync_config.py --csv      # force CSV
  python infra/sync_config.py --excel    # force Excel (requires openpyxl)
  python infra/sync_config.py --dry-run  # print JSON without writing
"""

import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(HERE, "config")
INFRA_DIR = os.path.join(HERE, "resources", "infrastructure")
EXCEL_FILE = os.path.join(CONFIG_DIR, "og_config.xlsx")

VALID_ENVS = {"DEV", "QA", "PROD"}
VALID_KINDS = {"DATA", "GOVERNANCE", "DBT"}
VALID_LEVELS = {"R", "W"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bool(val: str) -> bool:
    return str(val).strip().lower() in ("true", "1", "yes")


def _pipe(val: str) -> list:
    val = str(val).strip()
    return [x.strip().upper() for x in val.split("|") if x.strip()] if val else []


# ── Parsers (one per config file; each validates what Terraform can't) ────────

def parse_environments(rows):
    result = {}
    for row in rows:
        env = row["env"].strip().upper()
        if env not in VALID_ENVS:
            sys.exit(f"environments: invalid env '{env}' (must be one of {sorted(VALID_ENVS)})")
        result[row["key"].strip()] = {
            "env": env,
            "developers": _pipe(row.get("developers", "")),
            "is_active": _bool(row["is_active"]),
        }
    return result


def parse_warehouses(rows):
    result = {}
    for row in rows:
        result[row["key"].strip()] = {
            "function": row["function"].strip().upper(),
            "size": row["size"].strip().upper(),
            "auto_suspend": int(row["auto_suspend"]),
            "is_default": _bool(row.get("is_default", "false")),
            "comment": row["comment"].strip(),
            "is_active": _bool(row["is_active"]),
        }
    return result


def parse_schemas(rows):
    result = {}
    for row in rows:
        kind = row["kind"].strip().upper()
        if kind not in VALID_KINDS:
            sys.exit(f"schemas: invalid kind '{kind}' (must be one of {sorted(VALID_KINDS)})")
        result[row["key"].strip()] = {
            "schema": row["schema"].strip().upper(),
            "kind": kind,
            "writer_owns_future": _bool(row.get("writer_owns_future", "true")),
            "comment": row["comment"].strip(),
            "is_active": _bool(row["is_active"]),
        }
    return result


def parse_storage_integrations(rows):
    result = {}
    for row in rows:
        result[row["key"].strip()] = {
            "name": row["name"].strip().upper(),
            "provider": row["provider"].strip().upper(),
            "azure_tenant_id": row.get("azure_tenant_id", "").strip(),
            "allowed_locations": [x.strip() for x in str(row.get("allowed_locations", "")).split("|") if x.strip()],
            "granted_to_service_roles": _pipe(row.get("granted_to_service_roles", "")),
            "comment": row["comment"].strip(),
            "is_active": _bool(row["is_active"]),
        }
    return result


def parse_stages(rows):
    result = {}
    for row in rows:
        result[row["key"].strip()] = {
            "name": row["name"].strip().upper(),
            "schema": row["schema"].strip().upper(),
            "stage_type": row["stage_type"].strip().upper(),
            "url": row.get("url", "").strip(),
            "storage_integration": row.get("storage_integration", "").strip().upper(),
            "comment": row["comment"].strip(),
            "is_active": _bool(row["is_active"]),
        }
    return result


def parse_tables(rows):
    result = {}
    for row in rows:
        result[row["key"].strip()] = {
            "name": row["name"].strip().upper(),
            "schema": row["schema"].strip().upper(),
            "change_tracking": _bool(row.get("change_tracking", "false")),
            "comment": row["comment"].strip(),
            "is_active": _bool(row["is_active"]),
        }
    return result


def parse_file_formats(rows):
    result = {}
    for row in rows:
        result[row["key"].strip()] = {
            "name": row["name"].strip().upper(),
            "schema": row["schema"].strip().upper(),
            "format_type": row["format_type"].strip().upper(),
            "comment": row["comment"].strip(),
            "is_active": _bool(row["is_active"]),
        }
    return result


def parse_service_users(rows):
    """Service users (TYPE=SERVICE, key-pair only). Each holds ONE functional
    role — the account-wide role is what carries the privileges, so a service
    user is just an identity + its role. Not env-suffixed: the role spans
    envs (e.g. the dbt user builds DEV and PROD via REVOPS_DEVELOPER)."""
    result = {}
    for row in rows:
        result[row["key"].strip()] = {
            "name": row["name"].strip().upper(),
            "role": row["role"].strip().upper(),
            "warehouse": row["warehouse"].strip().upper(),  # function name for default wh
            # Public key managed in TF so a terraform apply never wipes it
            # (public key is not a secret). Empty = no key set yet.
            "rsa_public_key": row.get("rsa_public_key", "").strip(),
            "comment": row["comment"].strip(),
            "is_active": _bool(row["is_active"]),
        }
    return result


def parse_functional_roles(rows):
    result = {}
    for row in rows:
        result[row["key"].strip()] = {
            "name": row["name"].strip().upper(),
            "comment": row["comment"].strip(),
            "inherits_from": _pipe(row.get("inherits_from", "")),
            "granted_to": row.get("granted_to", "").strip().upper(),
            "warehouse": row.get("warehouse", "").strip().upper(),
            # human_assignable=false => SERVICE-ONLY (e.g. REVOPS_DEVELOPER,
            # ingestion roles). A human user must never be granted it.
            "human_assignable": _bool(row.get("human_assignable", "true")),
            "is_active": _bool(row["is_active"]),
        }
    return result


def parse_functional_grants(rows):
    result = {}
    for row in rows:
        env = row["env"].strip().upper()
        if env != "ALL" and env not in VALID_ENVS:
            sys.exit(f"functional_grants: invalid env '{env}' (DEV/QA/PROD or ALL)")
        level = row["level"].strip().upper()
        if level not in VALID_LEVELS:
            sys.exit(f"functional_grants: invalid level '{level}' (R or W)")
        result[row["key"].strip()] = {
            "role": row["role"].strip().upper(),
            "env": env,
            "schema": row["schema"].strip().upper(),  # exact, PREFIX* or *
            "level": level,
            "is_active": _bool(row["is_active"]),
        }
    return result


def parse_masking_rules(rows):
    """Defines the masking VOCABULARY: one row = one (tag, data_type) policy.
    A tag may span multiple data types (multiple rows) — each gets its own
    policy, since a Snowflake masking policy has a fixed argument type.
    mask_expression is the ELSE branch (what non-exempt roles see); it must
    reference the argument VAL and return the row's data_type."""
    result = {}
    for row in rows:
        tag = row["tag"].strip().upper()
        data_type = row["data_type"].strip().upper()
        base_type = data_type.split("(")[0]  # NUMBER(18,2) -> NUMBER
        result[row["key"].strip()] = {
            "tag": tag,
            # tag VALUES are case-sensitive data, not identifiers — do NOT
            # uppercase (must match pii_columns.tag_value exactly).
            "allowed_values": [x.strip() for x in str(row.get("allowed_values", "")).split("|") if x.strip()],
            "data_type": data_type,
            "mask_expression": row["mask_expression"].strip(),  # ELSE branch, references VAL
            # Policy name is derived once here so Terraform (creates it) and
            # apply_pii_tags.py (binds tag->policy) never disagree.
            "policy_name": f"MASK_{tag}_{base_type}",
            "comment": row["comment"].strip(),
            "is_active": _bool(row["is_active"]),
        }
    return result


def parse_pii_columns(rows):
    result = {}
    for row in rows:
        result[row["key"].strip()] = {
            "schema": row["schema"].strip().upper(),
            "table": row["table"].strip().upper(),
            "column": row["column"].strip().upper(),
            "tag": row["tag"].strip().upper(),
            "tag_value": row["tag_value"].strip(),
            "is_active": _bool(row["is_active"]),
        }
    return result


def parse_masking_exemptions(rows):
    result = {}
    for row in rows:
        role_type = row["role_type"].strip().upper()
        if role_type not in ("FUNCTIONAL", "SERVICE"):
            sys.exit(f"masking_exemptions: role_type must be FUNCTIONAL or SERVICE, got '{role_type}'")
        result[row["key"].strip()] = {
            "tag": row["tag"].strip().upper(),
            "role_type": role_type,
            "role": row["role"].strip().upper(),
            "is_active": _bool(row["is_active"]),
        }
    return result


def parse_human_users(rows):
    result = {}
    for row in rows:
        result[row["key"].strip()] = {
            "username": row["username"].strip().upper(),
            "login_name": row["login_name"].strip(),
            "email": row["email"].strip(),
            "default_role": row["default_role"].strip().upper(),
            "comment": row["comment"].strip(),
            "is_active": _bool(row["is_active"]),
        }
    return result


def parse_user_roles(rows):
    result = {}
    for row in rows:
        result[row["key"].strip()] = {
            "username": row["username"].strip().upper(),
            "role_name": row["role_name"].strip().upper(),
            "is_active": _bool(row["is_active"]),
        }
    return result


PARSERS = {
    "environments": ("environments.csv", "Environments", parse_environments),
    "warehouses": ("warehouses.csv", "Warehouses", parse_warehouses),
    "schemas": ("schemas.csv", "Schemas", parse_schemas),
    "storage_integrations": ("storage_integrations.csv", "StorageIntegrations", parse_storage_integrations),
    "stages": ("stages.csv", "Stages", parse_stages),
    "file_formats": ("file_formats.csv", "FileFormats", parse_file_formats),
    "tables": ("tables.csv", "Tables", parse_tables),
    "service_users": ("service_users.csv", "ServiceUsers", parse_service_users),
    "functional_roles": ("functional_roles.csv", "FunctionalRoles", parse_functional_roles),
    "functional_grants": ("functional_grants.csv", "FunctionalGrants", parse_functional_grants),
    "masking_rules": ("masking_rules.csv", "MaskingRules", parse_masking_rules),
    "pii_columns": ("pii_columns.csv", "PiiColumns", parse_pii_columns),
    "masking_exemptions": ("masking_exemptions.csv", "MaskingExemptions", parse_masking_exemptions),
    "human_users": ("human_users.csv", "HumanUsers", parse_human_users),
    "user_roles": ("user_roles.csv", "UserRoles", parse_user_roles),
}


# ── Readers ───────────────────────────────────────────────────────────────────

def load_csv(filename):
    path = os.path.join(CONFIG_DIR, filename)
    if not os.path.exists(path):
        sys.exit(f"Error: {path} not found")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_from_csv():
    return {name: parser(load_csv(fname)) for name, (fname, _, parser) in PARSERS.items()}


def load_from_excel():
    try:
        import openpyxl
    except ImportError:
        sys.exit("Error: openpyxl not installed. Run: pip install openpyxl")
    if not os.path.exists(EXCEL_FILE):
        sys.exit(f"Error: {EXCEL_FILE} not found")
    wb = openpyxl.load_workbook(EXCEL_FILE, data_only=True)

    def sheet_rows(sheet_name):
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
        headers = [str(h).strip() for h in rows[0]]
        return [
            {headers[i]: (str(c) if c is not None else "") for i, c in enumerate(row)}
            for row in rows[1:]
            if any(c is not None for c in row)
        ]

    return {name: parser(sheet_rows(sheet)) for name, (_, sheet, parser) in PARSERS.items()}


# ── Cross-file validation — fail here, not at terraform apply ─────────────────

def validate(manifests):
    schema_names = {v["schema"] for v in manifests["schemas"].values() if v["is_active"]}
    func_names = {v["name"] for v in manifests["functional_roles"].values() if v["is_active"]}
    active_envs = {v["env"] for v in manifests["environments"].values() if v["is_active"]}

    # Warehouses: functions referenced by roles must exist; exactly one
    # is_default per function (it becomes service users' default warehouse).
    wh_functions = {v["function"] for v in manifests["warehouses"].values() if v["is_active"]}
    for fn in sorted(wh_functions):
        defaults = [k for k, v in manifests["warehouses"].items()
                    if v["is_active"] and v["function"] == fn and v["is_default"]]
        if len(defaults) != 1:
            sys.exit(f"warehouses: function '{fn}' needs exactly one is_default=true row (found {len(defaults)})")

    # Service users hold ONE functional role; validate the role + warehouse fn.
    for k, su in manifests["service_users"].items():
        if not su["is_active"]:
            continue
        if su["role"] not in func_names:
            sys.exit(f"service_users[{k}]: unknown functional role '{su['role']}'")
        if su["warehouse"] not in wh_functions:
            sys.exit(f"service_users[{k}]: unknown warehouse function '{su['warehouse']}'")

    # Storage layer: stages must reference known schemas/integrations; the
    # integration's granted_to_roles must be known functional roles.
    integration_names = {v["name"] for v in manifests["storage_integrations"].values() if v["is_active"]}
    for k, si in manifests["storage_integrations"].items():
        if not si["is_active"]:
            continue
        for r in si["granted_to_service_roles"]:
            if r not in func_names:
                sys.exit(f"storage_integrations[{k}]: unknown role '{r}' (must be a functional role)")
    for k, st in manifests["stages"].items():
        if not st["is_active"]:
            continue
        if st["schema"] not in schema_names:
            sys.exit(f"stages[{k}]: unknown schema '{st['schema']}'")
        if st["stage_type"] == "EXTERNAL" and st["storage_integration"] not in integration_names:
            sys.exit(f"stages[{k}]: unknown storage integration '{st['storage_integration']}'")
    for k, ff in manifests["file_formats"].items():
        if ff["is_active"] and ff["schema"] not in schema_names:
            sys.exit(f"file_formats[{k}]: unknown schema '{ff['schema']}'")

    # Tables: only for custom-ingestion schemas (never Fivetran-owned ones,
    # where the connector manages DDL); each needs a column-definition JSON.
    fivetran_owned = {
        v["schema"] for v in manifests["schemas"].values()
        if v["is_active"] and v["schema"].endswith("_FIVETRAN")
    }
    for k, t in manifests["tables"].items():
        if not t["is_active"]:
            continue
        if t["schema"] not in schema_names:
            sys.exit(f"tables[{k}]: unknown schema '{t['schema']}'")
        if t["schema"] in fivetran_owned:
            sys.exit(f"tables[{k}]: schema '{t['schema']}' is Fivetran-owned - the connector manages its DDL")
        col_file = os.path.join(HERE, "resources", "tables", f"{k}.json")
        if not os.path.exists(col_file):
            sys.exit(f"tables[{k}]: missing column definition file resources/tables/{k}.json")
        with open(col_file, encoding="utf-8") as f:
            try:
                cols = json.load(f).get("columns", [])
            except json.JSONDecodeError as e:
                sys.exit(f"tables[{k}]: invalid JSON in resources/tables/{k}.json ({e})")
        if not cols:
            sys.exit(f"tables[{k}]: resources/tables/{k}.json has no columns")

    for k, fr in manifests["functional_roles"].items():
        if not fr["is_active"]:
            continue
        if fr["warehouse"] and fr["warehouse"] not in wh_functions:
            sys.exit(f"functional_roles[{k}]: unknown warehouse function '{fr['warehouse']}'")
        for p in fr["inherits_from"]:
            if p not in func_names:
                sys.exit(f"functional_roles[{k}]: inherits_from unknown role '{p}'")

    # Masking vocabulary is now data-driven: known tags come from ACTIVE
    # masking_rules rows, not a hardcoded list. Adding a tag = a CSV row.
    known_tags = {r["tag"] for r in manifests["masking_rules"].values() if r["is_active"]}
    for k, r in manifests["masking_rules"].items():
        if not r["is_active"]:
            continue
        if "VAL" not in r["mask_expression"] and r["mask_expression"].upper() != "NULL":
            sys.exit(f"masking_rules[{k}]: mask_expression must reference VAL (or be NULL), got '{r['mask_expression']}'")
    # One policy per (tag, data_type) — Snowflake allows multiple policies on a
    # tag only if their data types differ; a duplicate pair is a collision.
    seen_pairs = {}
    for k, r in manifests["masking_rules"].items():
        if not r["is_active"]:
            continue
        pair = (r["tag"], r["data_type"])
        if pair in seen_pairs:
            sys.exit(f"masking_rules[{k}]: duplicate (tag, data_type) {pair} also in '{seen_pairs[pair]}'")
        seen_pairs[pair] = k

    for k, p in manifests["pii_columns"].items():
        if not p["is_active"]:
            continue
        if p["schema"] not in schema_names:
            sys.exit(f"pii_columns[{k}]: unknown schema '{p['schema']}'")
        if p["tag"] not in known_tags:
            sys.exit(f"pii_columns[{k}]: unknown tag '{p['tag']}' (define it in masking_rules.csv)")

    for k, ex in manifests["masking_exemptions"].items():
        if not ex["is_active"]:
            continue
        if ex["tag"] not in known_tags:
            sys.exit(f"masking_exemptions[{k}]: unknown tag '{ex['tag']}' (define it in masking_rules.csv)")
        if ex["role"] not in func_names:
            sys.exit(f"masking_exemptions[{k}]: unknown functional role '{ex['role']}'")

    # SERVICE-ONLY roles (human_assignable=false) must never reach a human.
    human_ok = {v["name"] for v in manifests["functional_roles"].values()
                if v["is_active"] and v.get("human_assignable", True)}
    for k, hu in manifests["human_users"].items():
        if not hu["is_active"]:
            continue
        if hu["default_role"] and hu["default_role"] not in func_names:
            sys.exit(f"human_users[{k}]: default_role '{hu['default_role']}' is not an active functional role")
        if hu["default_role"] and hu["default_role"] not in human_ok:
            sys.exit(f"human_users[{k}]: default_role '{hu['default_role']}' is SERVICE-ONLY (human_assignable=false)")
    for k, ur in manifests["user_roles"].items():
        if ur["is_active"] and ur["role_name"] not in human_ok:
            sys.exit(f"user_roles[{k}]: role '{ur['role_name']}' is SERVICE-ONLY (human_assignable=false) - humans cannot hold it")

    for k, g in manifests["functional_grants"].items():
        if not g["is_active"]:
            continue
        if g["role"] not in func_names:
            sys.exit(f"functional_grants[{k}]: unknown role '{g['role']}'")
        if g["env"] != "ALL" and g["env"] not in active_envs:
            sys.exit(f"functional_grants[{k}]: env '{g['env']}' is not an active environment")
        exact = not g["schema"].endswith("*")
        if exact and g["schema"] not in schema_names:
            sys.exit(f"functional_grants[{k}]: unknown schema '{g['schema']}' (use PREFIX* for sandboxes)")


# ── Writer ────────────────────────────────────────────────────────────────────

def write_manifest(name, data, dry_run):
    payload = json.dumps({name: data}, indent=2)
    path = os.path.join(INFRA_DIR, f"{name}.json")
    if dry_run:
        print(f"\n{'-' * 60}\n[dry-run] {path}\n{payload}")
    else:
        os.makedirs(INFRA_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
        print(f"Written  {path}  ({len(data)} entries)")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--csv", action="store_true", help="Force CSV input")
    source.add_argument("--excel", action="store_true", help="Force Excel input (requires openpyxl)")
    parser.add_argument("--dry-run", action="store_true", help="Print JSON without writing files")
    args = parser.parse_args()

    if args.excel or (not args.csv and os.path.exists(EXCEL_FILE)):
        manifests = load_from_excel()
        print(f"Source: {EXCEL_FILE}")
    else:
        manifests = load_from_csv()
        print(f"Source: {CONFIG_DIR}\\*.csv")

    validate(manifests)

    for name, data in manifests.items():
        write_manifest(name, data, args.dry_run)

    if not args.dry_run:
        print("\nDone - commit config/ + resources/ together; CI runs terraform plan on the PR.")


if __name__ == "__main__":
    main()
