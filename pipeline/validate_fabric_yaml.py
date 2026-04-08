#!/usr/bin/env python3
"""
Strict validator for EVPN/VXLAN fabric intent.

Usage:
    python validate_fabric_yaml.py /path/to/fabric.yaml

Exit codes:
    0 = validation passed
    1 = validation failed
    2 = usage / file / parse error
"""

from __future__ import annotations

import ipaddress
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import yaml


ALLOWED_BLOCK_TYPES = {"compute", "storage", "object"}
ALLOWED_MODES = {"l2", "l3"}

LOCAL_VLAN_MIN = 100
LOCAL_VLAN_MAX = 999

STRETCHED_VLAN_MIN = 1000
STRETCHED_VLAN_MAX = 4094

VRF_ID_MIN = 1
VRF_ID_MAX = 9999


@dataclass
class ValidationResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def ok(self) -> bool:
        return not self.errors


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"ERROR: file not found: {path}")
    except yaml.YAMLError as exc:
        raise SystemExit(f"ERROR: invalid YAML in {path}: {exc}")

    if not isinstance(data, dict):
        raise SystemExit("ERROR: top-level YAML object must be a mapping")

    return data


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and value > 0


def _classify_vlan(vlan_id: int) -> str | None:
    if LOCAL_VLAN_MIN <= vlan_id <= LOCAL_VLAN_MAX:
        return "local"
    if STRETCHED_VLAN_MIN <= vlan_id <= STRETCHED_VLAN_MAX:
        return "stretched"
    return None


def _validate_top_level(data: Dict[str, Any], result: ValidationResult) -> None:
    required = {"fabrics", "tenants"}
    missing = required - set(data.keys())

    for key in sorted(missing):
        result.error(f"missing top-level key: '{key}'")

    fabrics = data.get("fabrics")
    tenants = data.get("tenants")

    if fabrics is not None and not isinstance(fabrics, list):
        result.error("'fabrics' must be a list")

    if tenants is not None and not isinstance(tenants, list):
        result.error("'tenants' must be a list")


def _validate_fabrics(
    data: Dict[str, Any],
    result: ValidationResult,
) -> Dict[int, Dict[str, Dict[str, int]]]:
    fabrics_by_id: Dict[int, Dict[str, Dict[str, int]]] = {}
    fabrics = data.get("fabrics", [])

    if not isinstance(fabrics, list):
        return fabrics_by_id

    if not fabrics:
        result.error("'fabrics' must not be empty")
        return fabrics_by_id

    seen_fabric_ids: Set[int] = set()
    seen_fabric_names: Set[str] = set()

    for idx, fabric in enumerate(fabrics, start=1):
        ctx = f"fabrics[{idx}]"

        if not isinstance(fabric, dict):
            result.error(f"{ctx} must be a mapping")
            continue

        allowed_keys = {"fabric_id", "name", "asn", "blocks"}
        unknown_keys = set(fabric.keys()) - allowed_keys
        if unknown_keys:
            result.error(f"{ctx} contains unsupported key(s): {sorted(unknown_keys)}")

        fabric_id = fabric.get("fabric_id")
        if not _is_positive_int(fabric_id):
            result.error(f"{ctx}.fabric_id must be a positive integer")
            continue

        if fabric_id in seen_fabric_ids:
            result.error(f"duplicate fabric_id: {fabric_id}")
            continue
        seen_fabric_ids.add(fabric_id)

        name = fabric.get("name")
        if not isinstance(name, str) or not name.strip():
            result.error(f"{ctx}.name must be a non-empty string")
        elif name in seen_fabric_names:
            result.error(f"duplicate fabric name: '{name}'")
        else:
            seen_fabric_names.add(name)

        asn = fabric.get("asn")
        if not _is_positive_int(asn):
            result.error(f"{ctx}.asn must be a positive integer")

        blocks = fabric.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            result.error(f"{ctx}.blocks must be a non-empty list")
            continue

        fabric_blocks: Dict[str, Dict[str, int]] = {}
        for bidx, block in enumerate(blocks, start=1):
            bctx = f"{ctx}.blocks[{bidx}]"

            if not isinstance(block, dict):
                result.error(f"{bctx} must be a mapping")
                continue

            allowed_block_keys = {"block_type", "leaf_pairs", "spines"}
            unknown_block_keys = set(block.keys()) - allowed_block_keys
            if unknown_block_keys:
                result.error(
                    f"{bctx} contains unsupported key(s): {sorted(unknown_block_keys)}"
                )

            block_type = block.get("block_type")
            if block_type not in ALLOWED_BLOCK_TYPES:
                result.error(
                    f"{bctx}.block_type must be one of {sorted(ALLOWED_BLOCK_TYPES)}"
                )
                continue

            if block_type in fabric_blocks:
                result.error(
                    f"{ctx}.blocks contains duplicate block_type '{block_type}'"
                )
                continue

            leaf_pairs = block.get("leaf_pairs")
            if not _is_positive_int(leaf_pairs):
                result.error(f"{bctx}.leaf_pairs must be a positive integer")

            spines = block.get("spines")
            if not _is_positive_int(spines):
                result.error(f"{bctx}.spines must be a positive integer")

            fabric_blocks[block_type] = {
                "leaf_pairs": leaf_pairs if _is_positive_int(leaf_pairs) else 0,
                "spines": spines if _is_positive_int(spines) else 0,
            }

        if fabric_blocks:
            fabrics_by_id[fabric_id] = fabric_blocks

    return fabrics_by_id


