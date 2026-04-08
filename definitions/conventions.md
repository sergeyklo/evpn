# EVPN/VXLAN Fabric Conventions (Final)

## 1. Naming Conventions

Leaf:
- Pattern: `az<fabric_id>-<block_type>-leaf-<leaf_pair_id>-<node_id>`
- Example: `az1-compute-leaf-01-1`

Spine:
- Pattern: `az<fabric_id>-<block_type>-spine-<spine_id>`
- Example: `az1-compute-spine-01`

Super Spine:
- Pattern: `az<fabric_id>-core-<id>`
- Example: `az1-core-01`

### Naming Rules
- Device naming is derived by the pipeline
- Device names must not be authored in `fabric.yaml`
- Naming must be deterministic for the same input

---

## 2. Intent Field Conventions

The canonical input file is `intent/fabric.yaml`.

### Top-level sections
The intent file must contain:
- `fabrics`
- `tenants`

### Fabric fields
Each fabric must include:
- `fabric_id`
- `name`
- `asn`
- `blocks`

### Block fields
Each block must include:
- `block_type`
- `leaf_pairs`
- `spines`

### Tenant fields
Each tenant must include:
- `tenant_name`
- `vrf_id`

Optional tenant fields:
- `description`
- `vlans`
- `attachment`

### VLAN fields
Each VLAN entry must include:
- `vlan_id`
- `name`
- `mode`

### Attachment fields
Each attachment entry must include:
- `fabric_id`
- `block_type`
- `leaf_pair_ids`
- `vlans`

Optional attachment fields:
- `static_routes`

### Forbidden in Intent
The following must not appear in `fabric.yaml` because they are derived by the pipeline:
- `device_name`
- `router_id`
- `loopback0`
- `loopback1`
- `p2p_subnet`
- `vni`
- `rd`
- `rt`
- `bgp_neighbors`
- `ospf`
- `interfaces`

---

## 3. VLAN Ranges

Fabric-local VLAN:
- `100–999`

Stretched VLAN:
- `1000–4094`

Native VLAN:
- `999`

vPC Peering VLAN:
- `900`

External Handoff (Super Spine):
- `700–710`

External Handoff (Leaf):
- `711–799`

---

## 4. VNI Rules

### L2VNI (6-digit format)

Local VLAN:
- `VNI = 2Axxxx`
- `A = Availability Zone ID`
- Derived from VLAN ID and fabric/site identity

Example:
- AZ1 VLAN 123 → 21123
- AZ2 VLAN 123 → 22123

Stretched VLAN:
- `VNI = 20xxxx`
- Same across all AZs

Example:
- VLAN 1200 → 201200

### L3VNI (5-digit format)

- `VNI = 30xxx`

Example:
- VRF ID 101 → 30101

---

## 5. VRF / Tenant Rules

- One Tenant = One VRF
- VRF name includes tenant name
- Each tenant must have:
  - `tenant_name`
  - `vrf_id` (numeric, unique)

VRF ID:
- Range: `1–9999`
- Must be globally unique

---

## 6. RD / RT Rules

RD:
- `<router_id>:<vni>`

RT:
- `target:<asn>:<vni>`

Import/Export:
- symmetric

---

## 7. Addressing

Loopback0 (Router ID):
- `10.6x.240.0/24`

Loopback1 (VTEP):
- `10.6x.241.0/24`

P2P Links:
- `10.6x.224.0/21`

Where:
- `x = AZ number (4,5,6 for AZ1, AZ2, AZ3)`

### Rules
- Loopbacks assigned per device sequentially
- P2P links use `/31`
- Allocation must be deterministic

---

## 8. ASN Rules

- One ASN per fabric (AZ)

Format:
- `6500x`

Example:
- AZ1 → `65001`
- AZ2 → `65002`

---

## 9. Uniqueness Rules

Device name:
- global

Tenant name:
- global

VRF name:
- global

VNI:
- global

VLAN:
- local VLAN → unique per fabric
- stretched VLAN → global

Loopback IP:
- global

P2P subnet:
- global

---

## 10. Interface Rules

Downlinks:
- `Eth1–46`

vPC Peer-Link:
- `Eth47–48`

Uplinks:
- `Eth49` and above

---

## 11. vPC Rules

- All Leafs operate in vPC pairs
- Each pair has:
  - vPC domain ID
  - peer-link (`Eth47–48`)
  - peer-keepalive

vPC Domain ID:
- unique per fabric
- derived by the pipeline

---

## 12. Multi-Site Rules

- Each fabric has:
  - unique ASN
  - site identity (AZ)

Super Spine:
- acts as Border Gateway

DCI:
- L3 connectivity between sites
- `/31` per link
- unique subnet per link

---

## 13. Design Principles

- Deterministic allocation
- YAML is the single source of truth
- No logic in templates
- All calculations happen in model layer
