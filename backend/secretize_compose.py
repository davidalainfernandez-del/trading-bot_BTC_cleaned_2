#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, os, re, sys
from pathlib import Path

def need_pyyaml():
    print("This tool needs PyYAML. Install with:\n  python3 -m pip install pyyaml", file=sys.stderr)

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

SECRET_RE = re.compile(r"(KEY|SECRET|TOKEN|PASSWORD|BEARER|CLIENT_ID|CLIENT_SECRET)", re.IGNORECASE)
ALLOWLIST = {
    "TWITTER_QUERY", "TWITTER_MAX_RESULTS", "TWITTER_TTL",
    "REDDIT_SUBS", "REDDIT_USER_AGENT", "REDDIT_USERNAME", "REDDIT_PASSWORD"
}

def is_secret_key(k: str) -> bool:
    return bool(SECRET_RE.search(k)) or (k in ALLOWLIST)

def parse_env_file(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#"): continue
            if "=" in s:
                k, v = s.split("=", 1)
                env[k.strip()] = v.strip()
    return env

def quote_env_value(v: str) -> str:
    # Quote if contains spaces or special chars; escape internal double quotes
    if v is None:
        return ""
    needs = any(c.isspace() for c in v) or any(c in v for c in ['"', "'", '#'])
    if needs:
        return '"' + v.replace('"','\\"') + '"'
    return v

def env_dict_from_any(env_section):
    """
    Converts docker compose 'environment' which can be a dict or a list ["A=B","C=D"]
    to a dict, and returns (dict, original_was_list, original_list_keys_order)
    """
    if env_section is None:
        return {}, False, []
    if isinstance(env_section, dict):
        return dict(env_section), False, list(env_section.keys())
    if isinstance(env_section, list):
        out = {}
        order = []
        for item in env_section:
            if isinstance(item, str) and "=" in item:
                k, v = item.split("=", 1)
                out[k] = v
                order.append(k)
            elif isinstance(item, str):
                out[item] = None
                order.append(item)
        return out, True, order
    return {}, False, []

def env_any_from_dict(d: dict, original_was_list: bool, order: list):
    if original_was_list:
        items = []
        for k in order:
            if k in d:
                v = d[k]
                if v is None:
                    items.append(k)
                else:
                    items.append(f"{k}={v}")
        # include any new keys at end
        for k, v in d.items():
            if k not in order:
                items.append(f"{k}={v}" if v is not None else k)
        return items
    else:
        return d

def process_compose(path: Path, env_map: dict, keys_only: set, dry_run=False):
    try:
        import yaml  # local import to honor availability
    except Exception:
        need_pyyaml()
        sys.exit(1)

    if not path.exists():
        return {"updated": False, "missing": True, "moved": []}

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "services" not in data:
        return {"updated": False, "missing": False, "moved": []}

    moved = []
    services = data.get("services", {})
    for svc_name, svc in services.items():
        env_section = svc.get("environment")
        env_dict, was_list, order = env_dict_from_any(env_section)
        changed = False
        for k, v in list(env_dict.items()):
            if v is None:
                continue
            # Skip if already ${VAR}
            if isinstance(v, str) and re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}", v):
                continue
            if keys_only and k not in keys_only and not is_secret_key(k):
                continue
            # Mark as to-be-moved
            env_value = str(v)
            moved.append((svc_name, k, env_value))
            # Replace in compose with ${VAR}
            env_dict[k] = "${" + k + "}"
            changed = True
            # Add to .env map if missing
            if k not in env_map:
                env_map[k] = env_value
        if changed:
            services[svc_name]["environment"] = env_any_from_dict(env_dict, was_list, order)

    data["services"] = services

    if dry_run:
        print(f"[DRY-RUN] Would modify {path} and move {len(moved)} vars to .env")
        return {"updated": False, "missing": False, "moved": moved}

    # Backup and write
    backup = path.with_suffix(path.suffix + ".bak")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False)

    return {"updated": True, "missing": False, "moved": moved, "backup": str(backup)}

def write_env(path: Path, env_map: dict, dry_run=False):
    if dry_run:
        print("[DRY-RUN] .env would include these keys:", ", ".join(sorted(env_map.keys())))
        return {"written": False}
    # Merge with existing while keeping existing values intact
    existing = parse_env_file(path)
    for k, v in env_map.items():
        if k not in existing:
            existing[k] = v
    # Write back
    with path.open("w", encoding="utf-8") as f:
        for k in sorted(existing.keys()):
            v = existing[k]
            # Quote if needed
            needs = any(c.isspace() for c in v) or any(c in v for c in ['"', "'", '#'])
            if needs:
                v = '"' + v.replace('"','\\"') + '"'
            f.write(f"{k}={v}\n")
    return {"written": True, "path": str(path)}

def main():
    ap = argparse.ArgumentParser(description="Move secrets/config from docker-compose files into .env and reference via ${VAR}.")
    ap.add_argument("--compose", default="docker-compose.yml", help="Path to base compose file")
    ap.add_argument("--override", default="docker-compose.override.yml", help="Path to override compose (optional)")
    ap.add_argument("--env-file", default=".env", help="Path to .env file to create/update")
    ap.add_argument("--only-keys", default="", help="Comma-separated keys to move (if set, ignore heuristics)")
    ap.add_argument("--dry-run", action="store_true", help="Print changes without writing files")
    args = ap.parse_args()

    env_path = Path(args.env_file)

    keys_only = set([k.strip() for k in args.only_keys.split(",") if k.strip()])

    # Start with current env content
    env_current = parse_env_file(env_path)

    results = []
    for p in [Path(args.compose), Path(args.override)]:
        r = process_compose(p, env_current, keys_only, dry_run=args.dry_run)
        results.append((p, r))

    env_res = write_env(env_path, env_current, dry_run=args.dry_run)

    # Summary
    moved_total = sum(len(r.get("moved", [])) for _, r in results)
    print(f"Moved {moved_total} variables into {env_path}.")
    for p, r in results:
        if r.get("missing"):
            print(f"- Skipped: {p} (not found)")
        else:
            print(f"- Updated: {p} | moved: {len(r.get('moved', []))} | backup: {r.get('backup','-')}")

if __name__ == "__main__":
    main()
