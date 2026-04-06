# EVPN/VXLAN Fabric Conventions (Final)

## 1. Naming Conventions

Leaf: az<id>-<block>-leaf-<id>  
Spine: az<id>-<block>-spine-<id>  
Super Spine: az<id>-core-<id>  

---

## 2. VLAN Ranges

Fabric-local VLAN: 100–999  
Stretched VLAN: 1000–4094  

Native VLAN: 999  
vPC Peering VLAN: 900  

External Handoff (Super Spine): 700–710  
External Handoff (Leaf): 711–799  

---

## 3. VNI Rules

### L2VNI (6-digit format)

Local VLAN:
- VNI = 2A<VLAN_ID>
- A = Availability Zone ID

Example:
- AZ1 VLAN 123 → 21123
- AZ2 VLAN 123 → 22123

Stretched VLAN:
- VNI = 20<VLAN_ID>
- Same across all AZ

Example:
- VLAN 1200 → 201200

---

### L3VNI (5-digit format)

- VNI = 30<VRF_ID>

Example:
- VRF ID 101 → 30101

---

## 4. VRF / Tenant Rules

- One Tenant = One VRF
- VRF name includes tenant name
- Each tenant must have:
  - tenant_name
  - vrf_id (numeric, unique)

VRF ID:
- Range: 1–9999
- Must be globally unique

---

## 5. RD / RT Rules

RD:
- <Loopback0>:<VNI>

RT:
- target:<ASN>:<VNI>

Import/Export:
- symmetric

---

## 6. Addressing

Loopback0 (Router ID):
- 10.6x.240.0/24

Loopback1 (VTEP):
- 10.6x.241.0/24

P2P Links:
- 10.6x.224.0/21

Where:
- x = AZ number (4,5,6 for AZ1, AZ2, AZ3)

### Rules

- Loopbacks assigned per device sequentially
- P2P links use /31
- Allocation must be deterministic

---

## 7. ASN Rules

- One ASN per fabric (AZ)

Format:
- 6500<AZ_ID>

Example:
- AZ1 → 65001
- AZ2 → 65002

---

## 8. Uniqueness Rules

Device name: global  
Tenant name: global  
VRF name: global  
VNI: global  

VLAN:
- local VLAN → unique per fabric
- stretched VLAN → global

Loopback IP: global  
P2P subnet: global  

---

## 9. Interface Rules

Downlinks: Eth1–46  
vPC Peer-Link: Eth47–48  
Uplinks: Eth49 and above  

---

## 10. vPC Rules

- All Leafs operate in vPC pairs
- Each pair has:
  - vPC domain ID
  - peer-link (Eth47–48)
  - peer-keepalive

vPC Domain ID:
- unique per fabric

---

## 11. Multi-Site Rules

- Each fabric has:
  - unique ASN
  - site identity (AZ)

Super Spine:
- acts as Border Gateway

DCI:
- L3 connectivity between sites
- /31 per link
- unique subnet per link

---

## 12. Design Principles

- Deterministic allocation
- YAML is the single source of truth
- No logic in templates
- All calculations happen in model layer
