#!/usr/bin/env python3
"""
Strict validator for EVPN/VXLAN fabric intent.

Usage:
    python validate_fabric.py /path/to/fabric.yaml

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


ALLOWED_BLOCKS = {"compute", "storage", "object"}
ALLOWED_MODES = {"l2", "l3"}
LOCAL_VLAN_MIN = 100
LOCAL_VLAN_MAX = 999
MULTISITE_VLAN_MIN = 1000
MULTISITE_VLAN_MAX = 4094
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


def _validate_fabrics(data: Dict[str, Any], result: ValidationResult) -> Dict[int, Dict[str, Any]]:
    fabrics_by_id: Dict[int, Dict[str, Any]] = {}
    fabrics = data.get("fabrics", [])
    if not isinstance(fabrics, list):
        return fabrics_by_id
    if not fabrics:
        result.error("'fabrics' must not be empty")
        return fabrics_by_id

    seen_ids: Set[int] = set()
    baseline_blocks: Set[str] | None = None

    for idx, fabric in enumerate(fabrics, start=1):
        ctx = f"fabrics[{idx}]"
        if not isinstance(fabric, dict):
            result.error(f"{ctx} must be a mapping")
            continue

        fabric_id = fabric.get("id")
        if not _is_positive_int(fabric_id):
            result.error(f"{ctx}.id must be a positive integer")
            continue
        if fabric_id in seen_ids:
            result.error(f"duplicate fabric id: {fabric_id}")
            continue
        seen_ids.add(fabric_id)
        fabrics_by_id[fabric_id] = fabric

        super_spines = fabric.get("super_spines")
        if not _is_positive_int(super_spines):
            result.error(f"{ctx}.super_spines must be a positive integer")

        blocks = fabric.get("blocks")
        if not isinstance(blocks, dict) or not blocks:
            result.error(f"{ctx}.blocks must be a non-empty mapping")
            continue

        block_names = set(blocks.keys())
        unknown = block_names - ALLOWED_BLOCKS
        if unknown:
            result.error(f"{ctx}.blocks contains unsupported block(s): {sorted(unknown)}")

        if baseline_blocks is None:
            baseline_blocks = block_names
        elif block_names != baseline_blocks:
            result.error(
                f"{ctx}.blocks keys {sorted(block_names)} do not match first fabric blocks {sorted(baseline_blocks)}"
            )

        for block_name, block in blocks.items():
            bctx = f"{ctx}.blocks.{block_name}"
            if block_name not in ALLOWED_BLOCKS:
                continue
            if not isinstance(block, dict):
                result.error(f"{bctx} must be a mapping")
                continue
            leaf_pairs = block.get("leaf_pairs")
            spines = block.get("spines")
            if not _is_positive_int(leaf_pairs):
                result.error(f"{bctx}.leaf_pairs must be a positive integer")
            if not _is_positive_int(spines):
                result.error(f"{bctx}.spines must be a positive integer")

    return fabrics_by_id


def _classify_vlan(vlan_id: int) -> str | None:
    if LOCAL_VLAN_MIN <= vlan_id <= LOCAL_VLAN_MAX:
        return "local"
    if MULTISITE_VLAN_MIN <= vlan_id <= MULTISITE_VLAN_MAX:
        return "multisite"
    return None


def _validate_tenants(
    data: Dict[str, Any],
    fabrics_by_id: Dict[int, Dict[str, Any]],
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
    global_multisite_vlan_ids: Dict[int, str] = {}

    for tidx, tenant in enumerate(tenants, start=1):
        tctx = f"tenants[{tidx}]"
        if not isinstance(tenant, dict):
            result.error(f"{tctx} must be a mapping")
            continue

        tenant_name = tenant.get("tenant_name")
        if not isinstance(tenant_name, str) or not tenant_name.strip():
            result.error(f"{tctx}.tenant_name must be a non-empty string")
            continue
        if tenant_name in tenant_names:
            result.error(f"duplicate tenant_name: '{tenant_name}'")
        tenant_names.add(tenant_name)

        vrf_id = tenant.get("vrf_id")
        if not isinstance(vrf_id, int) or not (VRF_ID_MIN <= vrf_id <= VRF_ID_MAX):
            result.error(f"{tctx}.vrf_id must be an integer in range {VRF_ID_MIN}-{VRF_ID_MAX}")
        elif vrf_id in vrf_ids:
            result.error(f"duplicate vrf_id: {vrf_id}")
        else:
            vrf_ids.add(vrf_id)

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

            vlan_id = vlan.get("vlan_id")
            if not isinstance(vlan_id, int):
                result.error(f"{vctx}.vlan_id must be an integer")
                continue
            vlan_class = _classify_vlan(vlan_id)
            if vlan_class is None:
                result.error(
                    f"{vctx}.vlan_id {vlan_id} is outside allowed ranges "
                    f"({LOCAL_VLAN_MIN}-{LOCAL_VLAN_MAX} local, "
                    f"{MULTISITE_VLAN_MIN}-{MULTISITE_VLAN_MAX} multisite)"
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

            if vlan_class == "multisite":
                previous_tenant = global_multisite_vlan_ids.get(vlan_id)
                if previous_tenant and previous_tenant != tenant_name:
                    result.error(
                        f"multisite VLAN {vlan_id} appears in multiple tenants: "
                        f"'{previous_tenant}' and '{tenant_name}'"
                    )
                else:
                    global_multisite_vlan_ids[vlan_id] = tenant_name

        attachment = tenant.get("attachment")
        if not isinstance(attachment, list) or not attachment:
            result.error(f"{tctx}.attachment must be a non-empty list")
            continue

        used_vlans: Set[int] = set()
        attachment_targets: Set[Tuple[int, str, int]] = set()
        vlan_fabrics: Dict[int, Set[int]] = {}
        vlan_targets: Dict[int, Set[Tuple[int, str, int]]] = {}

        for aidx, item in enumerate(attachment, start=1):
            actx = f"{tctx}.attachment[{aidx}]"
            if not isinstance(item, dict):
                result.error(f"{actx} must be a mapping")
                continue

            fabric_id = item.get("fabric_id")
            block = item.get("block")
            leaf_pair = item.get("leaf_pair")
            vlans_here = item.get("vlans")

            if fabric_id not in fabrics_by_id:
                result.error(f"{actx}.fabric_id references unknown fabric: {fabric_id}")
                continue
            fabric = fabrics_by_id[fabric_id]

            if block not in ALLOWED_BLOCKS:
                result.error(f"{actx}.block must be one of {sorted(ALLOWED_BLOCKS)}")
                continue
            if block not in fabric.get("blocks", {}):
                result.error(f"{actx}.block '{block}' is not defined in fabric {fabric_id}")
                continue

            max_leaf_pairs = fabric["blocks"][block].get("leaf_pairs")
            if not _is_positive_int(leaf_pair):
                result.error(f"{actx}.leaf_pair must be a positive integer")
                continue
            if isinstance(max_leaf_pairs, int) and leaf_pair > max_leaf_pairs:
                result.error(
                    f"{actx}.leaf_pair {leaf_pair} exceeds defined leaf_pairs "
                    f"({max_leaf_pairs}) for fabric {fabric_id} block '{block}'"
                )

            target = (fabric_id, block, leaf_pair)
            if target in attachment_targets:
                result.error(
                    f"{actx} duplicates attachment target "
                    f"(fabric_id={fabric_id}, block='{block}', leaf_pair={leaf_pair})"
                )
            attachment_targets.add(target)

            if not isinstance(vlans_here, list) or not vlans_here:
                result.error(f"{actx}.vlans must be a non-empty list")
                continue

            seen_here: Set[int] = set()
            for vlan_id in vlans_here:
                if not isinstance(vlan_id, int):
                    result.error(f"{actx}.vlans contains non-integer value: {vlan_id!r}")
                    continue
                if vlan_id in seen_here:
                    result.error(f"{actx}.vlans repeats VLAN {vlan_id}")
                    continue
                seen_here.add(vlan_id)

                if vlan_id not in vlan_defs:
                    result.error(
                        f"{actx}.vlans references VLAN {vlan_id} not defined in tenant '{tenant_name}'"
                    )
                    continue

                used_vlans.add(vlan_id)
                vlan_fabrics.setdefault(vlan_id, set()).add(fabric_id)
                vlan_targets.setdefault(vlan_id, set()).add(target)

        # Every defined VLAN must be attached somewhere.
        for vlan_id in sorted(vlan_defs):
            if vlan_id not in used_vlans:
                result.error(
                    f"tenant '{tenant_name}' defines VLAN {vlan_id} but does not attach it anywhere"
                )

        # Class-specific semantics.
        for vlan_id, fabrics_used in sorted(vlan_fabrics.items()):
            vlan_class = _classify_vlan(vlan_id)
            if vlan_class == "local":
                # Local VLANs are fabric-local instances; repeating across fabrics is allowed.
                # No extra hard error here.
                pass
            elif vlan_class == "multisite":
                if len(fabrics_used) < 2:
                    result.error(
                        f"tenant '{tenant_name}' VLAN {vlan_id} is in multisite range "
                        f"but is attached in only {len(fabrics_used)} fabric(s): {sorted(fabrics_used)}"
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

            prefix = route.get("prefix")
            next_hop = route.get("next_hop")
            apply_to = route.get("apply_to")

            try:
                ipaddress.ip_network(prefix, strict=False)
            except Exception:
                result.error(f"{sctx}.prefix is not a valid IP prefix: {prefix!r}")

            try:
                ipaddress.ip_address(next_hop)
            except Exception:
                result.error(f"{sctx}.next_hop is not a valid IP address: {next_hop!r}")

            if not isinstance(apply_to, list) or not apply_to:
                result.error(f"{sctx}.apply_to must be a non-empty list")
                continue

            seen_apply_targets: Set[Tuple[int, str, int]] = set()
            for aidx, target in enumerate(apply_to, start=1):
                atctx = f"{sctx}.apply_to[{aidx}]"
                if not isinstance(target, dict):
                    result.error(f"{atctx} must be a mapping")
                    continue

                fabric_id = target.get("fabric_id")
                block = target.get("block")
                leaf_pair = target.get("leaf_pair")
                tgt = (fabric_id, block, leaf_pair)

                if fabric_id not in fabrics_by_id:
                    result.error(f"{atctx}.fabric_id references unknown fabric: {fabric_id}")
                    continue
                if block not in ALLOWED_BLOCKS:
                    result.error(f"{atctx}.block must be one of {sorted(ALLOWED_BLOCKS)}")
                    continue
                if not _is_positive_int(leaf_pair):
                    result.error(f"{atctx}.leaf_pair must be a positive integer")
                    continue
                if tgt in seen_apply_targets:
                    result.error(
                        f"{atctx} duplicates static route apply target "
                        f"(fabric_id={fabric_id}, block='{block}', leaf_pair={leaf_pair})"
                    )
                seen_apply_targets.add(tgt)

                # Route can only be applied where the tenant itself is attached.
                if tgt not in attachment_targets:
                    result.error(
                        f"{atctx} applies route to unattached target "
                        f"(fabric_id={fabric_id}, block='{block}', leaf_pair={leaf_pair}) "
                        f"for tenant '{tenant_name}'"
                    )


def validate(data: Dict[str, Any]) -> ValidationResult:
    result = ValidationResult()
    _validate_top_level(data, result)
    fabrics_by_id = _validate_fabrics(data, result)
    _validate_tenants(data, fabrics_by_id, result)
    return result


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("Usage: python validate_fabric.py /path/to/fabric.yaml", file=sys.stderr)
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
