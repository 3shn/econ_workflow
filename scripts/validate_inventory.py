#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ipaddress
import pathlib
import sys
import tomllib
from typing import Any


def _fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)


def _required_keys(obj: dict[str, Any], keys: list[str], where: str) -> list[str]:
    missing = [k for k in keys if k not in obj]
    if missing:
        _fail(f"{where} missing required keys: {', '.join(missing)}")
    return missing


def _validate_ip(value: str, where: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        _fail(f"{where} invalid IP address: {value}")
        return False
    return True


def _validate_cidr(value: str, where: str) -> bool:
    try:
        ipaddress.ip_network(value, strict=False)
    except ValueError:
        _fail(f"{where} invalid CIDR: {value}")
        return False
    return True


def validate(data: dict[str, Any]) -> int:
    errors = 0

    for top in ("meta", "proxmox"):
        if top not in data or not isinstance(data[top], dict):
            _fail(f"top-level table `{top}` is required")
            errors += 1

    arrays = {
        "networks": ("id", "vlan", "cidr"),
        "assets": ("id", "kind", "network_id", "ip"),
        "services": ("id", "asset_id", "name", "listen_ip", "port", "protocol"),
    }
    for arr_name in arrays:
        if arr_name not in data or not isinstance(data[arr_name], list):
            _fail(f"array `[[{arr_name}]]` is required")
            errors += 1

    if errors:
        return errors

    network_ids: set[str] = set()
    asset_ids: set[str] = set()
    service_ids: set[str] = set()

    for idx, item in enumerate(data["networks"]):
        where = f"networks[{idx}]"
        if not isinstance(item, dict):
            _fail(f"{where} must be a table")
            errors += 1
            continue
        errors += len(_required_keys(item, list(arrays["networks"]), where))
        nid = item.get("id")
        if isinstance(nid, str):
            if nid in network_ids:
                _fail(f"{where} duplicate network id: {nid}")
                errors += 1
            network_ids.add(nid)
        else:
            _fail(f"{where}.id must be a string")
            errors += 1
        vlan = item.get("vlan")
        if not isinstance(vlan, int) or vlan < 1 or vlan > 4094:
            _fail(f"{where}.vlan must be an integer in [1, 4094]")
            errors += 1
        cidr = item.get("cidr")
        if not isinstance(cidr, str) or not _validate_cidr(cidr, f"{where}.cidr"):
            errors += 1
        gateway = item.get("gateway")
        if gateway is not None:
            if not isinstance(gateway, str) or not _validate_ip(gateway, f"{where}.gateway"):
                errors += 1

    for idx, item in enumerate(data["assets"]):
        where = f"assets[{idx}]"
        if not isinstance(item, dict):
            _fail(f"{where} must be a table")
            errors += 1
            continue
        errors += len(_required_keys(item, list(arrays["assets"]), where))
        aid = item.get("id")
        if isinstance(aid, str):
            if aid in asset_ids:
                _fail(f"{where} duplicate asset id: {aid}")
                errors += 1
            asset_ids.add(aid)
        else:
            _fail(f"{where}.id must be a string")
            errors += 1
        network_id = item.get("network_id")
        if not isinstance(network_id, str) or network_id not in network_ids:
            _fail(f"{where}.network_id must reference an existing networks.id")
            errors += 1
        ip = item.get("ip")
        if not isinstance(ip, str) or not _validate_ip(ip, f"{where}.ip"):
            errors += 1

    for idx, item in enumerate(data["services"]):
        where = f"services[{idx}]"
        if not isinstance(item, dict):
            _fail(f"{where} must be a table")
            errors += 1
            continue
        errors += len(_required_keys(item, list(arrays["services"]), where))
        sid = item.get("id")
        if isinstance(sid, str):
            if sid in service_ids:
                _fail(f"{where} duplicate service id: {sid}")
                errors += 1
            service_ids.add(sid)
        else:
            _fail(f"{where}.id must be a string")
            errors += 1
        asset_id = item.get("asset_id")
        if not isinstance(asset_id, str) or asset_id not in asset_ids:
            _fail(f"{where}.asset_id must reference an existing assets.id")
            errors += 1
        listen_ip = item.get("listen_ip")
        if not isinstance(listen_ip, str) or not _validate_ip(listen_ip, f"{where}.listen_ip"):
            errors += 1
        port = item.get("port")
        if not isinstance(port, int) or port < 1 or port > 65535:
            _fail(f"{where}.port must be an integer in [1, 65535]")
            errors += 1

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate infrastructure inventory TOML.")
    parser.add_argument("path", type=pathlib.Path, help="Path to inventory TOML file.")
    args = parser.parse_args()

    try:
        with args.path.open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        _fail(f"file not found: {args.path}")
        return 2
    except tomllib.TOMLDecodeError as exc:
        _fail(f"TOML parse error: {exc}")
        return 2

    err_count = validate(data)
    if err_count:
        print(f"Validation failed with {err_count} error(s).", file=sys.stderr)
        return 1

    print("Validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