def _expand_leaf_pair_ids(
    value: Any,
    ctx: str,
    result: ValidationResult,
) -> List[int]:
    if not isinstance(value, list) or not value:
        result.error(f"{ctx}.leaf_pair_ids must be a non-empty list")
        return []

    expanded: List[int] = []
    seen: Set[int] = set()

    for item in value:
        if not _is_positive_int(item):
            result.error(f"{ctx}.leaf_pair_ids contains invalid value: {item!r}")
            continue
        if item in seen:
            result.error(f"{ctx}.leaf_pair_ids repeats leaf pair {item}")
            continue
        seen.add(item)
        expanded.append(item)

    return expanded


def _validate_apply_to_targets(
    value: Any,
    ctx: str,
    fabrics_by_id: Dict[int, Dict[str, Dict[str, int]]],
    attachment_targets: Set[Tuple[int, str, int]],
    result: ValidationResult,
) -> None:
    if not isinstance(value, list) or not value:
        result.error(f"{ctx}.apply_to must be a non-empty list")
        return

    seen_targets: Set[Tuple[int, str, int]] = set()

    for tidx, target in enumerate(value, start=1):
        tctx = f"{ctx}.apply_to[{tidx}]"

        if not isinstance(target, dict):
            result.error(f"{tctx} must be a mapping")
            continue

        allowed_target_keys = {"fabric_id", "block_type", "leaf_pair_ids"}
        unknown_target_keys = set(target.keys()) - allowed_target_keys
        if unknown_target_keys:
            result.error(
                f"{tctx} contains unsupported key(s): {sorted(unknown_target_keys)}"
            )

        fabric_id = target.get("fabric_id")
        if fabric_id not in fabrics_by_id:
            result.error(f"{tctx}.fabric_id references unknown fabric: {fabric_id}")
            continue

        block_type = target.get("block_type")
        if block_type not in ALLOWED_BLOCK_TYPES:
            result.error(
                f"{tctx}.block_type must be one of {sorted(ALLOWED_BLOCK_TYPES)}"
            )
            continue

        if block_type not in fabrics_by_id[fabric_id]:
            result.error(
                f"{tctx}.block_type '{block_type}' is not defined in fabric {fabric_id}"
            )
            continue

        max_leaf_pairs = fabrics_by_id[fabric_id][block_type]["leaf_pairs"]
        leaf_pair_ids = _expand_leaf_pair_ids(target.get("leaf_pair_ids"), tctx, result)

        for leaf_pair_id in leaf_pair_ids:
            if leaf_pair_id > max_leaf_pairs:
                result.error(
                    f"{tctx}.leaf_pair_ids contains {leaf_pair_id}, "
                    f"which exceeds defined leaf_pairs ({max_leaf_pairs}) "
                    f"for fabric {fabric_id} block '{block_type}'"
                )
                continue

            atomic_target = (fabric_id, block_type, leaf_pair_id)

            if atomic_target in seen_targets:
                result.error(
                    f"{tctx} duplicates static route apply target "
                    f"(fabric_id={fabric_id}, block_type='{block_type}', "
                    f"leaf_pair_id={leaf_pair_id})"
                )
                continue

            seen_targets.add(atomic_target)

            if atomic_target not in attachment_targets:
                result.error(
                    f"{tctx} applies route to unattached target "
                    f"(fabric_id={fabric_id}, block_type='{block_type}', "
                    f"leaf_pair_id={leaf_pair_id})"
                )


