# EVPN/VXLAN Fabric Architecture Definitions

## 1. Fabric Model
- 1 Fabric = 1 Site = 1 Availability Zone (AZ)
- System supports multiple interconnected fabrics (sites) via DCI
- All fabrics share the same topology pattern

## 2. Topology per Fabric
Each fabric consists of three layers:
- Leaf
- Spine
- Super Spine

Additionally, each fabric is divided into logical blocks:
- Compute
- Storage
- Object Storage

Each block has:
- its own Leaf switches
- its own Spine switches

Super Spine switches are shared across the entire fabric and interconnect Spine switches of all blocks.

## 3. Device Roles
### Leaf
- VTEP (VXLAN Tunnel Endpoint)
- Tenant attachment point
- Operates as part of a vPC pair

### Spine
- Underlay routing only
- Does NOT participate in EVPN overlay

### Super Spine
- EVPN Route Reflector (RR)
- Multisite Border Gateway
- Provides inter-site connectivity

## 4. Redundancy Model
- Leafs operate in vPC pairs
- Tenant attachment is defined per leaf pair
- Anycast gateways (SVI) are deployed on all attached leaf pairs

## 5. Routing Model
### Underlay
- Protocol: OSPF
- Area: 0 (single area design)

### Overlay
- Protocol: BGP EVPN
- Leaf switches peer only with Super Spine (RR)
- Spine switches do not participate in overlay

### ASN Model
- One ASN per fabric (site)
- Different fabrics use different ASNs

## 6. Tenant Model
- One Tenant = One VRF
- VRF name includes tenant name
- Tenant name is explicitly defined
- Description is optional

### Tenant Placement
- Tenant may exist in multiple fabrics (sites)
- Tenant may span multiple blocks (Compute / Storage / Object Storage)
- Tenant attachment is defined per leaf pair

## 7. VLAN Model
Two VLAN types are supported:
1. Fabric-local VLAN
2. Stretched VLAN

### VLAN Modes
- L2-only (no SVI)
- L3 (with SVI / Anycast Gateway)

## 8. VNI / RD / RT
- VNI is automatically allocated
- VNI must be globally unique across all fabrics
- RD and RT are automatically derived

## 9. Static Routes
- Optional
- Defined per tenant VRF
- Applied only to specific leaf pairs

## 10. Multi-Site / DCI
- Fabrics interconnected using Cisco Multi-Site
- Super Spine acts as Border Gateway
- DCI provides L3 connectivity between sites

## 11. Physical Design Rules
- Downlinks → lowest port numbers
- Uplinks → highest port numbers

## 12. Hardware
Leaf: Cisco Nexus N9K-C93180YC-FX3 (NX-OS 10.4(4))
Spine: Cisco Nexus N9K-C9364D-GX2A (NX-OS 10.4(4))