def _validate_tenants(
    data: Dict[str, Any],
    fabrics_by_id: Dict[int, Dict[str, Dict[str, int]]],
    result: ValidationResult,
) -> None:
    tenants = data.get("tenants", [])

    if not isinstance(tenants, list):
        return

    if not tenants:
        result.error("'tenants' must not be empty")
        return

    tenant_names: Set[str] = set()
    vrf_ids: Set[int] = set()
    global_stretched_vlans: Dict[int, str] = {}

    for tidx, tenant in enumerate(tenants, start=1):
        tctx = f"tenants[{tidx}]"

        if not isinstance(tenant, dict):
            result.error(f"{tctx} must be a mapping")
            continue

        allowed_tenant_keys = {
            "tenant_name",
            "vrf_id",
            "description",
            "vlans",
            "attachment",
            "static_routes",
        }
        unknown_tenant_keys = set(tenant.keys()) - allowed_tenant_keys
        if unknown_tenant_keys:
            result.error(
                f"{tctx} contains unsupported key(s): {sorted(unknown_tenant_keys)}"
            )

        tenant_name = tenant.get("tenant_name")
        if not isinstance(tenant_name, str) or not tenant_name.strip():
            result.error(f"{tctx}.tenant_name must be a non-empty string")
            continue

        if tenant_name in tenant_names:
            result.error(f"duplicate tenant_name: '{tenant_name}'")
        else:
            tenant_names.add(tenant_name)

        vrf_id = tenant.get("vrf_id")
        if not isinstance(vrf_id, int) or not (VRF_ID_MIN <= vrf_id <= VRF_ID_MAX):
            result.error(
                f"{tctx}.vrf_id must be an integer in range {VRF_ID_MIN}-{VRF_ID_MAX}"
            )
        elif vrf_id in vrf_ids:
            result.error(f"duplicate vrf_id: {vrf_id}")
        else:
            vrf_ids.add(vrf_id)

        description = tenant.get("description")
        if description is not None and not isinstance(description, str):
            result.error(f"{tctx}.description must be a string if present")

        vlans = tenant.get("vlans")
        if not isinstance(vlans, list) or not vlans:
            result.error(f"{tctx}.vlans must be a non-empty list")
            continue

        vlan_defs: Dict[int, Dict[str, Any]] = {}
        vlan_names: Set[str] = set()

        for vidx, vlan in enumerate(vlans, start=1):
            vctx = f"{tctx}.vlans[{vidx}]"

            if not isinstance(vlan, dict):
                result.error(f"{vctx} must be a mapping")
                continue

            allowed_vlan_keys = {"vlan_id", "name", "mode"}
            unknown_vlan_keys = set(vlan.keys()) - allowed_vlan_keys
            if unknown_vlan_keys:
                result.error(
                    f"{vctx} contains unsupported key(s): {sorted(unknown_vlan_keys)}"
                )

            vlan_id = vlan.get("vlan_id")
            if not isinstance(vlan_id, int):
                result.error(f"{vctx}.vlan_id must be an integer")
                continue

            vlan_class = _classify_vlan(vlan_id)
            if vlan_class is None:
                result.error(
                    f"{vctx}.vlan_id {vlan_id} is outside allowed ranges "
                    f"({LOCAL_VLAN_MIN}-{LOCAL_VLAN_MAX} local, "
                    f"{STRETCHED_VLAN_MIN}-{STRETCHED_VLAN_MAX} stretched)"
                )
                continue

            if vlan_id in vlan_defs:
                result.error(f"duplicate vlan_id {vlan_id} inside tenant '{tenant_name}'")
                continue

            name = vlan.get("name")
            if not isinstance(name, str) or not name.strip():
                result.error(f"{vctx}.name must be a non-empty string")
            elif name in vlan_names:
                result.error(f"duplicate VLAN name '{name}' inside tenant '{tenant_name}'")
            else:
                vlan_names.add(name)

            mode = vlan.get("mode")
            if mode not in ALLOWED_MODES:
                result.error(f"{vctx}.mode must be one of {sorted(ALLOWED_MODES)}")

            vlan_defs[vlan_id] = vlan

            if vlan_class == "stretched":
                previous_tenant = global_stretched_vlans.get(vlan_id)
                if previous_tenant and previous_tenant != tenant_name:
                    result.error(
                        f"stretched VLAN {vlan_id} appears in multiple tenants: "
                        f"'{previous_tenant}' and '{tenant_name}'"
                    )
                else:
                    global_stretched_vlans[vlan_id] = tenant_name

        attachments = tenant.get("attachment")
        if not isinstance(attachments, list) or not attachments:
            result.error(f"{tctx}.attachment must be a non-empty list")
            continue

        used_vlans: Set[int] = set()
        attachment_targets: Set[Tuple[int, str, int]] = set()
        vlan_fabrics: Dict[int, Set[int]] = {}

        for aidx, item in enumerate(attachments, start=1):
            actx = f"{tctx}.attachment[{aidx}]"

            if not isinstance(item, dict):
                result.error(f"{actx} must be a mapping")
                continue

            allowed_attachment_keys = {"fabric_id", "block_type", "leaf_pair_ids", "vlans"}
            unknown_attachment_keys = set(item.keys()) - allowed_attachment_keys
            if unknown_attachment_keys:
                result.error(
                    f"{actx} contains unsupported key(s): {sorted(unknown_attachment_keys)}"
                )

            fabric_id = item.get("fabric_id")
            if fabric_id not in fabrics_by_id:
                result.error(f"{actx}.fabric_id references unknown fabric: {fabric_id}")
                continue

            block_type = item.get("block_type")
            if block_type not in ALLOWED_BLOCK_TYPES:
                result.error(
                    f"{actx}.block_type must be one of {sorted(ALLOWED_BLOCK_TYPES)}"
                )
                continue

            if block_type not in fabrics_by_id[fabric_id]:
                result.error(
                    f"{actx}.block_type '{block_type}' is not defined in fabric {fabric_id}"
                )
                continue

            max_leaf_pairs = fabrics_by_id[fabric_id][block_type]["leaf_pairs"]
            leaf_pair_ids = _expand_leaf_pair_ids(item.get("leaf_pair_ids"), actx, result)

            vlans_here = item.get("vlans")
            if not isinstance(vlans_here, list) or not vlans_here:
                result.error(f"{actx}.vlans must be a non-empty list")
                vlans_here = []

            atomic_targets_for_item: List[Tuple[int, str, int]] = []
            for leaf_pair_id in leaf_pair_ids:
                if leaf_pair_id > max_leaf_pairs:
                    result.error(
                        f"{actx}.leaf_pair_ids contains {leaf_pair_id}, "
                        f"which exceeds defined leaf_pairs ({max_leaf_pairs}) "
                        f"for fabric {fabric_id} block '{block_type}'"
                    )
                    continue

                atomic_target = (fabric_id, block_type, leaf_pair_id)

                if atomic_target in attachment_targets:
                    result.error(
                        f"{actx} duplicates attachment target "
                        f"(fabric_id={fabric_id}, block_type='{block_type}', "
                        f"leaf_pair_id={leaf_pair_id})"
                    )
                    continue

                attachment_targets.add(atomic_target)
                atomic_targets_for_item.append(atomic_target)

            seen_vlans_here: Set[int] = set()
            for vlan_id in vlans_here:
                if not isinstance(vlan_id, int):
                    result.error(f"{actx}.vlans contains non-integer value: {vlan_id!r}")
                    continue

                if vlan_id in seen_vlans_here:
                    result.error(f"{actx}.vlans repeats VLAN {vlan_id}")
                    continue
                seen_vlans_here.add(vlan_id)

                if vlan_id not in vlan_defs:
                    result.error(
                        f"{actx}.vlans references VLAN {vlan_id} not defined in tenant "
                        f"'{tenant_name}'"
                    )
                    continue

                used_vlans.add(vlan_id)
                vlan_fabrics.setdefault(vlan_id, set()).add(fabric_id)

        for vlan_id in sorted(vlan_defs):
            if vlan_id not in used_vlans:
                result.error(
                    f"tenant '{tenant_name}' defines VLAN {vlan_id} but does not attach it anywhere"
                )

        for vlan_id, fabrics_used in sorted(vlan_fabrics.items()):
            vlan_class = _classify_vlan(vlan_id)
            if vlan_class == "stretched" and len(fabrics_used) < 2:
                result.error(
                    f"tenant '{tenant_name}' VLAN {vlan_id} is in stretched range "
                    f"but is attached in only {len(fabrics_used)} fabric(s): "
                    f"{sorted(fabrics_used)}"
                )

        static_routes = tenant.get("static_routes", [])
        if static_routes is None:
            static_routes = []

        if not isinstance(static_routes, list):
            result.error(f"{tctx}.static_routes must be a list if present")
            static_routes = []

        for sidx, route in enumerate(static_routes, start=1):
            sctx = f"{tctx}.static_routes[{sidx}]"

            if not isinstance(route, dict):
                result.error(f"{sctx} must be a mapping")
                continue

            allowed_route_keys = {"prefix", "next_hop", "apply_to"}
            unknown_route_keys = set(route.keys()) - allowed_route_keys
            if unknown_route_keys:
                result.error(
                    f"{sctx} contains unsupported key(s): {sorted(unknown_route_keys)}"
                )

            prefix = route.get("prefix")
            next_hop = route.get("next_hop")

            try:
                ipaddress.ip_network(prefix, strict=False)
            except Exception:
                result.error(f"{sctx}.prefix is not a valid IP prefix: {prefix!r}")

            try:
                ipaddress.ip_address(next_hop)
            except Exception:
                result.error(f"{sctx}.next_hop is not a valid IP address: {next_hop!r}")

            _validate_apply_to_targets(
                route.get("apply_to"),
                sctx,
                fabrics_by_id,
                attachment_targets,
                result,
            )


def validate(data: Dict[str, Any]) -> ValidationResult:
    result = ValidationResult()
    _validate_top_level(data, result)
    fabrics_by_id = _validate_fabrics(data, result)
    _validate_tenants(data, fabrics_by_id, result)
    return result


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("Usage: python validate_fabric_yaml.py /path/to/fabric.yaml", file=sys.stderr)
        return 2

    path = Path(argv[1])
    data = _load_yaml(path)
    result = validate(data)

    if result.warnings:
        print("WARNINGS:")
        for warning in result.warnings:
            print(f" - {warning}")
        print()

    if result.errors:
        print("VALIDATION FAILED")
        for error in result.errors:
            print(f" - {error}")
        return 1

    print("VALIDATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
